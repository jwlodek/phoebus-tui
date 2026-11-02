"""Textual widgets that render phoebusgen widget models."""

from __future__ import annotations

import logging
import math
import numbers
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any, cast

from phoebusgen.v4.properties.types import (
    Action,
    ButtonMode,
    Color,
    GroupStyle,
    OpenDisplayAction,
    OpenWebpageAction,
    Rule,
    WritePvAction,
)
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.content import Content
from textual.events import Blur, Click, Focus, Key, Mount, MouseUp, Unmount
from textual.message import Message
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Button, Checkbox, Input, OptionList, Select, Static, TabbedContent, TabPane

from .formatting import (
    ALARM_COLORS,
    DISCONNECTED_COLOR,
    as_number,
    format_value,
    is_bit_on,
    parse_input,
    with_bit,
)
from .layout import Layout, Scale, is_frame
from .model import (
    EmbeddedContent,
    Node,
    clean_macros,
    color_hex,
    contrast,
    font_style,
    format_ordinal,
    get,
    is_transparent,
    load_embedded,
    to_color,
)
from .pv import PV, PVManager, PVState
from .rules import RuleError, evaluate, rule_variables

log = logging.getLogger(__name__)

H_ALIGN = {0: "left", 1: "center", 2: "right"}
V_ALIGN = {0: "top", 1: "middle", 2: "bottom"}
H_EIGHTHS = " ▏▎▍▌▋▊▉"
V_EIGHTHS = " ▁▂▃▄▅▆▇"
BLACK = Color((0, 0, 0))
DISCONNECTED = Color(DISCONNECTED_COLOR)


def _round(value: float) -> int:
    return math.floor(value + 0.5)


@dataclass(frozen=True)
class BuildContext:
    pvs: PVManager
    layout: Layout
    rules: list[RuleBinding] = field(default_factory=list)  # started/stopped by the owning screen

    @classmethod
    def for_nodes(cls, pvs: PVManager, scale: Scale, nodes: list[Node]) -> BuildContext:
        return cls(pvs, Layout(scale, nodes))

    @property
    def scale(self) -> Scale:
        return self.layout.scale

    def nested_display(self, nodes: list[Node]) -> BuildContext:
        """Context for tab contents, which have their own coordinate system."""
        return replace(self, layout=Layout(self.scale, nodes))

    def rect(self, node: Node) -> tuple[int, int, int, int]:
        """(x, y, width, height) in cells, relative to the node's Textual container."""
        return self.layout.rect(node)


class RuleBinding:
    """Applies one Phoebus rule to a widget (or the parts drawing it) whenever its trigger PVs update."""

    def __init__(self, widgets: list[Widget], node: Node, rule: Rule, pvs: PVManager) -> None:
        self.widgets = widgets
        self.node = node
        self.rule = rule
        self.pvs = [pvs.get(str(name)) for name in rule.pv_names]
        self.triggers = [pv for pv, trigger in zip(self.pvs, rule.pv_names.values()) if trigger]
        self._unsubscribers: list[Callable[[], None]] = []
        self._warned = False

    def start(self) -> None:
        self._unsubscribers = [pv.subscribe(lambda _: self.evaluate()) for pv in self.triggers]
        self.evaluate()

    def stop(self) -> None:
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers = []

    def evaluate(self) -> None:
        states = [pv.state for pv in self.pvs]
        if not states or not all(state.connected for state in states):
            self._apply(None)
            return
        variables = rule_variables(states)
        for expression in self.rule.expressions:
            try:
                if evaluate(expression.bool_exp, variables):
                    value = expression.value
                    if expression.value_as_expression or self.rule.out_exp:
                        value = evaluate(str(value), variables)
                    self._apply(value)
                    return
            except RuleError as e:
                if not self._warned:
                    log.warning("Rule %r on %r: %s", self.rule.name, self.node.prop("name", ""), e)
                    self._warned = True
        self._apply(None)

    def _apply(self, value: Any) -> None:
        """Set the rule's property, or restore the widget's own value when `value` is None."""
        prop, node = self.rule.prop_id, self.node
        for widget in self.widgets:
            self._apply_to(widget, prop, node, value)

    def _apply_to(self, widget: Widget, prop: str, node: Node, value: Any) -> None:
        if prop == "visible":
            widget.display = bool(node.flag("visible", True) if value is None else value)
        elif prop in ("foreground_color", "background_color"):
            color = node.color(prop) if value is None else to_color(value)
            if prop == "background_color" and node.flag("transparent", False):
                color = None  # transparent widgets don't show a background, as in Phoebus
            rule_name = "color" if prop == "foreground_color" else "background"
            if color is None:
                widget.styles.clear_rule(rule_name)
            else:
                setattr(widget.styles, rule_name, color_hex(color))
        elif prop == "text":
            text = Content(str(node.prop("text", "") if value is None else value))
            if isinstance(widget, Button):
                widget.label = text
            elif isinstance(widget, Static):
                widget.update(text)
        elif not self._warned:
            log.warning("Rules for property %r are not supported", prop)
            self._warned = True


