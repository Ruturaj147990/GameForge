"""GPU Workload Scheduler & Service Contract for GameForge IDE.

Compliant with GameForge Master Blueprint:
- Serial GPU lock managing contention between LLM inference, Unreal rendering, and 3D generation.
- Service contract for generation endpoints: GET /health, POST /generate, POST /remesh, POST /texture, POST /cancel.
- Token authorization, idempotency on input hash, job timeout enforcement.
"""

from __future__ import annotations

import enum
import hashlib
import json
import secrets
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field


class GPUWorkloadType(str, enum.Enum):
    LLM_INFERENCE = "LLM_INFERENCE"
    ASSET_GENERATION = "ASSET_GENERATION"
    UNREAL_RENDER = "UNREAL_RENDER"
    LIGHTMAP_BAKE = "LIGHTMAP_BAKE"


class GPUSchedulerState(BaseModel):
    active_workload: Optional[GPUWorkloadType] = None
    active_owner: Optional[str] = None
    active_since: Optional[float] = None
    queue_depth: int = 0
    queued_workloads: List[Dict[str, Any]] = Field(default_factory=list)
    vram_capacity_mb: int = 12288  # 12 GB VRAM on host RX 7700 XT
    vram_used_mb: int = 0


class GPUScheduler:
    """Thread-safe workload scheduler for single-GPU host architectures."""

    def __init__(self, vram_capacity_mb: int = 12288):
        self._lock = threading.RLock()
        self._cv = threading.Condition(self._lock)
        self.vram_capacity_mb = vram_capacity_mb
        self.active_workload: Optional[GPUWorkloadType] = None
        self.active_owner: Optional[str] = None
        self.active_since: Optional[float] = None
        self._queue: List[Dict[str, Any]] = []

    def acquire(
        self,
        workload_type: GPUWorkloadType,
        owner_id: str,
        timeout_seconds: float = 30.0,
    ) -> bool:
        """Acquires exclusive GPU execution lock, waiting if another workload is active."""
        start_time = time.time()
        with self._lock:
            # If already holding, re-entry allowed for same owner
            if self.active_workload is not None and self.active_owner == owner_id:
                return True

            request_entry = {
                "id": str(uuid.uuid4())[:8],
                "type": workload_type,
                "owner": owner_id,
                "requested_at": start_time,
            }
            self._queue.append(request_entry)

            try:
                while self.active_workload is not None:
                    remaining = timeout_seconds - (time.time() - start_time)
                    if remaining <= 0:
                        # Timeout occurred while waiting in queue
                        return False
                    self._cv.wait(timeout=min(remaining, 0.5))

                # Acquired
                self.active_workload = workload_type
                self.active_owner = owner_id
                self.active_since = time.time()
                return True
            finally:
                if request_entry in self._queue:
                    self._queue.remove(request_entry)

    def release(self, owner_id: str) -> bool:
        """Releases GPU lock and notifies queued waiting workloads."""
        with self._lock:
            if self.active_owner != owner_id:
                return False
            self.active_workload = None
            self.active_owner = None
            self.active_since = None
            self._cv.notify_all()
            return True

    def get_state(self) -> GPUSchedulerState:
        """Returns snapshot of GPU scheduler state for UI diagnostics."""
        with self._lock:
            vram_est = 0
            if self.active_workload == GPUWorkloadType.LLM_INFERENCE:
                vram_est = 6144  # ~6GB for 8B-27B quantized models
            elif self.active_workload == GPUWorkloadType.ASSET_GENERATION:
                vram_est = 8192  # ~8GB for 3D generative diffusion
            elif self.active_workload == GPUWorkloadType.UNREAL_RENDER:
                vram_est = 4096

            return GPUSchedulerState(
                active_workload=self.active_workload,
                active_owner=self.active_owner,
                active_since=self.active_since,
                queue_depth=len(self._queue),
                queued_workloads=[
                    {"type": q["type"].value, "owner": q["owner"], "wait_s": round(time.time() - q["requested_at"], 2)}
                    for q in self._queue
                ],
                vram_capacity_mb=self.vram_capacity_mb,
                vram_used_mb=vram_est,
            )


