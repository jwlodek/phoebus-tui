"""Textual application displaying Phoebus .bob screens in tabbed, splittable cells."""

from __future__ import annotations

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, ScrollableContainer
from textual.content import Content
from textual.css.query import NoMatches
from textual.geometry import Offset
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Footer, Header, OptionList, Static, Tab, TabbedContent, TabPane
from textual.widgets.option_list import Option

from phoebusgen.v4.properties.types import (
    Action,
    OpenDisplayAction,
    OpenDisplayTarget,
    OpenWebpageAction,
    WritePvAction,
)

from .formatting import parse_input
from .layout import Scale
from .model import Display, Node, clean_macros, color_hex, load_display, resolve_display_path
from .pv import PVManager
from .widgets import ActionRequested, BuildContext, Canvas, RuleBinding, build_widgets

History = list[tuple[Display, dict[str, str]]]
DIRECTIONS = {"left": "Move left", "right": "Move right", "up": "Move up", "down": "Move down"}
# direction -> (menu label, horizontal split, new cell goes first)
TAB_SPLITS = {
    "left": ("Split left", True, True),
    "right": ("Split right", True, False),
    "up": ("Split top", False, True),
    "down": ("Split bottom", False, False),
}


class DisplayView(Container):
    """A display's scrollable canvas. Owns the display's rule bindings."""

    DEFAULT_CSS = """
    DisplayView {
        height: 1fr;
    }
    """

    def __init__(self, display: Display, macros: dict[str, str]) -> None:
        super().__init__()
        self.display_model = display
        self.macros = macros
        self._rules: list[RuleBinding] = []

    def compose(self) -> ComposeResult:
        app = self.app
        assert isinstance(app, PhoebusTuiApp)
        nodes = self.display_model.nodes()
        ctx = BuildContext.for_nodes(app.pvs, app.scale, nodes)
        self._rules = ctx.rules
        width, height = self.display_model.size
        extent_w, extent_h = ctx.layout.extent
        canvas = Canvas(*build_widgets(nodes, ctx))
        canvas.styles.width = max(round(width / ctx.scale.cell_width), extent_w)
        canvas.styles.height = max(round(height / ctx.scale.cell_height), extent_h)
        background = color_hex(self.display_model.background)
        canvas.styles.background = background
        with ScrollableContainer() as viewport:
            viewport.styles.background = background
            yield canvas

    def on_mount(self) -> None:
        for rule in self._rules:
            rule.start()

    def on_unmount(self) -> None:
        for rule in self._rules:
            rule.stop()


class DisplayTab(TabPane):
    """A tab showing one display at a time, keeping a history of displays it replaced."""

    def __init__(self, history: History) -> None:
        super().__init__(Content(history[-1][0].title))
        self.history = list(history)

    @property
    def current(self) -> tuple[Display, dict[str, str]]:
        return self.history[-1]

    @property
    def cell(self) -> Cell:
        return next(a for a in self.ancestors if isinstance(a, Cell))

    def compose(self) -> ComposeResult:
        yield DisplayView(*self.current)

    async def show(self, display: Display, macros: dict[str, str], remember: bool = True) -> None:
        if remember:
            self.history.append((display, macros))
        else:
            self.history[-1] = (display, macros)
        await self.query(DisplayView).remove()
        await self.mount(DisplayView(display, macros))
        self.cell.tabbed.get_tab(self).label = Content(display.title)

    async def back(self) -> None:
        if len(self.history) > 1:
            self.history.pop()
            await self.show(*self.history.pop())

    async def on_action_requested(self, message: ActionRequested) -> None:
        message.stop()
        app = self.app
        assert isinstance(app, PhoebusTuiApp)
        await app.run_widget_action(message.action, message.node, self)