class ActionRequested(Message):
    """Posted when the user triggers a widget action; handled by the display screen."""

    def __init__(self, action: Action, node: Node) -> None:
        super().__init__()
        self.action = action
        self.node = node


def describe(action: Action) -> str:
    if action.description:
        return action.description
    if isinstance(action, WritePvAction):
        return f"Write {action.value} to {action.pv_name}"
    if isinstance(action, OpenDisplayAction):
        return f"Open {action.file}"
    if isinstance(action, OpenWebpageAction):
        return f"Open {action.url}"
    return type(action).__name__


def _apply_colors(widget: Widget, node: Node, fg_default: Color | None = BLACK) -> None:
    fg = node.color("foreground_color", fg_default)
    if fg is not None:
        widget.styles.color = color_hex(fg)
    if not node.flag("transparent", False):
        bg = node.color("background_color")
        if bg is not None and not is_transparent(bg):
            widget.styles.background = color_hex(bg)


def _apply_text_style(widget: Widget, node: Node) -> None:
    style = font_style(node.widget)
    if style:
        widget.styles.text_style = style


def _apply_alignment(widget: Widget, node: Node, h_default: int = 0, v_default: int = 0) -> None:
    widget.styles.content_align_horizontal = H_ALIGN.get(int(node.prop("horizontal_alignment", h_default)), "left")  # type: ignore[assignment]
    widget.styles.content_align_vertical = V_ALIGN.get(int(node.prop("vertical_alignment", v_default)), "top")  # type: ignore[assignment]


def _limits(state: PVState, from_pv: bool, minimum: float, maximum: float) -> tuple[float, float]:
    if from_pv and state.lower is not None and state.upper is not None and state.lower < state.upper:
        return float(state.lower), float(state.upper)
    return minimum, maximum


class PVMixin:
    """Mixin for widgets bound to a PV; `show_state` is called on every update while mounted."""

    # Deliberately not a Widget subclass: Textual only inherits DEFAULT_CSS and
    # COMPONENT_CLASSES through the first DOMNode base.
    pv: PV | None = None
    _unsubscribe: Callable[[], None] | None = None

    def _init_pv(self, node: Node, ctx: BuildContext) -> None:
        name = str(node.prop("pv_name", "") or "")
        if name:
            self.pv = ctx.pvs.get(name)
            cast(Widget, self).tooltip = name

    def _on_mount(self, event: Mount) -> None:
        if self.pv is not None:
            self._unsubscribe = self.pv.subscribe(self.show_state)
            self.show_state(self.pv.state)

    def _on_unmount(self, event: Unmount) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    def show_state(self, state: PVState) -> None:
        raise NotImplementedError

    def write(self, value: Any) -> None:
        if self.pv is None:
            return
        try:
            self.pv.put(value)
        except Exception as e:
            cast(Widget, self).notify(f"{self.pv.name}: {e}", title="Write failed", severity="error")


class Canvas(Container):
    """Container whose children are absolutely positioned from display coordinates."""

    DEFAULT_CSS = """
    Canvas {
        width: 100%;
        height: 1fr;
        overflow: hidden hidden;
    }
    """


class LabelWidget(Static):
    def __init__(self, node: Node, ctx: BuildContext) -> None:
        text = str(node.prop("text", "") or "")
        super().__init__(Content(text))
        _apply_colors(self, node)
        _apply_text_style(self, node)
        _apply_alignment(self, node)
        if not node.flag("wrap_words", True):
            self.styles.text_wrap = "nowrap"
        lines = text.splitlines()
        # Cells are coarser than pixels: fit plain one-line labels to their text so they neither
        # clip nor cover neighbouring widgets (Textual widgets are opaque)
        fits = not self.styles.has_rule("background") and len(lines) == 1
        self.text_width = len(lines[0]) if fits else None
        self.alignment = int(node.prop("horizontal_alignment", 0))


class TextUpdateWidget(PVMixin, Static):
    def __init__(self, node: Node, ctx: BuildContext) -> None:
        super().__init__("")
        self.fmt = format_ordinal(node.widget)
        self.precision = int(node.prop("precision", -1))
        self.show_units = node.flag("show_units", True)
        _apply_colors(self, node)
        _apply_text_style(self, node)
        _apply_alignment(self, node)
        if not node.flag("wrap_words", True):
            self.styles.text_wrap = "nowrap"
            self.styles.text_overflow = "ellipsis"
        self._init_pv(node, ctx)
        if self.pv is not None:
            self.update(Content.styled(self.pv.name, DISCONNECTED_COLOR))

    def show_state(self, state: PVState) -> None:
        assert self.pv is not None
        if not state.connected:
            self.update(Content.styled(self.pv.name, DISCONNECTED_COLOR))
            return
        text = format_value(state, self.fmt, self.precision, self.show_units)
        color = ALARM_COLORS.get(state.severity)
        self.update(Content.styled(text, color) if color else Content(text))