class GPUServiceContract:
    """Service contract controller implementing the 3D generation HTTP endpoints."""

    def __init__(
        self,
        auth_token: str = "gf-gpu-auth-token-local",
        scheduler: Optional[GPUScheduler] = None,
    ):
        self.auth_token = auth_token
        self.scheduler = scheduler or GPUScheduler()
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self.idempotency_cache: Dict[str, str] = {}  # input_hash -> job_id
        self._contract_lock = threading.Lock()

    def _verify_token(self, token: Optional[str]) -> bool:
        return bool(token and secrets.compare_digest(str(token), self.auth_token))

    def health(self) -> Dict[str, Any]:
        """GET /health - Query GPU service health and status."""
        state = self.scheduler.get_state()
        return {
            "status": "ok",
            "gpu_device": "AMD Radeon RX 7700 XT",
            "vram_capacity_mb": state.vram_capacity_mb,
            "vram_used_mb": state.vram_used_mb,
            "active_workload": state.active_workload.value if state.active_workload else None,
            "queue_depth": state.queue_depth,
        }

    def generate(
        self,
        prompt: str,
        token: str,
        seed: int = 42,
        parameters: Optional[Dict[str, Any]] = None,
        timeout_seconds: float = 30.0,
    ) -> Dict[str, Any]:
        """POST /generate - Dispatches 3D asset generation."""
        if not self._verify_token(token):
            return {"ok": False, "error": "UNAUTHORIZED: Invalid or missing GPU service token"}

        # Calculate idempotency input hash
        input_data = f"{prompt}:{seed}:{json.dumps(parameters or {}, sort_keys=True)}"
        input_hash = hashlib.sha256(input_data.encode("utf-8")).hexdigest()

        # Check idempotency cache
        with self._contract_lock:
            if input_hash in self.idempotency_cache:
                prev_job_id = self.idempotency_cache[input_hash]
                return {
                    "ok": True,
                    "job_id": prev_job_id,
                    "input_hash": input_hash,
                    "cached": True,
                    **self.jobs[prev_job_id],
                }

        job_id = f"job-{uuid.uuid4().hex[:8]}"

        # Acquire GPU lock for ASSET_GENERATION
        acquired = self.scheduler.acquire(
            GPUWorkloadType.ASSET_GENERATION, owner_id=job_id, timeout_seconds=timeout_seconds
        )
        if not acquired:
            return {"ok": False, "error": "GPU_BUSY: Timeout waiting for GPU scheduler lock"}

        try:
            # Simulate generation artifact creation
            artifact_sha = hashlib.sha256(f"mesh-data:{input_hash}".encode("utf-8")).hexdigest()
            job_record = {
                "status": "COMPLETED",
                "prompt": prompt,
                "seed": seed,
                "input_hash": input_hash,
                "artifact_hashes": {
                    "mesh_obj": artifact_sha,
                    "material_mtl": hashlib.sha256(b"mtl-data").hexdigest(),
                },
                "completed_at": time.time(),
            }
            with self._contract_lock:
                self.jobs[job_id] = job_record
                self.idempotency_cache[input_hash] = job_id
            return {"ok": True, "job_id": job_id, "input_hash": input_hash, "cached": False, **job_record}
        finally:
            self.scheduler.release(job_id)

    def remesh(
        self,
        mesh_id: str,
        token: str,
        target_triangles: int = 5000,
        timeout_seconds: float = 30.0,
    ) -> Dict[str, Any]:
        """POST /remesh - Simplifies/retopologizes an existing 3D mesh."""
        if not self._verify_token(token):
            return {"ok": False, "error": "UNAUTHORIZED: Invalid or missing GPU service token"}
        job_id = f"remesh-{uuid.uuid4().hex[:8]}"
        acquired = self.scheduler.acquire(
            GPUWorkloadType.ASSET_GENERATION, owner_id=job_id, timeout_seconds=timeout_seconds
        )
        if not acquired:
            return {"ok": False, "error": "GPU_BUSY: Timeout waiting for GPU scheduler lock"}
        try:
            artifact_sha = hashlib.sha256(f"remesh:{mesh_id}:{target_triangles}".encode("utf-8")).hexdigest()
            job_record = {
                "status": "COMPLETED",
                "mesh_id": mesh_id,
                "target_triangles": target_triangles,
                "artifact_hashes": {"mesh_obj": artifact_sha},
                "completed_at": time.time(),
            }
            with self._contract_lock:
                self.jobs[job_id] = job_record
            return {"ok": True, "job_id": job_id, **job_record}
        finally:
            self.scheduler.release(job_id)

    def texture(
        self,
        mesh_id: str,
        prompt: str,
        token: str,
        resolution: int = 2048,
        timeout_seconds: float = 30.0,
    ) -> Dict[str, Any]:
        """POST /texture - Generates PBR texture set for a 3D mesh."""
        if not self._verify_token(token):
            return {"ok": False, "error": "UNAUTHORIZED: Invalid or missing GPU service token"}
        job_id = f"tex-{uuid.uuid4().hex[:8]}"
        acquired = self.scheduler.acquire(
            GPUWorkloadType.ASSET_GENERATION, owner_id=job_id, timeout_seconds=timeout_seconds
        )
        if not acquired:
            return {"ok": False, "error": "GPU_BUSY: Timeout waiting for GPU scheduler lock"}
        try:
            tex_sha = hashlib.sha256(f"texture:{mesh_id}:{prompt}:{resolution}".encode("utf-8")).hexdigest()
            job_record = {
                "status": "COMPLETED",
                "mesh_id": mesh_id,
                "prompt": prompt,
                "resolution": resolution,
                "artifact_hashes": {
                    "base_color": tex_sha,
                    "normal": hashlib.sha256(b"normal").hexdigest(),
                    "roughness": hashlib.sha256(b"roughness").hexdigest(),
                },
                "completed_at": time.time(),
            }
            with self._contract_lock:
                self.jobs[job_id] = job_record
            return {"ok": True, "job_id": job_id, **job_record}
        finally:
            self.scheduler.release(job_id)

    def cancel(self, job_id: str, token: str) -> Dict[str, Any]:
        """POST /cancel - Cancels active generation job."""
        if not self._verify_token(token):
            return {"ok": False, "error": "UNAUTHORIZED: Invalid or missing GPU service token"}

        with self._contract_lock:
            if job_id not in self.jobs:
                return {"ok": False, "error": f"Job {job_id} not found"}
            self.jobs[job_id]["status"] = "CANCELLED"

        self.scheduler.release(job_id)
        return {"ok": True, "job_id": job_id, "status": "CANCELLED"}
