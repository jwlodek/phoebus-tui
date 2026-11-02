from phoebusgen.v4.properties.types import CommandAction, OpenDisplayAction, OpenWebpageAction, WritePvAction

from phoebus_tui.app import DisplayView


async def _run(app, action):
    node = app.current_tab.query_one(DisplayView).display_model.nodes()[0]
    await app.run_widget_action(action, node, app.current_tab)


async def test_write_pv(open_widgets, make_widget):
    async with open_widgets(make_widget("textupdate", pv_name="loc://a(0)")) as (app, pilot, pvs):
        await _run(app, WritePvAction(pv_name="loc://a", value="7"))
        assert pvs.get("loc://a").state.value == 7


async def test_write_pv_failure_is_reported(open_widgets, make_widget, notifications):
    async with open_widgets(make_widget("label")) as (app, pilot, pvs):
        messages = notifications(app)
        await _run(app, WritePvAction(pv_name="=x", value="7"))
        assert messages == [("=x: Formula PVs are not supported", "error")]


async def test_open_display_failure_is_reported(open_widgets, make_widget, notifications):
    async with open_widgets(make_widget("label")) as (app, pilot, pvs):
        messages = notifications(app)
        await _run(app, OpenDisplayAction(file="missing.bob"))
        assert len(messages) == 1 and "missing.bob" in messages[0][0]
        assert len(app.current_tab.history) == 1


async def test_open_display_inherits_widget_macros(open_widgets, make_widget, write_bob, make_display):
    write_bob(make_display(name="$(P)$(Q)"), "other.bob")
    async with open_widgets(make_widget("label"), macros={"P": "a"}) as (app, pilot, pvs):
        await _run(app, OpenDisplayAction(file="other.bob", macros={"Q": "b"}))
        assert app.title == "ab"


async def test_open_webpage(open_widgets, make_widget, monkeypatch):
    async with open_widgets(make_widget("label")) as (app, pilot, pvs):
        opened = []
        monkeypatch.setattr(app, "open_url", opened.append)
        await _run(app, OpenWebpageAction(url="https://example.com"))
        assert opened == ["https://example.com"]


async def test_unsupported_actions_warn(open_widgets, make_widget, notifications):
    async with open_widgets(make_widget("label")) as (app, pilot, pvs):
        messages = notifications(app)
        await _run(app, CommandAction(command="ls"))
        assert messages == [("CommandAction is not supported", "warning")]
