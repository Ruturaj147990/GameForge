"""Comprehensive unit tests for atomic file operations and crash-resilient storage."""
from __future__ import annotations

import json
import os
import stat
import time
from pathlib import Path
import pytest

from src.gameforge_ide.storage.atomic import (
    atomic_write,
    atomic_write_text,
    atomic_write_json,
    safe_read_text,
    safe_read_json,
    sweep_dangling_temp_files,
)


def test_atomic_write_binary_and_parents(tmp_path: Path):
    target = tmp_path / "deep" / "sub" / "file.bin"
    payload = b"\x00\x01\x02\x03\xff"
    res = atomic_write(target, payload, make_parents=True, sync=True)
    assert res == target
    assert target.is_file()
    assert target.read_bytes() == payload


def test_atomic_write_text_and_json(tmp_path: Path):
    txt_file = tmp_path / "test.txt"
    atomic_write_text(txt_file, "Hello GameForge Atomic", sync=True)
    assert txt_file.read_text(encoding="utf-8") == "Hello GameForge Atomic"

    json_file = tmp_path / "data.json"
    obj = {"project": "UnrealGame", "version": 1, "items": ["a", "b"]}
    atomic_write_json(json_file, obj, sync=True, backup=True)
    assert json_file.is_file()
    assert json.loads(json_file.read_text(encoding="utf-8")) == obj

    # Verified .bak was generated
    bak_file = json_file.with_suffix(".json.bak")
    assert bak_file.is_file()
    assert json.loads(bak_file.read_text(encoding="utf-8")) == obj


def test_safe_read_json_corruption_recovery(tmp_path: Path):
    target = tmp_path / "recover.json"
    original = {"status": "ok", "run_id": "run_12345"}
    atomic_write_json(target, original, backup=True, sync=True)

    # Corrupt primary file
    target.write_text("CORRUPTED JSON TRUNCATED {", encoding="utf-8")

    # Read should self-heal and recover from .bak
    data, recovered = safe_read_json(target, fallback_backup=True)
    assert recovered is True
    assert data == original

    # Primary file should now be restored
    assert json.loads(target.read_text(encoding="utf-8")) == original


def test_atomic_write_readonly_clearance(tmp_path: Path):
    target = tmp_path / "locked.txt"
    atomic_write_text(target, "Version 1")
    assert target.read_text(encoding="utf-8") == "Version 1"

    # Set file to read-only (Windows write lock simulation)
    os.chmod(target, stat.S_IREAD)

    # atomic_write must clear read-only flag and overwrite successfully
    atomic_write_text(target, "Version 2 Overwritten")
    assert target.read_text(encoding="utf-8") == "Version 2 Overwritten"


def test_sweep_dangling_temp_files(tmp_path: Path):
    dangling_1 = tmp_path / ".temp_abc.tmp"
    dangling_2 = tmp_path / "test.tmp_1234"
    valid_file = tmp_path / "real.json"

    dangling_1.write_text("abandoned 1")
    dangling_2.write_text("abandoned 2")
    valid_file.write_text("{}")

    # Artificially age the temporary files
    old_time = time.time() - 7200
    os.utime(dangling_1, (old_time, old_time))
    os.utime(dangling_2, (old_time, old_time))

    removed = sweep_dangling_temp_files(tmp_path, max_age_seconds=3600.0)
    assert len(removed) >= 2
    assert not dangling_1.exists()
    assert not dangling_2.exists()
    assert valid_file.exists()
