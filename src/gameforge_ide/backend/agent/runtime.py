"""Bounded Agent Runtime and Execution Loop for GameForge IDE."""

from __future__ import annotations

import json
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


class AgentEvent(BaseModel):
    event_type: str  # "status", "token", "plan", "tool_call", "tool_result", "diff_pending", "error", "done"
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)


class AgentRuntime:
    """Orchestrates the bounded agent loop with typed tools, diff approval, and error repair."""

    def __init__(
        self,
        workspace_root: Path,
        session_manager: SessionManager,
        model_router: ModelRouter,
        max_iterations: int = 6,
    ):
        self.workspace_root = workspace_root.resolve()
        self.session_manager = session_manager
        self.router = model_router
        self.tool_gateway = ToolGateway(self.workspace_root)
        self.context_manager = ContextManager(self.workspace_root)
        self.max_iterations = max_iterations

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
        """Keep whole messages within an estimated input budget, pinning this task's prompt."""
        input_budget = max(0, max_context - output_tokens - safety_tokens)
        system_tokens = cls.estimate_tokens(system_prompt)
        if system_tokens > input_budget:
            raise ValueError(
                f"GameForge system context is estimated at {system_tokens} tokens, "
                f"above the {input_budget}-token input budget for this model."
            )
        remaining = input_budget - system_tokens
        selected_indices: set[int] = set()
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
            selected_indices.add(pinned_index)
            remaining -= pinned_tokens

        omitted = 0
        for index in range(len(messages) - 1, -1, -1):
            if index in selected_indices:
                continue
            message_tokens = cls.estimate_tokens(messages[index].get("content", ""))
            if message_tokens <= remaining:
                selected_indices.add(index)
                remaining -= message_tokens
            else:
                omitted += 1
        selected = [message for index, message in enumerate(messages) if index in selected_indices]
        used = input_budget - remaining
        return selected, {
            "estimated_input_tokens": used,
            "input_budget_tokens": input_budget,
            "omitted_history_messages": omitted,
        }

    def _extract_tool_call(self, text: str) -> Optional[Dict[str, Any]]:
        """Extracts structured tool invocation from model output."""
        # Match ```json {"tool": "name", "args": {...}} ```
        pattern = re.compile(r"```(?:json)?\s*(\{\s*\"tool\"\s*:\s*\"[^\"]+\".*?\})\s*```", re.DOTALL)
        m = pattern.search(text)
        if m:
            try:
                data = json.loads(m.group(1))
                if "tool" in data and "args" in data:
                    return {"name": data["tool"], "arguments": data["args"]}
            except Exception:
                pass

        # Match single-line {"tool": "...", "args": {...}}
        pattern2 = re.compile(r"(\{\s*\"tool\"\s*:\s*\"[^\"]+\"\s*,\s*\"args\"\s*:\s*\{.*?\}\s*\})", re.DOTALL)
        m2 = pattern2.search(text)
        if m2:
            try:
                data = json.loads(m2.group(1))
                if "tool" in data and "args" in data:
                    return {"name": data["tool"], "arguments": data["args"]}
            except Exception:
                pass

        return None

    def _record_prompt_and_get_history(
        self, session_id: str, user_prompt: str, history_limit: int = 8
    ) -> tuple[Session, List[Dict[str, str]]]:
        """Persist the prompt, then build provider history from the refreshed session.

        SessionManager reads a fresh object from disk for each operation, so a
        previously loaded Session does not see append_message mutations.
        """
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
    ) -> AsyncIterator[AgentEvent]:
        """Runs the bounded agent loop, yielding real-time events for WebSocket streaming."""
        session = self.session_manager.get_session(session_id)
        if not session:
            yield AgentEvent(event_type="error", content=f"Session {session_id} not found.")
            return

        # 1. Build context and preflight the prompt before provider execution.
        tools_desc = self._format_tools_description()
        system_prompt = self.context_manager.build_system_prompt(tools_desc, active_model=session.model_name)
        provider = self.router.get_provider(session.provider_type)
        capabilities = provider.get_capabilities(session.model_name)
        output_tokens = min(1024, max(256, capabilities.max_context // 3))

        # 2. Record user message and reload the session snapshot. SessionManager
        # operations return independent objects, so the earlier `session`
        # value would otherwise omit this turn from the provider payload.
        try:
            session, conversation_history = self._record_prompt_and_get_history(
                session_id, user_prompt, history_limit=10_000
            )
            pinned_prompt = {"role": "user", "content": user_prompt}
            conversation_history, budget = self.fit_history_to_context(
                system_prompt,
                conversation_history,
                capabilities.max_context,
                output_tokens=output_tokens,
                pinned_message=pinned_prompt,
            )
        except Exception as exc:
            yield AgentEvent(event_type="error", content=f"Prompt/context preflight failed: {exc}")
            return
        yield AgentEvent(
            event_type="status",
            content="PLANNING",
            metadata={"message": "Analyzing project and goal...", **budget},
        )

        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1
            yield AgentEvent(
                event_type="status",
                content="THINKING",
                metadata={"iteration": iteration, "max_iterations": self.max_iterations},
            )

            # Generate model response stream
            full_response = ""
            async for chunk in provider.stream_chat(
                model_id=session.model_name,
                messages=conversation_history,
                system_prompt=system_prompt,
                temperature=0.2,
                max_tokens=output_tokens,
                num_ctx=capabilities.max_context,
            ):
                if chunk.error:
                    yield AgentEvent(event_type="error", content=chunk.error)
                    return
                if chunk.token:
                    full_response += chunk.token
                    yield AgentEvent(event_type="token", content=chunk.token)

            # Check for tool call in response
            tool_call = self._extract_tool_call(full_response)
            if not tool_call:
                # Direct conversational response, task iteration complete
                self.session_manager.append_message(session_id, "assistant", full_response)
                yield AgentEvent(event_type="done", content="Task completed.", metadata={"full_text": full_response})
                return

            tool_name = tool_call["name"]
            tool_args = tool_call["arguments"]

            yield AgentEvent(
                event_type="tool_call",
                content=f"Dispatching tool: {tool_name}",
                metadata={"tool": tool_name, "args": tool_args},
            )

            definition = next(
                (item for item in self.tool_gateway.get_definitions() if item.name == tool_name),
                None,
            )
            # A proposed edit is intentionally non-mutating and its specific
            # diff-review flow below supplies approval. Other dangerous actions
            # cannot be performed merely because a model emitted JSON.
            if definition and definition.requires_approval and tool_name != "propose_edit":
                tool_result = {
                    "status": "PENDING_APPROVAL",
                    "tool": tool_name,
                    "error": (
                        "This action requires an explicit user approval flow and was not executed. "
                        "Use the corresponding reviewed UI workflow."
                    ),
                }
                self.session_manager.record_tool(
                    session_id=session_id,
                    tool_name=tool_name,
                    arguments=tool_args,
                    output=json.dumps(tool_result),
                    status="PENDING_APPROVAL",
                )
                yield AgentEvent(
                    event_type="tool_result",
                    content=f"Tool {tool_name} requires approval.",
                    metadata={"tool": tool_name, "result": tool_result},
                )
                self.session_manager.append_message(
                    session_id, "assistant", f"{full_response}\n\n[Action requires user approval: {tool_name}]"
                )
                yield AgentEvent(event_type="status", content="WAITING_APPROVAL", metadata={"tool": tool_name})
                return

            # Execute tool
            yield AgentEvent(event_type="status", content="EXECUTING_TOOL", metadata={"tool": tool_name})
            tool_result = self.tool_gateway.execute_tool(tool_name, tool_args)

            # Record in session
            diff_id = tool_result.get("diff_id")
            rec = self.session_manager.record_tool(
                session_id=session_id,
                tool_name=tool_name,
                arguments=tool_args,
                output=json.dumps(tool_result),
                status=tool_result.get("status", "SUCCESS"),
                diff_id=diff_id,
            )

            if diff_id and tool_result.get("status") == "PENDING_APPROVAL":
                # Emits diff approval modal event
                yield AgentEvent(
                    event_type="diff_pending",
                    content="Diff proposed. Awaiting developer approval.",
                    metadata={
                        "diff_id": diff_id,
                        "file_path": tool_result.get("file_path"),
                        "diff_patch": tool_result.get("diff_patch"),
                    },
                )
                self.session_manager.append_message(
                    session_id,
                    "assistant",
                    f"{full_response}\n\n[Diff proposed: {diff_id}. Waiting for user review.]",
                )
                yield AgentEvent(event_type="status", content="WAITING_APPROVAL", metadata={"diff_id": diff_id})
                return

            yield AgentEvent(
                event_type="tool_result",
                content=f"Tool {tool_name} returned {tool_result.get('status')}",
                metadata={"tool": tool_name, "result": tool_result},
            )

            # Append tool result to history for next iteration
            conversation_history.append({"role": "assistant", "content": full_response})
            conversation_history.append({
                "role": "user",
                "content": f"[Tool Observation for `{tool_name}`]:\n{json.dumps(tool_result, indent=2)}\n\nNext action or final conclusion?",
            })
            try:
                conversation_history, budget = self.fit_history_to_context(
                    system_prompt,
                    conversation_history,
                    capabilities.max_context,
                    output_tokens=output_tokens,
                    pinned_message=pinned_prompt,
                )
            except ValueError as exc:
                yield AgentEvent(event_type="error", content=f"Context budget exceeded after tool result: {exc}")
                return

        yield AgentEvent(
            event_type="done",
            content=f"Bounded iteration limit ({self.max_iterations}) reached.",
            metadata={"status": "ITERATION_LIMIT"},
        )
