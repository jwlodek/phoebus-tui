import pytest

from phoebus_tui.app import Cell, DisplayTab


@pytest.fixture
def tab_labels():
    """Labels of each cell's tabs, cells ordered top-to-bottom then left-to-right."""

    def labels(app) -> list[list[str]]:
        cells = sorted(app.cells, key=lambda c: (c.region.y, c.region.x))
        return [[str(cell.tabbed.get_tab(tab).label) for tab in cell.display_tabs] for cell in cells]

    return labels


@pytest.fixture
def cell_at():
    """The cell furthest in a direction: 'left', 'right', 'top' or 'bottom'."""

    def find(app, side: str) -> Cell:
        key = {
            "left": lambda c: c.region.x,
            "right": lambda c: -c.region.x,
            "top": lambda c: c.region.y,
            "bottom": lambda c: -c.region.y,
        }[side]
        return min(app.cells, key=key)

    return find


@pytest.fixture
def tab_widget():
    """The tab-bar entry of a display tab, for right clicking."""

    def find(tab: DisplayTab):
        return tab.cell.tabbed.get_tab(tab)

    return find
