"""Isolated module loading and a real local TCP Modbus simulator."""

import asyncio
import contextlib
import importlib.util
import struct
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "ebyte_m31"
if (ROOT / ".test-deps").exists():
    sys.path.insert(0, str(ROOT / ".test-deps"))


def load_part(name):
    """Load transport without importing Home Assistant's integration entry point."""
    package = "m31_test"
    if package not in sys.modules:
        module = ModuleType(package)
        module.__path__ = [str(COMPONENT)]
        sys.modules[package] = module
    qualified = f"{package}.{name}"
    if qualified not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            qualified, COMPONENT / f"{name}.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[qualified] = module
        spec.loader.exec_module(module)
    return sys.modules[qualified]


def string_registers(text, count):
    return struct.unpack(f">{count}H", text.encode("ascii").ljust(count * 2, b"\0"))


class ModbusSimulator:
    """Validate requests and serve the published M31-U register map."""

    def __init__(self):
        self.inputs = [False] * 16
        self.registers = {}
        self.set_registers(0x0C20, string_registers("M31-AXXXA000G-U", 12))
        self.set_registers(0x0C2C, string_registers("9232-0-13", 8))
        self.set_registers(0x7534, (0x0211, 0x2233, 0x4455))
        self.set_registers(0x7587, (0,))
        self.set_modules(["GAXXXA000-U"])
        self.requests = []
        self.writers = set()
        self.tasks = set()
        self.connections = 0
        self.delay = 0
        self.fragment = False
        self.hook = None

    def set_registers(self, address, values):
        self.registers.update(
            (address + index, value) for index, value in enumerate(values)
        )

    def set_modules(self, modules):
        for index in range(32):
            model = modules[index] if index < len(modules) else "NONE"
            self.set_registers(0x0C80 + index * 8, string_registers(model, 8))

    def use_legacy_register_map(self, input_count=16):
        """Expose only registers documented by M31 Series V1.1-EN."""
        self.registers = {
            address: value
            for address, value in self.registers.items()
            if 0x7534 <= address < 0x7537 or address == 0x7587
        }
        self.inputs = [False] * input_count
        self.requests.clear()

    async def start(self):
        self.server = await asyncio.start_server(self.handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def stop(self):
        self.server.close()
        await self.server.wait_closed()
        for writer in list(self.writers):
            writer.close()
        for task in list(self.tasks):
            task.cancel()
        await asyncio.gather(*list(self.tasks), return_exceptions=True)

    async def handle(self, reader, writer):
        task = asyncio.current_task()
        self.tasks.add(task)
        self.writers.add(writer)
        self.connections += 1
        try:
            while True:
                request = await reader.readexactly(12)
                transaction, protocol, length, unit, function, address, count = (
                    struct.unpack(">HHHBBHH", request)
                )
                assert protocol == 0 and length == 6
                assert function in (2, 3), (
                    "Integration must never write to the controller"
                )
                self.requests.append((unit, function, address, count))
                if self.delay:
                    await asyncio.sleep(self.delay)
                if function == 2 and count <= len(self.inputs):
                    payload = bytearray((count + 7) // 8)
                    for index, state in enumerate(self.inputs[:count]):
                        if state:
                            payload[index // 8] |= 1 << (index % 8)
                    pdu = bytes((2, len(payload))) + payload
                elif function == 3 and all(
                    address + i in self.registers for i in range(count)
                ):
                    values = [self.registers[address + i] for i in range(count)]
                    pdu = bytes((3, count * 2)) + struct.pack(f">{count}H", *values)
                else:
                    pdu = bytes((function | 0x80, 2))
                response = (
                    struct.pack(">HHHB", transaction, 0, len(pdu) + 1, unit) + pdu
                )
                if self.hook:
                    response = self.hook(request, response)
                if response is None:
                    break
                if self.fragment:
                    for index in range(0, len(response), 3):
                        writer.write(response[index : index + 3])
                        await writer.drain()
                        await asyncio.sleep(0)
                else:
                    writer.write(response)
                    await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError, asyncio.CancelledError):
            pass
        finally:
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()
            self.writers.discard(writer)
            self.tasks.discard(task)
