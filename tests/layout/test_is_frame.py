import pytest

from phoebus_tui.layout import Scale, is_frame


@pytest.fixture
def frame_node(load_nodes, make_widget, make_color):
    def make(wtype="rectangle", width=160, height=60, line_width=1, line_alpha=255, **props):
        raw = make_color("line_color", 0, 0, 0, line_alpha)
        return load_nodes(make_widget(wtype, width=width, height=height, line_width=line_width, raw=raw, **props))[0]

    return make


def test_rectangle_with_visible_border_is_a_frame(frame_node):
    assert is_frame(frame_node(), Scale())
    assert is_frame(frame_node("ellipse"), Scale())


@pytest.mark.parametrize(
    "kwargs",
    [{"width": 10}, {"height": 20}, {"line_width": 0}, {"line_alpha": 0}],
    ids=["narrow", "short", "no line", "transparent line"],
)
def test_rectangles_that_are_not_frames(frame_node, kwargs):
    assert not is_frame(frame_node(**kwargs), Scale())


def test_arc_is_never_a_frame(frame_node):
    assert not is_frame(frame_node("arc"), Scale())


@pytest.mark.parametrize(("style", "expected"), [(None, True), (0, True), (1, True), (2, True), (3, False)])
def test_group_styles(style, expected, load_nodes, make_widget):
    props = {} if style is None else {"style": style}
    (group,) = load_nodes(make_widget("group", **props))
    assert is_frame(group, Scale()) is expected


@pytest.mark.parametrize(("border", "expected"), [(0, False), (2, True)])
def test_embedded_border(border, expected, load_nodes, make_widget):
    (node,) = load_nodes(make_widget("embedded", border_width=border))
    assert is_frame(node, Scale()) is expected


def test_label_is_not_a_frame(load_nodes, make_widget):
    (node,) = load_nodes(make_widget("label"))
    assert not is_frame(node, Scale())
