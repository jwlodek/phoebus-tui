import pytest
from phoebusgen.v4.properties.types import (
    ExecuteAction,
    OpenDisplayAction,
    OpenWebpageAction,
    WritePvAction,
)

from phoebus_tui import widgets
from phoebus_tui.widgets import LabelWidget, PlaceholderWidget, describe


@pytest.mark.parametrize("wtype", ["mystery", "xyplot"])
async def test_unsupported_widgets_become_placeholders(wtype, open_widgets, make_widget, text_of):
    async with open_widgets(make_widget(wtype, width=160, height=80, pv_name="loc://a")) as (app, pilot, pvs):
        placeholder = app.query_one(PlaceholderWidget)
        assert text_of(placeholder) == f"[{wtype}]"
        assert placeholder.styles.border_top[0] == "dashed"


async def test_build_failures_become_placeholders(open_widgets, make_widget, monkeypatch, caplog):
    def broken(node, ctx):
        raise RuntimeError("boom")

    monkeypatch.setitem(widgets.FACTORIES, "label", broken)
    async with open_widgets(make_widget("label", name="Broken")) as (app, pilot, pvs):
        placeholder = app.query_one(PlaceholderWidget)
        assert placeholder.tooltip == "boom"
        assert "Failed to build label widget 'Broken'" in caplog.text


async def test_invisible_widgets_are_hidden(open_widgets, make_widget):
    async with open_widgets(make_widget("label", text="hidden", visible="false")) as (app, pilot, pvs):
        assert not app.query_one(LabelWidget).display


async def test_later_widgets_are_drawn_on_top(open_widgets, make_widget):
    first, second = make_widget("label", text="first"), make_widget("label", text="second")
    async with open_widgets(first, second) as (app, pilot, pvs):
        widget, _ = app.get_widget_at(0, app.query(LabelWidget).first().region.y)
        assert str(widget.render()) == "second"


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        (WritePvAction(pv_name="X", value="1"), "Write 1 to X"),
        (WritePvAction(pv_name="X", value="1", description="Custom"), "Custom"),
        (OpenDisplayAction(file="a.bob"), "Open a.bob"),
        (OpenWebpageAction(url="https://example.com"), "Open https://example.com"),
        (ExecuteAction(), "ExecuteAction"),
    ],
)
def test_describe(action, expected):
    assert describe(action) == expected
