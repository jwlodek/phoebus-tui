from textual.color import Color
from textual.widgets import Static, TabbedContent, TabPane

from phoebus_tui.widgets import EmbeddedWidget, GroupWidget, LabelWidget, NavTabsWidget, TabsWidget


async def test_group_box(open_widgets, make_widget):
    group = make_widget("group", name="Settings", width=200, height=100, raw=make_widget("label", text="inside"))
    async with open_widgets(group) as (app, pilot, pvs):
        widget = app.query_one(GroupWidget)
        assert str(widget.border_title) == "Settings"
        assert widget.styles.border_top[0] == "round"
        assert widget.query_one(LabelWidget).parent is widget


async def test_group_styles(open_widgets, make_widget):
    groups = [make_widget("group", style=style, y=120 * style) for style in (1, 2, 3)]
    async with open_widgets(*groups) as (app, pilot, pvs):
        borders = [group.styles.border_top[0] for group in app.query(GroupWidget)]
        assert borders == ["heavy", "solid", ""]


async def test_embedded_display(open_widgets, make_widget, make_display, make_color, write_bob):
    write_bob(make_display(make_widget("label", text="$(DEV)"), raw=make_color("background_color", 5, 6, 7)), "inner.bob")
    embedded = make_widget("embedded", file="inner.bob", width=200, height=100, raw="<macros><DEV>m1</DEV></macros>")
    async with open_widgets(embedded) as (app, pilot, pvs):
        widget = app.query_one(EmbeddedWidget)
        assert widget.styles.background == Color(5, 6, 7)
        assert str(widget.query_one(LabelWidget).render()) == "m1"


async def test_embedded_display_errors_are_shown(open_widgets, make_widget):
    async with open_widgets(make_widget("embedded", file="missing.bob")) as (app, pilot, pvs):
        message = app.query_one(EmbeddedWidget).query_one(Static)
        assert "Cannot load missing.bob" in str(message.render())


async def test_transparent_bordered_embedded_display(open_widgets, make_widget, make_display, write_bob):
    write_bob(make_display(), "inner.bob")
    widget = make_widget("embedded", file="inner.bob", transparent="true", border_width=1)
    async with open_widgets(widget) as (app, pilot, pvs):
        embedded = app.query_one(EmbeddedWidget)
        assert embedded.styles.border_top[0] == "solid"
        assert embedded.styles.background.a == 0


async def test_tabs(open_widgets, make_widget):
    tabs = (
        "<tabs>"
        f"<tab><name>First</name><children>{make_widget('label', text='one')}</children></tab>"
        "<tab><name></name><children/></tab>"
        "</tabs>"
    )
    async with open_widgets(make_widget("tabs", width=300, height=200, raw=tabs)) as (app, pilot, pvs):
        inner = app.query_one(TabsWidget).query_one(TabbedContent)
        titles = [str(inner.get_tab(pane).label) for pane in inner.query(TabPane)]
        assert titles == ["First", "Tab 2"]
        assert str(inner.query_one(LabelWidget).render()) == "one"


async def test_navigation_tabs(open_widgets, make_widget, make_display, write_bob):
    write_bob(make_display(make_widget("label", text="$(N)")), "page.bob")
    tabs = (
        "<tabs>"
        "<tab><name>A</name><file>page.bob</file><macros><N>first</N></macros></tab>"
        "<tab><name>B</name><file>missing.bob</file></tab>"
        "</tabs>"
    )
    async with open_widgets(make_widget("navtabs", width=300, height=200, raw=tabs)) as (app, pilot, pvs):
        inner = app.query_one(NavTabsWidget).query_one(TabbedContent)
        first, second = inner.query(TabPane)
        assert str(first.query_one(LabelWidget).render()) == "first"
        assert "Cannot load missing.bob" in str(second.query_one(Static).render())
