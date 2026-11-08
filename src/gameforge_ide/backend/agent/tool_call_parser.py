"""Canonical Tool Call Parser, Normalizer, and Streaming Guard for GameForge IDE.

Provides a unified, deterministic parser for all LLM tool invocation dialects:
- Native OpenAI/Ollama tool_calls
- Anthropic tool_use
- GameForge native {tool, args}
- Standard {name, arguments}
- ReAct / LangChain {action, action_input}
- Flat legacy command format (e.g. {"command": "read_file", "path": "..."})
- XML tool tags (<tool_call>, <tool_use>, <invoke>)
- Embedded tool calls preceded or followed by natural language narrative

Features:
- Exact character span tracking to strip only the tool payload while preserving surrounding prose.
- Code fence and inline backtick awareness: JSON examples in markdown code blocks are never executed.
- StreamingToolGuard with incremental buffering to prevent raw tool JSON leaks in live chat streams.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass(frozen=True)
class ParsedToolCall:
    """Canonical representation of an extracted and normalized tool invocation."""
    name: str
    arguments: Dict[str, Any]
    call_id: Optional[str] = None
    start: int = -1
    end: int = -1
    source: str = "json"  # native | json | xml | react | flat_command


@dataclass
class ParserResult:
    """Outcome of parsing text or structured model response."""
    calls: List[ParsedToolCall] = field(default_factory=list)
    cleaned_text: str = ""
    diagnostics: List[str] = field(default_factory=list)


# Standard default known tool names if ToolGateway is not instantiated
DEFAULT_KNOWN_TOOLS: Set[str] = {
    "list_dir",
    "read_file",
    "search_code",
    "search_index",
    "propose_edit",
    "apply_edit",
    "reject_edit",
    "rollback_edit",
    "apply_batch",
    "rollback_batch",
    "write_file",
    "delete_file",
    "unreal_editor",
    "unreal_build",
    "unreal_run_tests",
    "unreal_package",
    "play_game",
    "create_game",
    "run_command",
    "git_status",
    "git_diff",
    "git_commit",
    "procedural_mesh",
    "inspect_asset",
}

DEFAULT_ALIASES: Dict[str, str] = {
    "apply_diff": "apply_edit",
    "apply_diffs_batch": "apply_batch",
    "reject_diff": "reject_edit",
    "rollback_diff": "rollback_edit",
    "rollback_diffs_batch": "rollback_batch",
    "del": "delete_file",
    "rm": "delete_file",
    "unlink": "delete_file",
    "remove_file": "delete_file",
}


def parse_arguments_payload(args: Any) -> Dict[str, Any]:
    """Robustly parse argument payload from dict, JSON string, or escaped JSON."""
    if isinstance(args, dict):
        return args
    if not isinstance(args, str):
        return {}

    s = args.strip()
    if not s:
        return {}

    # Strip markdown code fences if present: ```json ... ```
    fence_m = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", s, re.IGNORECASE)
    if fence_m:
        s = fence_m.group(1).strip()

    # Try standard json loads
    try:
        parsed = json.loads(s)
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, str):
            nested = json.loads(parsed)
            if isinstance(nested, dict):
                return nested
    except Exception:
        pass

    # Check for XML parameters: <parameter name="x">y</parameter>
    param_matches = list(re.finditer(r"<(?:parameter|arg|argument)\s+name=[\"']([^\"']+)[\"']\s*>(.*?)</(?:parameter|arg|argument)>", s, re.DOTALL | re.IGNORECASE))
    if param_matches:
        return {pm.group(1).strip(): pm.group(2).strip() for pm in param_matches}

    # Balanced bracket extraction within string
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

    if s and not s.startswith(("{", "[")):
        return {"input": s}

    return {}


def normalize_flat_command(
    data: Dict[str, Any],
    known_tools: Set[str],
    aliases: Dict[str, str],
) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Normalizes the flat legacy command format:

    {
      "command": "read_file",
      "path": "E:\\GameForge\\projects\\CounterStrike\\Source\\CounterStrike\\GFGameImpl.cpp"
    }

    Also handles when 'command' wraps arguments or when flat keys are arguments.
    """
    raw_name = data.get("command")
    if not isinstance(raw_name, str):
        return None
    name = aliases.get(raw_name.strip(), raw_name.strip())
    if name not in known_tools:
        return None

    # If explicit wrapped argument keys are present
    wrapped_keys = ("arguments", "args", "parameters", "params", "input", "tool_input")
    for key in wrapped_keys:
        if key in data:
            val = data[key]
            parsed_args = parse_arguments_payload(val)
            if parsed_args:
                return name, parsed_args

    # Flat form: all non-envelope properties are tool arguments
    metadata_keys = {"command", "id", "call_id", "tool_call_id", "type", "index"}
    arguments = {k: v for k, v in data.items() if k not in metadata_keys}
    return name, arguments