class Cell(Container):
    """One pane of the workspace: a tabbed container of displays."""

    DEFAULT_CSS = """
    Cell {
        width: 1fr;
        height: 1fr;
    }
    Cell > TabbedContent, Cell > TabbedContent > ContentSwitcher {
        height: 1fr;
    }
    Cell > TabbedContent > ContentSwitcher > DisplayTab {
        height: 1fr;
        padding: 0;
    }
    Cell > .empty {
        width: 1fr;
        height: 1fr;
        content-align: center middle;
        color: $text-muted;
    }
    """

    def __init__(self, histories: list[History] | None = None, active: int = 0) -> None:
        super().__init__()
        self._histories = histories or []
        self._active = active

    def compose(self) -> ComposeResult:
        initial = f"tab-{self._active + 1}" if self._histories else ""
        with TabbedContent(initial=initial):
            for history in self._histories:
                yield DisplayTab(history)
        yield Static("No displays open. Right-click to split or remove this cell.", classes="empty")

    def on_mount(self) -> None:
        self._update_empty()
        app = self.app
        if isinstance(app, PhoebusTuiApp) and app.current_cell is self:
            app.set_current_cell(self)

    @property
    def tabbed(self) -> TabbedContent | None:
        # None until composed (cells inside a newly mounted split are composed later)
        return next((child for child in self.children if isinstance(child, TabbedContent)), None)

    @property
    def display_tabs(self) -> list[DisplayTab]:
        tabbed = self.tabbed
        return [] if tabbed is None else [pane for pane in tabbed.query(DisplayTab) if pane.cell is self]

    @property
    def active_tab(self) -> DisplayTab | None:
        try:
            pane = self.tabbed.active_pane if self.tabbed is not None else None
        except NoMatches:  # TabbedContent not composed yet
            return None
        return pane if isinstance(pane, DisplayTab) else None

    def _update_empty(self) -> None:
        if self.tabbed is None:
            return
        empty = not self.display_tabs
        self.tabbed.display = not empty
        self.query_one(".empty").display = empty

    async def add_tab(self, history: History) -> DisplayTab:
        tabbed = self.tabbed
        assert tabbed is not None
        tab = DisplayTab(history)
        await tabbed.add_pane(tab)
        # Drop focus from the widget that opened the tab, or TabbedContent switches back to its tab
        self.screen.set_focus(None)
        tabbed.active = tab.id or ""
        self._update_empty()
        return tab

    async def close_tab(self, tab: DisplayTab) -> None:
        if tab.id and self.tabbed is not None:
            await self.tabbed.remove_pane(tab.id)
        self._update_empty()

    def on_descendant_focus(self, event: events.DescendantFocus) -> None:
        self._make_current()

    def on_mouse_down(self, event: events.MouseDown) -> None:
        self._make_current()

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        # Tabs widgets inside displays post this too
        if event.tabbed_content is self.tabbed:
            self._make_current()

    def _make_current(self) -> None:
        app = self.app
        if isinstance(app, PhoebusTuiApp):
            app.set_current_cell(self)


class Split(Container):
    """Cells (or nested splits) side by side or stacked."""

    DEFAULT_CSS = """
    Split {
        width: 1fr;
        height: 1fr;
    }
    Split.-horizontal {
        layout: horizontal;
    }
    """

    def __init__(self, *children: Widget, horizontal: bool) -> None:
        super().__init__(*children)
        self.set_class(horizontal, "-horizontal")


class Workspace(Container):
    DEFAULT_CSS = """
    Workspace {
        height: 1fr;
    }
    """


class ContextMenu(ModalScreen[str | None]):
    """Small popup menu shown at the mouse position."""

    DEFAULT_CSS = """
    ContextMenu {
        background: transparent;
    }
    ContextMenu > OptionList {
        width: auto;
        min-width: 16;
        height: auto;
        border: round $accent;
        background: $panel;
    }
    """
    BINDINGS = [Binding("escape", "dismiss(None)", "Cancel")]

    def __init__(self, items: list[tuple[str, str]], position: Offset) -> None:
        super().__init__()
        self.items = items
        self.position = position

    def compose(self) -> ComposeResult:
        yield OptionList(*[Option(label, id=key) for key, label in self.items])

    def on_mount(self) -> None:
        menu = self.query_one(OptionList)
        width = max(len(label) for _, label in self.items) + 4
        height = len(self.items) + 2
        menu.styles.offset = (
            max(0, min(self.position.x, self.size.width - width)),
            max(0, min(self.position.y, self.size.height - height)),
        )
        menu.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.id)

    def on_click(self, event: events.Click) -> None:
        if event.widget is self:
            self.dismiss(None)


