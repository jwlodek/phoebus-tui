from phoebus_tui.formatting import ALARM_COLORS, DISCONNECTED_COLOR
from phoebus_tui.pv import MAJOR
from phoebus_tui.widgets import TextSymbolWidget, TextUpdateWidget


async def test_shows_formatted_value_and_follows_updates(open_widgets, make_widget, text_of):
    async with open_widgets(make_widget("textupdate", pv_name="loc://a(1.25)", format=1, precision=1)) as (app, pilot, pvs):
        widget = app.query_one(TextUpdateWidget)
        assert text_of(widget) == "1.2"
        pvs.get("loc://a").put(3.0)
        await pilot.pause()
        assert text_of(widget) == "3.0"
        assert widget.tooltip == "loc://a(1.25)"


async def test_alarm_severity_colours_the_text(open_widgets, make_widget, span_styles):
    async with open_widgets(make_widget("textupdate", pv_name="loc://a(1)")) as (app, pilot, pvs):
        pvs.get("loc://a")._update(severity=MAJOR)
        await pilot.pause()
        assert span_styles(app.query_one(TextUpdateWidget).render()) == [ALARM_COLORS[MAJOR]]


async def test_disconnected_pv_shows_its_name(open_widgets, make_widget, text_of, span_styles):
    async with open_widgets(make_widget("textupdate", pv_name="=1+1")) as (app, pilot, pvs):
        widget = app.query_one(TextUpdateWidget)
        assert text_of(widget) == "=1+1"
        assert span_styles(widget.render()) == [DISCONNECTED_COLOR]


async def test_string_format(open_widgets, make_widget, text_of):
    async with open_widgets(make_widget("textupdate", pv_name="loc://a(72, 105)", format=6)) as (app, pilot, pvs):
        assert text_of(app.query_one(TextUpdateWidget)) == "Hi"


async def test_no_wrap(open_widgets, make_widget):
    async with open_widgets(make_widget("textupdate", pv_name="loc://a", wrap_words="false")) as (app, pilot, pvs):
        widget = app.query_one(TextUpdateWidget)
        assert widget.styles.text_wrap == "nowrap"
        assert widget.styles.text_overflow == "ellipsis"


async def test_text_symbol(open_widgets, make_widget, text_of):
    symbols = "<symbols><symbol>Zero</symbol><symbol>One</symbol></symbols>"
    async with open_widgets(make_widget("text-symbol", pv_name="loc://a(1)", raw=symbols)) as (app, pilot, pvs):
        widget = app.query_one(TextSymbolWidget)
        assert text_of(widget) == "One"
        pvs.get("loc://a").put(5)
        await pilot.pause()
        assert text_of(widget) == ""
