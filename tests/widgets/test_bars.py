import pytest

from phoebus_tui.widgets import BarWidget, SliderWidget


async def test_progress_bar_fraction_and_render(open_widgets, make_widget, text_of):
    widget = make_widget("progressbar", pv_name="loc://a(50)", width=160, height=20, limits_from_pv="false")
    async with open_widgets(widget) as (app, pilot, pvs):
        bar = app.query_one(BarWidget)
        assert bar.fraction() == 0.5
        assert text_of(bar) == "█" * 10 + " " * 10
        pvs.get("loc://a").put(150)
        await pilot.pause()
        assert bar.fraction() == 1.0


async def test_limits_from_pv(open_widgets, make_widget):
    async with open_widgets(make_widget("progressbar", pv_name="loc://a(5)")) as (app, pilot, pvs):
        bar = app.query_one(BarWidget)
        pvs.get("loc://a")._update(lower=0.0, upper=10.0)
        await pilot.pause()
        assert bar.limits() == (0.0, 10.0)
        assert bar.fraction() == 0.5


async def test_vertical_tank(open_widgets, make_widget, text_of):
    widget = make_widget("tank", pv_name="loc://a(50)", width=16, height=80, limits_from_pv="false")
    async with open_widgets(widget) as (app, pilot, pvs):
        assert text_of(app.query_one(BarWidget)).split("\n") == ["  ", "  ", "██", "██"]


async def test_meter_shows_value_row(open_widgets, make_widget, text_of):
    widget = make_widget("meter", pv_name="loc://a(25)", width=80, height=40, limits_from_pv="false")
    async with open_widgets(widget) as (app, pilot, pvs):
        assert text_of(app.query_one(BarWidget)).split("\n")[-1].strip() == "25"


async def test_disconnected_bar_shows_pv_name(open_widgets, make_widget, text_of):
    async with open_widgets(make_widget("meter", pv_name="=x", width=80, height=40)) as (app, pilot, pvs):
        bar = app.query_one(BarWidget)
        assert bar.fraction() == 0.0
        assert text_of(bar).split("\n")[-1].strip() == "=x"


@pytest.mark.parametrize("value", ["nan", '"text"'])
async def test_unusable_values_render_empty(value, open_widgets, make_widget):
    async with open_widgets(make_widget("progressbar", pv_name=f"loc://a({value})")) as (app, pilot, pvs):
        assert app.query_one(BarWidget).fraction() == 0.0


async def test_slider_keys_and_click(open_widgets, make_widget):
    widget = make_widget(
        "scaledslider", pv_name="loc://a(5.0)", width=160, height=40, increment=2,
        minimum=0, maximum=10, limits_from_pv="false",
    )
    async with open_widgets(widget) as (app, pilot, pvs):
        slider = app.query_one(SliderWidget)
        slider.focus()
        await pilot.press("right")
        assert pvs.get("loc://a").state.value == 7.0
        await pilot.press("left", "left", "left", "left", "left")
        assert pvs.get("loc://a").state.value == 0.0
        await pilot.click(slider, offset=(slider.size.width - 1, 0))
        assert pvs.get("loc://a").state.value == 10.0


async def test_integer_slider_writes_integers(open_widgets, make_widget):
    widget = make_widget("scrollbar", pv_name="loc://a<VLong>(3)", minimum=0, maximum=10, limits_from_pv="false")
    async with open_widgets(widget) as (app, pilot, pvs):
        app.query_one(SliderWidget).focus()
        await pilot.press("up")
        assert pvs.get("loc://a").state.value == 4
        assert isinstance(pvs.get("loc://a").state.value, int)
