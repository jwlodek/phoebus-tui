from phoebus_tui.model import MAX_EMBED_DEPTH, load_display


def test_content_with_macros(load_nodes, write_bob, make_display, make_widget):
    write_bob(make_display(make_widget("label", text="$(DEV)")), "inner.bob")
    (node,) = load_nodes(make_widget("embedded", file="inner.bob", raw="<macros><DEV>m1</DEV></macros>"))
    content = node.embedded()
    assert content is node.embedded()
    assert not content.error
    assert content.nodes[0].prop("text") == "m1"
    assert node.contents() == content.nodes


def test_group_name(load_nodes, write_bob, make_display, make_widget):
    wanted = make_widget("group", name="Wanted", raw=make_widget("label", text="in group"))
    outer = make_widget("group", name="Outer", raw=wanted)
    write_bob(make_display(make_widget("label", text="outside"), outer), "inner.bob")
    (node,) = load_nodes(make_widget("embedded", file="inner.bob", group_name="Wanted"))
    assert [n.prop("text") for n in node.embedded().nodes] == ["in group"]


def test_missing_group(load_nodes, write_bob, make_display, make_widget):
    write_bob(make_display(), "inner.bob")
    (node,) = load_nodes(make_widget("embedded", file="inner.bob", group_name="Nope"))
    assert "No group 'Nope'" in node.embedded().error


def test_missing_file(load_nodes, make_widget):
    (node,) = load_nodes(make_widget("embedded", file="missing.bob"))
    assert "Cannot load missing.bob" in node.embedded().error


def test_recursion_is_limited(write_bob, make_display, make_widget):
    node = load_display(write_bob(make_display(make_widget("embedded", file="test.bob")))).nodes()[0]
    depth = 0
    while not node.embedded().error:
        node = node.embedded().nodes[0]
        depth += 1
    assert depth == MAX_EMBED_DEPTH
    assert "nested too deeply" in node.embedded().error
