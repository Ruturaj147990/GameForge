"""Persistent Session Management for GameForge IDE."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import logging
from pathlib import Path
import re
import secrets
import threading
import time
from typing import Any, Dict, List, Optional, Union
import uuid
from pydantic import BaseModel, Field

from ..core.settings import get_settings
from ..storage.atomic import atomic_write_json, atomic_write_text, safe_read_json
from .models.modes import AutonomyProfile, PermissionsMode, TaskLifecycleStatus, TaskMode
from .models.plan_artifact import PlanArtifact


logger = logging.getLogger(__name__)

_SAFE_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,128}$")


def _validate_session_id(session_id: str) -> str:
    clean = str(session_id or "").strip()
    if (
        not clean
        or ".." in clean
        or "/" in clean
        or "\\" in clean
        or not _SAFE_SESSION_ID_RE.fullmatch(clean)
    ):
        raise ValueError(f"Invalid session_id: {session_id!r}")
    return clean


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
    model_name: str = Field(default_factory=lambda: get_settings().model_for("chat"))
    provider_type: str = "ollama"
    task_mode: TaskMode = Field(default=TaskMode.PLANNING)
    autonomy_profile: AutonomyProfile = Field(default=AutonomyProfile.AGENTIC)
    permissions_mode: PermissionsMode = Field(default=PermissionsMode.AUTO)
    active_plan: Optional[PlanArtifact] = None
    active_task_id: Optional[str] = None
    task_status: TaskLifecycleStatus = Field(default=TaskLifecycleStatus.CREATED)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    messages: List[ChatMessage] = Field(default_factory=list)
    tool_history: List[ToolRecord] = Field(default_factory=list)
    diff_history: List[DiffRecord] = Field(default_factory=list)
    checkpoints: List[TaskCheckpoint] = Field(default_factory=list)
    project_dir: Optional[str] = None


@dataclass
class SessionTokenRecord:
    token_hash: str
    session_id: str
    created_at: float
    expires_at: float
    revoked: bool = False


class SessionManager:
    """Handles persistence of GameForge sessions to disk (.gameforge/sessions)."""

    def __init__(self, workspace_path: Path | str):
        self.workspace_path = Path(workspace_path).resolve()
        self.storage_dir = self.workspace_path / ".gameforge" / "sessions"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._tokens: Dict[str, SessionTokenRecord] = {}

    def _session_file_path(self, session_id: str) -> Path:
        safe_id = _validate_session_id(session_id)
        candidate = (self.storage_dir / f"{safe_id}.json").resolve()
        if candidate.parent != self.storage_dir.resolve():
            raise ValueError(f"Session path escapes storage directory: {session_id!r}")
        return candidate

    def issue_session_token(self, session_id: str, lifetime_seconds: float = 86400.0) -> str:
        """Issue a cryptographically secure, high-entropy session bearer token (DEF-REM-P3A)."""
        safe_id = _validate_session_id(session_id)
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        now = time.time()
        with self._lock:
            # Prune expired tokens to prevent unbounded in-memory accumulation
            self._tokens = {k: v for k, v in self._tokens.items() if v.expires_at > now}
            self._tokens[safe_id] = SessionTokenRecord(
                token_hash=token_hash,
                session_id=safe_id,
                created_at=now,
                expires_at=now + lifetime_seconds,
                revoked=False,
            )
        return raw_token

    def validate_session_token(self, session_id: str, raw_token: str) -> bool:
        """Validate bearer token for session_id with expiry, revocation, and constant-time check."""
        if not session_id or not raw_token:
            return False
        try:
            safe_id = _validate_session_id(session_id)
        except ValueError:
            return False
        with self._lock:
            rec = self._tokens.get(safe_id)
            if not rec or rec.revoked:
                return False
            if time.time() > rec.expires_at:
                return False
            expected_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
            return hmac.compare_digest(expected_hash, rec.token_hash)

    def validate_any_session_token(self, raw_token: str) -> bool:
        """Validate bearer token against any active unexpired session token."""
        if not raw_token:
            return False
        now = time.time()
        expected_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        with self._lock:
            for rec in self._tokens.values():
                if not rec.revoked and rec.expires_at > now:
                    if hmac.compare_digest(expected_hash, rec.token_hash):
                        return True
        return False

    def revoke_session_token(self, session_id: str) -> None:
        """Revoke active token for session_id."""
        try:
            safe_id = _validate_session_id(session_id)
        except ValueError:
            return
        with self._lock:
            rec = self._tokens.get(safe_id)
            if rec:
                rec.revoked = True

    def create_session(
        self,
        name: str = "New Session",
        model_name: Optional[str] = None,
        provider_type: str = "ollama",
        task_mode: Optional[TaskMode | str] = None,
        autonomy_profile: Optional[AutonomyProfile | str] = None,
        permissions_mode: Optional[PermissionsMode | str] = None,
        project_dir: Optional[str | Path] = None,
    ) -> Session:
        settings = get_settings()
        m_mode = TaskMode(task_mode) if task_mode else TaskMode(getattr(settings, "default_task_mode", "planning"))
        a_profile = AutonomyProfile(autonomy_profile) if autonomy_profile else AutonomyProfile(getattr(settings, "default_autonomy_profile", "agentic"))
        if permissions_mode is not None:
            p_mode = PermissionsMode.from_str(permissions_mode)
        elif autonomy_profile is not None:
            p_mode = PermissionsMode.from_str(autonomy_profile)
        else:
            p_mode = PermissionsMode.from_str(getattr(settings, "default_permissions_mode", "auto"))

        session = Session(
            name=name,
            workspace_path=str(self.workspace_path),
            model_name=model_name or settings.model_for("chat"),
            provider_type=provider_type,
            task_mode=m_mode,
            autonomy_profile=a_profile,
            permissions_mode=p_mode,
            project_dir=str(project_dir) if project_dir else None,
        )
        self.save_session(session)
        return session

    def set_session_mode(
        self,
        session_id: str,
        task_mode: Optional[TaskMode | str] = None,
        autonomy_profile: Optional[AutonomyProfile | str] = None,
        permissions_mode: Optional[PermissionsMode | str] = None,
    ) -> bool:
        """Update task_mode, autonomy_profile, and/or permissions_mode on an existing session."""
        with self._lock:
            session = self.get_session(session_id)
            if not session:
                return False
            if task_mode:
                session.task_mode = TaskMode(task_mode)
            if autonomy_profile:
                session.autonomy_profile = AutonomyProfile(autonomy_profile)
            if permissions_mode is not None:
                session.permissions_mode = PermissionsMode.from_str(permissions_mode)
            elif autonomy_profile is not None:
                session.permissions_mode = PermissionsMode.from_str(autonomy_profile)
            self.save_session(session)
            return True

    def set_session_project_dir(self, session_id: str, project_dir: Optional[Union[str, Path]]) -> bool:
        """Update active project directory on an existing session."""
        with self._lock:
            session = self.get_session(session_id)
            if not session:
                return False
            session.project_dir = str(project_dir) if project_dir else None
            session.updated_at = time.time()
            self.save_session(session)
            return True

    def set_active_plan(self, session_id: str, plan: PlanArtifact) -> bool:
        """Store or update the active plan artifact on the session."""
        with self._lock:
            session = self.get_session(session_id)
            if not session:
                return False
            session.active_plan = plan
            self.save_session(session)
            return True

    def clear_active_plan(self, session_id: str) -> bool:
        """Clear the active plan artifact from the session."""
        with self._lock:
            session = self.get_session(session_id)
            if not session:
                return False
            session.active_plan = None
            self.save_session(session)
            return True

    def get_session(self, session_id: str) -> Optional[Session]:
        with self._lock:
            path = self._session_file_path(session_id)
            bak_path = path.with_suffix(path.suffix + ".bak")
            for target in (path, bak_path):
                if not target.exists():
                    continue
                try:
                    data, recovered = safe_read_json(target, max_retries=3)
                    if recovered:
                        logger.warning("Recovered JSON from backup: %s", target)
                    if isinstance(data, dict):
                        return Session(**data)
                except Exception as exc:
                    logger.debug("Failed reading session from %s: %s", target, exc)
                    continue
            return None

    def save_session(self, session: Session) -> None:
        with self._lock:
            session.updated_at = time.time()
            path = self._session_file_path(session.session_id)
            atomic_write_json(path, session.model_dump(), indent=2, sync=True, backup=True)

    def set_session_model(self, session_id: str, model_name: str, provider_type: Optional[str] = None) -> bool:
        """Update model_name (and optionally provider_type) on an existing session."""
        with self._lock:
            session = self.get_session(session_id)
            if not session:
                return False
            session.model_name = model_name
            if provider_type:
                session.provider_type = provider_type
            self.save_session(session)
            return True

    def list_sessions(self) -> List[Dict[str, Any]]:
        with self._lock:
            sessions = []
            for p in self.storage_dir.glob("*.json"):
                if p.name.endswith(".bak") or ".tmp" in p.name:
                    continue
                try:
                    data, _ = safe_read_json(p, fallback_backup=True)
                    if not isinstance(data, dict):
                        continue
                    sessions.append({
                        "session_id": data.get("session_id"),
                        "name": data.get("name"),
                        "created_at": data.get("created_at"),
                        "updated_at": data.get("updated_at"),
                        "model_name": data.get("model_name"),
                        "task_mode": data.get("task_mode", "planning"),
                        "autonomy_profile": data.get("autonomy_profile", "agentic"),
                        "has_active_plan": bool(data.get("active_plan")),
                        "task_status": data.get("task_status", "CREATED"),
                        "message_count": len(data.get("messages", [])),
                    })
                except Exception:
                    continue
            sessions.sort(key=lambda s: s.get("updated_at", 0), reverse=True)
            return sessions

    def append_message(self, session_id: str, role: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> ChatMessage:
        with self._lock:
            session = self.get_session(session_id)
            if not session:
                raise ValueError(f"Session {session_id} not found")
            msg = ChatMessage(role=role, content=content, metadata=metadata or {})
            session.messages.append(msg)
            self.save_session(session)
            return msg

    def record_tool(self, session_id: str, tool_name: str, arguments: Dict[str, Any], output: str, status: str, diff_id: Optional[str] = None) -> ToolRecord:
        with self._lock:
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
        with self._lock:
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

    def export_session(self, session_id: str, format: str = "markdown") -> Path:
        """Export session transcript and tool execution log to markdown."""
        safe_id = _validate_session_id(session_id)
        with self._lock:
            session = self.get_session(safe_id)
            if not session:
                raise ValueError(f"Session {session_id} not found")
            export_dir = (self.workspace_path / ".gameforge" / "exports").resolve()
            export_dir.mkdir(parents=True, exist_ok=True)
            export_path = (export_dir / f"{safe_id}.md").resolve()
            if export_path.parent != export_dir:
                raise ValueError(f"Export path escapes export directory: {session_id!r}")

            lines = [
                f"# GameForge Session Export: {session.name}",
                f"- **Session ID:** `{session.session_id}`",
                f"- **Model:** `{session.model_name}` ({session.provider_type})",
                f"- **Created:** `{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(session.created_at))}`",
                f"- **Updated:** `{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(session.updated_at))}`",
                f"- **Message Count:** {len(session.messages)}",
                "",
                "## Conversation Transcript",
                "",
            ]
            for msg in session.messages:
                role_header = f"### [{msg.role.upper()}] ({time.strftime('%H:%M:%S', time.localtime(msg.timestamp))})"
                lines.append(role_header)
                lines.append(msg.content)
                lines.append("")

            if session.tool_history:
                lines.append("## Tool Execution History")
                lines.append("")
                for tool in session.tool_history:
                    lines.append(f"- **Tool:** `{tool.tool_name}` — Status: `{tool.status}`")
                    lines.append(f"  - Arguments: `{tool.arguments}`")
                    lines.append(f"  - Output preview: `{tool.output[:200]}`")
                lines.append("")

            atomic_write_text(export_path, "\n".join(lines), encoding="utf-8", sync=True, backup=False)
            return export_path

    def delete_session(self, session_id: str) -> bool:
        """Delete session checkpoint and backup sidecar from disk."""
        with self._lock:
            path = self._session_file_path(session_id)
            self.revoke_session_token(session_id)
            backup_path = path.with_suffix(path.suffix + ".bak")
            removed = False
            for target in (path, backup_path):
                try:
                    if target.is_file():
                        target.unlink()
                        removed = True
                except OSError as exc:
                    logger.warning("Could not delete session file %s: %s", target, exc)
                    return False
            return removed
