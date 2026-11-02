from phoebus_tui.model import clean_macros, expand_macros


def test_both_syntaxes_and_unknown_left_alone():
    macros = {"P": "XF:", "R": "cam1:"}
    assert expand_macros("$(P)${R}$(Q)", macros.get) == "XF:cam1:$(Q)"


def test_nested_macros():
    macros = {"A": "$(B)", "B": "done"}
    assert expand_macros("$(A)", macros.get) == "done"


def test_recursive_definitions_terminate():
    macros = {"A": "x$(A)"}
    assert expand_macros("$(A)", macros.get).startswith("xxxx")


def test_clean_macros():
    assert clean_macros({"A": None, 1: 2}) == {"A": "", "1": "2"}
    assert clean_macros(None) == {}


def test_widget_property_macros(load_nodes, make_widget):
    (node,) = load_nodes(make_widget("textupdate", pv_name="$(P)X", tooltip="$(pv_name)"), macros={"P": "A:"})
    assert node.prop("tooltip") == "A:X"


def test_group_macros_apply_only_inside_the_group(load_nodes, make_widget):
    group = make_widget("group", raw="<macros><M>inner</M></macros>" + make_widget("label", text="$(M)"))
    group_node, sibling = load_nodes(group, make_widget("label", text="$(M)"))
    assert group_node.children()[0].prop("text") == "inner"
    assert sibling.prop("text") == "$(M)"
