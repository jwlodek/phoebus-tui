import asyncio

import pytest

from phoebus_tui.pv import PVManager, SimPV, UnavailablePV


async def test_sine_updates_on_its_own():
    pv = PVManager().get("sim://sine(0, 10, 20, 0.02)")
    assert isinstance(pv, SimPV)
    assert (pv.state.lower, pv.state.upper, pv.state.precision) == (0, 10, 3)
    seen = []
    pv.subscribe(lambda state: seen.append(state.value))
    await asyncio.sleep(0.15)
    assert len(set(seen)) > 2
    assert all(0 <= v <= 10 for v in seen)
    pv.close()


async def test_close_stops_updates():
    pv = PVManager().get("sim://ramp(0, 5, 1, 0.01)")
    pv.close()
    value = pv.state.value
    await asyncio.sleep(0.05)
    assert pv.state.value == value


async def test_const_never_updates():
    pv = PVManager().get("sim://const(4)")
    assert pv.state.value == 4
    assert pv._timer is None


@pytest.mark.parametrize(
    ("spec", "counts", "expected"),
    [
        ("ramp(0, 3, 1, 1)", [0, 1, 3, 4], [0, 1, 3, 0]),
        ("sawtooth(0, 10, 5, 1)", [0, 1, 5], [0, 2, 0]),
        ("flipflop(1)", [0, 1, 2], [0, 1, 0]),
        ("sine(-1, 1, 1)", [0], [0.0]),
    ],
)
async def test_waveforms(spec, counts, expected):
    pv = PVManager().get(f"sim://{spec}")
    values = []
    for count in counts:
        pv._count = count
        values.append(pv._compute())
    pv.close()
    assert values == pytest.approx(expected)


async def test_noise_stays_in_range():
    pv = PVManager().get("sim://noise(2, 3, 1)")
    assert all(2 <= pv._compute() <= 3 for _ in range(50))
    gaussian = PVManager().get("sim://gaussianNoise")
    assert gaussian.state.lower is None
    pv.close()
    gaussian.close()


async def test_unsupported_function():
    assert isinstance(PVManager().get("sim://bogus"), UnavailablePV)


async def test_read_only():
    pv = PVManager().get("sim://const(1)")
    with pytest.raises(PermissionError):
        pv.put(2)
