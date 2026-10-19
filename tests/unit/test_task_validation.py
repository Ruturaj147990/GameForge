"""Unit tests for task validation, inventory checks, and discrepancy detection."""

from pathlib import Path
from gameforge_bench.task_validation import (
    validate_all_specs,
    validate_inventory_file,
    validate_single_task_spec,
)


def test_validate_all_existing_specs():
    result = validate_all_specs(Path.cwd())
    assert result.is_valid is True, f"Expected validation to pass, found errors: {result.errors}"
    assert result.total_inventory_tasks == 30
    assert result.total_specs_checked == 6
    assert len(result.errors) == 0
    # Provenance warnings should be present
    assert len(result.warnings) >= 6
    # T3-016 pilot discrepancy should be detected
    discrepancy_fields = [d.field_name for d in result.discrepancies]
    assert "T3-016.pilot" in discrepancy_fields


def test_detect_duplicate_inventory_ids(tmp_path):
    dup_csv = tmp_path / "dup_inventory.csv"
    dup_csv.write_text(
        "id,tier,title,category,engine_pairing,primary_grading,pilot,notes\n"
        "T2-001,T2,Task One,gameplay,paired,tests,yes,notes\n"
        "T2-001,T2,Duplicate Task,gameplay,paired,tests,yes,notes\n",
        encoding="utf-8",
    )
    issues = validate_inventory_file(dup_csv)
    errs = [i for i in issues if i.severity == "ERROR"]
    assert any("Duplicate" in e.message for e in errs)


def test_detect_invalid_tier_and_category(tmp_path):
    bad_csv = tmp_path / "bad_inventory.csv"
    bad_csv.write_text(
        "id,tier,title,category,engine_pairing,primary_grading,pilot,notes\n"
        "T9-999,T9,Invalid Tier Task,nonexistent_category,paired,tests,no,notes\n",
        encoding="utf-8",
    )
    issues = validate_inventory_file(bad_csv)
    errs = [i for i in issues if i.severity == "ERROR"]
    assert any("Invalid tier" in e.message for e in errs)
    assert any("Invalid category" in e.message for e in errs)
