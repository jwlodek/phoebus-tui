import pytest

from phoebus_tui.pv import PVManager, PVState


def test_default_value():
    assert PVManager().get("loc://a").state == PVState(value=0.0, connected=True)


@pytest.mark.parametrize(
    ("name", "value", "enum_strs"),
    [
        ("loc://a(5)", 5, ()),
        ("loc://a(1.5)", 1.5, ()),
        ('loc://a("text")', "text", ()),
        ("loc://a(1, 2, 3)", [1, 2, 3], ()),
        ('loc://a<VEnum>(1, "Low", "High")', 1, ("Low", "High")),
        ("loc://a<VString>(7)", "7", ()),
        ("loc://a<VLong>(3.0)", 3, ()),
        ("loc://a<VDouble>(3)", 3.0, ()),
        ("loc://a(unquoted)", "unquoted", ()),
    ],
)
def test_initializers(name, value, enum_strs):
    state = PVManager().get(name).state
    assert state.value == value
    assert state.enum_strs == enum_strs


def test_shared_by_base_name_and_initialized_once():
    pvs = PVManager()
    bare = pvs.get("loc://a")
    initialized = pvs.get("loc://a(5)")
    again = pvs.get("loc://a(9)")
    assert bare is initialized is again
    assert bare.state.value == 5


@pytest.mark.parametrize(
    ("name", "text", "expected"),
    [
        ("loc://i(1)", "0x10", 16),
        ("loc://f(1.0)", "2.5", 2.5),
        ('loc://e<VEnum>(0, "A", "B")', "B", 1),
        ('loc://s("x")', "y", "y"),
    ],
)
def test_put_converts_text(name, text, expected):
    pv = PVManager().get(name)
    pv.put(text)
    assert pv.state.value == expected
