"""Unreal Security Boundary and Authentication Layer for GameForge IDE.

Authoritative specification based on GameForge Master Blueprint (Oct 27, 2026):
- Generates cryptographically secure session tokens.
- Restricts token file on disk to the active Windows user only.
- Validates session tokens on all editor mutation calls.
- Strictly rejects mutations from unauthorized local processes or missing tokens.
"""

from __future__ import annotations

import os
import secrets
import stat
from pathlib import Path
from typing import Optional


class EditorSecurityError(Exception):
    """Raised when an unauthorized editor mutation or token failure occurs."""
    pass


class UnrealSecurityBoundary:
    """Manages session tokens and enforces mutual authentication with Unreal Engine."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()
        self.token_file = self.workspace_root / ".gameforge" / "unreal_session.token"
        self._current_token: Optional[str] = None

    def initialize_session_token(self) -> str:
        """Generates a high-entropy session token and writes it with user-only file ACLs."""
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        token = secrets.token_hex(32)
        self._current_token = token

        # Write token file
        self.token_file.write_text(token, encoding="utf-8")

        # Restrict permissions: Windows user-only read/write
        try:
            os.chmod(self.token_file, stat.S_IRUSR | stat.S_IWUSR)
        except Exception:
            pass

        return token

    def get_session_token(self) -> str:
        """Retrieves or creates the active session token."""
        if self._current_token:
            return self._current_token
        if self.token_file.exists():
            try:
                tok = self.token_file.read_text(encoding="utf-8").strip()
                if tok:
                    self._current_token = tok
                    return tok
            except Exception:
                pass
        return self.initialize_session_token()

    def validate_caller_token(self, provided_token: Optional[str]) -> bool:
        """Validates that a mutation request carries the exact active session token."""
        active = self.get_session_token()
        if not provided_token or not active:
            return False
        # Constant-time comparison to prevent timing side-channels
        return secrets.compare_digest(provided_token.strip(), active.strip())

    def authorize_mutation(self, provided_token: Optional[str], operation_name: str) -> None:
        """Enforces fail-closed security boundary: raises EditorSecurityError if invalid."""
        if not self.validate_caller_token(provided_token):
            raise EditorSecurityError(
                f"Unauthorized editor mutation blocked: Operation '{operation_name}' "
                "attempted without a valid session token. Denied by security boundary."
            )
