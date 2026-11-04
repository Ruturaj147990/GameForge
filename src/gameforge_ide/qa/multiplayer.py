"""Multiplayer listen server + client QA harness and consensus verifier (WI-10.4).

Executes and verifies multiplayer gameplay between a listen server and local client(s):
1. Server authority: overlaps and game rules processed on server only.
2. Client replication: stats (entity.pickups.collected) and end-game state (game.won).
3. Consensus verification: server and client scenarios must agree on outcomes and stats.
4. Process log piping: captures server and client stdout/stderr and extracts diagnostics.
"""
from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from ..core import jobs
from ..unreal.toolchain import UnrealToolchain
from .events import EventStream
from .runner import _extract_crash_diagnostics
from .scenario import Scenario, ScenarioResult


@dataclass
class NetEmulationConfig:
    packet_lag_ms: int = 100
    packet_loss_pct: int = 2

    def to_exec_cmd(self) -> str:
        return f'-ExecCmds="Net PktLag={self.packet_lag_ms},Net PktLoss={self.packet_loss_pct}"'


@dataclass
class MultiplayerConsensusResult:
    scenario_id: str
    passed: bool
    consensus: bool
    duration_s: float
    server_result: Optional[ScenarioResult] = None
    client_results: List[ScenarioResult] = field(default_factory=list)
    stats_agreement: Dict[str, Any] = field(default_factory=dict)
    failures: List[str] = field(default_factory=list)
    evidence_file: Optional[Path] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "passed": self.passed,
            "consensus": self.consensus,
            "duration_s": round(self.duration_s, 3),
            "server_passed": self.server_result.passed if self.server_result else False,
            "clients_count": len(self.client_results),
            "stats_agreement": self.stats_agreement,
            "failures": self.failures,
            "evidence_file": str(self.evidence_file) if self.evidence_file else None,
        }


