"""GameForge Step 9 Game IR & Executable Contract Compiler.

Implements Section 6 and Section 28.6 (Step 9 Gate — Game IR choice):
- Parses and statically validates Game IR v0.1 JSON definitions.
- Deterministic lowering into Unreal Engine 5.7.4 C++ component pairs (.h/.cpp).
- Generates native reflection macros (UCLASS, UPROPERTY, GENERATED_BODY).
- Preserves executable contracts as runtime validation probes and asserts.
- Supports native escape hatches for complex physics and shaders.
- Enables controlled A/B experiment comparing Direct Generation vs. IR Compiler.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class CompilationResult:
    success: bool
    generated_files: Dict[str, str] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    contracts_emitted_count: int = 0
    escape_hatches_used_count: int = 0


class GameIRCompiler:
    """Compiles Game IR v0.1 definitions into native engine source files."""

    def __init__(self, target_engine: str = "unreal") -> None:
        self.target_engine = target_engine.lower()

    def compile_ir(self, ir_data: Dict[str, Any]) -> CompilationResult:
        errors: List[str] = []
        files: Dict[str, str] = {}
        contracts_count = 0
        escape_hatches_count = 0

        # Validate basic schema
        for req in ["schema_version", "ir_version", "module_name", "entities", "contracts"]:
            if req not in ir_data:
                errors.append(f"Missing required Game IR field: '{req}'")

        if errors:
            return CompilationResult(success=False, errors=errors)

        entities = ir_data.get("entities", [])
        contracts = {c["target_component"]: c for c in ir_data.get("contracts", [])}
        contracts_count = len(contracts)

        for entity in entities:
            entity_id = entity.get("entity_id", "DefaultEntity")
            components = entity.get("components", [])

            for comp in components:
                comp_id = comp.get("component_id", "GameplayComponent")
                comp_type = comp.get("type", "ActorComponent")
                props = comp.get("properties", {})

                if self.target_engine == "unreal":
                    h_code, cpp_code = self._lower_to_unreal(comp_id, comp_type, props, contracts.get(comp_id))
                    files[f"Source/GameForgePilot/Public/{comp_id}.h"] = h_code
                    files[f"Source/GameForgePilot/Private/{comp_id}.cpp"] = cpp_code
                elif self.target_engine == "unity":
                    cs_code = self._lower_to_unity(comp_id, props, contracts.get(comp_id))
                    files[f"Assets/Scripts/{comp_id}.cs"] = cs_code
                else:
                    errors.append(f"Unsupported target engine: {self.target_engine}")

        # Native escape hatches
        hatches = ir_data.get("native_escape_hatches", [])
        for h in hatches:
            if h.get("target_engine") == self.target_engine:
                dest = h.get("file_target", f"Source/GameForgePilot/Private/{h.get('hatch_id')}.cpp")
                files[dest] = h.get("code_block", "")
                escape_hatches_count += 1

        return CompilationResult(
            success=len(errors) == 0,
            generated_files=files,
            errors=errors,
            contracts_emitted_count=contracts_count,
            escape_hatches_used_count=escape_hatches_count,
        )

    def _lower_to_unreal(
        self,
        comp_id: str,
        comp_type: str,
        props: Dict[str, Any],
        contract: Optional[Dict[str, Any]],
    ) -> Tuple[str, str]:
        """Lowers component properties and contracts into native Unreal C++."""
        class_name = f"U{comp_id}"
        header = f"""// GameForge Game IR Lowered Component: {class_name}
#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "{comp_id}.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOn{comp_id}StateChanged, float, NewValue);

UCLASS(ClassGroup=(Custom), meta=(BlueprintSpawnableComponent))
class GAMEFORGEPILOT_API {class_name} : public UActorComponent
{{
\tGENERATED_BODY()

public:
\t{class_name}();

protected:
\tvirtual void BeginPlay() override;

public:
"""
        # Properties
        for prop_name, prop_val in props.items():
            prop_type = "float" if isinstance(prop_val, (int, float)) else "bool"
            header += f"\tUPROPERTY(EditAnywhere, BlueprintReadWrite, Category = \"GameForge\")\n"
            header += f"\t{prop_type} {prop_name};\n\n"

        header += f"\tUPROPERTY(BlueprintAssignable, Category = \"GameForge\")\n"
        header += f"\tFOn{comp_id}StateChanged On{comp_id}Changed;\n\n"
        header += f"\tUFUNCTION(BlueprintCallable, Category = \"GameForge\")\n"
        header += f"\tvoid ValidateContracts();\n"
        header += "};\n"

        # C++ Implementation
        cpp = f"""// GameForge Game IR Lowered Component Implementation: {comp_id}
#include "{comp_id}.h"

{class_name}::{class_name}()
{{
\tPrimaryComponentTick.bCanEverTick = false;
"""
        for prop_name, prop_val in props.items():
            if isinstance(prop_val, float):
                cpp += f"\t{prop_name} = {prop_val}f;\n"
            elif isinstance(prop_val, bool):
                cpp += f"\t{prop_name} = {'true' if prop_val else 'false'};\n"
            else:
                cpp += f"\t{prop_name} = {prop_val};\n"

        cpp += f"}}\n\nvoid {class_name}::BeginPlay()\n{{\n\tSuper::BeginPlay();\n\tValidateContracts();\n}}\n\n"
        cpp += f"void {class_name}::ValidateContracts()\n{{\n"

        # Invariant checks from contracts
        if contract:
            for inv in contract.get("invariants", []):
                rule = inv.get("rule", "Invariant")
                expr = inv.get("expression", "true")
                cpp += f"\t// Contract: {rule}\n"
                cpp += f"\tcheckf({expr}, TEXT(\"Contract violation: {rule}\"));\n"

        cpp += "}\n"
        return header, cpp

    def _lower_to_unity(
        self,
        comp_id: str,
        props: Dict[str, Any],
        contract: Optional[Dict[str, Any]],
    ) -> str:
        code = f"""using System;
using UnityEngine;

namespace GameForge.Gameplay
{{
    public class {comp_id} : MonoBehaviour
    {{
"""
        for prop_name, prop_val in props.items():
            prop_type = "float" if isinstance(prop_val, (int, float)) else "bool"
            code += f"        [SerializeField] private {prop_type} {prop_name};\n"

        code += "\n        private void Awake()\n        {\n            ValidateContracts();\n        }\n\n"
        code += "        public void ValidateContracts()\n        {\n"
        if contract:
            for inv in contract.get("invariants", []):
                rule = inv.get("rule", "Invariant")
                expr = inv.get("expression", "true")
                code += f"            Debug.Assert({expr}, \"Contract violation: {rule}\");\n"
        code += "        }\n    }\n}\n"
        return code
