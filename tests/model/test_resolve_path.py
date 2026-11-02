from pathlib import Path

import pytest

from phoebus_tui.model import resolve_display_path


def test_relative_and_absolute(tmp_path):
    parent = tmp_path / "screens" / "main.bob"
    assert resolve_display_path("sub/other.bob", parent) == tmp_path / "screens" / "sub" / "other.bob"
    assert resolve_display_path(Path("/abs/x.bob"), parent) == Path("/abs/x.bob")


def test_opi_prefers_existing_bob(tmp_path):
    (tmp_path / "old.bob").write_text("")
    parent = tmp_path / "main.bob"
    assert resolve_display_path("old.opi", parent) == tmp_path / "old.bob"
    assert resolve_display_path("other.opi", parent) == tmp_path / "other.opi"


@pytest.mark.parametrize("file", [None, "", "."])
def test_empty(file, tmp_path):
    with pytest.raises(ValueError, match="No display file"):
        resolve_display_path(file, tmp_path / "main.bob")


def test_remote(tmp_path):
    with pytest.raises(ValueError, match="Remote displays"):
        resolve_display_path("https://host/x.bob", tmp_path / "main.bob")