class TextSymbolWidget(PVMixin, Static):
    def __init__(self, node: Node, ctx: BuildContext) -> None:
        super().__init__("")
        self.symbols = [str(s) for s in node.prop("symbols", []) or []]
        _apply_colors(self, node)
        _apply_text_style(self, node)
        _apply_alignment(self, node, 1, 1)
        self._init_pv(node, ctx)

    def show_state(self, state: PVState) -> None:
        number = as_number(state.value)
        index = int(number) if number is not None and math.isfinite(number) else -1
        self.update(Content(self.symbols[index] if 0 <= index < len(self.symbols) else ""))


class TextEntryWidget(PVMixin, Input):
    def __init__(self, node: Node, ctx: BuildContext) -> None:
        super().__init__(compact=True)
        self.node = node
        self.fmt = format_ordinal(node.widget)
        self.precision = int(node.prop("precision", -1))
        self.show_units = node.flag("show_units", True)
        self._shown = ""
        self._select_on_click = False
        _apply_colors(self, node)
        _apply_text_style(self, node)
        self.styles.padding = 0
        self.disabled = not node.flag("enabled", True)
        self._init_pv(node, ctx)
        if self.pv is not None:
            self.placeholder = self.pv.name

    def show_state(self, state: PVState) -> None:
        if self.has_focus and self.value != self._shown:
            return  # user is editing; refreshed on blur/submit
        self._shown = format_value(state, self.fmt, self.precision, self.show_units) if state.connected else ""
        self.value = self._shown

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        if self.pv is None:
            return
        try:
            value = parse_input(self.value, self.pv.state)
        except ValueError:
            self.notify(f"Invalid value for {self.pv.name}: {self.value!r}", severity="error")
            return
        self.write(value)
        self._revert()

    def on_blur(self, event: Blur) -> None:
        self._revert()

    def on_focus(self, event: Focus) -> None:
        self._select_on_click = True

    def on_key(self, event: Key) -> None:
        self._select_on_click = False

    def on_mouse_up(self, event: MouseUp) -> None:
        # Like Phoebus, the click that focuses the entry selects everything so typing replaces it
        if self._select_on_click and self.selection.is_empty:
            self.select_all()
        self._select_on_click = False

    def _revert(self) -> None:
        if self.pv is not None:
            self._shown = self.value
            self.show_state(self.pv.state)


class SpinnerWidget(TextEntryWidget):
    BINDINGS = [
        Binding("up", "step(1)", "Increment", show=False),
        Binding("down", "step(-1)", "Decrement", show=False),
    ]

    def __init__(self, node: Node, ctx: BuildContext) -> None:
        super().__init__(node, ctx)
        self.increment = float(node.prop("increment", 1.0))
        self.minimum = float(node.prop("minimum", 0.0))
        self.maximum = float(node.prop("maximum", 100.0))
        self.limits_from_pv = node.flag("limits_from_pv", True)

    def action_step(self, direction: int) -> None:
        if self.pv is None:
            return
        state = self.pv.state
        current = as_number(state.value)
        if current is None:
            return
        low, high = _limits(state, self.limits_from_pv, self.minimum, self.maximum)
        value = min(max(current + direction * self.increment, low), high)
        self.write(int(round(value)) if isinstance(state.value, numbers.Integral) else value)


class LEDBase(PVMixin, Static):
    def __init__(self, node: Node, ctx: BuildContext) -> None:
        super().__init__("")
        self.styles.content_align = ("center", "middle")
        _apply_text_style(self, node)
        self._init_pv(node, ctx)
        self._show(DISCONNECTED, "")

    def _show(self, color: Color, label: str) -> None:
        if label:
            self.styles.background = color_hex(color)
            self.update(Content.styled(label, contrast(color)))
        else:
            self.styles.clear_rule("background")
            self.update(Content.styled("●", color_hex(color)))


class LEDWidget(LEDBase):
    def __init__(self, node: Node, ctx: BuildContext) -> None:
        self.bit = int(node.prop("bit", -1))
        self.on_color = node.color("on_color", Color((0, 255, 0)))
        self.off_color = node.color("off_color", Color((60, 100, 60)))
        self.on_label = str(node.prop("on_label", "") or "")
        self.off_label = str(node.prop("off_label", "") or "")
        super().__init__(node, ctx)

    def show_state(self, state: PVState) -> None:
        if not state.connected:
            self._show(DISCONNECTED, "")
        elif is_bit_on(state, self.bit):
            self._show(self.on_color, self.on_label)
        else:
            self._show(self.off_color, self.off_label)


