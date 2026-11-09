"""Argument models for editor ops (AD-14), validated host-side before anything reaches the editor.

Hand-reviewed models below take precedence over the generated drafts in ``op_schemas_generated.py``
(``scripts/tools/gen_op_schemas.py``). In P0 an op without any schema passes through unchanged unless
``strict=True``; P2 makes strict validation the default for the agent gateway and the composer.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError

from .op_schemas_generated import GENERATED


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Vec3(_Strict):
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


class Rot3(_Strict):
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0


Label = Field(min_length=1, max_length=200)
GamePath = Field(pattern=r"^/(Game|Engine|Script)/")


# ── 6 Core Level Ops ─────────────────────────────────────────────────────────

class SpawnActorArgs(_Strict):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    label: Optional[str] = Field(None, min_length=1, max_length=200)
    actor_class: str = "StaticMeshActor"
    static_mesh: Optional[str] = Field(None, validation_alias=AliasChoices("static_mesh", "mesh_path"))
    location: Vec3 = Field(default_factory=Vec3)
    rotation: Rot3 = Field(default_factory=Rot3)
    scale: Optional[Vec3] = None
    mobility: Optional[str] = None
    material: Optional[str] = Field(None, validation_alias=AliasChoices("material", "material_path"))
    light_intensity: Optional[float] = None   # read only for light actors
    # Theme tint: linear RGB(A) 0..1. A cached MaterialInstanceConstant of BasicShapeMaterial ("Color" param)
    # is created per unique colour, so prototype geometry carries the game's art direction instead of grey.
    color: Optional[list[float]] = Field(None, min_length=3, max_length=4)
    light_color: Optional[list[float]] = Field(None, min_length=3, max_length=4)
    # Drop the actor onto the first blocking surface below it (landscape, floor) plus ground_offset cm.
    snap_to_ground: bool = False
    ground_offset: float = Field(0.0, ge=-1000.0, le=5000.0)
    # Actors whose labels start with these prefixes are ignored by the ground trace (decoration must not stack).
    snap_ignore_prefixes: list[str] = Field(default_factory=lambda: ["GF_Decor"], max_length=8)


class NewLevelArgs(_Strict):
    level_path: str = GamePath
    partitioned: bool = False
    if_exists: str = "load"


class LoadLevelArgs(_Strict):
    level_path: str = GamePath


class SetActorPropertyArgs(_Strict):
    label: str = Label
    property: str = Field(min_length=1, max_length=120)
    value: Any
    asset: bool = False  # value is an asset path to load


class DeleteActorArgs(_Strict):
    label: str = Label


class ActorsInLevelArgs(_Strict):
    limit: int = Field(1000, ge=1, le=100000)


# ── 24 Hand-Reviewed High-Use Ops (WI-0.8) ───────────────────────────────────

class AssetExistsArgs(_Strict):
    """Check if an asset exists and optionally match its class."""
    asset_path: str = Field(..., description="Unreal asset path e.g. /Game/Maps/MyMap")
    asset_class: Optional[str] = Field(None, description="Optional class name to match e.g. Material")


class ListAssetsArgs(_Strict):
    """List assets under a directory."""
    directory: str = Field("/Game", description="Root package path to search")
    recursive: bool = Field(True, description="Whether to recurse into subdirectories")
    limit: int = Field(500, ge=1, le=50000, description="Max assets to return")


class ImportAssetArgs(_Strict):
    """Import an asset from disk into the project."""
    source_file: str = Field(..., min_length=1, description="Absolute filesystem path to source file")
    destination_path: str = Field("/Game/Quarantine", description="Target Unreal package directory")
    replace_existing: bool = Field(False, description="Whether to overwrite existing asset")


class CreateMaterialArgs(_Strict):
    """Create a basic material with optional constant color/roughness/metallic/emissive."""
    asset_path: str = Field(..., description="Unreal asset path e.g. /Game/Materials/M_Base")
    base_color: Optional[list[float]] = Field(None, description="[R, G, B] base color (0..1)")
    roughness: Optional[float] = Field(None, ge=0.0, le=1.0, description="Roughness value (0..1)")
    metallic: Optional[float] = Field(None, ge=0.0, le=1.0, description="Metallic value (0..1)")
    emissive: Optional[list[float]] = Field(None, description="[R, G, B] emissive color")


class MaterialNodeSpec(_Strict):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    id: str = Field(..., min_length=1, description="Unique node ID in graph")
    class_name: str = Field(..., alias="class", description="MaterialExpression class name")
    x: int = Field(-600, description="Graph X coordinate")
    y: int = Field(0, description="Graph Y coordinate")
    props: Optional[dict[str, Any]] = Field(None, description="Node property overrides")


class MaterialEdgeSpec(_Strict):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    from_node: str = Field(..., alias="from", description="Source node ID")
    output: str = Field("", description="Output pin name")
    to_node: str = Field(..., alias="to", description="Target node ID")
    input: str = Field("", description="Input pin name")


class MaterialOutputSpec(_Strict):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    from_node: str = Field(..., alias="from", description="Source node ID")
    output: str = Field("", description="Output pin name")
    property: str = Field(..., description="MaterialProperty enum name e.g. MP_BASE_COLOR")


class MaterialBuildGraphArgs(_Strict):
    """Build a complete material node graph."""
    asset_path: str = Field(..., description="Target material asset path")
    replace_existing: bool = Field(False, description="Overwrite if already exists")
    nodes: list[MaterialNodeSpec] = Field(default_factory=list, description="Graph expression nodes")
    edges: list[MaterialEdgeSpec] = Field(default_factory=list, description="Connections between nodes")
    outputs: list[MaterialOutputSpec] = Field(default_factory=list, description="Connections to material inputs")
    usage_flags: list[str] = Field(default_factory=list, description="MaterialUsage flags")


class MaterialAssignToActorArgs(_Strict):
    """Assign a MaterialInterface to all mesh components on a level actor."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    label: Optional[str] = Field(None, description="Target actor label")
    actor_label: Optional[str] = Field(None, description="Alias for target actor label")
    material_path: Optional[str] = Field(None, description="MaterialInterface asset path")
    material: Optional[str] = Field(None, description="Alias for MaterialInterface asset path")
    slot: int = Field(0, ge=0, description="Material slot index")


