"""Parity test: ensure GameForgeEventNames.h matches design.events_catalog.all_events()."""

import re
from pathlib import Path

from src.gameforge_ide.design.events_catalog import all_events

HEADER_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "gameforge_ide"
    / "unreal"
    / "GameForge"
    / "Source"
    / "GameForgeRuntime"
    / "Public"
    / "GameForgeEventNames.h"
)


def test_event_names_parity():
    assert HEADER_PATH.is_file(), f"Header not found: {HEADER_PATH}"
    content = HEADER_PATH.read_text(encoding="utf-8")
    matches = re.findall(r'X\((\w+),\s*"([a-z0-9_.]+)"\)', content)
    assert len(matches) > 0, "No event declarations found in GameForgeEventNames.h"

    header_event_strings = {str_val for _, str_val in matches}
    catalog_event_strings = set(all_events())

    assert (
        header_event_strings == catalog_event_strings
    ), f"Mismatch between C++ header and events catalog!\nMissing in C++: {catalog_event_strings - header_event_strings}\nExtra in C++: {header_event_strings - catalog_event_strings}"