class MultiStateLEDWidget(LEDBase):
    def __init__(self, node: Node, ctx: BuildContext) -> None:
        self.states = [
            (int(s.value), str(s.label or ""), to_color(s.color, BLACK)) for s in node.prop("states", []) or []
        ]
        self.fallback_label = str(node.prop("fallback_label", "Err") or "")
        self.fallback_color = node.color("fallback_color", Color((255, 0, 255)))
        super().__init__(node, ctx)

    def show_state(self, state: PVState) -> None:
        if not state.connected:
            self._show(DISCONNECTED, "")
            return
        number = as_number(state.value)
        for value, label, color in self.states:
            if number is not None and int(number) == value:
                self._show(color, label)
                return
        self._show(self.fallback_color, self.fallback_label)


class ByteMonitorWidget(PVMixin, Static):
    def __init__(self, node: Node, ctx: BuildContext) -> None:
        super().__init__("")
        start = int(node.prop("start_bit", 0))
        bits = list(range(start, start + int(node.prop("num_bits", 8))))
        self.bits = bits if node.flag("reverse_bits", False) else bits[::-1]
        self.horizontal = node.flag("horizontal", True)
        self.on_color = color_hex(node.color("on_color", Color((0, 255, 0))))
        self.off_color = color_hex(node.color("off_color", Color((60, 100, 60))))
        self._init_pv(node, ctx)

    def show_state(self, state: PVState) -> None:
        number = as_number(state.value)
        value = int(number) if state.connected and number is not None and math.isfinite(number) else None
        separator = "" if self.horizontal else "\n"
        parts: list[str | tuple[str, str]] = []
        for i, bit in enumerate(self.bits):
            if i:
                parts.append(separator)
            if value is None:
                color = DISCONNECTED_COLOR
            else:
                color = self.on_color if (value >> bit) & 1 else self.off_color
            parts.append(("●", color))
        self.update(Content.assemble(*parts))


class ActionMenu(ModalScreen[int | None]):
    """Menu shown for action buttons with more than one action."""

    DEFAULT_CSS = """
    ActionMenu {
        align: center middle;
    }
    ActionMenu OptionList {
        width: auto;
        max-width: 80%;
        height: auto;
        border: round $accent;
    }
    """
    BINDINGS = [Binding("escape", "dismiss(None)", "Cancel")]

    def __init__(self, actions: list[Action]) -> None:
        super().__init__()
        self.actions = actions

    def compose(self) -> ComposeResult:
        yield OptionList(*[Content(describe(a)) for a in self.actions])

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option_index)


class ActionButtonWidget(Button):
    def __init__(self, node: Node, ctx: BuildContext) -> None:
        self.node = node
        self.actions: list[Action] = list(node.prop("actions", []) or [])
        text = str(node.prop("text", "$(actions)") or "")
        if "$(actions)" in text:
            text = text.replace("$(actions)", describe(self.actions[0]) if self.actions else "")
        super().__init__(Content(text), compact=True)
        _apply_colors(self, node)
        _apply_text_style(self, node)
        self.styles.padding = 0
        self.disabled = not node.flag("enabled", True)
        pv_name = str(node.prop("pv_name", "") or "")
        self.tooltip = "\n".join(filter(None, [pv_name, *(describe(a) for a in self.actions)])) or None

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if len(self.actions) == 1:
            self.post_message(ActionRequested(self.actions[0], self.node))
        elif self.actions:
            def chosen(index: int | None) -> None:
                if index is not None:
                    self.post_message(ActionRequested(self.actions[index], self.node))

            self.app.push_screen(ActionMenu(self.actions), chosen)


class BoolButtonWidget(PVMixin, Button):
    def __init__(self, node: Node, ctx: BuildContext, slide: bool = False) -> None:
        super().__init__("", compact=True)
        self.bit = int(node.prop("bit", 0))
        if slide:
            self.on_label = self.off_label = str(node.prop("label", "") or "")
            self.mode = ButtonMode.TOGGLE
        else:
            self.on_label = str(node.prop("on_label", "On") or "")
            self.off_label = str(node.prop("off_label", "Off") or "")
            self.mode = ButtonMode(int(node.prop("mode", 0)))
        self.on_color = node.color("on_color", Color((0, 255, 0)))
        self.off_color = node.color("off_color", Color((60, 100, 60)))
        self.show_led = node.flag("show_led", True)
        self._on = False
        _apply_colors(self, node)
        _apply_text_style(self, node)
        self.styles.padding = 0
        self.disabled = not node.flag("enabled", True)
        self._init_pv(node, ctx)
        self.show_state(PVState())

    def show_state(self, state: PVState) -> None:
        self._on = is_bit_on(state, self.bit)
        color = (self.on_color if self._on else self.off_color) if state.connected else DISCONNECTED
        label = self.on_label if self._on else self.off_label
        self.label = Content.assemble(("● ", color_hex(color)), label) if self.show_led else Content(label)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if self.pv is None:
            return
        if self.mode == ButtonMode.TOGGLE:
            self.write(with_bit(self.pv.state, self.bit, not self._on))
            return
        pressed = self.mode == ButtonMode.PUSH
        self.write(with_bit(self.pv.state, self.bit, pressed))
        # No key/mouse release in a terminal, so emulate it
        self.set_timer(0.2, lambda: self.write(with_bit(self.pv.state, self.bit, not pressed)) if self.pv else None)


