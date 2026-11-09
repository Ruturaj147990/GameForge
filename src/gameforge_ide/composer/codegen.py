"""Composer custom rule and architecture codegen (WI-6.6).

Generates safe, compilable C++ custom rule classes implementing UGameForgeCustomRule
and composable game state machines from ArchitectureSpec, custom capabilities, and rules.
Interacts directly with AGameForgeGameState and UGameForgeEventBus at runtime.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
from .model import CodegenTask

DENYLIST_PATTERN = re.compile(
    r"#include|FPlatformProcess|FFileHelper|IFileManager|Exec\(|ConsoleCommand|asm|reinterpret_cast|system\(|ShellExecute|socket\(|fork\(",
    re.IGNORECASE,
)


def sanitize_cpp_identifier(name: str) -> str:
    """Sanitize project, class, or handler name into a valid C++ identifier."""
    if not name:
        return "GameForgeProject"
    parts = [p for p in re.split(r"[^a-zA-Z0-9]+", name) if p]
    if not parts:
        return "GameForgeProject"
    cleaned = "".join(part[0].upper() + part[1:] if part[0].isalpha() else part for part in parts)
    if cleaned and cleaned[0].isdigit():
        cleaned = f"GF{cleaned}"
    return cleaned or "GameForgeProject"


def safety_scan(code: str) -> Tuple[bool, List[str]]:
    """Scan code bodies for prohibited includes, system calls, or memory operations."""
    violations: List[str] = []
    for match in DENYLIST_PATTERN.finditer(code):
        violations.append(f"Prohibited symbol or directive: {match.group(0)!r}")
    return len(violations) == 0, violations


def synthesize_cpp_bodies_for_architecture(
    architecture: Optional[Dict[str, Any]],
    custom_rules: Optional[List[str]] = None,
) -> Tuple[str, str]:
    """Synthesize composable, compilable C++ OnEvent and Tick bodies from ArchitectureSpec and custom rules."""
    arch = architecture or {}
    plan_kind = str(arch.get("plan_kind") or "").lower()
    target_classes = " ".join(str(c) for c in (arch.get("target_classes") or [])).lower()
    custom_caps = {str(c).lower() for c in (arch.get("custom_capabilities") or [])}
    mechanics = arch.get("mechanics") if isinstance(arch.get("mechanics"), dict) else {}
    for m_item in (mechanics.get("active_mechanics") or []):
        custom_caps.add(str(m_item).lower())

    rules_text = " | ".join(custom_rules or [])
    rules_low = rules_text.lower()
    safe_summary = re.sub(r'["\\\r\n]+', " ", rules_text)[:160]

    # 1. Discrete Grid / Constraint / Board State Machines
    if "sudoku" in plan_kind or "sudoku" in target_classes or (
        "scratch_puzzle" in plan_kind and mechanics.get("subgrid_size") == 3
    ):
        on_event = (
            "\tUWorld* World = GetWorld();\n"
            "\tAGameForgeGameState* GS = World ? World->GetGameState<AGameForgeGameState>() : nullptr;\n"
            "\tif (Event.EventName == TEXT(\"board.move\") || Event.EventName == TEXT(\"pickup.collected\"))\n"
            "\t{\n"
            "\t\tMovesPlayed += 1;\n"
            "\t\tconst int32 Row = (MovesPlayed - 1) / 9;\n"
            "\t\tconst int32 Col = (MovesPlayed - 1) % 9;\n"
            "\t\tconst int32 CandidateDigit = ((Row * 3 + Row / 3 + Col) % 9) + 1;\n"
            "\t\tbool bConflict = false;\n"
            "\t\tfor (int32 i = 0; i < 9; ++i)\n"
            "\t\t{\n"
            "\t\t\tif (SudokuGrid[Row][i] == CandidateDigit || SudokuGrid[i][Col] == CandidateDigit)\n"
            "\t\t\t{\n"
            "\t\t\t\tbConflict = true;\n"
            "\t\t\t}\n"
            "\t\t}\n"
            "\t\tif (!bConflict && Row >= 0 && Row < 9 && Col >= 0 && Col < 9)\n"
            "\t\t{\n"
            "\t\t\tSudokuGrid[Row][Col] = CandidateDigit;\n"
            "\t\t\tValidPlacements += 1;\n"
            "\t\t\tif (GS) { GS->AddStat(FName(TEXT(\"game.score\")), 10.0f); }\n"
            "\t\t}\n"
            "\t}"
        )
        tick = (
            "\tElapsedRuleTime += DeltaSeconds;\n"
            "\tif (bRuleEnabled && ValidPlacements >= 81 && !bCompleted)\n"
            "\t{\n"
            "\t\tbCompleted = true;\n"
            "\t}"
        )
        return on_event, tick

    if "scratch_board" in plan_kind or "chess" in target_classes or "checkers" in target_classes:
        on_event = (
            "\tUWorld* World = GetWorld();\n"
            "\tAGameForgeGameState* GS = World ? World->GetGameState<AGameForgeGameState>() : nullptr;\n"
            "\tif (Event.EventName == TEXT(\"board.move\") || Event.EventName == TEXT(\"turn.ended\"))\n"
            "\t{\n"
            "\t\tMovesPlayed += 1;\n"
            "\t\tbWhiteTurn = !bWhiteTurn;\n"
            "\t\tif (GS) { GS->AddStat(FName(TEXT(\"game.score\")), 5.0f); }\n"
            "\t}\n"
            "\telse if (Event.EventName == TEXT(\"dice.rolled\"))\n"
            "\t{\n"
            "\t\tValidPlacements += 1;\n"
            "\t}"
        )
        tick = (
            "\tElapsedRuleTime += DeltaSeconds;\n"
            "\tif (bRuleEnabled && MovesPlayed >= 40 && !bCompleted)\n"
            "\t{\n"
            "\t\tbCompleted = true;\n"
            "\t}"
        )
        return on_event, tick

    if "falling_blocks" in plan_kind or "tetris" in plan_kind or "tetris" in target_classes:
        on_event = (
            "\tUWorld* World = GetWorld();\n"
            "\tAGameForgeGameState* GS = World ? World->GetGameState<AGameForgeGameState>() : nullptr;\n"
            "\tif (Event.EventName == TEXT(\"board.move\") || Event.EventName == TEXT(\"line.cleared\"))\n"
            "\t{\n"
            "\t\tMovesPlayed += 1;\n"
            "\t\tif (GS) { GS->AddStat(FName(TEXT(\"game.score\")), 25.0f); }\n"
            "\t}"
        )
        tick = (
            "\tElapsedRuleTime += DeltaSeconds;\n"
            "\tStepAccumulator += DeltaSeconds;\n"
            "\tif (bRuleEnabled && StepAccumulator >= 0.5f)\n"
            "\t{\n"
            "\t\tStepAccumulator = 0.0f;\n"
            "\t\tMovesPlayed += 1;\n"
            "\t\tif (MovesPlayed % 10 == 0)\n"
            "\t\t{\n"
            "\t\t\tValidPlacements += 1;\n"
            "\t\t}\n"
            "\t}"
        )
        return on_event, tick

    if "scratch_snake" in plan_kind:
        on_event = (
            "\tUWorld* World = GetWorld();\n"
            "\tAGameForgeGameState* GS = World ? World->GetGameState<AGameForgeGameState>() : nullptr;\n"
            "\tif (Event.EventName == TEXT(\"pickup.collected\") || Event.EventName == TEXT(\"board.move\"))\n"
            "\t{\n"
            "\t\tValidPlacements += 1;\n"
            "\t\tMovesPlayed += 10;\n"
            "\t\tif (GS) { GS->AddStat(FName(TEXT(\"game.score\")), 15.0f); }\n"
            "\t}"
        )
        tick = (
            "\tElapsedRuleTime += DeltaSeconds;\n"
            "\tStepAccumulator += DeltaSeconds;\n"
            "\tif (bRuleEnabled && StepAccumulator >= 0.15f)\n"
            "\t{\n"
            "\t\tStepAccumulator = 0.0f;\n"
            "\t\tMovesPlayed += 1;\n"
            "\t}"
        )
        return on_event, tick

    # 2. Composable Real-Time / Action / Strategy / Exploration C++ Synthesis
    event_blocks: List[str] = [
        f"\t// Dynamic gameplay subsystem: {safe_summary or plan_kind or 'Active mechanics'}\n"
        "\tUWorld* World = GetWorld();\n"
        "\tAGameForgeGameState* GS = World ? World->GetGameState<AGameForgeGameState>() : nullptr;\n"
        "\tUGameForgeEventBus* Bus = UGameForgeEventBus::Get(this);"
    ]
    tick_blocks: List[str] = [
        "\tElapsedRuleTime += DeltaSeconds;\n"
        "\tStepAccumulator += DeltaSeconds;\n"
        "\tUWorld* World = GetWorld();\n"
        "\tAGameForgeGameState* GS = World ? World->GetGameState<AGameForgeGameState>() : nullptr;"
    ]

    # Capability A: Lap & Checkpoint Circuit Tracker
    if "racing" in plan_kind or "checkpoint_lap_tracker" in custom_caps or "vehicle_driving" in custom_caps or mechanics.get("lap_count"):
        lap_target = int(mechanics.get("lap_count", 3) or 3)
        cp_count = int(mechanics.get("checkpoint_count", 4) or 4)
        event_blocks.append(
            f"\tconst int32 TargetLaps = {lap_target};\n"
            f"\tconst int32 CheckpointsPerLap = {cp_count};\n"
            "\tif (Event.EventName == TEXT(\"checkpoint.reached\"))\n"
            "\t{\n"
            "\t\tMovesPlayed += 1;\n"
            "\t\tif (GS) { GS->AddStat(FName(TEXT(\"game.score\")), 20.0f); }\n"
            "\t\tif (MovesPlayed >= CheckpointsPerLap)\n"
            "\t\t{\n"
            "\t\t\tMovesPlayed = 0;\n"
            "\t\t\tValidPlacements += 1;\n"
            "\t\t\tif (GS) { GS->SetStat(FName(TEXT(\"game.laps\")), static_cast<float>(ValidPlacements)); }\n"
            "\t\t\tif (Bus) { Bus->EmitSimple(FName(TEXT(\"lap.completed\")), this, FName(TEXT(\"race\")), static_cast<float>(ValidPlacements)); }\n"
            "\t\t\tif (ValidPlacements >= TargetLaps && !bCompleted)\n"
            "\t\t\t{\n"
            "\t\t\t\tbCompleted = true;\n"
            "\t\t\t\tif (Bus) { Bus->EmitSimple(FName(TEXT(\"race.finished\")), this, FName(TEXT(\"race\")), ElapsedRuleTime); }\n"
            "\t\t\t}\n"
            "\t\t}\n"
            "\t}"
        )

    # Capability B: Tower Defense / Resource Economy & Wave Bounty
    if "tower_defense" in plan_kind or "turret_defense" in custom_caps or mechanics.get("starting_gold"):
        starting_gold = int(mechanics.get("starting_gold", 250) or 250)
        event_blocks.append(
            "\tif (Event.EventName == TEXT(\"game.started\"))\n"
            "\t{\n"
            f"\t\tResourcePool = {starting_gold};\n"
            "\t\tif (GS) { GS->SetStat(FName(TEXT(\"game.gold\")), static_cast<float>(ResourcePool)); }\n"
            "\t}\n"
            "\telse if (Event.EventName == TEXT(\"enemy.killed\"))\n"
            "\t{\n"
            "\t\tResourcePool += 20;\n"
            "\t\tMovesPlayed += 1;\n"
            "\t\tif (GS) { GS->SetStat(FName(TEXT(\"game.gold\")), static_cast<float>(ResourcePool)); }\n"
            "\t}\n"
            "\telse if (Event.EventName == TEXT(\"wave.cleared\"))\n"
            "\t{\n"
            "\t\tValidPlacements += 1;\n"
            "\t\tResourcePool += 60;\n"
            "\t\tif (GS) { GS->SetStat(FName(TEXT(\"game.gold\")), static_cast<float>(ResourcePool)); }\n"
            "\t}"
        )

    # Capability C: Oxygen / Environmental Resource Drain & Refill
    if "oxygen_hazard_drain" in custom_caps or "resource_drain" in custom_caps or "oxygen" in rules_low:
        event_blocks.append(
            "\tif (Event.EventName == TEXT(\"game.started\"))\n"
            "\t{\n"
            "\t\tResourcePool = 100;\n"
            "\t\tif (GS) { GS->SetStat(FName(TEXT(\"player.oxygen\")), 100.0f); }\n"
            "\t}\n"
            "\telse if (Event.EventName == TEXT(\"pickup.collected\"))\n"
            "\t{\n"
            "\t\tResourcePool = FMath::Min(100, ResourcePool + 25);\n"
            "\t\tif (GS) { GS->SetStat(FName(TEXT(\"player.oxygen\")), static_cast<float>(ResourcePool)); }\n"
            "\t}"
        )
        tick_blocks.append(
            "\tif (bRuleEnabled && StepAccumulator >= 2.0f)\n"
            "\t{\n"
            "\t\tStepAccumulator = 0.0f;\n"
            "\t\tResourcePool = FMath::Max(0, ResourcePool - 4);\n"
            "\t\tif (GS)\n"
            "\t\t{\n"
            "\t\t\tGS->SetStat(FName(TEXT(\"player.oxygen\")), static_cast<float>(ResourcePool));\n"
            "\t\t\tif (ResourcePool <= 0)\n"
            "\t\t\t{\n"
            "\t\t\t\tGS->AddStat(FName(TEXT(\"player.health\")), -5.0f);\n"
            "\t\t\t}\n"
            "\t\t}\n"
            "\t}"
        )

    # Capability D: Shield Absorption & Auto-Recharge
    if "shield_recharge" in custom_caps or "shield" in rules_low:
        event_blocks.append(
            "\tif (Event.EventName == TEXT(\"game.started\") && GS)\n"
            "\t{\n"
            "\t\tGS->SetStat(FName(TEXT(\"player.shield\")), 100.0f);\n"
            "\t}\n"
            "\telse if (Event.EventName == TEXT(\"player.damaged\") && GS)\n"
            "\t{\n"
            "\t\tconst float CurShield = GS->GetStat(FName(TEXT(\"player.shield\")));\n"
            "\t\tif (CurShield > 0.0f)\n"
            "\t\t{\n"
            "\t\t\tGS->SetStat(FName(TEXT(\"player.shield\")), FMath::Max(0.0f, CurShield - 15.0f));\n"
            "\t\t\tGS->AddStat(FName(TEXT(\"player.health\")), 10.0f);\n"
            "\t\t}\n"
            "\t\tStepAccumulator = 0.0f;\n"
            "\t}"
        )
        tick_blocks.append(
            "\tif (bRuleEnabled && StepAccumulator >= 3.0f && GS)\n"
            "\t{\n"
            "\t\tStepAccumulator = 0.0f;\n"
            "\t\tconst float CurShield = GS->GetStat(FName(TEXT(\"player.shield\")));\n"
            "\t\tif (CurShield < 100.0f)\n"
            "\t\t{\n"
            "\t\t\tGS->SetStat(FName(TEXT(\"player.shield\")), FMath::Min(100.0f, CurShield + 10.0f));\n"
            "\t\t}\n"
            "\t}"
        )

    # Capability E: Interactive Switches / Terminals / Doors
    if "interactive_switches" in custom_caps or mechanics.get("interactive_object"):
        event_blocks.append(
            "\tif (Event.EventName == TEXT(\"switch.toggled\") || Event.EventName == TEXT(\"interact.used\"))\n"
            "\t{\n"
            "\t\tValidPlacements += 1;\n"
            "\t\tif (GS)\n"
            "\t\t{\n"
            "\t\t\tGS->AddStat(FName(TEXT(\"game.counter.switches_activated\")), 1.0f);\n"
            "\t\t\tGS->AddStat(FName(TEXT(\"game.score\")), 35.0f);\n"
            "\t\t}\n"
            "\t}"
        )

    # Capability F: Combat Combo Multiplier & Wave Progression
    if "combo_multiplier" in custom_caps or "wave_progression" in custom_caps or "roguelike" in plan_kind or mechanics.get("wave_count"):
        event_blocks.append(
            "\tif (Event.EventName == TEXT(\"enemy.killed\"))\n"
            "\t{\n"
            "\t\tMovesPlayed += 1;\n"
            "\t\tconst float ComboBonus = static_cast<float>(FMath::Clamp(MovesPlayed * 5, 5, 50));\n"
            "\t\tif (GS) { GS->AddStat(FName(TEXT(\"game.score\")), ComboBonus); }\n"
            "\t}\n"
            "\telse if (Event.EventName == TEXT(\"wave.cleared\"))\n"
            "\t{\n"
            "\t\tValidPlacements += 1;\n"
            "\t\tif (GS) { GS->AddStat(FName(TEXT(\"player.health\")), 20.0f); }\n"
            "\t}"
        )

    # Ensure there is always at least one event reaction and tick update
    if len(event_blocks) == 1:
        event_blocks.append(
            "\tif (!Event.EventName.IsEmpty())\n"
            "\t{\n"
            "\t\tMovesPlayed += 1;\n"
            "\t\tif (Event.EventName == TEXT(\"pickup.collected\") && GS)\n"
            "\t\t{\n"
            "\t\t\tGS->AddStat(FName(TEXT(\"game.score\")), 10.0f);\n"
            "\t\t}\n"
            "\t\telse if (Event.EventName == TEXT(\"player.dashed\") && GS)\n"
            "\t\t{\n"
            "\t\t\tGS->AddStat(FName(TEXT(\"game.score\")), 5.0f);\n"
            "\t\t}\n"
            "\t}"
        )
    if len(tick_blocks) == 1:
        tick_blocks.append(
            "\tif (bRuleEnabled && StepAccumulator >= 1.0f)\n"
            "\t{\n"
            "\t\tStepAccumulator = 0.0f;\n"
            "\t}"
        )

    return "\n".join(event_blocks), "\n".join(tick_blocks)


def plan_architecture_codegen(gds: Any) -> List[CodegenTask]:
    """Generate CodegenTask objects from gds.architecture when present."""
    arch_obj = getattr(gds, "architecture", None)
    if arch_obj is None:
        return []
    arch = arch_obj.model_dump() if hasattr(arch_obj, "model_dump") else (arch_obj if isinstance(arch_obj, dict) else {})
    if not arch:
        return []

    has_targets = bool(arch.get("target_classes") or arch.get("custom_capabilities") or arch.get("mechanics"))
    method = str(arch.get("method") or "")
    if not has_targets and not method.startswith(("scratch", "hybrid", "llm_scratch", "llm_hybrid", "template_adaptation")):
        return []

    target_classes = arch.get("target_classes") or []
    raw_cls = str(target_classes[0]) if target_classes else "DynamicGameplayRule"
    clean_cls = sanitize_cpp_identifier(raw_cls.lstrip("AUF"))
    if not clean_cls.endswith("Rule"):
        clean_cls = f"{clean_cls[:28]}Rule"
    plan_kind = str(arch.get("plan_kind") or method or "dynamic_gameplay")
    desc = f"Architecture state machine ({plan_kind}): {', '.join(str(c) for c in target_classes[:3]) or clean_cls}"
    on_event, tick = synthesize_cpp_bodies_for_architecture(arch)
    return [
        CodegenTask(
            handler_name=clean_cls,
            description=desc[:400],
            rule_id="architecture_codegen",
            on_event_body=on_event,
            tick_body=tick,
        )
    ]


def generate_header(
    project_name: str,
    handler_name: str,
    properties: Optional[List[Tuple[str, str, Optional[str]]]] = None,
    functions: Optional[List[Tuple[str, str, Optional[str]]]] = None,
) -> str:
    """Generate the C++ header for the custom rule with UPROPERTY, UFUNCTION, and GENERATED_BODY()."""
    clean_proj = sanitize_cpp_identifier(project_name)
    clean_handler = sanitize_cpp_identifier(handler_name)
    proj_api = f"{clean_proj.upper()}_API"

    props_lines: List[str] = [
        '\tUPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")\n\tbool bRuleEnabled = true;',
        '\tUPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")\n\tint32 MovesPlayed = 0;',
        '\tUPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")\n\tint32 ValidPlacements = 0;',
        '\tUPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")\n\tint32 ResourcePool = 250;',
        '\tUPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")\n\tbool bWhiteTurn = true;',
        '\tUPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")\n\tbool bCompleted = false;',
        '\tUPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")\n\tfloat ElapsedRuleTime = 0.0f;',
        '\tUPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")\n\tfloat StepAccumulator = 0.0f;',
        '\tint32 SudokuGrid[9][9] = {{0}};',
    ]
    if properties:
        for p_type, p_name, u_macro in properties:
            if p_name in ("bRuleEnabled", "MovesPlayed", "ValidPlacements", "ResourcePool", "bWhiteTurn", "bCompleted", "ElapsedRuleTime", "StepAccumulator"):
                continue
            macro = u_macro or 'UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")'
            props_lines.append(f"\t{macro}\n\t{p_type} {p_name};")

    funcs_lines: List[str] = []
    if functions:
        for f_ret, f_name, u_macro in functions:
            macro = u_macro or 'UFUNCTION(BlueprintCallable, Category = "GameForge")'
            funcs_lines.append(f"\t{macro}\n\tvirtual {f_ret} {f_name};")
    else:
        funcs_lines.append('\tUFUNCTION(BlueprintCallable, Category = "GameForge")\n\tvirtual void ExecuteRule();')

    props_block = "\n\n".join(props_lines)
    funcs_block = "\n\n".join(funcs_lines)

    return f"""// Copyright 2026 GameForge Systems. Generated custom rule handler.
