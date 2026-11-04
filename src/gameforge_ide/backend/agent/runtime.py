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
from .context_manager import ContextManager
from .task_state import (
    LedgerEntry,
    PendingApproval,
    TaskAcceptancePredicate,
    TaskBudget,
    TaskState,
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
        self.max_iterations = max_iterations
        # Native tool calling is on by default; GAMEFORGE_NATIVE_TOOLS=0 restores text extraction.
        self.native_tools = os.environ.get("GAMEFORGE_NATIVE_TOOLS", "1") != "0"
        self.tasks_dir = self.workspace_root / ".gameforge" / "tasks"
        try:
            self.tasks_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self._active_tasks: Dict[str, TaskState] = {}

    def set_workspace(self, new_workspace: Path | str) -> None:
        """Switch the agent runtime active workspace and re-initialize path-dependent subsystems."""
        self.workspace_root = Path(new_workspace).resolve()
        self.tool_gateway = ToolGateway(self.workspace_root)
        self.context_manager = ContextManager(self.workspace_root)
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
            for index in range(len(messages) - 1, -1, -1):
                if messages[index] == pinned_message:
                    pinned_index = index
                    break
            if pinned_index is None:
                raise ValueError("The active user prompt is missing from provider history.")
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
                if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
                    try:
                        parsed = json.loads(s)
                        if isinstance(parsed, dict):
                            return parsed
                    except Exception:
                        pass
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
            '<tool_call>', '<tool_use>', '<invoke', '<function_call>',
        )
        if any(stripped.startswith(pfx) for pfx in tool_prefixes):
            return True
        if re.search(r"```(?:json)?\s*\{\s*\"(?:tool|name|function|action|tool_name|tool_calls|type)\"", stripped):
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
            r"<(?:tool_call|tool_use|function_call|invoke(?:\s+name=[^>]+)?)>.*?</(?:tool_call|tool_use|function_call|invoke)>",
            "",
            cleaned,
            flags=re.DOTALL | re.IGNORECASE,
        )
        cleaned = re.sub(r"\{\s*\"(?:tool|name|function|action|tool_name|tool_calls|type)\"\s*:.*?\}\s*$", "", cleaned, flags=re.DOTALL)
        cleaned = re.sub(r"^\s*\{\s*\"(?:tool|name|function|action|tool_name|tool_calls|type)\"\s*:.*?\}\s*", "", cleaned, flags=re.DOTALL)
        return cleaned.strip()

    @staticmethod
    def _is_conversational(user_prompt: str) -> bool:
        """Return True when the prompt is clearly conversational and should never trigger tools."""
        p = user_prompt.strip().lower()
        words = re.findall(r"\b\w+\b", p)
        action_keywords = {
            "create", "build", "make", "implement", "generate", "inspect",
            "fix", "refactor", "write", "setup", "develop", "code", "author",
            "add", "remove", "delete", "update", "edit", "explore", "list",
            "search", "check", "run", "verify", "test", "compile", "diff",
        }
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
                if any(k in rest for k in ("create", "build", "make", "fix", "add", "remove", "update", "game", "shoot", "run", "check", "speed")):
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
        if any(p.startswith(pfx) for pfx in qa_prefixes):
            return True

        # Any inquiry ending with '?' or containing question phrases
        if (p.endswith("?") or "?" in p) and not re.search(r"\b(create|scaffold|generate|build me|make me)\b", p):
            return True

        # Questions or discussions about GameForge itself, the chat, IDE, or general concepts
        meta_qa = (
            "what does the chat", "what does the assistant", "what does chat do",
            "what does the ide do", "how does the chat work", "how does gameforge work",
            "what can you do", "what are your capabilities", "who are you",
        )
        if any(mq in p for mq in meta_qa):
            return True

        if any(re.search(rf"(?:^|[,\.]\s*){re.escape(pfx)}\b", p) for pfx in qa_prefixes):
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

        return predicates

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

        is_conversational = self._is_conversational(user_prompt)
        intent = "answer" if is_conversational else "mutate"
        predicates = acceptance_predicates or self._propose_acceptance_predicates(user_prompt)

        task_state = TaskState(
            session_id=session_id,
            goal=user_prompt,
            intent=intent,
            acceptance=predicates,
            budget=TaskBudget(max_iterations=self.max_iterations),
            phase="author" if intent == "mutate" else "discover",
        )
        self._active_tasks[session_id] = task_state
        self._save_task_state(task_state)

        # 1. Build context and preflight the prompt before provider execution.
        tools_desc = self._format_tools_description()
        full_system_prompt = self.context_manager.build_system_prompt(
            tools_desc,
            active_model=session.model_name,
            include_tools=True,
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
            metadata={"message": "Analyzing project and goal...", "task_id": task_state.task_id, **budget},
        )

        # Game-production fast path: a request that matches an installed, verified recipe is
        # planned deterministically and suspended for one scoped approval. The heavy work then
        # runs from the trusted UI approval path, never from model text (rules 1 and 5).
        if not is_conversational:
            if self.studio_mode or os.environ.get("GAMEFORGE_STUDIO_MODE") == "1":
                from ...pipeline.spec_from_prompt import is_game_creation_request
                is_create = is_game_creation_request(user_prompt)

                # Distinguish informational queries and direct C++ code requests from GDS game changes
                is_question = (
                    user_prompt.strip().endswith("?")
                    or bool(re.search(r"^(what|how|why|where|when|who|which)\b", user_prompt.strip(), re.I))
                    or bool(re.search(r"\b(what does (?:the )?(?:chat|assistant)|can you explain|tell me about)\b", user_prompt, re.I))
                )

                is_code_request = bool(re.search(
                    r"\b(source\s+code|\.cpp\b|\.h\b|source/|c\+\+|header\s+file|cpp\s+file|\bclass\s+[A-Z]\w*|\bstruct\s+[A-Z]\w*)\b",
                    user_prompt,
                    re.I,
                ))

                is_modal_request = bool(re.search(r"^(can|could|would)\s+you\b|^please\b", user_prompt.strip(), re.I))
                is_explanation = bool(re.search(r"\b(can you explain|tell me about|what is|how does|why does)\b", user_prompt, re.I))

                if is_code_request:
                    is_create = False
                    is_change = False
                elif is_question and not is_create and not (is_modal_request and not is_explanation):
                    is_change = False
                else:
                    is_change = bool(re.search(
                        r"\b(complete|finish|expand|build\s+out|implement|code|author|change|modify|update|adjust|faster|slower|add|ad|remove|tweak|increase|decrease|more|mor|less|replace|enhance|fix|improve|switch|set|turn|double|halve|insert|make|spawn|give|equip|grant|provide|place|put|attach|drop|include|enable|disable|raise|lower|boost|scale|cut)\b",
                        user_prompt,
                        re.I,
                    )) and bool(re.search(
                        r"\b(game|project|level|leavl|scene|player|players|character|characters|hero|weapon|weapons?|wepon|gun|shotgun|shotgn|pistol|rifle|knife|bot|bots|enemy|enemies|enemiez|combat|spawner|hazard|speed|health|damage|rules?|arena|box|camera|view|perspective|jump|height|boss|lighting|pickups?|collectibles?|checkpoint|checkpoints|obstacles?|doors?|keys?|bombs?|defus\w*|tactical|coins?|gems?|potions?|chests?|traps?|turrets?|shields?|armor|ammo|bullets?|flags?|platforms?|switches?|gates?|walls?|goals?|objectives?|timers?|scores?|difficulty|gravity|art|style|music|audio|biome|theme|fog|dark|skybox|cards?|decks?|dice|board|grid)\b",
                        user_prompt,
                        re.I,
                    )) and not is_create

                active_has_gds = (self.workspace_root / "GameForge" / "design" / "game.gds.json").is_file()

                if is_create or is_change:
                    mode = "change" if active_has_gds else "create"
                    p_name = self.workspace_root.name
                    card = {
                        "type": "open_design",
                        "prompt": user_prompt,
                        "mode": mode,
                        "project": p_name if (mode == "change" or active_has_gds) else "",
                    }
                    if mode == "change":
                        msg = (
                            f"I've mapped your request to update active project **{p_name}**.\n\n"
                            f"In GameForge, gameplay mechanics, weapons, and level rules are managed through "
                            f"the Game Definition Spec (GDS) and compiled through the engine pipeline. "
                            f"Click **Open in Design** below to review these rules and trigger the build."
                        )
                    else:
                        msg = (
                            "I've mapped your game prompt into a Game Definition Spec (GDS).\n\n"
                            "Click **Open in Design** below to review the architecture, mechanics, and build your game."
                        )
                    yield AgentEvent(event_type="token", content=msg)
                    self.session_manager.append_message(session_id, "assistant", msg)
                    task_state.terminal_reason = f"routed to studio design ({mode})"
                    self._save_task_state(task_state)
                    yield AgentEvent(event_type="status", content="READY", metadata={"card": card})
                    yield AgentEvent(event_type="done", content=msg)
                    return

            try:
                proposal = self.tool_gateway.game_tools.propose_create_game(user_prompt, session_id=session_id)
            except Exception as exc:  # planning must never break the normal agent loop
                proposal = None
                yield AgentEvent(event_type="status", content="PLANNING",
                                 metadata={"message": f"Game planner unavailable: {exc}"})
            if proposal and proposal.get("approval_id"):
                plan_text = proposal["plan_text"]
                yield AgentEvent(event_type="token", content=plan_text)
                self.session_manager.append_message(session_id, "assistant", plan_text)
                task_state.terminal_reason = f"waiting for approval {proposal['approval_id']}"
                self._save_task_state(task_state)
                yield AgentEvent(event_type="status", content="WAITING_APPROVAL",
                                 metadata={"tool": proposal["tool"], "approval": proposal})
                yield AgentEvent(event_type="done", content=plan_text)
                return

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
        _modified_files: set[str] = set()
        _tool_history: List[Dict[str, Any]] = []
        _edit_proposed = False
        _task_needs_edit = self._is_actionable_task(user_prompt, "")
        _unmet_predicates_nudged = False

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
                if full_response:
                    yield AgentEvent(event_type="token", content=full_response)
                if native.get("tool_calls"):
                    native_call = native["tool_calls"][0]
                    # Never set full_response to tool JSON dumps so the user sees clean conversation
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
                            metadata={"action": "nudge_unmet_predicates", "unmet": unmet, "iteration": iteration},
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
                    metadata={"full_text": full_response, "terminal_status": "COMPLETED"},
                )
                return

            tool_name = tool_call["name"]
            tool_args = tool_call["arguments"]

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

            yield AgentEvent(
                event_type="tool_call",
                content=f"Dispatching tool: {tool_name}",
                metadata={"tool": tool_name, "args": tool_args},
            )

            definition = next(
                (item for item in self.tool_gateway.get_definitions() if item.name == tool_name),
                None,
            )
            if definition and self.tool_gateway.tool_requires_approval(tool_name, tool_args) and tool_name != "propose_edit":
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
            if call_count == 2 and _tool_key in _cached_observations:
                tool_result = _cached_observations[_tool_key]
            else:
                tool_result = self.tool_gateway.execute_tool(tool_name, tool_args)
                _cached_observations[_tool_key] = tool_result

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
            elif tool_name in ("unreal_find_projects", "unreal_engine_info", "list_dir"):
                continuation_nudge = (
                    f"[Observation for `{tool_name}`]:\n{obs_json}\n\n"
                    "You now have the required workspace/engine information. "
                    "Proceed with the next appropriate tool call to complete the task, or synthesize your final response. "
                    "Do not call discovery tools again unless you need a specific piece of information not yet retrieved."
                )
            else:
                continuation_nudge = (
                    f"[Observation for `{tool_name}`]:\n{obs_json}\n\n"
                    "Review the observation above and proceed with the next appropriate tool call or synthesize your final response."
                )

            # Compact older tool observations in history to avoid multi-turn context overflow
            if len(conversation_history) > 4:
                for hist_idx in range(len(conversation_history) - 2):
                    h_msg = conversation_history[hist_idx]
                    if h_msg.get("role") == "user" and "[Observation for `" in h_msg.get("content", ""):
                        m_tool = re.search(r"\[Observation for `([^`]+)`\]", h_msg["content"])
                        t_lbl = m_tool.group(1) if m_tool else "tool"
                        h_msg["content"] = f"[Observation for `{t_lbl}`: completed (compacted)]"

            conversation_history.append({"role": "assistant", "content": full_response})
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
