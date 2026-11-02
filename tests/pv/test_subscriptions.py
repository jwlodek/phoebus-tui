import logging

import pytest

from phoebus_tui.pv import PV, LocalPV


def test_subscribers_receive_updates_until_unsubscribed():
    pv = LocalPV("loc://x")
    seen = []
    unsubscribe = pv.subscribe(lambda state: seen.append(state.value))
    pv.put(1.5)
    unsubscribe()
    pv.put(2.5)
    assert seen == [1.5]
    unsubscribe()  # idempotent


def test_failing_subscriber_does_not_block_others(caplog):
    pv = LocalPV("loc://x")
    seen = []
    pv.subscribe(lambda state: 1 / 0)
    pv.subscribe(lambda state: seen.append(state.value))
    with caplog.at_level(logging.ERROR):
        pv.put(3.0)
    assert seen == [3.0]
    assert "Subscriber of loc://x failed" in caplog.text


def test_base_pv_is_read_only():
    with pytest.raises(PermissionError):
        PV("x").put(1)
