from textual.color import Color

from phoebus_tui.formatting import DISCONNECTED_COLOR
from phoebus_tui.widgets import ByteMonitorWidget, LEDWidget, MultiStateLEDWidget


async def test_led_follows_pv(open_widgets, make_widget, make_color, text_of, span_styles):
    colors = make_color("on_color", 0, 255, 0) + make_color("off_color", 10, 10, 10)
    async with open_widgets(make_widget("led", pv_name="loc://a(0)", raw=colors)) as (app, pilot, pvs):
        led = app.query_one(LEDWidget)
        assert (text_of(led), span_styles(led.render())) == ("●", ["#0a0a0a"])
        pvs.get("loc://a").put(1)
        await pilot.pause()
        assert span_styles(led.render()) == ["#00ff00"]


async def test_led_bit_and_labels(open_widgets, make_widget, make_color, text_of):
    raw = make_color("on_color", 255, 255, 255)
    widget = make_widget("led", pv_name="loc://a(4)", bit=2, on_label="ON", off_label="OFF", raw=raw)
    async with open_widgets(widget) as (app, pilot, pvs):
        led = app.query_one(LEDWidget)
        assert text_of(led) == "ON"
        assert led.styles.background == Color(255, 255, 255)
        pvs.get("loc://a").put(3)
        await pilot.pause()
        assert text_of(led) == "OFF"


async def test_disconnected_led(open_widgets, make_widget, span_styles):
    async with open_widgets(make_widget("led", pv_name="=x")) as (app, pilot, pvs):
        assert span_styles(app.query_one(LEDWidget).render()) == [DISCONNECTED_COLOR]


async def test_multi_state_led(open_widgets, make_widget, make_color, text_of):
    states = (
        "<states>"
        f"<state><value>0</value><label>Idle</label>{make_color('color', 0, 0, 255)}</state>"
        f"<state><value>1</value><label>Busy</label>{make_color('color', 255, 0, 0)}</state>"
        "</states>"
    )
    widget = make_widget("multi_state_led", pv_name="loc://a(0)", fallback_label="???", raw=states)
    async with open_widgets(widget) as (app, pilot, pvs):
        led = app.query_one(MultiStateLEDWidget)
        assert text_of(led) == "Idle"
        assert led.styles.background == Color(0, 0, 255)
        for value, expected in ((1, "Busy"), (7, "???")):
            pvs.get("loc://a").put(value)
            await pilot.pause()
            assert text_of(led) == expected


async def test_byte_monitor(open_widgets, make_widget, make_color, span_styles):
    colors = make_color("on_color", 0, 255, 0) + make_color("off_color", 0, 0, 0)
    widget = make_widget("byte_monitor", pv_name="loc://a(5)", numBits=4, raw=colors)
    async with open_widgets(widget) as (app, pilot, pvs):
        monitor = app.query_one(ByteMonitorWidget)
        # Most significant bit first
        assert span_styles(monitor.render()) == ["#000000", "#00ff00", "#000000", "#00ff00"]


async def test_byte_monitor_reversed_vertical(open_widgets, make_widget, make_color, text_of, span_styles):
    colors = make_color("on_color", 0, 255, 0) + make_color("off_color", 0, 0, 0)
    widget = make_widget("byte_monitor", pv_name="loc://a(1)", numBits=2, bitReverse="true", horizontal="false", raw=colors)
    async with open_widgets(widget) as (app, pilot, pvs):
        monitor = app.query_one(ByteMonitorWidget)
        assert text_of(monitor) == "●\n●"
        assert span_styles(monitor.render()) == ["#00ff00", "#000000"]
