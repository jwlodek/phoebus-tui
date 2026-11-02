import pytest
from phoebusgen.v4.properties.types import Color

from phoebus_tui.model import load_display


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_display(tmp_path / "nope.bob")


def test_not_a_display(write_bob):
    with pytest.raises(ValueError, match="not a Phoebus"):
        load_display(write_bob("<widget/>"))


def test_properties(write_bob, make_display, make_color):
    path = write_bob(make_display(name="$(P) Screen", width=500, height=250, raw=make_color("background_color", 1, 2, 3)))
    display = load_display(path, {"P": "XF"})
    assert display.name == display.title == "XF Screen"
    assert display.size == (500, 250)
    assert display.background == Color((1, 2, 3))
    assert display.path == path.resolve()


def test_title_falls_back_to_path(write_bob, make_display):
    display = load_display(write_bob(make_display(name=None)))
    assert display.name == ""
    assert display.title == str(display.path)
    assert display.macros["DNAME"] == "test"


def test_passed_macros_override_file_macros(write_bob, make_display, make_widget):
    raw = "<macros><P>file</P><Q>$(P)-q</Q></macros>"
    path = write_bob(make_display(make_widget("label", text="$(P) $(Q) $(DNAME)"), raw=raw))
    display = load_display(path, {"P": "cli"})
    assert display.nodes()[0].prop("text") == "cli cli-q Test"