class MaterialInstanceCreateArgs(_Strict):
    """Create a MaterialInstanceConstant from a parent material."""
    asset_path: str = Field(..., description="Asset path for the new instance")
    parent: str = Field(..., description="Parent material or instance path")
    scalars: Optional[dict[str, float]] = Field(None, description="Scalar parameter overrides")
    vectors: Optional[dict[str, list[float]]] = Field(None, description="Vector/color parameter overrides")
    textures: Optional[dict[str, str]] = Field(None, description="Texture parameter overrides (paths)")


class TextureImportArgs(_Strict):
    """Import an image file as a Texture2D with channel role presets."""
    source_file: str = Field(..., min_length=1, description="Absolute filesystem path to source file")
    destination_path: str = Field("/Game/Quarantine/Textures", description="Target package path")
    destination_name: Optional[str] = Field(None, description="Optional asset name override")
    role: str = Field("color", description="Texture role: color, normal, roughness, metallic, etc.")


class MeshPartSpec(_Strict):
    shape: str = Field(..., description="Primitive shape: box, cylinder, sphere, cone")
    op: str = Field("union", description="CSG operation: union or subtract")
    size: Optional[list[float]] = Field(None, description="[X, Y, Z] size for box")
    radius: Optional[float] = Field(None, description="Radius for cylinder/sphere/cone")
    height: Optional[float] = Field(None, description="Height for cylinder/cone")
    top_radius: Optional[float] = Field(None, description="Top radius for cone")
    radial_steps: Optional[int] = Field(None, description="Tessellation steps")
    height_steps: Optional[int] = Field(None, description="Height tessellation steps")
    steps: Optional[int] = Field(None, description="Steps for box")
    steps_phi: Optional[int] = Field(None, description="Phi steps for sphere")
    steps_theta: Optional[int] = Field(None, description="Theta steps for sphere")
    material_id: int = Field(0, description="Material slot index")
    location: Optional[Vec3] = Field(None, description="Offset position")
    rotation: Optional[Rot3] = Field(None, description="Rotation")
    scale: Optional[Vec3] = Field(None, description="Scale")


class MeshGeneratePropArgs(_Strict):
    """Procedurally generate a static mesh prop using Geometry Script."""
    asset_path: str = Field(..., description="Asset path for the created StaticMesh")
    parts: list[MeshPartSpec] = Field(default_factory=list, description="Geometric primitive parts")
    triangle_budget: int = Field(0, ge=0, description="Optional triangle reduction budget")