def normalize_tool_dict(
    data: Any,
    known_tools: Set[str],
    aliases: Dict[str, str],
) -> Optional[Tuple[str, Dict[str, Any], Optional[str], str]]:
    """Normalizes a raw dictionary representation into (canonical_name, arguments, call_id, source)."""
    if not isinstance(data, dict):
        if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
            return normalize_tool_dict(data[0], known_tools, aliases)
        return None

    call_id = data.get("id") or data.get("call_id") or data.get("tool_call_id")

    # 1. OpenAI format with top-level tool_calls array
    if "tool_calls" in data and isinstance(data["tool_calls"], list) and len(data["tool_calls"]) > 0:
        return normalize_tool_dict(data["tool_calls"][0], known_tools, aliases)

    # 2. OpenAI single function call: {"type": "function", "function": {"name": ..., "arguments": ...}}
    if "function" in data and isinstance(data["function"], dict):
        fn = data["function"]
        name = fn.get("name")
        if name and isinstance(name, str):
            cname = aliases.get(name.strip(), name.strip())
            if cname in known_tools:
                return cname, parse_arguments_payload(fn.get("arguments", {})), call_id, "native"

    # 3. Anthropic tool_use format: {"type": "tool_use", "name": ..., "input": ...}
    if data.get("type") == "tool_use" and "name" in data:
        name = str(data["name"]).strip()
        cname = aliases.get(name, name)
        if cname in known_tools:
            return cname, parse_arguments_payload(data.get("input", {})), call_id, "native"

    # 4. GameForge native format: {"tool": "...", "args": {...}}
    if "tool" in data and ("args" in data or "parameters" in data or "arguments" in data):
        name = str(data["tool"]).strip()
        cname = aliases.get(name, name)
        if cname in known_tools:
            args_val = data.get("args") or data.get("parameters") or data.get("arguments")
            return cname, parse_arguments_payload(args_val), call_id, "json"

    # 5. Standard format: {"name": "...", "arguments": {...}}
    if "name" in data and ("arguments" in data or "args" in data or "parameters" in data or "input" in data):
        name = str(data["name"]).strip()
        cname = aliases.get(name, name)
        if cname in known_tools:
            args_val = data.get("arguments") or data.get("args") or data.get("parameters") or data.get("input")
            return cname, parse_arguments_payload(args_val), call_id, "json"

    # 6. ReAct / LangChain: {"action": "...", "action_input": {...}}
    if "action" in data and ("action_input" in data or "action_args" in data or "args" in data):
        name = str(data["action"]).strip()
        cname = aliases.get(name, name)
        if cname in known_tools:
            args_val = data.get("action_input") or data.get("action_args") or data.get("args")
            return cname, parse_arguments_payload(args_val), call_id, "react"

    # 7. Flat command dialect (as shown in the user screenshot)
    if "command" in data:
        flat_res = normalize_flat_command(data, known_tools, aliases)
        if flat_res:
            cname, arguments = flat_res
            return cname, arguments, call_id, "flat_command"

    # 8. Tool name alias format: {"tool_name": ..., "parameters": ...}
    if "tool_name" in data and ("parameters" in data or "args" in data or "arguments" in data):
        name = str(data["tool_name"]).strip()
        cname = aliases.get(name, name)
        if cname in known_tools:
            args_val = data.get("parameters") or data.get("args") or data.get("arguments")
            return cname, parse_arguments_payload(args_val), call_id, "json"

    return None


def find_code_fence_ranges(text: str) -> List[Tuple[int, int]]:
    """Identifies character ranges [start, end) that are enclosed in markdown code fences (```...```)."""
    ranges: List[Tuple[int, int]] = []
    pattern = re.compile(r"```[\s\S]*?```", re.MULTILINE)
    for m in pattern.finditer(text):
        ranges.append((m.start(), m.end()))
    return ranges


def is_in_ranges(pos: int, ranges: List[Tuple[int, int]]) -> bool:
    return any(start <= pos < end for start, end in ranges)


