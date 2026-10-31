"""FastAPI Backend Server and WebSocket Hub for GameForge IDE."""

from __future__ import annotations

import json
import hmac
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from .agent.runtime import AgentRuntime
from .providers.router import ModelRouter
from .session_manager import SessionManager
from .tools.gateway import ToolGateway
from .unreal_context import UnrealEditorContext, persist_unreal_context
from ..core.settings import get_settings

app = FastAPI(
    title="GameForge IDE Backend",
    version="1.0.0",
    description="Agentic Game Development IDE Backend",
)

# Global runtime state
WORKSPACE_ROOT = get_settings().default_workspace.resolve()
session_manager = SessionManager(WORKSPACE_ROOT)
model_router = ModelRouter()
tool_gateway = ToolGateway(WORKSPACE_ROOT)
agent_runtime = AgentRuntime(WORKSPACE_ROOT, session_manager, model_router)

# Store for editor context received from Unreal Engine plugin
latest_unreal_context: Dict[str, Any] = {
    "project_name": "",
    "engine_version": "",
    "selected_actor": "",
    "active_asset": "",
    "open_assets": [],
    "last_sync": None,
}


class CreateSessionRequest(BaseModel):
    name: str = "New Session"
    model_name: str = "gameforge-27b-sft"
    provider_type: str = "ollama"


class ExecuteToolRequest(BaseModel):
    name: str
    arguments: Dict[str, Any] = {}


class GenerateAssetRequest(BaseModel):
    name: str = "SM_BlockoutCube"
    size: float = 100.0


@app.get("/api/health")
def get_health() -> Dict[str, Any]:
    ollama_ok = model_router.get_provider("ollama").is_available()
    engine_info = tool_gateway.unreal_tools.get_engine_info()
    return {
        "status": "ok",
        "version": "1.0.0",
        "workspace": str(WORKSPACE_ROOT),
        "local_ollama_online": ollama_ok,
        "unreal_engine_5_7_detected": engine_info.get("installed", False),
    }


def require_unreal_bridge_auth(authorization: Optional[str] = Header(default=None)) -> None:
    """Require a shared bearer secret for editor metadata read/write routes."""
    configured_token = os.environ.get("GAMEFORGE_BRIDGE_TOKEN", "").strip()
    if not configured_token:
        raise HTTPException(
            status_code=503,
            detail="Unreal bridge is disabled: GAMEFORGE_BRIDGE_TOKEN is not configured.",
        )
    expected = f"Bearer {configured_token}"
    if authorization is None or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Invalid Unreal bridge bearer token.")


@app.get("/api/workspace")
def get_workspace() -> Dict[str, Any]:
    git_stat = tool_gateway.git_tools.get_status()
    uprojects = tool_gateway.unreal_tools.find_uprojects()
    engine_info = tool_gateway.unreal_tools.get_engine_info()
    return {
        "workspace_root": str(WORKSPACE_ROOT),
        "git": git_stat,
        "unreal_projects": uprojects,
        "engine_info": engine_info,
    }


@app.get("/api/models")
def get_models() -> List[Dict[str, Any]]:
    models = model_router.list_all_models()
    return [m.model_dump() for m in models]


@app.get("/api/sessions")
def list_sessions() -> List[Dict[str, Any]]:
    return session_manager.list_sessions()


@app.post("/api/sessions")
def create_session(req: CreateSessionRequest) -> Dict[str, Any]:
    session = session_manager.create_session(
        name=req.name,
        model_name=req.model_name,
        provider_type=req.provider_type,
    )
    return session.model_dump()


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str) -> Dict[str, Any]:
    s = session_manager.get_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    return s.model_dump()


@app.get("/api/tools")
def get_tools() -> List[Dict[str, Any]]:
    defs = tool_gateway.get_definitions()
    return [d.model_dump() for d in defs]


@app.post("/api/tools/execute")
def execute_tool(req: ExecuteToolRequest) -> Dict[str, Any]:
    return tool_gateway.execute_tool(req.name, req.arguments)


@app.post("/api/diffs/{diff_id}/approve")
def approve_diff(diff_id: str) -> Dict[str, Any]:
    res = tool_gateway.edit_tools.apply_diff(diff_id)
    if res.get("status") == "ERROR":
        raise HTTPException(status_code=400, detail=res.get("error"))
    return res


@app.post("/api/diffs/{diff_id}/reject")
def reject_diff(diff_id: str) -> Dict[str, Any]:
    return tool_gateway.edit_tools.reject_diff(diff_id)


@app.post("/api/diffs/{diff_id}/rollback")
def rollback_diff(diff_id: str) -> Dict[str, Any]:
    res = tool_gateway.edit_tools.rollback_diff(diff_id)
    if res.get("status") == "ERROR":
        raise HTTPException(status_code=400, detail=res.get("error"))
    return res


@app.post("/api/unreal/context", dependencies=[Depends(require_unreal_bridge_auth)])
def receive_unreal_context(ctx: UnrealEditorContext) -> Dict[str, Any]:
    global latest_unreal_context
    try:
        latest_unreal_context = persist_unreal_context(WORKSPACE_ROOT, ctx)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Could not store Unreal context: {exc}") from exc
    return {"status": "SUCCESS", "received": latest_unreal_context}


@app.get("/api/unreal/context", dependencies=[Depends(require_unreal_bridge_auth)])
def get_unreal_context() -> Dict[str, Any]:
    return latest_unreal_context


@app.post("/api/assets/generate")
def generate_asset(req: GenerateAssetRequest) -> Dict[str, Any]:
    res = tool_gateway.asset_tools.generate_cube(name=req.name, size=req.size)
    return res


@app.websocket("/api/ws/agent/{session_id}")
async def agent_websocket(websocket: WebSocket, session_id: str):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            prompt = payload.get("prompt", "")
            if not prompt:
                continue

            async for event in agent_runtime.execute_task_stream(session_id, prompt):
                await websocket.send_text(json.dumps(event.model_dump()))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_text(json.dumps({"event_type": "error", "content": str(e)}))
        except Exception:
            pass