class StaticMeshConfigureArgs(_Strict):
    """Configure LODs, collision, nanite and materials on a StaticMesh."""
    static_mesh_path: str = Field(..., description="Target StaticMesh asset path")
    lod_reduction: Optional[list[float]] = Field(None, description="List of triangle reduction fractions")
    collision: Optional[str] = Field(None, description="Collision type e.g. complex_as_simple, box, sphere, none")
    nanite: Optional[bool] = Field(None, description="Enable or disable Nanite")
    materials: Optional[list[str]] = Field(None, description="Material asset paths per slot")


class PCGMeshEntry(_Strict):
    mesh: str = Field(..., description="StaticMesh asset path")
    weight: int = Field(1, ge=1, description="Selection weight")


class PCGNodeSpec(_Strict):
    id: str = Field(..., min_length=1, description="Node identifier")
    settings: str = Field(..., description="PCGSettings class name")
    props: Optional[dict[str, Any]] = Field(None, description="Property values for settings")
    meshes: Optional[list[PCGMeshEntry]] = Field(None, description="Mesh entries for mesh spawner")


class PCGEdgeSpec(_Strict):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    from_node: str = Field(..., alias="from", description="Source node ID")
    from_pin: str = Field("Out", description="Source pin name")
    to_node: str = Field(..., alias="to", description="Target node ID")
    to_pin: str = Field("In", description="Target pin name")


class PCGBuildGraphArgs(_Strict):
    """Build a procedural content generation (PCG) graph and spawn volume."""
    graph_path: str = Field(..., description="Asset path for the new PCGGraph")
    nodes: list[PCGNodeSpec] = Field(default_factory=list, description="PCG nodes")
    edges: list[PCGEdgeSpec] = Field(default_factory=list, description="Connections between PCG nodes")
    center: Vec3 = Field(default_factory=Vec3, description="Volume center position")
    extent: Vec3 = Field(default_factory=lambda: Vec3(x=5000, y=5000, z=5000), description="Volume extents (size)")
    label: str = Field("GF_PCGGraph", description="Actor label for spawned PCG volume")
    seed: Optional[int] = Field(None, description="Random seed")


class LandscapePaintLayerSpec(_Strict):
    name: str = Field(..., min_length=1, description="Paint layer name")
    rule: str = Field("low", description="Placement rule: low, steep, high")


class LandscapeCreateArgs(_Strict):
    """Create a procedural landscape with heightfield and paint layers."""
    component_count_x: int = Field(2, ge=1, le=64, description="Components along X")
    component_count_y: int = Field(2, ge=1, le=64, description="Components along Y")
    quads_per_section: int = Field(63, description="Quads per section (e.g. 63, 127)")
    sections_per_component: int = Field(1, description="Sections per component (1 or 2)")
    elevation_scale: float = Field(2000.0, description="Height elevation scale in cm")
    seed: int = Field(1337, description="Noise seed")
    terrain_type: str = Field("Valley", description="Terrain type: Valley, Mountains, Plateau")
    material_path: str = Field("", description="Optional landscape material asset path")
    paint_layers: Optional[list[LandscapePaintLayerSpec]] = Field(None, description="Paint layer rules")
    layer_info_path: str = Field("/Game/Landscape/LayerInfo", description="Folder for LayerInfo objects")
    high_start: float = Field(0.72, ge=0.0, le=1.0, description="Threshold for high rule")
    steep_start_cm_per_quad: float = Field(45.0, description="Slope threshold in cm per quad")


class SplineCreateRoadArgs(_Strict):
    """Create a procedural spline road/trail."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    road_name: str = Field("Road_MainTrail", description="Actor name for spline road")
    road_width: float = Field(400.0, description="Road width in cm")
    mesh_path: str = Field("/Engine/BasicShapes/Cube.Cube", description="StaticMesh for spline segments")
    material_path: str = Field("", validation_alias=AliasChoices("material_path", "road_material"), description="Optional road material path")
    points: list[Vec3] = Field(default_factory=list, description="Control points along the spline")


class FoliageScatterArgs(_Strict):
    """Scatter procedural instanced foliage on terrain."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    cluster_name: str = Field("Foliage_PineForest", description="Actor name for foliage cluster")
    mesh_path: str = Field("/Engine/BasicShapes/Cylinder.Cylinder", validation_alias=AliasChoices("mesh_path", "static_mesh"), description="Foliage StaticMesh path")
    material_path: str = Field("", description="Optional foliage material path")
    instance_count: int = Field(60, ge=1, description="Number of instances to scatter")
    seed: int = Field(777, description="Random seed")
    area_radius: float = Field(3500.0, description="Scatter radius in cm")
    min_elevation: float = Field(-500.0, description="Min Z elevation")
    max_elevation: float = Field(2500.0, description="Max Z elevation")
    max_slope_degrees: float = Field(35.0, description="Max surface slope in degrees")
    road_clearance: float = Field(450.0, description="Minimum clearance from road splines in cm")


