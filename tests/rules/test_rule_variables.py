from phoebus_tui.pv import MAJOR, PVState
from phoebus_tui.rules import rule_variables


def test_rule_variables():
    variables = rule_variables([
        PVState(value=2.7, connected=True, severity=MAJOR, precision=1),
        PVState(value=1, connected=True, enum_strs=("Off", "On")),
        PVState(value="text", connected=True),
        PVState(),
    ])
    assert variables["pv0"] == 2.7
    assert variables["pvInt0"] == 2
    assert variables["pvStr0"] == "2.7"
    assert variables["pvSev0"] == MAJOR
    assert variables["pv1"] == 1.0
    assert variables["pvStr1"] == "On"
    assert variables["pv2"] == "text"
    assert variables["pvInt2"] == 0
    assert variables["pvSev3"] == -1
