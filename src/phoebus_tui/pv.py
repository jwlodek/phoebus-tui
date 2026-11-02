"""Process variable backends: local (loc://), simulated (sim://), Channel Access and PV Access."""

from __future__ import annotations

import ast
import asyncio
import dataclasses
import logging
import math
import numbers
import random
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

NO_ALARM, MINOR, MAJOR, INVALID = 0, 1, 2, 3


@dataclass(frozen=True)
class PVState:
    value: Any = None
    connected: bool = False
    severity: int = NO_ALARM
    units: str = ""
    precision: int | None = None
    enum_strs: tuple[str, ...] = ()
    lower: float | None = None
    upper: float | None = None


Subscriber = Callable[[PVState], None]


class PV:
    """Base PV. Backends must call `_update` on the asyncio event loop thread."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.state = PVState()
        self._subscribers: list[Subscriber] = []

    def subscribe(self, callback: Subscriber) -> Callable[[], None]:
        """Call `callback` with the new state on every update. Returns an unsubscribe function."""
        self._subscribers.append(callback)

        def unsubscribe() -> None:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

        return unsubscribe

    def _update(self, **changes: Any) -> None:
        self.state = dataclasses.replace(self.state, **changes)
        for callback in list(self._subscribers):
            try:
                callback(self.state)
            except Exception:
                log.exception("Subscriber of %s failed", self.name)

    def put(self, value: Any) -> None:
        raise PermissionError(f"{self.name} is read-only")

    def close(self) -> None:
        pass


class UnavailablePV(PV):
    def __init__(self, name: str, reason: str) -> None:
        super().__init__(name)
        self.reason = reason

    def put(self, value: Any) -> None:
        raise ConnectionError(self.reason)


def _parse_args(text: str | None) -> list[Any]:
    if not text or not text.strip():
        return []
    try:
        return list(ast.literal_eval(f"({text},)"))
    except (ValueError, SyntaxError):
        return [part.strip() for part in text.split(",")]


_LOC_RE = re.compile(r"^(?P<name>[^<(]+)(?:<(?P<type>\w+)>)?(?:\((?P<args>.*)\))?$")


class LocalPV(PV):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.initialized = False
        self._update(value=0.0, connected=True)

    def initialize(self, vtype: str | None, args: list[Any]) -> None:
        self.initialized = True
        vtype = (vtype or "").lower()
        if vtype == "venum":
            index = int(args[0]) if args else 0
            self._update(value=index, enum_strs=tuple(str(a) for a in args[1:]))
        elif vtype == "vstring":
            self._update(value=str(args[0]) if args else "")
        elif vtype in ("vlong", "vint"):
            self._update(value=int(args[0]) if args else 0)
        elif vtype == "vdouble":
            self._update(value=float(args[0]) if args else 0.0)
        elif len(args) == 1:
            self._update(value=args[0])
        elif args:
            self._update(value=list(args))

    def put(self, value: Any) -> None:
        current = self.state.value
        if isinstance(value, str) and not isinstance(current, str):
            if self.state.enum_strs and value in self.state.enum_strs:
                value = self.state.enum_strs.index(value)
            elif isinstance(current, numbers.Integral):
                value = int(value, 0)
            elif isinstance(current, numbers.Real):
                value = float(value)
        self._update(value=value)


class SimPV(PV):
    """Subset of Phoebus sim:// PVs: sine, ramp, sawtooth, noise, gaussianNoise, flipflop, const."""

    _DEFAULTS: dict[str, list[float]] = {
        "sine": [-5, 5, 10, 1],
        "ramp": [-5, 5, 1, 1],
        "sawtooth": [-5, 5, 10, 1],
        "noise": [-5, 5, 1],
        "gaussiannoise": [0, 1, 0.1],
        "flipflop": [0.5],
        "const": [0],
    }

    def __init__(self, name: str, spec: str) -> None:
        super().__init__(name)
        match = re.match(r"^(\w+)(?:\((.*)\))?$", spec)
        func = match.group(1).lower() if match else spec.lower()
        if func not in self._DEFAULTS:
            raise ValueError(f"Unsupported simulated PV: sim://{spec}")
        args = _parse_args(match.group(2) if match else None)
        defaults = self._DEFAULTS[func]
        if func in ("sine", "ramp", "sawtooth") and len(args) == 3:
            # (min, max, update_seconds) form
            args = [args[0], args[1], defaults[2], args[2]]
        self.func = func
        self.args = [float(a) for a in args] + defaults[len(args):]
        self.period = max(self.args[-1], 0.01)
        self._count = 0
        lower, upper = (self.args[0], self.args[1]) if func not in ("flipflop", "const", "gaussiannoise") else (None, None)
        self._update(connected=True, precision=3, lower=lower, upper=upper, value=self._compute())
        self._loop = asyncio.get_running_loop()
        self._timer: asyncio.TimerHandle | None = None
        if func != "const":
            self._timer = self._loop.call_later(self.period, self._tick)

    def _compute(self) -> Any:
        a = self.args
        n = self._count
        match self.func:
            case "sine":
                mid, amp = (a[0] + a[1]) / 2, (a[1] - a[0]) / 2
                return mid + amp * math.sin(2 * math.pi * n / a[2])
            case "ramp":
                span = a[1] - a[0]
                return a[0] + (n * a[2]) % (span + a[2]) if span > 0 else a[0]
            case "sawtooth":
                return a[0] + (a[1] - a[0]) * ((n % a[2]) / a[2])
            case "noise":
                return random.uniform(a[0], a[1])
            case "gaussiannoise":
                return random.gauss(a[0], a[1])
            case "flipflop":
                return n % 2
            case _:
                return a[0]

    def _tick(self) -> None:
        self._count += 1
        self._update(value=self._compute())
        self._timer = self._loop.call_later(self.period, self._tick)

    def close(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None


class CAPV(PV):
    """Channel Access PV using aioca.

    aioca schedules work on the running asyncio loop, so this must be created from
    within the Textual app's event loop; callbacks then run on the UI thread.
    """

    def __init__(self, name: str) -> None:
        super().__init__(name)
        from aioca import FORMAT_CTRL, camonitor

        self._puts: set[asyncio.Task[Any]] = set()
        self._sub = camonitor(name, self._on_value, format=FORMAT_CTRL, notify_disconnect=True)

    def _on_value(self, value: Any) -> None:
        if not getattr(value, "ok", True):
            self._update(connected=False)
            return
        precision = getattr(value, "precision", None)
        self._update(
            value=value,
            connected=True,
            severity=int(getattr(value, "severity", 0) or 0),
            units=getattr(value, "units", "") or "",
            precision=int(precision) if precision is not None else None,
            enum_strs=tuple(getattr(value, "enums", ()) or ()),
            lower=getattr(value, "lower_disp_limit", None),
            upper=getattr(value, "upper_disp_limit", None),
        )

    def put(self, value: Any) -> None:
        from aioca import caput

        if not self.state.connected:
            raise ConnectionError(f"{self.name} is not connected")
        if isinstance(value, str) and value in self.state.enum_strs:
            value = self.state.enum_strs.index(value)
        task = asyncio.get_running_loop().create_task(caput(self.name, value))
        self._puts.add(task)
        task.add_done_callback(self._put_done)

    def _put_done(self, task: asyncio.Task[Any]) -> None:
        self._puts.discard(task)
        if not task.cancelled() and task.exception() is not None:
            log.error("Put to %s failed: %s", self.name, task.exception())

    def close(self) -> None:
        self._sub.close()
        for task in self._puts:
            task.cancel()


_pva_context: Any = None
_pva_lock = threading.Lock()


def _get_pva_context() -> Any:
    global _pva_context
    with _pva_lock:
        if _pva_context is None:
            from p4p.client.thread import Context

            _pva_context = Context("pva", nt=False)
    return _pva_context


def _field(value: Any, name: str, default: Any = None) -> Any:
    try:
        return value[name]
    except (KeyError, AttributeError, TypeError):
        return default


class PVAPV(PV):
    """PV Access PV using p4p. Must be created from within the running event loop."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self._loop = asyncio.get_running_loop()
        self._ctx = _get_pva_context()
        self._sub = self._ctx.monitor(name, self._on_monitor, notify_disconnect=True)

    def _on_monitor(self, value: Any) -> None:
        # p4p calls back on its own worker thread
        try:
            self._loop.call_soon_threadsafe(self._on_update, value)
        except RuntimeError:
            pass  # event loop already closed during shutdown

    def _on_update(self, value: Any) -> None:
        if isinstance(value, Exception):
            self._update(connected=False)
            return
        changes: dict[str, Any] = {"connected": True}
        index = _field(value, "value.index")
        if index is not None:
            changes["value"] = int(index)
            changes["enum_strs"] = tuple(_field(value, "value.choices", ()))
        else:
            changes["value"] = _field(value, "value")
        changes["severity"] = int(_field(value, "alarm.severity", 0) or 0)
        changes["units"] = _field(value, "display.units", "") or ""
        precision = _field(value, "display.precision", _field(value, "display.form.digits"))
        changes["precision"] = int(precision) if precision is not None else None
        changes["lower"] = _field(value, "display.limitLow")
        changes["upper"] = _field(value, "display.limitHigh")
        if changes["lower"] == changes["upper"]:
            changes["lower"] = changes["upper"] = None
        self._update(**changes)

    def put(self, value: Any) -> None:
        if not self.state.connected:
            raise ConnectionError(f"{self.name} is not connected")
        if self.state.enum_strs:
            if isinstance(value, str) and value in self.state.enum_strs:
                value = self.state.enum_strs.index(value)
            payload = {"value.index": int(value)}
        else:
            payload = {"value": value}

        def do_put() -> None:
            try:
                self._ctx.put(self.name, payload)
            except Exception:
                log.exception("Put to %s failed", self.name)

        threading.Thread(target=do_put, daemon=True).start()

    def close(self) -> None:
        self._sub.close()


class PVManager:
    """Creates and caches PVs by name."""

    def __init__(self, default_protocol: str = "ca") -> None:
        self.default_protocol = default_protocol
        self._pvs: dict[str, PV] = {}

    def get(self, name: str) -> PV:
        name = name.strip()
        if name.startswith("="):
            return self._pvs.setdefault(name, UnavailablePV(name, "Formula PVs are not supported"))
        proto, sep, rest = name.partition("://")
        if not sep:
            proto, rest = self.default_protocol, name
        proto = proto.lower()

        if proto == "loc":
            match = _LOC_RE.match(rest)
            base = match.group("name").strip() if match else rest
            key = f"loc://{base}"
            pv = self._pvs.get(key)
            if pv is None:
                pv = self._pvs[key] = LocalPV(key)
            if isinstance(pv, LocalPV) and not pv.initialized and match and match.group("args") is not None:
                pv.initialize(match.group("type"), _parse_args(match.group("args")))
            return pv

        key = f"{proto}://{rest}"
        if key in self._pvs:
            return self._pvs[key]
        pv = self._create(proto, rest, key)
        self._pvs[key] = pv
        return pv

    def _create(self, proto: str, rest: str, key: str) -> PV:
        try:
            if proto == "sim":
                return SimPV(key, rest)
            if proto == "ca":
                return CAPV(rest)
            if proto == "pva":
                return PVAPV(rest)
        except ImportError as e:
            return UnavailablePV(key, f"{e.name} is not installed")
        except Exception as e:
            return UnavailablePV(key, str(e))
        return UnavailablePV(key, f"Unsupported PV protocol: {proto}")

    def close(self) -> None:
        for pv in self._pvs.values():
            try:
                pv.close()
            except Exception:
                log.exception("Failed to close %s", pv.name)
        self._pvs.clear()