class WorldClearGeneratedArgs(_Strict):
    """Delete generated actors (by DataLayer or prefix)."""
    data_layer_asset: Optional[str] = Field(None, description="Optional DataLayerAsset path")
    prefixes: list[str] = Field(default_factory=lambda: ["GF_"], description="Actor label prefixes to remove")


class DatalayerEnsureArgs(_Strict):
    """Ensure a DataLayerAsset exists and has an instance in the level."""
    asset_path: str = Field(..., description="DataLayerAsset path")


class DatalayerAddActorsArgs(_Strict):
    """Add actors to a DataLayer."""
    asset_path: str = Field(..., description="DataLayerAsset path")
    labels: list[str] = Field(..., description="Actor labels to assign")


class NavRebuildArgs(_Strict):
    """Trigger rebuild of navigation mesh."""
    pass


class NavFindPathArgs(_Strict):
    """Query real NavMesh for synchronous path between two points."""
    start: Vec3 = Field(..., description="Start location")
    end: Vec3 = Field(..., description="Target location")
    in_pie: bool = Field(False, description="Query PIE game world instead of editor world")


class PieStartArgs(_Strict):
    """Start Play-in-Editor session."""
    simulate: bool = Field(False, description="Simulate in editor without spawning player controller")


class PieStopArgs(_Strict):
    """Stop active Play-in-Editor session."""
    pass


class PieActorStateArgs(_Strict):
    """Query state/properties of actors during active PIE session."""
    actor_class: str = Field(..., min_length=1, description="Actor class path or name")
    properties: list[str] = Field(default_factory=list, description="Property names to query")


class VfxCreateSystemArgs(_Strict):
    """Create a NiagaraSystem from template system or emitters."""
    asset_path: str = Field(..., description="Target NiagaraSystem asset path")
    template_system: Optional[str] = Field(None, description="Engine template system name e.g. SimpleExplosion")
    template_emitters: list[str] = Field(default_factory=list, description="Template emitter names e.g. Fountain")


class AudioImportArgs(_Strict):
    """Import a WAV file as a SoundWave."""
    source_file: str = Field(..., min_length=1, description="Filesystem path to source WAV")
    destination_path: str = Field("/Game/Quarantine/Audio", description="Package path for asset")
    destination_name: Optional[str] = Field(None, description="Optional asset name override")
    looping: Optional[bool] = Field(None, description="Set looping property")
    attenuation_path: Optional[str] = Field(None, description="Optional SoundAttenuation asset path")


class AudioCreateAttenuationArgs(_Strict):
    """Create a SoundAttenuation settings asset."""
    asset_path: str = Field(..., description="Target SoundAttenuation asset path")
    inner_radius: float = Field(200.0, ge=0.0, description="Inner full-volume radius in cm")
    falloff_distance: float = Field(2000.0, ge=0.0, description="Falloff distance in cm")
    function: str = Field("LINEAR", description="Distance attenuation algorithm e.g. LINEAR, LOGARITHMIC")


class SequenceShotSpec(_Strict):
    camera_label: str = Field(..., min_length=1, description="Camera actor label")
    start: int = Field(..., ge=0, description="Start frame")
    end: int = Field(..., ge=0, description="End frame")
    location: Vec3 = Field(..., description="Camera world position")
    rotation: Rot3 = Field(..., description="Camera world rotation")


class SequenceTransformKeySpec(_Strict):
    frame: int = Field(..., ge=0, description="Keyframe index")
    location: Vec3 = Field(..., description="Transform position at frame")


class SequenceBindingSpec(_Strict):
    actor_label: str = Field(..., min_length=1, description="Actor to bind in sequence")
    keys: list[SequenceTransformKeySpec] = Field(default_factory=list, description="Transform keyframes")


class SequenceAudioSpec(_Strict):
    sound_path: str = Field(..., description="SoundWave asset path")
    start: int = Field(0, ge=0, description="Start frame")


