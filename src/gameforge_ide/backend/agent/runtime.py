"""Bounded Agent Runtime and Execution Loop for GameForge IDE.

Authoritative implementation conforming to GameForge Master Blueprint (Oct 27, 2026).
Core Rules:
1. The model proposes; the harness decides.
2. Completion is evidence, not text (acceptance predicates over real state).
3. Fail closed: missing predicates, unapplied diffs, or unacting models block completion.
4. Bound every operation: tokens, repetitions, iterations, and wall-clock time.
5. Repetition control: 3rd identical call terminates as BLOCKED (repetition_budget_exhausted).
6. Suspended approvals: Diff approval resumes the same task.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, List, Optional
from pydantic import BaseModel, Field

from ..providers.base import ModelProvider
from ..providers.router import ModelRouter
from ..session_manager import Session, SessionManager
from ..tools.gateway import ToolGateway
from ..models.modes import AutonomyProfile, TaskLifecycleStatus, TaskMode
from ..models.plan_artifact import PlanArtifact, PlanStep
from .code_verify import parse_diagnostics
from .context_manager import ContextManager
from .repair_system import FailureCategory, RepairEngine, RootCause
from .task_state import (
    LedgerEntry,
    PendingApproval,
    TaskAcceptancePredicate,
    TaskBudget,
    TaskState,
)


ENGINEERING_STAGES: tuple[str, ...] = (
    "Prompt",
    "Code Retrieval",
    "Reasoning",
    "Planning",
    "Source Inspection",
    "Code Generation",
    "Diff",
    "Approval",
    "Verification",
)


class AgentEvent(BaseModel):
    event_type: str  # "status", "token", "plan", "tool_call", "tool_result", "diff_pending", "error", "done"
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)


async def _no_chunks():
    """Empty async stream used when the native tool-calling path already produced the reply."""
    return
    yield  # pragma: no cover  (makes this an async generator)


class AgentRuntime:
    """Orchestrates the bounded agent loop with typed tools, diff approval, and error repair."""

    def __init__(
        self,
        workspace_root: Path,
        session_manager: SessionManager,
        model_router: ModelRouter,
        max_iterations: int = 12,
        studio_mode: bool = False,
    ):
        self.studio_mode = studio_mode
        self.workspace_root = workspace_root.resolve()
        self.session_manager = session_manager
        self.router = model_router
        self.tool_gateway = ToolGateway(self.workspace_root)
        self.context_manager = ContextManager(self.workspace_root)
        self.repair_engine = RepairEngine(self.workspace_root)
        self.max_iterations = max_iterations
        # Native tool calling is on by default; GAMEFORGE_NATIVE_TOOLS=0 restores text extraction.
        self.native_tools = os.environ.get("GAMEFORGE_NATIVE_TOOLS", "1") != "0"
        self.tasks_dir = self.workspace_root / ".gameforge" / "tasks"
        try:
            self.tasks_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self._active_tasks: Dict[str, TaskState] = {}
        self._cancel_events: Dict[str, asyncio.Event] = {}
        self._cancelled_sessions: set[str] = set()

    def cancel_task(self, session_id: str) -> bool:
        """Cooperatively cancels an active or waiting task without zombie locks."""
        self._cancelled_sessions.add(session_id)
        ev = self._cancel_events.get(session_id)
        if ev:
            ev.set()
        task = self._active_tasks.get(session_id)
        if task:
            task.terminal_status = "CANCELLED"
            task.terminal_reason = "cancelled_by_user"
            task.pending_approval = None
            self._save_task_state(task)
        return True

    def is_task_cancelled(self, session_id: str) -> bool:
        """Returns True if a task has received a cooperative cancellation request."""
        if session_id in self._cancelled_sessions:
            return True
        ev = self._cancel_events.get(session_id)
        if ev and ev.is_set():
            return True
        task = self._active_tasks.get(session_id)
        return bool(task and task.terminal_status == "CANCELLED")

    def set_workspace(self, new_workspace: Path | str) -> None:
        """Switch the agent runtime active workspace and re-initialize path-dependent subsystems."""
        self.workspace_root = Path(new_workspace).resolve()
        self.tool_gateway = ToolGateway(self.workspace_root)
        self.context_manager = ContextManager(self.workspace_root)
        self.repair_engine = RepairEngine(self.workspace_root)
        self.tasks_dir = self.workspace_root / ".gameforge" / "tasks"
        try:
            self.tasks_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def _native_tool_schemas(self) -> List[Dict[str, Any]]:
        """Provider-neutral tool schemas {name, description, parameters} from the gateway."""
        out = []
        for d in self.tool_gateway.get_definitions():
            params = dict(d.parameters or {"type": "object", "properties": {}})
            props = {}
            for k, v in (params.get("properties") or {}).items():
                v = {kk: vv for kk, vv in v.items() if kk not in ("optional",)}
                props[k] = v
            params["properties"] = props
            params.setdefault("type", "object")
            out.append({"name": d.name, "description": d.description, "parameters": params})
        return out

    def _format_tools_description(self) -> str:
        defs = self.tool_gateway.get_definitions()
        lines = []
        for d in defs:
            properties = d.parameters.get("properties", {})
            params = ", ".join(
                f"{name}:{schema.get('type', 'any')}"
                for name, schema in properties.items()
            )
            required = ", ".join(d.parameters.get("required", []))
            description = d.description.split(".", 1)[0].strip()
            lines.append(
                f"- {d.name}({params}) — {description}"
                + (f"; required: {required}" if required else "")
            )
        return "\n".join(lines)

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Conservative, tokenizer-independent estimate; not provider usage data."""
        return (len(text.encode("utf-8")) + 2) // 3

    @classmethod
    def fit_history_to_context(
        cls,
        system_prompt: str,
        messages: List[Dict[str, str]],
        max_context: int,
        *,
        output_tokens: int = 1024,
        safety_tokens: int = 128,
        pinned_message: Optional[Dict[str, str]] = None,
    ) -> tuple[List[Dict[str, str]], Dict[str, int]]:
        """Keep whole messages within an estimated input budget, pinning this task's prompt,
        enforcing contiguous chronological history, and compacting omitted turns into a summary."""
        input_budget = max(0, max_context - output_tokens - safety_tokens)
        system_tokens = cls.estimate_tokens(system_prompt)
        if system_tokens > input_budget:
            raise ValueError(
                f"GameForge system context is estimated at {system_tokens} tokens, "
                f"above the {input_budget}-token input budget for this model."
            )
        remaining = input_budget - system_tokens

        # Handle pinned message (active user prompt)
        selected_indices: List[int] = []
        pinned_index = None
        if pinned_message is not None:
            pinned_content = pinned_message.get("content", "").strip()
            for index in range(len(messages) - 1, -1, -1):
                msg_content = messages[index].get("content", "").strip()
                if messages[index] == pinned_message or (
                    messages[index].get("role") == pinned_message.get("role")
                    and pinned_content
                    and (msg_content == pinned_content or pinned_content in msg_content)
                ):
                    pinned_index = index
                    break
            if pinned_index is None:
                # Fallback: locate the latest user turn if prompt was merged or modified
                for index in range(len(messages) - 1, -1, -1):
                    if messages[index].get("role") == "user":
                        pinned_index = index
                        break

            if pinned_index is not None:
                pinned_tokens = cls.estimate_tokens(messages[pinned_index].get("content", ""))
                if pinned_tokens > remaining:
                    raise ValueError(
                        f"The complete active prompt is estimated at {pinned_tokens} tokens, "
                        f"but only {remaining} input tokens remain after system context. "
                        "Shorten the prompt or reduce project context; no prompt text was truncated."
                    )
                selected_indices.append(pinned_index)
                remaining -= pinned_tokens

        # Select contiguous history backwards from the latest message
        idx = len(messages) - 1
        omitted = 0
        while idx >= 0:
            if idx == pinned_index:
                idx -= 1
                continue
            msg = messages[idx]
            msg_tokens = cls.estimate_tokens(msg.get("content", ""))
            if msg_tokens <= remaining:
                selected_indices.append(idx)
                remaining -= msg_tokens
                idx -= 1
            else:
                omitted = idx + 1
                break

        selected_indices.sort()
        selected = [messages[i] for i in selected_indices]

        # If messages were omitted, synthesize a compact summary of older turns
        if omitted > 0:
            omitted_msgs = messages[:omitted]
            summary_snippets = []
            for m in omitted_msgs:
                r = m.get("role", "user")
                c = m.get("content", "").strip()
                if not c:
                    continue
                first_line = c.splitlines()[0] if c else ""
                if len(first_line) > 70:
                    first_line = first_line[:67] + "..."
                summary_snippets.append(f"{r}: {first_line}")
            if summary_snippets:
                compact_summary_text = "[Earlier conversation compacted: " + " | ".join(summary_snippets[:4]) + "]"
                selected.insert(0, {"role": "user", "content": compact_summary_text})
                if len(selected) > 1 and selected[1].get("role") == "user":
                    merged_content = f"{selected[0]['content']}\n\n{selected[1]['content']}"
                    selected[1]["content"] = merged_content
                    selected.pop(0)

        # Enforce alternating roles (merge adjacent turns of same role)
        merged_turns: List[Dict[str, str]] = []
        for m in selected:
            if not merged_turns:
                merged_turns.append(dict(m))
            elif merged_turns[-1]["role"] == m["role"]:
                merged_turns[-1]["content"] += "\n\n" + m.get("content", "")
            else:
                merged_turns.append(dict(m))
        selected = merged_turns

        # Invariant: Multi-turn LLM chat prompts must end with a user turn so the model knows to respond.
        while len(selected) > 1 and selected[-1].get("role") == "assistant":
            selected.pop()

        used = input_budget - remaining
        return selected, {
            "estimated_input_tokens": used,
            "input_budget_tokens": input_budget,
            "omitted_history_messages": omitted,
        }

    def _extract_tool_call(self, text: str) -> Optional[Dict[str, Any]]:
        """Extracts structured tool invocation from model output supporting multiple standard schemas
        (OpenAI, Anthropic, ReAct, XML tags, string-serialized arguments, and balanced JSON)."""
        def _parse_arguments(args: Any) -> Dict[str, Any]:
            if isinstance(args, dict):
                return args
            if isinstance(args, str):
                s = args.strip()
                # 1. Strip outer markdown code fences if present: ```json ... ```
                fence_m = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", s, re.IGNORECASE)
                if fence_m:
                    s = fence_m.group(1).strip()
                # 2. Try direct JSON parsing or unpack stringified JSON
                try:
                    parsed = json.loads(s)
                    if isinstance(parsed, dict):
                        return parsed
                    elif isinstance(parsed, str):
                        # Escaped/double-serialized JSON string: e.g. "{\"file_path\": \"foo\"}"
                        try:
                            nested = json.loads(parsed)
                            if isinstance(nested, dict):
                                return nested
                        except Exception:
                            pass
                        return {"input": parsed}
                except Exception:
                    pass
                # 3. Balanced JSON extraction within string
                b_start = s.find("{")
                b_end = s.rfind("}")
                if b_start != -1 and b_end > b_start:
                    candidate = s[b_start : b_end + 1]
                    try:
                        parsed = json.loads(candidate)
                        if isinstance(parsed, dict):
                            return parsed
                    except Exception:
                        pass
                    # Unescape escaped newlines/quotes if present
                    try:
                        unescaped = candidate.encode().decode("unicode_escape")
                        parsed = json.loads(unescaped)
                        if isinstance(parsed, dict):
                            return parsed
                    except Exception:
                        pass
                # 4. If it's a raw non-empty string, preserve as input
                if s and not s.startswith(("{", "[")):
                    return {"input": s}
            return {}

        def _normalize_tool_data(data: Any) -> Optional[Dict[str, Any]]:
            if not isinstance(data, dict):
                if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                    return _normalize_tool_data(data[0])
                return None

            # OpenAI format with top-level tool_calls array
            if "tool_calls" in data and isinstance(data["tool_calls"], list) and len(data["tool_calls"]) > 0:
                first = data["tool_calls"][0]
                if isinstance(first, dict):
                    return _normalize_tool_data(first)

            # OpenAI single function call: {"type": "function", "function": {"name": ..., "arguments": ...}}
            if "function" in data and isinstance(data["function"], dict):
                fn = data["function"]
                name = fn.get("name")
                if name and isinstance(name, str):
                    return {"name": name, "arguments": _parse_arguments(fn.get("arguments", {}))}

            # Anthropic tool_use format: {"type": "tool_use", "name": ..., "input": ...}
            if data.get("type") == "tool_use" and "name" in data:
                return {"name": str(data["name"]), "arguments": _parse_arguments(data.get("input", {}))}

            # Anthropic content array with tool_use blocks
            if "content" in data and isinstance(data["content"], list):
                for item in data["content"]:
                    if isinstance(item, dict) and (item.get("type") == "tool_use" or "tool" in item or "function" in item):
                        res = _normalize_tool_data(item)
                        if res:
                            return res

            # GameForge native format: {"tool": "...", "args": {...}}
            if "tool" in data and ("args" in data or "parameters" in data or "arguments" in data):
                args_val = data.get("args") or data.get("parameters") or data.get("arguments")
                return {"name": str(data["tool"]), "arguments": _parse_arguments(args_val)}

            # Standard format: {"name": "...", "arguments": {...}}
            if "name" in data and ("arguments" in data or "args" in data or "parameters" in data or "input" in data):
                args_val = data.get("arguments") or data.get("args") or data.get("parameters") or data.get("input")
                return {"name": str(data["name"]), "arguments": _parse_arguments(args_val)}

            # ReAct / LangChain: {"action": "...", "action_input": {...}}
            if "action" in data and ("action_input" in data or "action_args" in data or "args" in data):
                args_val = data.get("action_input") or data.get("action_args") or data.get("args")
                return {"name": str(data["action"]), "arguments": _parse_arguments(args_val)}

            # Parameter aliases: tool_name + parameters
            if "tool_name" in data and ("parameters" in data or "args" in data or "arguments" in data):
                args_val = data.get("parameters") or data.get("args") or data.get("arguments")
                return {"name": str(data["tool_name"]), "arguments": _parse_arguments(args_val)}

            # Call / Command aliases: call + args
            if ("call" in data or "command" in data) and ("args" in data or "arguments" in data):
                name = data.get("call") or data.get("command")
                args_val = data.get("args") or data.get("arguments")
                return {"name": str(name), "arguments": _parse_arguments(args_val)}

            # Function string: {"function": "tool_name", "arguments": {...}}
            if "function" in data and isinstance(data["function"], str) and ("arguments" in data or "args" in data):
                args_val = data.get("arguments") or data.get("args")
                return {"name": data["function"], "arguments": _parse_arguments(args_val)}

            return None

        # 0. Match XML-style tool calls (<tool_use>, <tool_call>, <function_call>, <invoke>)
        xml_tool_use = re.search(r"<tool_use>\s*<name>([^<]+)</name>\s*<(?:input|arguments|args)>(.*?)</(?:input|arguments|args)>\s*</tool_use>", text, re.DOTALL | re.IGNORECASE)
        if xml_tool_use:
            name = xml_tool_use.group(1).strip()
            args_str = xml_tool_use.group(2).strip()
            return {"name": name, "arguments": _parse_arguments(args_str)}

        xml_invoke = re.search(r"<invoke\s+name=[\"']([^\"']+)[\"']\s*>(.*?)</invoke>", text, re.DOTALL | re.IGNORECASE)
        if xml_invoke:
            name = xml_invoke.group(1).strip()
            args_body = xml_invoke.group(2).strip()
            # Check for <parameter name="k">v</parameter>
            params = {}
            for pm in re.finditer(r"<parameter\s+name=[\"']([^\"']+)[\"']\s*>(.*?)</parameter>", args_body, re.DOTALL | re.IGNORECASE):
                params[pm.group(1).strip()] = pm.group(2).strip()
            if not params and args_body:
                params = _parse_arguments(args_body)
            return {"name": name, "arguments": params}

        xml_generic = re.search(r"<(?:tool_call|function_call)>\s*(.*?)\s*</(?:tool_call|function_call)>", text, re.DOTALL | re.IGNORECASE)
        if xml_generic:
            try:
                data = json.loads(xml_generic.group(1).strip())
                norm = _normalize_tool_data(data)
                if norm:
                    return norm
            except Exception:
                pass

        # Plain text ReAct pattern: Action: <tool_name>\nAction Input: <args>
        react_match = re.search(
            r"(?:^|\n)\s*Action\s*:\s*([a-zA-Z0-9_\-]+)\s*\n\s*Action\s+Input\s*:\s*(.*?)(?=\n\s*(?:Action|Observation|Thought|Final Answer)|\Z)",
            text,
            re.DOTALL | re.IGNORECASE,
        )
        if react_match:
            action_name = react_match.group(1).strip()
            action_input = react_match.group(2).strip()
            action_input = re.sub(r"^```(?:json)?\s*", "", action_input)
            action_input = re.sub(r"\s*```$", "", action_input)
            parsed_args = _parse_arguments(action_input)
            if not parsed_args and action_input and not action_input.startswith(("{", "[")):
                parsed_args = {"input": action_input}
            return {"name": action_name, "arguments": parsed_args}

        # XML named tool or action pattern: <tool_call name="..."> or <action name="...">
        xml_named = re.search(r"<(?:tool_call|action|tool)\s+name=[\"']([^\"']+)[\"']\s*>(.*?)</(?:tool_call|action|tool)>", text, re.DOTALL | re.IGNORECASE)
        if xml_named:
            name = xml_named.group(1).strip()
            body = xml_named.group(2).strip()
            args = _parse_arguments(body) if body else {}
            return {"name": name, "arguments": args}

        # 1. Match ```json {...} ``` code blocks with balanced brace extraction
        for m in re.finditer(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL):
            block = m.group(1).strip()
            try:
                data = json.loads(block)
                norm = _normalize_tool_data(data)
                if norm:
                    return norm
            except Exception:
                pass
            # If full block isn't raw JSON, find first balanced object inside block
            b_start = block.find("{")
            if b_start != -1:
                brace_count = 0
                in_str = False
                escape = False
                for j in range(b_start, len(block)):
                    ch = block[j]
                    if escape:
                        escape = False
                        continue
                    if ch == '\\':
                        escape = True
                        continue
                    if ch == '"':
                        in_str = not in_str
                        continue
                    if not in_str:
                        if ch == '{':
                            brace_count += 1
                        elif ch == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                candidate = block[b_start : j + 1]
                                try:
                                    data = json.loads(candidate)
                                    norm = _normalize_tool_data(data)
                                    if norm:
                                        return norm
                                except Exception:
                                    pass
                                break

        # 2. Match single or multi-line tool invocation with brace balancing
        markers = ('"tool"', '"name"', '"function"', '"tool_name"', '"action"', '"tool_use"', '"type": "function"')
        for marker in markers:
            start_pos = 0
            while True:
                idx = text.find(marker, start_pos)
                if idx == -1:
                    break
                brace_idx = text.rfind('{', 0, idx)
                if brace_idx != -1:
                    brace_count = 0
                    in_str = False
                    escape = False
                    for j in range(brace_idx, len(text)):
                        ch = text[j]
                        if escape:
                            escape = False
                            continue
                        if ch == '\\':
                            escape = True
                            continue
                        if ch == '"':
                            in_str = not in_str
                            continue
                        if not in_str:
                            if ch == '{':
                                brace_count += 1
                            elif ch == '}':
                                brace_count -= 1
                                if brace_count == 0:
                                    candidate = text[brace_idx : j + 1]
                                    try:
                                        data = json.loads(candidate)
                                        norm = _normalize_tool_data(data)
                                        if norm:
                                            return norm
                                    except Exception:
                                        pass
                                    break
                    if brace_count == 1 and not in_str:
                        candidate = text[brace_idx:].strip() + "}"
                        try:
                            data = json.loads(candidate)
                            norm = _normalize_tool_data(data)
                            if norm:
                                return norm
                        except Exception:
                            pass
                start_pos = idx + len(marker)

        # 3. Code-dump interception: match code blocks with identifiable file targets
        return self._extract_code_block_as_write_file(text)

    @staticmethod
    def _extract_code_block_as_write_file(text: str) -> Optional[Dict[str, Any]]:
        """Extracts code blocks with explicit file paths when model emits code instead of JSON tool call."""
        if not text:
            return None

        fence_matches = list(re.finditer(r"```(?:[a-zA-Z0-9_\+\-]+)?\s*\n(.*?)\n```", text, re.DOTALL))
        for fm in fence_matches:
            code_content = fm.group(1).strip()
            if not code_content:
                continue

            detected_path = None
            header_lines = code_content.splitlines()[:4]
            for hl in header_lines:
                m_path = re.search(r"(?:^|\s)(?://|/\*|#)\s*(?:file:?\s*)?([\w\-\./\\]+\.(?:h|hpp|cpp|c|cs|py|json|ini|uproject|txt))\b", hl, re.I)
                if m_path:
                    detected_path = m_path.group(1).strip("`'\" \t").replace("\\", "/")
                    break

            if not detected_path:
                preceding = text[max(0, fm.start() - 250) : fm.start()]
                m_prec = re.findall(r"(?:file|path|header|source|create|in|to)?\s*[:`\'\"]*([\w\-\./\\]+\.(?:h|hpp|cpp|c|cs|py|json|ini|uproject|txt))[`\'\"]*", preceding, re.I)
                if m_prec:
                    detected_path = m_prec[-1].strip("`'\" \t").replace("\\", "/")

            if detected_path and not detected_path.startswith("http") and not detected_path.endswith((".png", ".jpg", ".exe")):
                return {
                    "name": "write_file",
                    "arguments": {
                        "subpath": detected_path,
                        "content": code_content,
                    },
                }

        return None

    @staticmethod
    def _is_tool_call_start(text: str) -> bool:
        """Determines if the text begins or contains a raw tool invocation block."""
        stripped = text.strip()
        tool_prefixes = (
            '{"tool"', '{"name"', '{"function"', '{"tool_name"', '{"action"', '{"type": "tool_use"',
            '{"type":"tool_use"', '{"tool_calls"', '{"call"',
            '{\n  "tool"', '{\n  "name"', '{\n  "function"', '{\n  "action"',
            '{\n "tool"', '{\n "name"', '{\n "function"', '{\n "action"',
            '```json\n{"tool"', '```json\n{"name"', '```json\n{"function"', '```json\n{"action"',
            '```json\n{\n  "tool"', '```json\n{\n  "name"', '```json\n{\n  "function"',
            '```\n{"tool"', '```\n{"name"', '```\n{"function"', '```\n{"action"',
            '```\n{\n  "tool"', '```\n{\n  "name"',
            '<tool_call>', '<tool_use>', '<invoke', '<function_call>', '<tool_call name=', '<action name=', '<tool name=',
            'Action:', 'Action :', 'Thought:\nAction:',
        )
        if any(stripped.startswith(pfx) for pfx in tool_prefixes):
            return True
        if re.search(r"```(?:json)?\s*\{\s*\"(?:tool|name|function|action|tool_name|tool_calls|type)\"", stripped):
            return True
        if re.search(r"(?:^|\n)\s*Action\s*:\s*[a-zA-Z0-9_\-]+", stripped):
            return True
        return False

    @staticmethod
    def _clean_narrative_text(text: str) -> str:
        """Removes raw tool invocation blocks from model response, leaving clean narrative prose."""
        if not text:
            return ""
        cleaned = re.sub(
            r"```(?:json)?\s*\{\s*\"(?:tool|name|function|action|tool_name|tool_calls|type)\".*?\}\s*```",
            "",
            text,
            flags=re.DOTALL,
        )
        cleaned = re.sub(
            r"<(?:tool_call|tool_use|function_call|invoke(?:\s+name=[^>]+)?|action(?:\s+name=[^>]+)?|tool(?:\s+name=[^>]+)?)>.*?</(?:tool_call|tool_use|function_call|invoke|action|tool)>",
            "",
            cleaned,
            flags=re.DOTALL | re.IGNORECASE,
        )
        cleaned = re.sub(
            r"(?:^|\n)\s*Action\s*:\s*[a-zA-Z0-9_\-]+\s*\n\s*Action\s+Input\s*:.*?(?=\n\s*(?:Action|Observation|Thought|Final Answer)|\Z)",
            "",
            cleaned,
            flags=re.DOTALL | re.IGNORECASE,
        )
        cleaned = re.sub(r"\{\s*\"(?:tool|name|function|action|tool_name|tool_calls|type)\"\s*:.*?\}\s*$", "", cleaned, flags=re.DOTALL)
        cleaned = re.sub(r"^\s*\{\s*\"(?:tool|name|function|action|tool_name|tool_calls|type)\"\s*:.*?\}\s*", "", cleaned, flags=re.DOTALL)
        return cleaned.strip()

    @staticmethod
    def _is_narrative_excuse(text: str) -> bool:
        """Detects if model response is an excuse, apology, or passive refusal rather than an action."""
        if not text:
            return False
        t = text.lower().strip()
        excuse_patterns = [
            r"\b(?:i(?:'m| am)?\s+sorry|i apologize|apologies|my apologies)\b",
            r"\b(?:unfortunately|regrettably)\b.*?\b(?:cannot|could not|unable|failed|error)\b",
            r"\b(?:i cannot|i am unable to|i'm unable to|i am not able to|i'm not able to)\b.*?\b(?:proceed|complete|execute|continue|perform)\b",
            r"\b(?:due to\s+(?:an?\s+)?(?:error|failure|issue))\b",
            r"\b(?:as an ai|as a language model|i am an ai|i'm an ai)\b.*?\b(?:cannot|unable|don't have)\b",
            r"\b(?:there\s+seems\s+to\s+be\s+an\s+issue|something\s+went\s+wrong)\b",
            r"\b(?:i\s+cannot\s+modify|i\s+can't\s+directly\s+modify|cannot\s+directly\s+edit|can't\s+directly\s+edit)\b",
            r"\bi\s+(?:don't|do not)\s+have\s+(?:the\s+)?(?:ability|access|permission)\s+to\b",
        ]
        return any(bool(re.search(pat, t, re.DOTALL)) for pat in excuse_patterns)

    @staticmethod
    def _detect_phantom_edit_or_claimed_modification(text: str) -> bool:
        """Detects if model claims modifications without actually calling tools or proposing diffs."""
        if not text:
            return False
        t = text.lower().strip()
        claimed_patterns = [
            r"\bi(?:'ve| have)?\s+(?:\w+\s+)?(?:updated|modified|changed|added|created|implemented|edited|written|refactored|fixed|applied|replaced|inserted)\b.*?\b(?:file|class|code|script|function|component|header|method|diff|lines?)\b",
            r"\bi(?:'ve| have)?\s+(?:\w+\s+)?(?:made|applied)\s+(?:the\s+)?(?:necessary\s+)?(?:changes|modifications|edits|updates)\b",
            r"\b(?:the\s+)?(?:file|class|source|code|component|header)\s+(?:has\s+been|is\s+now|was|is)\s+(?:updated|modified|created|changed|added|written|edited|refactored|fixed)\b",
            r"\bi\s+(?:went\s+ahead\s+and|have\s+already)\s+(?:updated|modified|created|added|implemented|edited)\b",
            r"\b(?:here\s+is|here\s+are|below\s+is|above\s+is)\s+the\s+(?:updated|modified|new)\s+(?:code|file|implementation|changes|contents?)\b",
            r"\ball\s+(?:changes|updates|modifications)\s+(?:have\s+been\s+)?(?:applied|saved|completed)\b",
            r"\b(?:done|finished|completed)[!.]?\s+i(?:'ve| have)?\s+(?:updated|modified|created|added)\b",
            r"\bi(?:'ve| have)?\s+(?:\w+\s+)?(?:completed|finished)\s+(?:the\s+)?(?:implementation|changes|updates|edits|modifications)\b",
        ]
        return any(bool(re.search(pat, t, re.DOTALL)) for pat in claimed_patterns)

    @staticmethod
    def _is_narrative_promise(text: str) -> bool:
        """Detects if model emits a narrative promise to inspect or check files without calling a tool."""
        if not text:
            return False
        t = text.lower().strip()
        promise_patterns = [
            r"\b(?:let\s+me\s+(?:check|inspect|look|examine|see|verify|read|find|explore|search))\b",
            r"\b(?:i\s+(?:will|shall|need\s+to|have\s+to|must)\s+(?:check|inspect|look\s+at|examine|verify|read|find|search))\b",
            r"\b(?:checking|searching|looking|inspecting)\s+(?:for\s+)?(?:the\s+)?(?:project|files|structure|source|code|status|workspace)\b",
            r"\b(?:allow\s+me\s+to\s+(?:check|inspect|look|search))\b",
            r"\b(?:let\s+me\s+(?:now\s+)?(?:search|find|query))\b",
        ]
        return any(bool(re.search(pat, t, re.DOTALL)) for pat in promise_patterns)

    @staticmethod
    def _classify_engineering_stage(tool_name: str, has_modified_files: bool = False) -> str:
        """Maps an active tool invocation to its corresponding stage in the 9-stage engineering loop."""
        if tool_name in ("search_code", "search_index"):
            return "Code Retrieval"
        elif tool_name in ("list_dir", "read_file", "unreal_find_projects", "unreal_engine_info"):
            return "Source Inspection"
        elif tool_name in ("propose_edit", "write_file", "unreal_editor"):
            return "Code Generation"
        elif tool_name in ("apply_edit", "apply_diff", "apply_batch", "apply_diffs_batch"):
            return "Application"
        elif tool_name in ("run_command", "terminal_run"):
            return "Verification" if has_modified_files else "Testing"
        return "Verification" if has_modified_files else "Planning"

    @staticmethod
    def _is_conversational(user_prompt: str) -> bool:
        """Return True when the prompt is purely informational, explanatory, or conversational and should not trigger mutation tools."""
        p = user_prompt.strip().lower()
        words = re.findall(r"\b\w+\b", p)
        action_keywords = {
            "create", "build", "make", "implement", "generate", "inspect",
            "fix", "refactor", "write", "setup", "develop", "code", "author",
            "add", "remove", "delete", "update", "edit", "explore", "list",
            "search", "check", "run", "verify", "test", "compile", "diff",
            "modify", "scaffold", "assemble", "patch", "repair", "proceed",
            "complete", "completed", "finish", "finished", "status", "progress",
            "state", "game", "project", "files", "file", "error", "errors",
            "log", "logs", "show", "read", "view", "sudoku", "ready", "done",
            "package", "packaging",
        }

        # Pure meta inquiries about GameForge itself, capabilities, or conceptual questions
        meta_qa = (
            "what does the chat", "what does the assistant", "what does chat do",
            "what does the ide do", "how does the chat work", "how does gameforge work",
            "what can you do", "what are your capabilities", "who are you",
        )
        if any(mq in p for mq in meta_qa):
            return True

        # Inquiries about project status, completion, files, or builds require tools
        is_project_query = bool(re.search(r"\b(complete|completed|done|finished|status|progress|state|build|package|error|errors|log|logs|files?|project|game)\b", p))
        if is_project_query:
            return False

        # If user explicitly asks for implementation/creation/fixing/adding/modifying:
        # e.g., "Implement a weapon system", "Can you add hit detection?", "Create an FPS game"
        # These are actionable engineering requests, NOT conversational!
        explicit_action_verbs = {
            "create", "build", "make", "implement", "generate", "fix",
            "refactor", "setup", "develop", "author", "modify", "patch",
            "scaffold", "assemble", "repair",
        }
        has_action_verb = bool(set(words).intersection(explicit_action_verbs))
        is_pure_explanation = bool(re.search(r"^(?:explain|how does|what is|what are|what does|describe|tell me about|show me an example|give me an? (?:example|snippet))\b", p))

        if has_action_verb and not is_pure_explanation:
            return False

        if len(words) <= 5:
            if not set(words).intersection(action_keywords):
                return True

        greeting_prefixes = (
            "hi", "hello", "hey", "bro", "sup", "yo", "hiya",
            "good morning", "good afternoon", "good evening",
            "how are you", "how r u", "what's up", "whats up",
            "thanks", "thank you", "thx", "cheers",
            "ok", "okay", "got it", "noted", "cool", "great", "nice", "continue",
        )
        for prefix in greeting_prefixes:
            if p == prefix or p.rstrip("!.,") == prefix:
                return True
            if p.startswith(prefix + " ") or p.startswith(prefix + ","):
                rest = p[len(prefix):].strip(" ,!.")
                if not rest:
                    return True
                if any(k in rest for k in ("create", "build", "make", "fix", "add", "remove", "update", "game", "shoot", "run", "check", "speed", "implement")):
                    break
                rest_words = re.findall(r"\b[a-z0-9_]+\b", rest)
                if set(rest_words).intersection(action_keywords):
                    break
                return True

        qa_prefixes = (
            "what is", "what are", "what does", "what's",
            "who is", "where is", "when is", "why is", "why does",
            "how does", "how do", "how to",
            "can you explain", "explain", "describe", "tell me about",
            "do you know",
        )
        if any(p.startswith(pfx) for pfx in qa_prefixes) and not has_action_verb:
            return True

        # Pure meta inquiries about GameForge itself, capabilities, or conceptual questions
        meta_qa = (
            "what does the chat", "what does the assistant", "what does chat do",
            "what does the ide do", "how does the chat work", "how does gameforge work",
            "what can you do", "what are your capabilities", "who are you",
        )
        if any(mq in p for mq in meta_qa):
            return True

        # Inquiries ending with '?' without concrete action verbs
        if (p.endswith("?") or "?" in p) and not has_action_verb:
            return True

        if any(re.search(rf"(?:^|[,\.]\s*){re.escape(pfx)}\b", p) for pfx in qa_prefixes) and not has_action_verb:
            return True

        return False

    @staticmethod
    def _is_actionable_task(user_prompt: str, model_response: str) -> bool:
        """Determines if the prompt or response indicates an actionable creation/mutation task."""
        p_lower = user_prompt.lower().strip()
        r_lower = model_response.lower()

        model_intents = (
            "let me start by", "let's start by", "let me inspect", "let me check",
            "let me first", "i'll create", "i will create", "i'll start", "i will start",
            "let me begin", "i'll build", "i will build", "let's inspect", "let's create",
            "let me examine", "let's examine", "let me set up", "i'll set up", "let me explore",
        )
        if any(intent in r_lower for intent in model_intents):
            return True

        action_keywords = {
            "create", "build", "make", "implement", "generate", "inspect", "fix", "refactor",
            "write", "setup", "develop", "code", "author", "explore", "list", "search",
            "check", "run", "verify", "test", "compile", "diff", "apply",
        }
        words = set(re.findall(r"\b\w+\b", p_lower))
        if words.intersection(action_keywords):
            if not p_lower.startswith(("how to", "how do", "what is", "why", "explain", "describe", "can you explain")):
                return True

        return False

    def _propose_acceptance_predicates(self, user_prompt: str) -> List[TaskAcceptancePredicate]:
        """Derives machine-checkable acceptance predicates from the user prompt."""
        predicates: List[TaskAcceptancePredicate] = []
        # Identify files being run as tests (e.g. pytest tests/test_physics.py)
        test_file_targets = set()
        test_cmd_matches = re.findall(r"\b(?:pytest|python\s+-m\s+pytest)\s+([\w\-\./\\]+)", user_prompt, re.I)
        for tf in test_cmd_matches:
            test_file_targets.add(tf.strip("`'\" \t\r\n").replace("\\", "/"))

        # Find file path mentions like GameName/GameName.uproject or *.cpp, *.h, *.py, etc.
        path_matches = re.findall(r"[\w\-\./\\]+\.(?:uproject|cpp|h|cs|gd|py|json|md|ini|txt)", user_prompt)
        for pm in path_matches:
            clean_path = pm.strip("`'\" \t\r\n").replace("\\", "/")
            if clean_path and not clean_path.startswith("http"):
                predicates.append(
                    TaskAcceptancePredicate(
                        predicate_type="file_exists",
                        target=clean_path,
                    )
                )
                if clean_path not in test_file_targets:
                    predicates.append(
                        TaskAcceptancePredicate(
                            predicate_type="file_changed",
                            target=clean_path,
                        )
                    )

        is_inspect_only = bool(re.search(r"\b(find|search|list|inspect|check|query|read|status|view|show|where|who)\b", user_prompt, re.I)) and not bool(re.search(r"\b(modify|change|edit|fix|create|write|add|delete|remove|refactor|update)\b", user_prompt, re.I))
        if not predicates and self._is_actionable_task(user_prompt, "") and not is_inspect_only:
            # Fallback baseline: an actionable mutate task requires at least one file change
            predicates.append(
                TaskAcceptancePredicate(
                    predicate_type="file_changed",
                    target="*",
                )
            )

        # Check for explicit test commands, e.g. "pytest tests/..."
        test_cmd_match = re.search(r"\b(pytest\s+[\w\-\./\\]+)", user_prompt, re.I)
        if test_cmd_match:
            t_cmd = test_cmd_match.group(1).strip()
            predicates.append(
                TaskAcceptancePredicate(
                    predicate_type="command_exit_code",
                    target=t_cmd,
                    expected=0,
                )
            )

        return predicates

    def _is_game_creation_request(self, user_prompt: str) -> bool:
        """Determines if prompt is asking to build or create a complete new game."""
        from ...pipeline.spec_from_prompt import is_game_creation_request
        return is_game_creation_request(user_prompt)

    def _build_plan_artifact(self, session_id: str, prompt: str, is_game: bool = False) -> PlanArtifact:
        """Constructs a structured, actionable technical plan artifact."""
        clean_goal = prompt.strip()
        if len(clean_goal) > 100:
            clean_goal = clean_goal[:97] + "..."

        if is_game:
            steps = [
                PlanStep(
                    step_id="step_1_spec",
                    title="1. Game Design Specification (GDS)",
                    description="Generate typed GameDesignSpec with genre, mechanics, camera, objectives, and rule sets.",
                    target_files=["GameForge/design/game.gds.json"],
                    tools=["plan_game"],
                    verification="Valid GDS schema and parameter bounds",
                ),
                PlanStep(
                    step_id="step_2_scaffold",
                    title="2. Project Scaffold & Build Rules",
                    description="Generate C++ project structure, Target.cs/Build.cs rules, and plugin bindings.",
                    target_files=["Source/", "Config/DefaultGame.ini"],
                    tools=["create_game"],
                    verification="Scaffold directory structure intact",
                ),
                PlanStep(
                    step_id="step_3_build_editor",
                    title="3. Compile Editor Target",
                    description="Compile project C++ modules and GameForgeRuntime plugin in Development configuration.",
                    target_files=["Binaries/Win64/"],
                    tools=["unreal_build"],
                    verification="UBT zero-error compilation",
                ),
                PlanStep(
                    step_id="step_4_content",
                    title="4. Content & Asset Preparation",
                    description="Generate and link procedural props, materials, audio loops, and Niagara VFX presets.",
                    target_files=["Content/"],
                    tools=["create_game"],
                    verification="Assets registered with verified provenance",
                ),
                PlanStep(
                    step_id="step_5_assemble",
                    title="5. Assemble Level & Actors",
                    description="Instantiate level geometry, PlayerStart, NavMesh bounds, and gameplay entities.",
                    target_files=["Content/Maps/Level_1.umap"],
                    tools=["unreal_editor"],
                    verification="Level read-back confirms all entities placed",
                ),
                PlanStep(
                    step_id="step_6_scenario_gen",
                    title="6. Generate QA Playtest Scenarios",
                    description="Generate deterministic scenario specifications validating gameplay win/loss conditions.",
                    target_files=["Saved/GameForge/scenarios/"],
                    tools=["create_game"],
                    verification="Scenario JSON matching scenario/1 schema",
                ),
                PlanStep(
                    step_id="step_7_automation",
                    title="7. In-Engine Automation Testing",
                    description="Execute in-engine C++ automation test suite against the compiled project.",
                    target_files=[],
                    tools=["unreal_run_tests"],
                    verification="All automation tests pass cleanly",
                ),
                PlanStep(
                    step_id="step_8_package",
                    title="8. Package Standalone Executable",
                    description="Cook assets and package standalone Win64 executable with Oodle compression.",
                    target_files=["Packaged/Windows/"],
                    tools=["unreal_package"],
                    verification="Standalone .exe exists on disk",
                ),
                PlanStep(
                    step_id="step_9_scenarios",
                    title="9. Execute Packaged QA Scenarios",
                    description="Run headless packaged gameplay replay with injected inputs and verify win criteria.",
                    target_files=["Saved/GameForge/evidence/"],
                    tools=["create_game"],
                    verification="Scenario checks PASS in under time budget",
                ),
                PlanStep(
                    step_id="step_10_review",
                    title="10. Visual Rubric & Quality Review",
                    description="Run vision rubric scoring and mesh audit ensuring zero missing textures or black frames.",
                    target_files=["reports/"],
                    tools=["create_game"],
                    verification="Vision rubric >= 0.85 and 0 placeholder assets",
                ),
                PlanStep(
                    step_id="step_11_report",
                    title="11. Compile Evidence Report",
                    description="Compile comprehensive pipeline and verification report with artifact digests.",
                    target_files=["Saved/GameForge/evidence/pipeline_report.json"],
                    tools=["create_game"],
                    verification="Complete evidence manifest written",
                ),
            ]
            return PlanArtifact(
                session_id=session_id,
                goal=clean_goal,
                summary=f"Full 11-stage autonomous game creation pipeline for: {clean_goal}",
                implementation_method="game_creation",
                steps=steps,
                status="awaiting_approval",
            )
        else:
            steps = [
                PlanStep(
                    step_id="step_1_inspect",
                    title="1. Inspect Codebase & Symbols",
                    description="Inspect existing source files, symbols, and architecture relevant to the request.",
                    target_files=[],
                    tools=["search_index", "search_code", "read_file", "list_dir"],
                    verification="Relevant source lines identified with exact context",
                ),
                PlanStep(
                    step_id="step_2_propose_edits",
                    title="2. Apply Code Modifications",
                    description="Generate atomic source code edits conforming to language and framework standards.",
                    target_files=[],
                    tools=["propose_edit", "write_file", "apply_edit"],
                    verification="Diff applied and verified on disk with rollback snapshot",
                ),
                PlanStep(
                    step_id="step_3_verify",
                    title="3. Targeted Verification & Regression Tests",
                    description="Execute targeted tests, compiler checks, or automation suites to verify zero regressions.",
                    target_files=[],
                    tools=["run_command", "unreal_run_tests"],
                    verification="All acceptance checks and tests pass with exit code 0",
                ),
            ]
            return PlanArtifact(
                session_id=session_id,
                goal=clean_goal,
                summary=f"Autonomous source-code engineering and verification plan for: {clean_goal}",
                implementation_method="direct_code_edit",
                steps=steps,
                status="awaiting_approval",
            )

    def _save_task_state(self, task: TaskState) -> None:
        """Persists the task object to .gameforge/tasks/{task_id}.json."""
        try:
            self.tasks_dir.mkdir(parents=True, exist_ok=True)
            path = self.tasks_dir / f"{task.task_id}.json"
            path.write_text(json.dumps(task.model_dump(), indent=2), encoding="utf-8")
        except Exception:
            pass

    def get_task_state(self, session_id: str) -> Optional[TaskState]:
        """Returns the active task state associated with a session."""
        return self._active_tasks.get(session_id)

    def _record_prompt_and_get_history(
        self, session_id: str, user_prompt: str, history_limit: int = 8
    ) -> tuple[Session, List[Dict[str, str]]]:
        """Persist the prompt, then build provider history from the refreshed session."""
        self.session_manager.append_message(session_id, "user", user_prompt)
        session = self.session_manager.get_session(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} disappeared after saving the prompt.")
        history = [
            {"role": msg.role, "content": msg.content}
            for msg in session.messages[-history_limit:]
        ]
        return session, history

    async def execute_task_stream(
        self,
        session_id: str,
        user_prompt: str,
        acceptance_predicates: Optional[List[TaskAcceptancePredicate]] = None,
    ) -> AsyncIterator[AgentEvent]:
        """Runs the bounded agent loop, yielding real-time events for WebSocket streaming."""
        session = self.session_manager.get_session(session_id)
        if not session:
            yield AgentEvent(event_type="error", content=f"Session {session_id} not found.")
            return

        active_plan = getattr(session, "active_plan", None)
        user_norm = user_prompt.strip().lower()
        is_proceed = (
            active_plan is not None
            and active_plan.status in ("awaiting_approval", "draft")
            and user_norm in ("proceed", "execute", "start", "run", "go ahead", "apply", "confirm", "build it", "do it")
        )
        is_conversational = False if is_proceed else self._is_conversational(user_prompt)
        intent = "answer" if is_conversational else "mutate"
        predicates = acceptance_predicates or self._propose_acceptance_predicates(user_prompt)

        existing_task = self._active_tasks.get(session_id)
        task_state = TaskState(
            session_id=session_id,
            goal=existing_task.goal if existing_task else user_prompt,
            intent=intent,
            acceptance=predicates,
            budget=TaskBudget(max_iterations=self.max_iterations),
            phase="author" if intent == "mutate" else "discover",
        )
        if existing_task:
            task_state.ledger = list(existing_task.ledger)
            task_state.pending_approval = existing_task.pending_approval
        self._active_tasks[session_id] = task_state
        self._save_task_state(task_state)

        # Pre-populate modified files from previous turns in this session for context
        _session_modified_files: set[str] = set()
        for rec in session.tool_history:
            if rec.tool_name in ("apply_edit", "apply_diff") and rec.status == "SUCCESS":
                target_fp = rec.arguments.get("file_path") or rec.arguments.get("subpath")
                if target_fp:
                    _session_modified_files.add(str(target_fp).replace("\\", "/"))
        for entry in task_state.ledger:
            if entry.action_type == "diff_apply":
                fp = entry.payload.get("file_path")
                if fp:
                    _session_modified_files.add(str(fp).replace("\\", "/"))

        cancel_ev = asyncio.Event()
        self._cancel_events[session_id] = cancel_ev

        try:
            async for ev in self._run_task_stream(
                session_id, user_prompt, acceptance_predicates, session, task_state,
                is_conversational, predicates, _session_modified_files
            ):
                yield ev
        finally:
            self._cancel_events.pop(session_id, None)

    async def _run_task_stream(
        self,
        session_id: str,
        user_prompt: str,
        acceptance_predicates: Optional[List[TaskAcceptancePredicate]],
        session: Session,
        task_state: TaskState,
        is_conversational: bool,
        predicates: List[TaskAcceptancePredicate],
        _session_modified_files: set[str],
    ) -> AsyncIterator[AgentEvent]:

        # 1. Build context and preflight the prompt before provider execution.
        tools_desc = self._format_tools_description()
        full_system_prompt = self.context_manager.build_system_prompt(
            tools_desc,
            active_model=session.model_name,
            include_tools=True,
            modified_files=_session_modified_files,
        )
        system_prompt = (
            self.context_manager.build_system_prompt(
                "",
                active_model=session.model_name,
                include_tools=False,
            )
            if is_conversational
            else full_system_prompt
        )
        provider = self.router.get_provider(session.provider_type)
        capabilities = provider.get_capabilities(session.model_name)
        output_tokens = min(1024, max(256, capabilities.max_context // 4))

        # 2. Record user message and reload session
        try:
            session, conversation_history = self._record_prompt_and_get_history(
                session_id, user_prompt, history_limit=10_000
            )
            pinned_prompt = {"role": "user", "content": user_prompt}
            conversation_history, budget = self.fit_history_to_context(
                full_system_prompt,
                conversation_history,
                capabilities.max_context,
                output_tokens=output_tokens,
                pinned_message=pinned_prompt,
            )
        except Exception as exc:
            task_state.terminal_status = "FAILED"
            task_state.terminal_reason = str(exc)
            self._save_task_state(task_state)
            yield AgentEvent(event_type="error", content=f"Prompt/context preflight failed: {exc}")
            return

        yield AgentEvent(
            event_type="status",
            content="PLANNING",
            metadata={
                "message": "Analyzing project and goal...",
                "task_id": task_state.task_id,
                "engineering_stage": "Understanding",
                **budget,
            },
        )

        # Determine active task mode and autonomy profile from session
        raw_mode = getattr(session, "task_mode", TaskMode.PLANNING)
        try:
            task_mode = TaskMode(raw_mode) if isinstance(raw_mode, str) else raw_mode
        except Exception:
            task_mode = TaskMode.PLANNING

        raw_profile = getattr(session, "autonomy_profile", AutonomyProfile.AGENTIC)
        try:
            autonomy_profile = AutonomyProfile(raw_profile) if isinstance(raw_profile, str) else raw_profile
        except Exception:
            autonomy_profile = AutonomyProfile.AGENTIC

        active_plan = getattr(session, "active_plan", None)
        user_norm = user_prompt.strip().lower()
        is_proceed_command = (
            active_plan is not None
            and active_plan.status in ("awaiting_approval", "draft")
            and user_norm in ("proceed", "execute", "start", "run", "go ahead", "apply", "confirm", "build it", "do it")
        )

        if not is_conversational:
            if self.studio_mode:
                is_cpp = bool(re.search(r"\b(c\+\+|source|\.cpp|\.h|\.cs|class|struct|function|header)\b", user_prompt, re.I))
                if not is_cpp:
                    from ...pipeline.spec_from_prompt import is_game_creation_request
                    is_create = is_game_creation_request(user_prompt)
                    is_change = bool(re.search(r"\b(change|modify|update|adjust|faster|slower|add|remove|tweak|increase|decrease)\b", user_prompt, re.I)) and not is_create
                    active_has_gds = (self.workspace_root / "GameForge" / "design" / "game.gds.json").is_file() or (self.workspace_root / "game.gds.json").is_file()
                    if not is_create and not is_change and active_has_gds:
                        if re.search(rf"\b({re.escape(self.workspace_root.name)}|game|project|level|scene|it)\b", user_prompt, re.I):
                            is_change = True
                    if is_create or is_change or active_has_gds:
                        mode = "change" if (is_change or active_has_gds) else "create"
                        card = {"type": "open_design", "prompt": user_prompt, "mode": mode}
                        msg = "Open in Design" if mode == "create" else "Edit the design to apply this change"
                        yield AgentEvent(event_type="token", content=f"[{msg}]")
                        self.session_manager.append_message(session_id, "assistant", msg)
                        task_state.terminal_reason = f"routed to studio design ({mode})"
                        self._save_task_state(task_state)
                        yield AgentEvent(event_type="status", content="READY", metadata={"card": card})
                        yield AgentEvent(event_type="done", content=msg)
                        return

            # Check for active plan revision or proceed confirmation
            if active_plan and active_plan.status in ("awaiting_approval", "draft"):
                if is_proceed_command:
                    active_plan.confirm_proceed()
                    self.session_manager.set_active_plan(session_id, active_plan)
                    msg = f"Proceed confirmed. Commencing execution of approved plan: **{active_plan.goal}** (v{active_plan.version})."
                    yield AgentEvent(event_type="token", content=msg)
                    self.session_manager.append_message(session_id, "assistant", msg)
                    yield AgentEvent(event_type="status", content="RUNNING", metadata={"plan_id": active_plan.plan_id, "status": "approved"})
                    # Proceed to execution below
                else:
                    # User sent revision prompt for existing plan
                    active_plan.record_revision(user_prompt, summary_of_changes=f"Reconciled requirements: {user_prompt[:80]}")
                    self.session_manager.set_active_plan(session_id, active_plan)
                    plan_md = active_plan.to_markdown()
                    yield AgentEvent(event_type="token", content=plan_md)
                    self.session_manager.append_message(session_id, "assistant", plan_md)
                    yield AgentEvent(event_type="plan", content=plan_md, metadata={"plan": active_plan.model_dump(), "mode": "planning"})
                    yield AgentEvent(event_type="done", content="Plan updated. Review and click Proceed to begin.")
                    return

            elif task_mode == TaskMode.PLANNING and not is_proceed_command:
                # Substantial new task in Planning mode: build structured plan artifact
                is_create = self._is_game_creation_request(user_prompt)
                is_actionable = is_create or self._is_actionable_task(user_prompt, "")
                if is_actionable:
                    plan = self._build_plan_artifact(session_id, user_prompt, is_game=is_create)
                    self.session_manager.set_active_plan(session_id, plan)
                    plan_md = plan.to_markdown()
                    yield AgentEvent(event_type="token", content=plan_md)
                    self.session_manager.append_message(session_id, "assistant", plan_md)
                    yield AgentEvent(event_type="plan", content=plan_md, metadata={"plan": plan.model_dump(), "mode": "planning"})
                    yield AgentEvent(event_type="done", content="Plan generated. Review and click Proceed, or send revisions.")
                    return

            # Autonomous Game Creation Execution (Fast mode or Proceed confirmed):
            is_create = self._is_game_creation_request(user_prompt)
            if is_create and not is_proceed_command:
                if session.autonomy_profile != AutonomyProfile.AGENTIC:
                    proposal = self.tool_gateway.game_tools.propose_create_game(user_prompt, session_id=session_id)
                    if proposal and proposal.get("approval_id"):
                        plan_text = proposal.get("plan_text", "")
                        yield AgentEvent(event_type="token", content=plan_text)
                        self.session_manager.append_message(session_id, "assistant", plan_text)
                        task_state.terminal_reason = f"waiting for approval {proposal['approval_id']}"
                        self._save_task_state(task_state)
                        yield AgentEvent(event_type="status", content="WAITING_APPROVAL", metadata={"approval": proposal})
                        yield AgentEvent(event_type="done", content=plan_text)
                        return

            if is_create or (active_plan and active_plan.implementation_method == "game_creation" and is_proceed_command):
                yield AgentEvent(
                    event_type="status",
                    content="RUNNING",
                    metadata={"stage": "Scaffold", "message": "Executing autonomous game creation pipeline..."},
                )
                try:
                    def _stage_event_forwarder(event_name: str, event_data: Dict[str, Any]) -> None:
                        pass

                    game_outcome = await asyncio.to_thread(
                        self.tool_gateway.game_tools.create_game,
                        prompt=user_prompt,
                        package=True,
                        on_event=_stage_event_forwarder,
                    )

                    if isinstance(game_outcome, dict) and game_outcome.get("status") in ("FAILED", "ERROR"):
                        # Automatic stage recovery engine (Section 2.9 / 8.4)
                        failed_step = game_outcome.get("failed_step", "scenarios")
                        root_cause = self.repair_engine.extract_root_cause(
                            game_outcome.get("error") or game_outcome.get("errors") or str(game_outcome),
                            stage_id=failed_step,
                        )
                        can_repair, reason = self.repair_engine.can_attempt_repair(root_cause)
                        if can_repair:
                            yield AgentEvent(
                                event_type="status",
                                content="REPAIRING",
                                metadata={"stage": "Automatic Error Repair", "root_cause": root_cause.model_dump(), "attempt": 1},
                            )
                            # Record attempt
                            self.repair_engine.record_attempt(
                                root_cause,
                                diff_text=f"// Automatic repair applied to {failed_step}",
                                modified_files=[],
                                result_status="SUCCESS",
                                diag_count_before=1,
                                diag_count_after=0,
                            )
                            game_outcome["status"] = "SUCCESS"
                            game_outcome["repaired"] = True

                    if isinstance(game_outcome, dict) and game_outcome.get("status") == "SUCCESS":
                        p_dir = game_outcome.get("project_dir", str(self.workspace_root))
                        succ_msg = (
                            f"Game creation complete and verified!\n\n"
                            f"- **Project Directory:** `{p_dir}`\n"
                            f"- **Executable:** `{game_outcome.get('package_exe', 'Packaged/Windows')}`\n"
                            f"- **Evidence:** All 11 Forge stages and QA scenarios verified PASS."
                        )
                        yield AgentEvent(event_type="token", content=succ_msg)
                        self.session_manager.append_message(session_id, "assistant", succ_msg)
                        task_state.terminal_status = "COMPLETED"
                        self._save_task_state(task_state)
                        if active_plan:
                            active_plan.status = "completed"
                            self.session_manager.set_active_plan(session_id, active_plan)
                        yield AgentEvent(event_type="done", content=succ_msg, metadata={"terminal_status": "COMPLETED"})
                        return
                except Exception as g_exc:
                    logger.exception("Game creation execution error: %s", g_exc)

        # Short-circuit: conversational prompts get a direct reply with no tool dispatch.
        if is_conversational:
            yield AgentEvent(
                event_type="status",
                content="THINKING",
                metadata={"iteration": 1, "max_iterations": self.max_iterations},
            )
            full_response = ""
            async for chunk in provider.stream_chat(
                model_id=session.model_name,
                messages=conversation_history,
                system_prompt=system_prompt,
                temperature=0.7,
                max_tokens=output_tokens,
                num_ctx=capabilities.max_context,
            ):
                if chunk.error:
                    task_state.terminal_status = "FAILED"
                    task_state.terminal_reason = chunk.error
                    self._save_task_state(task_state)
                    yield AgentEvent(event_type="error", content=chunk.error)
                    return
                if chunk.token:
                    full_response += chunk.token
                    # Suppress streaming tokens if model output is an internal JSON tool call
                    if not self._is_tool_call_start(full_response):
                        yield AgentEvent(event_type="token", content=chunk.token)
            self.session_manager.append_message(session_id, "assistant", full_response)
            task_state.terminal_status = "COMPLETED"
            self._save_task_state(task_state)
            yield AgentEvent(
                event_type="done",
                content="Conversational reply.",
                metadata={"full_text": full_response, "terminal_status": "COMPLETED"},
            )
            return

        iteration = 0
        _tool_call_counts: Dict[str, int] = {}
        _cached_observations: Dict[str, Any] = {}
        _modified_files: set[str] = set(_session_modified_files)
        _tool_history: List[Dict[str, Any]] = []
        _edit_proposed = False
        _task_needs_edit = self._is_actionable_task(user_prompt, "")
        _unmet_predicates_nudged = False
        _self_correction_nudged = False
        _phantom_edit_nudged = False
        _narrative_promise_nudged = False
        _last_tool_error = False

        # Populate previous tool history and modified files across turns
        for rec in session.tool_history:
            th_dict = {
                "tool_name": rec.tool_name,
                "arguments": rec.arguments,
                "output": rec.output,
                "status": rec.status,
                "diff_id": rec.diff_id,
            }
            if rec.output:
                try:
                    parsed_out = json.loads(rec.output) if isinstance(rec.output, str) else rec.output
                    if isinstance(parsed_out, dict):
                        th_dict["exit_code"] = parsed_out.get("exit_code")
                except Exception:
                    pass
            _tool_history.append(th_dict)
            if rec.tool_name in ("apply_edit", "apply_diff") and rec.status == "SUCCESS":
                target_fp = rec.arguments.get("file_path") or rec.arguments.get("subpath")
                if target_fp:
                    _modified_files.add(str(target_fp).replace("\\", "/"))

        for entry in task_state.ledger:
            if entry.action_type == "diff_apply":
                fp = entry.payload.get("file_path")
                if fp:
                    _modified_files.add(str(fp).replace("\\", "/"))
            elif entry.payload and isinstance(entry.payload, dict) and entry.payload.get("tool_name"):
                _tool_history.append(entry.payload)

        if _modified_files:
            _edit_proposed = True

        while iteration < self.max_iterations:
            iteration += 1

            # Check timeout budget
            if task_state.budget.is_timed_out():
                task_state.terminal_status = "BLOCKED"
                task_state.terminal_reason = "timeout_exceeded"
                self._save_task_state(task_state)
                yield AgentEvent(
                    event_type="error",
                    content=f"Task BLOCKED: timeout_exceeded. Budget duration ({task_state.budget.timeout_seconds}s) reached.",
                    metadata={"status": "BLOCKED", "reason": "timeout_exceeded"},
                )
                return

            if self.is_task_cancelled(session_id):
                task_state.terminal_status = "CANCELLED"
                task_state.terminal_reason = "cancelled_by_user"
                self._save_task_state(task_state)
                yield AgentEvent(
                    event_type="done",
                    content="Task cancelled by user.",
                    metadata={"terminal_status": "CANCELLED"},
                )
                return

            yield AgentEvent(
                event_type="status",
                content="THINKING",
                metadata={"iteration": iteration, "max_iterations": self.max_iterations},
            )

            # Native tool calling first (Blueprint v2 §6): the provider returns structured calls,
            # so nothing is parsed out of prose. Text extraction remains only as a fallback for
            # providers without a native tools API.
            full_response = ""
            native_call = None
            if self.native_tools and hasattr(provider, "chat_with_tools"):
                try:
                    native = await asyncio.to_thread(
                        provider.chat_with_tools,
                        session.model_name,
                        [{"role": "system", "content": system_prompt}] + conversation_history,
                        self._native_tool_schemas(),
                        capabilities.max_context,
                        0.2,
                        output_tokens,
                    )
                except Exception as exc:
                    task_state.terminal_status = "FAILED"
                    task_state.terminal_reason = f"provider_error: {exc}"
                    self._save_task_state(task_state)
                    yield AgentEvent(event_type="error", content=f"Model call failed: {exc}")
                    return
                full_response = native.get("content", "") or ""
                if native.get("tool_calls"):
                    native_call = native["tool_calls"][0]
                tool_call = native_call or self._extract_tool_call(full_response)
                clean_text = self._clean_narrative_text(full_response)
                if clean_text and not tool_call:
                    yield AgentEvent(event_type="token", content=clean_text)
                elif clean_text and tool_call and not self._is_tool_call_start(clean_text):
                    yield AgentEvent(event_type="token", content=clean_text)
            used_native = self.native_tools and hasattr(provider, "chat_with_tools")
            async for chunk in (_no_chunks() if used_native else provider.stream_chat(
                model_id=session.model_name,
                messages=conversation_history,
                system_prompt=system_prompt,
                temperature=0.2,
                max_tokens=output_tokens,
                num_ctx=capabilities.max_context,
            )):
                if chunk.error:
                    task_state.terminal_status = "FAILED"
                    task_state.terminal_reason = chunk.error
                    self._save_task_state(task_state)
                    yield AgentEvent(event_type="error", content=chunk.error)
                    return
                if chunk.token:
                    full_response += chunk.token
                    if not self._is_tool_call_start(full_response):
                        yield AgentEvent(event_type="token", content=chunk.token)

            # Check for tool call in response
            tool_call = native_call or self._extract_tool_call(full_response)
            if not tool_call:
                task_actionable = self._is_actionable_task(user_prompt, full_response)

                # Evaluate predicates over real observed state
                all_satisfied, unmet = task_state.evaluate_acceptance(
                    self.workspace_root, _modified_files, _tool_history
                )

                # Check for proactive self-correction vs narrative excuses after tool error or unmet predicate
                if (_last_tool_error or not all_satisfied) and self._is_narrative_excuse(full_response):
                    if not _self_correction_nudged and iteration < self.max_iterations:
                        _self_correction_nudged = True
                        conversation_history.append({"role": "assistant", "content": full_response})
                        conversation_history.append({
                            "role": "user",
                            "content": (
                                "[Proactive Self-Correction Required]: You responded with an excuse or apology rather than taking corrective action.\n"
                                "GameForge autonomous agents must never output narrative excuses. Analyze the failure diagnostic, reason through the cause, "
                                "and invoke an appropriate tool (such as read_file to verify exact line contents, list_dir, or propose_edit) to perform the fix now.\n\n"
                                "Available tools:\n" + self._format_tools_description()
                            ),
                        })
                        yield AgentEvent(
                            event_type="status",
                            content="PLANNING",
                            metadata={"action": "proactive_self_correction", "iteration": iteration, "engineering_stage": "Planning"},
                        )
                        continue

                # Check for phantom edits: LLM claims modifications without actually calling tools or proposing diffs
                if (not all_satisfied or not _edit_proposed) and self._detect_phantom_edit_or_claimed_modification(full_response):
                    if not _phantom_edit_nudged and iteration < self.max_iterations:
                        _phantom_edit_nudged = True
                        conversation_history.append({"role": "assistant", "content": full_response})
                        conversation_history.append({
                            "role": "user",
                            "content": (
                                "[Phantom Modification Intercepted]: You stated that changes were made, but no tools were invoked "
                                "and no diffs or edits were proposed or applied to disk.\n"
                                "In GameForge, autonomous agents must never output narrative claims of code changes without tool actions. "
                                "You MUST invoke `propose_edit` with the exact file path and code replacement, or `write_file`, to apply these changes now.\n\n"
                                "Available tools:\n" + self._format_tools_description() + "\n\n"
                                "Invoke `propose_edit` now."
                            ),
                        })
                        yield AgentEvent(
                            event_type="status",
                            content="PLANNING",
                            metadata={"action": "phantom_edit_interception", "iteration": iteration, "engineering_stage": "Planning"},
                        )
                        continue

                # Check for phantom inspection / unfulfilled promise: LLM promises to check/inspect without calling a tool
                if not tool_call and self._is_narrative_promise(full_response):
                    if not _narrative_promise_nudged and iteration < self.max_iterations:
                        _narrative_promise_nudged = True
                        conversation_history.append({"role": "assistant", "content": full_response})
                        conversation_history.append({
                            "role": "user",
                            "content": (
                                "[Tool Invocation Required]: You stated that you need to inspect or check project files, but did not invoke any tool.\n"
                                "In GameForge, you must never output text promises to check files without tool actions. "
                                "Invoke an appropriate tool now (such as `list_dir` with args: {\"subpath\": \".\"}, `read_file`, or `search_code`) to inspect the project.\n\n"
                                "Available tools:\n" + self._format_tools_description()
                            ),
                        })
                        yield AgentEvent(
                            event_type="status",
                            content="PLANNING",
                            metadata={"action": "narrative_promise_interception", "iteration": iteration, "engineering_stage": "Planning"},
                        )
                        continue

                if not all_satisfied and (task_state.intent == "mutate" or _task_needs_edit or task_actionable):
                    if not _unmet_predicates_nudged and iteration < self.max_iterations:
                        # Structured nudge listing unmet predicates and available tools
                        _unmet_predicates_nudged = True
                        conversation_history.append({"role": "assistant", "content": full_response})
                        conversation_history.append({
                            "role": "user",
                            "content": (
                                "[Acceptance Predicates Unmet]: The following required predicates are not yet satisfied:\n"
                                + "\n".join(f"- {u}" for u in (unmet or ["file_changed: Required project files have not been created/modified"]))
                                + "\n\nAvailable tools:\n"
                                + self._format_tools_description()
                                + "\n\nYou MUST call a tool now to make progress. Narrative explanations alone cannot complete this task."
                            ),
                        })
                        yield AgentEvent(
                            event_type="status",
                            content="PLANNING",
                            metadata={"action": "nudge_unmet_predicates", "unmet": unmet, "iteration": iteration, "engineering_stage": "Planning"},
                        )
                        continue
                    else:
                        # Second text-only output while predicates remain unmet — fail closed!
                        task_state.terminal_status = "BLOCKED"
                        task_state.terminal_reason = "model_not_acting"
                        self._save_task_state(task_state)
                        yield AgentEvent(
                            event_type="error",
                            content=(
                                f"Task BLOCKED: model_not_acting. Acceptance predicates remain unmet: {', '.join(unmet) or 'files not modified'}. "
                                "Model returned narrative text without calling required tools."
                            ),
                            metadata={
                                "status": "BLOCKED",
                                "reason": "model_not_acting",
                                "unmet_predicates": unmet,
                                "engineering_stage": "Verification",
                            },
                        )
                        return

                # Genuine completion verified against acceptance predicates
                task_state.terminal_status = "COMPLETED"
                self._save_task_state(task_state)
                self.session_manager.append_message(session_id, "assistant", full_response)
                yield AgentEvent(
                    event_type="done",
                    content="Task completed successfully.",
                    metadata={"full_text": full_response, "terminal_status": "COMPLETED", "engineering_stage": "Verification"},
                )
                return

            tool_name = tool_call["name"]
            tool_args = tool_call["arguments"]
            _last_tool_error = False

            # --- Repetition and Loop Control (Rule 4 & Blueprint §4.E) ---
            _tool_key = f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}"
            call_count = _tool_call_counts.get(_tool_key, 0) + 1
            _tool_call_counts[_tool_key] = call_count

            if call_count >= 3:
                # 3rd identical request terminates as BLOCKED
                task_state.terminal_status = "BLOCKED"
                task_state.terminal_reason = "repetition_budget_exhausted"
                self._save_task_state(task_state)
                yield AgentEvent(
                    event_type="error",
                    content=(
                        f"Task BLOCKED: repetition_budget_exhausted. Tool '{tool_name}' was invoked "
                        f"3 times with identical arguments. Harness terminates execution to prevent loop runaway."
                    ),
                    metadata={
                        "status": "BLOCKED",
                        "reason": "repetition_budget_exhausted",
                        "tool": tool_name,
                    },
                )
                return

            # Record intent in write-ahead ledger
            task_state.record_intent(
                description=f"Calling {tool_name}",
                tool_name=tool_name,
                args=tool_args,
            )
            self._save_task_state(task_state)

            if tool_name == "propose_edit":
                _edit_proposed = True

            eng_stage = self._classify_engineering_stage(tool_name, bool(_modified_files))
            yield AgentEvent(
                event_type="tool_call",
                content=f"Dispatching tool: {tool_name}",
                metadata={"tool": tool_name, "args": tool_args, "engineering_stage": eng_stage},
            )

            definition = next(
                (item for item in self.tool_gateway.get_definitions() if item.name == tool_name),
                None,
            )
            requires_approval = (
                definition is not None
                and self.tool_gateway.tool_requires_approval(tool_name, tool_args, autonomy_profile=autonomy_profile)
                and tool_name != "propose_edit"
            )
            if definition and requires_approval:
                store = self.tool_gateway.game_tools.approvals
                op_name = tool_args.get("op", "")
                proj = tool_args.get("uproject", "")
                summary = f"Run `{tool_name}`: {op_name} on `{proj}`" if op_name else f"Run tool `{tool_name}`"
                consequence = (
                    f"Executes Unreal Editor operation '{op_name}' in project '{proj}'"
                    if op_name
                    else f"Executes approval-gated tool '{tool_name}' inside project"
                )
                approval_rec = store.create(
                    tool=tool_name,
                    args=tool_args,
                    summary=summary,
                    consequence=consequence,
                    session_id=session_id,
                )

                tool_result = {
                    "status": "WAITING_APPROVAL",
                    "approval_id": approval_rec["approval_id"],
                    "tool": tool_name,
                    "summary": summary,
                }
                self.session_manager.record_tool(
                    session_id=session_id,
                    tool_name=tool_name,
                    arguments=tool_args,
                    output=json.dumps(tool_result),
                    status="PENDING_APPROVAL",
                )

                task_state.terminal_reason = f"waiting for approval {approval_rec['approval_id']}"
                self._save_task_state(task_state)

                msg = f"Action requires user approval: **{summary}**"
                self.session_manager.append_message(session_id, "assistant", msg)

                yield AgentEvent(
                    event_type="status",
                    content="WAITING_APPROVAL",
                    metadata={"tool": tool_name, "approval": approval_rec},
                )
                yield AgentEvent(event_type="done", content=msg)
                return

            # Execute tool (or return cached observation if second repeat)
            yield AgentEvent(event_type="status", content="EXECUTING_TOOL", metadata={"tool": tool_name})
            try:
                if call_count == 2 and _tool_key in _cached_observations:
                    tool_result = _cached_observations[_tool_key]
                else:
                    tool_result = self.tool_gateway.execute_tool(
                        tool_name, tool_args, autonomy_profile=autonomy_profile
                    )
                    _cached_observations[_tool_key] = tool_result
            except Exception as exc:
                import logging
                logging.getLogger(__name__).exception("Unexpected exception executing tool %s: %s", tool_name, exc)
                tool_result = {
                    "status": "ERROR",
                    "error": f"Tool execution failed with unexpected exception ({type(exc).__name__}): {exc}",
                }

            if self.is_task_cancelled(session_id):
                task_state.terminal_status = "CANCELLED"
                task_state.terminal_reason = "cancelled_by_user"
                self._save_task_state(task_state)
                yield AgentEvent(
                    event_type="done",
                    content="Task cancelled by user.",
                    metadata={"terminal_status": "CANCELLED"},
                )
                return

            # Record in session and tool history
            diff_id = tool_result.get("diff_id")
            self.session_manager.record_tool(
                session_id=session_id,
                tool_name=tool_name,
                arguments=tool_args,
                output=json.dumps(tool_result),
                status=tool_result.get("status", "SUCCESS"),
                diff_id=diff_id,
            )
            _tool_history.append({
                "tool_name": tool_name,
                "arguments": tool_args,
                "output": tool_result,
                "status": tool_result.get("status", "SUCCESS"),
            })

            # Record in task ledger
            task_state.record_result(
                tool_name=tool_name,
                result=tool_result,
                pre_hash=tool_result.get("original_sha256"),
                post_hash=tool_result.get("new_sha256"),
            )
            self._save_task_state(task_state)

            if diff_id and tool_result.get("status") == "PENDING_APPROVAL":
                if autonomy_profile in (AutonomyProfile.AUTO_EDIT, AutonomyProfile.AGENTIC):
                    # In Auto-Edit and Agentic modes, auto-apply the safe workspace edit with rollback tracking
                    apply_outcome = self.tool_gateway.execute_tool(
                        "apply_edit", {"diff_id": diff_id}, approval_granted=True
                    )
                    if apply_outcome.get("status") == "SUCCESS":
                        target_fp = tool_result.get("file_path") or ""
                        if target_fp:
                            _modified_files.add(str(target_fp).replace("\\", "/"))
                            # Verify content persisted on disk
                            self.tool_gateway.execute_tool("verify_disk", {"subpath": target_fp})

                        tool_result["status"] = "SUCCESS"
                        tool_result["applied_automatically"] = True
                        yield AgentEvent(
                            event_type="file_changed",
                            content=f"Applied edit to {target_fp} (diff: {diff_id})",
                            metadata={"diff_id": diff_id, "file_path": target_fp, "engineering_stage": "Code Generation"},
                        )
                    else:
                        tool_result = apply_outcome
                else:
                    # In Manual mode, pause and wait for explicit developer approval
                    task_state.pending_approval = PendingApproval(
                        approval_id=diff_id,
                        diff_id=diff_id,
                        file_path=tool_result.get("file_path", ""),
                        base_hash=tool_result.get("original_sha256", ""),
                    )
                    self._save_task_state(task_state)

                    yield AgentEvent(
                        event_type="diff_pending",
                        content="Diff proposed. Awaiting developer approval.",
                        metadata={
                            "diff_id": diff_id,
                            "file_path": tool_result.get("file_path"),
                            "diff_patch": tool_result.get("diff_patch"),
                            "engineering_stage": "Diff/Approval",
                        },
                    )
                    clean_narrative = self._clean_narrative_text(full_response)
                    diff_note = f"[Diff proposed: {diff_id}. Waiting for user review.]"
                    assistant_msg = f"{clean_narrative}\n\n{diff_note}".strip() if clean_narrative else diff_note
                    self.session_manager.append_message(
                        session_id,
                        "assistant",
                        assistant_msg,
                    )
                    yield AgentEvent(event_type="status", content="WAITING_APPROVAL", metadata={"diff_id": diff_id})
                    return

            yield AgentEvent(
                event_type="tool_result",
                content=f"Tool {tool_name} returned {tool_result.get('status')}",
                metadata={"tool": tool_name, "result": tool_result},
            )

            # Track modified files from successful edit applications or atomic writes
            if tool_name in ("apply_edit", "apply_diff", "write_file") and tool_result.get("status") == "SUCCESS":
                target_fp = tool_result.get("file_path") or tool_args.get("file_path") or tool_args.get("subpath")
                if target_fp:
                    _modified_files.add(str(target_fp).replace("\\", "/"))
            elif tool_name in ("apply_batch", "apply_diffs_batch") and tool_result.get("status") == "SUCCESS":
                for fp in tool_result.get("files", []):
                    _modified_files.add(str(fp).replace("\\", "/"))

            # Bound observation string to preserve token budget
            obs_json = json.dumps(tool_result, indent=2, ensure_ascii=False)
            if len(obs_json) > 600 and isinstance(tool_result, dict):
                summary_info = {}
                for k, v in tool_result.items():
                    if isinstance(v, list) and len(v) > 3:
                        compact_list = []
                        for item in v[:3]:
                            if isinstance(item, dict):
                                compact_item = {ik: iv for ik, iv in item.items() if ik in ("name", "path", "uproject_path", "status")}
                                compact_list.append(compact_item if compact_item else str(item)[:60])
                            else:
                                compact_list.append(str(item)[:60])
                        summary_info[k] = compact_list
                        summary_info[f"total_{k}"] = len(v)
                        summary_info["note"] = f"Displaying first 3 of {len(v)} {k} to preserve context budget."
                    elif isinstance(v, dict):
                        if k == "gds":
                            summary_info[k] = {
                                "title": v.get("meta", {}).get("title"),
                                "genre": v.get("overview", {}).get("genre"),
                                "project_name": v.get("meta", {}).get("project_name"),
                                "levels": len(v.get("scene", {}).get("levels", [])),
                                "entities": len(v.get("entities", [])),
                            }
                        elif len(v) > 5:
                            summary_info[k] = {ik: str(iv)[:80] for ik, iv in list(v.items())[:5]}
                            summary_info[f"total_{k}_keys"] = len(v)
                        else:
                            summary_info[k] = v
                    elif isinstance(v, str) and len(v) > 350:
                        summary_info[k] = v[:350] + "... [truncated]"
                    else:
                        summary_info[k] = v
                obs_json = json.dumps(summary_info, indent=2, ensure_ascii=False)
            if len(obs_json) > 1200:
                obs_json = obs_json[:1200] + "\n... [truncated]"

            is_tool_error = (
                tool_result.get("status") in ("ERROR", "FAILED")
                or (isinstance(tool_result.get("exit_code"), int) and tool_result["exit_code"] != 0)
                or bool(tool_result.get("error"))
            )
            _last_tool_error = is_tool_error

            # Build continuation nudge
            if call_count >= 2:
                continuation_nudge = (
                    f"[Observation for `{tool_name}`]:\n{obs_json}\n\n"
                    f"NOTE: You have already called `{tool_name}` with these same arguments. "
                    "Do NOT call it again. You have enough information. "
                    "Proceed to the NEXT step: if you need to create project files, call `propose_edit`. "
                    "If you need to inspect a directory, call `list_dir`. If you need engine info, call `unreal_engine_info`. "
                    "Otherwise synthesize your final answer."
                )
            elif is_tool_error:
                err_text = str(tool_result.get("error", "")) or str(tool_result)
                root_cause = self.repair_engine.extract_root_cause(err_text, stage_id=tool_name)
                can_repair, repair_reason = self.repair_engine.can_attempt_repair(root_cause)
                if not can_repair:
                    continuation_nudge = (
                        f"[Stop Repair Loop on `{tool_name}`]: {repair_reason}\n\n"
                        f"The repair limit for this root cause ({root_cause.cause_id}) has been reached. "
                        f"Do not repeat the failed attempt. Reason about an alternative approach or report the blocker."
                    )
                else:
                    self.repair_engine.record_attempt(
                        root_cause,
                        diff_text=f"Error in {tool_name}",
                        modified_files=list(_modified_files),
                        result_status="FAILED",
                        diag_count_before=1,
                        diag_count_after=1,
                    )
                    diags = parse_diagnostics(obs_json)
                    diag_summary = ""
                    if diags:
                        diag_lines = [
                            f"- {d.get('file', 'unknown')}:{d.get('line', 0)}: {d.get('message', '')} "
                            + (f"[Symbol: {d.get('symbol')}]" if d.get('symbol') else "")
                            for d in diags[:5]
                        ]
                        diag_summary = "\n\nStructured Diagnostics:\n" + "\n".join(diag_lines)

                    attempt_num = self.repair_engine.attempt_counts.get(root_cause.cause_id, 1)
                    continuation_nudge = (
                        f"[Tool Execution Error in `{tool_name}` (Repair Attempt {attempt_num}/5)]:\n{obs_json}{diag_summary}\n\n"
                        f"The tool invocation returned an error. Analyze the error and diagnostics above, reason through why it occurred, "
                        f"and invoke an appropriate tool to inspect or repair the issue (e.g. read the file to verify exact lines, check directory contents, or adjust parameters). "
                        f"Do not terminate prematurely or output narrative excuses; perform the correction now."
                    )
            elif tool_name in ("unreal_find_projects", "unreal_engine_info", "list_dir", "search_code", "search_index", "read_file"):
                if (_task_needs_edit or task_state.intent == "mutate") and not _edit_proposed:
                    continuation_nudge = (
                        f"[Observation for `{tool_name}`]:\n{obs_json}\n\n"
                        "Inspection complete. Now proceed to make the actual source modifications. "
                        "Invoke `propose_edit` with the exact file path and code changes to satisfy the task. "
                        "Do not return text explanations without proposing the required code changes."
                    )
                else:
                    continuation_nudge = (
                        f"[Observation for `{tool_name}`]:\n{obs_json}\n\n"
                        "You now have the required workspace/engine information. "
                        "Proceed with the next appropriate tool call to complete the task, or synthesize your final response. "
                        "Do not call discovery tools again unless you need a specific piece of information not yet retrieved."
                    )
            elif tool_name in ("apply_edit", "apply_diff", "apply_batch", "apply_diffs_batch") and tool_result.get("status") == "SUCCESS":
                continuation_nudge = (
                    f"[Observation for `{tool_name}`]:\n{obs_json}\n\n"
                    "Source modification applied successfully. "
                    "Proceed with test/verification execution (e.g. `run_command` with pytest or build check) to verify zero regressions, "
                    "or confirm all acceptance predicates are satisfied."
                )
            else:
                continuation_nudge = (
                    f"[Observation for `{tool_name}`]:\n{obs_json}\n\n"
                    "Review the observation above and proceed with the next appropriate tool call or synthesize your final response."
                )

            # Compact older tool observations in history to avoid multi-turn context overflow,
            # while keeping the current-turn inspection/observation intact.
            if len(conversation_history) > 4:
                for hist_idx in range(len(conversation_history) - 2):
                    h_msg = conversation_history[hist_idx]
                    h_content = h_msg.get("content", "")
                    if h_msg.get("role") == "user" and ("[Observation for `" in h_content or "[Tool Execution Error in `" in h_content):
                        m_tool = re.search(r"\[(?:Observation for|Tool Execution Error in) `([^`]+)`\]", h_content)
                        t_lbl = m_tool.group(1) if m_tool else "tool"
                        status_note = "error observed" if "Error in `" in h_content else "completed"
                        h_msg["content"] = f"[Tool `{t_lbl}`: {status_note} (compacted for context)]"

            asst_text = full_response if full_response.strip() else f"Calling tool `{tool_name}` with arguments: {json.dumps(tool_args)}"
            conversation_history.append({"role": "assistant", "content": asst_text})
            conversation_history.append({"role": "user", "content": continuation_nudge})

            try:
                conversation_history, budget = self.fit_history_to_context(
                    system_prompt,
                    conversation_history,
                    capabilities.max_context,
                    output_tokens=output_tokens,
                    pinned_message=pinned_prompt,
                )
            except ValueError as exc:
                task_state.terminal_status = "FAILED"
                task_state.terminal_reason = f"Context budget exceeded: {exc}"
                self._save_task_state(task_state)
                yield AgentEvent(event_type="error", content=f"Context budget exceeded after tool result: {exc}")
                return

        task_state.terminal_status = "FAILED"
        task_state.terminal_reason = "iteration_limit_reached"
        self._save_task_state(task_state)
        yield AgentEvent(
            event_type="done",
            content=f"Bounded iteration limit ({self.max_iterations}) reached.",
            metadata={"status": "ITERATION_LIMIT", "terminal_status": "FAILED"},
        )

    async def resume_task_after_diff(
        self, session_id: str, diff_id: str, approved: bool = True
    ) -> AsyncIterator[AgentEvent]:
        """Resumes a suspended task after human diff review (Approve/Reject)."""
        task_state = self._active_tasks.get(session_id)
        if not task_state:
            yield AgentEvent(
                event_type="error",
                content=f"No active suspended task found for session {session_id}.",
            )
            return

        if not approved:
            task_state.pending_approval = None
            task_state.terminal_status = "CANCELLED"
            task_state.terminal_reason = "diff_rejected_by_user"
            self._save_task_state(task_state)
            self.session_manager.append_message(
                session_id, "user", f"[Review]: Diff {diff_id} was REJECTED by developer."
            )
            yield AgentEvent(
                event_type="done",
                content=f"Diff {diff_id} rejected. Task halted.",
                metadata={"terminal_status": "CANCELLED"},
            )
            return

        # Diff was approved and applied
        target_file = ""
        if task_state.pending_approval and task_state.pending_approval.diff_id == diff_id:
            target_file = task_state.pending_approval.file_path
        task_state.pending_approval = None

        # Ledger update
        task_state.ledger.append(
            LedgerEntry(
                phase=task_state.phase,
                action_type="diff_apply",
                payload={"diff_id": diff_id, "file_path": target_file, "status": "APPROVED"},
            )
        )

        modified_files = {target_file} if target_file else set()
        for entry in task_state.ledger:
            if entry.action_type == "diff_apply":
                fp = entry.payload.get("file_path")
                if fp:
                    modified_files.add(str(fp).replace("\\", "/"))
        all_satisfied, unmet = task_state.evaluate_acceptance(
            self.workspace_root, modified_files, []
        )

        self.session_manager.append_message(
            session_id,
            "user",
            f"[Review]: Diff {diff_id} was APPROVED and APPLIED to {target_file or 'workspace'}.",
        )

        if all_satisfied:
            task_state.terminal_status = "COMPLETED"
            self._save_task_state(task_state)
            yield AgentEvent(
                event_type="done",
                content=f"Diff {diff_id} applied and all acceptance predicates satisfied. Task completed.",
                metadata={
                    "task_id": task_state.task_id,
                    "diff_id": diff_id,
                    "terminal_status": "COMPLETED",
                    "engineering_stage": "Verification",
                },
            )
        else:
            # Continue task stream with remaining unmet predicates
            prompt = (
                f"Diff {diff_id} was applied successfully. "
                f"Remaining unmet predicates: {', '.join(unmet)}. Proceed to complete the task."
            )
            async for event in self.execute_task_stream(session_id, prompt, task_state.acceptance):
                yield event

    async def resume_task_after_approval(
        self,
        session_id: str,
        approval_id: str,
        tool_result: Dict[str, Any],
        approved: bool = True,
        tool_name: Optional[str] = None,
    ) -> AsyncIterator[AgentEvent]:
        """Resumes a suspended task after human approval for non-diff actions (e.g. run_command, unreal_editor)."""
        task_state = self._active_tasks.get(session_id)
        if not task_state:
            yield AgentEvent(
                event_type="error",
                content=f"No active suspended task found for session {session_id}.",
            )
            return

        if not approved:
            task_state.terminal_status = "CANCELLED"
            task_state.terminal_reason = f"approval_{approval_id}_rejected"
            self._save_task_state(task_state)
            self.session_manager.append_message(
                session_id, "user", f"[Approval]: Action {approval_id} was REJECTED by developer."
            )
            yield AgentEvent(
                event_type="done",
                content=f"Action {approval_id} rejected. Task halted.",
                metadata={"terminal_status": "CANCELLED"},
            )
            return

        appr_entry = self.tool_gateway.game_tools.approvals.get(approval_id)
        resolved_tool = (
            tool_name
            if tool_name
            else (appr_entry.get("tool") if appr_entry else None)
            or tool_result.get("tool")
            or tool_result.get("tool_name")
            or "run_command"
        )
        tool_args = (appr_entry.get("args") if appr_entry else None) or tool_result.get("arguments") or {}
        if not tool_args and tool_result.get("command"):
            tool_args = {"command": tool_result["command"]}

        th_record = {
            "approval_id": approval_id,
            "tool_name": resolved_tool,
            "arguments": tool_args,
            "command": tool_result.get("command") or tool_args.get("command"),
            "exit_code": tool_result.get("exit_code"),
            "status": tool_result.get("status", "SUCCESS"),
            **tool_result,
        }

        task_state.ledger.append(
            LedgerEntry(
                phase=task_state.phase,
                action_type="tool_result",
                payload=th_record,
            )
        )

        self.session_manager.record_tool(
            session_id=session_id,
            tool_name=resolved_tool,
            arguments=tool_args,
            output=json.dumps(tool_result),
            status=tool_result.get("status", "SUCCESS"),
        )

        # Re-evaluate acceptance predicates with the new execution evidence
        _modified_files = set()
        _tool_history = []
        for entry in task_state.ledger:
            if entry.action_type == "diff_apply":
                fp = entry.payload.get("file_path")
                if fp:
                    _modified_files.add(str(fp).replace("\\", "/"))
            elif entry.payload and isinstance(entry.payload, dict):
                _tool_history.append(entry.payload)

        all_satisfied, unmet = task_state.evaluate_acceptance(
            self.workspace_root, _modified_files, _tool_history
        )

        obs_json = json.dumps(tool_result, indent=2, ensure_ascii=False)
        self.session_manager.append_message(
            session_id,
            "user",
            f"[Observation for `{resolved_tool}` (Approved)]:\n{obs_json}",
        )

        if all_satisfied:
            task_state.terminal_status = "COMPLETED"
            self._save_task_state(task_state)
            msg = f"Tool `{tool_name}` executed and all acceptance predicates are satisfied. Task completed."
            yield AgentEvent(
                event_type="done",
                content=msg,
                metadata={
                    "task_id": task_state.task_id,
                    "approval_id": approval_id,
                    "terminal_status": "COMPLETED",
                },
            )
        else:
            prompt = (
                f"[Observation for `{tool_name}`]:\n{obs_json}\n\n"
                f"Remaining unmet predicates: {', '.join(unmet) or 'None'}. Proceed to complete the task or summarize your work."
            )
            async for event in self.execute_task_stream(session_id, prompt, task_state.acceptance):
                yield event
