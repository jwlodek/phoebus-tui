"""Display Phoebus .bob screens as a terminal UI."""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path


def parse_macros(specs: list[str]) -> dict[str, str]:
    """Parse ["P=XF:10ID,R=cam1:", ...] into a macro dict."""
    macros: dict[str, str] = {}
    for spec in specs:
        for item in filter(None, (part.strip() for part in spec.split(","))):
            name, sep, value = item.partition("=")
            if not sep or not name.strip():
                raise ValueError(f"Invalid macro {item!r}, expected NAME=VALUE")
            macros[name.strip()] = value.strip().strip("\"'")
    return macros


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="phoebus-tui", description="Display a Phoebus .bob screen in the terminal.")
    parser.add_argument("display", type=Path, help="Path to the .bob display file")
    parser.add_argument(
        "-m", "--macros", action="append", default=[], metavar="NAME=VALUE[,...]",
        help="Macros for the display, may be given multiple times",
    )
    parser.add_argument("--default-protocol", choices=("ca", "pva"), default="ca",
                        help="Protocol for PV names without a prefix (default: ca)")
    parser.add_argument("--cell-width", type=float, default=8.0, help="Display pixels per terminal column (default: 8)")
    parser.add_argument("--cell-height", type=float, default=20.0, help="Display pixels per terminal row (default: 20)")
    args = parser.parse_args(argv)

    try:
        macros = parse_macros(args.macros)
    except ValueError as e:
        parser.error(str(e))

    from .app import PhoebusTuiApp
    from .layout import Scale
    from .model import load_display
    from .pv import PVManager

    try:
        display = load_display(args.display, macros)
    except (OSError, ValueError, ET.ParseError) as e:
        parser.exit(1, f"phoebus-tui: {e}\n")

    PhoebusTuiApp(display, macros, PVManager(args.default_protocol), Scale(args.cell_width, args.cell_height)).run()
