"""Typed IO snapshots and strictly addressed Modbus output commands."""

import math
import struct
from dataclasses import dataclass

from .errors import M31Error

AI_RANGE = 0x0DAC
AO_RANGE = 0x1194
PT_VALUES = 0x0DAC
PT_UNITS = 0x39A4
PT_ERRORS = {
    32766: "disconnected",
    -32766: "short_circuit",
    32765: "chip_fault",
    32767: "overflow",
    -32768: "underflow",
    -32767: "disabled",
}


def signed(value: int) -> int:
    return value - 65536 if value & 0x8000 else value


def ao_limits(kind: str, mode: int) -> tuple[float, float]:
    if kind not in ("current", "voltage") or mode not in (0, 1):
        raise M31Error("Unsupported analog output type or range")
    return (
        (4.0 if mode else 0.0, 20.0)
        if kind == "current"
        else (0.0, 5.0 if mode else 10.0)
    )


@dataclass(frozen=True)
class IOState:
    di: tuple[bool, ...] = ()
    do: tuple[bool, ...] = ()
    ai: tuple[float, ...] = ()
    ao: tuple[float, ...] = ()
    pt: tuple[float | None, ...] = ()
    ai_ranges: tuple[int, ...] = ()
    ao_ranges: tuple[int, ...] = ()
    pt_status: tuple[str, ...] = ()

    def __getitem__(self, index):
        return self.di[index]


class IOMixin:
    """Shared registers and write semantics documented by both series."""

    async def _block(self, function: int, address: int, count: int) -> tuple[int, ...]:
        result = []
        for offset in range(0, count, 125):
            size = min(125, count - offset)
            payload = await self._read(function, address + offset, size)
            if len(payload) != size * 2:
                self.close()
                raise M31Error("Wrong number of registers in IO response")
            result.extend(struct.unpack(f">{size}H", payload))
        return tuple(result)

    async def read_coils(self, count: int) -> tuple[bool, ...]:
        if not 1 <= count <= 512:
            raise ValueError("Invalid DO count")
        payload = await self._read(1, 0, count)
        if len(payload) != (count + 7) // 8:
            self.close()
            raise M31Error("Wrong number of coils in response")
        return tuple(bool(payload[i // 8] & (1 << (i % 8))) for i in range(count))

    async def _health(self) -> None:
        (fault,) = await self.read_registers(0x7587, 1)
        if fault:
            raise M31Error(f"Controller IO bus fault {fault}; IO is unavailable")

    async def read_io(self, info) -> IOState:
        """Read a complete snapshot; this method never writes to hardware."""
        async with self._io_lock:
            await self._health()
            layout = info.io_layout
            di = await self.read_inputs(layout.di) if layout.di else ()
            do = await self.read_coils(layout.do) if layout.do else ()
            ai_ranges = await self._block(3, AI_RANGE, len(layout.ai))
            for kind, mode in zip(layout.ai, ai_ranges, strict=True):
                if mode not in range(7) or (kind == "voltage") != (mode >= 3):
                    raise M31Error("AI range does not match the configured module type")
            ai = tuple(
                signed(raw) / 1000 for raw in await self._block(4, 0, len(layout.ai))
            )
            ao_ranges = await self._block(3, AO_RANGE, len(layout.ao))
            for kind, mode in zip(layout.ao, ao_ranges, strict=True):
                ao_limits(kind, mode)
            ao = tuple(raw / 1000 for raw in await self._block(3, 0, len(layout.ao)))
            pt_raw = await self._block(4, PT_VALUES, layout.pt)
            units = await self._block(3, PT_UNITS, layout.pt)
            temperatures, status = [], []
            for raw, unit in zip(pt_raw, units, strict=True):
                if unit not in (0, 1, 2):
                    raise M31Error("Invalid PT100 temperature unit")
                raw = signed(raw)
                state = PT_ERRORS.get(raw, "normal")
                value = raw / 10
                if unit == 1:
                    value = (value - 32) / 1.8
                elif unit == 2:
                    value -= 273.15
                temperatures.append(round(value, 3) if state == "normal" else None)
                status.append(state)
            return IOState(
                di, do, ai, ao, tuple(temperatures), ai_ranges, ao_ranges, tuple(status)
            )

    async def set_do(self, info, index: int, state: bool) -> None:
        """Write exactly one known DO and validate the FC05 echo."""
        if not 0 <= index < info.io_layout.do or not isinstance(state, bool):
            raise ValueError("Invalid digital output")
        async with self._io_lock:
            await self._health()
            command = struct.pack(">HH", index, 0xFF00 if state else 0)
            if await self._exchange(5, command) != command:
                self.close()
                raise M31Error("Digital output write was not acknowledged correctly")

    async def set_ao(self, info, index: int, value: float) -> None:
        """Check the live range then write one engineering-value register (FC16)."""
        if (
            not 0 <= index < len(info.io_layout.ao)
            or isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError("Invalid analog output value or channel")
        async with self._io_lock:
            await self._health()
            (mode,) = await self.read_registers(AO_RANGE + index, 1)
            minimum, maximum = ao_limits(info.io_layout.ao[index], mode)
            if not minimum <= value <= maximum:
                raise ValueError(f"Output must be between {minimum} and {maximum}")
            raw = int(round(value * 1000))
            command = struct.pack(">HHBH", index, 1, 2, raw)
            if await self._exchange(16, command) != struct.pack(">HH", index, 1):
                self.close()
                raise M31Error("Analog output write was not acknowledged correctly")
