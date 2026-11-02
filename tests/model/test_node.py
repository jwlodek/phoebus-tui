from phoebusgen.v4.properties.types import Color, WritePvAction


def test_typed_and_raw_properties(load_nodes, make_widget, make_color):
    (node,) = load_nodes(make_widget(
        "led", pv_name="loc://a", x=10, y=20, width=30, height=40, visible="false",
        raw=make_color("on_color", 1, 2, 3) + "<custom>raw</custom><custom_flag>true</custom_flag>",
    ))
    assert node.type == "led"
    assert node.prop("pv_name") == "loc://a"
    assert node.geometry() == (10, 20, 30, 40)
    assert node.flag("visible", True) is False
    assert node.color("on_color") == Color((1, 2, 3))
    assert node.prop("custom") == "raw"
    assert node.flag("custom_flag", False) is True
    assert node.prop("absent", "dflt") == "dflt"
    assert node.color("absent_color", Color((9, 9, 9))) == Color((9, 9, 9))


def test_raw_color_on_unknown_widget(load_nodes, make_widget, make_color):
    raw = make_color("line_color", 4, 5, 6) + "<bad_color><color red='x'/></bad_color>"
    (node,) = load_nodes(make_widget("mystery", raw=raw))
    assert node.color("line_color") == Color((4, 5, 6))
    assert node.color("bad_color", Color((0, 0, 1))) == Color((0, 0, 1))


def test_unknown_widget_type(load_nodes, make_widget):
    (node,) = load_nodes(make_widget("mystery", x=5, width="bad"))
    assert node.widget is None
    assert node.geometry() == (5, 0, 100, 20)


def test_malformed_typed_property_uses_default(load_nodes, make_widget):
    (node,) = load_nodes(make_widget("label", x="$(UNDEFINED)"))
    assert node.geometry()[0] == 0


def test_group_children_are_cached_and_tolerate_unknown_types(load_nodes, make_widget):
    (group,) = load_nodes(make_widget("group", raw=make_widget("label") + make_widget("mystery")))
    children = group.children()
    assert children is group.children()
    assert children[1].widget is None
    assert group.contents() == children


def test_tabs(load_nodes, make_widget):
    tabs = (
        "<tabs><tab><name>One</name><children>" + make_widget("label", text="a") + "</children></tab>"
        "<tab><name>Two</name><children/></tab></tabs>"
    )
    (node,) = load_nodes(make_widget("tabs", raw=tabs))
    assert [(name, [c.prop("text") for c in children]) for name, children in node.tabs()] == [("One", ["a"]), ("Two", [])]


def test_actions(load_nodes, make_widget):
    actions = '<actions><action type="write_pv"><pv_name>$(P)X</pv_name><value>1</value></action></actions>'
    (node,) = load_nodes(make_widget("action_button", raw=actions), macros={"P": "A:"})
    (action,) = node.prop("actions")
    assert isinstance(action, WritePvAction)
    assert (action.pv_name, action.value) == ("A:X", "1")


def test_leaf_contents_are_empty(load_nodes, make_widget):
    (node,) = load_nodes(make_widget("label"))
    assert node.contents() == []