class CheckBoxWidget(PVMixin, Checkbox):
    def __init__(self, node: Node, ctx: BuildContext) -> None:
        super().__init__(Content(str(node.prop("label", "") or "")), compact=True)
        self.bit = int(node.prop("bit", 0))
        self._expected: bool | None = None
        _apply_colors(self, node)
        self._init_pv(node, ctx)

    def show_state(self, state: PVState) -> None:
        self._expected = is_bit_on(state, self.bit)
        self.value = self._expected

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        event.stop()
        if self.pv is None or event.value == self._expected:
            return
        self._expected = event.value
        self.write(with_bit(self.pv.state, self.bit, event.value))


class ComboWidget(PVMixin, Select[str]):
    """Used for combo, choice and radio widgets."""

    def __init__(self, node: Node, ctx: BuildContext) -> None:
        self.items_from_pv = node.flag("items_from_pv", True)
        self.static_items = [str(i) for i in node.prop("items", []) or []]
        self._items = list(self.static_items)
        self._expected: str | None = None
        # A blank entry is only needed while there is nothing to choose from
        super().__init__(
            [(Content(i), i) for i in self._items], allow_blank=not self._items, compact=True, prompt=""
        )
        self._fg = color_hex(node.color("foreground_color", BLACK))
        background = node.color("background_color", Color((210, 210, 210)))
        self._bg = color_hex(background)
        self.disabled = not node.flag("enabled", True)
        self._init_pv(node, ctx)

    def on_mount(self) -> None:
        # Select's inner widgets set theme colors in their own CSS, so apply ours to them directly
        for widget in self.query("SelectCurrent, SelectOverlay"):
            widget.styles.background = self._bg
            widget.styles.color = self._fg
        for widget in self.query("SelectCurrent Static"):
            widget.styles.color = self._fg

    def show_state(self, state: PVState) -> None:
        items = list(state.enum_strs) if self.items_from_pv and state.enum_strs else self.static_items
        if items != self._items:
            self._items = items
            self._allow_blank = not items
            self.set_options([(Content(i), i) for i in items])
        self._expected = format_value(state, show_units=False) if state.connected else None
        if self._expected in items:
            self.value = self._expected
        elif self._allow_blank:
            self.clear()

    def on_select_changed(self, event: Select.Changed) -> None:
        event.stop()
        # Programmatic changes (e.g. set_options selecting the first item) are stale by now or match the PV
        if self.pv is None or self._expected is None or event.value == Select.NULL:
            return
        if event.value != self.value or event.value == self._expected:
            return
        self._expected = str(event.value)
        state = self.pv.state
        try:
            self.write(self._expected if state.enum_strs else parse_input(self._expected, state))
        except ValueError:
            self.notify(f"Invalid value for {self.pv.name}: {self._expected!r}", severity="error")


class BarWidget(PVMixin, Widget):
    """Progress bar, tank, thermometer and meter rendered with block characters."""

    def __init__(self, node: Node, ctx: BuildContext, horizontal: bool, show_value: bool = False) -> None:
        super().__init__()
        self.horizontal = horizontal
        self.show_value = show_value
        self.fill = color_hex(node.color("fill_color", Color((60, 255, 60))))
        self.empty = color_hex(node.color("empty_color") or node.color("background_color", Color((250, 250, 250))))
        self.foreground = color_hex(node.color("foreground_color", BLACK))
        self.minimum = float(node.prop("minimum", 0.0))
        self.maximum = float(node.prop("maximum", 100.0))
        self.limits_from_pv = node.flag("limits_from_pv", True)
        self.fmt = format_ordinal(node.widget)
        self.precision = int(node.prop("precision", -1))
        self.state = PVState()
        self._init_pv(node, ctx)

    def show_state(self, state: PVState) -> None:
        self.state = state
        self.refresh()

    def limits(self) -> tuple[float, float]:
        return _limits(self.state, self.limits_from_pv, self.minimum, self.maximum)

    def fraction(self) -> float:
        low, high = self.limits()
        value = as_number(self.state.value)
        if value is None or not math.isfinite(value) or high <= low:
            return 0.0
        return min(max((value - low) / (high - low), 0.0), 1.0)

    def render(self) -> Content:
        width, height = self.size
        if width <= 0 or height <= 0:
            return Content("")
        value_row = self.show_value and height >= 2
        rows = height - 1 if value_row else height
        frac = self.fraction() if self.state.connected else 0.0
        if self.horizontal:
            full, part = divmod(_round(frac * width * 8), 8)
            line = ("█" * full + (H_EIGHTHS[part] if part else "")).ljust(width)[:width]
            lines = [line] * rows
        else:
            level = frac * rows * 8
            lines = []
            for row in range(rows):
                cell = min(max(_round(level - (rows - 1 - row) * 8), 0), 8)
                lines.append(("█" if cell == 8 else V_EIGHTHS[cell]) * width)
        parts: list[str | Content] = []
        for i, line in enumerate(lines):
            if i:
                parts.append("\n")
            parts.append(Content.styled(line, f"{self.fill} on {self.empty}"))
        if value_row:
            if self.state.connected:
                text, style = format_value(self.state, self.fmt, self.precision), self.foreground
            else:
                text, style = self.pv.name if self.pv else "", DISCONNECTED_COLOR
            parts += ["\n", Content.styled(text.center(width)[:width], style)]
        return Content.assemble(*parts)


