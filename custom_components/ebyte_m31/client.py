"""Small, asynchronous, read-only Modbus TCP client for EBYTE M31-U.

This module has no Home Assistant dependencies. Only FC02 and FC03 are exposed.
Register addresses come from the M31-U Series V1.4 user manual, sections
4.10.1, 4.10.6 and 4.10.7; addresses on the wire are zero based.
"""

from __future__ import annotations

import asyncio
import re
import struct
from dataclasses import dataclass

MODEL_REGISTER = 0x0C20
FIRMWARE_REGISTER = 0x0C2C
MAC_REGISTER = 0x7534
MODULE_REGISTER = 0x0C80
FAULT_REGISTER = 0x7587
# Only documented M31-U channel encodings are accepted (A means 16).
CHANNEL_COUNTS = {str(value): value for value in range(10)} | {"A": 16}


class M31Error(Exception):
    """Communication or identification failed."""


class ModbusError(M31Error):
    """The controller returned a Modbus exception response."""

    def __init__(self, function: int, code: int) -> None:
        self.function = function
        self.code = code
        super().__init__(f"Modbus function {function:02x}, exception {code:02x}")


class UnsupportedModel(M31Error):
    """The number of inputs cannot be determined from this model."""


@dataclass(frozen=True)
class ControllerInfo:
    """Stable controller identity and the configured DI count."""

    model: str
    input_count: int
    mac: str | None = None
    firmware: str | None = None
    modules: tuple[str, ...] = ()


def decode_string(registers: tuple[int, ...]) -> str:
    """Decode an EBYTE big-endian ASCII register string."""
    raw = struct.pack(f">{len(registers)}H", *registers)
    return raw.split(b"\0", 1)[0].decode("ascii", errors="replace").strip()


def inputs_for_model(model: str) -> int:
    """Get the host's DI count, without double-counting its internal slave."""
    # e.g. M31-AXXXA000G-U (16DI), M31-AXEX8080G-U (8DI).
    match = re.fullmatch(r"M31-[A-Z]{4}([0-9A]{4})G-U", model.upper())
    if match is None:
        raise UnsupportedModel(f"Unsupported M31-U host model: {model!r}")
    count = CHANNEL_COUNTS[match[1][0]]
    if count == 0:
        raise UnsupportedModel(f"The host {model} has no digital inputs")
    return count


def inputs_for_module(model: str) -> int:
    """Decode an internal/expansion card, including cards with no DI."""
    match = re.fullmatch(r"(?:M31-)?G[A-Z]{4}([0-9A]{4})-U", model.upper())
    if match is None:
        raise UnsupportedModel(f"Unsupported M31-U IO card: {model!r}")
    return CHANNEL_COUNTS[match[1][0]]


