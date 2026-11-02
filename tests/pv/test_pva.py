import asyncio
import threading

import pytest

from phoebus_tui.pv import PVAPV, PVState


def test_scalar(bare_pv):
    pv = bare_pv(PVAPV, "X")
    pv._on_update({
        "value": 1.5,
        "alarm.severity": 2,
        "display.units": "V",
        "display.precision": 3,
        "display.limitLow": 0.0,
        "display.limitHigh": 10.0,
    })
    assert pv.state == PVState(value=1.5, connected=True, severity=2, units="V", precision=3, lower=0.0, upper=10.0)


def test_enum_and_equal_limits(bare_pv):
    pv = bare_pv(PVAPV, "X")
    pv._on_update({"value.index": 1, "value.choices": ["A", "B"], "display.limitLow": 0, "display.limitHigh": 0})
    assert (pv.state.value, pv.state.enum_strs) == (1, ("A", "B"))
    assert (pv.state.lower, pv.state.upper) == (None, None)


def test_disconnect(bare_pv):
    pv = bare_pv(PVAPV, "X")
    pv._on_update({"value": 1})
    pv._on_update(RuntimeError("Disconnected"))
    assert not pv.state.connected


async def test_monitor_callbacks_are_moved_onto_the_event_loop(bare_pv):
    pv = bare_pv(PVAPV, "X")
    pv._loop = asyncio.get_running_loop()
    threads = []
    pv.subscribe(lambda state: threads.append(threading.current_thread()))
    worker = threading.Thread(target=pv._on_monitor, args=({"value": 1},))
    worker.start()
    worker.join()
    await asyncio.sleep(0.01)
    assert threads == [threading.main_thread()]


def test_put_requires_connection(bare_pv):
    pv = bare_pv(PVAPV, "X")
    with pytest.raises(ConnectionError):
        pv.put(1)
