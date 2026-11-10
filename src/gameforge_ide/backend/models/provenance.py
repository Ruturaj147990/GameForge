"""Asset Provenance and License Registry for GameForge IDE.

Compliant with GameForge Master Blueprint:
- Cryptographic SHA-256 hashes of inputs, generator seeds, and output artifacts.
- License compliance and territory restriction enforcement (e.g. Hunyuan 3D 2.1).
- Complete gate records for Stages 1 through 8.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field


class LicenseRecord(BaseModel):
    """Model license definition with commercial terms and distribution territory limits."""
    model_name: str
    version: str
    license_name: str
    commercial_use_allowed: bool = True
    excluded_territories: List[str] = Field(default_factory=list)
    attribution_required: bool = False
    source_url: str = ""


class AssetProvenanceRecord(BaseModel):
    """Full cryptographic provenance record saved alongside every generated asset."""
    asset_id: str
    asset_name: str
    model_name: str
    model_version: str
    license_name: str
    territory_flags: List[str] = Field(default_factory=list)
    target_territory: str = "GLOBAL"
    input_hashes: Dict[str, str] = Field(default_factory=dict)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    seed: int = 42
    tool_versions: Dict[str, str] = Field(default_factory=dict)
    output_hashes: Dict[str, str] = Field(default_factory=dict)
    gate_results: Dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)
    provenance_hash: Optional[str] = None

    def compute_record_hash(self) -> str:
        """Computes SHA-256 hash of the canonical serialized provenance metadata."""
        record_dict = self.model_dump(exclude={"provenance_hash"})
        canonical_json = json.dumps(record_dict, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    def seal(self) -> str:
        """Calculates and stores the cryptographic digest for this provenance record."""
        self.provenance_hash = self.compute_record_hash()
        return self.provenance_hash

    def save_to_file(self, target_path: Path | str) -> Path:
        """Saves formatted provenance record to disk next to the asset atomically."""
        from ...storage.atomic import atomic_write_json
        p = Path(target_path)
        self.seal()
        atomic_write_json(p, self.model_dump(), indent=2, sync=True)
        return p


class LicenseRegistry:
    """Authoritative registry of generator model licenses and territory constraints."""

    # Default registry of known 3D generative models and procedural engines
    KNOWN_LICENSES: Dict[str, LicenseRecord] = {
        "TRELLIS.2": LicenseRecord(
            model_name="TRELLIS.2",
            version="2.0",
            license_name="MIT",
            commercial_use_allowed=True,
            excluded_territories=[],
            attribution_required=True,
            source_url="https://github.com/microsoft/TRELLIS",
        ),
        "Hunyuan3D-2.1": LicenseRecord(
            model_name="Hunyuan3D-2.1",
            version="2.1",
            license_name="Hunyuan-Community",
            commercial_use_allowed=True,
            excluded_territories=["EU", "UK", "KR"],  # Excluded by Tencent Community Terms
            attribution_required=True,
            source_url="https://github.com/Tencent/Hunyuan3D-2",
        ),
        "TripoSR": LicenseRecord(
            model_name="TripoSR",
            version="1.0",
            license_name="MIT",
            commercial_use_allowed=True,
            excluded_territories=[],
            attribution_required=True,
            source_url="https://github.com/VAST-AI-Research/TripoSR",
        ),
        "Shap-E": LicenseRecord(
            model_name="Shap-E",
            version="1.0",
            license_name="MIT",
            commercial_use_allowed=True,
            excluded_territories=[],
            attribution_required=False,
            source_url="https://github.com/openai/shap-e",
        ),
        "GameForge-Procedural": LicenseRecord(
            model_name="GameForge-Procedural",
            version="1.0",
            license_name="Proprietary-Project",
            commercial_use_allowed=True,
            excluded_territories=[],
            attribution_required=False,
            source_url="local://gameforge/procedural",
        ),
        "GameForge-ProceduralRig-V1": LicenseRecord(
            model_name="GameForge-ProceduralRig-V1",
            version="1.0.0",
            license_name="CC-BY-4.0",
            commercial_use_allowed=True,
            excluded_territories=[],
            attribution_required=True,
            source_url="local://gameforge/character_rig",
        ),
        "EpicGames-Engine-Content": LicenseRecord(
            model_name="EpicGames-Engine-Content",
            version="5.7.4",
            license_name="Unreal-Engine-EULA",
            commercial_use_allowed=True,
            excluded_territories=[],
            attribution_required=True,
            source_url="https://unrealengine.com/eula",
        ),
    }

    def __init__(self, custom_records: Optional[Dict[str, LicenseRecord]] = None):
        self.registry = dict(self.KNOWN_LICENSES)
        if custom_records:
            self.registry.update(custom_records)

    def register_model(self, record: LicenseRecord) -> None:
        """Registers or updates a model license record."""
        self.registry[record.model_name] = record

    def get_license(self, model_name: str) -> Optional[LicenseRecord]:
        """Retrieves license record for a given model."""
        return self.registry.get(model_name)

    def validate_territory_compliance(
        self, model_name: str, target_territory: str = "GLOBAL"
    ) -> Tuple[bool, Optional[str]]:
        """Validates that using model_name does not violate license territory restrictions.

        Returns:
            Tuple of (is_compliant, error_message).
        """
        record = self.get_license(model_name)
        if not record:
            return False, f"UNKNOWN_MODEL: No license record found for model '{model_name}'"

        target_upper = target_territory.upper()

        # If target territory is GLOBAL or explicitly matches an excluded territory
        if record.excluded_territories:
            if target_upper == "GLOBAL":
                return False, (
                    f"LICENCE_TERRITORY_CONFLICT: Model '{model_name}' license '{record.license_name}' "
                    f"excludes territories {record.excluded_territories} and cannot be used for GLOBAL distribution."
                )
            if target_upper in [t.upper() for t in record.excluded_territories]:
                return False, (
                    f"LICENCE_TERRITORY_CONFLICT: Model '{model_name}' license '{record.license_name}' "
                    f"excludes target territory '{target_territory}'."
                )

        return True, None
