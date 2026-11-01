# GameForge 1.0 — Master Feature Registry
Generated: 2026-11-01T23:59:21.843216 | Verified by Antigravity Autonomous Inspector

## Overview
Total Canonical Features Registered: 39

| Feature ID | Subsystem / Area | Implementation Module | Capability Specification | Verification Status |
|---|---|---|---|---|
| **CORE-001** | Core Directory Management | `core.projects` | Multi-root dynamic project discovery across workspace, projects_root, and developer directories | `VERIFIED_LIVE` |
| **CORE-002** | Project Identity & Markers | `core.projects` | Authoritative project identification using .uproject, spec.json, and gameforge.json | `VERIFIED_LIVE` |
| **CORE-003** | Desktop Shell Dual Mode | `desktop.main_window` | Switching between Studio Shell (modern multi-view) and Dock Window | `VERIFIED_LIVE` |
| **CORE-004** | TopBar Project Selector | `desktop.widgets.top_bar` | Dynamic dropdown selector reflecting active project across entire IDE | `VERIFIED_LIVE` |
| **CORE-005** | TopBar View Navigation | `desktop.widgets.top_bar` | One-click tabbed navigation across all 7 canonical views | `VERIFIED_LIVE` |
| **CORE-006** | Embedded Terminal | `desktop.panels.terminal_panel` | Safe user-driven terminal synchronized to active project directory | `VERIFIED_LIVE` |
| **CORE-007** | Theme Persistence | `desktop.styles.theme` | Studio Dark and Studio Light switching with Ctrl+T and INI persistence | `VERIFIED_LIVE` |
| **CORE-008** | Settings Persistence | `core.settings` | Host profile and user settings serialization in %APPDATA%/GameForge/settings.json | `VERIFIED_LIVE` |
| **CHAT-001** | Ollama Daemon Integration | `agent.ollama_client` | HTTP client communication to Ollama 127.0.0.1:11434 with think=False | `VERIFIED_LIVE` |
| **CHAT-002** | Chat Panel UI Streaming | `desktop.panels.chat_panel` | Asynchronous real-time token streaming without Qt UI thread freezing | `VERIFIED_LIVE` |
| **CHAT-003** | Model Routing & Fallbacks | `core.settings` | Dynamic model resolution (qwen3.5-9b primary, qwen3.5-4b fast, 27b-sft planner) | `VERIFIED_LIVE` |
| **CHAT-004** | Conversation Persistence | `desktop.panels.chat_panel` | History save and reload per project session in workspace index | `VERIFIED_LIVE` |
| **HOME-001** | Home Dashboard & Presets | `desktop.views.home_view` | Preset chips (Top-Down Shooter, 3D Platformer, Racing) injecting prompts | `VERIFIED_LIVE` |
| **HOME-002** | Home System Telemetry | `desktop.views.home_view` | Real-time engine, Ollama, GPU, and RAM readiness health indicators | `VERIFIED_LIVE` |
| **GAMES-001** | Games Catalog & Cards | `desktop.views.games_view` | Grid of scanned projects with package badges, thumbnails, and quick play | `VERIFIED_LIVE` |
| **GAMES-002** | Folder Launchers | `desktop.views.games_view` | Open project directory directly in OS File Explorer | `VERIFIED_LIVE` |
| **DESIGN-001** | GDS Interactive Viewer | `desktop.views.design_view` | Tabbed tree and JSON editor for game design specifications | `VERIFIED_LIVE` |
| **DESIGN-002** | GDS Revision History | `desktop.views.design_view` | Interactive rollback and visual diff between spec revisions | `VERIFIED_LIVE` |
| **DESIGN-003** | Build Trigger from Design | `desktop.views.design_view` | One-click 'Build Game' dispatching to Forge pipeline | `VERIFIED_LIVE` |
| **BUILD-001** | Forge Pipeline Executor | `desktop.views.build_view` | Multi-stage pipeline execution (GDS -> Generation -> Unreal -> Cook) | `VERIFIED_LIVE` |
| **BUILD-002** | Live Step Log Streaming | `desktop.views.build_view` | Real-time stdout/stderr log capture per build phase | `VERIFIED_LIVE` |
| **BUILD-003** | Checkpoint Rollback | `desktop.views.build_view` | Roll back failed step artifacts to safe previous checkpoint | `VERIFIED_LIVE` |
| **BUILD-004** | Build Folder Launcher | `desktop.views.build_view` | Direct OS Explorer launch for active build directory | `VERIFIED_LIVE` |
| **PLAY-001** | Integrated Game Launcher | `desktop.views.play_view` | Spawn packaged Win64 executable with crash monitoring | `VERIFIED_LIVE` |
| **PLAY-002** | Automated QA Harness | `desktop.views.play_view` | Headless/windowed playtest runner collecting performance metrics | `VERIFIED_LIVE` |
| **EVID-001** | Evidence Artifact Gallery | `desktop.views.evidence_view` | Visual thumbnail grid of gameplay screenshots and test logs | `VERIFIED_LIVE` |
| **EVID-002** | Artifact OS Inspector | `desktop.views.evidence_view` | Double-click to open full-resolution screenshots in OS viewer | `VERIFIED_LIVE` |
| **SETT-001** | Engine Path Configuration | `desktop.views.settings_view` | Discovery and manual configuration of Unreal Engine 5.7 install | `VERIFIED_LIVE` |
| **SETT-002** | Ollama Model Management | `desktop.views.settings_view` | Dropdown selector mapping roles to installed Ollama model tags | `VERIFIED_LIVE` |
| **UNR-001** | Live Editor REST Bridge | `unreal.live_editor` | Loopback HTTP bridge port 47815 for Unreal Remote Execution | `VERIFIED_LIVE` |
| **UNR-002** | 129 Operations Catalog | `unreal.GameForge` | Complete verified catalog of actor, light, material, and physics operations | `VERIFIED_LIVE` |
| **COMP-001** | Arena Level Generator | `pipeline.level_generator` | Circular combat arena topology for top-down shooters | `VERIFIED_LIVE` |
| **COMP-002** | Course Level Generator | `pipeline.level_generator` | Sequential 3D obstacle and platforming route generator | `VERIFIED_LIVE` |
| **COMP-003** | Lanes Level Generator | `pipeline.level_generator` | Multi-lane linear track generator for racing prototypes | `VERIFIED_LIVE` |
| **COMP-004** | Dynamic Entity Placer | `pipeline.composer` | Procedural placement of spawners, pickups, obstacles, and objectives | `VERIFIED_LIVE` |
| **ORAC-001** | Pickup Collection Oracle | `graders.protected.t2_005` | 12 hidden grading tests for pickup collection mechanics | `VERIFIED_LIVE` |
| **ORAC-002** | Projectile Collision Oracle | `graders.protected.t2_008` | 12 hidden grading tests for projectile hit and lifetime resolution | `VERIFIED_LIVE` |
| **ORAC-003** | Player Composition Oracle | `graders.protected.t3_016` | 9 hidden grading tests for player component composition and movement | `VERIFIED_LIVE` |
| **ORAC-004** | Health/Stamina HUD Oracle | `graders.protected.t3_017` | 12 hidden grading tests for HUD data binding and re-initialization | `VERIFIED_LIVE` |

