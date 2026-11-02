from textual.color import Color

from phoebus_tui.widgets import LabelWidget


async def test_label_text_and_style(open_widgets, make_widget, make_color, text_of):
    font = '<font><font family="Liberation Sans" style="BOLD" size="14.0"/></font>'
    widget = make_widget("label", text="Hello", raw=font + make_color("foreground_color", 255, 0, 0))
    async with open_widgets(widget) as (app, pilot, pvs):
        label = app.query_one(LabelWidget)
        assert text_of(label) == "Hello"
        assert label.styles.color == Color(255, 0, 0)
        assert "bold" in str(label.styles.text_style)


async def test_transparent_single_line_label_fits_its_text(open_widgets, make_widget):
    async with open_widgets(make_widget("label", text="Hi", x=0, width=160)) as (app, pilot, pvs):
        label = app.query_one(LabelWidget)
        assert label.size.width == 2
        assert label.styles.offset.x.value == 0


async def test_centred_label_keeps_its_centre(open_widgets, make_widget):
    widget = make_widget("label", text="Hi", x=0, width=160, horizontal_alignment=1)
    async with open_widgets(widget) as (app, pilot, pvs):
        label = app.query_one(LabelWidget)
        assert label.size.width == 2
        assert label.styles.offset.x.value == 9


async def test_filled_label_keeps_its_box(open_widgets, make_widget, make_color):
    widget = make_widget("label", text="Hi", width=160, transparent="false", raw=make_color("background_color", 1, 2, 3))
    async with open_widgets(widget) as (app, pilot, pvs):
        label = app.query_one(LabelWidget)
        assert label.size.width == 20
        assert label.styles.background == Color(1, 2, 3)


async def test_transparent_label_shows_the_fill_of_a_shape_beneath(open_widgets, make_widget, make_color):
    rect = make_widget("rectangle", width=200, height=40, line_width=0, raw=make_color("background_color", 10, 20, 30))
    label = make_widget("label", text="Title", x=40, y=10)
    async with open_widgets(rect, label) as (app, pilot, pvs):
        assert app.query_one(LabelWidget).styles.background == Color(10, 20, 30)


async def test_label_outside_a_shape_keeps_no_background(open_widgets, make_widget, make_color):
    rect = make_widget("rectangle", width=100, height=20, line_width=0, raw=make_color("background_color", 10, 20, 30))
    label = make_widget("label", text="Away", x=200, y=100)
    async with open_widgets(rect, label) as (app, pilot, pvs):
        assert app.query_one(LabelWidget).styles.background.a == 0
