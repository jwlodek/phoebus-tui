import pytest

from phoebus_tui.app import DisplayView, Split

SIZE = (160, 50)


async def test_split_adds_an_empty_cell(open_widgets, make_widget, tab_labels):
    async with open_widgets(make_widget("label"), name="Main", size=SIZE) as (app, pilot, pvs):
        await app.split(app.cells[0], horizontal=True)
        await pilot.pause()
        assert tab_labels(app) == [["Main", *[]], []]
        assert app.workspace.has_class("-split")
        assert app.query_one(Split).has_class("-horizontal")
        assert app.current_cell is app.cells[1]
        assert app.title == "phoebus-tui"


async def test_vertical_split(open_widgets, make_widget, cell_at):
    async with open_widgets(make_widget("label"), size=SIZE) as (app, pilot, pvs):
        await app.split(app.cells[0], horizontal=False)
        await pilot.pause()
        top, bottom = cell_at(app, "top"), cell_at(app, "bottom")
        assert top.display_tabs and not bottom.display_tabs
        assert top.region.x == bottom.region.x


async def test_split_keeps_tabs_and_their_history(open_widgets, make_widget, write_bob, make_display):
    write_bob(make_display(name="Other"), "other.bob")
    async with open_widgets(make_widget("label"), name="Main", size=SIZE) as (app, pilot, pvs):
        from phoebusgen.v4.properties.types import OpenDisplayAction

        node = app.current_tab.query_one(DisplayView).display_model.nodes()[0]
        await app.run_widget_action(OpenDisplayAction(file="other.bob"), node, app.current_tab)
        await app.split(app.cells[0], horizontal=True)
        await pilot.pause()
        (tab,) = app.cells[0].display_tabs
        assert [display.title for display, _ in tab.history] == ["Main", "Other"]


async def test_remove_cell(open_widgets, make_widget, tab_labels):
    async with open_widgets(make_widget("label"), name="Main", size=SIZE) as (app, pilot, pvs):
        await app.split(app.cells[0], horizontal=True)
        await app.split(app.cells[1], horizontal=False)
        await pilot.pause()
        # Removing a cell rebuilds its sibling, so re-query each time
        for _ in range(2):
            await app.remove_cell(next(c for c in app.cells if not c.display_tabs))
            await pilot.pause()
        assert tab_labels(app) == [["Main"]]
        assert not app.query(Split)
        assert not app.workspace.has_class("-split")
        assert app.current_cell is app.cells[0]


async def test_last_cell_cannot_be_removed(open_widgets, make_widget):
    async with open_widgets(make_widget("label"), size=SIZE) as (app, pilot, pvs):
        await app.remove_cell(app.cells[0])
        assert len(app.cells) == 1


async def test_neighbours(open_widgets, make_widget, cell_at):
    async with open_widgets(make_widget("label"), size=SIZE) as (app, pilot, pvs):
        await app.split(app.cells[0], horizontal=True)
        await pilot.pause()
        left, right = cell_at(app, "left"), cell_at(app, "right")
        assert app.neighbour(left, "right") is right
        assert app.neighbour(right, "left") is left
        assert app.neighbour(left, "up") is None
        assert app.neighbour(left, "down") is None
        assert app.neighbour(left, "left") is None


async def test_move_tab(open_widgets, make_widget, tab_labels, cell_at):
    async with open_widgets(make_widget("label"), name="Main", size=SIZE) as (app, pilot, pvs):
        await app.split(app.cells[0], horizontal=True)
        await pilot.pause()
        left, right = cell_at(app, "left"), cell_at(app, "right")
        await app.move_tab(left.display_tabs[0], right)
        assert tab_labels(app) == [[], ["Main"]]
        assert app.current_cell is right
        assert app.title == "Main"


async def test_closing_the_last_tab_of_a_cell_leaves_it_empty(open_widgets, make_widget, cell_at):
    async with open_widgets(make_widget("label"), size=SIZE) as (app, pilot, pvs):
        await app.current_cell.add_tab([app.current_tab.current])
        await app.split(app.cells[0], horizontal=True)
        await pilot.pause()
        left, right = cell_at(app, "left"), cell_at(app, "right")
        await app.move_tab(left.display_tabs[0], right)
        await app.close_tab(left.display_tabs[0])
        await pilot.pause()
        assert not left.display_tabs
        assert left.query_one(".empty").display
        assert not left.tabbed.display


@pytest.mark.parametrize(
    ("direction", "new_side", "old_side"),
    [("left", "left", "right"), ("right", "right", "left"), ("up", "top", "bottom"), ("down", "bottom", "top")],
)
async def test_split_tab_into_a_new_cell(direction, new_side, old_side, open_widgets, make_widget, cell_at):
    async with open_widgets(make_widget("label"), name="Main", size=SIZE) as (app, pilot, pvs):
        await app.current_cell.add_tab([app.current_tab.current])
        moving = app.current_cell.display_tabs[0]
        await app.split_tab(moving, direction)
        await pilot.pause()
        assert len(app.cells) == 2
        assert len(cell_at(app, new_side).display_tabs) == 1
        assert len(cell_at(app, old_side).display_tabs) == 1
        assert app.current_cell is cell_at(app, new_side)


async def test_split_tab_reuses_an_empty_neighbour(open_widgets, make_widget, tab_labels):
    async with open_widgets(make_widget("label"), name="Main", size=SIZE) as (app, pilot, pvs):
        await app.current_cell.add_tab([app.current_tab.current])
        await app.split(app.cells[0], horizontal=True)
        await pilot.pause()
        await app.split_tab(app.cells[0].display_tabs[0], "right")
        await pilot.pause()
        assert len(app.cells) == 2
        assert tab_labels(app) == [["Main"], ["Main"]]
