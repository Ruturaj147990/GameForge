"""Data-driven rule and condition evaluator for gfdef/1 (WI-5.3).

Python reference implementation of FGameForgeConditionEvaluator
and RulesEvaluator with exact parity to the C++ engine evaluator.
"""
from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional, Tuple


class EvaluationContext:
    """Evaluation state context for condition checks."""

    def __init__(
        self,
        get_stat: Optional[Callable[[str], float]] = None,
        count_events: Optional[Callable[[str, Optional[str]], int]] = None,
        has_event: Optional[Callable[[str, Optional[str]], bool]] = None,
        elapsed_seconds: float = 0.0,
    ) -> None:
        self.get_stat = get_stat or (lambda s: float("nan"))
        self.count_events = count_events or (lambda e, ent: 0)
        self.has_event = has_event or (lambda e, ent: False)
        self.elapsed_seconds = elapsed_seconds


class ConditionEvaluator:
    """Evaluates gfdef/1 condition dictionaries."""

    @staticmethod
    def evaluate(cond: Dict[str, Any], ctx: EvaluationContext, depth: int = 0) -> Tuple[bool, Optional[str]]:
        """Returns (result, error_if_malformed). Never raises."""
        if depth > 3:
            return False, "Exceeded maximum nesting depth of 3"

        if not isinstance(cond, dict):
            return False, "Condition must be a JSON object"

        kind = cond.get("kind")
        if not kind:
            return False, "Condition missing 'kind' field"

        if kind == "count_at_least":
            event = cond.get("event")
            n = cond.get("n")
            if not event or n is None:
                return False, "count_at_least requires 'event' and 'n'"
            source = cond.get("source")
            count = ctx.count_events(event, source)
            return count >= n, None

        elif kind == "stat":
            stat_name = cond.get("stat")
            op = cond.get("op")
            target = cond.get("value")
            if not stat_name or not op or target is None:
                return False, "stat condition requires 'stat', 'op', and 'value'"

            val = ctx.get_stat(stat_name)
            if math.isnan(val):
                return False, None

            if op == "<":
                return val < target, None
            elif op == "<=":
                return val <= target, None
            elif op in ("==", "="):
                return abs(val - target) < 1e-4, None
            elif op == ">=":
                return val >= target, None
            elif op == ">":
                return val > target, None
            elif op == "!=":
                return abs(val - target) >= 1e-4, None
            else:
                return False, f"Unknown comparison operator {op!r}"

        elif kind == "timer":
            seconds = cond.get("seconds")
            if seconds is None:
                return False, "timer requires 'seconds'"
            return ctx.elapsed_seconds >= seconds, None

        elif kind == "event":
            event = cond.get("event")
            if not event:
                return False, "event requires 'event'"
            source = cond.get("source")
            return ctx.has_event(event, source), None

        elif kind == "all":
            conditions = cond.get("conditions")
            if not isinstance(conditions, list) or len(conditions) == 0:
                return False, "'all' requires non-empty 'conditions' list"
            for sub in conditions:
                res, err = ConditionEvaluator.evaluate(sub, ctx, depth + 1)
                if err:
                    return False, err
                if not res:
                    return False, None
            return True, None

        elif kind == "any":
            conditions = cond.get("conditions")
            if not isinstance(conditions, list):
                return False, "'any' requires 'conditions' list"
            if len(conditions) == 0:
                return False, None
            for sub in conditions:
                res, err = ConditionEvaluator.evaluate(sub, ctx, depth + 1)
                if err:
                    return False, err
                if res:
                    return True, None
            return False, None

        else:
            return False, f"Unknown condition kind: {kind!r}"


class RulesEvaluator:
    """In-memory rules engine for executing gfdef rules on events."""

    def __init__(self, gfdef: Dict[str, Any]) -> None:
        self.gfdef = gfdef
        self.stats: Dict[str, float] = {}
        self.stat_bounds: Dict[str, Tuple[float, float]] = {}
        self.event_counts: Dict[Tuple[str, Optional[str]], int] = {}
        self.game_ended: bool = False
        self.end_reason: Optional[str] = None
        self.outcome: Optional[str] = None  # "win" | "lose"
        self.elapsed: float = 0.0

        # Initialize stats
        for s_name, s_def in gfdef.get("stats", {}).items():
            self.stats[s_name] = float(s_def.get("initial", 0.0))
            s_min = s_def.get("min", float("-inf"))
            s_max = s_def.get("max", float("inf"))
            self.stat_bounds[s_name] = (s_min, s_max)

    def get_stat(self, name: str) -> float:
        return self.stats.get(name, float("nan"))

    def set_stat(self, name: str, value: float) -> None:
        bounds = self.stat_bounds.get(name)
        if bounds:
            value = max(bounds[0], min(bounds[1], value))
        self.stats[name] = value

    def add_stat(self, name: str, delta: float) -> None:
        cur = self.stats.get(name, 0.0)
        self.set_stat(name, cur + delta)

    def handle_event(self, event_name: str, entity_id: Optional[str] = None, data: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Dispatch event through rules and evaluate win/lose conditions."""
        if self.game_ended:
            return []

        # Increment count
        key = (event_name, entity_id)
        self.event_counts[key] = self.event_counts.get(key, 0) + 1
        key_wildcard = (event_name, None)
        if entity_id is not None:
            self.event_counts[key_wildcard] = self.event_counts.get(key_wildcard, 0) + 1

        applied_effects: List[Dict[str, Any]] = []
        ctx = EvaluationContext(
            get_stat=self.get_stat,
            count_events=lambda e, ent: self.event_counts.get((e, ent), 0),
            has_event=lambda e, ent: (e, ent) in self.event_counts,
            elapsed_seconds=self.elapsed,
        )

        # Evaluate rules
        for rule in self.gfdef.get("rules", []):
            when = rule.get("when", {})
            w_event = when.get("e")
            w_ent = when.get("ent")
            if w_event == event_name and (w_ent is None or w_ent == entity_id):
                # Check 'if' conditions
                conditions_met = True
                for cond in rule.get("if", []):
                    ok, _ = ConditionEvaluator.evaluate(cond, ctx)
                    if not ok:
                        conditions_met = False
                        break

                if conditions_met:
                    for effect in rule.get("do", []):
                        self._apply_effect(effect)
                        applied_effects.append(effect)

        # Check win/lose conditions: lose checked first (tie-break rule)
        for i, cond in enumerate(self.gfdef.get("lose", [])):
            ok, _ = ConditionEvaluator.evaluate(cond, ctx)
            if ok:
                self.game_ended = True
                self.outcome = "lose"
                self.end_reason = f"lose[{i}]"
                return applied_effects

        for i, cond in enumerate(self.gfdef.get("win", [])):
            ok, _ = ConditionEvaluator.evaluate(cond, ctx)
            if ok:
                self.game_ended = True
                self.outcome = "win"
                self.end_reason = f"win[{i}]"
                return applied_effects

        return applied_effects

    def _apply_effect(self, effect: Dict[str, Any]) -> None:
        kind = effect.get("kind")
        if kind == "add_stat":
            self.add_stat(effect.get("stat", ""), float(effect.get("delta", 0.0)))
        elif kind == "set_stat":
            self.set_stat(effect.get("stat", ""), float(effect.get("value", 0.0)))
        elif kind == "end_game":
            self.game_ended = True
            self.outcome = effect.get("outcome", "win")
            self.end_reason = "end_game effect"
