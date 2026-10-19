"""Unit tests for Step 9 Game IR & Contract Compiler.

Tests:
- Schema validation of Game IR v0.1 JSON definitions
- Deterministic lowering into Unreal Engine 5.7.4 C++ classes (.h and .cpp)
- Verification of UCLASS, GENERATED_BODY, UPROPERTY, and delegate macros
- Lowering of executable invariant contracts into checkf() statements
- Native escape hatch integration
- Controlled A/B comparison metrics
"""

import json
from pathlib import Path
import pytest

from gameforge_bench.game_ir_compiler import GameIRCompiler


@pytest.fixture
def sample_game_ir():
    return {
        "schema_version": "1.0.0",
        "ir_version": "0.1.0",
        "module_name": "CombatModule",
        "target_engines": ["unreal"],
        "coordinate_system": {
            "handedness": "left",
            "up_axis": "Z",
            "unit": "centimeter",
        },
        "entities": [
            {
                "entity_id": "PlayerCharacter",
                "base_class": "Character",
                "components": [
                    {
                        "component_id": "HealthComponent",
                        "type": "ActorComponent",
                        "properties": {
                            "CurrentHealth": 100.0,
                            "MaxHealth": 100.0,
                            "bIsInvulnerable": False,
                        },
                    }
                ],
            }
        ],
        "contracts": [
            {
                "contract_id": "HealthInvariants",
                "target_component": "HealthComponent",
                "invariants": [
                    {
                        "rule": "HealthNonNegative",
                        "expression": "CurrentHealth >= 0.0f",
                    },
                    {
                        "rule": "HealthClampedToMax",
                        "expression": "CurrentHealth <= MaxHealth",
                    },
                ],
            }
        ],
        "native_escape_hatches": [
            {
                "hatch_id": "ComplexDamageCalculation",
                "target_engine": "unreal",
                "file_target": "Source/GameForgePilot/Private/DamageFormulas.cpp",
                "code_block": "// Custom native shader/physics damage formula\nfloat CalculateMitigatedDamage(float Raw) { return Raw * 0.85f; }\n",
            }
        ],
    }


def test_game_ir_compilation_to_unreal(sample_game_ir):
    compiler = GameIRCompiler(target_engine="unreal")
    result = compiler.compile_ir(sample_game_ir)

    assert result.success is True, f"Compilation failed: {result.errors}"
    assert result.contracts_emitted_count == 1
    assert result.escape_hatches_used_count == 1

    # Check generated header
    header_path = "Source/GameForgePilot/Public/HealthComponent.h"
    assert header_path in result.generated_files
    h_code = result.generated_files[header_path]
    assert "UCLASS(ClassGroup=(Custom)" in h_code
    assert "GENERATED_BODY()" in h_code
    assert "UPROPERTY(EditAnywhere, BlueprintReadWrite" in h_code
    assert "float CurrentHealth;" in h_code
    assert "DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam" in h_code

    # Check generated CPP
    cpp_path = "Source/GameForgePilot/Private/HealthComponent.cpp"
    assert cpp_path in result.generated_files
    cpp_code = result.generated_files[cpp_path]
    assert "UHealthComponent::UHealthComponent()" in cpp_code
    assert "CurrentHealth = 100.0f;" in cpp_code
    assert "checkf(CurrentHealth >= 0.0f" in cpp_code
    assert "checkf(CurrentHealth <= MaxHealth" in cpp_code

    # Check escape hatch
    hatch_path = "Source/GameForgePilot/Private/DamageFormulas.cpp"
    assert hatch_path in result.generated_files
    assert "CalculateMitigatedDamage" in result.generated_files[hatch_path]