class MultiplayerHarness:
    """Manages spawning, monitoring, and consensus validation for listen-server multiplayer tests."""

    def __init__(self, out_dir: Path, timeout_s: float = 120.0):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.timeout_s = timeout_s

    def run_multiplayer(
        self,
        exe: Path,
        server_scenario: Scenario,
        client_scenario: Scenario,
        map_path: str = "/Game/Maps/Level_1",
        net_emulation: Optional[NetEmulationConfig] = None,
        extra_args: Sequence[str] = (),
    ) -> MultiplayerConsensusResult:
        """Launch listen server and client processes, wait for completion, and verify consensus."""
        t0 = time.time()
        exe = Path(exe)

        server_out = self.out_dir / f"{server_scenario.scenario_id}_result.json"
        client_out = self.out_dir / f"{client_scenario.scenario_id}_result.json"
        for p in (server_out, client_out):
            if p.exists():
                p.unlink()

        server_sc_file = self.out_dir / f"{server_scenario.scenario_id}.json"
        client_sc_file = self.out_dir / f"{client_scenario.scenario_id}.json"
        server_scenario.to_file(server_sc_file)
        client_scenario.to_file(client_sc_file)

        server_events = self.out_dir / f"{server_scenario.scenario_id}_events.jsonl"
        client_events = self.out_dir / f"{client_scenario.scenario_id}_events.jsonl"

        # 1. Server arguments
        clean_map = map_path.strip().split("?")[0]
        server_url = f"{clean_map}?listen?game=/Script/GameForgeRuntime.GameForgeGameMode"
        server_argv: List[str] = [
            str(exe),
            server_url,
            f"-GFScenario={server_sc_file.resolve()}",
            f"-GFScenarioOut={server_out.resolve()}",
            f"-GFEventsOut={server_events.resolve()}",
            "-RenderOffscreen",
            "-ResX=1280",
            "-ResY=720",
            "-unattended",
            "-nosplash",
            "-nosound",
        ]
        server_argv.extend(extra_args)

        # 2. Client arguments
        client_url = "127.0.0.1"
        client_argv: List[str] = [
            str(exe),
            client_url,
            f"-GFScenario={client_sc_file.resolve()}",
            f"-GFScenarioOut={client_out.resolve()}",
            f"-GFEventsOut={client_events.resolve()}",
            "-RenderOffscreen",
            "-ResX=1280",
            "-ResY=720",
            "-unattended",
            "-nosplash",
            "-nosound",
        ]
        if net_emulation:
            client_argv.append(net_emulation.to_exec_cmd())
        client_argv.extend(extra_args)

        server_log_path = self.out_dir / f"{server_scenario.scenario_id}_stdout.log"
        client_log_path = self.out_dir / f"{client_scenario.scenario_id}_stdout.log"

        s_log = open(server_log_path, "w", encoding="utf-8", errors="replace")
        c_log = open(client_log_path, "w", encoding="utf-8", errors="replace")

        server_proc = None
        client_proc = None
        failures: List[str] = []

        try:
            try:
                server_proc = jobs.spawn(server_argv, stdout=s_log, stderr=s_log)
            except Exception as e:
                failures.append(f"Failed to spawn server: {e}")
                return MultiplayerConsensusResult(
                    scenario_id=server_scenario.scenario_id,
                    passed=False,
                    consensus=False,
                    duration_s=time.time() - t0,
                    failures=failures,
                )

            # Give server 1.5s to open listen socket
            time.sleep(1.5)

            try:
                client_proc = jobs.spawn(client_argv, stdout=c_log, stderr=c_log)
            except Exception as e:
                failures.append(f"Failed to spawn client: {e}")
                UnrealToolchain.kill_tree(server_proc)
                return MultiplayerConsensusResult(
                    scenario_id=server_scenario.scenario_id,
                    passed=False,
                    consensus=False,
                    duration_s=time.time() - t0,
                    failures=failures,
                )

            # Wait for client to complete (client executes user inputs)
            try:
                client_proc.wait(timeout=self.timeout_s)
            except Exception as exc:
                failures.append(f"Client TIMEOUT after {self.timeout_s}s ({exc})")

            # Allow server brief grace period to process final client disconnect
            try:
                server_proc.wait(timeout=10.0)
            except Exception:
                pass

        finally:
            if client_proc:
                UnrealToolchain.kill_tree(client_proc)
            if server_proc:
                UnrealToolchain.kill_tree(server_proc)
            s_log.close()
            c_log.close()

        # Load results
        server_res = ScenarioResult.from_file(server_out) if server_out.is_file() else ScenarioResult(
            schema="scenario_result/1",
            scenario_id=server_scenario.scenario_id,
            passed=False,
            failures=[f"SERVER_NO_RESULT: {_extract_crash_diagnostics(exe, server_log_path, None)}"],
        )

        client_res = ScenarioResult.from_file(client_out) if client_out.is_file() else ScenarioResult(
            schema="scenario_result/1",
            scenario_id=client_scenario.scenario_id,
            passed=False,
            failures=[f"CLIENT_NO_RESULT: {_extract_crash_diagnostics(exe, client_log_path, None)}"],
        )

        # Check consensus
        s_stream = EventStream.from_file(server_events)
        c_stream = EventStream.from_file(client_events)

        s_won = s_stream.count("game.won") > 0
        c_won = c_stream.count("game.won") > 0
        s_pickups = s_stream.count("pickup.collected")
        c_pickups = c_stream.count("pickup.collected")

        consensus_agreed = (s_won == c_won) and (s_pickups == c_pickups)
        overall_passed = server_res.passed and client_res.passed and consensus_agreed

        if not consensus_agreed:
            failures.append(
                f"Multiplayer consensus mismatch: server(won={s_won}, pickups={s_pickups}) != client(won={c_won}, pickups={c_pickups})"
            )

        duration = round(time.time() - t0, 3)
        evidence_file = self.out_dir / "multiplayer.json"
        result = MultiplayerConsensusResult(
            scenario_id=server_scenario.scenario_id,
            passed=overall_passed,
            consensus=consensus_agreed,
            duration_s=duration,
            server_result=server_res,
            client_results=[client_res],
            stats_agreement={
                "server_won": s_won,
                "client_won": c_won,
                "server_pickups": s_pickups,
                "client_pickups": c_pickups,
            },
            failures=failures,
            evidence_file=evidence_file,
        )

        evidence_file.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
        return result
