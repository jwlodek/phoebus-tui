from types import SimpleNamespace

from phoebus_tui.pv import CAPV


def test_augmented_value(bare_pv):
    pv = bare_pv(CAPV, "X")
    pv._on_value(SimpleNamespace(
        ok=True, severity=1, units="mA", precision=2, enums=[], lower_disp_limit=0, upper_disp_limit=5
    ))
    assert pv.state.connected
    assert (pv.state.severity, pv.state.units, pv.state.precision) == (1, "mA", 2)
    assert (pv.state.lower, pv.state.upper) == (0, 5)


def test_enum_and_disconnect(bare_pv):
    pv = bare_pv(CAPV, "X")
    pv._on_value(SimpleNamespace(ok=True, enums=["A", "B"]))
    assert pv.state.enum_strs == ("A", "B")
    assert pv.state.precision is None
    pv._on_value(SimpleNamespace(ok=False))
    assert not pv.state.connected
