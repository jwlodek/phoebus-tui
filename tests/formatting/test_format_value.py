import math

import pytest

from phoebus_tui.formatting import BINARY, COMPACT, DECIMAL, ENGINEERING, EXPONENTIAL, HEX, STRING, format_value
from phoebus_tui.pv import PVState


def test_none_is_empty():
    assert format_value(PVState(value=None)) == ""


def test_strings_and_bytes_pass_through():
    assert format_value(PVState(value="hello", units="mm")) == "hello"
    assert format_value(PVState(value=b"bytes")) == "bytes"


def test_enum_label():
    state = PVState(value=1, enum_strs=("Off", "On"))
    assert format_value(state) == "On"
    assert format_value(state, STRING) == "On"


def test_enum_index_out_of_range():
    assert format_value(PVState(value=5, enum_strs=("Off", "On"))) == "5"


def test_enum_with_decimal_format_shows_number():
    assert format_value(PVState(value=1, enum_strs=("Off", "On")), DECIMAL) == "1"


def test_precision_from_widget_overrides_pv():
    state = PVState(value=3.14159, precision=4)
    assert format_value(state, DECIMAL, 2) == "3.14"
    assert format_value(state, DECIMAL, -1) == "3.1416"


def test_default_without_precision():
    assert format_value(PVState(value=3.14159265)) == "3.14159"


def test_units():
    state = PVState(value=2.5, precision=1, units="mm")
    assert format_value(state) == "2.5 mm"
    assert format_value(state, show_units=False) == "2.5"


def test_integers_and_bools():
    assert format_value(PVState(value=42)) == "42"
    assert format_value(PVState(value=True)) == "true"


@pytest.mark.parametrize(
    ("fmt", "value", "precision", "expected"),
    [
        (HEX, 255, -1, "0xFF"),
        (BINARY, 5, -1, "0b101"),
        (EXPONENTIAL, 1234.5, 2, "1.23E+03"),
        (ENGINEERING, 12500.0, 2, "12.50E3"),
        (ENGINEERING, 0.0, 3, "0.000E0"),
        (COMPACT, 0.000012345, -1, "1.2345e-05"),
    ],
)
def test_formats(fmt, value, precision, expected):
    assert format_value(PVState(value=value), fmt, precision) == expected


def test_non_finite():
    assert format_value(PVState(value=math.nan)) == "nan"


def test_arrays():
    assert format_value(PVState(value=[1, 2, 3])) == "[1, 2, 3]"
    assert format_value(PVState(value=list(range(40)))).endswith(", ...]")


def test_char_array_as_string():
    assert format_value(PVState(value=[72, 105, 0, 0]), STRING) == "Hi"


def test_non_numeric_objects():
    assert format_value(PVState(value=object())).startswith("<object")
