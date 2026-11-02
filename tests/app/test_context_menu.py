from phoebus_tui.app import ContextMenu
from phoebus_tui.widgets import ActionButtonWidget

SIZE = (160, 50)


def menu_labels(app):
    return [label for _, label in app.screen.items] if isinstance(app.screen, ContextMenu) else None


async def test_background_menu(open_widgets, make_widget, right_click):
    async with open_widgets(make_widget("label"), size=SIZE) as (app, pilot, pvs):
        await right_click(app, pilot, app.cells[0], (20, 10))
        assert menu_labels(app) == ["Split left/right", "Split top/bottom"]


async def test_background_split_from_menu(open_widgets, make_widget, right_click):
    async with open_widgets(make_widget("label"), size=SIZE) as (app, pilot, pvs):
        await right_click(app, pilot, app.cells[0], (20, 10))
        app.screen.dismiss("split:vertical")
        await pilot.pause(0.3)
        assert len(app.cells) == 2
        assert app.cells[0].region.x == app.cells[1].region.x


async def test_empty_cell_menu_offers_removal(open_widgets, make_widget, right_click):
    async with open_widgets(make_widget("label"), size=SIZE) as (app, pilot, pvs):
        await app.split(app.cells[0], horizontal=True)
        await pilot.pause()
        empty = app.cells[1]
        await right_click(app, pilot, empty, (5, 5))
        assert menu_labels(app)[-1] == "Remove cell"
        app.screen.dismiss("remove")
        await pilot.pause()
        assert len(app.cells) == 1


async def test_tab_menu(open_widgets, make_widget, right_click, tab_widget):
    async with open_widgets(make_widget("label"), size=SIZE) as (app, pilot, pvs):
        await app.current_cell.add_tab([app.current_tab.current])
        await right_click(app, pilot, tab_widget(app.current_cell.display_tabs[0]))
        assert menu_labels(app) == ["Split left", "Split right", "Split top", "Split bottom", "Close tab"]


async def test_tab_menu_offers_moves_to_occupied_neighbours(open_widgets, make_widget, right_click, tab_widget, cell_at):
    async with open_widgets(make_widget("label"), size=SIZE) as (app, pilot, pvs):
        await app.current_cell.add_tab([app.current_tab.current])
        await app.split_tab(app.current_cell.display_tabs[0], "right")
        await pilot.pause()
        left = cell_at(app, "left")
        await right_click(app, pilot, tab_widget(left.display_tabs[0]))
        assert "Move right" in menu_labels(app)
        assert "Move left" not in menu_labels(app)
        app.screen.dismiss("move:right")
        await pilot.pause()
        assert len(cell_at(app, "right").display_tabs) == 2


async def test_tab_menu_actions(open_widgets, make_widget, right_click, tab_widget, cell_at):
    async with open_widgets(make_widget("label"), size=SIZE) as (app, pilot, pvs):
        await app.current_cell.add_tab([app.current_tab.current])
        await right_click(app, pilot, tab_widget(app.current_cell.display_tabs[0]))
        app.screen.dismiss("split-tab:down")
        await pilot.pause(0.3)
        assert len(cell_at(app, "bottom").display_tabs) == 1
        await right_click(app, pilot, tab_widget(cell_at(app, "bottom").display_tabs[0]))
        app.screen.dismiss("close")
        await pilot.pause()
        assert not cell_at(app, "bottom").display_tabs


async def test_only_tab_of_only_cell_cannot_be_closed_from_the_menu(open_widgets, make_widget, right_click, tab_widget):
    async with open_widgets(make_widget("label"), size=SIZE) as (app, pilot, pvs):
        await right_click(app, pilot, tab_widget(app.current_tab))
        assert "Close tab" not in menu_labels(app)


async def test_escape_and_outside_clicks_dismiss(open_widgets, make_widget, right_click):
    async with open_widgets(make_widget("label"), size=SIZE) as (app, pilot, pvs):
        await right_click(app, pilot, app.cells[0], (40, 20))
        await pilot.press("escape")
        assert menu_labels(app) is None
        await right_click(app, pilot, app.cells[0], (40, 20))
        await pilot.click(offset=(0, 0))
        await pilot.pause()
        assert menu_labels(app) is None


async def test_menu_is_kept_on_screen(open_widgets, make_widget, right_click):
    async with open_widgets(make_widget("label"), size=SIZE) as (app, pilot, pvs):
        cell = app.cells[0]
        await right_click(app, pilot, cell, (cell.size.width - 1, cell.size.height - 1))
        menu = app.screen.query_one("OptionList")
        assert menu.region.right <= SIZE[0]
        assert menu.region.bottom <= SIZE[1]


async def test_right_click_does_not_press_widgets(open_widgets, make_widget, right_click):
    action = '<actions><action type="write_pv"><pv_name>loc://a</pv_name><value>1</value></action></actions>'
    async with open_widgets(make_widget("action_button", raw=action), size=SIZE) as (app, pilot, pvs):
        pvs.get("loc://a(0)")
        await right_click(app, pilot, app.query_one(ActionButtonWidget))
        assert menu_labels(app) == ["Split left/right", "Split top/bottom"]
        assert pvs.get("loc://a").state.value == 0


async def test_right_click_is_ignored_while_a_menu_is_open(open_widgets, make_widget, right_click):
    async with open_widgets(make_widget("label"), size=SIZE) as (app, pilot, pvs):
        await right_click(app, pilot, app.cells[0], (20, 10))
        menu = app.screen
        await right_click(app, pilot, app.cells[0], (30, 10))
        assert app.screen is menu


async def test_tabs_inside_a_display_get_the_background_menu(open_widgets, make_widget, right_click):
    tabs = f"<tabs><tab><name>Inner</name><children>{make_widget('label')}</children></tab></tabs>"
    async with open_widgets(make_widget("tabs", width=300, height=200, raw=tabs), size=SIZE) as (app, pilot, pvs):
        inner_tab = app.current_tab.query_one("TabsWidget").query_one("Tab")
        await right_click(app, pilot, inner_tab)
        assert menu_labels(app) == ["Split left/right", "Split top/bottom"]
