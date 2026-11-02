import math

import pytest

from phoebus_tui.formatting import as_number, is_bit_on, with_bit
from phoebus_tui.pv import PVState


@pytest.mark.parametrize(
    ("value", "expected"),
    [(3, 3.0), ("3.5", 3.5), ([7, 8], 7.0), ([], None), ("x", None), (None, None)],
)
def test_as_number(value, expected):
    assert as_number(value) == expected


def test_is_bit_on():
    assert is_bit_on(PVState(value=0b100), 2)
    assert not is_bit_on(PVState(value=0b100), 1)
    assert is_bit_on(PVState(value=3.0), -1)
    assert not is_bit_on(PVState(value=0), -1)
    assert not is_bit_on(PVState(value=math.nan), -1)
    assert not is_bit_on(PVState(value="x"), 0)


def test_with_bit():
    assert with_bit(PVState(value=0b0101), 1, True) == 0b0111
    assert with_bit(PVState(value=0b0101), 0, False) == 0b0100
    assert with_bit(PVState(value=7), -1, True) == 1
    assert with_bit(PVState(value=7), -1, False) == 0
    assert with_bit(PVState(), 3, True) == 0b1000
