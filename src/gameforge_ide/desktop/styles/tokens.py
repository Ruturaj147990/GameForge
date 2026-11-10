"""GameForge IDE — Design Tokens.

Single canonical source of truth for:
- Spacing scale: (4, 8, 12, 16)
- Standard corner radius: 6px
- Typography scale: two sizes per level:
    Body: 11px (small/metadata), 13px (regular body)
    Heading: 14px (card/section), 18px (panel/hero)
- Color tokens: Midnight Purple Dark palette and semantic roles
"""

from __future__ import annotations

# Spacing scale (pixels)
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16

# Corner radius (pixels)
RADIUS_SM = 4
RADIUS = 6
RADIUS_MD = 6
RADIUS_LG = 8
RADIUS_XL = 12

# Typography scale (pixels, two per level)
FONT_BODY_SM = 11      # Captions, badges, timestamps, secondary labels
FONT_BODY = 13         # Standard body, text inputs, lists, table items
FONT_HEADING_SM = 14   # Section headers, card titles, subheadings
FONT_HEADING = 18      # Main window titles, panel headers, hero titles

# Dark Palette Colors
BG_ROOT = "#08070d"        # Deep black application background
BG_PANEL = "#0d0b14"       # Dock panels and sidebar containers
BG_SURFACE = "#120f1d"     # Cards, list items, text fields, headers
BG_HOVER = "#1a1528"       # Hover states
BG_ACTIVE = "#251d38"      # Active/pressed states

BORDER = "#231c34"         # Subtle purple-tinted borders
BORDER_FOCUS = "#8b5cf6"   # Focus outlines

TEXT_PRIMARY = "#f5f3ff"   # High-contrast primary text (contrast > 14:1)
TEXT_SECONDARY = "#9d95b0" # Readable secondary labels (contrast > 6.5:1)
TEXT_MUTED = "#9d95b0"     # High-contrast secondary/muted (contrast > 6.6:1)

# Accent Colors (from styles/ only)
ACCENT_PRIMARY = "#7c3aed" # Refined purple
ACCENT_HOVER = "#8b5cf6"   # Vibrant purple hover
ACCENT_ACTIVE = "#6d28d9"  # Pressed purple
ACCENT_SUCCESS = "#00d9a3" # Emerald teal (assistant, verified, connected)
ACCENT_WARNING = "#f59e0b" # Amber (busy, tool invocation)
ACCENT_ERROR = "#ef4444"   # Coral red (failure, error)

__all__ = [
    "SPACE_XS",
    "SPACE_SM",
    "SPACE_MD",
    "SPACE_LG",
    "RADIUS_SM",
    "RADIUS",
    "RADIUS_MD",
    "RADIUS_LG",
    "RADIUS_XL",
    "FONT_BODY_SM",
    "FONT_BODY",
    "FONT_HEADING_SM",
    "FONT_HEADING",
    "BG_ROOT",
    "BG_PANEL",
    "BG_SURFACE",
    "BG_HOVER",
    "BG_ACTIVE",
    "BORDER",
    "BORDER_FOCUS",
    "TEXT_PRIMARY",
    "TEXT_SECONDARY",
    "TEXT_MUTED",
    "ACCENT_PRIMARY",
    "ACCENT_HOVER",
    "ACCENT_ACTIVE",
    "ACCENT_SUCCESS",
    "ACCENT_WARNING",
    "ACCENT_ERROR",
]