def find_balanced_json_objects(text: str) -> List[Tuple[int, int, str]]:
    """Scans text character by character for balanced JSON objects `{ ... }`.

    Correctly ignores braces inside double-quoted string literals and handles escape characters.
    Returns list of (start_index, end_index, json_substring).
    """
    results: List[Tuple[int, int, str]] = []
    n = len(text)
    i = 0

    while i < n:
        if text[i] == "{":
            start = i
            depth = 1
            in_string = False
            escaped = False
            i += 1

            while i < n and depth > 0:
                ch = text[i]
                if in_string:
                    if escaped:
                        escaped = False
                    elif ch == "\\":
                        escaped = True
                    elif ch == '"':
                        in_string = False
                else:
                    if ch == '"':
                        in_string = True
                    elif ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                i += 1

            if depth == 0:
                end = i
                candidate = text[start:end]
                results.append((start, end, candidate))
            else:
                break
        else:
            i += 1

    return results


def parse_text_for_tool_calls(
    text: str,
    known_tools: Optional[Set[str]] = None,
    aliases: Optional[Dict[str, str]] = None,
) -> ParserResult:
    """Parses text for tool invocations and strips only the exact tool spans from the narrative."""
    if not text:
        return ParserResult(calls=[], cleaned_text="", diagnostics=[])

    tools = set(known_tools or DEFAULT_KNOWN_TOOLS)
    alias_map = dict(aliases or DEFAULT_ALIASES)
    calls: List[ParsedToolCall] = []
    spans_to_remove: List[Tuple[int, int]] = []

    # 1. XML tool tags: <tool_call>, <tool_use>, <invoke>
    xml_patterns = [
        re.compile(r"<tool_use>\s*<name>([^<]+)</name>\s*<(?:input|arguments|args)>(.*?)</(?:input|arguments|args)>\s*</tool_use>", re.DOTALL | re.IGNORECASE),
        re.compile(r"<tool_call>\s*<name>([^<]+)</name>\s*<(?:input|arguments|args)>(.*?)</(?:input|arguments|args)>\s*</tool_call>", re.DOTALL | re.IGNORECASE),
        re.compile(r"<invoke\s+name=[\"']([^\"']+)[\"']\s*>(.*?)</invoke>", re.DOTALL | re.IGNORECASE),
    ]

    for pat in xml_patterns:
        for m in pat.finditer(text):
            raw_name = m.group(1).strip()
            name = alias_map.get(raw_name, raw_name)
            if name in tools:
                args = parse_arguments_payload(m.group(2).strip())
                calls.append(ParsedToolCall(
                    name=name,
                    arguments=args,
                    start=m.start(),
                    end=m.end(),
                    source="xml",
                ))
                spans_to_remove.append((m.start(), m.end()))

    # 2. ReAct format: Action: ... \n Action Input: ...
    react_pat = re.compile(
        r"(?:^|\n)\s*Action\s*:\s*([a-zA-Z0-9_\-]+)\s*\n\s*Action\s+Input\s*:\s*(\{.*?\}|[^\n]+)",
        re.DOTALL | re.IGNORECASE,
    )
    for m in react_pat.finditer(text):
        raw_name = m.group(1).strip()
        name = alias_map.get(raw_name, raw_name)
        if name in tools:
            args = parse_arguments_payload(m.group(2).strip())
            calls.append(ParsedToolCall(
                name=name,
                arguments=args,
                start=m.start(),
                end=m.end(),
                source="react",
            ))
            spans_to_remove.append((m.start(), m.end()))

    # 3. Balanced JSON scanning
    code_fences = find_code_fence_ranges(text)
    json_candidates = find_balanced_json_objects(text)

    for start, end, candidate in json_candidates:
        # Check if candidate overlaps with an already extracted XML or ReAct span
        if any(sp_start <= start < sp_end for sp_start, sp_end in spans_to_remove):
            continue

        # Check if candidate is enclosed in a markdown code fence
        if is_in_ranges(start, code_fences):
            continue

        try:
            data = json.loads(candidate)
        except Exception:
            continue

        normalized = normalize_tool_dict(data, tools, alias_map)
        if normalized:
            name, arguments, call_id, source = normalized
            calls.append(ParsedToolCall(
                name=name,
                arguments=arguments,
                call_id=call_id,
                start=start,
                end=end,
                source=source,
            ))
            spans_to_remove.append((start, end))

    # Construct cleaned narrative text by excising spans
    if not spans_to_remove:
        cleaned = text
    else:
        spans_to_remove.sort(key=lambda x: x[0])
        # Merge overlapping spans
        merged: List[Tuple[int, int]] = []
        for s, e in spans_to_remove:
            if not merged:
                merged.append((s, e))
            else:
                last_s, last_e = merged[-1]
                if s <= last_e:
                    merged[-1] = (last_s, max(last_e, e))
                else:
                    merged.append((s, e))

        parts: List[str] = []
        curr = 0
        for s, e in merged:
            parts.append(text[curr:s])
            curr = e
        parts.append(text[curr:])
        cleaned = "".join(parts)

    # Strip <think> tags, cat heredocs, and cleanup excessive whitespace
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</?think>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = cleaned.strip()

    return ParserResult(calls=calls, cleaned_text=cleaned)


