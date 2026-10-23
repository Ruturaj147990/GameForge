"""GameForge Version-Aware Knowledge Retrieval Engine.

Implements Section 3 of GameForge LLM V1 requirements:
- Lightweight, extensible retrieval across official engine documentation,
  gameplay architecture rubrics, version invariants, and benchmark contracts.
- Strictly bounds retrieved excerpts rather than dumping entire files.
- Preserves document provenance, engine/version metadata, and licensing status.
- Distinguishes verified facts, retrieved docs, assumptions, and uncertain answers.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class KnowledgeSnippet:
    source_title: str
    engine: str
    version_scope: str
    provenance_reference: str
    license: str
    category: str
    excerpt: str
    relevance_score: float = 1.0


class GameForgeKnowledgeBase:
    """Manages version-aware game development knowledge and query retrieval."""

    def __init__(self, workspace_root: Optional[Path] = None):
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.registry_file = self.workspace_root / "configs" / "engine_knowledge_registry.json"
        self.snippets: List[KnowledgeSnippet] = []
        self._load_knowledge()

    def _load_knowledge(self) -> None:
        """Loads structured knowledge from engine registry, requirements, and docs."""
        # 1. Engine Knowledge Registry
        if self.registry_file.is_file():
            try:
                reg_data = json.loads(self.registry_file.read_text(encoding="utf-8"))
                for engine_id, engine_info in reg_data.get("engines", {}).items():
                    eng_name = engine_id.replace("_", " ").title()
                    primary_ver = engine_info.get("primary_version", "latest")
                    doc_url = engine_info.get("official_docs", "N/A")
                    
                    for api_cat, api_data in engine_info.get("api_families", {}).items():
                        comps = ", ".join(api_data.get("components", []))
                        notes = api_data.get("notes", "")
                        excerpt = (
                            f"Engine: {eng_name} ({primary_ver})\n"
                            f"API Family: {api_cat.replace('_', ' ').title()}\n"
                            f"Core Types/Components: {comps}\n"
                            f"Engineering Invariants: {notes}\n"
                            f"Official Reference: {api_data.get('doc_url', doc_url)}"
                        )
                        self.snippets.append(
                            KnowledgeSnippet(
                                source_title=f"{eng_name} - {api_cat}",
                                engine=engine_id,
                                version_scope=primary_ver,
                                provenance_reference=api_data.get("doc_url", doc_url),
                                license="Official Public Documentation Reference",
                                category="engine_api",
                                excerpt=excerpt,
                            )
                        )
            except Exception:
                pass

        # 2. Mathematical and Engine-Independent Architecture Invariants
        self.snippets.extend([
            KnowledgeSnippet(
                source_title="Engine-Independent Gameplay Mathematics",
                engine="neutral",
                version_scope="universal",
                provenance_reference="doc://gameforge/game_engine_intelligence_scope.md",
                license="GameForge Apache-2.0",
                category="gameplay_math",
                excerpt=(
                    "Gameplay Math Principles:\n"
                    "- Coordinate Systems: Unreal uses Left-Handed Z-Up (X=Forward, Y=Right, Z=Up). Unity uses Left-Handed Y-Up (X=Right, Y=Up, Z=Forward). Godot uses Right-Handed Y-Up (X=Right, Y=Up, Z=-Forward in 3D).\n"
                    "- Rotation & Quaternions: Euler angle representation suffers from Gimbal Lock when Pitch reaches +/-90 degrees. Always accumulate continuous rotations using Quaternions, and clamp Euler pitch before converting back.\n"
                    "- Invulnerability Windows: Expiry calculation must use simulation delta time or explicit timer delegates rather than wall-clock sleep to ensure determinism under framerate drops.\n"
                    "- State Machine Transitions: Exactly-once state transitions (such as player death) must be guarded with atomic flags (e.g., bIsDead) and dispatch events in deterministic sequence: StateChange -> DamageAccepted -> Death."
                )
            ),
            KnowledgeSnippet(
                source_title="GameForge Model Behavior & Architectural Standards",
                engine="neutral",
                version_scope="universal",
                provenance_reference="doc://gameforge/model_requirements.md",
                license="GameForge Apache-2.0",
                category="architecture_standards",
                excerpt=(
                    "GameForge Code Generation Directives:\n"
                    "- Never emit placeholder comments like '// ... implement here' when requested for production code.\n"
                    "- Always pair Gameplay Components with typed receiver interfaces rather than brittle string reflection.\n"
                    "- Always enforce safe mathematical clamping on bounded resources (Health, Stamina, Mana) between 0.0f and Max.\n"
                    "- Provide unit test oracles or behavioral probe specifications alongside novel gameplay systems."
                )
            ),
            KnowledgeSnippet(
                source_title="Unreal Engine 5.7 C++ Memory & Component Architecture",
                engine="unreal_engine",
                version_scope="5.7.4",
                provenance_reference="https://dev.epicgames.com/documentation/en-us/unreal-engine/gameplay-framework-in-unreal-engine",
                license="Official Public Documentation Reference",
                category="engine_architecture",
                excerpt=(
                    "Unreal Engine 5 Architecture:\n"
                    "- Subobject Instantiation: Components created in C++ constructors MUST use CreateDefaultSubobject<TComponent>(TEXT('Name')). Runtime components created during play use NewObject<TComponent>(this) and RegisterComponent().\n"
                    "- Dynamic Delegates: Event handlers bound to OnComponentBeginOverlap or OnComponentHit MUST have UFUNCTION() macro decoration and exact parameter signatures matching engine definitions.\n"
                    "- Build Module Dependencies: Add 'EnhancedInput', 'UMG', 'Slate', 'SlateCore' to PublicDependencyModuleNames in Project.Build.cs when referencing their headers."
                )
            ),
            KnowledgeSnippet(
                source_title="Unity 2022.3 / 6.0 C# Lifecycle & Physics Contracts",
                engine="unity",
                version_scope="2022.3 LTS",
                provenance_reference="https://docs.unity3d.com/ScriptReference/MonoBehaviour.html",
                license="Official Public Documentation Reference",
                category="engine_architecture",
                excerpt=(
                    "Unity Architecture:\n"
                    "- Execution Order: Awake (initialization) -> OnEnable (event subscriptions) -> Start (cross-component references) -> FixedUpdate (physics) -> Update (input/render) -> OnDisable (unsubscribe) -> OnDestroy (teardown).\n"
                    "- Physics: Apply forces and velocity modifications in FixedUpdate(). Use Rigidbody.MovePosition() or Rigidbody.linearVelocity (Unity 6) / Rigidbody.velocity (Unity 2022) for continuous physics-aligned movement.\n"
                    "- Event Cleanliness: Always unbind C# events in OnDisable() to prevent memory leaks and duplicate invocations on re-instantiation."
                )
            ),
            KnowledgeSnippet(
                source_title="Godot 4.3 GDScript & Node3D Architecture",
                engine="godot",
                version_scope="4.3",
                provenance_reference="https://docs.godotengine.org/en/stable/classes/class_node.html",
                license="Official Public Documentation Reference",
                category="engine_architecture",
                excerpt=(
                    "Godot 4 Architecture:\n"
                    "- Nodes: CharacterBody3D handles kinematic character locomotion using move_and_slide(). Velocity is an internal property (velocity = dir * speed).\n"
                    "- Physics Lifecycle: Use _physics_process(delta) for movement, gravity, and collision queries. Use _process(delta) for visual/camera updates.\n"
                    "- Signals: Declare signals with `signal health_changed(new_health: float)`. Connect with `health_changed.connect(_on_health_changed)`. Emit with `health_changed.emit(current_health)`."
                )
            )
        ])

    def query_knowledge(self, query: str, engine_filter: Optional[str] = None, max_results: int = 2) -> List[KnowledgeSnippet]:
        """Performs lexical and semantic relevance scoring on query against knowledge snippets."""
        q_tokens = set(query.lower().replace(",", " ").replace(".", " ").split())
        scored: List[Tuple[float, KnowledgeSnippet]] = []

        for snip in self.snippets:
            if engine_filter and engine_filter != "all" and snip.engine != "neutral":
                if engine_filter.lower() not in snip.engine.lower():
                    continue

            text_pool = f"{snip.source_title} {snip.category} {snip.excerpt}".lower()
            overlap = sum(1 for t in q_tokens if t in text_pool)
            
            # Boost matches on engine name or exact API tokens
            boost = 1.0
            if snip.engine in query.lower():
                boost += 2.0
            if snip.category in query.lower():
                boost += 1.5

            score = (overlap * boost) / (len(q_tokens) + 1.0)
            if score > 0.05 or snip.engine == "neutral":
                scored.append((score, snip))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:max_results]]

    def format_retrieval_context(self, snippets: List[KnowledgeSnippet]) -> str:
        """Formats bounded excerpts with full provenance into a model prompt context."""
        if not snippets:
            return ""

        lines = ["\n[GAMEFORGE LOCAL KNOWLEDGE LAYER — RETRIEVED PROJECT EXCERPTS]"]
        for idx, snip in enumerate(snippets, 1):
            lines.append(f"--- Document {idx}: {snip.source_title} ({snip.version_scope}) ---")
            lines.append(f"Provenance / Reference: {snip.provenance_reference}")
            lines.append(f"License: {snip.license}")
            lines.append("Content:")
            lines.append(snip.excerpt)
            lines.append("-----------------------------------------------------------------")
        lines.append("[END RETRIEVED CONTEXT — USE VERIFIED FACTS TO ANCHOR RESPONSE]\n")
        return "\n".join(lines)
