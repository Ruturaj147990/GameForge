import pytest

from gameforge_ide.backend.assets import AssetRecord, AssetRegistry


def _hero():
    return AssetRecord(name="GFAdventurerHero", asset_type="skeletal_mesh", purpose="player character",
                       provenance="procedural", backend="ProceduralSkinnedCharacterGenerator", backend_version="1",
                       license="project-owned", spec={"height_cm": 182, "bones": 20}, tags=["hero", "humanoid"])


@pytest.fixture
def registry(tmp_path):
    reg = AssetRegistry(tmp_path)
    yield reg
    reg.close()


def test_lifecycle_and_promotion_gate(registry, tmp_path):
    asset_id = registry.register(_hero())
    artifact = tmp_path / "hero.gltf"
    artifact.write_text("{}")
    registry.advance(asset_id, "GENERATE", True, artifact_path=str(artifact))
    with pytest.raises(ValueError, match="ENGINE_VERIFY"):
        registry.advance(asset_id, "PROMOTE", True)
    registry.advance(asset_id, "ENGINE_VERIFY", False, "deformation NaN")
    assert registry.get(asset_id)["stage"] == "GENERATE"
    registry.advance(asset_id, "ENGINE_VERIFY", True, evidence=["reports/audit_m9_m10_completion.json"])
    registry.advance(asset_id, "PROMOTE", True, unreal_path="/Game/Characters/GFAdventurerHero")
    row = registry.get(asset_id)
    assert (row["stage"], row["unreal_path"], row["provenance"]) == (
        "PROMOTE", "/Game/Characters/GFAdventurerHero", "procedural")
    assert [h["stage"] for h in registry.history(asset_id)] == [
        "GENERATE", "ENGINE_VERIFY", "ENGINE_VERIFY", "PROMOTE"]


def test_artifact_tamper_detection(registry, tmp_path):
    asset_id = registry.register(_hero())
    artifact = tmp_path / "hero.gltf"
    artifact.write_text("{}")
    registry.advance(asset_id, "GENERATE", True, artifact_path=str(artifact))
    assert registry.artifact_unchanged(asset_id)
    artifact.write_text('{"edited": true}')
    assert not registry.artifact_unchanged(asset_id)


def test_rejects_dishonest_or_incomplete_records(registry):
    for field, value in (("provenance", "ai-ish"), ("asset_type", "thing"), ("license", " ")):
        record = _hero()
        setattr(record, field, value)
        with pytest.raises(ValueError):
            registry.register(record)


def test_search_dependencies_and_persistence(tmp_path):
    reg = AssetRegistry(tmp_path)
    hero = reg.register(_hero())
    reg.add_dependency(hero, "material:M_Skin:abc")
    reg.close()
    reg = AssetRegistry(tmp_path)
    assert [r["asset_id"] for r in reg.search("humanoid", asset_type="skeletal_mesh")] == [hero]
    assert reg.search("dragon") == []
    assert reg.dependencies(hero) == ["material:M_Skin:abc"]
    reg.close()