class PhoebusTuiApp(App[None]):
    TITLE = "phoebus-tui"
    # Cell borders only appear once the workspace is split
    CSS = """
    Workspace.-split Cell {
        border: round $panel-lighten-2;
    }
    """
    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("f5", "reload", "Reload"),
        Binding("ctrl+x", "close_tab", "Close tab"),
        Binding("ctrl+q", "quit", "Quit", priority=True),
    ]

    def __init__(self, display: Display, macros: dict[str, str], pvs: PVManager, scale: Scale) -> None:
        super().__init__()
        self.pvs = pvs
        self.scale = scale
        self._initial: History = [(display, macros)]
        self.current_cell: Cell | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Workspace():
            yield Cell([self._initial])
        yield Footer()

    def on_mount(self) -> None:
        self.set_current_cell(self.query_one(Cell))

    def on_unmount(self) -> None:
        self.pvs.close()

    @property
    def workspace(self) -> Workspace:
        return self.query_one(Workspace)

    @property
    def cells(self) -> list[Cell]:
        return list(self.workspace.query(Cell))

    @property
    def current_tab(self) -> DisplayTab | None:
        return self.current_cell.active_tab if self.current_cell is not None else None

    def set_current_cell(self, cell: Cell) -> None:
        self.current_cell = cell
        self._update_title()

    def _update_title(self) -> None:
        tab = self.current_tab
        if tab is None:
            self.title, self.sub_title = "phoebus-tui", ""
        else:
            display = tab.current[0]
            self.title = display.title
            self.sub_title = str(display.path)
        self.refresh_bindings()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        tab = self.current_tab
        if action == "back":
            return True if tab is not None and len(tab.history) > 1 else None
        if action == "reload":
            return True if tab is not None else None
        if action == "close_tab":
            return True if tab is not None and self._can_close(tab) else None
        return True

    def _can_close(self, tab: DisplayTab) -> bool:
        # Keep at least one display open somewhere
        return len(self.cells) > 1 or len(tab.cell.display_tabs) > 1

    async def open_display(self, display: Display, macros: dict[str, str], source: DisplayTab, replace: bool) -> None:
        """Show a display in `source`'s tab, or in a new tab of the same cell."""
        cell = source.cell
        if replace:
            await source.show(display, macros)
        else:
            await cell.add_tab([(display, macros)])
        self.set_current_cell(cell)

    async def action_back(self) -> None:
        tab = self.current_tab
        if tab is not None:
            await tab.back()
            self._update_title()

    async def action_reload(self) -> None:
        tab = self.current_tab
        if tab is None:
            return
        display, macros = tab.current
        try:
            reloaded = load_display(display.path, macros)
        except Exception as e:
            self.notify(str(e), title="Reload failed", severity="error")
            return
        await tab.show(reloaded, macros, remember=False)
        self._update_title()

    async def action_close_tab(self) -> None:
        tab = self.current_tab
        if tab is not None:
            await self.close_tab(tab)

    async def close_tab(self, tab: DisplayTab) -> None:
        if self._can_close(tab):
            await tab.cell.close_tab(tab)
            self._update_title()

    async def split(self, cell: Cell, horizontal: bool, before: bool = False, moving: DisplayTab | None = None) -> None:
        """Split `cell` in two. The new cell is empty, or holds `moving` (taken from `cell`)."""
        tabs = [tab for tab in cell.display_tabs if tab is not moving]
        active = cell.active_tab
        histories = [tab.history for tab in tabs]
        index = tabs.index(active) if active in tabs else 0
        parent = cell.parent
        assert isinstance(parent, Widget)
        position = parent.children.index(cell)
        new_cell = Cell([moving.history] if moving is not None else [])
        await cell.remove()
        # Textual cannot re-parent widgets, so the split cell is rebuilt with the same tabs
        kept = Cell(histories, index)
        split = Split(*((new_cell, kept) if before else (kept, new_cell)), horizontal=horizontal)
        if position < len(parent.children):
            await parent.mount(split, before=position)
        else:
            await parent.mount(split)
        self.workspace.add_class("-split")
        self.set_current_cell(new_cell)

    async def split_tab(self, tab: DisplayTab, direction: str) -> None:
        """Put `tab` in an empty neighbouring cell in `direction`, splitting its cell if there is none."""
        cell = tab.cell
        target = self.neighbour(cell, direction)
        if target is not None and not target.display_tabs:
            await self.move_tab(tab, target)
        else:
            _, horizontal, before = TAB_SPLITS[direction]
            await self.split(cell, horizontal, before, moving=tab)

    async def remove_cell(self, cell: Cell) -> None:
        if len(self.cells) <= 1:
            return
        parent = cell.parent
        await cell.remove()
        # Replace splits left with one child by that child (rebuilt, as Textual cannot re-parent)
        while isinstance(parent, Split) and len(parent.children) <= 1:
            grandparent = parent.parent
            assert isinstance(grandparent, Widget)
            position = grandparent.children.index(parent)
            replacement = [self._rebuild(child) for child in parent.children]
            await parent.remove()
            if replacement:
                if position < len(grandparent.children):
                    await grandparent.mount(*replacement, before=position)
                else:
                    await grandparent.mount(*replacement)
            parent = grandparent
        self.workspace.set_class(len(self.cells) > 1, "-split")
        self.current_cell = None
        self.set_current_cell(self.cells[0])

    def _rebuild(self, widget: Widget) -> Widget:
        if isinstance(widget, Cell):
            tabs = widget.display_tabs
            active = widget.active_tab
            return Cell([tab.history for tab in tabs], tabs.index(active) if active in tabs else 0)
        assert isinstance(widget, Split)
        return Split(*(self._rebuild(child) for child in widget.children), horizontal=widget.has_class("-horizontal"))

    async def move_tab(self, tab: DisplayTab, target: Cell) -> None:
        source = tab.cell
        history = tab.history
        await source.close_tab(tab)
        await target.add_tab(history)
        self.set_current_cell(target)

    def neighbour(self, cell: Cell, direction: str) -> Cell | None:
        """The closest cell in `direction` whose extent overlaps `cell`'s."""
        region = cell.region
        best: tuple[int, Cell] | None = None
        for other in self.cells:
            if other is cell:
                continue
            o = other.region
            overlap_x = o.x < region.right and region.x < o.right
            overlap_y = o.y < region.bottom and region.y < o.bottom
            distance = {
                "left": region.x - o.right if overlap_y and o.right <= region.x else None,
                "right": o.x - region.right if overlap_y and o.x >= region.right else None,
                "up": region.y - o.bottom if overlap_x and o.bottom <= region.y else None,
                "down": o.y - region.bottom if overlap_x and o.y >= region.bottom else None,
            }[direction]
            if distance is not None and (best is None or distance < best[0]):
                best = (distance, other)
        return best[1] if best else None

    async def on_event(self, event: events.Event) -> None:
        # Right clicks open context menus instead of reaching (and e.g. pressing) widgets
        if isinstance(event, (events.MouseDown, events.MouseUp, events.Click)) and event.button == 3:
            if not event.is_forwarded:
                if isinstance(event, events.MouseUp) and not isinstance(self.screen, ModalScreen):
                    self._show_context_menu(event.screen_offset)
                return
        await super().on_event(event)

    def _show_context_menu(self, position: Offset) -> None:
        try:
            widget, _ = self.get_widget_at(*position)
        except Exception:
            return
        chain = [widget, *widget.ancestors]
        cell = next((w for w in chain if isinstance(w, Cell)), None)
        if cell is None:
            return
        self.set_current_cell(cell)
        tab_widget = next((w for w in chain if isinstance(w, Tab)), None)
        tab = None
        owner = next((w for w in chain if isinstance(w, TabbedContent)), None)
        if tab_widget is not None and owner is cell.tabbed:
            pane = cell.tabbed.get_pane(tab_widget)  # type: ignore[arg-type]  # a ContentTab at runtime
            tab = pane if isinstance(pane, DisplayTab) and pane.cell is cell else None

        items: list[tuple[str, str]] = []
        if tab is not None:
            items += [(f"split-tab:{d}", label) for d, (label, _, _) in TAB_SPLITS.items()]
            for direction, label in DIRECTIONS.items():
                neighbour = self.neighbour(cell, direction)
                if neighbour is not None and neighbour.display_tabs:
                    items.append((f"move:{direction}", label))
            if self._can_close(tab):
                items.append(("close", "Close tab"))
        else:
            items += [("split:horizontal", "Split left/right"), ("split:vertical", "Split top/bottom")]
            if not cell.display_tabs and len(self.cells) > 1:
                items.append(("remove", "Remove cell"))
        if not items:
            return

        async def chosen(choice: str | None) -> None:
            if choice is None:
                return
            kind, _, arg = choice.partition(":")
            if kind == "move" and tab is not None:
                target = self.neighbour(cell, arg)
                if target is not None:
                    await self.move_tab(tab, target)
            elif kind == "split-tab" and tab is not None:
                await self.split_tab(tab, arg)
            elif kind == "close" and tab is not None:
                await self.close_tab(tab)
            elif kind == "split":
                await self.split(cell, horizontal=arg == "horizontal")
            elif kind == "remove":
                await self.remove_cell(cell)

        self.push_screen(ContextMenu(items, position), chosen)

    async def run_widget_action(self, action: Action, node: Node, source: DisplayTab) -> None:
        if isinstance(action, WritePvAction):
            pv = self.pvs.get(action.pv_name)
            try:
                pv.put(parse_input(action.value, pv.state))
            except Exception as e:
                self.notify(f"{pv.name}: {e}", title="Write failed", severity="error")
        elif isinstance(action, OpenDisplayAction):
            macros = {**node.macros, **clean_macros(action.macros)}
            try:
                display = load_display(resolve_display_path(action.file, node.display_path), macros)
            except Exception as e:
                self.notify(str(e), title="Cannot open display", severity="error")
                return
            # New tabs are used for both the "tab" and "window" targets
            await self.open_display(display, macros, source, replace=action.target == OpenDisplayTarget.REPLACE)
        elif isinstance(action, OpenWebpageAction):
            self.open_url(action.url)
        else:
            self.notify(f"{type(action).__name__} is not supported", severity="warning")