class SequenceBuildArgs(_Strict):
    """Build a LevelSequence asset with camera shots, transform bindings and audio."""
    asset_path: str = Field(..., description="Asset path for the new LevelSequence")
    fps: int = Field(24, ge=1, le=120, description="Frames per second")
    end_frame: int = Field(72, ge=1, description="End frame")
    shots: list[SequenceShotSpec] = Field(default_factory=list, description="Camera shot sections")
    bindings: list[SequenceBindingSpec] = Field(default_factory=list, description="Actor transform bindings")
    audio: list[SequenceAudioSpec] = Field(default_factory=list, description="Audio track sections")


class ViewportScreenshotArgs(_Strict):
    """Request a viewport screenshot to disk."""
    output_path: str = Field(..., min_length=1, description="Target filesystem path for PNG")
    resolution: list[int] = Field(default_factory=lambda: [1280, 720], description="[width, height] in pixels")
    show_ui: bool = Field(False, description="Capture UI/UMG widgets alongside viewport")


class ActorSetTagsArgs(_Strict):
    label: str = Field(..., min_length=1, max_length=200)
    tags: list[str] = Field(default_factory=list)


class GameDefWriteArgs(_Strict):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    asset_path: str = Field("/Game/GameForge/GD_Main", pattern=r"^/(Game|Engine|Script)/")
    def_json: Any = Field(..., alias="json")


class GameDefInspectArgs(_Strict):
    asset_path: str = Field("/Game/GameForge/GD_Main", pattern=r"^/(Game|Engine|Script)/")


# ── Registry & Dispatch ──────────────────────────────────────────────────────

REVIEWED: dict[str, type[BaseModel]] = {
    # 6 core level ops
    "spawn_actor": SpawnActorArgs,
    "actor_set_tags": ActorSetTagsArgs,
    "gamedef_write": GameDefWriteArgs,
    "gamedef_inspect": GameDefInspectArgs,
    "new_level": NewLevelArgs,
    "load_level": LoadLevelArgs,
    "set_actor_property": SetActorPropertyArgs,
    "delete_actor": DeleteActorArgs,
    "actors_in_level": ActorsInLevelArgs,
    # 24+ hand-reviewed high-use ops
    "asset_exists": AssetExistsArgs,
    "list_assets": ListAssetsArgs,
    "import_asset": ImportAssetArgs,
    "create_material": CreateMaterialArgs,
    "material_build_graph": MaterialBuildGraphArgs,
    "material_instance_create": MaterialInstanceCreateArgs,
    "material_assign_to_actor": MaterialAssignToActorArgs,
    "texture_import": TextureImportArgs,
    "mesh_generate_prop": MeshGeneratePropArgs,
    "static_mesh_configure": StaticMeshConfigureArgs,
    "pcg_build_graph": PCGBuildGraphArgs,
    "landscape_create": LandscapeCreateArgs,
    "spline_create_road": SplineCreateRoadArgs,
    "foliage_scatter": FoliageScatterArgs,
    "world_clear_generated": WorldClearGeneratedArgs,
    "datalayer_ensure": DatalayerEnsureArgs,
    "datalayer_add_actors": DatalayerAddActorsArgs,
    "nav_rebuild": NavRebuildArgs,
    "nav_find_path": NavFindPathArgs,
    "pie_start": PieStartArgs,
    "pie_stop": PieStopArgs,
    "pie_actor_state": PieActorStateArgs,
    "vfx_create_system": VfxCreateSystemArgs,
    "audio_import": AudioImportArgs,
    "audio_create_attenuation": AudioCreateAttenuationArgs,
    "sequence_build": SequenceBuildArgs,
    "viewport_screenshot": ViewportScreenshotArgs,
}

SCHEMAS: dict[str, type[BaseModel]] = {**GENERATED, **REVIEWED}


def validate_args(op: str, args: dict, strict: bool = False) -> tuple[Optional[dict], list[str]]:
    """Return (clean_args, errors). ``clean_args`` is None when validation failed."""
    model = SCHEMAS.get(op)
    if model is None:
        return (None, [f"no argument schema for op {op!r}"]) if strict else (dict(args), [])
    try:
        return model.model_validate(args).model_dump(exclude_unset=True, by_alias=True), []
    except ValidationError as exc:
        return None, [f"{'.'.join(str(p) for p in e['loc']) or '<args>'}: {e['msg']}" for e in exc.errors()]
