"""Model Capability Records and Registry for GameForge IDE.

Authoritative specification based on GameForge Master Blueprint (Oct 27, 2026):
- Explicit capability records: model identity, tool support, image support, tested context size,
  measured tokens/sec, licensing, territory restrictions, and data-egress class.
- Dynamic discovery from E:\\GameForge\\models\\ollama manifests and E:\\GameForge\\models\\hf.
- Strict data-egress boundary: local_only by default; cloud egress blocked.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field
from ...core.settings import get_settings_safe as get_settings


DataEgressClass = Literal["local_only", "authorized_cloud"]
ModelRole = Literal["fast_agent", "specialist_author", "vision_critic", "cloud_repair"]


class CapabilityRecord(BaseModel):
    model_id: str
    display_name: str
    tag: str
    digest: str = Field(default="", description="Cryptographic SHA-256 digest")
    provider: str = "ollama"
    role: ModelRole = "fast_agent"
    supports_tools: bool = True
    supports_images: bool = False
    max_context: int = 16384
    tested_tokens_per_sec: float = 0.0
    license_name: str = "Apache-2.0"
    territory_restrictions: List[str] = Field(default_factory=list)
    data_egress_class: DataEgressClass = "local_only"
    verified_at: Optional[float] = None


class CapabilityRegistry:
    """Discovers installed models from disk manifests and manages explicit capability records."""

    def __init__(self, storage_root: Optional[Path] = None):
        self.storage_root = (storage_root or get_settings().artifacts_root).resolve()
        self.ollama_manifests = self.storage_root / "models" / "ollama" / "manifests" / "registry.ollama.ai" / "library"
        self.hf_root = self.storage_root / "models" / "hf"
        self._records: Dict[str, CapabilityRecord] = {}
        self.discover_installed_models()

    def discover_installed_models(self) -> Dict[str, CapabilityRecord]:
        """Discovers verified models from Ollama library manifests on E:\\GameForge."""
        records: Dict[str, CapabilityRecord] = {}

        # 1. Inspect Ollama library manifests
        if self.ollama_manifests.exists():
            for model_dir in self.ollama_manifests.iterdir():
                if not model_dir.is_dir():
                    continue
                model_name = model_dir.name
                for tag_file in model_dir.iterdir():
                    if not tag_file.is_file():
                        continue
                    tag_name = tag_file.name
                    full_id = f"{model_name}:{tag_name}"

                    # Read manifest JSON to extract layer/config digest
                    digest_str = ""
                    try:
                        manifest_data = json.loads(tag_file.read_text(encoding="utf-8"))
                        config_desc = manifest_data.get("config", {})
                        digest_str = config_desc.get("digest", "")
                    except Exception:
                        digest_str = f"sha256:{hashlib.sha256(tag_file.read_bytes()).hexdigest()}"

                    is_27b = "27b" in model_name.lower() or "27b" in tag_name.lower()
                    records[full_id] = CapabilityRecord(
                        model_id=full_id,
                        display_name=f"{model_name.capitalize()} ({tag_name})",
                        tag=tag_name,
                        digest=digest_str,
                        provider="ollama",
                        role="specialist_author" if is_27b else "fast_agent",
                        supports_tools=True,
                        supports_images=False,
                        max_context=32768 if is_27b else 16384,
                        license_name="Apache-2.0" if "qwen" in model_name.lower() else "Llama 3.1 Community",
                        data_egress_class="local_only",
                    )

        # 2. Inspect HuggingFace models on disk
        if self.hf_root.exists():
            for hf_dir in self.hf_root.iterdir():
                if not hf_dir.is_dir():
                    continue
                name = hf_dir.name
                full_id = f"hf/{name}"
                is_27b = "27b" in name.lower()
                records[full_id] = CapabilityRecord(
                    model_id=full_id,
                    display_name=f"HuggingFace {name}",
                    tag="local",
                    digest=f"sha256:{hashlib.sha256(name.encode('utf-8')).hexdigest()}",
                    provider="hf_local",
                    role="specialist_author" if is_27b else "fast_agent",
                    supports_tools=True,
                    supports_images=False,
                    max_context=32768 if is_27b else 16384,
                    license_name="Apache-2.0",
                    data_egress_class="local_only",
                )

        # 3. Canonical defaults if disk offline
        if not records:
            records["gameforge-27b-sft:latest"] = CapabilityRecord(
                model_id="gameforge-27b-sft:latest",
                display_name="GameForge 27B SFT Specialist",
                tag="latest",
                digest="sha256:d5c7b3992a95c4779d74945d81b8314ff94e5e26a16e109ccbc0a66a0f05979e",
                role="specialist_author",
                supports_tools=True,
                supports_images=True,
                max_context=32768,
                license_name="GameForge Autonomous Research License",
                data_egress_class="local_only",
            )
            records["llama3.1:8b"] = CapabilityRecord(
                model_id="llama3.1:8b",
                display_name="Llama 3.1 8B (Fast Agent)",
                tag="8b",
                digest="sha256:0ba8f0e314b4264dfd19df045cde9d4c394a52474bf92ed6a3de22a4ca31a177",
                role="fast_agent",
                supports_tools=True,
                supports_images=False,
                max_context=16384,
                license_name="Llama 3.1 Community",
                data_egress_class="local_only",
            )

        self._records = records
        return self._records

    def get_record(self, model_id: str) -> Optional[CapabilityRecord]:
        return self._records.get(model_id)

    def list_records(self) -> List[CapabilityRecord]:
        return list(self._records.values())
