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


def sanitize_cpp_identifier(name: str) -> str:
    """Sanitize project, class, or handler name into a valid C++ identifier.
    
    Transforms names like 'My-Game 2' -> 'MyGame2' and ensures the result
    never starts with a digit or contains illegal characters.
    """
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

    props_lines: List[str] = []
    if properties:
        for p_type, p_name, u_macro in properties:
            macro = u_macro or 'UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")'
            props_lines.append(f"\t{macro}\n\t{p_type} {p_name};")
    else:
        props_lines.append('\tUPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")\n\tbool bRuleEnabled = true;')

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
\t// Default custom rule execution implementation
}}

void U{clean_handler}::OnEvent(const FGameForgeEvent& Event)
{{
\tSuper::OnEvent(Event);
\t// BEGIN MODEL CODE
{on_event_body}
\t// END MODEL CODE
}}

void U{clean_handler}::Tick(float DeltaSeconds)
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
