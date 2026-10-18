"""Documented M31/M31-U model encoding and IO inventories."""

import re
from dataclasses import dataclass

from .errors import UnsupportedModel

COUNTS = {str(value): value for value in range(10)} | {"A": 16}
LEGACY_HOSTS = (
    "M31-AAAX4440G",
    "M31-AXXX8000G",
    "M31-XXAX0080G",
    "M31-AXAX4040G",
    "M31-AXXXA000G",
    "M31-XXAX00A0G",
    "M31-AXAX8080G",
    "M31-XAXX0800G",
    "M31-XXXA0008G",
    "M31-XAXA0404G",
    "M31-XFXX0800G",
    "M31-XGXX0800G",
)
U_HOSTS = (
    "M31-AFAX4440G-U",
    "M31-AXAX8080G-U",
    "M31-AXXX8000G-U",
    "M31-AXXXA000G-U",
    "M31-AXEX8080G-U",
    "M31-XXAX00A0G-U",
    "M31-XXEX00A0G-U",
    "M31-AXAX4040G-U",
    "M31-XFXX0800G-U",
    "M31-XAXX0A00G-U",
    "M31-XBXX0A00G-U",
    "M31-XXXA0008G-U",
    "M31-XXXB0008G-U",
    "M31-XDXX0600G-U",
)
HOST_MODELS = (*LEGACY_HOSTS, *U_HOSTS)


@dataclass(frozen=True)
class IOLayout:
    """Channel order is independent and contiguous within each IO register area."""

    di: int = 0
    do: int = 0
    ai: tuple[str, ...] = ()
    ao: tuple[str, ...] = ()
    pt: int = 0

    def __add__(self, other):
        return IOLayout(
            self.di + other.di,
            self.do + other.do,
            self.ai + other.ai,
            self.ao + other.ao,
            self.pt + other.pt,
        )


def model_layout(model: str, module: bool = False) -> IOLayout:
    """Decode DI/AI/DO/AO counts and electrical types from the model name."""
    name = model.strip().upper()
    if module:
        match = re.fullmatch(r"(?:M31-)?G([A-Z]{4})([0-9A]{4})(?:-U)?", name)
    else:
        match = re.fullmatch(r"M31-([A-Z]{4})([0-9A]{4})G(?:-U)?", name)
    if match is None:
        raise UnsupportedModel(
            f"Unsupported M31 {'card' if module else 'host'}: {model!r}"
        )
    features, counts = match.groups()
    for feature, code, allowed in zip(
        features, counts, ("AX", "ABDFGX", "AEX", "ABX"), strict=True
    ):
        if feature not in allowed or ((feature == "X") != (code == "0")):
            raise UnsupportedModel(f"Inconsistent M31 IO encoding: {model}")
    di, ai, do, ao = (COUNTS[code] for code in counts)
    ai_kind = "voltage" if features[1] in "BG" else "current"
    ao_kind = "voltage" if features[3] == "B" else "current"
    return IOLayout(
        di,
        do,
        () if features[1] == "D" else (ai_kind,) * ai,
        (ao_kind,) * ao,
        ai if features[1] == "D" else 0,
    )


def parse_expansions(value: str | list[str] | tuple[str, ...]) -> tuple[str, ...]:
    """Accept card model names in physical bus order, without the internal card."""
    if isinstance(value, str):
        values = re.split(r"[,;\s]+", value.strip()) if value.strip() else []
    else:
        values = value
    if len(values) > 32:
        raise UnsupportedModel("Too many expansion cards")
    result = tuple(item.strip().upper() for item in values)
    for model in result:
        model_layout(model, module=True)
    return result


def combine(models: tuple[str, ...], module: bool = False) -> IOLayout:
    layout = IOLayout()
    for model in models:
        layout += model_layout(model, module=module)
    if max(layout.di, layout.do, len(layout.ai), len(layout.ao), layout.pt) > 512:
        raise UnsupportedModel("IO channel count exceeds 512 per type")
    return layout
