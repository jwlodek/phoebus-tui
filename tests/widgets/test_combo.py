from textual.widgets import Select

from phoebus_tui.widgets import ComboWidget

ENUM_PV = 'loc://mode<VEnum>(0, "Idle", "Running", "Fault")'


def options(combo):
    return [str(option.prompt) for option in combo.query_one("SelectOverlay")._options]


async def test_options_come_from_the_pv_without_a_blank_entry(open_widgets, make_widget):
    async with open_widgets(make_widget("combo", pv_name=ENUM_PV)) as (app, pilot, pvs):
        combo = app.query_one(ComboWidget)
        assert options(combo) == ["Idle", "Running", "Fault"]
        assert combo.value == "Idle"
        assert pvs.get("loc://mode").state.value == 0


async def test_choosing_an_option_writes_it(open_widgets, make_widget):
    async with open_widgets(make_widget("combo", pv_name=ENUM_PV)) as (app, pilot, pvs):
        await pilot.click(app.query_one(ComboWidget))
        await pilot.press("down", "down", "enter")
        assert pvs.get("loc://mode").state.value == 2


async def test_pv_updates_change_the_selection(open_widgets, make_widget):
    async with open_widgets(make_widget("combo", pv_name=ENUM_PV)) as (app, pilot, pvs):
        pvs.get("loc://mode").put(1)
        await pilot.pause()
        assert app.query_one(ComboWidget).value == "Running"


async def test_static_items(open_widgets, make_widget):
    items = "<items><item>1.5</item><item>2.5</item></items>"
    widget = make_widget("combo", pv_name="loc://x(2.5)", items_from_pv="false", raw=items)
    async with open_widgets(widget) as (app, pilot, pvs):
        combo = app.query_one(ComboWidget)
        assert options(combo) == ["1.5", "2.5"]
        assert combo.value == "2.5"
        await pilot.click(combo)
        await pilot.press("up", "enter")
        assert pvs.get("loc://x").state.value == 1.5


async def test_disconnected_without_items_is_blank(open_widgets, make_widget):
    async with open_widgets(make_widget("combo", pv_name="=x")) as (app, pilot, pvs):
        assert app.query_one(ComboWidget).value == Select.NULL


async def test_colours_reach_the_inner_widgets(open_widgets, make_widget, make_color):
    raw = make_color("background_color", 1, 2, 3) + make_color("foreground_color", 4, 5, 6)
    async with open_widgets(make_widget("combo", pv_name=ENUM_PV, raw=raw)) as (app, pilot, pvs):
        current = app.query_one(ComboWidget).query_one("SelectCurrent")
        assert current.styles.background.rgb == (1, 2, 3)
        assert current.styles.color.rgb == (4, 5, 6)
