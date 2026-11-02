from phoebusgen.v4.properties.types import OpenDisplayAction, OpenDisplayTarget

from phoebus_tui.app import DisplayView


def _first_node(app):
    return app.current_tab.query_one(DisplayView).display_model.nodes()[0]


async def test_title_and_tab_label(open_widgets, make_widget, tab_labels):
    async with open_widgets(make_widget("label"), name="Main $(P)", macros={"P": "XF"}) as (app, pilot, pvs):
        assert app.title == "Main XF"
        assert app.sub_title.endswith("test.bob")
        assert tab_labels(app) == [["Main XF"]]


async def test_unnamed_display_uses_its_path(open_widgets, make_widget, tab_labels):
    async with open_widgets(make_widget("label"), name=None) as (app, pilot, pvs):
        assert tab_labels(app) == [[app.sub_title]]
        assert app.title == app.sub_title


async def test_open_in_new_tab_switches_to_it(run_app, write_bob, make_display, make_widget, tab_labels):
    write_bob(make_display(make_widget("label"), name="Detail"), "detail.bob")
    action = '<actions><action type="open_display"><file>detail.bob</file><target>tab</target></action></actions>'
    path = write_bob(make_display(make_widget("action_button", text="Open", raw=action), name="Main"))
    async with run_app(path) as (app, pilot, pvs):
        await pilot.click("ActionButtonWidget")
        await pilot.pause(0.3)
        assert tab_labels(app) == [["Main", "Detail"]]
        assert app.title == "Detail"
        assert app.current_tab is app.current_cell.display_tabs[1]


async def test_window_target_also_opens_a_tab(open_widgets, make_widget, write_bob, make_display, tab_labels):
    write_bob(make_display(name="Other"), "other.bob")
    async with open_widgets(make_widget("label"), name="Main") as (app, pilot, pvs):
        action = OpenDisplayAction(file="other.bob", target=OpenDisplayTarget.NEW_WINDOW)
        await app.run_widget_action(action, _first_node(app), app.current_tab)
        assert tab_labels(app) == [["Main", "Other"]]


async def test_replace_then_back(open_widgets, make_widget, write_bob, make_display, tab_labels):
    write_bob(make_display(name="Other $(X)"), "other.bob")
    async with open_widgets(make_widget("label"), name="Main") as (app, pilot, pvs):
        action = OpenDisplayAction(file="other.bob", macros={"X": "1"})
        await app.run_widget_action(action, _first_node(app), app.current_tab)
        assert tab_labels(app) == [["Other 1"]]
        assert app.title == "Other 1"
        await pilot.press("escape")
        await pilot.pause()
        assert tab_labels(app) == [["Main"]]
        assert len(app.current_tab.history) == 1


async def test_back_is_disabled_without_history(open_widgets, make_widget):
    async with open_widgets(make_widget("label")) as (app, pilot, pvs):
        assert app.check_action("back", ()) is None
        await pilot.press("escape")
        assert len(app.current_tab.history) == 1


async def test_reload_picks_up_file_changes(run_app, write_bob, make_display, make_widget, tab_labels):
    path = write_bob(make_display(make_widget("label"), name="Before"))
    async with run_app(path) as (app, pilot, pvs):
        write_bob(make_display(make_widget("label"), name="After"))
        await pilot.press("f5")
        await pilot.pause()
        assert tab_labels(app) == [["After"]]
        assert len(app.current_tab.history) == 1


async def test_reload_failure_is_reported(run_app, write_bob, make_display, notifications, tab_labels):
    path = write_bob(make_display(name="Before"))
    async with run_app(path) as (app, pilot, pvs):
        messages = notifications(app)
        path.write_text("<not xml")
        await pilot.press("f5")
        assert messages and messages[0][1] == "error"
        assert tab_labels(app) == [["Before"]]


async def test_last_display_cannot_be_closed(open_widgets, make_widget, tab_labels):
    async with open_widgets(make_widget("label"), name="Only") as (app, pilot, pvs):
        assert app.check_action("close_tab", ()) is None
        await pilot.press("ctrl+x")
        assert tab_labels(app) == [["Only"]]


async def test_ctrl_x_closes_the_current_tab(open_widgets, make_widget, tab_labels):
    async with open_widgets(make_widget("label"), name="Main") as (app, pilot, pvs):
        await app.current_cell.add_tab([app.current_tab.current])
        await pilot.press("ctrl+x")
        await pilot.pause()
        assert tab_labels(app) == [["Main"]]


async def test_footer_bindings(open_widgets, make_widget):
    async with open_widgets(make_widget("label")) as (app, pilot, pvs):
        shown = {key: active.binding.description for key, active in app.active_bindings.items() if active.binding.show}
        assert shown["ctrl+q"] == "Quit"
        assert shown["ctrl+x"] == "Close tab"
        assert shown["f5"] == "Reload"


async def test_ctrl_q_quits(open_widgets, make_widget):
    async with open_widgets(make_widget("label")) as (app, pilot, pvs):
        await pilot.press("ctrl+q")
        await pilot.pause()
        assert not app.is_running


async def test_pvs_are_closed_on_exit(open_widgets, make_widget):
    async with open_widgets(make_widget("textupdate", pv_name="loc://a")) as (app, pilot, pvs):
        assert pvs._pvs
    assert not pvs._pvs
