"""Persistent Session Management for GameForge IDE."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    role: str  # "user", "assistant", "system", "tool"
    content: str
    timestamp: float = Field(default_factory=time.time)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ToolRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tool_name: str
    arguments: Dict[str, Any]
    output: str
    status: str  # "SUCCESS", "ERROR", "BLOCKED", "REJECTED"
    timestamp: float = Field(default_factory=time.time)
    diff_id: Optional[str] = None


class DiffRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    file_path: str
    original_content: str
    new_content: str
    diff_patch: str
    status: str = "PENDING_APPROVAL"  # "PENDING_APPROVAL", "APPROVED", "REJECTED", "ROLLED_BACK"
    timestamp: float = Field(default_factory=time.time)


class TaskCheckpoint(BaseModel):
    step_number: int
    objective: str
    completed_steps: List[str]
    pending_steps: List[str]
    active_blockers: List[str] = Field(default_factory=list)
    timestamp: float = Field(default_factory=time.time)


class Session(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "New GameForge Session"
    workspace_path: str
    model_name: str = "gameforge-27b-sft"
    provider_type: str = "ollama"
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    messages: List[ChatMessage] = Field(default_factory=list)
    tool_history: List[ToolRecord] = Field(default_factory=list)
    diff_history: List[DiffRecord] = Field(default_factory=list)
    checkpoints: List[TaskCheckpoint] = Field(default_factory=list)


class SessionManager:
    """Handles persistence of GameForge sessions to disk (.gameforge/sessions)."""

    def __init__(self, workspace_path: Path | str):
        self.workspace_path = Path(workspace_path).resolve()
        self.storage_dir = self.workspace_path / ".gameforge" / "sessions"
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def create_session(self, name: str = "New Session", model_name: str = "gameforge-27b-sft", provider_type: str = "ollama") -> Session:
        session = Session(
            name=name,
            workspace_path=str(self.workspace_path),
            model_name=model_name,
            provider_type=provider_type,
        )
        self.save_session(session)
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        path = self.storage_dir / f"{session_id}.json"
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return Session(**data)
        except Exception:
            return None

    def save_session(self, session: Session) -> None:
        session.updated_at = time.time()
        path = self.storage_dir / f"{session.session_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(session.model_dump(), f, indent=2)

    def list_sessions(self) -> List[Dict[str, Any]]:
        sessions = []
        for p in self.storage_dir.glob("*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                sessions.append({
                    "session_id": data.get("session_id"),
                    "name": data.get("name"),
                    "created_at": data.get("created_at"),
                    "updated_at": data.get("updated_at"),
                    "model_name": data.get("model_name"),
                    "message_count": len(data.get("messages", [])),
                })
            except Exception:
                continue
        sessions.sort(key=lambda s: s.get("updated_at", 0), reverse=True)
        return sessions

    def append_message(self, session_id: str, role: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> ChatMessage:
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        msg = ChatMessage(role=role, content=content, metadata=metadata or {})
        session.messages.append(msg)
        self.save_session(session)
        return msg

    def record_tool(self, session_id: str, tool_name: str, arguments: Dict[str, Any], output: str, status: str, diff_id: Optional[str] = None) -> ToolRecord:
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        rec = ToolRecord(
            tool_name=tool_name,
            arguments=arguments,
            output=output,
            status=status,
            diff_id=diff_id,
        )
        session.tool_history.append(rec)
        self.save_session(session)
        return rec

    def record_diff(self, session_id: str, file_path: str, original_content: str, new_content: str, diff_patch: str) -> DiffRecord:
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        diff = DiffRecord(
            file_path=file_path,
            original_content=original_content,
            new_content=new_content,
            diff_patch=diff_patch,
        )
        session.diff_history.append(diff)
        self.save_session(session)
        return diff
