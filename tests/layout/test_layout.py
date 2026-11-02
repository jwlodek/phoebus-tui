import pytest

from phoebus_tui.layout import Layout, Scale


@pytest.fixture
def layout_of(load_nodes):
    """Lay out widgets; returns the layout and the top-level nodes."""

    def lay_out(*widgets, scale=Scale()):
        nodes = load_nodes(*widgets)
        return Layout(scale, nodes), nodes

    return lay_out


@pytest.fixture
def frame(make_widget, make_color):
    def make(x, y, width, height, raw=""):
        return make_widget(
            "rectangle", x=x, y=y, width=width, height=height, line_width=1, transparent="true",
            raw=make_color("line_color", 0, 0, 0) + raw,
        )

    return make


def _inside(inner, outer):
    ix, iy, iw, ih = inner
    ox, oy, ow, oh = outer
    return ox < ix and ix + iw <= ox + ow - 1 and oy < iy and iy + ih <= oy + oh - 1


def test_plain_widget_scales_by_cell_size(layout_of, make_widget):
    layout, (label,) = layout_of(make_widget("label", x=80, y=40, width=100, height=20))
    assert layout.rect(label) == (10, 2, 13, 1)


def test_custom_scale(layout_of, make_widget):
    layout, (label,) = layout_of(make_widget("label", x=80, y=40, width=100, height=20), scale=Scale(10, 10))
    assert layout.rect(label) == (8, 4, 10, 2)


def test_single_row_widgets_a_pixel_apart_share_a_row(layout_of, make_widget):
    layout, (label, readout) = layout_of(
        make_widget("label", x=80, y=34, width=90, height=20),
        make_widget("textupdate", x=175, y=35, width=165, height=18),
    )
    assert layout.rect(label)[1] == layout.rect(readout)[1]


def test_widgets_drawn_on_a_frame_stay_inside_its_border(layout_of, frame, make_widget):
    layout, (box, top, bottom) = layout_of(
        frame(0, 0, 400, 200),
        make_widget("label", x=10, y=5, width=100, height=20),
        make_widget("label", x=280, y=175, width=110, height=20),
    )
    assert _inside(layout.rect(top), layout.rect(box))
    assert _inside(layout.rect(bottom), layout.rect(box))


def test_frame_grows_to_fit_its_contents(layout_of, frame, make_widget):
    layout, (box, *labels) = layout_of(
        frame(0, 0, 200, 60),
        *(make_widget("label", x=10, y=y, width=100, height=20) for y in (0, 20, 40)),
    )
    assert layout.rect(box)[3] >= 5
    assert all(_inside(layout.rect(label), layout.rect(box)) for label in labels)
    assert len({layout.rect(label)[1] for label in labels}) == 3


def test_nested_frames(layout_of, frame, make_widget):
    layout, (outer, inner, label) = layout_of(
        frame(0, 0, 400, 200),
        frame(20, 20, 200, 100),
        make_widget("label", x=40, y=40, width=80, height=20),
    )
    assert _inside(layout.rect(inner), layout.rect(outer))
    assert _inside(layout.rect(label), layout.rect(inner))


def test_adjacent_frames_do_not_share_a_border(layout_of, frame):
    layout, (left, right) = layout_of(frame(0, 0, 160, 60), frame(160, 0, 160, 60))
    lx, _, lw, _ = layout.rect(left)
    rx, _, _, _ = layout.rect(right)
    assert lx + lw <= rx


def test_borderless_group_children_use_group_coordinates(layout_of, make_widget):
    group = make_widget("group", x=80, y=40, width=200, height=100, style=3, raw=make_widget("label", x=0, y=0))
    layout, (node,) = layout_of(group)
    (label,) = node.children()
    assert layout.rect(node)[:2] == (10, 2)
    assert layout.rect(label)[:2] == (0, 0)


def test_bordered_group_grows_to_fit_border_and_children(layout_of, make_widget):
    group = make_widget("group", x=0, y=0, width=80, height=20, raw=make_widget("label", x=0, y=0, width=80, height=20))
    layout, (node,) = layout_of(group)
    (label,) = node.children()
    _, _, width, height = layout.rect(node)
    _, _, label_width, label_height = layout.rect(label)
    assert width >= label_width + 2
    assert height >= label_height + 2


def test_borderless_group_grows_to_fit_a_same_sized_frame(layout_of, frame, make_widget):
    group = make_widget("group", x=0, y=0, width=160, height=60, style=3, raw=frame(0, 0, 160, 60))
    layout, (node,) = layout_of(group)
    (box,) = node.children()
    _, _, gw, gh = layout.rect(node)
    bx, by, bw, bh = layout.rect(box)
    assert bx + bw <= gw and by + bh <= gh


def test_embedded_display_grows_to_fit_its_content(layout_of, frame, make_widget, make_display, write_bob):
    write_bob(make_display(frame(0, 0, 160, 60), make_widget("label", x=10, y=10)), "inner.bob")
    layout, (embedded,) = layout_of(make_widget("embedded", file="inner.bob", width=160, height=60))
    inner_frame = embedded.embedded().nodes[0]
    _, _, width, height = layout.rect(embedded)
    fx, fy, fw, fh = layout.rect(inner_frame)
    assert fx + fw <= width and fy + fh <= height


def test_nodes_outside_the_layout_fall_back_to_plain_scaling(load_nodes, make_widget):
    (label,) = load_nodes(make_widget("label", x=80, y=40, width=100, height=20))
    assert Layout(Scale(), []).rect(label) == (10, 2, 13, 1)


def test_extent(layout_of, make_widget):
    layout, (label,) = layout_of(make_widget("label", x=80, y=40, width=100, height=20))
    assert layout.extent == (23, 3)