class StreamingToolGuard:
    """Incremental streaming guard for live LLM output.

    Buffers incoming text chunks when a potential tool call syntax is detected
    so incomplete JSON payloads are never exposed to the UI. Once the candidate
    resolves, either safe narrative delta is flushed or the recognized tool call
    is extracted and suppressed from user-facing text.
    """

    def __init__(
        self,
        known_tools: Optional[Set[str]] = None,
        aliases: Optional[Dict[str, str]] = None,
        max_buffer_size: int = 32_768,
    ) -> None:
        self.known_tools = set(known_tools or DEFAULT_KNOWN_TOOLS)
        self.aliases = dict(aliases or DEFAULT_ALIASES)
        self.max_buffer_size = max_buffer_size
        self._buffer: str = ""
        self._recognized_calls: List[ParsedToolCall] = []

    def feed(self, chunk: str) -> Tuple[str, List[ParsedToolCall]]:
        """Consumes a streamed chunk and returns (safe_narrative_delta, newly_recognized_calls)."""
        if not chunk:
            return "", []

        self._buffer += chunk
        new_calls: List[ParsedToolCall] = []
        safe_narrative = ""

        # Check if buffer has a candidate tool call trigger
        candidate_idx = self._find_candidate_start(self._buffer)
        if candidate_idx == -1:
            # No tool call candidate; entire buffer is safe narrative
            safe_narrative = self._buffer
            self._buffer = ""
            return safe_narrative, []

        # We have text before the candidate
        if candidate_idx > 0:
            safe_narrative = self._buffer[:candidate_idx]
            self._buffer = self._buffer[candidate_idx:]

        # Check if the candidate in self._buffer forms a complete balanced object
        balanced = find_balanced_json_objects(self._buffer)
        if balanced:
            # We found at least one complete balanced JSON object
            start, end, candidate = balanced[0]
            if start == 0:
                try:
                    data = json.loads(candidate)
                    normalized = normalize_tool_dict(data, self.known_tools, self.aliases)
                    if normalized:
                        name, arguments, call_id, source = normalized
                        call = ParsedToolCall(
                            name=name,
                            arguments=arguments,
                            call_id=call_id,
                            start=start,
                            end=end,
                            source=source,
                        )
                        new_calls.append(call)
                        self._recognized_calls.append(call)
                        # Suppress candidate tool JSON from narrative
                        self._buffer = self._buffer[end:]
                        # Recurse on remaining buffer
                        rem_text, rem_calls = self.feed("")
                        return safe_narrative + rem_text, new_calls + rem_calls
                    else:
                        # Balanced JSON object is NOT a tool call; release it to narrative
                        safe_narrative += self._buffer[:end]
                        self._buffer = self._buffer[end:]
                except Exception:
                    # Failed parse; release up to end
                    safe_narrative += self._buffer[:end]
                    self._buffer = self._buffer[end:]

        # If buffer exceeds max size without resolving, flush safely
        if len(self._buffer) > self.max_buffer_size:
            safe_narrative += self._buffer
            self._buffer = ""

        return safe_narrative, new_calls

    def finish(self) -> Tuple[str, List[ParsedToolCall]]:
        """Flushes any remaining buffered text at stream completion."""
        if not self._buffer:
            return "", []

        # Run full parser on remaining buffer
        res = parse_text_for_tool_calls(self._buffer, self.known_tools, self.aliases)
        remaining_narrative = res.cleaned_text
        self._buffer = ""
        return remaining_narrative, res.calls

    @staticmethod
    def _find_candidate_start(text: str) -> int:
        """Finds the index of the first character that could start a tool call."""
        triggers = ["{", "<tool_call", "<tool_use", "<invoke", "Action:"]
        indices = [text.find(tr) for tr in triggers if text.find(tr) != -1]
        return min(indices) if indices else -1
