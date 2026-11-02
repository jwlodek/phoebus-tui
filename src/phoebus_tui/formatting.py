"""Value formatting and parsing following the Phoebus text widget `format` property."""

from __future__ import annotations

import math
import numbers
from typing import Any

from .pv import INVALID, MAJOR, MINOR, PVState

# Phoebus FormatOption ordinals
DEFAULT, DECIMAL, EXPONENTIAL, ENGINEERING, HEX, COMPACT, STRING = range(7)
BINARY = 10

ALARM_COLORS = {MINOR: "#ff8000", MAJOR: "#ff0000", INVALID: "#ff00ff"}
DISCONNECTED_COLOR = "#c800c8"


def _is_sequence(value: Any) -> bool:
    return hasattr(value, "__len__") and not isinstance(value, (str, bytes))


def _format_number(value: Any, fmt: int, precision: int | None) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if fmt == HEX:
        return f"0x{int(value):X}"
    if fmt == BINARY:
        return f"0b{int(value):b}"
    if isinstance(value, numbers.Integral) and fmt not in (EXPONENTIAL, ENGINEERING):
        return str(int(value))
    value = float(value)
    if not math.isfinite(value):
        return str(value)
    if fmt == EXPONENTIAL:
        return f"{value:.{precision if precision is not None else 4}E}"
    if fmt == ENGINEERING:
        p = precision if precision is not None else 3
        if value == 0:
            return f"{0:.{p}f}E0"
        exponent = int(math.floor(math.log10(abs(value)) / 3) * 3)
        return f"{value / 10**exponent:.{p}f}E{exponent}"
    if fmt == COMPACT:
        return f"{value:.{max(precision or 6, 1)}g}"
    if precision is None:
        return f"{value:.6g}"
    return f"{value:.{precision}f}"


def format_value(state: PVState, fmt: int = DEFAULT, precision: int = -1, show_units: bool = True) -> str:
    value = state.value
    if value is None:
        return ""
    prec = precision if precision >= 0 else state.precision
    if isinstance(value, bytes):
        value = value.decode(errors="replace")
    if isinstance(value, str):
        return value
    if state.enum_strs and isinstance(value, numbers.Integral) and fmt in (DEFAULT, STRING):
        index = int(value)
        return state.enum_strs[index] if 0 <= index < len(state.enum_strs) else str(index)
    if _is_sequence(value):
        items = list(value)
        if fmt == STRING:
            return "".join(chr(int(c)) for c in items if int(c) != 0)
        text = ", ".join(_format_number(v, fmt, prec) for v in items[:32])
        return f"[{text}{', ...' if len(items) > 32 else ''}]"
    if not isinstance(value, numbers.Number):
        return str(value)
    text = _format_number(value, fmt, prec)
    if show_units and state.units:
        text = f"{text} {state.units}"
    return text


def parse_input(text: str, state: PVState) -> Any:
    """Convert user text into a value suitable for writing to a PV with the given state."""
    text = text.strip()
    if state.units and text.endswith(state.units):
        text = text[: -len(state.units)].strip()
    current = state.value
    if state.enum_strs:
        if text in state.enum_strs:
            return state.enum_strs.index(text)
        return int(text, 0)
    if isinstance(current, str) or _is_sequence(current):
        return text
    if isinstance(current, numbers.Integral) and not isinstance(current, bool):
        try:
            return int(text, 0)
        except ValueError:
            return int(float(text))
    if isinstance(current, numbers.Real):
        return float(text)
    for convert in (lambda t: int(t, 0), float):
        try:
            return convert(text)
        except ValueError:
            pass
    return text


def as_number(value: Any) -> float | None:
    if _is_sequence(value):
        value = value[0] if len(value) else None
    if isinstance(value, numbers.Number):
        return float(value)  # type: ignore[arg-type]
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def is_bit_on(state: PVState, bit: int) -> bool:
    number = as_number(state.value)
    if number is None or math.isnan(number):
        return False
    if bit < 0:
        return number != 0
    return bool((int(number) >> bit) & 1)


def with_bit(state: PVState, bit: int, on: bool) -> int:
    if bit < 0:
        return 1 if on else 0
    current = int(as_number(state.value) or 0)
    return current | (1 << bit) if on else current & ~(1 << bit)