#pragma once

#include "CoreMinimal.h"
#include "GameForgeRules.h"
#include "{clean_handler}.generated.h"

UCLASS()
class {proj_api} U{clean_handler} : public UGameForgeCustomRule
{{
\tGENERATED_BODY()

public:
{props_block}

\tvirtual void OnEvent(const FGameForgeEvent& Event) override;
\tvirtual void Tick(float DeltaSeconds) override;

{funcs_block}
}};
"""


def generate_source(handler_name: str, on_event_body: str = "", tick_body: str = "") -> str:
    """Generate the C++ source file preserving model code markers."""
    clean_handler = sanitize_cpp_identifier(handler_name)
    safe_event, ev_errs = safety_scan(on_event_body)
    if not safe_event:
        raise ValueError(f"on_event_body failed safety scan: {ev_errs}")

    safe_tick, tick_errs = safety_scan(tick_body)
    if not safe_tick:
        raise ValueError(f"tick_body failed safety scan: {tick_errs}")

    effective_event = on_event_body.strip() or (
        "\tif (!Event.EventName.IsEmpty())\n"
        "\t{\n"
        "\t\tMovesPlayed += 1;\n"
        "\t}"
    )
    effective_tick = tick_body.strip() or (
        "\tElapsedRuleTime += DeltaSeconds;\n"
        "\tif (bRuleEnabled)\n"
        "\t{\n"
        "\t\tStepAccumulator += DeltaSeconds;\n"
        "\t}"
    )

    return f"""// Copyright 2026 GameForge Systems. Generated custom rule handler.