class SliderWidget(BarWidget):
    """Scaled slider / scrollbar: arrow keys step by `increment`, clicking sets the value."""

    can_focus = True
    DEFAULT_CSS = """
    SliderWidget:focus {
        tint: $accent 25%;
    }
    """
    BINDINGS = [
        Binding("right,up", "step(1)", "Increase", show=False),
        Binding("left,down", "step(-1)", "Decrease", show=False),
    ]

    def __init__(self, node: Node, ctx: BuildContext, horizontal: bool, show_value: bool = True) -> None:
        super().__init__(node, ctx, horizontal, show_value)
        self.increment = float(node.prop("increment", 1.0))
        self.disabled = not node.flag("enabled", True)

    def _set(self, value: float) -> None:
        low, high = self.limits()
        value = min(max(value, low), high)
        self.write(int(round(value)) if isinstance(self.state.value, numbers.Integral) else value)

    def action_step(self, direction: int) -> None:
        current = as_number(self.state.value)
        self._set((current if current is not None else self.limits()[0]) + direction * self.increment)

    def on_click(self, event: Click) -> None:
        width, height = self.size
        if self.horizontal:
            frac = event.x / max(1, width - 1)
        else:
            frac = 1 - event.y / max(1, height - 1)
        low, high = self.limits()
        self._set(low + frac * (high - low))


class ShapeWidget(Widget):
    """Filled rectangle, ellipse, arc or polygon approximated as a box."""

    def __init__(self, node: Node, ctx: BuildContext) -> None:
        super().__init__()
        self.fill: str | None = None
        if not node.flag("transparent", False):
            bg = node.color("background_color")
            if bg is not None and not is_transparent(bg):
                self.fill = color_hex(bg)
                self.styles.background = self.fill
        self.line: str | None = None
        if is_frame(node, ctx.scale):
            self.line = color_hex(node.color("line_color", BLACK))
            self.round = node.type == "ellipse"
            self.styles.border = ("round" if self.round else "solid", self.line)

    def render(self) -> Content:
        # The default Widget.render shows the class name
        return Content("")


class FrameEdge(Static):
    """One side of a transparent frame.

    Textual widgets hide whatever is beneath them, so a transparent frame is drawn as four
    edges instead of one box to keep widgets under its interior visible.
    """


def _frame_edges(rect: Rect, color: str, round_corners: bool) -> list[tuple[Widget, Rect]]:
    x, y, width, height = rect
    tl, tr, bl, br = "╭╮╰╯" if round_corners else "┌┐└┘"
    middle = "─" * max(width - 2, 0)
    side = "\n".join("│" * max(height - 2, 0))
    edges: list[tuple[Widget, Rect]] = [
        (FrameEdge(Content.styled(tl + middle + tr, color)), (x, y, width, 1)),
        (FrameEdge(Content.styled(bl + middle + br, color)), (x, y + height - 1, width, 1)),
    ]
    if height > 2:
        edges += [
            (FrameEdge(Content.styled(side, color)), (x, y + 1, 1, height - 2)),
            (FrameEdge(Content.styled(side, color)), (x + width - 1, y + 1, 1, height - 2)),
        ]
    return edges


