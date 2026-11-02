"""Fixtures for building .bob files and driving the Textual app headlessly."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from xml.sax.saxutils import escape

import pytest
from textual import events
from textual.pilot import Pilot
from textual.widget import Widget

from phoebus_tui.app import PhoebusTuiApp
from phoebus_tui.layout import Scale
from phoebus_tui.model import Node, load_display
from phoebus_tui.pv import PVManager

AppRunner = Callable[..., AbstractAsyncContextManager[tuple[PhoebusTuiApp, Pilot, PVManager]]]


@pytest.fixture
def examples_dir() -> Path:
    return Path(__file__).parent.parent / "examples"


@pytest.fixture
def make_color() -> Callable[..., str]:
    def make(tag: str, red: int, green: int, blue: int, alpha: int = 255) -> str:
        return f'<{tag}><color red="{red}" green="{green}" blue="{blue}" alpha="{alpha}"/></{tag}>'

    return make


@pytest.fixture
def make_widget() -> Callable[..., str]:
    """XML for a widget; keyword props become simple tags, `raw` is appended verbatim."""

    def make(wtype: str, raw: str = "", **props: object) -> str:
        tags = "".join(f"<{key}>{escape(str(value))}</{key}>" for key, value in props.items())
        return f'<widget type="{wtype}" version="2.0.0">{tags}{raw}</widget>'

    return make


@pytest.fixture
def make_display() -> Callable[..., str]:
    def make(*widgets: str, name: str | None = "Test", width: int = 400, height: int = 300, raw: str = "") -> str:
        name_tag = f"<name>{escape(name)}</name>" if name is not None else ""
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<display version="2.0.0">{name_tag}<width>{width}</width><height>{height}</height>'
            f'{raw}{"".join(widgets)}</display>'
        )

    return make


@pytest.fixture
def make_rule() -> Callable[..., str]:
    def make(prop_id: str, bool_exp: str, value: str, pv: str, out_exp: bool = False) -> str:
        return (
            f'<rules><rule name="r" prop_id="{prop_id}" out_exp="{str(out_exp).lower()}">'
            f'<exp bool_exp="{escape(bool_exp)}"><value>{value}</value></exp>'
            f"<pv_name>{escape(pv)}</pv_name></rule></rules>"
        )

    return make


@pytest.fixture
def write_bob(tmp_path: Path) -> Callable[..., Path]:
    def write(content: str, filename: str = "test.bob") -> Path:
        path = tmp_path / filename
        path.write_text(content)
        return path

    return write


@pytest.fixture
def load_nodes(write_bob, make_display) -> Callable[..., list[Node]]:
    """Write a display with the given widget XML and return its top-level nodes."""

    def load(*widgets: str, macros: dict[str, str] | None = None) -> list[Node]:
        return load_display(write_bob(make_display(*widgets)), macros).nodes()

    return load


@pytest.fixture
def run_app() -> AppRunner:
    """Run the app headlessly on a display file: `async with run_app(path) as (app, pilot, pvs)`."""

    @asynccontextmanager
    async def run(
        path: Path, macros: dict[str, str] | None = None, size: tuple[int, int] = (120, 40)
    ) -> AsyncIterator[tuple[PhoebusTuiApp, Pilot, PVManager]]:
        macros = macros or {}
        pvs = PVManager()
        app = PhoebusTuiApp(load_display(path, macros), macros, pvs, Scale())
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            yield app, pilot, pvs

    return run


@pytest.fixture
def open_widgets(run_app, write_bob, make_display) -> AppRunner:
    """Run the app on a display made of the given widget XML."""

    def open_(*widgets: str, size: tuple[int, int] = (120, 40), macros: dict[str, str] | None = None, **display_kwargs):
        return run_app(write_bob(make_display(*widgets, **display_kwargs)), macros, size=size)

    return open_


@pytest.fixture
def notifications(monkeypatch) -> Callable[[PhoebusTuiApp], list[tuple[str, str]]]:
    """Record (message, severity) of notifications posted through the app."""

    def capture(app: PhoebusTuiApp) -> list[tuple[str, str]]:
        messages: list[tuple[str, str]] = []
        monkeypatch.setattr(app, "notify", lambda message, **kw: messages.append((str(message), kw.get("severity", ""))))
        return messages

    return capture


@pytest.fixture
def right_click() -> Callable[..., Awaitable[None]]:
    """Right click as a terminal delivers it (through App.on_event, which the pilot bypasses)."""

    async def click(app: PhoebusTuiApp, pilot: Pilot, target: Widget, offset: tuple[int, int] = (1, 0)) -> None:
        x, y = target.region.x + offset[0], target.region.y + offset[1]
        for cls in (events.MouseDown, events.MouseUp):
            await app.on_event(cls(None, x, y, 0, 0, 3, False, False, False, x, y))
        await pilot.pause()

    return click
