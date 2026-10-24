"""Regression tests for GameForge evaluation harness fixes (Phase B).

Validates:
1. Reconciled delta counting and arithmetic integrity (prevents '3 tasks improved' vs 4 tasks table mismatch).
2. Code block extraction and syntax completeness (bracket balance, non-empty code).
3. Truncation detection and finish reason analysis.
4. Whitespace and normalization tolerance in rubric matching.
5. Deprecation / API version violation detection.
"""

import re
import pytest


def calculate_task_deltas(baseline_scores: dict[str, float], candidate_scores: dict[str, float]) -> dict:
    """Calculates per-task deltas, total points delta, and counts improved/regressed/unchanged tasks."""
    improved = 0
    regressed = 0
    unchanged = 0
    deltas = {}
    total_delta = 0.0

    for task_id, b_score in baseline_scores.items():
        c_score = candidate_scores.get(task_id, 0.0)
        delta = c_score - b_score
        deltas[task_id] = delta
        total_delta += delta
        if delta > 0.001:
            improved += 1
        elif delta < -0.001:
            regressed += 1
        else:
            unchanged += 1

    return {
        "improved_count": improved,
        "regressed_count": regressed,
        "unchanged_count": unchanged,
        "total_delta": round(total_delta, 2),
        "per_task_deltas": deltas,
    }


def extract_code_blocks(text: str) -> list[str]:
    """Extracts code blocks from markdown fences; falls back to raw text if no fences."""
    matches = re.findall(r"```(?:[a-zA-Z0-9_\+\#]+)?\s*\n(.*?)```", text, re.DOTALL)
    if matches:
        return [m.strip() for m in matches if m.strip()]
    return [text.strip()]


def check_syntax_balance(code: str) -> bool:
    """Checks for balanced braces, brackets, and parentheses in code."""
    stack = []
    pairs = {"{": "}", "[": "]", "(": ")"}
    for char in code:
        if char in pairs:
            stack.append(pairs[char])
        elif char in pairs.values():
            if not stack or stack.pop() != char:
                return False
    return len(stack) == 0


def match_rubric_normalized(text: str, rubric_item: str) -> bool:
    """Matches rubric item with whitespace and punctuation normalization."""
    # Split rubric item into tokens (words and punctuation)
    tokens = re.findall(r"\w+|[^\w\s]", rubric_item.lower())
    if not tokens:
        return False
    # Build regex allowing optional whitespace between tokens
    pattern_parts = []
    for token in tokens:
        pattern_parts.append(re.escape(token))
    pattern = r"\s*".join(pattern_parts)
    return bool(re.search(pattern, text.lower()))


def check_api_violations(text: str, engine: str = "ue5.7") -> list[str]:
    """Detects obsolete or deprecated patterns."""
    violations = []
    if engine == "ue5.7":
        # Check for raw UObject pointer member variable declarations
        if re.search(r"UPROPERTY\s*\([^)]*\)\s*U[A-Z][a-zA-Z0-9_]*\s*\*\s*[a-zA-Z0-9_]+;", text):
            violations.append("Raw UObject pointer in UPROPERTY (should use TObjectPtr<T> in UE 5.7)")
    return violations


# --- TESTS ---

def test_arithmetic_discrepancy_fix():
    """Verifies that 4 improving tasks are reported as 4, resolving the Phase B discrepancy."""
    baseline = {
        "TASK-01": 4.0,
        "TASK-02": 1.0,
        "TASK-03": 6.0,
        "TASK-04": 0.0,
        "TASK-05": 0.0,
        "TASK-06": 7.0,
        "TASK-07": 3.0,
        "TASK-08": 0.0,
    }
    candidate = {
        "TASK-01": 4.0,
        "TASK-02": 10.0,  # +9
        "TASK-03": 7.0,   # +1
        "TASK-04": 0.0,   # +0
        "TASK-05": 10.0,  # +10
        "TASK-06": 7.0,   # +0
        "TASK-07": 3.0,   # +0
        "TASK-08": 10.0,  # +10
    }
    result = calculate_task_deltas(baseline, candidate)
    assert result["improved_count"] == 4, f"Expected 4 improved tasks, got {result['improved_count']}"
    assert result["regressed_count"] == 0
    assert result["unchanged_count"] == 4
    assert result["total_delta"] == 30.0


def test_code_block_extraction():
    """Verifies code extraction isolates implementation from conversational preamble."""
    markdown_output = (
        "Here is the implementation of the weapon component in Unreal Engine 5.7:\n\n"
        "```cpp\n"
        "UCLASS()\n"
        "class AWeapon : public AActor {\n"
        "    GENERATED_BODY()\n"
        "};\n"
        "```\n\n"
        "Let me know if you need any adjustments!"
    )
    blocks = extract_code_blocks(markdown_output)
    assert len(blocks) == 1
    assert "Here is the implementation" not in blocks[0]
    assert "class AWeapon" in blocks[0]


def test_syntax_balance_check():
    """Verifies syntax balance catches truncated or malformed code."""
    valid_code = "void Test() { if (true) { DoWork(); } }"
    truncated_code = "void Test() { if (true) { DoWork();"
    assert check_syntax_balance(valid_code) is True
    assert check_syntax_balance(truncated_code) is False


def test_rubric_normalization_matching():
    """Verifies whitespace-insensitive matching for engine invariants."""
    code_variant1 = "PrimaryActorTick.bCanEverTick = false;"
    code_variant2 = "PrimaryActorTick.bCanEverTick=false;"
    code_variant3 = "PrimaryActorTick.bCanEverTick  =  false;"
    
    assert match_rubric_normalized(code_variant1, "bCanEverTick = false") is True
    assert match_rubric_normalized(code_variant2, "bCanEverTick = false") is True
    assert match_rubric_normalized(code_variant3, "bCanEverTick = false") is True


def test_ue57_api_deprecation_check():
    """Verifies detection of deprecated raw UObject pointers in UE 5.7 UPROPERTY."""
    deprecated_code = "UPROPERTY(EditAnywhere) UStaticMesh* MeshComponent;"
    modern_code = "UPROPERTY(EditAnywhere) TObjectPtr<UStaticMesh> MeshComponent;"
    
    assert len(check_api_violations(deprecated_code, "ue5.7")) == 1
    assert len(check_api_violations(modern_code, "ue5.7")) == 0
