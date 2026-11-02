import logging

from textual.color import Color

from phoebus_tui.widgets import ActionButtonWidget, FrameEdge, LabelWidget


async def test_visibility_rule(open_widgets, make_widget, make_rule):
    widget = make_widget("label", text="Connected", raw=make_rule("visible", "!(pv0!=0)", "false", "loc://c(0)"))
    async with open_widgets(widget) as (app, pilot, pvs):
        label = app.query_one(LabelWidget)
        assert not label.display
        pvs.get("loc://c").put(1)
        await pilot.pause()
        assert label.display


async def test_rule_can_show_a_widget_hidden_in_the_file(open_widgets, make_widget, make_rule):
    rule = make_rule("visible", "pv0 == 1", "true", "loc://c(0)")
    async with open_widgets(make_widget("label", visible="false", raw=rule)) as (app, pilot, pvs):
        label = app.query_one(LabelWidget)
        assert not label.display
        pvs.get("loc://c").put(1)
        await pilot.pause()
        assert label.display


async def test_colour_rules_restore_the_original_colour(open_widgets, make_widget, make_rule, make_color):
    rule = make_rule("foreground_color", "pv0 == 1", '<color red="255" green="0" blue="0"/>', "loc://c(0)")
    widget = make_widget("label", raw=rule + make_color("foreground_color", 0, 0, 255))
    async with open_widgets(widget) as (app, pilot, pvs):
        label = app.query_one(LabelWidget)
        assert label.styles.color == Color(0, 0, 255)
        pvs.get("loc://c").put(1)
        await pilot.pause()
        assert label.styles.color == Color(255, 0, 0)
        pvs.get("loc://c").put(0)
        await pilot.pause()
        assert label.styles.color == Color(0, 0, 255)


async def test_background_rule_restores_the_original_background(open_widgets, make_widget, make_rule, make_color):
    rule = make_rule("background_color", "pv0 == 1", '<color red="0" green="255" blue="0"/>', "loc://c(1)")
    widget = make_widget("label", transparent="false", raw=rule + make_color("background_color", 1, 2, 3))
    async with open_widgets(widget) as (app, pilot, pvs):
        label = app.query_one(LabelWidget)
        assert label.styles.background == Color(0, 255, 0)
        pvs.get("loc://c").put(0)
        await pilot.pause()
        assert label.styles.background == Color(1, 2, 3)


async def test_background_rule_is_ignored_on_transparent_widgets(open_widgets, make_widget, make_rule):
    rule = make_rule("background_color", "pv0 == 1", '<color red="0" green="255" blue="0"/>', "loc://c(1)")
    async with open_widgets(make_widget("label", raw=rule)) as (app, pilot, pvs):
        assert app.query_one(LabelWidget).styles.background.a == 0


async def test_text_rules(open_widgets, make_widget, make_rule, text_of):
    label = make_widget("label", text="Idle", raw=make_rule("text", "pv0 == 1", "Busy", "loc://c(1)"))
    button = make_widget("action_button", text="Go", y=100, raw=make_rule("text", "pv0 == 1", "Stop", "loc://c(1)"))
    async with open_widgets(label, button) as (app, pilot, pvs):
        assert text_of(app.query_one(LabelWidget)) == "Busy"
        assert str(app.query_one(ActionButtonWidget).label) == "Stop"


async def test_output_expression(open_widgets, make_widget, make_rule, text_of):
    rule = make_rule("text", "true", "pvStr0", "loc://c(42)", out_exp=True)
    async with open_widgets(make_widget("label", raw=rule)) as (app, pilot, pvs):
        assert text_of(app.query_one(LabelWidget)) == "42"


async def test_disconnected_pvs_leave_the_widget_as_designed(open_widgets, make_widget, make_rule):
    widget = make_widget("label", raw=make_rule("visible", "true", "false", "=x"))
    async with open_widgets(widget) as (app, pilot, pvs):
        assert app.query_one(LabelWidget).display


async def test_rules_apply_to_all_frame_edges(open_widgets, make_widget, make_rule, make_color):
    raw = make_color("line_color", 0, 0, 0) + make_rule("visible", "pv0 == 0", "false", "loc://c(0)")
    frame = make_widget("rectangle", width=160, height=60, line_width=1, transparent="true", raw=raw)
    async with open_widgets(frame) as (app, pilot, pvs):
        assert not any(edge.display for edge in app.query(FrameEdge))
        pvs.get("loc://c").put(1)
        await pilot.pause()
        assert all(edge.display for edge in app.query(FrameEdge))


async def test_bad_expressions_are_logged_once(open_widgets, make_widget, make_rule, caplog):
    widget = make_widget("label", raw=make_rule("visible", "pv0 ===", "false", "loc://c(0)"))
    with caplog.at_level(logging.WARNING):
        async with open_widgets(widget) as (app, pilot, pvs):
            pvs.get("loc://c").put(1)
            await pilot.pause()
            assert app.query_one(LabelWidget).display
    assert caplog.text.count("Cannot parse rule expression") == 1


async def test_unsupported_properties_are_logged(open_widgets, make_widget, make_rule, caplog):
    widget = make_widget("label", raw=make_rule("tooltip", "true", "tip", "loc://c(0)"))
    with caplog.at_level(logging.WARNING):
        async with open_widgets(widget):
            pass
    assert "Rules for property 'tooltip' are not supported" in caplog.text


async def test_rules_stop_with_their_display(open_widgets, make_widget, make_rule):
    widget = make_widget("label", raw=make_rule("visible", "pv0 == 0", "false", "loc://c(0)"))
    async with open_widgets(widget) as (app, pilot, pvs):
        pv = pvs.get("loc://c")
        assert pv._subscribers
        await app.current_cell.display_tabs[0].show(*app.current_tab.current, remember=False)
        await pilot.pause()
        assert len(pv._subscribers) == 1
