"""API Integration Tests for GameForge IDE Backend Endpoints."""

from uuid import uuid4
from importlib import import_module
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.gameforge_ide.backend.app import app
from src.gameforge_ide.launcher import _is_loopback_host

backend_app = import_module("src.gameforge_ide.backend.app")


def test_bridge_server_host_is_loopback_only():
    assert _is_loopback_host("127.0.0.1")
    assert _is_loopback_host("localhost")
    assert _is_loopback_host("::1")
    assert not _is_loopback_host("0.0.0.0")
    assert not _is_loopback_host("192.168.1.25")
    assert not _is_loopback_host("gameforge.example")


@pytest.fixture
def client():
    repo_root = Path(__file__).resolve().parent.parent.parent
    backend_app.tool_gateway = backend_app.ToolGateway(repo_root)
    return TestClient(app)


def test_api_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "local_ollama_online" in data
    assert "unreal_engine_5_7_detected" in data


def test_api_workspace(client):
    response = client.get("/api/workspace")
    assert response.status_code == 200
    data = response.json()
    assert "workspace_root" in data
    assert "git" in data
    assert "unreal_projects" in data


def test_api_models(client):
    response = client.get("/api/models")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_api_session_lifecycle(client):
    session_id = None
    try:
        create_res = client.post("/api/sessions", json={"name": "Integration Test Session"})
        assert create_res.status_code == 200
        session_data = create_res.json()
        session_id = session_data["session_id"]
        assert session_id is not None

        get_res = client.get(f"/api/sessions/{session_id}")
        assert get_res.status_code == 200
        assert get_res.json()["name"] == "Integration Test Session"

        list_res = client.get("/api/sessions")
        assert list_res.status_code == 200
        session_ids = [s["session_id"] for s in list_res.json()]
        assert session_id in session_ids
    finally:
        if session_id:
            session_file = backend_app.session_manager.storage_dir / f"{session_id}.json"
            session_file.unlink(missing_ok=True)


def test_api_tools_list_and_execution(client):
    # List tools
    tools_res = client.get("/api/tools")
    assert tools_res.status_code == 200
    tools = tools_res.json()
    tool_names = [t["name"] for t in tools]
    assert "list_dir" in tool_names
    assert "read_file" in tool_names
    assert "generate_3d_mesh" in tool_names

    # Execute list_dir
    exec_res = client.post(
        "/api/tools/execute",
        json={"name": "list_dir", "arguments": {"subpath": "src", "max_depth": 1}},
    )
    assert exec_res.status_code == 200
    data = exec_res.json()
    assert data["status"] == "SUCCESS"
    assert data["count"] > 0


def test_api_asset_generation(client):
    # Never overwrite a user-created generated asset during endpoint tests.
    asset_name = f"SM_ApiTestCube_{uuid4().hex[:8]}"
    output_dir = Path(r"E:\GameForge\assets\generated\meshes")
    try:
        res = client.post(
            "/api/assets/generate",
            json={"name": asset_name, "size": 120.0},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "SUCCESS"
        assert data["vertex_count"] == 8
        assert data["triangle_count"] == 12
        assert "sha256" in data
    finally:
        for extension in ("obj", "mtl", "ue_import.json"):
            (output_dir / f"{asset_name}.{extension}").unlink(missing_ok=True)


def test_api_unreal_context_requires_token(client, monkeypatch):
    monkeypatch.delenv("GAMEFORGE_BRIDGE_TOKEN", raising=False)
    payload = {"project_name": "AuthProbe", "engine_version": "5.7.4"}
    assert client.post("/api/unreal/context", json=payload).status_code == 503
    assert client.get("/api/unreal/context").status_code == 503

    monkeypatch.setenv("GAMEFORGE_BRIDGE_TOKEN", "unit-test-bridge-secret")
    assert client.post("/api/unreal/context", json=payload).status_code == 401
    assert client.post(
        "/api/unreal/context",
        json=payload,
        headers={"Authorization": "Bearer wrong-secret"},
    ).status_code == 401


def test_api_unreal_context_sync(client, monkeypatch):
    bridge_token = "unit-test-bridge-secret"
    monkeypatch.setenv("GAMEFORGE_BRIDGE_TOKEN", bridge_token)
    context_path = Path(backend_app.WORKSPACE_ROOT) / ".gameforge" / "unreal_context.json"
    previous_bytes = context_path.read_bytes() if context_path.exists() else None
    previous_context = dict(backend_app.latest_unreal_context)
    payload = {
        "project_name": "GameForgeShooter",
        "engine_version": "5.7.4",
        "selected_actor": "BP_HealthPickup_C_1",
        "active_asset": "/Game/Blueprints/BP_HealthPickup",
    }
    try:
        auth_headers = {"Authorization": f"Bearer {bridge_token}"}
        sync_res = client.post("/api/unreal/context", json=payload, headers=auth_headers)
        assert sync_res.status_code == 200
        assert sync_res.json()["status"] == "SUCCESS"

        get_res = client.get("/api/unreal/context", headers=auth_headers)
        assert get_res.status_code == 200
        data = get_res.json()
        assert data["project_name"] == "GameForgeShooter"
        assert data["selected_actor"] == "BP_HealthPickup_C_1"
    finally:
        backend_app.latest_unreal_context.clear()
        backend_app.latest_unreal_context.update(previous_context)
        if previous_bytes is None:
            context_path.unlink(missing_ok=True)
        else:
            restore_path = context_path.with_suffix(".restore.tmp")
            restore_path.write_bytes(previous_bytes)
            restore_path.replace(context_path)
