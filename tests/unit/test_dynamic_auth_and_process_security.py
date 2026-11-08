import os
import pytest
from fastapi.testclient import TestClient
from src.gameforge_ide.backend.app import app, require_session_auth
from src.gameforge_ide.backend.session_manager import SessionManager
from src.gameforge_ide.core.process_manager import sanitize_environment

def test_dynamic_session_token_lifecycle(tmp_path):
    sm = SessionManager(tmp_path)
    sess = sm.create_session("AuthTestSession")
    
    # 1. Issue token
    token = sm.issue_session_token(sess.session_id, lifetime_seconds=10.0)
    assert token and isinstance(token, str)
    assert len(token) > 20
    
    # 2. Valid token check
    assert sm.validate_session_token(sess.session_id, token) is True
    
    # 3. Wrong token / wrong session check
    assert sm.validate_session_token(sess.session_id, "invalid_token_xyz") is False
    assert sm.validate_session_token("nonexistent_session", token) is False
    
    # 4. Token revocation check
    sm.revoke_session_token(sess.session_id)
    assert sm.validate_session_token(sess.session_id, token) is False

def test_child_process_environment_sanitization():
    dirty_env = {
        "PATH": "C:\\Windows\\system32",
        "USER": "developer",
        "GAMEFORGE_API_TOKEN": "secret_admin_token_12345",
        "GAMEFORGE_BRIDGE_TOKEN": "secret_bridge_token_67890",
        "GAMEFORGE_SECRET_KEY": "super_secret_key",
        "CUSTOM_VAR": "safe_value",
    }
    clean = sanitize_environment(base_env=dirty_env)
    assert "PATH" in clean
    assert "USER" in clean
    assert "CUSTOM_VAR" in clean
    assert "GAMEFORGE_API_TOKEN" not in clean
    assert "GAMEFORGE_BRIDGE_TOKEN" not in clean
    assert "GAMEFORGE_SECRET_KEY" not in clean

def test_fastapi_lifespan_state_attachment():
    with TestClient(app) as client:
        # Check that app.state attributes are attached during lifespan
        assert hasattr(app.state, "session_manager")
        assert hasattr(app.state, "model_router")
        assert hasattr(app.state, "tool_gateway")
        assert hasattr(app.state, "agent_runtime")
        
        # Test creating session via client returns bearer_token
        res = client.post("/api/sessions", json={"name": "ClientSession"})
        assert res.status_code == 200
        data = res.json()
        assert "bearer_token" in data
        assert "session_id" in data
