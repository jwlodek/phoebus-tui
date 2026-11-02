import pytest

from phoebus_tui.formatting import parse_input
from phoebus_tui.pv import PVState


def test_strips_units():
    assert parse_input(" 2.5 mm ", PVState(value=1.0, units="mm")) == 2.5


def test_enum_by_label_or_index():
    state = PVState(value=0, enum_strs=("Off", "On"))
    assert parse_input("On", state) == 1
    assert parse_input("0", state) == 0


def test_enum_rejects_unknown_label():
    with pytest.raises(ValueError):
        parse_input("Maybe", PVState(value=0, enum_strs=("Off", "On")))


def test_integer_pv():
    assert parse_input("0x10", PVState(value=1)) == 16
    assert parse_input("2.7", PVState(value=1)) == 2


def test_float_pv():
    assert parse_input("1e3", PVState(value=1.5)) == 1000.0
    with pytest.raises(ValueError):
        parse_input("abc", PVState(value=1.5))


def test_string_and_array_pvs_keep_text():
    assert parse_input("abc", PVState(value="x")) == "abc"
    assert parse_input("1 2", PVState(value=[1, 2])) == "1 2"


def test_unknown_type_guesses():
    assert parse_input("5", PVState()) == 5
    assert parse_input("5.5", PVState()) == 5.5
    assert parse_input("abc", PVState()) == "abc"