class M31Client:
    """Serialize reads on one TCP connection and reconnect after failures."""

    def __init__(
        self, host: str, port: int = 502, unit_id: int = 1, timeout: float = 5
    ) -> None:
        if not host or not 1 <= port <= 65535 or not 1 <= unit_id <= 255:
            raise ValueError("Invalid host, port or Modbus unit ID")
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.timeout = timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._transaction = 0
        self._lock = asyncio.Lock()

    def close(self) -> None:
        """Release the socket; the next read will reconnect."""
        if self._writer is not None:
            self._writer.close()
        self._reader = None
        self._writer = None

    async def _read(self, function: int, address: int, count: int) -> bytes:
        """Exchange one request, validating MBAP and the response PDU."""
        async with self._lock:
            try:
                async with asyncio.timeout(self.timeout):
                    if self._writer is None or self._writer.is_closing():
                        self._reader, self._writer = await asyncio.open_connection(
                            self.host, self.port
                        )
                    self._transaction = (self._transaction + 1) & 0xFFFF
                    transaction = self._transaction
                    self._writer.write(
                        struct.pack(
                            ">HHHBBHH",
                            transaction,
                            0,
                            6,
                            self.unit_id,
                            function,
                            address,
                            count,
                        )
                    )
                    await self._writer.drain()
                    assert self._reader is not None
                    header = await self._reader.readexactly(7)
                    reply_id, protocol, length, unit = struct.unpack(">HHHB", header)
                    if (
                        reply_id != transaction
                        or protocol != 0
                        or unit != self.unit_id
                        or not 3 <= length <= 254
                    ):
                        raise M31Error("Invalid Modbus TCP response header")
                    pdu = await self._reader.readexactly(length - 1)
                    if pdu[0] == function | 0x80:
                        if len(pdu) != 2:
                            raise M31Error("Malformed Modbus exception")
                        raise ModbusError(function, pdu[1])
                    if pdu[0] != function or pdu[1] != len(pdu) - 2:
                        raise M31Error("Invalid Modbus response function or byte count")
                    return pdu[2:]
            except ModbusError:
                # The complete exception frame was consumed; the stream is usable.
                raise
            except asyncio.CancelledError:
                self.close()
                raise
            except (
                OSError,
                TimeoutError,
                asyncio.IncompleteReadError,
                M31Error,
            ) as err:
                self.close()
                raise M31Error(f"Cannot read {self.host}:{self.port}: {err}") from err

    async def read_registers(self, address: int, count: int) -> tuple[int, ...]:
        """Read holding registers (FC03)."""
        if not 1 <= count <= 125 or not 0 <= address <= 65536 - count:
            raise ValueError("Invalid register range")
        payload = await self._read(3, address, count)
        if len(payload) != count * 2:
            self.close()
            raise M31Error("Wrong number of holding registers in response")
        return struct.unpack(f">{count}H", payload)

    async def read_inputs(self, count: int) -> tuple[bool, ...]:
        """Read DI1 onwards (FC02); input 1 is the least significant bit."""
        if not 1 <= count <= 512:
            raise ValueError("Input count must be between 1 and 512")
        payload = await self._read(2, 0, count)
        if len(payload) != (count + 7) // 8:
            self.close()
            raise M31Error("Wrong number of discrete inputs in response")
        return tuple(
            bool(payload[index // 8] & (1 << (index % 8))) for index in range(count)
        )

    async def read_state(self, count: int) -> tuple[bool, ...]:
        """Reject stale inputs when the controller reports a bus fault."""
        (fault,) = await self.read_registers(FAULT_REGISTER, 1)
        if fault:
            raise M31Error(
                f"Controller IO bus fault {fault}; input state is unavailable"
            )
        return await self.read_inputs(count)

    async def _identify_modules(self) -> tuple[str, ...]:
        """Read the documented 32-slot inventory, which includes the host card."""
        modules = []
        try:
            # At most 64 registers per frame, below the Modbus limit of 125.
            for start in range(0, 32, 8):
                registers = await self.read_registers(MODULE_REGISTER + start * 8, 64)
                for index in range(0, 64, 8):
                    model = decode_string(registers[index : index + 8])
                    if not model or model.upper() == "NONE":
                        return tuple(modules)
                    inputs_for_module(model)  # Reject unrecognized encodings.
                    modules.append(model)
        except ModbusError as err:
            if err.code not in (1, 2) or modules:
                raise
            # Older firmware may lack inventory registers; use the host only.
            return ()
        return tuple(modules)

    async def identify(self, input_count: int = 0) -> ControllerInfo:
        """Identify the host and validate its DI range with an actual read.

        An explicit input count includes all expansion inputs in bus order.
        The built-in IO card is slave ID 0, so the inventory already includes
        the host inputs and must never be added to the host input count.
        """
        if not 0 <= input_count <= 512:
            raise ValueError("Invalid input count override")
        try:
            model = decode_string(await self.read_registers(MODEL_REGISTER, 12))
        except ModbusError as err:
            if err.code not in (1, 2) or not input_count:
                raise
            model = "M31 (manual)"
        modules = ()
        if input_count:
            count = input_count
        else:
            host_count = inputs_for_model(model)
            modules = await self._identify_modules()
            if modules:
                # Confirm slot 0 is the internal card described by the host model.
                internal = re.sub(r"^(?:M31-)?G", "", modules[0].upper())
                expected = model.upper().removeprefix("M31-").removesuffix("G-U") + "-U"
                if internal != expected:
                    raise UnsupportedModel(
                        "IO slot 0 does not match the host model; use an explicit input count"
                    )
                count = sum(inputs_for_module(module) for module in modules)
            else:
                count = host_count
        mac = None
        firmware = None
        for address, size in ((MAC_REGISTER, 3), (FIRMWARE_REGISTER, 8)):
            try:
                registers = await self.read_registers(address, size)
            except ModbusError as err:
                if err.code not in (1, 2):
                    raise
                continue
            if address == MAC_REGISTER:
                raw = struct.pack(">3H", *registers)
                if raw not in (b"\0" * 6, b"\xff" * 6):
                    mac = ":".join(f"{byte:02x}" for byte in raw)
            else:
                firmware = decode_string(registers) or None
        await self.read_state(count)
        return ControllerInfo(model, count, mac, firmware, modules)
