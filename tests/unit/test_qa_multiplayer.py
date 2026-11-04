"""Unit tests for multiplayer listen-server + client harness and consensus verification (WI-10.4)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.gameforge_ide.qa.multiplayer import (
    MultiplayerConsensusResult,
    MultiplayerHarness,
    NetEmulationConfig,
)
from src.gameforge_ide.qa.scenario import Scenario, ScenarioResult


def test_net_emulation_config_args():
    cfg = NetEmulationConfig(packet_lag_ms=100, packet_loss_pct=2)
    assert '-ExecCmds="Net PktLag=100,Net PktLoss=2"' == cfg.to_exec_cmd()


def test_multiplayer_harness_consensus_pass(tmp_path: Path):
    harness = MultiplayerHarness(out_dir=tmp_path / "mp_qa", timeout_s=5.0)
    server_sc = Scenario(scenario_id="server_test", steps=[], expect=[])
    client_sc = Scenario(scenario_id="client_test", steps=[], expect=[])

    # Pre-write successful scenario results and events for consensus
    out_dir = tmp_path / "mp_qa"
    out_dir.mkdir(parents=True, exist_ok=True)

    s_res = ScenarioResult(schema="scenario_result/1", scenario_id="server_test", passed=True)
    c_res = ScenarioResult(schema="scenario_result/1", scenario_id="client_test", passed=True)
    (out_dir / "server_test_result.json").write_text(s_res.model_dump_json(by_alias=True), encoding="utf-8")
    (out_dir / "client_test_result.json").write_text(c_res.model_dump_json(by_alias=True), encoding="utf-8")

    events = (
        '{"e": "pickup.collected", "t": 1.0}\n'
        '{"e": "pickup.collected", "t": 2.0}\n'
        '{"e": "pickup.collected", "t": 3.0}\n'
        '{"e": "game.won", "t": 3.5}\n'
    )

    mock_proc = MagicMock()
    mock_proc.wait.return_value = 0

    def _mock_spawn(argv, stdout=None, stderr=None):
        # Simulate engine writing result and event files
        (out_dir / "server_test_result.json").write_text(s_res.model_dump_json(by_alias=True), encoding="utf-8")
        (out_dir / "client_test_result.json").write_text(c_res.model_dump_json(by_alias=True), encoding="utf-8")
        (out_dir / "server_test_events.jsonl").write_text(events, encoding="utf-8")
        (out_dir / "client_test_events.jsonl").write_text(events, encoding="utf-8")
        return mock_proc

    with patch("src.gameforge_ide.core.jobs.spawn", side_effect=_mock_spawn):
        with patch("time.sleep"):  # skip the 1.5s delay
            res = harness.run_multiplayer(
                exe=tmp_path / "Game.exe",
                server_scenario=server_sc,
                client_scenario=client_sc,
                net_emulation=NetEmulationConfig(),
            )

            assert res.passed is True
            assert res.consensus is True
            assert res.stats_agreement["server_pickups"] == 3
            assert res.stats_agreement["client_pickups"] == 3
            assert res.stats_agreement["server_won"] is True
            assert res.evidence_file.is_file()


def test_multiplayer_harness_consensus_mismatch_detected(tmp_path: Path):
    harness = MultiplayerHarness(out_dir=tmp_path / "mp_qa", timeout_s=5.0)
    server_sc = Scenario(scenario_id="server_test", steps=[], expect=[])
    client_sc = Scenario(scenario_id="client_test", steps=[], expect=[])

    out_dir = tmp_path / "mp_qa"
    out_dir.mkdir(parents=True, exist_ok=True)

    s_res = ScenarioResult(schema="scenario_result/1", scenario_id="server_test", passed=True)
    c_res = ScenarioResult(schema="scenario_result/1", scenario_id="client_test", passed=True)
    (out_dir / "server_test_result.json").write_text(s_res.model_dump_json(by_alias=True), encoding="utf-8")
    (out_dir / "client_test_result.json").write_text(c_res.model_dump_json(by_alias=True), encoding="utf-8")

    mock_proc = MagicMock()
    mock_proc.wait.return_value = 0

    def _mock_spawn(argv, stdout=None, stderr=None):
        (out_dir / "server_test_result.json").write_text(s_res.model_dump_json(by_alias=True), encoding="utf-8")
        (out_dir / "client_test_result.json").write_text(c_res.model_dump_json(by_alias=True), encoding="utf-8")
        # Mismatch: server recorded 3 pickups, client only recorded 2!
        (out_dir / "server_test_events.jsonl").write_text('{"e": "pickup.collected"}\n' * 3 + '{"e": "game.won"}\n', encoding="utf-8")
        (out_dir / "client_test_events.jsonl").write_text('{"e": "pickup.collected"}\n' * 2 + '{"e": "game.won"}\n', encoding="utf-8")
        return mock_proc

    with patch("src.gameforge_ide.core.jobs.spawn", side_effect=_mock_spawn):
        with patch("time.sleep"):
            res = harness.run_multiplayer(
                exe=tmp_path / "Game.exe",
                server_scenario=server_sc,
                client_scenario=client_sc,
            )

            assert res.consensus is False
            assert res.passed is False
            assert any("consensus mismatch" in f for f in res.failures)
