"""Composer custom rule codegen (WI-6.6).

Generates safe C++ custom rule classes implementing UGameForgeCustomRule.
Validates model output against strict denylist and enforces scaffolding bounds.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple
from .model import CodegenTask

DENYLIST_PATTERN = re.compile(
    r"#include|FPlatformProcess|FFileHelper|IFileManager|Exec\(|ConsoleCommand|asm|reinterpret_cast|system\(|ShellExecute|socket\(|fork\(",
    re.IGNORECASE,
)


def safety_scan(code: str) -> Tuple[bool, List[str]]:
    """Scan code bodies for prohibited includes, system calls, or memory operations."""
    violations: List[str] = []
    for match in DENYLIST_PATTERN.finditer(code):
        violations.append(f"Prohibited symbol or directive: {match.group(0)!r}")
    return len(violations) == 0, violations


def generate_header(project_name: str, handler_name: str) -> str:
    """Generate the C++ header for the custom rule."""
    proj_api = f"{project_name.upper()}_API"
    return f"""// Copyright 2026 GameForge Systems. Generated custom rule handler.
#pragma once

#include "CoreMinimal.h"
#include "GameForgeRules.h"
#include "{handler_name}.generated.h"

UCLASS()
class {proj_api} U{handler_name} : public UGameForgeCustomRule
{{
\tGENERATED_BODY()

public:
\tvirtual void OnEvent(const FGameForgeEvent& Event) override;
\tvirtual void Tick(float DeltaSeconds) override;
}};
"""


def generate_source(handler_name: str, on_event_body: str = "", tick_body: str = "") -> str:
    """Generate the C++ source file preserving model code markers."""
    safe_event, ev_errs = safety_scan(on_event_body)
    if not safe_event:
        raise ValueError(f"on_event_body failed safety scan: {ev_errs}")

    safe_tick, tick_errs = safety_scan(tick_body)
    if not safe_tick:
        raise ValueError(f"tick_body failed safety scan: {tick_errs}")

    return f"""// Copyright 2026 GameForge Systems. Generated custom rule handler.
#include "{handler_name}.h"
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

void U{handler_name}::OnEvent(const FGameForgeEvent& Event)
{{
\tSuper::OnEvent(Event);
\t// BEGIN MODEL CODE
{on_event_body}
\t// END MODEL CODE
}}

void U{handler_name}::Tick(float DeltaSeconds)
{{
\tSuper::Tick(DeltaSeconds);
\t// BEGIN MODEL CODE
{tick_body}
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
