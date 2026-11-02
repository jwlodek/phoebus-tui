"""Load .bob displays via phoebusgen and apply the runtime macro expansion phoebusgen does not do."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from phoebusgen.v4.properties.property_helpers import PropertyBase
from phoebusgen.v4.properties.types import Color, FontStyle
from phoebusgen.v4.screen import Screen
from phoebusgen.v4.widgets import Widget

_MACRO_RE = re.compile(r"\$\((\w+)\)|\$\{(\w+)\}")

# Widgets whose own <macros> apply to themselves and their children.
_SCOPING_TYPES = {"group", "tabs"}
MAX_EMBED_DEPTH = 8


def expand_macros(text: str, lookup: Callable[[str], str | None]) -> str:
    """Replace $(NAME) and ${NAME}, leaving unknown macros untouched."""

    def repl(match: re.Match[str]) -> str:
        value = lookup(match.group(1) or match.group(2))
        return match.group(0) if value is None else value

    for _ in range(10):  # bounded to break recursive macro definitions
        new_text = _MACRO_RE.sub(repl, text)
        if new_text == text:
            break
        text = new_text
    return text


def get(obj: Any, name: str, default: Any = None) -> Any:
    """Read a phoebusgen property, falling back to `default` if absent or malformed in the XML."""
    if obj is None:
        return default
    try:
        return getattr(obj, name)
    except Exception:
        return default


def to_color(value: Any, default: Color | None = None) -> Color | None:
    if value is None:
        return default
    try:
        return value if isinstance(value, Color) else Color(tuple(value) if isinstance(value, list) else value)
    except (ValueError, TypeError):
        return default


def color_hex(color: Color) -> str:
    return "#{:02x}{:02x}{:02x}".format(*color[:3])


def is_transparent(color: Color) -> bool:
    return len(color) == 4 and color[3] == 0


def contrast(color: Color) -> str:
    """Black or white, whichever is more readable on top of `color`."""
    luma = 0.299 * color[0] + 0.587 * color[1] + 0.114 * color[2]
    return "#000000" if luma > 140 else "#ffffff"


def font_style(widget: Any) -> str:
    style = get(get(widget, "font"), "style")
    return {
        FontStyle.BOLD: "bold",
        FontStyle.ITALIC: "italic",
        FontStyle.BOLD_AND_ITALIC: "bold italic",
    }.get(style, "")


def _scoped_macros(element: ET.Element, parent: dict[str, str]) -> dict[str, str]:
    scope = dict(parent)
    macros_el = element.find("macros")
    if macros_el is not None:
        for macro in macros_el:
            if macro.tag != "include_parent_macros":
                scope[macro.tag] = expand_macros(macro.text or "", parent.get)
    return scope


def _expand_properties(element: ET.Element, lookup: Callable[[str], str | None]) -> None:
    """Expand macros in all property text/attributes of `element`, not descending into child widgets."""
    for child in element:
        if child.tag == "widget":
            continue
        if child.text:
            child.text = expand_macros(child.text, lookup)
        for key, value in child.attrib.items():
            child.attrib[key] = expand_macros(value, lookup)
        _expand_properties(child, lookup)


@dataclass
class Node:
    """A phoebusgen widget together with the macro scope and display file it belongs to."""

    widget: Widget | None  # None when phoebusgen does not know the widget type
    element: ET.Element
    macros: dict[str, str]
    display_path: Path
    depth: int = 0  # embedded display nesting level
    _children: list[Node] | None = field(default=None, init=False, repr=False, compare=False)
    _embedded: EmbeddedContent | None = field(default=None, init=False, repr=False, compare=False)

    @property
    def type(self) -> str:
        return self.element.get("type", "unknown")

    def prop(self, name: str, default: Any = None) -> Any:
        """Typed phoebusgen property, or the raw XML text for properties phoebusgen does not model."""
        if self.widget is not None and name in self.widget.get_property_names():
            return get(self.widget, name, default)
        text = self.element.findtext(name)
        return default if text is None else text

    def flag(self, name: str, default: bool) -> bool:
        value = self.prop(name, default)
        if isinstance(value, str):
            return value.strip().lower() == "true"
        return bool(value)

    def color(self, name: str, default: Color | None = None) -> Color | None:
        if self.widget is not None and name in self.widget.get_property_names():
            return to_color(get(self.widget, name), default)
        element = self.element.find(name)
        if element is None:
            return default
        try:
            return PropertyBase._get_color_property(element)
        except (ValueError, TypeError):
            return default

    def geometry(self) -> tuple[float, float, float, float]:
        if self.widget is not None:
            return (get(self.widget, "x", 0), get(self.widget, "y", 0),
                    get(self.widget, "width", 100), get(self.widget, "height", 20))

        def raw(tag: str, default: float) -> float:
            el = self.element.find(tag)
            try:
                return float(el.text) if el is not None and el.text else default
            except ValueError:
                return default

        return raw("x", 0), raw("y", 0), raw("width", 100), raw("height", 20)

    def children(self) -> list[Node]:
        # Parsed one by one so a single unknown child type doesn't break the whole container
        if self._children is None:
            self._children = [
                parse_widget(el, self.macros, self.display_path, self.depth) for el in self.element.findall("widget")
            ]
        return self._children

    def embedded(self) -> EmbeddedContent:
        """Content of an embedded display widget."""
        if self._embedded is None:
            macros = {**self.macros, **clean_macros(self.prop("macros"))}
            group_name = str(self.prop("group_name", "") or "")
            self._embedded = load_embedded(self.prop("file"), macros, group_name, self.display_path, self.depth + 1)
        return self._embedded

    def contents(self) -> list[Node]:
        """Widgets laid out inside this one, in the same coordinate system."""
        if self.type == "group":
            return self.children()
        if self.type == "embedded":
            return self.embedded().nodes
        return []

    def tabs(self) -> list[tuple[str, list[Node]]]:
        result = []
        for tab in self.element.findall("tabs/tab"):
            name = tab.findtext("name", "")
            children = [
                parse_widget(el, self.macros, self.display_path, self.depth) for el in tab.findall("children/widget")
            ]
            result.append((name, children))
        return result


def parse_widget(element: ET.Element, macros: dict[str, str], display_path: Path, depth: int = 0) -> Node:
    scope = _scoped_macros(element, macros) if element.get("type") in _SCOPING_TYPES else macros
    # Phoebus lets widgets reference their own properties as macros, e.g. $(pv_name)
    props = {child.tag: child.text for child in element if len(child) == 0 and child.text}
    _expand_properties(element, lambda name: scope.get(name, props.get(name)))
    try:
        widget = Widget.from_element(element)
    except (ValueError, KeyError):
        widget = None
    return Node(widget, element, scope, display_path, depth)


@dataclass
class Display:
    screen: Screen
    path: Path
    macros: dict[str, str]
    name: str = ""  # empty when the file doesn't name the display

    @property
    def title(self) -> str:
        return self.name or str(self.path)

    @property
    def size(self) -> tuple[float, float]:
        return get(self.screen, "width", 800), get(self.screen, "height", 600)

    @property
    def background(self) -> Color:
        return to_color(get(self.screen, "background_color"), Color((255, 255, 255)))

    def nodes(self, depth: int = 0) -> list[Node]:
        return [parse_widget(el, self.macros, self.path, depth) for el in self.screen.root.findall("widget")]


def load_display(path: str | Path, macros: dict[str, str] | None = None) -> Display:
    """Load a .bob file. Macros passed in override those defined in the file."""
    path = Path(path).resolve()
    if not path.is_file():
        # phoebusgen silently creates an empty screen for missing files
        raise FileNotFoundError(f"Display file not found: {path}")
    # phoebusgen fills in "Display" for a missing name, so read the file's own name first
    raw_name = (ET.parse(path).getroot().findtext("name") or "").strip()
    screen = Screen(f_name=path)
    if screen.root.tag != "display":
        raise ValueError(f"{path} is not a Phoebus .bob display file")

    passed = dict(macros or {})
    merged = {**_scoped_macros(screen.root, passed), **passed}
    merged.setdefault("DNAME", raw_name or path.stem)
    _expand_properties(screen.root, merged.get)
    return Display(screen, path, merged, expand_macros(raw_name, merged.get))


def resolve_display_path(file: str | Path | None, parent: Path) -> Path:
    """Resolve a display reference relative to the display that references it."""
    text = str(file or "")
    if text in ("", "."):
        raise ValueError("No display file specified")
    if "://" in text:
        raise ValueError(f"Remote displays are not supported: {text}")
    path = Path(text)
    if not path.is_absolute():
        path = parent.parent / path
    if path.suffix == ".opi" and path.with_suffix(".bob").exists():
        path = path.with_suffix(".bob")
    return path


def clean_macros(macros: Any) -> dict[str, str]:
    return {str(k): str(v or "") for k, v in dict(macros or {}).items()}


@dataclass
class EmbeddedContent:
    display: Display | None
    nodes: list[Node]
    error: str = ""


def _find_group(nodes: list[Node], name: str) -> Node | None:
    for node in nodes:
        if node.type == "group":
            if node.prop("name", "") == name:
                return node
            found = _find_group(node.children(), name)
            if found is not None:
                return found
    return None


def load_embedded(file: Any, macros: dict[str, str], group_name: str, parent: Path, depth: int) -> EmbeddedContent:
    """Load the widgets shown by an embedded display or navigation tab."""
    if depth > MAX_EMBED_DEPTH:
        return EmbeddedContent(None, [], "Embedded displays nested too deeply")
    try:
        display = load_display(resolve_display_path(file, parent), macros)
    except Exception as e:
        return EmbeddedContent(None, [], f"Cannot load {file}: {e}")
    nodes = display.nodes(depth)
    if group_name:
        group = _find_group(nodes, group_name)
        if group is None:
            return EmbeddedContent(display, [], f"No group {group_name!r} in {file}")
        nodes = group.children()
    return EmbeddedContent(display, nodes)


def format_ordinal(widget: Any) -> int:
    """Phoebus FormatOption ordinal of a widget's `format` property."""
    # phoebusgen's Format enum omits EXPONENTIAL, so ordinals >= 2 would be misread
    text = widget.root.findtext("format") if widget is not None else None
    if text is not None:
        try:
            return int(text)
        except ValueError:
            pass
    return int(get(widget, "format", 0))
