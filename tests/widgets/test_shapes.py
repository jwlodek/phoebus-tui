from textual.color import Color

from phoebus_tui.widgets import FrameEdge, LineWidget, ShapeWidget


async def test_filled_rectangle(open_widgets, make_widget, make_color, text_of):
    rect = make_widget("rectangle", width=160, height=60, line_width=0, raw=make_color("background_color", 1, 2, 3))
    async with open_widgets(rect) as (app, pilot, pvs):
        shape = app.query_one(ShapeWidget)
        assert shape.styles.background == Color(1, 2, 3)
        assert text_of(shape) == ""
        assert not app.query(FrameEdge)


async def test_filled_frame_keeps_its_border(open_widgets, make_widget, make_color):
    rect = make_widget("rectangle", width=160, height=60, line_width=1, raw=make_color("line_color", 9, 9, 9))
    async with open_widgets(rect) as (app, pilot, pvs):
        assert app.query_one(ShapeWidget).styles.border_top == ("solid", Color(9, 9, 9))


async def test_transparent_frame_is_drawn_as_edges(open_widgets, make_widget, make_color, text_of):
    rect = make_widget(
        "rectangle", width=160, height=60, line_width=1, transparent="true", raw=make_color("line_color", 0, 0, 0)
    )
    async with open_widgets(rect) as (app, pilot, pvs):
        assert not app.query(ShapeWidget)
        edges = list(app.query(FrameEdge))
        top, bottom, left, right = (text_of(edge) for edge in edges)
        assert top.startswith("┌") and top.endswith("┐")
        assert bottom.startswith("└") and bottom.endswith("┘")
        assert set(left) == set(right) == {"│", "\n"}


async def test_transparent_ellipse_frame_has_round_corners(open_widgets, make_widget, make_color, text_of):
    ellipse = make_widget(
        "ellipse", width=160, height=60, line_width=1, transparent="true", raw=make_color("line_color", 0, 0, 0)
    )
    async with open_widgets(ellipse) as (app, pilot, pvs):
        assert text_of(app.query(FrameEdge).first()).startswith("╭")


async def test_transparent_shape_without_border_draws_nothing(open_widgets, make_widget):
    async with open_widgets(make_widget("rectangle", transparent="true", line_width=0)) as (app, pilot, pvs):
        assert not app.query(ShapeWidget)
        assert not app.query(FrameEdge)


async def test_polyline(open_widgets, make_widget, text_of):
    points = '<points><point x="0" y="10"/><point x="80" y="10"/></points>'
    async with open_widgets(make_widget("polyline", width=80, height=20, raw=points)) as (app, pilot, pvs):
        assert set(text_of(app.query_one(LineWidget))) == {"─"}


async def test_polyline_needs_two_points(open_widgets, make_widget, text_of):
    points = '<points><point x="0" y="10"/></points>'
    async with open_widgets(make_widget("polyline", raw=points)) as (app, pilot, pvs):
        assert text_of(app.query_one(LineWidget)) == ""