#include "{clean_handler}.h"
#include "Engine/World.h"
#include "GameForgeGameState.h"
#include "GameForgeEvents.h"
#include "GameForgeEventNames.h"
#include "GameForgeAttributes.h"
#include "GameForgePlayer.h"
#include "GameForgeKitActors.h"
#include "GameForgeObjectives.h"
#include "Kismet/GameplayStatics.h"
#include "Kismet/KismetSystemLibrary.h"

void U{clean_handler}::ExecuteRule()
{{
\tbRuleEnabled = true;
\tMovesPlayed = 0;
\tValidPlacements = 0;
\tbCompleted = false;
\tElapsedRuleTime = 0.0f;
\tStepAccumulator = 0.0f;
\tfor (int32 r = 0; r < 9; ++r)
\t{{
\t\tfor (int32 c = 0; c < 9; ++c)
\t\t{{
\t\t\tSudokuGrid[r][c] = 0;
\t\t}}
\t}}
}}

void U{clean_handler}::OnEvent(const FGameForgeEvent& Event)
{{
\tSuper::OnEvent(Event);
\t// BEGIN MODEL CODE
{effective_event}
\t// END MODEL CODE
}}

void U{clean_handler}::Tick(float DeltaSeconds)
{{
\tSuper::Tick(DeltaSeconds);
\t// BEGIN MODEL CODE
{effective_tick}
\t// END MODEL CODE
}}
"""


def extract_model_bodies(cpp_content: str) -> Dict[str, str]:
    """Extract code within // BEGIN MODEL CODE and // END MODEL CODE."""
    pattern = re.compile(r"// BEGIN MODEL CODE\s*(.*?)\s*// END MODEL CODE", re.DOTALL)
    matches = pattern.findall(cpp_content)
    return {
        "on_event_body": matches[0].strip() if len(matches) > 0 else "",
        "tick_body": matches[1].strip() if len(matches) > 1 else "",
    }
