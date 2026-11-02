import pytest
from phoebusgen.v4.properties.types import Color

from phoebus_tui.model import color_hex, contrast, font_style, format_ordinal, get, is_transparent, to_color


class _Broken:
    @property
    def value(self):
        raise ValueError("bad xml")


def test_get_falls_back_to_default():
    assert get(None, "x", 1) == 1
    assert get(object(), "missing", 2) == 2
    assert get(_Broken(), "value", 3) == 3


def test_to_color():
    assert to_color([1, 2, 3]) == Color((1, 2, 3))
    assert to_color("#0a0b0c") == Color((10, 11, 12))
    assert to_color(None, Color((1, 1, 1))) == Color((1, 1, 1))
    assert to_color("not a color") is None


def test_color_helpers():
    assert color_hex(Color((255, 0, 16))) == "#ff0010"
    assert is_transparent(Color((1, 2, 3, 0)))
    assert not is_transparent(Color((1, 2, 3)))
    assert contrast(Color((255, 255, 255))) == "#000000"
    assert contrast(Color((0, 0, 80))) == "#ffffff"


def test_format_ordinal(load_nodes, make_widget):
    nodes = load_nodes(
        make_widget("textupdate", format=6),
        make_widget("textupdate"),
        make_widget("textupdate", format="bad"),
    )
    # Phoebus STRING is ordinal 6; phoebusgen's own Format enum would misread it
    assert [format_ordinal(n.widget) for n in nodes] == [6, 0, 0]
    assert format_ordinal(None) == 0


@pytest.mark.parametrize(
    ("style", "expected"), [("BOLD", "bold"), ("ITALIC", "italic"), ("BOLD_ITALIC", "bold italic"), ("REGULAR", "")]
)
def test_font_style(style, expected, load_nodes, make_widget):
    font = f'<font><font family="Liberation Sans" style="{style}" size="14.0"/></font>'
    (node,) = load_nodes(make_widget("label", raw=font))
    assert font_style(node.widget) == expected
