import builtins
import logging

import pytest

from phoebus_tui.pv import CAPV, PVManager, UnavailablePV


def test_formula_pvs_are_unavailable():
    pv = PVManager().get("=pv1 + 1")
    assert isinstance(pv, UnavailablePV)
    with pytest.raises(ConnectionError, match="Formula"):
        pv.put(1)


def test_unknown_protocol():
    pv = PVManager().get("foo://bar")
    assert isinstance(pv, UnavailablePV)
    assert "Unsupported PV protocol" in pv.reason


def test_sim_requires_event_loop():
    assert isinstance(PVManager().get("sim://sine"), UnavailablePV)


def test_cache_and_close():
    pvs = PVManager()
    pv = pvs.get(" loc://a ")
    assert pvs.get("loc://a") is pv
    pvs.close()
    assert pvs.get("loc://a") is not pv


def test_close_logs_failures(caplog):
    pvs = PVManager()
    pv = pvs.get("loc://a")
    pv.close = lambda: 1 / 0
    with caplog.at_level(logging.ERROR):
        pvs.close()
    assert "Failed to close loc://a" in caplog.text


async def test_default_protocol_is_ca():
    pvs = PVManager()
    pv = pvs.get("PHOEBUSTUI:TEST:DOES:NOT:EXIST")
    assert isinstance(pv, CAPV)
    assert pvs.get("ca://PHOEBUSTUI:TEST:DOES:NOT:EXIST") is pv
    assert not pv.state.connected
    with pytest.raises(ConnectionError):
        pv.put(1)
    pvs.close()


def test_missing_backend_library(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "aioca":
            raise ImportError(name=name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    pv = PVManager().get("ca://X")
    assert isinstance(pv, UnavailablePV)
    assert pv.reason == "aioca is not installed"
