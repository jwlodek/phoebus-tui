"""Conversion of Phoebus pixel geometry into terminal cell boxes."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from phoebusgen.v4.properties.types import GroupStyle

from .model import Node, is_transparent

# Widgets that become Textual containers; their children use the container's coordinates
CONTAINER_TYPES = ("group", "embedded")


def _round(value: float) -> int:
    return math.floor(value + 0.5)


@dataclass(frozen=True)
class Scale:
    """Display pixels per terminal cell."""

    cell_width: float = 8.0
    cell_height: float = 20.0


def is_frame(node: Node, scale: Scale) -> bool:
    """Whether the node draws a border that the widgets on or inside it must stay within."""
    if node.type == "group":
        return int(node.prop("style", GroupStyle.GROUP_BOX)) != GroupStyle.NONE
    if node.type == "embedded":
        return int(node.prop("border_width", 0)) > 0
    if node.type not in ("rectangle", "ellipse"):
        return False
    line = node.color("line_color")
    if line is None or is_transparent(line) or int(node.prop("line_width", 0)) <= 0:
        return False
    _, _, width, height = node.geometry()
    return width >= 2 * scale.cell_width and height >= 2 * scale.cell_height


@dataclass(eq=False)
class _Item:
    node: Node
    x: float
    y: float
    width: float
    height: float
    frame: bool
    container: bool
    children: list[_Item] = field(default_factory=list)
    need: tuple[int, int] = (0, 0)  # required outer size in cells
    local: tuple[int, int, int, int] = (0, 0, 0, 0)  # x0, y0, x1, y1 relative to the owner's content origin

    @property
    def border(self) -> int:
        return 1 if self.frame else 0

    def contains_center_of(self, other: _Item) -> bool:
        cx, cy = other.x + other.width / 2, other.y + other.height / 2
        return (self.x <= cx < self.x + self.width and self.y <= cy < self.y + self.height
                and other.width * other.height < self.width * self.height)


class _Axis:
    """Maps pixel positions along one axis to cells, with extra cells inserted at frame/container edges."""

    def __init__(self, cell: float, origin: float) -> None:
        self.cell = cell
        self.origin = origin
        self._starts: dict[float, int] = {}
        self._ends: dict[float, int] = {}

    def reserve(self, start: float, end: float, before: int, after: int) -> None:
        # Edges shared by several items reserve the maximum, not the sum
        self._starts[start] = max(self._starts.get(start, 0), before)
        self._ends[end] = max(self._ends.get(end, 0), after)

    def base(self, p: float) -> int:
        return _round((p - self.origin) / self.cell)

    def _inserted(self, p: float, inclusive: bool) -> int:
        edges = [*self._starts.items(), *self._ends.items()]
        return sum(n for e, n in edges if e < p or (inclusive and e == p))

    def start(self, p: float) -> int:
        return self.base(p) + self._inserted(p, inclusive=True)

    def end(self, p: float) -> int:
        return self.base(p) + self._inserted(p, inclusive=False)


def _items(nodes: list[Node], scale: Scale) -> list[_Item]:
    items = []
    for node in nodes:
        x, y, width, height = node.geometry()
        container = node.type in CONTAINER_TYPES
        item = _Item(node, x, y, width, height, is_frame(node, scale), container)
        if container:
            item.children = _items(node.contents(), scale)
        items.append(item)

    # Plain frames (rectangles) adopt the siblings drawn on them so those are laid out inside the border
    frames = [item for item in items if item.frame and not item.container]
    if not frames:
        return items
    top = []
    for item in items:
        owners = [f for f in frames if f is not item and f.contains_center_of(item)]
        if owners:
            min(owners, key=lambda f: f.width * f.height).children.append(item)
        else:
            top.append(item)
    return top


def _layout(items: list[_Item], ox: float, oy: float, scale: Scale) -> tuple[int, int]:
    """Assign `local` boxes to items relative to pixel origin (ox, oy); returns the content extent in cells."""
    xs, ys = _Axis(scale.cell_width, ox), _Axis(scale.cell_height, oy)
    for item in items:
        if item.children or item.frame:
            # Container children are relative to the container; adopted children share our coordinates
            cox, coy = (0.0, 0.0) if item.container else (item.x, item.y)
            width, height = _layout(item.children, cox, coy, scale)
            b = item.border
            item.need = (width + 2 * b, height + 2 * b)
            x0, x1, y0, y1 = item.x, item.x + item.width, item.y, item.y + item.height
            xs.reserve(x0, x1, b, max(b, item.need[0] - (xs.base(x1) - xs.base(x0)) - b))
            ys.reserve(y0, y1, b, max(b, item.need[1] - (ys.base(y1) - ys.base(y0)) - b))

    extent_x = extent_y = 0
    for item in items:
        x0, x1 = xs.start(item.x), xs.end(item.x + item.width)
        if item.children or item.frame:
            y0, y1 = ys.start(item.y), ys.end(item.y + item.height)
            b = item.border
            x0, y0 = x0 - b, y0 - b
            x1, y1 = max(x1 + b, x0 + item.need[0]), max(y1 + b, y0 + item.need[1])
        else:
            rows = max(1, _round(item.height / scale.cell_height))
            if rows == 1:
                # Snap single-row widgets by their centre so a label and readout 1-2px apart share a row
                y0 = ys.start(item.y + item.height / 2 - scale.cell_height / 2)
                y1 = y0 + 1
            else:
                y0, y1 = ys.start(item.y), ys.end(item.y + item.height)
        item.local = (x0, y0, max(x1, x0 + 1), max(y1, y0 + 1))
        extent_x, extent_y = max(extent_x, item.local[2]), max(extent_y, item.local[3])
    return extent_x, extent_y


class Layout:
    """Cell boxes for every widget of a display, relative to the Textual container holding it.

    Terminal borders take a whole cell where Phoebus draws a thin outline, so frames lay out
    the widgets drawn on them locally and grow as needed instead of overlapping them.
    """

    def __init__(self, scale: Scale, nodes: list[Node]) -> None:
        self.scale = scale
        self._boxes: dict[int, tuple[int, int, int, int]] = {}
        items = _items(nodes, scale)
        self.extent = _layout(items, 0.0, 0.0, scale)
        self._place(items, 0, 0)

    def _place(self, items: list[_Item], dx: int, dy: int) -> None:
        for item in items:
            x0, y0, x1, y1 = item.local
            self._boxes[id(item.node)] = (x0 + dx, y0 + dy, x1 - x0, y1 - y0)
            if item.container:
                self._place(item.children, 0, 0)
            else:
                self._place(item.children, x0 + dx + item.border, y0 + dy + item.border)

    def rect(self, node: Node) -> tuple[int, int, int, int]:
        """(x, y, width, height) in cells relative to the node's Textual container."""
        box = self._boxes.get(id(node))
        if box is not None:
            return box
        x, y, width, height = node.geometry()
        x0, y0 = _round(x / self.scale.cell_width), _round(y / self.scale.cell_height)
        x1, y1 = _round((x + width) / self.scale.cell_width), _round((y + height) / self.scale.cell_height)
        return x0, y0, max(1, x1 - x0), max(1, y1 - y0)
