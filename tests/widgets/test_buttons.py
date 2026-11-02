from phoebus_tui.widgets import ActionButtonWidget, ActionMenu, BoolButtonWidget, CheckBoxWidget


def write_action(pv, value, description=""):
    desc = f"<description>{description}</description>" if description else ""
    return f'<action type="write_pv"><pv_name>{pv}</pv_name><value>{value}</value>{desc}</action>'


async def test_action_button_runs_its_action(open_widgets, make_widget):
    actions = f"<actions>{write_action('loc://a', 5)}</actions>"
    async with open_widgets(make_widget("action_button", raw=actions)) as (app, pilot, pvs):
        pvs.get("loc://a(0)")
        button = app.query_one(ActionButtonWidget)
        assert str(button.label) == "Write 5 to loc://a"
        await pilot.click(button)
        await pilot.pause()
        assert pvs.get("loc://a").state.value == 5


async def test_action_button_with_several_actions_shows_a_menu(open_widgets, make_widget):
    actions = f"<actions>{write_action('loc://a', 1, 'First')}{write_action('loc://a', 2, 'Second')}</actions>"
    async with open_widgets(make_widget("action_button", text="Go", raw=actions)) as (app, pilot, pvs):
        pvs.get("loc://a(0)")
        button = app.query_one(ActionButtonWidget)
        assert str(button.label) == "Go"
        assert button.tooltip == "First\nSecond"
        await pilot.click(button)
        assert isinstance(app.screen, ActionMenu)
        app.screen.dismiss(1)
        await pilot.pause()
        assert pvs.get("loc://a").state.value == 2


async def test_cancelled_action_menu_does_nothing(open_widgets, make_widget):
    actions = f"<actions>{write_action('loc://a', 1)}{write_action('loc://a', 2)}</actions>"
    async with open_widgets(make_widget("action_button", raw=actions)) as (app, pilot, pvs):
        pvs.get("loc://a(0)")
        await pilot.click(app.query_one(ActionButtonWidget))
        await pilot.press("escape")
        assert pvs.get("loc://a").state.value == 0


async def test_action_button_without_actions(open_widgets, make_widget):
    async with open_widgets(make_widget("action_button", enabled="false")) as (app, pilot, pvs):
        button = app.query_one(ActionButtonWidget)
        assert str(button.label) == ""
        assert button.disabled


async def test_bool_button_toggles(open_widgets, make_widget):
    widget = make_widget("bool_button", pv_name="loc://a(0)", on_label="Running", off_label="Stopped")
    async with open_widgets(widget) as (app, pilot, pvs):
        button = app.query_one(BoolButtonWidget)
        assert str(button.label) == "● Stopped"
        await pilot.click(button)
        assert pvs.get("loc://a").state.value == 1
        assert str(button.label) == "● Running"
        # Buttons ignore presses during their 0.2s press animation
        await pilot.pause(0.3)
        await pilot.click(button)
        assert pvs.get("loc://a").state.value == 0


async def test_bool_button_bit(open_widgets, make_widget):
    async with open_widgets(make_widget("bool_button", pv_name="loc://a(1)", bit=2, show_led="false")) as (app, pilot, pvs):
        button = app.query_one(BoolButtonWidget)
        assert str(button.label) == "Off"
        await pilot.click(button)
        assert pvs.get("loc://a").state.value == 5


async def test_push_button_releases(open_widgets, make_widget):
    async with open_widgets(make_widget("bool_button", pv_name="loc://a(0)", mode=1)) as (app, pilot, pvs):
        seen = []
        pvs.get("loc://a").subscribe(lambda state: seen.append(state.value))
        await pilot.click(app.query_one(BoolButtonWidget))
        await pilot.pause(0.4)
        assert seen == [1, 0]


async def test_inverted_push_button(open_widgets, make_widget):
    async with open_widgets(make_widget("bool_button", pv_name="loc://a(1)", mode=2)) as (app, pilot, pvs):
        seen = []
        pvs.get("loc://a").subscribe(lambda state: seen.append(state.value))
        await pilot.click(app.query_one(BoolButtonWidget))
        await pilot.pause(0.4)
        assert seen == [0, 1]


async def test_slide_button(open_widgets, make_widget):
    async with open_widgets(make_widget("slide_button", pv_name="loc://a(0)", label="Busy")) as (app, pilot, pvs):
        button = app.query_one(BoolButtonWidget)
        assert str(button.label) == "● Busy"
        await pilot.click(button)
        assert pvs.get("loc://a").state.value == 1


async def test_checkbox(open_widgets, make_widget):
    async with open_widgets(make_widget("checkbox", pv_name="loc://a(0)", label="Enable")) as (app, pilot, pvs):
        checkbox = app.query_one(CheckBoxWidget)
        assert not checkbox.value
        await pilot.click(checkbox)
        assert pvs.get("loc://a").state.value == 1
        pvs.get("loc://a").put(0)
        await pilot.pause()
        assert not checkbox.value
        assert pvs.get("loc://a").state.value == 0
