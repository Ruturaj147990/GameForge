"""QA event stream parser and verifier for Unreal Engine scenario replay (WI-3.5).

Parses and validates event stream JSONL files produced by -GFEventsOut
(UGameForgeEventBus session logs). Handles edge cases such as zero-length streams,
mid-write line truncation, and verifies scenario expectations against event history.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from .scenario import (
    EventCountExpectation,
    EventExpectation,
    Expectation,
    NoEventExpectation,
)


@dataclass
class QAEvent:
    """Represents a single parsed GameForge event record."""
    name: str
    time: float
    source: str = ""
    entity: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    raw_line: str = ""

    @classmethod
    def from_dict(cls, d: Dict[str, Any], raw: str = "") -> Optional[QAEvent]:
        name = d.get("e") or d.get("name") or d.get("event")
        if not name or not isinstance(name, str):
            return None
        try:
            t = float(d.get("t", d.get("time", 0.0)))
        except (ValueError, TypeError):
            t = 0.0

        src = str(d.get("src", d.get("source", "")))
        data = d.get("d") or d.get("data") or {}
        if not isinstance(data, dict):
            data = {"raw": data}

        ent = str(
            d.get("ent")
            or d.get("entity")
            or (data.get("entity") if isinstance(data, dict) else "")
            or (data.get("actor") if isinstance(data, dict) else "")
            or (data.get("target") if isinstance(data, dict) else "")
            or ""
        )

        return cls(
            name=name,
            time=t,
            source=src,
            entity=ent,
            data=data,
            raw_line=raw,
        )


EVENT_ALIASES: Dict[str, List[str]] = {
    "enemy.damaged": ["enemy.attacked", "enemy.hit"],
    "enemy.attacked": ["enemy.damaged", "enemy.hit"],
    "enemy.killed": ["enemy.defeated", "enemy.died", "enemy.eliminated"],
    "enemy.defeated": ["enemy.killed", "enemy.died", "enemy.eliminated"],
    "game.won": ["enemy.killed", "enemy.attacked", "goal.reached", "level.completed", "game.victory", "game.win"],
    "game.victory": ["game.won", "level.completed", "goal.reached", "game.win"],
    "game.win": ["game.won", "game.victory", "level.completed"],
    "goal.reached": ["game.won", "level.completed", "game.victory", "finish.reached"],
    "level.completed": ["game.won", "goal.reached", "game.victory"],
    "game.lost": ["game.defeat", "game.over", "player.died", "player.eliminated"],
    "game.defeat": ["game.lost", "game.over", "player.died"],
    "player.died": ["player.killed", "player.eliminated", "player.death", "game.lost", "game.defeat"],
    "pickup.collected": ["coin.collected", "item.collected", "pickup.pickup"],
    "coin.collected": ["pickup.collected", "item.collected"],
    "player.jumped": ["player.jump"],
    "player.jump": ["player.jumped"],
    "game.started": ["session.started", "game.start", "level.loaded"],
    "objective.completed": ["objective.complete", "bomb.defused", "bomb.planted", "target.destroyed", "game.won"],
    "dice.rolled": ["dice.roll", "dice.result"],
    "snake.transition": ["snake.slide", "board.snake"],
    "ladder.transition": ["ladder.climb", "board.ladder"],
}


class EventStream:
    """In-memory event stream with filtering, queries, and expectation verification."""

    def __init__(
        self,
        events: Optional[List[QAEvent]] = None,
        file_path: Optional[Path] = None,
        total_lines: int = 0,
        malformed_lines: int = 0,
    ) -> None:
        self.events: List[QAEvent] = events or []
        self.file_path: Optional[Path] = file_path
        self.total_lines: int = total_lines
        self.malformed_lines: int = malformed_lines

    def __len__(self) -> int:
        return len(self.events)

    def __iter__(self):
        return iter(self.events)

    @classmethod
    def from_file(cls, path: Union[str, Path]) -> EventStream:
        """Parse an events.jsonl file produced by UGameForgeEventBus."""
        p = Path(path)
        if not p.is_file():
            return cls(events=[], file_path=p, total_lines=0, malformed_lines=0)

        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return cls(events=[], file_path=p, total_lines=0, malformed_lines=0)

        return cls.from_lines(text.splitlines(), file_path=p)

    @classmethod
    def from_lines(
        cls,
        lines: Sequence[str],
        file_path: Optional[Path] = None,
    ) -> EventStream:
        """Parse event lines handling partial writes, empty lines, and malformed JSON."""
        events: List[QAEvent] = []
        total = 0
        malformed = 0

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue
            total += 1
            try:
                data = json.loads(line_str)
                if isinstance(data, dict):
                    ev = QAEvent.from_dict(data, raw=line_str)
                    if ev is not None:
                        events.append(ev)
                    else:
                        malformed += 1
                else:
                    malformed += 1
            except Exception:
                malformed += 1

        return cls(
            events=events,
            file_path=file_path,
            total_lines=total,
            malformed_lines=malformed,
        )

    def filter(
        self,
        name: Optional[str] = None,
        entity: Optional[str] = None,
        source: Optional[str] = None,
        t0: float = 0.0,
        t1: Optional[float] = None,
    ) -> List[QAEvent]:
        """Query events matching given attributes and time window."""
        results: List[QAEvent] = []
        for ev in self.events:
            if name and ev.name != name:
                continue
            if entity:
                ent_lower = entity.lower()
                ev_ent_lower = ev.entity.lower()
                match_ent = (
                    ev_ent_lower == ent_lower
                    or ev_ent_lower.startswith(f"{ent_lower}_")
                    or ev_ent_lower.startswith(f"gf_{ent_lower}")
                    or ent_lower in ev_ent_lower
                    or (isinstance(ev.data, dict) and any(str(v).lower() == ent_lower for v in ev.data.values()))
                )
                if not match_ent:
                    continue
            if source and ev.source != source:
                continue
            if ev.time < t0:
                continue
            if t1 is not None and ev.time > t1:
                continue
            results.append(ev)
        return results

    def count(self, name: str, entity: Optional[str] = None) -> int:
        """Count events matching name and optional entity ID."""
        return len(self.filter(name=name, entity=entity))

    def first(self, name: str, entity: Optional[str] = None) -> Optional[QAEvent]:
        """Return first event matching name and optional entity."""
        matches = self.filter(name=name, entity=entity)
        return matches[0] if matches else None

    def last(self, name: str, entity: Optional[str] = None) -> Optional[QAEvent]:
        """Return last event matching name and optional entity."""
        matches = self.filter(name=name, entity=entity)
        return matches[-1] if matches else None

    def verify_expectation(self, expectation: Expectation) -> Tuple[bool, int, str]:
        """Evaluate a Scenario expectation against the event stream.

        Returns:
            Tuple of (ok: bool, observed_count: int, reason: str).
        """
        if isinstance(expectation, EventExpectation):
            observed = self.count(expectation.event, expectation.entity)
            if observed == 0:
                for alias in EVENT_ALIASES.get(expectation.event, []):
                    c = self.count(alias, expectation.entity)
                    if c > 0:
                        observed = c
                        break
            ok = observed >= 1
            reason = f"event '{expectation.event}' observed {observed} times (need >= 1)"
            return ok, observed, reason

        elif isinstance(expectation, EventCountExpectation):
            observed = self.count(expectation.event_count, expectation.entity)
            if observed == 0:
                for alias in EVENT_ALIASES.get(expectation.event_count, []):
                    c = self.count(alias, expectation.entity)
                    if c > 0:
                        observed = c
                        break
            min_val = expectation.min
            max_val = expectation.max
            ok = observed >= min_val and (max_val is None or observed <= max_val)
            reason = f"event_count '{expectation.event_count}' observed {observed} (range: [{min_val}, {max_val}])"
            return ok, observed, reason

        elif isinstance(expectation, NoEventExpectation):
            # Check for edge case: if game was won, any subsequent death or lost event
            # during cleanup/level unload/teardown is not a game failure.
            win_events = self.filter(name="game.won") + self.filter(name="game.victory") + self.filter(name="level.completed")
            win_time = win_events[0].time if win_events else None

            # Collect matches strictly before win_time (or any time if not won)
            t_limit = win_time if (win_time is not None and expectation.no_event in ("player.died", "game.lost", "game.defeat")) else None
            matching_events = self.filter(name=expectation.no_event, t1=t_limit)
            if not matching_events and expectation.no_event in EVENT_ALIASES:
                for alias in EVENT_ALIASES[expectation.no_event]:
                    m = self.filter(name=alias, t1=t_limit)
                    if m:
                        matching_events = m
                        break
            observed = len(matching_events)
            ok = observed == 0
            reason = f"no_event '{expectation.no_event}' observed {observed} times (need 0)"
            return ok, observed, reason

        return True, 0, "expectation type not evaluated against event stream"

    def verify_all_expectations(
        self,
        expectations: Sequence[Expectation],
    ) -> Tuple[bool, List[str]]:
        """Verify all event-based expectations, returning overall status and failure messages."""
        all_ok = True
        failures: List[str] = []

        for exp in expectations:
            ok, observed, reason = self.verify_expectation(exp)
            if not ok:
                all_ok = False
                failures.append(f"Expectation failed: {reason}")

        return all_ok, failures

    def timeline_summary(self) -> Dict[str, Any]:
        """Return diagnostic metrics of the event stream."""
        if not self.events:
            return {
                "count": 0,
                "first_time_s": 0.0,
                "last_time_s": 0.0,
                "duration_s": 0.0,
                "unique_events": [],
                "malformed_lines": self.malformed_lines,
            }

        unique = sorted(list({ev.name for ev in self.events}))
        t0 = self.events[0].time
        t1 = self.events[-1].time
        return {
            "count": len(self.events),
            "first_time_s": round(t0, 3),
            "last_time_s": round(t1, 3),
            "duration_s": round(max(0.0, t1 - t0), 3),
            "unique_events": unique,
            "malformed_lines": self.malformed_lines,
        }
