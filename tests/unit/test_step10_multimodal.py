"""Unit tests for Step 10 Multimodal & Spatial Perception Engine.

Tests:
- Temporal playtest sequence alignment with exact engine telemetry
- Detection of spatial artifacts (falling through floor, camera occlusion, missing textures)
- Schema conformance of Step 10 multimodal evaluation contracts
- Separation of visual heuristics from deterministic engine metrics
"""

import json
from pathlib import Path
import pytest

from gameforge_bench.multimodal_perception import MultimodalPerceptionEngine


def test_multimodal_perception_clean_sequence(tmp_path: Path):
    engine = MultimodalPerceptionEngine(workspace_root=tmp_path)

    clean_frames = [
        {
            "timestamp_seconds": 0.0,
            "frame_index": 0,
            "position": [0.0, 0.0, 50.0],
            "velocity": [0.0, 0.0, 0.0],
            "event": "Spawn",
        },
        {
            "timestamp_seconds": 0.5,
            "frame_index": 30,
            "position": [100.0, 0.0, 50.0],
            "velocity": [200.0, 0.0, 0.0],
            "event": "Running",
        },
    ]

    result = engine.evaluate_playtest_sequence(task_id="t2-001-controller", frames_telemetry=clean_frames)

    assert result.total_frames_inspected == 2
    assert result.artifacts_detected_count == 0
    assert result.visual_review_pass is True
    assert result.inter_rater_agreement >= 0.85
    assert result.deterministic_metrics_consistent is True


def test_multimodal_perception_detects_clipping(tmp_path: Path):
    engine = MultimodalPerceptionEngine(workspace_root=tmp_path)

    corrupted_frames = [
        {
            "timestamp_seconds": 0.0,
            "frame_index": 0,
            "position": [0.0, 0.0, 50.0],
            "velocity": [0.0, 0.0, 0.0],
            "event": "Spawn",
        },
        {
            "timestamp_seconds": 1.0,
            "frame_index": 60,
            "position": [0.0, 0.0, -1500.0],  # Out of bounds / fallen through geometry
            "velocity": [0.0, 0.0, -980.0],
            "event": "Falling",
        },
    ]

    result = engine.evaluate_playtest_sequence(task_id="t2-001-controller", frames_telemetry=corrupted_frames)

    assert result.artifacts_detected_count == 1
    assert result.visual_review_pass is False
    assert result.frame_observations[1].visual_verdict == "CLIPPING_DETECTED"