class LineWidget(Widget):
    """Polyline drawn on the character grid."""

    def __init__(self, node: Node, ctx: BuildContext) -> None:
        super().__init__()
        self.scale = ctx.scale
        self.points = [(float(p.x), float(p.y)) for p in node.prop("points", []) or []]
        self.color = color_hex(node.color("line_color", Color((0, 0, 255))))

    def render(self) -> Content:
        cols, rows = self.size
        if cols <= 0 or rows <= 0 or len(self.points) < 2:
            return Content("")
        grid = [[" "] * cols for _ in range(rows)]
        cells = [(x / self.scale.cell_width, y / self.scale.cell_height) for x, y in self.points]
        for (x0, y0), (x1, y1) in zip(cells, cells[1:]):
            char = "─" if abs(y1 - y0) < 0.5 else "│" if abs(x1 - x0) < 0.5 else "•"
            steps = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
            for i in range(steps + 1):
                t = i / steps
                cx = min(max(int(x0 + (x1 - x0) * t), 0), cols - 1)
                cy = min(max(int(y0 + (y1 - y0) * t), 0), rows - 1)
                grid[cy][cx] = char
        return Content.styled("\n".join("".join(row) for row in grid), self.color)


class PlaceholderWidget(Static):
    """Stand-in for widget types that cannot be rendered in a terminal."""

    def __init__(self, node: Node, ctx: BuildContext, error: str = "") -> None:
        super().__init__(Content.styled(f"[{node.type}]", "red" if error else "dim italic"))
        self.styles.content_align = ("center", "middle")
        self.styles.color = "#808080"
        _, _, width, height = ctx.rect(node)
        if width >= 3 and height >= 3:
            self.styles.border = ("dashed", "#808080")
        self.tooltip = error or str(node.prop("pv_name", "") or "") or None


class GroupWidget(Container):
    def __init__(self, node: Node, ctx: BuildContext) -> None:
        self.built = build_widgets(node.children(), ctx)
        super().__init__(*self.built)
        self.styles.overflow_x = "hidden"
        self.styles.overflow_y = "hidden"
        fg = node.color("foreground_color", BLACK)
        line = node.color("line_color") or fg
        style = int(node.prop("style", GroupStyle.GROUP_BOX))
        if style in (GroupStyle.GROUP_BOX, GroupStyle.TITLE_BAR):
            self.styles.border = ("round" if style == GroupStyle.GROUP_BOX else "heavy", color_hex(line))
            self.border_title = Content(str(node.prop("name", "") or ""))
            self.styles.border_title_color = color_hex(fg)
        elif style == GroupStyle.LINE:
            self.styles.border = ("solid", color_hex(line))
        _apply_colors(self, node)
        _apply_text_style(self, node)


def _embedded_widgets(content: EmbeddedContent, ctx: BuildContext) -> list[Widget]:
    if content.error:
        return [Static(Content.styled(content.error, "red"))]
    return build_widgets(content.nodes, ctx)


class EmbeddedWidget(Container):
    def __init__(self, node: Node, ctx: BuildContext) -> None:
        content = node.embedded()
        self.built = _embedded_widgets(content, ctx)
        super().__init__(*self.built)
        self.styles.overflow_x = "hidden"
        self.styles.overflow_y = "hidden"
        if content.display is not None and not node.flag("transparent", False):
            self.styles.background = color_hex(content.display.background)
        if is_frame(node, ctx.scale):
            self.styles.border = ("solid", color_hex(node.color("border_color", BLACK)))


class TabsWidget(Container):
    DEFAULT_CSS = """
    TabsWidget TabbedContent {
        height: 1fr;
    }
    TabsWidget TabbedContent > ContentSwitcher {
        height: 1fr;
    }
    TabsWidget TabPane {
        height: 1fr;
        padding: 0;
    }
    """

    def __init__(self, node: Node, ctx: BuildContext) -> None:
        super().__init__()
        self.tabs = [(name, build_widgets(children, ctx.nested_display(children))) for name, children in node.tabs()]
        _apply_colors(self, node, fg_default=None)

    def compose(self) -> ComposeResult:
        with TabbedContent():
            for i, (name, widgets) in enumerate(self.tabs):
                yield TabPane(Content(name or f"Tab {i + 1}"), Canvas(*widgets))


class NavTabsWidget(TabsWidget):
    def __init__(self, node: Node, ctx: BuildContext) -> None:
        Container.__init__(self)
        self.tabs = []
        for tab in node.prop("tabs", []) or []:
            macros = {**node.macros, **clean_macros(tab.macros)}
            content = load_embedded(tab.file, macros, str(tab.group_name or ""), node.display_path, node.depth + 1)
            widgets = _embedded_widgets(content, ctx.nested_display(content.nodes))
            self.tabs.append((str(tab.name or ""), widgets))


def _bar(horizontal: bool | None, show_value: bool = False, slider: bool = False) -> Callable[[Node, BuildContext], Widget]:
    def factory(node: Node, ctx: BuildContext) -> Widget:
        is_horizontal = node.flag("horizontal", True) if horizontal is None else horizontal
        cls = SliderWidget if slider else BarWidget
        return cls(node, ctx, is_horizontal, show_value)

    return factory


