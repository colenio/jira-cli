"""Shared theme-color properties for rendered resource items."""

from __future__ import annotations

import hashlib
import re
from typing import Any

_THEME_COLORS = (
    "bright_cyan",
    "bright_magenta",
    "bright_green",
    "bright_blue",
    "bright_red",
    "bright_yellow",
)
_ALLOWED_COLORS = frozenset(_THEME_COLORS) | {"cyan", "magenta", "green", "blue", "red", "yellow", "dim"}
_HEX_COLOR = re.compile(r"^#?[0-9a-fA-F]{6}$")


def normalize_theme_color(value: Any) -> str | None:
    """Return a safe Rich color/style value supplied by a provider."""
    if not isinstance(value, str):
        return None
    color = value.strip()
    if color.casefold() in _ALLOWED_COLORS:
        return color
    if _HEX_COLOR.fullmatch(color):
        return color if color.startswith("#") else f"#{color}"
    return None


def label_theme_color(label: dict[str, Any]) -> str:
    """Choose a provider color or a stable palette color for a label."""
    supplied = normalize_theme_color(label.get("themeColor"))
    if supplied:
        return supplied

    native = normalize_theme_color(label.get("color"))
    if native:
        return native

    name = str(label.get("name", ""))
    digest = hashlib.sha256(name.casefold().encode("utf-8")).digest()
    return _THEME_COLORS[int.from_bytes(digest[:4], "big") % len(_THEME_COLORS)]
