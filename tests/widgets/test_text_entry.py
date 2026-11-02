from phoebus_tui.widgets import SpinnerWidget, TextEntryWidget


async def test_shows_value_and_placeholder(open_widgets, make_widget):
    async with open_widgets(make_widget("textentry", pv_name="loc://a(2.5)", precision=2, format=1)) as (app, pilot, pvs):
        entry = app.query_one(TextEntryWidget)
        assert entry.value == "2.50"
        assert entry.placeholder == "loc://a"


async def test_submit_writes_and_reverts_to_pv_value(open_widgets, make_widget):
    async with open_widgets(make_widget("textentry", pv_name="loc://a(1.0)")) as (app, pilot, pvs):
        entry = app.query_one(TextEntryWidget)
        entry.focus()
        entry.value = "4.5"
        await pilot.press("enter")
        assert pvs.get("loc://a").state.value == 4.5
        assert entry.value == "4.5"


async def test_invalid_input_is_reported_not_written(open_widgets, make_widget, notifications):
    async with open_widgets(make_widget("textentry", pv_name="loc://a(1.0)")) as (app, pilot, pvs):
        messages = notifications(app)
        entry = app.query_one(TextEntryWidget)
        entry.focus()
        entry.value = "abc"
        await pilot.press("enter")
        assert pvs.get("loc://a").state.value == 1.0
        assert messages == [("Invalid value for loc://a: 'abc'", "error")]


async def test_write_failure_is_reported(open_widgets, make_widget, notifications):
    async with open_widgets(make_widget("textentry", pv_name="=1+1")) as (app, pilot, pvs):
        messages = notifications(app)
        entry = app.query_one(TextEntryWidget)
        entry.focus()
        entry.value = "3"
        await pilot.press("enter")
        assert messages == [("=1+1: Formula PVs are not supported", "error")]


async def test_updates_do_not_clobber_typing(open_widgets, make_widget):
    async with open_widgets(make_widget("textentry", pv_name="loc://a(1.0)")) as (app, pilot, pvs):
        entry = app.query_one(TextEntryWidget)
        entry.focus()
        await pilot.press("end", "9")
        pvs.get("loc://a").put(2.0)
        await pilot.pause()
        assert entry.value == "19"
        entry.blur()
        await pilot.pause()
        assert entry.value == "2"


async def test_click_to_focus_selects_everything(open_widgets, make_widget):
    async with open_widgets(make_widget("textentry", pv_name="loc://a(123)")) as (app, pilot, pvs):
        entry = app.query_one(TextEntryWidget)
        await pilot.click(entry, offset=(1, 0))
        assert (entry.selection.start, entry.selection.end) == (0, 3)
        await pilot.click(entry, offset=(1, 0))
        assert entry.selection.is_empty


async def test_typing_replaces_the_selected_value(open_widgets, make_widget):
    async with open_widgets(make_widget("textentry", pv_name="loc://a(123)")) as (app, pilot, pvs):
        entry = app.query_one(TextEntryWidget)
        await pilot.click(entry)
        await pilot.press("7", "enter")
        assert pvs.get("loc://a").state.value == 7


async def test_disabled(open_widgets, make_widget):
    async with open_widgets(make_widget("textentry", pv_name="loc://a", enabled="false")) as (app, pilot, pvs):
        assert app.query_one(TextEntryWidget).disabled


async def test_spinner_steps_within_limits(open_widgets, make_widget):
    widget = make_widget(
        "spinner", pv_name="loc://n<VLong>(9)", increment=1, minimum=0, maximum=10, limits_from_pv="false"
    )
    async with open_widgets(widget) as (app, pilot, pvs):
        app.query_one(SpinnerWidget).focus()
        await pilot.press("up", "up")
        assert pvs.get("loc://n").state.value == 10
        await pilot.press("down")
        assert pvs.get("loc://n").state.value == 9