FACTORIES: dict[str, Callable[[Node, BuildContext], Widget]] = {
    "label": LabelWidget,
    "textupdate": TextUpdateWidget,
    "textentry": TextEntryWidget,
    "spinner": SpinnerWidget,
    "text-symbol": TextSymbolWidget,
    "led": LEDWidget,
    "multi_state_led": MultiStateLEDWidget,
    "byte_monitor": ByteMonitorWidget,
    "action_button": ActionButtonWidget,
    "bool_button": BoolButtonWidget,
    "slide_button": lambda node, ctx: BoolButtonWidget(node, ctx, slide=True),
    "checkbox": CheckBoxWidget,
    "combo": ComboWidget,
    "choice": ComboWidget,
    "radio": ComboWidget,
    "progressbar": _bar(None),
    "tank": lambda node, ctx: BarWidget(node, ctx, node.flag("horizontal", False)),
    "thermometer": _bar(False),
    "meter": _bar(True, show_value=True),
    "linearmeter": lambda node, ctx: BarWidget(node, ctx, node.flag("horizontal", True), node.flag("show_value", True)),
    "scaledslider": _bar(None, show_value=True, slider=True),
    "scrollbar": _bar(None, slider=True),
    "rectangle": ShapeWidget,
    "ellipse": ShapeWidget,
    "arc": ShapeWidget,
    "polygon": ShapeWidget,
    "polyline": LineWidget,
    "group": GroupWidget,
    "embedded": EmbeddedWidget,
    "tabs": TabsWidget,
    "navtabs": NavTabsWidget,
}


Rect = tuple[int, int, int, int]


def _position(widget: Widget, rect: Rect) -> None:
    x, y, width, height = rect
    styles = widget.styles
    styles.position = "absolute"
    styles.offset = (x, y)
    styles.width = width
    styles.height = height
    styles.min_width = 0
    styles.min_height = 0
    styles.margin = 0


def place(widget: Widget, node: Node, ctx: BuildContext) -> Rect:
    x, y, width, height = ctx.rect(node)
    text_width = getattr(widget, "text_width", None)
    if text_width:
        shift = {1: (width - text_width) // 2, 2: width - text_width}.get(getattr(widget, "alignment", 0), 0)
        x, width = x + shift, text_width
    _position(widget, (x, y, width, height))
    return x, y, width, height


def _fills(widget: Widget, node: Node, rect: Rect, ctx: BuildContext) -> list[tuple[Rect, str]]:
    """Filled areas drawn by `widget`, in its container's coordinates."""
    if isinstance(widget, ShapeWidget):
        return [(rect, widget.fill)] if widget.fill else []
    fills: list[tuple[Rect, str]] = []
    border = 1 if is_frame(node, ctx.scale) else 0
    for child in getattr(widget, "built", []):
        for (fx, fy, fw, fh), color in getattr(child, "fills", []):
            fills.append(((fx + rect[0] + border, fy + rect[1] + border, fw, fh), color))
    return fills


def build_widgets(nodes: list[Node], ctx: BuildContext) -> list[Widget]:
    """Create Textual widgets for display nodes, in file order so later widgets draw on top."""
    widgets: list[Widget] = []
    fills: list[tuple[Rect, str]] = []
    for node in nodes:
        factory = FACTORIES.get(node.type if node.widget is not None else "", PlaceholderWidget)
        try:
            widget = factory(node, ctx)
        except Exception as e:
            log.exception("Failed to build %s widget %r", node.type, node.prop("name", ""))
            widget = PlaceholderWidget(node, ctx, error=str(e))
        rect = place(widget, node, ctx)
        parts = [widget]
        if isinstance(widget, ShapeWidget) and widget.fill is None:
            parts = []
            if widget.line is not None:
                for edge, edge_rect in _frame_edges(rect, widget.line, widget.round):
                    _position(edge, edge_rect)
                    parts.append(edge)
        visible = node.flag("visible", True)
        for part in parts:
            part.display = visible
        # Only our own (inline) styles count: Textual may have already applied its default CSS
        if not isinstance(widget, ShapeWidget) and not widget.styles.inline.has_rule("background"):
            # Transparent widgets only show their parent's background in Textual, so copy the
            # colour of a filled shape they are drawn on
            cx, cy = rect[0] + rect[2] // 2, rect[1] + rect[3] // 2
            for (fx, fy, fw, fh), color in reversed(fills):
                if fx <= cx < fx + fw and fy <= cy < fy + fh:
                    widget.styles.background = color
                    break
            else:
                # Otherwise Textual's dark theme background would show (e.g. Checkbox, Button)
                widget.styles.background = "transparent"
        widget_fills = _fills(widget, node, rect, ctx)
        setattr(widget, "fills", widget_fills)
        fills.extend(widget_fills)
        if parts:
            for rule in node.prop("rules", []) or []:
                ctx.rules.append(RuleBinding(parts, node, rule, ctx.pvs))
        widgets.extend(parts)
    return widgets
