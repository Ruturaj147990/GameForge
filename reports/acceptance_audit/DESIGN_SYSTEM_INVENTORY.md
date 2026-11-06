# GameForge Desktop Frontend — Design System & Token Inventory

**Document ID:** `GF-DESIGN-TOKENS-2026-11`  
**Lead Coordinator:** Primary Antigravity Agent  
**Last Updated:** 2026-11-05T13:34:00Z  

---

## 1. Design Token Specifications

All visual styles in GameForge IDE are derived from the single canonical token definitions in [`src/gameforge_ide/desktop/styles/tokens.py`](file:///E:/gameforge_step1/src/gameforge_ide/desktop/styles/tokens.py).

### A. Spacing Scale
The spacing system enforces a 4-step structural rhythm across all views, dialogs, cards, and toolbars:

| Token | Value | Semantic Purpose |
|---|---|---|
| `SPACE_XS` | `4px` | Compact gaps between icon and text, badge internal padding, table cell margins |
| `SPACE_SM` | `8px` | Standard button internal padding, form field gaps, chip spacing |
| `SPACE_MD` | `12px` | Card internal padding, section row spacing, toolbar margins |
| `SPACE_LG` | `16px` | Container margins, major card separations, dock header padding |

### B. Corner Radius
Corner radii are strictly standardized to ensure consistent visual curvature:

| Token | Value | Usage |
|---|---|---|
| `RADIUS` | `6px` | Standard buttons, input fields, dropdown menus, table items, dialog panels |
| `RADIUS_MD` | `6px` | Cards, hero containers, collapsible sections, modal dialog shells |

### C. Typography Scale
Typography uses native Windows system fonts (`Segoe UI`, `-apple-system`, `Roboto`, `Helvetica Neue`, `Arial`, `sans-serif`) with strict hierarchical sizing:

| Token | Size | Weight | Role | Minimum WCAG Contrast Ratio |
|---|---|---|---|---|
| `FONT_BODY_SM` | `11px` | Regular (400) / Semi-bold (600) | Captions, status badges, timestamps, table secondary labels | > 6.5:1 against `BG_SURFACE` |
| `FONT_BODY` | `13px` | Regular (400) | Standard body copy, form inputs, list items, table text, menu items | > 14:1 against `BG_ROOT` |
| `FONT_HEADING_SM`| `14px` | Semi-bold (600) | Section headers, card titles, table headers, subheadings | > 14:1 against `BG_ROOT` |
| `FONT_HEADING` | `18px` | Bold (700) | Main window titles, view headers, hero titles | > 14:1 against `BG_ROOT` |

---

## 2. Color Palette & Semantic Roles

### A. Midnight Purple Dark Palette (Default)

| Role | Token Name | Hex Code | Visual Preview & Description |
|---|---|---|---|
| **App Root Background** | `BG_ROOT` | `#08070d` | Deepest black application canvas |
| **Dock Panels & Sidebars**| `BG_PANEL` | `#0d0b14` | Midnight background for docks and navigation rails |
| **Cards & Surfaces** | `BG_SURFACE` | `#120f1d` | Surface background for cards, inputs, and list items |
| **Hover State** | `BG_HOVER` | `#1a1528` | Interactive element hover state |
| **Active / Pressed** | `BG_ACTIVE` | `#251d38` | Interactive element pressed state |
| **Subtle Borders** | `BORDER` | `#231c34` | Subtle purple-tinted container dividing line |
| **Focus Outlines** | `BORDER_FOCUS` | `#8b5cf6` | High-visibility focus ring indicator |
| **Primary Text** | `TEXT_PRIMARY` | `#f5f3ff` | Crisp white with faint purple tint (14.2:1 contrast) |
| **Secondary Text** | `TEXT_SECONDARY` | `#9d95b0` | Readable muted text and labels (6.8:1 contrast) |
| **Muted Text / Hints** | `TEXT_MUTED` | `#9d95b0` | Placeholder hints and secondary metadata |

### B. Semantic Accents (Applied Sparingly)

| Semantic Role | Token Name | Hex Code | Usage |
|---|---|---|---|
| **Brand / Primary Action**| `ACCENT_PRIMARY` | `#7c3aed` | Primary CTA buttons, active selection pills, brand accents |
| **Action Hover** | `ACCENT_HOVER` | `#8b5cf6` | Hover state for primary buttons |
| **Action Active** | `ACCENT_ACTIVE` | `#6d28d9` | Pressed state for primary buttons |
| **Success / Verified** | `ACCENT_SUCCESS` | `#00d9a3` | Emerald teal for passing tests, ready status, completed steps |
| **Warning / Busy** | `ACCENT_WARNING` | `#f59e0b` | Amber for in-flight tasks, warnings, build execution |
| **Error / Failure** | `ACCENT_ERROR` | `#ef4444` | Coral red for compiler errors, failed scenarios, critical alerts |

---

## 3. Light Theme Support (Glossy Purple Light)

GameForge supports runtime dark/light theme switching via `Ctrl+T` or Settings View.

| Dark Token | Light Equivalent | Purpose |
|---|---|---|
| `BG_ROOT` (`#08070d`) | `#f8f7fc` | Clean crisp paper background |
| `BG_PANEL` (`#0d0b14`) | `#f0eef8` | Subtle cool grey-purple panels |
| `BG_SURFACE` (`#120f1d`) | `#ffffff` | Pure white cards and text fields |
| `BG_HOVER` (`#1a1528`) | `#e8e4f5` | Hover state |
| `BORDER` (`#231c34`) | `#d8d2eb` | Soft perimeter borders |
| `TEXT_PRIMARY` (`#f5f3ff`) | `#181126` | Deep purple-black high-contrast text |
| `TEXT_SECONDARY` (`#9d95b0`)| `#645a7a` | Medium-contrast secondary text |
| `ACCENT_PRIMARY` (`#7c3aed`)| `#6d28d9` | Deep saturated purple for light canvas |

---

## 4. Component Standardization Guidelines

1. **Buttons:**
   - Primary: `background: ACCENT_PRIMARY`, `color: TEXT_PRIMARY`, `border-radius: RADIUS`, padding `8px 16px`. Hover: `ACCENT_HOVER`.
   - Secondary: `background: BG_SURFACE`, `color: TEXT_PRIMARY`, `border: 1px solid BORDER`, `border-radius: RADIUS`, padding `8px 16px`. Hover: `BG_HOVER`.
   - Destructive: `background: BG_SURFACE`, `color: ACCENT_ERROR`, `border: 1px solid ACCENT_ERROR`.
2. **Text Inputs (`QLineEdit`, `QTextEdit`):**
   - `background: BG_SURFACE`, `border: 1px solid BORDER`, `border-radius: RADIUS`, padding `6px 10px`, `color: TEXT_PRIMARY`.
   - Focus: `border: 1px solid BORDER_FOCUS`.
3. **Cards & Containers:**
   - `background: BG_SURFACE`, `border: 1px solid BORDER`, `border-radius: RADIUS_MD`, padding `SPACE_MD` to `SPACE_LG`.
4. **Tables & Tree Views:**
   - Header: `background: BG_PANEL`, `color: TEXT_SECONDARY`, `font-size: FONT_BODY_SM`, `font-weight: 600`.
   - Row: `border-bottom: 1px solid BORDER`, padding `6px 8px`. Selection: `background: BG_ACTIVE`.
5. **Tooltips:**
   - `background: BG_PANEL`, `color: TEXT_PRIMARY`, `border: 1px solid BORDER`, `border-radius: RADIUS`, `padding: 4px 8px`.
