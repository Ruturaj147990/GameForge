"""GameForge in-editor operation library (runs inside UnrealEditor's embedded Python).

Every operation is a named function taking a JSON-compatible dict and returning the
Blueprint envelope: ok, op, data, warnings, errors, affected_paths, reversibility.

Rules enforced here (Master Blueprint v2, section 4):
  * Calls must carry the session token written by the GameForge supervisor to
    <Project>/Saved/GameForge/session.token. No token, no call (fail closed).
  * Mutations run inside ScopedEditorTransaction where the editor supports undo.
  * Every mutation returns read-back data queried from the editor after the write.
  * Assets are moved/created only through AssetTools / EditorAssetLibrary.

The host invokes ``dispatch(request_json)``; the result is printed as a single line
prefixed with RESULT_SENTINEL so the host can parse it from the command output.
"""

import json
import os
import traceback

import unreal

LIBRARY_VERSION = "2.0.0"
RESULT_SENTINEL = "@@GAMEFORGE_RESULT@@"

_OPS = {}


def op(name, mutates=False, reversibility="read-only"):
    def wrap(fn):
        _OPS[name] = {"fn": fn, "mutates": mutates, "reversibility": reversibility}
        return fn
    return wrap


def _envelope(name, ok, data=None, errors=None, warnings=None, affected=None, reversibility="read-only"):
    return {
        "ok": bool(ok),
        "op": name,
        "data": data or {},
        "warnings": warnings or [],
        "errors": errors or [],
        "affected_paths": affected or [],
        "reversibility": reversibility,
    }


def _token_path():
    return os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()),
                        "GameForge", "session.token")


def _check_token(provided):
    path = _token_path()
    if not os.path.isfile(path):
        return "session token file missing: supervisor did not initialise this editor"
    with open(path, "r", encoding="utf-8") as fh:
        expected = fh.read().strip()
    if not provided or not expected:
        return "session token missing"
    import hmac
    if not hmac.compare_digest(str(provided).strip(), expected):
        return "session token mismatch"
    return None


def _actor_sub():
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def _level_sub():
    return unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)


def _find_actor(label):
    for actor in _actor_sub().get_all_level_actors():
        if actor.get_actor_label() == label:
            return actor
    return None


def _vec(d, default=(0.0, 0.0, 0.0)):
    d = d or {}
    return unreal.Vector(float(d.get("x", default[0])), float(d.get("y", default[1])), float(d.get("z", default[2])))


def _rot(d):
    d = d or {}
    return unreal.Rotator(float(d.get("roll", 0.0)), float(d.get("pitch", 0.0)), float(d.get("yaw", 0.0)))


def _active_log_path():
    cmd = unreal.SystemLibrary.get_command_line()
    for tok in cmd.split():
        if tok.lower().startswith("-abslog="):
            return tok.split("=", 1)[1].strip('"')
    log_dir = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_log_dir())
    return os.path.join(log_dir, unreal.SystemLibrary.get_game_name() + ".log")


def _log_size():
    try:
        return os.path.getsize(_active_log_path())
    except OSError:
        return 0


def _log_since(offset):
    try:
        with open(_active_log_path(), "rb") as fh:
            fh.seek(offset)
            return fh.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return []


def _actor_record(actor):
    loc = actor.get_actor_location()
    rot = actor.get_actor_rotation()
    return {
        "label": actor.get_actor_label(),
        "class": actor.get_class().get_path_name(),
        "path": actor.get_path_name(),
        "location": {"x": loc.x, "y": loc.y, "z": loc.z},
        "rotation": {"pitch": rot.pitch, "yaw": rot.yaw, "roll": rot.roll},
    }


def _load_class(class_path):
    if "." not in class_path and "/" not in class_path:
        cls = getattr(unreal, class_path, None)
        if cls is not None:
            # Python wrapper types must be converted to the reflected UClass.
            return cls.static_class() if hasattr(cls, "static_class") else cls
        class_path = "/Script/Engine." + class_path
    cls = unreal.load_class(None, class_path)
    if cls is None:
        bp = unreal.EditorAssetLibrary.load_blueprint_class(class_path)
        cls = bp
    return cls


# ── Read-back operations ────────────────────────────────────────────────────

@op("handshake")
def handshake(args):
    return _envelope("handshake", True, {
        "library_version": LIBRARY_VERSION,
        "engine_version": unreal.SystemLibrary.get_engine_version(),
        "project_file": unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path()),
        "project_name": unreal.SystemLibrary.get_game_name(),
        "operations": sorted(_OPS.keys()),
        "features": feature_detect(),
    })


def feature_detect():
    probes = {
        "EditorActorSubsystem": hasattr(unreal, "EditorActorSubsystem"),
        "LevelEditorSubsystem": hasattr(unreal, "LevelEditorSubsystem"),
        "MaterialEditingLibrary": hasattr(unreal, "MaterialEditingLibrary"),
        "BlueprintEditorLibrary": hasattr(unreal, "BlueprintEditorLibrary"),
        "InterchangeManager": hasattr(unreal, "InterchangeManager"),
        "AssetImportTask": hasattr(unreal, "AssetImportTask"),
        "MovieSceneSequence": hasattr(unreal, "LevelSequence"),
        "NiagaraSystem": hasattr(unreal, "NiagaraSystem"),
        "PCGGraph": hasattr(unreal, "PCGGraph"),
        "ControlRigBlueprint": hasattr(unreal, "ControlRigBlueprint"),
        "MetaSoundBuilderSubsystem": hasattr(unreal, "MetaSoundBuilderSubsystem"),
        "WidgetBlueprint": hasattr(unreal, "WidgetBlueprint"),
        "GeometryScript": hasattr(unreal, "GeometryScript_Primitives") or hasattr(unreal, "GeometryScriptLibrary_MeshPrimitiveFunctions"),
    }
    return probes


@op("asset_exists")
def asset_exists(args):
    path = args["asset_path"]
    exists = unreal.EditorAssetLibrary.does_asset_exist(path)
    data = {"asset_path": path, "exists": bool(exists)}
    if exists:
        asset = unreal.EditorAssetLibrary.load_asset(path)
        data["class"] = asset.get_class().get_name() if asset else None
        want = args.get("asset_class")
        data["class_match"] = (want is None) or (data["class"] == want)
    return _envelope("asset_exists", True, data)


@op("list_assets")
def list_assets(args):
    directory = args.get("directory", "/Game")
    recursive = bool(args.get("recursive", True))
    limit = int(args.get("limit", 500))
    paths = unreal.EditorAssetLibrary.list_assets(directory, recursive, False)
    paths = [str(p) for p in paths]
    return _envelope("list_assets", True, {"directory": directory, "count": len(paths),
                                           "assets": paths[:limit], "truncated": len(paths) > limit})


@op("asset_dependencies")
def asset_dependencies(args):
    path = args["asset_path"]
    reg = unreal.AssetRegistryHelpers.get_asset_registry()
    package = path.split(".")[0]
    opts = unreal.AssetRegistryDependencyOptions()
    deps = reg.get_dependencies(package, opts) or []
    return _envelope("asset_dependencies", True, {"asset_path": path, "dependencies": [str(d) for d in deps]})


@op("actors_in_level")
def actors_in_level(args):
    limit = int(args.get("limit", 1000))
    actors = _actor_sub().get_all_level_actors()
    world = unreal.EditorLevelLibrary.get_editor_world() if hasattr(unreal, "EditorLevelLibrary") else None
    recs = [_actor_record(a) for a in actors[:limit]]
    return _envelope("actors_in_level", True, {
        "level": world.get_path_name() if world else None,
        "count": len(actors), "actors": recs, "truncated": len(actors) > limit,
    })


@op("log_tail")
def log_tail(args):
    max_lines = int(args.get("max_lines", 100))
    path = args.get("log_path") or _active_log_path()
    lines = []
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()[-max_lines:]
    return _envelope("log_tail", True, {"log_path": path, "lines": [l.rstrip("\n") for l in lines]})


# ── Mutation operations ─────────────────────────────────────────────────────

@op("spawn_actor", mutates=True, reversibility="transactional")
def spawn_actor(args):
    cls = _load_class(args.get("actor_class", "StaticMeshActor"))
    if cls is None:
        return _envelope("spawn_actor", False, errors=["actor class not found: %s" % args.get("actor_class")])
    label = args.get("label")
    with unreal.ScopedEditorTransaction("GameForge spawn_actor"):
        actor = _actor_sub().spawn_actor_from_class(cls, _vec(args.get("location")), _rot(args.get("rotation")))
        if actor is None:
            return _envelope("spawn_actor", False, errors=["spawn_actor_from_class returned None"])
        if label:
            actor.set_actor_label(label)
        mesh_path = args.get("static_mesh")
        if mesh_path and isinstance(actor, unreal.StaticMeshActor):
            mesh = unreal.EditorAssetLibrary.load_asset(mesh_path)
            if mesh:
                actor.static_mesh_component.set_editor_property("static_mesh", mesh)
        scale = args.get("scale")
        if scale:
            actor.set_actor_scale3d(_vec(scale, (1, 1, 1)))
        mobility = args.get("mobility")
        if mobility and actor.root_component:
            actor.root_component.set_mobility(getattr(unreal.ComponentMobility, mobility.upper()))
        if "light_intensity" in args and hasattr(actor, "light_component") and actor.light_component:
            actor.light_component.set_intensity(float(args["light_intensity"]))
        material = args.get("material")
        if material and isinstance(actor, unreal.StaticMeshActor):
            mat = unreal.EditorAssetLibrary.load_asset(material)
            if mat:
                actor.static_mesh_component.set_material(0, mat)
    readback = _find_actor(actor.get_actor_label())
    if readback is None:
        return _envelope("spawn_actor", False, errors=["read-back failed: actor not found after spawn"])
    return _envelope("spawn_actor", True, _actor_record(readback), reversibility="transactional")


@op("delete_actor", mutates=True, reversibility="transactional")
def delete_actor(args):
    actor = _find_actor(args["label"])
    if actor is None:
        return _envelope("delete_actor", False, errors=["actor not found: %s" % args["label"]])
    with unreal.ScopedEditorTransaction("GameForge delete_actor"):
        _actor_sub().destroy_actor(actor)
    gone = _find_actor(args["label"]) is None
    return _envelope("delete_actor", gone, {"label": args["label"], "deleted": gone},
                     errors=[] if gone else ["read-back: actor still present"], reversibility="transactional")


@op("set_actor_property", mutates=True, reversibility="transactional")
def set_actor_property(args):
    actor = _find_actor(args["label"])
    if actor is None:
        return _envelope("set_actor_property", False, errors=["actor not found: %s" % args["label"]])
    name, value = args["property"], args["value"]
    if args.get("asset"):
        # Object reference properties (e.g. a NiagaraSystem) take the loaded asset, not its path string.
        value = unreal.EditorAssetLibrary.load_asset(value)
        if value is None:
            return _envelope("set_actor_property", False, errors=["asset not found: %s" % args["value"]])
    elif isinstance(value, list):
        value = [_vec(v) if isinstance(v, dict) and set(v) == {"x", "y", "z"} else v for v in value]
    elif isinstance(value, dict) and set(value) == {"x", "y", "z"}:
        value = _vec(value)
    with unreal.ScopedEditorTransaction("GameForge set_actor_property"):
        actor.set_editor_property(name, value)
    actual = actor.get_editor_property(name)
    return _envelope("set_actor_property", True, {"label": args["label"], "property": name, "value": str(actual)},
                     reversibility="transactional")


def _exposure_record(vol):
    st = vol.get_editor_property("settings")
    return {"label": vol.get_actor_label(), "unbound": bool(vol.get_editor_property("unbound")),
            "method": _enum_name(st.get_editor_property("auto_exposure_method")),
            "bias": round(st.get_editor_property("auto_exposure_bias"), 3),
            "override_method": bool(st.get_editor_property("override_auto_exposure_method")),
            "override_bias": bool(st.get_editor_property("override_auto_exposure_bias"))}


@op("scene_set_manual_exposure", mutates=True, reversibility="transactional")
def scene_set_manual_exposure(args):
    """Unbound PostProcessVolume with manual exposure, so captures do not depend on eye adaptation."""
    label = args.get("label", "GF_Exposure")
    with unreal.ScopedEditorTransaction("GameForge scene_set_manual_exposure"):
        vol = _find_actor(label)
        if vol is None:
            vol = _actor_sub().spawn_actor_from_class(unreal.PostProcessVolume, unreal.Vector(0, 0, 0))
            vol.set_actor_label(label)
        vol.set_editor_property("unbound", True)
        st = vol.get_editor_property("settings")
        st.set_editor_property("override_auto_exposure_method", True)
        st.set_editor_property("auto_exposure_method", unreal.AutoExposureMethod.AEM_MANUAL)
        st.set_editor_property("override_auto_exposure_bias", True)
        st.set_editor_property("auto_exposure_bias", float(args.get("exposure_bias", 10.0)))
        vol.set_editor_property("settings", st)
    rec = _exposure_record(vol)
    ok = rec["method"] == "AEM_MANUAL" and rec["unbound"]
    return _envelope("scene_set_manual_exposure", ok, rec, reversibility="transactional",
                     errors=[] if ok else ["read-back does not show manual exposure"])


@op("scene_get_exposure", reversibility="read-only")
def scene_get_exposure(args):
    vol = _find_actor(args.get("label", "GF_Exposure"))
    if not isinstance(vol, unreal.PostProcessVolume):
        return _envelope("scene_get_exposure", False, errors=["no PostProcessVolume with that label"])
    return _envelope("scene_get_exposure", True, _exposure_record(vol))


@op("new_level", mutates=True, reversibility="snapshot-only")
def new_level(args):
    path = args["level_path"]
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        if args.get("if_exists", "load") != "load":
            return _envelope("new_level", False, {"level_path": path, "exists": True},
                             errors=["level already exists: " + path])
        ok = _level_sub().load_level(path)
        return _envelope("new_level", bool(ok), {"level_path": path, "exists": True, "loaded_existing": True},
                         warnings=["level existed; loaded instead of created"], affected=[path],
                         reversibility="snapshot-only", errors=[] if ok else ["load_level failed"])
    partitioned = bool(args.get("partitioned", False))
    ok = _level_sub().new_level(path, partitioned) if partitioned else _level_sub().new_level(path)
    exists = unreal.EditorAssetLibrary.does_asset_exist(path)
    is_partitioned = _world_is_partitioned()
    if partitioned and not is_partitioned:
        ok = False
    return _envelope("new_level", bool(ok) and exists, {"level_path": path, "exists": exists, "partitioned": is_partitioned},
                     affected=[path], reversibility="snapshot-only",
                     errors=[] if (ok and exists) else ["new_level failed or level not on disk"])


@op("load_level", mutates=False)
def load_level(args):
    ok = _level_sub().load_level(args["level_path"])
    return _envelope("load_level", bool(ok), {"level_path": args["level_path"]})


@op("save_all", mutates=True, reversibility="snapshot-only")
def save_all(args):
    world = unreal.EditorLevelLibrary.get_editor_world()
    world_path = world.get_path_name() if world else ""
    errors = []
    if world_path.startswith("/Temp/"):
        level_ok = False
        errors.append("current level is untitled (%s); create it with new_level first" % world_path)
    else:
        level_ok = _level_sub().save_current_level()
    assets_ok = unreal.EditorAssetLibrary.save_directory(args.get("directory", "/Game"), True, True)
    return _envelope("save_all", bool(level_ok) and bool(assets_ok),
                     {"level": world_path, "level_saved": bool(level_ok), "assets_saved": bool(assets_ok)},
                     errors=errors, reversibility="snapshot-only")


@op("create_material", mutates=True, reversibility="snapshot-only")
def create_material(args):
    path = args["asset_path"]
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        return _envelope("create_material", False, {"asset_path": path, "exists": True},
                         errors=["asset already exists: " + path + " (delete_asset first)"])
    package_path, name = path.rsplit("/", 1)
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    mat = tools.create_asset(name, package_path, unreal.Material, unreal.MaterialFactoryNew())
    if mat is None:
        return _envelope("create_material", False, errors=["create_asset returned None"])
    mel = unreal.MaterialEditingLibrary
    color = args.get("base_color")
    if color:
        node = mel.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector, -400, 0)
        node.set_editor_property("constant", unreal.LinearColor(color[0], color[1], color[2], 1.0))
        mel.connect_material_property(node, "", unreal.MaterialProperty.MP_BASE_COLOR)
    for prop_name, mprop in (("roughness", unreal.MaterialProperty.MP_ROUGHNESS),
                             ("metallic", unreal.MaterialProperty.MP_METALLIC)):
        if prop_name in args:
            node = mel.create_material_expression(mat, unreal.MaterialExpressionConstant, -400, 200)
            node.set_editor_property("r", float(args[prop_name]))
            mel.connect_material_property(node, "", mprop)
    if args.get("emissive"):
        e = args["emissive"]
        node = mel.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector, -400, 400)
        node.set_editor_property("constant", unreal.LinearColor(e[0], e[1], e[2], 1.0))
        mel.connect_material_property(node, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(mat)
    unreal.EditorAssetLibrary.save_loaded_asset(mat)
    exists = unreal.EditorAssetLibrary.does_asset_exist(path)
    return _envelope("create_material", exists, {"asset_path": path, "exists": exists,
                                                 "expressions": mel.get_num_material_expressions(mat)},
                     affected=[path], reversibility="snapshot-only")


@op("create_blueprint", mutates=True, reversibility="snapshot-only")
def create_blueprint(args):
    path = args["asset_path"]
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        return _envelope("create_blueprint", False, {"asset_path": path, "exists": True},
                         errors=["asset already exists: " + path + " (delete_asset first)"])
    package_path, name = path.rsplit("/", 1)
    parent = _load_class(args.get("parent_class", "Actor"))
    if parent is None:
        return _envelope("create_blueprint", False, errors=["parent class not found"])
    factory = unreal.BlueprintFactory()
    factory.set_editor_property("parent_class", parent)
    bp = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, package_path, unreal.Blueprint, factory)
    if bp is None:
        return _envelope("create_blueprint", False, errors=["create_asset returned None"])
    unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    unreal.EditorAssetLibrary.save_loaded_asset(bp)
    exists = unreal.EditorAssetLibrary.does_asset_exist(path)
    return _envelope("create_blueprint", exists, {"asset_path": path, "parent_class": parent.get_name(), "exists": exists},
                     affected=[path], reversibility="snapshot-only")


@op("compile_blueprint", mutates=True, reversibility="transactional")
def compile_blueprint(args):
    bp = unreal.EditorAssetLibrary.load_asset(args["blueprint_path"])
    if bp is None:
        return _envelope("compile_blueprint", False, errors=["blueprint not found"])
    # Blueprint.status is protected from Python on 5.7.4, so verify through the
    # generated class plus compiler errors written to the log during this call.
    offset = _log_size()
    unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    name = args["blueprint_path"].rsplit("/", 1)[-1].split(".")[0]
    diag = [l for l in _log_since(offset)
            if ("LogBlueprint" in l or "Kismet" in l) and ("Error" in l or "Warning" in l) and name in l]
    gen = unreal.EditorAssetLibrary.load_blueprint_class(args["blueprint_path"])
    errs = [l for l in diag if "Error" in l]
    ok = gen is not None and not errs
    return _envelope("compile_blueprint", ok, {"blueprint_path": args["blueprint_path"],
                                               "generated_class": gen.get_path_name() if gen else None,
                                               "diagnostics": diag[-20:]},
                     errors=errs[-5:] + ([] if gen else ["no generated class after compile"]))


@op("import_asset", mutates=True, reversibility="snapshot-only")
def import_asset(args):
    src = args["source_file"]
    if not os.path.isfile(src):
        return _envelope("import_asset", False, errors=["source file not found: " + src])
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", src)
    task.set_editor_property("destination_path", args.get("destination_path", "/Game/Quarantine"))
    task.set_editor_property("automated", True)
    task.set_editor_property("save", True)
    task.set_editor_property("replace_existing", bool(args.get("replace_existing", False)))
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    imported = [str(p) for p in task.get_editor_property("imported_object_paths")]
    verified = [p for p in imported if unreal.EditorAssetLibrary.does_asset_exist(p.split(".")[0])]
    ok = bool(imported) and len(verified) == len(imported)
    return _envelope("import_asset", ok, {"imported": imported, "verified": verified},
                     affected=imported, reversibility="snapshot-only",
                     errors=[] if ok else ["import produced no verifiable assets"])


# ── M11 materials and textures ──────────────────────────────────────────────

_TEXTURE_ROLES = {  # role -> (sRGB, compression setting)
    "color": (True, "TC_DEFAULT"), "normal": (False, "TC_NORMALMAP"), "masks": (False, "TC_MASKS"),
    "grayscale": (False, "TC_GRAYSCALE"), "linear": (False, "TC_DEFAULT"),
}
_SAMPLERS = {"color": "SAMPLERTYPE_COLOR", "normal": "SAMPLERTYPE_NORMAL", "masks": "SAMPLERTYPE_MASKS",
             "grayscale": "SAMPLERTYPE_GRAYSCALE", "linear": "SAMPLERTYPE_LINEAR_COLOR"}


def _enum_name(value):
    name = getattr(value, "name", None)
    return name if isinstance(name, str) else str(value).split(".")[-1].split(":")[0].strip("<> ")


def _texture_record(tex):
    return {"path": tex.get_path_name(), "srgb": bool(tex.get_editor_property("srgb")),
            "compression": _enum_name(tex.get_editor_property("compression_settings")),
            "size": [tex.blueprint_get_size_x(), tex.blueprint_get_size_y()]}


@op("texture_import", mutates=True, reversibility="snapshot-only")
def texture_import(args):
    """Imports an image as a Texture2D and sets sRGB and compression from its channel role."""
    role = args.get("role", "color")
    if role not in _TEXTURE_ROLES:
        return _envelope("texture_import", False, errors=[f"unknown role {role}; use one of {sorted(_TEXTURE_ROLES)}"])
    src = args["source_file"]
    if not os.path.isfile(src):
        return _envelope("texture_import", False, errors=["source file not found: " + src])
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", src)
    task.set_editor_property("destination_path", args.get("destination_path", "/Game/Quarantine/Textures"))
    if args.get("destination_name"):
        task.set_editor_property("destination_name", args["destination_name"])
    task.set_editor_property("automated", True)
    task.set_editor_property("save", False)
    task.set_editor_property("replace_existing", True)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    paths = [str(x) for x in task.get_editor_property("imported_object_paths")]
    tex = unreal.EditorAssetLibrary.load_asset(paths[0]) if paths else None
    if not isinstance(tex, unreal.Texture2D):
        return _envelope("texture_import", False, {"imported": paths}, errors=["import produced no Texture2D"])
    srgb, compression = _TEXTURE_ROLES[role]
    tex.set_editor_property("srgb", srgb)
    tex.set_editor_property("compression_settings", getattr(unreal.TextureCompressionSettings, compression))
    unreal.EditorAssetLibrary.save_loaded_asset(tex)
    rec = _texture_record(tex)
    ok = rec["srgb"] == srgb and rec["compression"] == compression
    return _envelope("texture_import", ok, rec | {"role": role}, affected=[rec["path"]], reversibility="snapshot-only",
                     errors=[] if ok else [f"read-back mismatch: wanted sRGB={srgb} {compression}, got {rec}"])


@op("texture_inspect", reversibility="read-only")
def texture_inspect(args):
    tex = unreal.EditorAssetLibrary.load_asset(args["texture_path"])
    if not isinstance(tex, unreal.Texture2D):
        return _envelope("texture_inspect", False, errors=["not a Texture2D: " + args["texture_path"]])
    return _envelope("texture_inspect", True, _texture_record(tex))


def _expr_props(node, props):
    for key, value in (props or {}).items():
        if key in ("texture", "material_function"):
            value = unreal.EditorAssetLibrary.load_asset(value)
        elif key == "sampler_type":
            value = getattr(unreal.MaterialSamplerType, _SAMPLERS.get(value, value))
        elif key in ("constant", "default_value") and isinstance(value, (list, tuple)):
            value = unreal.LinearColor(*(list(value) + [1.0] * (4 - len(value))))
        elif key == "layers":  # LandscapeLayerBlend: [{"name", "blend": "LB_WEIGHT_BLEND"}]
            inputs = []
            for layer in value:
                entry = unreal.LayerBlendInput()
                entry.set_editor_property("layer_name", layer["name"])
                entry.set_editor_property("blend_type", getattr(unreal.LandscapeLayerBlendType,
                                                                layer.get("blend", "LB_WEIGHT_BLEND")))
                inputs.append(entry)
            value = inputs
        node.set_editor_property(key, value)


@op("material_build_graph", mutates=True, reversibility="snapshot-only")
def material_build_graph(args):
    """Creates a Material from a declarative graph: nodes [{id, class, x, y, props}], edges
    [{from, output, to, input}] and outputs [{from, output, property}] (property like MP_BASE_COLOR)."""
    path = args["asset_path"]
    mel = unreal.MaterialEditingLibrary
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        if not args.get("replace_existing"):
            return _envelope("material_build_graph", False, errors=["asset already exists: " + path])
        unreal.EditorAssetLibrary.delete_asset(path)
    package_path, name = path.rsplit("/", 1)
    mat = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, package_path, unreal.Material,
                                                                  unreal.MaterialFactoryNew())
    if mat is None:
        return _envelope("material_build_graph", False, errors=["create_asset returned None"])
    errors, nodes = [], {}
    for spec in args.get("nodes", []):
        cls = getattr(unreal, spec["class"], None)
        if cls is None:
            errors.append(f"unknown expression class {spec['class']}")
            continue
        node = mel.create_material_expression(mat, cls, int(spec.get("x", -600)), int(spec.get("y", 0)))
        try:
            _expr_props(node, spec.get("props"))
        except Exception as exc:
            errors.append(f"{spec['id']}: {exc}")
        nodes[spec["id"]] = node
    for e in args.get("edges", []):
        if not mel.connect_material_expressions(nodes.get(e["from"]), e.get("output", ""), nodes.get(e["to"]),
                                                e.get("input", "")):
            errors.append(f"edge failed: {e}")
    for o in args.get("outputs", []):
        if not mel.connect_material_property(nodes.get(o["from"]), o.get("output", ""),
                                             getattr(unreal.MaterialProperty, o["property"])):
            errors.append(f"output failed: {o}")
    for flag in args.get("usage_flags", []):  # e.g. MATUSAGE_INSTANCED_STATIC_MESHES
        mel.set_material_usage(mat, getattr(unreal.MaterialUsage, flag))
    mel.recompile_material(mat)
    unreal.EditorAssetLibrary.save_loaded_asset(mat)
    return _envelope("material_build_graph", not errors, {"asset_path": mat.get_path_name(),
                                                          "expressions": mel.get_num_material_expressions(mat)},
                     errors=errors, affected=[path], reversibility="snapshot-only")


_READBACK_PROPERTIES = ("MP_BASE_COLOR", "MP_METALLIC", "MP_SPECULAR", "MP_ROUGHNESS", "MP_NORMAL",
                        "MP_AMBIENT_OCCLUSION", "MP_EMISSIVE_COLOR", "MP_OPACITY", "MP_OPACITY_MASK")


def _expr_summary(node):
    out = {"class": node.get_class().get_name()}
    for key in ("parameter_name", "sampler_type", "texture", "material_function", "input_name", "output_name",
                "default_value", "constant", "r",
                "coordinate_index", "u_tiling", "v_tiling"):
        try:
            value = node.get_editor_property(key)
        except Exception:
            continue
        if isinstance(value, unreal.Object):
            value = value.get_path_name()
        elif isinstance(value, unreal.LinearColor):
            value = [round(value.r, 4), round(value.g, 4), round(value.b, 4), round(value.a, 4)]
        elif isinstance(value, float):
            value = round(value, 4)
        else:
            value = _enum_name(value) if not isinstance(value, (int, str, bool)) else value
        out[key] = value
    return out


@op("material_readback_graph", reversibility="read-only")
def material_readback_graph(args):
    """Walks the graph backwards from every connected material output, using the engine's own links."""
    mat = unreal.EditorAssetLibrary.load_asset(args["material_path"])
    if not isinstance(mat, unreal.Material):
        return _envelope("material_readback_graph", False, errors=["not a Material: " + args["material_path"]])
    mel = unreal.MaterialEditingLibrary
    ids, nodes, edges, outputs = {}, [], [], []

    def visit(node):
        key = node.get_name()
        if key in ids:
            return key
        ids[key] = node
        nodes.append({"name": key, **_expr_summary(node)})
        inputs = mel.get_inputs_for_material_expression(mat, node)
        try:
            names = list(mel.get_input_names_for_material_expression(mat, node))
        except Exception:
            names = [str(i) for i in range(len(inputs))]
        for idx, upstream in enumerate(inputs):
            if upstream:
                edges.append({"from": visit(upstream), "to": key, "input": names[idx] if idx < len(names) else idx})
        return key

    for prop in _READBACK_PROPERTIES:
        node = mel.get_material_property_input_node(mat, getattr(unreal.MaterialProperty, prop))
        if node:
            try:
                out_name = mel.get_material_property_input_node_output_name(mat, getattr(unreal.MaterialProperty, prop))
            except Exception:
                out_name = ""
            outputs.append({"property": prop, "from": visit(node), "output": str(out_name)})
    stats = mel.get_statistics(mat)
    data = {"material": mat.get_path_name(), "expression_count": mel.get_num_material_expressions(mat),
            "nodes": sorted(nodes, key=lambda n: n["name"]), "edges": sorted(edges, key=lambda e: (e["to"], str(e["input"]))),
            "outputs": outputs,
            "used_textures": sorted(t.get_path_name() for t in mel.get_used_textures(mat)),
            "statistics": {"pixel_shader_instructions": stats.num_pixel_shader_instructions,
                           "vertex_shader_instructions": stats.num_vertex_shader_instructions,
                           "samplers": stats.num_samplers}}
    return _envelope("material_readback_graph", True, data)


@op("material_function_build", mutates=True, reversibility="snapshot-only")
def material_function_build(args):
    """Creates a MaterialFunction from nodes/edges (same format as material_build_graph). Use
    MaterialExpressionFunctionInput (props input_name, input_type) and MaterialExpressionFunctionOutput
    (props output_name) as the function's pins; call it from a material with MaterialExpressionMaterialFunctionCall
    (props material_function)."""
    path = args["asset_path"]
    mel = unreal.MaterialEditingLibrary
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        unreal.EditorAssetLibrary.delete_asset(path)
    package_path, name = path.rsplit("/", 1)
    func = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, package_path, unreal.MaterialFunction,
                                                                   unreal.MaterialFunctionFactoryNew())
    if func is None:
        return _envelope("material_function_build", False, errors=["create_asset returned None"])
    if args.get("description"):
        func.set_editor_property("description", args["description"])
    errors, nodes = [], {}
    for spec in args.get("nodes", []):
        cls = getattr(unreal, spec["class"], None)
        if cls is None:
            errors.append(f"unknown expression class {spec['class']}")
            continue
        node = mel.create_material_expression_in_function(func, cls, int(spec.get("x", -600)), int(spec.get("y", 0)))
        try:
            props = dict(spec.get("props") or {})
            if "input_type" in props:
                props["input_type"] = getattr(unreal.FunctionInputType, props["input_type"])
            _expr_props(node, props)
        except Exception as exc:
            errors.append(f"{spec['id']}: {exc}")
        nodes[spec["id"]] = node
    for e in args.get("edges", []):
        if not mel.connect_material_expressions(nodes.get(e["from"]), e.get("output", ""), nodes.get(e["to"]),
                                                e.get("input", "")):
            errors.append(f"edge failed: {e}")
    mel.update_material_function(func, None)
    unreal.EditorAssetLibrary.save_loaded_asset(func)
    count = mel.get_num_material_expressions_in_function(func)
    ok = not errors and count == len(nodes)
    return _envelope("material_function_build", ok, {"asset_path": func.get_path_name(), "expressions": count},
                     errors=errors, affected=[path], reversibility="snapshot-only")


@op("material_function_inspect", reversibility="read-only")
def material_function_inspect(args):
    func = unreal.EditorAssetLibrary.load_asset(args["function_path"])
    if not isinstance(func, unreal.MaterialFunction):
        return _envelope("material_function_inspect", False, errors=["not a MaterialFunction"])
    return _envelope("material_function_inspect", True, {
        "path": func.get_path_name(), "description": str(func.get_editor_property("description")),
        "expressions": unreal.MaterialEditingLibrary.get_num_material_expressions_in_function(func)})


@op("material_instance_create", mutates=True, reversibility="snapshot-only")
def material_instance_create(args):
    """Creates a MaterialInstanceConstant and sets scalar / vector / texture parameter overrides."""
    path = args["asset_path"]
    parent = unreal.EditorAssetLibrary.load_asset(args["parent"])
    if not isinstance(parent, unreal.MaterialInterface):
        return _envelope("material_instance_create", False, errors=["parent is not a material: " + args["parent"]])
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        unreal.EditorAssetLibrary.delete_asset(path)
    package_path, name = path.rsplit("/", 1)
    # The factory's InitialParent is not exposed to Python in 5.7, so the parent is set after creation.
    mi = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, package_path, unreal.MaterialInstanceConstant,
                                                                 unreal.MaterialInstanceConstantFactoryNew())
    if mi is None:
        return _envelope("material_instance_create", False, errors=["create_asset returned None"])
    mel, errors = unreal.MaterialEditingLibrary, []
    mel.set_material_instance_parent(mi, parent)
    # The setters' return values are unreliable across engine versions, so every override is confirmed by
    # reading it back from the instance.
    for key, value in (args.get("scalars") or {}).items():
        mel.set_material_instance_scalar_parameter_value(mi, key, float(value))
        if abs(mel.get_material_instance_scalar_parameter_value(mi, key) - float(value)) > 1e-4:
            errors.append(f"scalar parameter not applied: {key}")
    for key, value in (args.get("vectors") or {}).items():
        color = unreal.LinearColor(*(list(value) + [1.0] * (4 - len(value))))
        mel.set_material_instance_vector_parameter_value(mi, key, color)
        got = mel.get_material_instance_vector_parameter_value(mi, key)
        if max(abs(got.r - color.r), abs(got.g - color.g), abs(got.b - color.b), abs(got.a - color.a)) > 1e-4:
            errors.append(f"vector parameter not applied: {key}")
    for key, value in (args.get("textures") or {}).items():
        tex = unreal.EditorAssetLibrary.load_asset(value)
        mel.set_material_instance_texture_parameter_value(mi, key, tex)
        got = mel.get_material_instance_texture_parameter_value(mi, key)
        if not tex or not got or got.get_path_name() != tex.get_path_name():
            errors.append(f"texture parameter not applied: {key}")
    mel.update_material_instance(mi)
    unreal.EditorAssetLibrary.save_loaded_asset(mi)
    return _envelope("material_instance_create", not errors, {"asset_path": mi.get_path_name()}, errors=errors,
                     affected=[path], reversibility="snapshot-only")


@op("material_instance_inspect", reversibility="read-only")
def material_instance_inspect(args):
    mi = unreal.EditorAssetLibrary.load_asset(args["instance_path"])
    if not isinstance(mi, unreal.MaterialInstanceConstant):
        return _envelope("material_instance_inspect", False, errors=["not a MaterialInstanceConstant"])
    mel = unreal.MaterialEditingLibrary
    vectors = {}
    for key in args.get("vectors", []):
        c = mel.get_material_instance_vector_parameter_value(mi, key)
        vectors[key] = [round(c.r, 4), round(c.g, 4), round(c.b, 4), round(c.a, 4)]
    textures = {}
    for key in args.get("textures", []):
        t = mel.get_material_instance_texture_parameter_value(mi, key)
        textures[key] = t.get_path_name() if t else None
    return _envelope("material_instance_inspect", True, {
        "parent": mi.get_editor_property("parent").get_path_name(),
        "scalars": {k: round(mel.get_material_instance_scalar_parameter_value(mi, k), 4) for k in args.get("scalars", [])},
        "vectors": vectors, "textures": textures})


@op("actor_get_materials", reversibility="read-only")
def actor_get_materials(args):
    actor = _find_actor(args["label"])
    if actor is None:
        return _envelope("actor_get_materials", False, errors=["actor not found: " + args["label"]])
    slots = []
    for comp in actor.get_components_by_class(unreal.MeshComponent):
        for i in range(comp.get_num_materials()):
            m = comp.get_material(i)
            slots.append({"component": comp.get_name(), "slot": i, "material": m.get_path_name() if m else None})
    return _envelope("actor_get_materials", True, {"label": args["label"], "slots": slots})


# ── M12 static-mesh production (Geometry Script) ────────────────────────────

@op("api_introspect", reversibility="read-only")
def api_introspect(args):
    """Lists public attribute names of `unreal` classes (development aid for engine-version API drift)."""
    out = {}
    for name in args.get("classes", []):
        cls = getattr(unreal, name, None)
        out[name] = None if cls is None else sorted(a for a in dir(cls) if not a.startswith("_")
                                                    and args.get("filter", "") in a)
    return _envelope("api_introspect", True, {"classes": out})


def _gs(name):
    lib = getattr(unreal, name, None)
    if lib is None:
        raise RuntimeError(f"unreal.{name} missing (is the GeometryScripting plugin enabled?)")
    return lib


def _gs_transform(part):
    return unreal.Transform(_vec(part.get("location")), _rot(part.get("rotation")), _vec(part.get("scale"), (1, 1, 1)))


def _append_part(mesh, part):
    prim = _gs("GeometryScript_Primitives")
    opts = unreal.GeometryScriptPrimitiveOptions()
    opts.set_editor_property("material_id", int(part.get("material_id", 0)))
    xf = _gs_transform(part)
    shape, size = part["shape"], part.get("size", [100, 100, 100])
    origin = unreal.GeometryScriptPrimitiveOriginMode.BASE
    if shape == "box":
        prim.append_box(mesh, opts, xf, float(size[0]), float(size[1]), float(size[2]),
                        int(part.get("steps", 0)), int(part.get("steps", 0)), int(part.get("steps", 0)), origin)
    elif shape == "cylinder":
        prim.append_cylinder(mesh, opts, xf, float(part.get("radius", 50)), float(part.get("height", 100)),
                             int(part.get("radial_steps", 16)), int(part.get("height_steps", 0)), True, origin)
    elif shape == "sphere":
        prim.append_sphere_lat_long(mesh, opts, xf, float(part.get("radius", 50)),
                                    int(part.get("steps_phi", 12)), int(part.get("steps_theta", 16)),
                                    unreal.GeometryScriptPrimitiveOriginMode.CENTER)
    elif shape == "cone":
        prim.append_cone(mesh, opts, xf, float(part.get("radius", 50)), float(part.get("top_radius", 0)),
                         float(part.get("height", 100)), int(part.get("radial_steps", 16)),
                         int(part.get("height_steps", 0)), True, origin)
    else:
        raise ValueError(f"unknown shape {shape}")


def _triangles(mesh):
    queries = _gs("GeometryScript_MeshQueries")
    # Python binding names mangle the "IDs" suffix (GetNumTriangleIDs -> get_num_triangle_i_ds).
    for name in ("get_num_triangle_i_ds", "get_num_triangle_ids", "get_triangle_count"):
        if hasattr(queries, name):
            return int(getattr(queries, name)(mesh))
    raise RuntimeError("no triangle-count query on GeometryScript_MeshQueries")


@op("mesh_generate_prop", mutates=True, reversibility="snapshot-only")
def mesh_generate_prop(args):
    """Builds a static mesh in-engine from parts [{shape, size|radius/height, location, rotation, material_id,
    op: union|subtract}] with Geometry Script, auto-unwraps UVs, recomputes normals, simplifies to the triangle
    budget and saves it as a new StaticMesh asset."""
    path = args["asset_path"]
    errors, steps = [], []
    try:
        mesh = unreal.DynamicMesh()
        for i, part in enumerate(args.get("parts", [])):
            if part.get("op", "union") == "union":
                _append_part(mesh, part)
            else:
                tool = unreal.DynamicMesh()
                _append_part(tool, part)
                bopts = unreal.GeometryScriptMeshBooleanOptions()
                _gs("GeometryScript_MeshBooleans").apply_mesh_boolean(
                    mesh, unreal.Transform(), tool, unreal.Transform(),
                    unreal.GeometryScriptBooleanOperation.SUBTRACT, bopts)
            steps.append({"part": i, "triangles": _triangles(mesh)})
        uvs = _gs("GeometryScript_UVs")
        if hasattr(uvs, "auto_generate_x_atlas_mesh_u_vs"):
            uvs.auto_generate_x_atlas_mesh_u_vs(mesh, 0, unreal.GeometryScriptXAtlasOptions())
            steps.append({"uv": "xatlas"})
        else:
            uvs.auto_generate_patch_builder_mesh_u_vs(mesh, 0, unreal.GeometryScriptPatchBuilderOptions())
            steps.append({"uv": "patch_builder"})
        _gs("GeometryScript_Normals").compute_split_normals(mesh, unreal.GeometryScriptSplitNormalsOptions(),
                                                            unreal.GeometryScriptCalculateNormalsOptions())
        budget = int(args.get("triangle_budget", 0))
        if budget and _triangles(mesh) > budget:
            _gs("GeometryScript_MeshSimplification").apply_simplify_to_triangle_count(
                mesh, budget, unreal.GeometryScriptSimplifyMeshOptions())
            steps.append({"simplified_to": _triangles(mesh)})
        if unreal.EditorAssetLibrary.does_asset_exist(path):
            unreal.EditorAssetLibrary.delete_asset(path)
        sm_opts = unreal.GeometryScriptCreateNewStaticMeshAssetOptions()
        result = _gs("GeometryScript_NewAssetUtils").create_new_static_mesh_asset_from_mesh(mesh, path, sm_opts)
        static_mesh = result[0] if isinstance(result, (tuple, list)) else result
        if not isinstance(static_mesh, unreal.StaticMesh):
            raise RuntimeError(f"create_new_static_mesh_asset_from_mesh returned {result!r}")
        unreal.EditorAssetLibrary.save_loaded_asset(static_mesh)
        tris = _triangles(mesh)
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
        return _envelope("mesh_generate_prop", False, {"steps": steps}, errors=errors)
    ok = unreal.EditorAssetLibrary.does_asset_exist(path)
    return _envelope("mesh_generate_prop", ok, {"asset_path": static_mesh.get_path_name(), "triangles": tris,
                                                "steps": steps}, affected=[path], reversibility="snapshot-only",
                     errors=[] if ok else ["asset not on disk after save"])


def _sm_sub():
    return unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)


def _lod_triangles_via_geometry_script(sm, lod):
    opts = unreal.GeometryScriptCopyMeshFromAssetOptions()
    req = unreal.GeometryScriptMeshReadLOD()
    req.set_editor_property("lod_index", int(lod))
    res = _gs("GeometryScript_AssetUtils").copy_mesh_from_static_mesh(sm, unreal.DynamicMesh(), opts, req)
    mesh = res[0] if isinstance(res, (tuple, list)) else res
    return _triangles(mesh)


def _lod_triangles(sm, lod):
    for getter in (lambda: sm.get_num_triangles(lod), lambda: _lod_triangles_via_geometry_script(sm, lod)):
        try:
            return int(getter())
        except Exception:
            continue
    return None


def _static_mesh_record(sm):
    sub = _sm_sub()
    lods = sub.get_lod_count(sm)
    bounds = sm.get_bounding_box()
    nanite = None
    try:
        nanite = bool(sm.get_editor_property("nanite_settings").get_editor_property("enabled"))
    except Exception:
        pass
    return {"path": sm.get_path_name(), "lod_count": lods,
            "lod_triangles": [_lod_triangles(sm, i) for i in range(lods)],
            "lod_vertices": [sub.get_number_verts(sm, i) for i in range(lods)],
            "simple_collision_count": sub.get_simple_collision_count(sm),
            "collision_complexity": _enum_name(sm.get_editor_property("body_setup").get_editor_property(
                "collision_trace_flag")) if sm.get_editor_property("body_setup") else None,
            "nanite": nanite,
            "bounds_cm": [round(bounds.max.x - bounds.min.x, 2), round(bounds.max.y - bounds.min.y, 2),
                          round(bounds.max.z - bounds.min.z, 2)],
            "materials": [(m.get_editor_property("material_interface").get_path_name()
                           if m.get_editor_property("material_interface") else None)
                          for m in sm.get_editor_property("static_materials")]}


@op("static_mesh_inspect", reversibility="read-only")
def static_mesh_inspect(args):
    sm = unreal.EditorAssetLibrary.load_asset(args["static_mesh_path"])
    if not isinstance(sm, unreal.StaticMesh):
        return _envelope("static_mesh_inspect", False, errors=["not a StaticMesh: " + args["static_mesh_path"]])
    try:
        return _envelope("static_mesh_inspect", True, _static_mesh_record(sm))
    except Exception as exc:
        return _envelope("static_mesh_inspect", False, errors=[f"{type(exc).__name__}: {exc}"])


_COLLISION_SHAPES = {"box": "BOX", "sphere": "SPHERE", "capsule": "CAPSULE", "convex": "NDOP26"}


@op("static_mesh_configure", mutates=True, reversibility="snapshot-only")
def static_mesh_configure(args):
    """LODs from reduction fractions, simple/complex collision, Nanite flag and material slots; then saves."""
    sm = unreal.EditorAssetLibrary.load_asset(args["static_mesh_path"])
    if not isinstance(sm, unreal.StaticMesh):
        return _envelope("static_mesh_configure", False, errors=["not a StaticMesh: " + args["static_mesh_path"]])
    sub, errors = _sm_sub(), []
    try:
        reduction = args.get("lod_reduction")
        if reduction is not None:
            opts = unreal.StaticMeshReductionOptions()
            settings = []
            for frac in [1.0] + list(reduction):
                s = unreal.StaticMeshReductionSettings()
                s.set_editor_property("percent_triangles", float(frac))
                s.set_editor_property("screen_size", float(frac))
                settings.append(s)
            opts.set_editor_property("reduction_settings", settings)
            sub.set_lods(sm, opts)
        collision = args.get("collision")
        if collision:
            sub.remove_collisions(sm)
            body = sm.get_editor_property("body_setup")
            if collision == "complex_as_simple":
                body.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
            elif collision != "none":
                sub.add_simple_collisions(sm, getattr(unreal.ScriptCollisionShapeType, _COLLISION_SHAPES[collision]))
        if "nanite" in args:
            ns = sm.get_editor_property("nanite_settings")
            ns.set_editor_property("enabled", bool(args["nanite"]))
            sm.set_editor_property("nanite_settings", ns)
        for i, mat_path in enumerate(args.get("materials", [])):
            mat = unreal.EditorAssetLibrary.load_asset(mat_path)
            if mat:
                sm.set_material(i, mat)
            else:
                errors.append(f"material not found: {mat_path}")
        unreal.EditorAssetLibrary.save_loaded_asset(sm)
        rec = _static_mesh_record(sm)
    except Exception as exc:
        return _envelope("static_mesh_configure", False, errors=errors + [f"{type(exc).__name__}: {exc}"])
    return _envelope("static_mesh_configure", not errors, rec, errors=errors, affected=[rec["path"]],
                     reversibility="snapshot-only")


# ── M13 Niagara VFX ─────────────────────────────────────────────────────────

_NIAGARA_TEMPLATES = "/Niagara/DefaultAssets/Templates"


@op("vfx_create_system", mutates=True, reversibility="snapshot-only")
def vfx_create_system(args):
    """Creates a NiagaraSystem asset either by duplicating an engine template system ("template_system", e.g.
    "SimpleExplosion") or from engine template emitters ("template_emitters", e.g. ["Fountain"])."""
    path = args["asset_path"]
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        unreal.EditorAssetLibrary.delete_asset(path)
    package_path, name = path.rsplit("/", 1)
    errors = []
    if args.get("template_system"):
        src = f"{_NIAGARA_TEMPLATES}/Systems/{args['template_system']}"
        system = unreal.EditorAssetLibrary.duplicate_asset(src, path)
    else:
        emitters = []
        for e in args.get("template_emitters", []):
            emitter = unreal.EditorAssetLibrary.load_asset(f"{_NIAGARA_TEMPLATES}/Emitters/{e}")
            if emitter is None:
                errors.append(f"template emitter not found: {e}")
            else:
                emitters.append(emitter)
        factory = unreal.NiagaraSystemFactoryNew()
        try:
            factory.set_editor_property("emitters_to_add_to_new_system", emitters)
        except Exception as exc:
            errors.append(f"factory does not take emitters in Python: {exc}")
        system = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, package_path, unreal.NiagaraSystem, factory)
    if not isinstance(system, unreal.NiagaraSystem):
        return _envelope("vfx_create_system", False, errors=errors + ["no NiagaraSystem created"])
    unreal.EditorAssetLibrary.save_loaded_asset(system)
    return _envelope("vfx_create_system", not errors, {"asset_path": system.get_path_name()}, errors=errors,
                     affected=[path], reversibility="snapshot-only")


@op("vfx_inspect_system", reversibility="read-only")
def vfx_inspect_system(args):
    system = unreal.EditorAssetLibrary.load_asset(args["system_path"])
    if not isinstance(system, unreal.NiagaraSystem):
        return _envelope("vfx_inspect_system", False, errors=["not a NiagaraSystem: " + args["system_path"]])
    data = {"path": system.get_path_name()}
    for key in ("warmup_time", "fixed_bounds"):
        try:
            value = system.get_editor_property(key)
            data[key] = value if isinstance(value, (int, float, bool, str)) else str(value)
        except Exception:
            pass
    return _envelope("vfx_inspect_system", True, data)


def _vfx_lib():
    if not hasattr(unreal, "GameForgeVFXLibrary"):
        raise RuntimeError("GameForgeVFXLibrary not loaded (rebuild/install the plugin)")
    return unreal.GameForgeVFXLibrary


@op("vfx_spawn", mutates=True, reversibility="transient")
def vfx_spawn(args):
    """Spawns a Niagara system in the editor or PIE world (world: "editor" | "pie"); read back with
    vfx_particle_counts."""
    try:
        res = json.loads(_vfx_lib().spawn_system(json.dumps(args)))
    except RuntimeError as exc:
        return _envelope("vfx_spawn", False, errors=[str(exc)])
    return _envelope("vfx_spawn", res.get("success", False), res.get("data", {}), errors=res.get("errors", []),
                     reversibility="transient")


@op("vfx_particle_counts", reversibility="read-only")
def vfx_particle_counts(args):
    try:
        res = json.loads(_vfx_lib().inspect_particles(json.dumps(args)))
    except RuntimeError as exc:
        return _envelope("vfx_particle_counts", False, errors=[str(exc)])
    return _envelope("vfx_particle_counts", res.get("success", False), res.get("data", {}), errors=res.get("errors", []))


# ── M14 audio ───────────────────────────────────────────────────────────────

def _sound_record(sound):
    rec = {"path": sound.get_path_name(), "class": sound.get_class().get_name()}
    for key in ("duration", "num_channels", "looping", "volume", "pitch"):
        try:
            value = sound.get_editor_property(key)
            rec[key] = round(value, 4) if isinstance(value, float) else value
        except Exception:
            pass
    try:
        rec["sample_rate"] = sound.get_sample_rate_for_current_platform()
    except Exception:
        pass
    att = sound.get_editor_property("attenuation_settings")
    rec["attenuation"] = att.get_path_name() if att else None
    return rec


@op("audio_import", mutates=True, reversibility="snapshot-only")
def audio_import(args):
    """Imports a WAV as USoundWave; optional looping flag and attenuation asset. Read back with audio_inspect."""
    src = args["source_file"]
    if not os.path.isfile(src):
        return _envelope("audio_import", False, errors=["source file not found: " + src])
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", src)
    task.set_editor_property("destination_path", args.get("destination_path", "/Game/Quarantine/Audio"))
    if args.get("destination_name"):
        task.set_editor_property("destination_name", args["destination_name"])
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", False)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    paths = [str(x) for x in task.get_editor_property("imported_object_paths")]
    sound = unreal.EditorAssetLibrary.load_asset(paths[0]) if paths else None
    if not isinstance(sound, unreal.SoundWave):
        return _envelope("audio_import", False, {"imported": paths}, errors=["import produced no SoundWave"])
    if "looping" in args:
        sound.set_editor_property("looping", bool(args["looping"]))
    if args.get("attenuation_path"):
        sound.set_editor_property("attenuation_settings", unreal.EditorAssetLibrary.load_asset(args["attenuation_path"]))
    unreal.EditorAssetLibrary.save_loaded_asset(sound)
    return _envelope("audio_import", True, _sound_record(sound), affected=[sound.get_path_name()],
                     reversibility="snapshot-only")


@op("audio_inspect", reversibility="read-only")
def audio_inspect(args):
    sound = unreal.EditorAssetLibrary.load_asset(args["sound_path"])
    if not isinstance(sound, unreal.SoundBase):
        return _envelope("audio_inspect", False, errors=["not a sound: " + args["sound_path"]])
    return _envelope("audio_inspect", True, _sound_record(sound))


def _attenuation_record(att):
    st = att.get_editor_property("attenuation")
    ext = st.get_editor_property("attenuation_shape_extents")
    return {"path": att.get_path_name(), "spatialize": bool(st.get_editor_property("spatialize")),
            "attenuate": bool(st.get_editor_property("attenuate")),
            "inner_radius": round(ext.x, 2), "falloff_distance": round(st.get_editor_property("falloff_distance"), 2),
            "function": _enum_name(st.get_editor_property("distance_algorithm"))}


@op("audio_create_attenuation", mutates=True, reversibility="snapshot-only")
def audio_create_attenuation(args):
    path = args["asset_path"]
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        unreal.EditorAssetLibrary.delete_asset(path)
    package_path, name = path.rsplit("/", 1)
    att = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, package_path, unreal.SoundAttenuation,
                                                                  unreal.SoundAttenuationFactory())
    if att is None:
        return _envelope("audio_create_attenuation", False, errors=["create_asset returned None"])
    st = att.get_editor_property("attenuation")
    st.set_editor_property("attenuate", True)
    st.set_editor_property("spatialize", True)
    st.set_editor_property("attenuation_shape_extents", unreal.Vector(float(args.get("inner_radius", 200.0)), 0, 0))
    st.set_editor_property("falloff_distance", float(args.get("falloff_distance", 2000.0)))
    st.set_editor_property("distance_algorithm", getattr(unreal.AttenuationDistanceModel,
                                                         args.get("function", "LINEAR")))
    att.set_editor_property("attenuation", st)
    unreal.EditorAssetLibrary.save_loaded_asset(att)
    return _envelope("audio_create_attenuation", True, _attenuation_record(att), affected=[path],
                     reversibility="snapshot-only")


@op("audio_inspect_attenuation", reversibility="read-only")
def audio_inspect_attenuation(args):
    att = unreal.EditorAssetLibrary.load_asset(args["attenuation_path"])
    if not isinstance(att, unreal.SoundAttenuation):
        return _envelope("audio_inspect_attenuation", False, errors=["not a SoundAttenuation"])
    return _envelope("audio_inspect_attenuation", True, _attenuation_record(att))


_AUDIO_COMPONENTS = {}


def _pie_world():
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world()


def _load_asset_pie_safe(path):
    """EditorAssetLibrary.load_asset returns None while PIE runs ("The Editor is currently in a play mode");
    unreal.load_asset works in both modes. Use this in any op that can run during PIE."""
    obj = unreal.load_asset(path)
    if obj is None and "." not in path.rsplit("/", 1)[-1]:
        obj = unreal.load_asset(f"{path}.{path.rsplit('/', 1)[-1]}")
    return obj


@op("audio_play_at", mutates=True, reversibility="transient")
def audio_play_at(args):
    """Plays a sound at a location in the running PIE world (GameplayStatics.spawn_sound_at_location)."""
    world = _pie_world()
    if world is None:
        return _envelope("audio_play_at", False, errors=["PIE is not running"])
    sound = _load_asset_pie_safe(args["sound_path"])
    if not isinstance(sound, unreal.SoundBase):
        return _envelope("audio_play_at", False, errors=["not a sound: " + args["sound_path"]])
    label = args.get("label", "GF_Sound")
    comp = unreal.GameplayStatics.spawn_sound_at_location(world, sound, _vec(args.get("location")))
    if comp is None:
        return _envelope("audio_play_at", False,
                         errors=["spawn_sound_at_location returned None (sound disabled, or a short one-shot culled as inaudible)"])
    _AUDIO_COMPONENTS[label] = comp
    unreal.log(f"GF_EVENT audio_play {label} {sound.get_path_name()}")
    return _envelope("audio_play_at", True, {"label": label, "playing": comp.is_playing()},
                     reversibility="transient")


def _state_value(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple, unreal.Array)):
        return [_state_value(v) for v in value]
    if isinstance(value, unreal.Vector):
        return [round(value.x, 1), round(value.y, 1), round(value.z, 1)]
    if isinstance(value, unreal.AudioComponent):
        return {"component": value.get_name(), "playing": bool(value.is_playing()),
                "sound": value.sound.get_path_name() if value.sound else None}
    if isinstance(value, unreal.ActorComponent):
        return {"component": value.get_name(), "active": bool(value.is_active())}
    if isinstance(value, unreal.Object):
        return value.get_path_name()
    return str(value)


@op("gameplay_objectives", reversibility="read-only")
def gameplay_objectives(args):
    """Objective/quest state of the running PIE game (GameForgeObjectiveSubsystem on the game instance)."""
    world = _pie_world()
    if world is None:
        return _envelope("gameplay_objectives", False, errors=["PIE is not running"])
    sub = unreal.GameForgeObjectiveSubsystem.get_for_world(world)
    if sub is None:
        return _envelope("gameplay_objectives", False, errors=["GameForgeObjectiveSubsystem not found (plugin build older than m15b?)"])
    return _envelope("gameplay_objectives", True, json.loads(sub.get_objectives_json()))


@op("pie_actor_state", reversibility="read-only")
def pie_actor_state(args):
    """Reads properties of every live PIE actor of a class (e.g. a kit pickup's bCollected / SpawnedSound)."""
    world = _pie_world()
    if world is None:
        return _envelope("pie_actor_state", False, errors=["PIE is not running"])
    cls = _load_class(args["actor_class"])
    if cls is None:
        return _envelope("pie_actor_state", False, errors=["actor class not found: " + args["actor_class"]])
    actors = []
    for actor in unreal.GameplayStatics.get_all_actors_of_class(world, cls):
        rec = {"name": actor.get_name()}
        for prop in args.get("properties", []):
            try:
                rec[prop] = _state_value(actor.get_editor_property(prop))
            except Exception as exc:
                rec[prop] = {"error": f"{type(exc).__name__}: {exc}"}
        actors.append(rec)
    return _envelope("pie_actor_state", True, {"world": world.get_name(), "actors": actors})


# ── M14 MetaSound authoring (MetaSoundBuilderSubsystem + MetaSoundEditorSubsystem) ──────────────────────

def _ms_ok(result):
    return result is not None and _enum_name(result).upper().endswith("SUCCEEDED")


def _ms_class(spec):
    ns, name, variant = (list(spec) + ["", "", ""])[:3]
    cls = unreal.MetasoundFrontendClassName()
    cls.set_editor_property("namespace", ns)
    cls.set_editor_property("name", name)
    cls.set_editor_property("variant", variant)
    return cls


def _ms_graph_spec_check(builder, nodes, spec):
    """Read-back on any builder: every declared node exists, every declared edge/default input is connected."""
    out = {"nodes": {}, "edges": [], "on_play": [], "on_finished": None}
    for node_id, handle in nodes.items():
        out["nodes"][node_id] = bool(builder.contains_node(handle))
    for edge in spec.get("edges", []):
        (dst, dst_in) = edge["to"]
        handle, res = builder.find_node_input_by_name(nodes[dst], dst_in)
        out["edges"].append({"to": edge["to"], "connected": _ms_ok(res) and bool(builder.node_input_is_connected(handle))})
    for dst, dst_in in spec.get("on_play", []):
        handle, res = builder.find_node_input_by_name(nodes[dst], dst_in)
        out["on_play"].append({"to": [dst, dst_in], "connected": _ms_ok(res) and bool(builder.node_input_is_connected(handle))})
    return out


@op("metasound_build_source", mutates=True, reversibility="snapshot-only")
def metasound_build_source(args):
    """Builds a MetaSound Source asset from a node graph spec:
    nodes [{id, class: [namespace, name, variant], defaults: {input: float}}], edges [{from: [id, output],
    to: [id, input]}], on_play [[id, input]] (fed by the source's OnPlay trigger), on_finished [id, output]
    (drives the source's OnFinished), audio_out [id, output] (to the mono output), one_shot."""
    path = args["asset_path"]
    package_path, name = path.rsplit("/", 1)
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        unreal.EditorAssetLibrary.delete_asset(path)
    sub = unreal.get_engine_subsystem(unreal.MetaSoundBuilderSubsystem)
    steps, errors, nodes = [], [], {}
    builder, on_play, on_finished, audio_outs, res = sub.create_source_builder(
        name, output_format=unreal.MetaSoundOutputAudioFormat.MONO, is_one_shot=bool(args.get("one_shot", True)))
    if not _ms_ok(res):
        return _envelope("metasound_build_source", False, errors=[f"create_source_builder: {_enum_name(res)}"])
    for spec in args.get("nodes", []):
        handle, res = builder.add_node_by_class_name(_ms_class(spec["class"]))
        steps.append({"add_node": spec["id"], "result": _enum_name(res)})
        if not _ms_ok(res):
            errors.append(f"add node {spec['id']} {spec['class']}: {_enum_name(res)}")
            continue
        nodes[spec["id"]] = handle
        for input_name, value in (spec.get("defaults") or {}).items():
            in_handle, r1 = builder.find_node_input_by_name(handle, input_name)
            literal, _type = sub.create_float_meta_sound_literal(float(value))
            r2 = builder.set_node_input_default(in_handle, literal) if _ms_ok(r1) else r1
            if not (_ms_ok(r1) and _ms_ok(r2)):
                errors.append(f"default {spec['id']}.{input_name}: {_enum_name(r1)}/{_enum_name(r2)}")

    def connect(src, src_out_handle, dst, dst_in):
        if dst not in nodes:
            errors.append(f"connect to unknown node {dst}")
            return
        in_handle, r1 = builder.find_node_input_by_name(nodes[dst], dst_in)
        r2 = builder.connect_nodes(src_out_handle, in_handle) if _ms_ok(r1) else r1
        steps.append({"connect": [src, dst, dst_in], "result": _enum_name(r2)})
        if not (_ms_ok(r1) and _ms_ok(r2)):
            errors.append(f"connect {src} -> {dst}.{dst_in}: {_enum_name(r1)}/{_enum_name(r2)}")

    for edge in args.get("edges", []):
        (src, src_out), (dst, dst_in) = edge["from"], edge["to"]
        if src not in nodes:
            errors.append(f"edge from unknown node {src}")
            continue
        out_handle, r = builder.find_node_output_by_name(nodes[src], src_out)
        if not _ms_ok(r):
            errors.append(f"output {src}.{src_out}: {_enum_name(r)}")
            continue
        connect(src, out_handle, dst, dst_in)
    for dst, dst_in in args.get("on_play", []):
        connect("OnPlay", on_play, dst, dst_in)
    for key, target in (("on_finished", on_finished), ("audio_out", audio_outs[0] if audio_outs else None)):
        if args.get(key) and target is not None:
            src, src_out = args[key]
            out_handle, r = builder.find_node_output_by_name(nodes.get(src), src_out) if src in nodes else (None, None)
            r2 = builder.connect_nodes(out_handle, target) if _ms_ok(r) else r
            steps.append({key: [src, src_out], "result": _enum_name(r2)})
            if not _ms_ok(r2):
                errors.append(f"{key} {src}.{src_out}: {_enum_name(r)}/{_enum_name(r2)}")
    asset, res = unreal.get_editor_subsystem(unreal.MetaSoundEditorSubsystem).build_to_asset(
        builder, "GameForge", name, package_path)
    if not _ms_ok(res):
        errors.append(f"build_to_asset: {_enum_name(res)}")
    unreal.EditorAssetLibrary.save_asset(path)
    _MS_NODE_HANDLES[path] = nodes
    return _envelope("metasound_build_source", not errors,
                     {"asset_path": path, "nodes": list(nodes), "steps": steps}, errors=errors, affected=[path],
                     reversibility="snapshot-only")


_MS_NODE_HANDLES = {}


@op("metasound_inspect", reversibility="read-only")
def metasound_inspect(args):
    """Re-opens a built MetaSound asset with a fresh builder and checks the declared graph (nodes, edges, OnPlay
    inputs) against what the saved document holds. Needs the same spec that built it."""
    path = args["asset_path"]
    asset = unreal.EditorAssetLibrary.load_asset(path)
    if asset is None:
        return _envelope("metasound_inspect", False, errors=["asset not found: " + path])
    builder, res = unreal.get_editor_subsystem(unreal.MetaSoundEditorSubsystem).find_or_begin_building(asset)
    if not _ms_ok(res):
        return _envelope("metasound_inspect", False, errors=[f"find_or_begin_building: {_enum_name(res)}"])
    nodes = _MS_NODE_HANDLES.get(path, {})
    rec = _ms_graph_spec_check(builder, nodes, args.get("spec", {}))
    rec |= {"asset_class": asset.get_class().get_name(), "duration": round(asset.get_editor_property("duration"), 3)
            if hasattr(asset, "get_editor_property") else None}
    ok = bool(nodes) and all(rec["nodes"].values()) and all(e["connected"] for e in rec["edges"] + rec["on_play"])
    return _envelope("metasound_inspect", ok, rec, errors=[] if ok else ["graph read-back mismatch"])


@op("audio_diagnose_spawn", mutates=True, reversibility="transient")
def audio_diagnose_spawn(args):
    """Diagnostic only: tries GameplayStatics sound-spawn variants in PIE with different context objects and
    reports which return a component (spawned sounds are stopped again). Never acceptance evidence."""
    world = _pie_world()
    if world is None:
        return _envelope("audio_diagnose_spawn", False, errors=["PIE is not running"])
    sound = _load_asset_pie_safe(args["sound_path"])
    loc = _vec(args.get("location"))
    gs = unreal.GameplayStatics
    pawn = gs.get_player_pawn(world, 0)
    rec = {"world": world.get_name(), "sound": sound.get_path_name() if sound else None,
           "pawn": pawn.get_name() if pawn else None}
    try:
        rec["listeners_within_100m"] = bool(gs.are_any_listeners_within_range(world, loc, 10000.0))
    except Exception as exc:
        rec["listeners_within_100m"] = f"{type(exc).__name__}: {exc}"
    attempts = {
        "at_location_world_ctx": lambda: gs.spawn_sound_at_location(world, sound, loc),
        "at_location_pawn_ctx": lambda: gs.spawn_sound_at_location(pawn, sound, loc),
        "sound_2d_world_ctx": lambda: gs.spawn_sound2d(world, sound),
        "attached_to_pawn": lambda: gs.spawn_sound_attached(sound, pawn.get_editor_property("root_component")),
    }
    for name, fn in attempts.items():
        try:
            comp = fn()
            rec[name] = {"component": comp is not None, "playing": bool(comp and comp.is_playing())}
            if comp:
                comp.stop()
        except Exception as exc:
            rec[name] = {"error": f"{type(exc).__name__}: {exc}"}
    return _envelope("audio_diagnose_spawn", True, rec, reversibility="transient")


@op("audio_place_ambient", mutates=True, reversibility="transactional")
def audio_place_ambient(args):
    """Places an AmbientSound actor in the editor level (sound, auto-activate); PIE copies it into the game world."""
    sound = unreal.EditorAssetLibrary.load_asset(args["sound_path"])
    if not isinstance(sound, unreal.SoundBase):
        return _envelope("audio_place_ambient", False, errors=["not a sound: " + args["sound_path"]])
    with unreal.ScopedEditorTransaction("GameForge audio_place_ambient"):
        actor = _actor_sub().spawn_actor_from_class(unreal.AmbientSound, _vec(args.get("location")))
        actor.set_actor_label(args.get("label", "GF_Ambient"))
        comp = actor.get_editor_property("audio_component")
        comp.set_sound(sound)
        comp.set_editor_property("auto_activate", bool(args.get("auto_activate", False)))
    comp = _find_actor(actor.get_actor_label()).get_editor_property("audio_component")
    return _envelope("audio_place_ambient", comp.sound == sound,
                     {"label": actor.get_actor_label(), "sound": comp.sound.get_path_name() if comp.sound else None,
                      "auto_activate": bool(comp.get_editor_property("auto_activate"))}, reversibility="transactional")


@op("audio_play_actor", mutates=True, reversibility="transient")
def audio_play_actor(args):
    """Plays the AudioComponent of an AmbientSound actor in the running PIE world (by label)."""
    world = _pie_world()
    if world is None:
        return _envelope("audio_play_actor", False, errors=["PIE is not running"])
    label = args["label"]
    for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.AmbientSound):
        if actor.get_actor_label() == label:
            comp = actor.get_editor_property("audio_component")
            comp.play(0.0)
            _AUDIO_COMPONENTS[label] = comp
            unreal.log(f"GF_EVENT audio_play {label} {comp.sound.get_path_name() if comp.sound else None}")
            return _envelope("audio_play_actor", True, {"label": label, "playing": comp.is_playing()},
                             reversibility="transient")
    return _envelope("audio_play_actor", False, errors=[f"no AmbientSound labelled {label} in PIE"])


@op("audio_status", reversibility="read-only")
def audio_status(args):
    """Playing state of sounds started by audio_play_at, and their distance to the PIE player pawn."""
    world = _pie_world()
    if world is None:
        return _envelope("audio_status", False, errors=["PIE is not running"])
    listener = None
    pc = unreal.GameplayStatics.get_player_controller(world, 0)
    if pc and pc.get_controlled_pawn():
        listener = pc.get_controlled_pawn().get_actor_location()
    out = []
    for label, comp in list(_AUDIO_COMPONENTS.items()):
        try:
            loc = comp.get_world_location()
            out.append({"label": label, "playing": comp.is_playing(),
                        "sound": comp.sound.get_path_name() if comp.sound else None,
                        "distance_to_listener": round((loc - listener).length(), 1) if listener else None})
        except Exception as exc:  # component destroyed with the PIE world
            out.append({"label": label, "error": f"{type(exc).__name__}: {exc}"})
    return _envelope("audio_status", bool(out), {"components": out}, errors=[] if out else ["no sounds started"])


# ── M16 cinematics (Sequencer + Movie Render Queue) ────────────────────────

def _binding_id(seq, binding):
    for getter in (lambda: seq.get_portable_binding_id(seq, binding), lambda: seq.get_binding_id(binding),
                   lambda: unreal.MovieSceneSequenceExtensions.get_binding_id(seq, binding)):
        try:
            return getter()
        except Exception:
            continue
    raise RuntimeError("no binding-id accessor on this engine version")


@op("sequence_build", mutates=True, reversibility="snapshot-only")
def sequence_build(args):
    """Builds a LevelSequence: shots [{camera_label, start, end, location, rotation}] become CineCameraActors with a
    camera-cut section each; bindings [{actor_label, keys: [{frame, location}]}] get transform keys; audio
    [{sound_path, start}] gets audio sections. Frames are at `fps`."""
    path = args["asset_path"]
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        unreal.EditorAssetLibrary.delete_asset(path)
    package_path, name = path.rsplit("/", 1)
    seq = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, package_path, unreal.LevelSequence,
                                                                  unreal.LevelSequenceFactoryNew())
    if seq is None:
        return _envelope("sequence_build", False, errors=["create_asset returned None"])
    errors = []
    fps = int(args.get("fps", 24))
    end = int(args.get("end_frame", 72))
    seq.set_display_rate(unreal.FrameRate(fps, 1))
    seq.set_playback_start(0)
    seq.set_playback_end(end)
    cut_track = seq.add_track(unreal.MovieSceneCameraCutTrack)
    for shot in args.get("shots", []):
        cam = _actor_sub().spawn_actor_from_class(unreal.CineCameraActor, _vec(shot["location"]), _rot(shot["rotation"]))
        cam.set_actor_label(shot["camera_label"])
        binding = seq.add_possessable(cam)
        section = cut_track.add_section()
        section.set_range(int(shot["start"]), int(shot["end"]))
        try:
            section.set_camera_binding_id(_binding_id(seq, binding))
        except Exception as exc:
            errors.append(f"camera cut {shot['camera_label']}: {exc}")
    for spec in args.get("bindings", []):
        actor = _find_actor(spec["actor_label"])
        if actor is None:
            errors.append(f"actor not found: {spec['actor_label']}")
            continue
        binding = seq.add_possessable(actor)
        track = binding.add_track(unreal.MovieScene3DTransformTrack)
        section = track.add_section()
        section.set_range(0, end)
        channels = section.get_all_channels()
        for key in spec.get("keys", []):
            loc = key["location"]
            for axis, channel in zip(("x", "y", "z"), channels[:3]):
                channel.add_key(unreal.FrameNumber(int(key["frame"])), float(loc[axis]))
    for spec in args.get("audio", []):
        sound = unreal.EditorAssetLibrary.load_asset(spec["sound_path"])
        track = seq.add_track(unreal.MovieSceneAudioTrack)
        section = track.add_section()
        section.set_sound(sound)
        length = int(round(sound.get_editor_property("duration") * fps)) if sound else fps
        section.set_range(int(spec.get("start", 0)), int(spec.get("start", 0)) + max(1, length))
    unreal.EditorAssetLibrary.save_loaded_asset(seq)
    return _envelope("sequence_build", not errors, {"asset_path": seq.get_path_name()}, errors=errors, affected=[path],
                     reversibility="snapshot-only")


def _section_range(section):
    return [section.get_start_frame(), section.get_end_frame()]


@op("sequence_inspect", reversibility="read-only")
def sequence_inspect(args):
    seq = unreal.EditorAssetLibrary.load_asset(args["sequence_path"])
    if not isinstance(seq, unreal.LevelSequence):
        return _envelope("sequence_inspect", False, errors=["not a LevelSequence: " + args["sequence_path"]])
    bindings = []
    for b in seq.get_bindings():
        tracks = []
        for t in b.get_tracks():
            keys = 0
            for s in t.get_sections():
                for c in s.get_all_channels():
                    try:
                        keys += len(c.get_keys())
                    except Exception:
                        pass
            tracks.append({"type": t.get_class().get_name(), "keys": keys})
        bindings.append({"name": str(b.get_display_name()), "tracks": tracks})
    cuts, audio = [], []
    for t in seq.get_tracks():
        cls = t.get_class().get_name()
        for s in t.get_sections():
            if cls == "MovieSceneCameraCutTrack":
                cuts.append({"range": _section_range(s)})
            elif cls == "MovieSceneAudioTrack":
                snd = s.get_sound()
                audio.append({"range": _section_range(s), "sound": snd.get_path_name() if snd else None})
    rate = seq.get_display_rate()
    return _envelope("sequence_inspect", True, {
        "path": seq.get_path_name(), "fps": rate.numerator / max(rate.denominator, 1),
        "playback": [seq.get_playback_start(), seq.get_playback_end()], "bindings": bindings,
        "camera_cuts": sorted(cuts, key=lambda c: c["range"][0]), "audio": audio})


@op("sequence_evaluate", reversibility="read-only")
def sequence_evaluate(args):
    """Opens the sequence in the editor, scrubs to each frame and reads the bound actors' locations back."""
    seq = unreal.EditorAssetLibrary.load_asset(args["sequence_path"])
    lib = unreal.LevelSequenceEditorBlueprintLibrary
    lib.open_level_sequence(seq)
    out = []
    try:
        for frame in args.get("frames", [0]):
            lib.set_current_time(int(frame))
            row = {"frame": int(frame)}
            for label in args.get("actor_labels", []):
                actor = _find_actor(label)
                if actor:
                    loc = actor.get_actor_location()
                    row[label] = [round(loc.x, 2), round(loc.y, 2), round(loc.z, 2)]
            out.append(row)
    finally:
        lib.close_level_sequence()
    return _envelope("sequence_evaluate", True, {"samples": out})


_MRQ_JOB = {}


@op("sequence_render", mutates=True, reversibility="transient")
def sequence_render(args):
    """Queues a Movie Render Queue job (PIE executor) writing a PNG sequence to output_dir; poll the files."""
    if not hasattr(unreal, "MoviePipelineQueueSubsystem"):
        return _envelope("sequence_render", False, errors=["MovieRenderPipeline plugin not enabled"])
    sub = unreal.get_editor_subsystem(unreal.MoviePipelineQueueSubsystem)
    queue = sub.get_queue()
    for job in list(queue.get_jobs()):
        queue.delete_job(job)
    job = queue.allocate_new_job(unreal.MoviePipelineExecutorJob)
    job.set_editor_property("sequence", unreal.SoftObjectPath(args["sequence_path"]))
    job.set_editor_property("map", unreal.SoftObjectPath(args["map_path"]))
    config = job.get_configuration()
    # "lit" = MoviePipelineDeferredPassBase; "unlit" renders base colour only (no lighting/exposure dependence).
    pass_class = {"lit": unreal.MoviePipelineDeferredPassBase,
                  "unlit": unreal.MoviePipelineDeferredPass_Unlit}[args.get("render_pass", "lit")]
    config.find_or_add_setting_by_class(pass_class)
    aa = config.find_or_add_setting_by_class(unreal.MoviePipelineAntiAliasingSetting)
    aa.set_editor_property("engine_warm_up_count", int(args.get("warmup_frames", 32)))
    aa.set_editor_property("render_warm_up_count", int(args.get("warmup_frames", 32)))
    config.find_or_add_setting_by_class(unreal.MoviePipelineImageSequenceOutput_PNG)
    out = config.find_or_add_setting_by_class(unreal.MoviePipelineOutputSetting)
    out.set_editor_property("output_directory", unreal.DirectoryPath(args["output_dir"]))
    res = args.get("resolution", [640, 360])
    out.set_editor_property("output_resolution", unreal.IntPoint(int(res[0]), int(res[1])))
    # {sequence_name} resolved to "" in 5.7 (files became hidden ".0000.png"), so use a fixed prefix.
    out.set_editor_property("file_name_format", args.get("file_prefix", "frame") + ".{frame_number}")
    executor_class = getattr(unreal, args.get("executor", "MoviePipelinePIEExecutor"))
    executor = sub.render_queue_with_executor(executor_class)
    _MRQ_JOB["executor"] = executor
    return _envelope("sequence_render", executor is not None, {"output_dir": args["output_dir"]},
                     reversibility="transient")


@op("sequence_render_status", reversibility="read-only")
def sequence_render_status(args):
    sub = unreal.get_editor_subsystem(unreal.MoviePipelineQueueSubsystem)
    return _envelope("sequence_render_status", True, {"rendering": bool(sub.is_rendering())})


# ── M19 profiling ───────────────────────────────────────────────────────────

_PERF_COMMANDS = ("csvprofile start", "csvprofile stop", "stat unit", "stat fps", "stat none")


def _csv_dir():
    return os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()), "Profiling", "CSV")


@op("perf_console", mutates=True, reversibility="transient")
def perf_console(args):
    """Runs one allow-listed profiling console command in the PIE world (or the editor world if PIE is off)."""
    cmd = args["command"].strip().lower()
    if cmd not in _PERF_COMMANDS:
        return _envelope("perf_console", False, errors=[f"command not allow-listed: {cmd}; allowed: {list(_PERF_COMMANDS)}"])
    sub = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    world = sub.get_game_world() or sub.get_editor_world()
    unreal.SystemLibrary.execute_console_command(world, cmd)
    return _envelope("perf_console", True, {"command": cmd, "world": world.get_name()}, reversibility="transient")


@op("perf_list_csv", reversibility="read-only")
def perf_list_csv(args):
    folder = _csv_dir()
    files = []
    if os.path.isdir(folder):
        for name in sorted(os.listdir(folder)):
            full = os.path.join(folder, name)
            files.append({"path": full, "bytes": os.path.getsize(full), "mtime": os.path.getmtime(full)})
    return _envelope("perf_list_csv", True, {"folder": folder, "files": files})


@op("rename_asset", mutates=True, reversibility="snapshot-only")
def rename_asset(args):
    """Move/rename through EditorAssetLibrary so references are fixed up (never os.rename)."""
    src, dst = args["source_path"], args["destination_path"]
    if not unreal.EditorAssetLibrary.does_asset_exist(src):
        return _envelope("rename_asset", False, errors=["source asset not found: " + src])
    if unreal.EditorAssetLibrary.does_asset_exist(dst):
        return _envelope("rename_asset", False, errors=["destination already exists: " + dst])
    ok = unreal.EditorAssetLibrary.rename_asset(src, dst)
    moved = unreal.EditorAssetLibrary.does_asset_exist(dst) and not unreal.EditorAssetLibrary.does_asset_exist(src)
    return _envelope("rename_asset", bool(ok) and moved, {"old_path": src, "new_path": dst, "moved": moved},
                     affected=[src, dst], reversibility="snapshot-only",
                     errors=[] if (ok and moved) else ["read-back: asset not at destination"])


@op("delete_asset", mutates=True, reversibility="snapshot-only")
def delete_asset(args):
    path = args["asset_path"]
    if unreal.EditorAssetLibrary.does_directory_exist(path) and not unreal.EditorAssetLibrary.does_asset_exist(path):
        # A content folder: delete it and everything in it.
        ok = unreal.EditorAssetLibrary.delete_directory(path)
        gone = not unreal.EditorAssetLibrary.does_directory_exist(path) or not unreal.EditorAssetLibrary.list_assets(path)
        return _envelope("delete_asset", bool(ok) and gone, {"asset_path": path, "deleted": gone, "directory": True},
                         affected=[path], reversibility="snapshot-only")
    ok = unreal.EditorAssetLibrary.delete_asset(path)
    gone = not unreal.EditorAssetLibrary.does_asset_exist(path)
    return _envelope("delete_asset", bool(ok) and gone, {"asset_path": path, "deleted": gone},
                     affected=[path], reversibility="snapshot-only")


@op("viewport_screenshot")
def viewport_screenshot(args):
    out = args["output_path"]
    res = args.get("resolution", [1280, 720])
    if args.get("show_ui"):
        # Game viewport including UMG/Slate; HighResShot renders the camera only (no widgets).
        if not hasattr(unreal, "GameForgeWidgetLibrary"):
            return _envelope("viewport_screenshot", False, errors=["GameForgeWidgetLibrary not loaded in editor"])
        r = json.loads(unreal.GameForgeWidgetLibrary.capture_viewport_with_ui(out))
        return _envelope("viewport_screenshot", r.get("success", False), {"requested_path": out, "async": True, "show_ui": True},
                         errors=r.get("errors", []))
    unreal.AutomationLibrary.take_high_res_screenshot(int(res[0]), int(res[1]), out)
    # Screenshot is written asynchronously on a later frame; host must poll for the file.
    return _envelope("viewport_screenshot", True, {"requested_path": out, "async": True},
                     warnings=["file appears after the next rendered frame; unavailable under -nullrhi"])


@op("set_viewport_camera")
def set_viewport_camera(args):
    sub = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    sub.set_level_viewport_camera_info(_vec(args.get("location")), _rot(args.get("rotation")))
    loc, rot = sub.get_level_viewport_camera_info()
    return _envelope("set_viewport_camera", True, {
        "location": {"x": loc.x, "y": loc.y, "z": loc.z},
        "rotation": {"pitch": rot.pitch, "yaw": rot.yaw, "roll": rot.roll}})


@op("quit_editor", mutates=True, reversibility="read-only")
def quit_editor(args):
    # The exit request is honoured on a later tick, so this envelope still reaches the host.
    unreal.SystemLibrary.quit_editor()
    return _envelope("quit_editor", True, {"requested": True})


# ── Blueprint Graph Operations (Native Unreal C++ Bridge) ────────────────────

@op("blueprint_inspect")
def blueprint_inspect(args):
    bp_path = args.get("blueprint_path") or args.get("asset_path")
    if not bp_path:
        return _envelope("blueprint_inspect", False, errors=["blueprint_path is required"])
    if not hasattr(unreal, "GameForgeBlueprintGraphLibrary"):
        return _envelope("blueprint_inspect", False, errors=["GameForgeBlueprintGraphLibrary not loaded in editor"])
    res_raw = unreal.GameForgeBlueprintGraphLibrary.inspect_blueprint(bp_path)
    res = json.loads(res_raw)
    return _envelope("blueprint_inspect", res.get("ok", False), res.get("data", {}),
                     errors=res.get("errors", []), warnings=res.get("warnings", []), reversibility="read-only")


@op("blueprint_readback_graph")
def blueprint_readback_graph(args):
    bp_path = args.get("blueprint_path") or args.get("asset_path")
    graph_name = args.get("graph_name", "EventGraph")
    if not bp_path:
        return _envelope("blueprint_readback_graph", False, errors=["blueprint_path is required"])
    if not hasattr(unreal, "GameForgeBlueprintGraphLibrary"):
        return _envelope("blueprint_readback_graph", False, errors=["GameForgeBlueprintGraphLibrary not loaded in editor"])
    res_raw = unreal.GameForgeBlueprintGraphLibrary.readback_graph(bp_path, graph_name)
    res = json.loads(res_raw)
    return _envelope("blueprint_readback_graph", res.get("ok", False), res.get("data", {}),
                     errors=res.get("errors", []), warnings=res.get("warnings", []), reversibility="read-only")


@op("blueprint_create_node", mutates=True, reversibility="transactional")
def blueprint_create_node(args):
    bp_path = args.get("blueprint_path")
    graph_name = args.get("graph_name", "EventGraph")
    node_type = args.get("node_type") or args.get("node_class")
    pos_x = int(args.get("pos_x", 0))
    pos_y = int(args.get("pos_y", 0))
    extra_params = args.get("extra_params") or {}
    if not bp_path or not node_type:
        return _envelope("blueprint_create_node", False, errors=["blueprint_path and node_type are required"])
    if not hasattr(unreal, "GameForgeBlueprintGraphLibrary"):
        return _envelope("blueprint_create_node", False, errors=["GameForgeBlueprintGraphLibrary not loaded in editor"])
    res_raw = unreal.GameForgeBlueprintGraphLibrary.create_node(bp_path, graph_name, node_type, pos_x, pos_y, json.dumps(extra_params))
    res = json.loads(res_raw)
    return _envelope("blueprint_create_node", res.get("ok", False), res.get("data", {}),
                     errors=res.get("errors", []), warnings=res.get("warnings", []), affected=[bp_path], reversibility="transactional")


@op("blueprint_set_pin_default", mutates=True, reversibility="transactional")
def blueprint_set_pin_default(args):
    bp_path = args.get("blueprint_path")
    node_id = args.get("node_id") or args.get("node_name")
    pin_name = args.get("pin_name")
    default_val = str(args.get("default_value", ""))
    if not bp_path or not node_id or not pin_name:
        return _envelope("blueprint_set_pin_default", False, errors=["blueprint_path, node_id, and pin_name are required"])
    if not hasattr(unreal, "GameForgeBlueprintGraphLibrary"):
        return _envelope("blueprint_set_pin_default", False, errors=["GameForgeBlueprintGraphLibrary not loaded in editor"])
    res_raw = unreal.GameForgeBlueprintGraphLibrary.set_pin_default(bp_path, node_id, pin_name, default_val)
    res = json.loads(res_raw)
    return _envelope("blueprint_set_pin_default", res.get("ok", False), res.get("data", {}),
                     errors=res.get("errors", []), warnings=res.get("warnings", []), affected=[bp_path], reversibility="transactional")


@op("blueprint_connect_pins", mutates=True, reversibility="transactional")
def blueprint_connect_pins(args):
    bp_path = args.get("blueprint_path")
    from_node = args.get("from_node") or args.get("from_node_id")
    from_pin = args.get("from_pin") or args.get("from_pin_name")
    to_node = args.get("to_node") or args.get("to_node_id")
    to_pin = args.get("to_pin") or args.get("to_pin_name")
    if not bp_path or not from_node or not from_pin or not to_node or not to_pin:
        return _envelope("blueprint_connect_pins", False, errors=["blueprint_path, from_node, from_pin, to_node, and to_pin are required"])
    if not hasattr(unreal, "GameForgeBlueprintGraphLibrary"):
        return _envelope("blueprint_connect_pins", False, errors=["GameForgeBlueprintGraphLibrary not loaded in editor"])
    res_raw = unreal.GameForgeBlueprintGraphLibrary.connect_pins(bp_path, from_node, from_pin, to_node, to_pin)
    res = json.loads(res_raw)
    return _envelope("blueprint_connect_pins", res.get("ok", False), res.get("data", {}),
                     errors=res.get("errors", []), warnings=res.get("warnings", []), affected=[bp_path], reversibility="transactional")


@op("blueprint_disconnect_pins", mutates=True, reversibility="transactional")
def blueprint_disconnect_pins(args):
    bp_path = args.get("blueprint_path")
    from_node = args.get("from_node") or args.get("from_node_id")
    from_pin = args.get("from_pin") or args.get("from_pin_name")
    to_node = args.get("to_node") or args.get("to_node_id") or ""
    to_pin = args.get("to_pin") or args.get("to_pin_name") or ""
    if not bp_path or not from_node or not from_pin:
        return _envelope("blueprint_disconnect_pins", False, errors=["blueprint_path, from_node, and from_pin are required"])
    if not hasattr(unreal, "GameForgeBlueprintGraphLibrary"):
        return _envelope("blueprint_disconnect_pins", False, errors=["GameForgeBlueprintGraphLibrary not loaded in editor"])
    res_raw = unreal.GameForgeBlueprintGraphLibrary.disconnect_pins(bp_path, from_node, from_pin, to_node, to_pin)
    res = json.loads(res_raw)
    return _envelope("blueprint_disconnect_pins", res.get("ok", False), res.get("data", {}),
                     errors=res.get("errors", []), warnings=res.get("warnings", []), affected=[bp_path], reversibility="transactional")


@op("blueprint_delete_node", mutates=True, reversibility="transactional")
def blueprint_delete_node(args):
    bp_path = args.get("blueprint_path")
    node_id = args.get("node_id") or args.get("node_name")
    if not bp_path or not node_id:
        return _envelope("blueprint_delete_node", False, errors=["blueprint_path and node_id are required"])
    if not hasattr(unreal, "GameForgeBlueprintGraphLibrary"):
        return _envelope("blueprint_delete_node", False, errors=["GameForgeBlueprintGraphLibrary not loaded in editor"])
    res_raw = unreal.GameForgeBlueprintGraphLibrary.delete_node(bp_path, node_id)
    res = json.loads(res_raw)
    return _envelope("blueprint_delete_node", res.get("ok", False), res.get("data", {}),
                     errors=res.get("errors", []), warnings=res.get("warnings", []), affected=[bp_path], reversibility="transactional")


@op("blueprint_compile", mutates=True, reversibility="transactional")
def blueprint_compile_op(args):
    bp_path = args.get("blueprint_path")
    if not bp_path:
        return _envelope("blueprint_compile", False, errors=["blueprint_path is required"])
    if hasattr(unreal, "GameForgeBlueprintGraphLibrary"):
        res_raw = unreal.GameForgeBlueprintGraphLibrary.compile_blueprint(bp_path)
        res = json.loads(res_raw)
        return _envelope("blueprint_compile", res.get("ok", False), res.get("data", {}),
                         errors=res.get("errors", []), warnings=res.get("warnings", []), affected=[bp_path], reversibility="transactional")
    return compile_blueprint(args)


@op("blueprint_save", mutates=True, reversibility="snapshot-only")
def blueprint_save_op(args):
    bp_path = args.get("blueprint_path")
    if not bp_path:
        return _envelope("blueprint_save", False, errors=["blueprint_path is required"])
    if hasattr(unreal, "GameForgeBlueprintGraphLibrary"):
        res_raw = unreal.GameForgeBlueprintGraphLibrary.save_blueprint(bp_path)
        res = json.loads(res_raw)
        return _envelope("blueprint_save", res.get("ok", False), res.get("data", {}),
                         errors=res.get("errors", []), warnings=res.get("warnings", []), affected=[bp_path], reversibility="snapshot-only")
    bp = unreal.EditorAssetLibrary.load_asset(bp_path)
    if not bp:
        return _envelope("blueprint_save", False, errors=["asset not found"])
    saved = unreal.EditorAssetLibrary.save_loaded_asset(bp)
    return _envelope("blueprint_save", bool(saved), {"blueprint_path": bp_path, "saved": bool(saved)},
                     affected=[bp_path], reversibility="snapshot-only")


@op("pie_start", mutates=True, reversibility="transient")
def pie_start(args):
    sub = _level_sub()
    if not sub:
        return _envelope("pie_start", False, errors=["LevelEditorSubsystem not found"])
    if args.get("simulate", False):
        sub.editor_play_simulate()
    else:
        sub.editor_request_begin_play()
    return _envelope("pie_start", True, {"requested": True})


@op("pie_status", mutates=False, reversibility="read-only")
def pie_status(args):
    sub = _level_sub()
    in_pie = sub.is_in_play_in_editor() if sub else False
    return _envelope("pie_status", True, {"in_pie": in_pie})


@op("pie_stop", mutates=True, reversibility="transient")
def pie_stop(args):
    sub = _level_sub()
    if not sub:
        return _envelope("pie_stop", False, errors=["LevelEditorSubsystem not found"])
    sub.editor_request_end_play()
    return _envelope("pie_stop", True, {"stopped": True})


# ── UMG Widget Operations ───────────────────────────────────────────────────

@op("widget_create_blueprint", mutates=True, reversibility="transactional")
def widget_create_blueprint(args):
    asset_path = args.get("asset_path")
    parent_class = args.get("parent_class", "UserWidget")
    root_class = args.get("root_widget_class", "CanvasPanel")
    if not asset_path:
        return _envelope("widget_create_blueprint", False, errors=["asset_path is required"])
    if not hasattr(unreal, "GameForgeWidgetLibrary"):
        return _envelope("widget_create_blueprint", False, errors=["GameForgeWidgetLibrary not loaded in editor"])
    res_raw = unreal.GameForgeWidgetLibrary.create_widget_blueprint(asset_path, parent_class, root_class)
    res = json.loads(res_raw)
    return _envelope("widget_create_blueprint", res.get("success", False), res.get("data", {}),
                     errors=res.get("errors", []), warnings=res.get("warnings", []), affected=[asset_path])


@op("widget_inspect", mutates=False, reversibility="read-only")
def widget_inspect(args):
    asset_path = args.get("asset_path")
    if not asset_path:
        return _envelope("widget_inspect", False, errors=["asset_path is required"])
    if not hasattr(unreal, "GameForgeWidgetLibrary"):
        return _envelope("widget_inspect", False, errors=["GameForgeWidgetLibrary not loaded in editor"])
    res_raw = unreal.GameForgeWidgetLibrary.inspect_widget_blueprint(asset_path)
    res = json.loads(res_raw)
    return _envelope("widget_inspect", res.get("success", False), res.get("data", {}),
                     errors=res.get("errors", []), warnings=res.get("warnings", []))


@op("widget_readback_tree", mutates=False, reversibility="read-only")
def widget_readback_tree(args):
    asset_path = args.get("asset_path")
    if not asset_path:
        return _envelope("widget_readback_tree", False, errors=["asset_path is required"])
    if not hasattr(unreal, "GameForgeWidgetLibrary"):
        return _envelope("widget_readback_tree", False, errors=["GameForgeWidgetLibrary not loaded in editor"])
    res_raw = unreal.GameForgeWidgetLibrary.readback_widget_tree(asset_path)
    res = json.loads(res_raw)
    return _envelope("widget_readback_tree", res.get("success", False), res.get("data", {}),
                     errors=res.get("errors", []), warnings=res.get("warnings", []))


@op("widget_create", mutates=True, reversibility="transactional")
def widget_create(args):
    asset_path = args.get("asset_path")
    widget_class = args.get("widget_class")
    widget_name = args.get("widget_name")
    parent_name = args.get("parent_name", "")
    if not asset_path or not widget_class or not widget_name:
        return _envelope("widget_create", False, errors=["asset_path, widget_class, and widget_name are required"])
    if not hasattr(unreal, "GameForgeWidgetLibrary"):
        return _envelope("widget_create", False, errors=["GameForgeWidgetLibrary not loaded in editor"])
    res_raw = unreal.GameForgeWidgetLibrary.create_widget(asset_path, widget_class, widget_name, parent_name)
    res = json.loads(res_raw)
    return _envelope("widget_create", res.get("success", False), res.get("data", {}),
                     errors=res.get("errors", []), warnings=res.get("warnings", []), affected=[asset_path])


@op("widget_set_property", mutates=True, reversibility="transactional")
def widget_set_property(args):
    asset_path = args.get("asset_path")
    widget_name = args.get("widget_name")
    property_name = args.get("property_name")
    value = args.get("value")
    if not asset_path or not widget_name or not property_name:
        return _envelope("widget_set_property", False, errors=["asset_path, widget_name, and property_name are required"])
    if not hasattr(unreal, "GameForgeWidgetLibrary"):
        return _envelope("widget_set_property", False, errors=["GameForgeWidgetLibrary not loaded in editor"])
    val_json = json.dumps(value if isinstance(value, dict) else {"value": value})
    res_raw = unreal.GameForgeWidgetLibrary.set_widget_property(asset_path, widget_name, property_name, val_json)
    res = json.loads(res_raw)
    return _envelope("widget_set_property", res.get("success", False), res.get("data", {}),
                     errors=res.get("errors", []), warnings=res.get("warnings", []), affected=[asset_path])


@op("widget_set_slot_property", mutates=True, reversibility="transactional")
def widget_set_slot_property(args):
    asset_path = args.get("asset_path")
    widget_name = args.get("widget_name")
    slot_properties = args.get("slot_properties") or {}
    if not asset_path or not widget_name:
        return _envelope("widget_set_slot_property", False, errors=["asset_path and widget_name are required"])
    if not hasattr(unreal, "GameForgeWidgetLibrary"):
        return _envelope("widget_set_slot_property", False, errors=["GameForgeWidgetLibrary not loaded in editor"])
    res_raw = unreal.GameForgeWidgetLibrary.set_widget_slot_property(asset_path, widget_name, json.dumps(slot_properties))
    res = json.loads(res_raw)
    return _envelope("widget_set_slot_property", res.get("success", False), res.get("data", {}),
                     errors=res.get("errors", []), warnings=res.get("warnings", []), affected=[asset_path])


@op("widget_remove", mutates=True, reversibility="transactional")
def widget_remove(args):
    asset_path = args.get("asset_path")
    widget_name = args.get("widget_name")
    if not asset_path or not widget_name:
        return _envelope("widget_remove", False, errors=["asset_path and widget_name are required"])
    if not hasattr(unreal, "GameForgeWidgetLibrary"):
        return _envelope("widget_remove", False, errors=["GameForgeWidgetLibrary not loaded in editor"])
    res_raw = unreal.GameForgeWidgetLibrary.remove_widget(asset_path, widget_name)
    res = json.loads(res_raw)
    return _envelope("widget_remove", res.get("success", False), res.get("data", {}),
                     errors=res.get("errors", []), warnings=res.get("warnings", []), affected=[asset_path])


@op("widget_compile", mutates=True, reversibility="transactional")
def widget_compile(args):
    asset_path = args.get("asset_path")
    if not asset_path:
        return _envelope("widget_compile", False, errors=["asset_path is required"])
    if not hasattr(unreal, "GameForgeWidgetLibrary"):
        return _envelope("widget_compile", False, errors=["GameForgeWidgetLibrary not loaded in editor"])
    res_raw = unreal.GameForgeWidgetLibrary.compile_widget_blueprint(asset_path)
    res = json.loads(res_raw)
    return _envelope("widget_compile", res.get("success", False), res.get("data", {}),
                     errors=res.get("errors", []), warnings=res.get("warnings", []), affected=[asset_path])


@op("widget_save", mutates=True, reversibility="snapshot-only")
def widget_save(args):
    asset_path = args.get("asset_path")
    if not asset_path:
        return _envelope("widget_save", False, errors=["asset_path is required"])
    if not hasattr(unreal, "GameForgeWidgetLibrary"):
        return _envelope("widget_save", False, errors=["GameForgeWidgetLibrary not loaded in editor"])
    res_raw = unreal.GameForgeWidgetLibrary.save_widget_blueprint(asset_path)
    res = json.loads(res_raw)
    return _envelope("widget_save", res.get("success", False), res.get("data", {}),
                     errors=res.get("errors", []), warnings=res.get("warnings", []), affected=[asset_path])


@op("widget_display_in_game", mutates=True, reversibility="transient")
def widget_display_in_game(args):
    asset_path = args.get("asset_path")
    z_order = int(args.get("z_order", 0))
    if not asset_path:
        return _envelope("widget_display_in_game", False, errors=["asset_path is required"])
    if not hasattr(unreal, "GameForgeWidgetLibrary"):
        return _envelope("widget_display_in_game", False, errors=["GameForgeWidgetLibrary not loaded in editor"])
    res_raw = unreal.GameForgeWidgetLibrary.display_widget_in_game(asset_path, z_order)
    res = json.loads(res_raw)
    return _envelope("widget_display_in_game", res.get("success", False), res.get("data", {}),
                     errors=res.get("errors", []), warnings=res.get("warnings", []))


@op("widget_bind_event", mutates=True, reversibility="snapshot-only")
def widget_bind_event(args):
    asset_path = args.get("asset_path")
    widget_name = args.get("widget_name")
    delegate_name = args.get("delegate_name", "OnClicked")
    action_type = args.get("action_type", "PrintString")
    action_params = args.get("action_params") or {}
    action_payload = {"action_type": action_type, **action_params}

    if not asset_path or not widget_name:
        return _envelope("widget_bind_event", False, errors=["asset_path and widget_name are required"])
    if not hasattr(unreal, "GameForgeWidgetLibrary"):
        return _envelope("widget_bind_event", False, errors=["GameForgeWidgetLibrary not loaded in editor"])

    res_raw = unreal.GameForgeWidgetLibrary.bind_widget_event(
        asset_path, widget_name, delegate_name, json.dumps(action_payload)
    )
    res = json.loads(res_raw)
    return _envelope("widget_bind_event", res.get("success", False), res.get("data", {}),
                     errors=res.get("errors", []), warnings=res.get("warnings", []), affected=[asset_path])


@op("widget_inspect_events", reversibility="read-only")
def widget_inspect_events(args):
    asset_path = args.get("asset_path")
    if not asset_path:
        return _envelope("widget_inspect_events", False, errors=["asset_path is required"])
    if not hasattr(unreal, "GameForgeWidgetLibrary"):
        return _envelope("widget_inspect_events", False, errors=["GameForgeWidgetLibrary not loaded in editor"])

    res_raw = unreal.GameForgeWidgetLibrary.inspect_widget_events(asset_path)
    res = json.loads(res_raw)
    return _envelope("widget_inspect_events", res.get("success", False), res.get("data", {}),
                     errors=res.get("errors", []), warnings=res.get("warnings", []), reversibility="read-only")


@op("widget_click_button", mutates=True, reversibility="transient")
def widget_click_button(args):
    asset_path = args.get("asset_path", "")
    button_name = args.get("button_name") or args.get("widget_name")
    mode = args.get("mode", "real_input")
    if not button_name:
        return _envelope("widget_click_button", False, errors=["button_name or widget_name is required"])
    if not hasattr(unreal, "GameForgeWidgetLibrary"):
        return _envelope("widget_click_button", False, errors=["GameForgeWidgetLibrary not loaded in editor"])

    if mode == "delegate_diagnostic":
        fn = getattr(unreal.GameForgeWidgetLibrary, "trigger_button_delegate_diagnostic", unreal.GameForgeWidgetLibrary.trigger_button_click)
        res_raw = fn(asset_path, button_name)
    else:
        fn = getattr(unreal.GameForgeWidgetLibrary, "trigger_button_click_real_input", unreal.GameForgeWidgetLibrary.trigger_button_click)
        res_raw = fn(asset_path, button_name)

    res = json.loads(res_raw)
    return _envelope("widget_click_button", res.get("success", False), res.get("data", {}),
                     errors=res.get("errors", []), warnings=res.get("warnings", []))


@op("widget_trigger_delegate_diagnostic", mutates=True, reversibility="transient")
def widget_trigger_delegate_diagnostic(args):
    """Diagnostic tool: directly broadcasts OnClicked delegate. Labeled as diagnostic only."""
    asset_path = args.get("asset_path", "")
    button_name = args.get("button_name") or args.get("widget_name")
    if not button_name:
        return _envelope("widget_trigger_delegate_diagnostic", False, errors=["button_name or widget_name is required"])
    if not hasattr(unreal, "GameForgeWidgetLibrary"):
        return _envelope("widget_trigger_delegate_diagnostic", False, errors=["GameForgeWidgetLibrary not loaded in editor"])

    fn = getattr(unreal.GameForgeWidgetLibrary, "trigger_button_delegate_diagnostic", unreal.GameForgeWidgetLibrary.trigger_button_click)
    res_raw = fn(asset_path, button_name)
    res = json.loads(res_raw)
    return _envelope("widget_trigger_delegate_diagnostic", res.get("success", False), res.get("data", {}),
                     errors=res.get("errors", []), warnings=["Direct delegate invocation diagnostic; not proof of UI hit-testing."])


@op("widget_runtime_state", reversibility="read-only")
def widget_runtime_state(args):
    asset_path = args.get("asset_path")
    if not asset_path:
        return _envelope("widget_runtime_state", False, errors=["asset_path is required"])
    if not hasattr(unreal, "GameForgeWidgetLibrary"):
        return _envelope("widget_runtime_state", False, errors=["GameForgeWidgetLibrary not loaded in editor"])

    res_raw = unreal.GameForgeWidgetLibrary.get_widget_runtime_state(asset_path)
    res = json.loads(res_raw)
    return _envelope("widget_runtime_state", res.get("success", False), res.get("data", {}),
                     errors=res.get("errors", []), warnings=res.get("warnings", []), reversibility="read-only")


@op("gameplay_get_state", reversibility="read-only")
def gameplay_get_state(args):
    if not hasattr(unreal, "GameForgeWidgetLibrary"):
        return _envelope("gameplay_get_state", False, errors=["GameForgeWidgetLibrary not loaded in editor"])

    res_raw = unreal.GameForgeWidgetLibrary.get_gameplay_state()
    res = json.loads(res_raw)
    return _envelope("gameplay_get_state", res.get("success", False), res.get("data", {}),
                     errors=res.get("errors", []), warnings=res.get("warnings", []), reversibility="read-only")


@op("gameplay_modify_state", mutates=True, reversibility="transient")
def gameplay_modify_state(args):
    delta_health = float(args.get("delta_health", 0.0))
    delta_stamina = float(args.get("delta_stamina", 0.0))
    menu_action = str(args.get("menu_action", ""))

    if not hasattr(unreal, "GameForgeWidgetLibrary"):
        return _envelope("gameplay_modify_state", False, errors=["GameForgeWidgetLibrary not loaded in editor"])

    res_raw = unreal.GameForgeWidgetLibrary.modify_gameplay_state(delta_health, delta_stamina, menu_action)
    res = json.loads(res_raw)
    return _envelope("gameplay_modify_state", res.get("success", False), res.get("data", {}),
                     errors=res.get("errors", []), warnings=res.get("warnings", []))




# ── Landscape & Procedural World Operations ──────────────────────────────────

@op("landscape_create", mutates=True, reversibility="transactional")
def landscape_create(args):
    if not hasattr(unreal, "GameForgeLandscapeLibrary"):
        return _envelope("landscape_create", False, errors=["GameForgeLandscapeLibrary not loaded in editor"])
    res_raw = unreal.GameForgeLandscapeLibrary.create_landscape(json.dumps(args))
    res = json.loads(res_raw)
    return _envelope("landscape_create", res.get("success", False), res.get("data", {}),
                     errors=res.get("errors", []), warnings=res.get("warnings", []))


@op("spline_create_road", mutates=True, reversibility="transactional")
def spline_create_road(args):
    if not hasattr(unreal, "GameForgeLandscapeLibrary"):
        return _envelope("spline_create_road", False, errors=["GameForgeLandscapeLibrary not loaded in editor"])
    res_raw = unreal.GameForgeLandscapeLibrary.create_spline_road(json.dumps(args))
    res = json.loads(res_raw)
    return _envelope("spline_create_road", res.get("success", False), res.get("data", {}),
                     errors=res.get("errors", []), warnings=res.get("warnings", []))


@op("foliage_scatter", mutates=True, reversibility="transactional")
def foliage_scatter(args):
    if not hasattr(unreal, "GameForgeLandscapeLibrary"):
        return _envelope("foliage_scatter", False, errors=["GameForgeLandscapeLibrary not loaded in editor"])
    res_raw = unreal.GameForgeLandscapeLibrary.create_foliage_scatter(json.dumps(args))
    res = json.loads(res_raw)
    return _envelope("foliage_scatter", res.get("success", False), res.get("data", {}),
                     errors=res.get("errors", []), warnings=res.get("warnings", []))


@op("landmark_spawn", mutates=True, reversibility="transactional")
def landmark_spawn(args):
    if not hasattr(unreal, "GameForgeLandscapeLibrary"):
        return _envelope("landmark_spawn", False, errors=["GameForgeLandscapeLibrary not loaded in editor"])
    res_raw = unreal.GameForgeLandscapeLibrary.create_landmark(json.dumps(args))
    res = json.loads(res_raw)
    return _envelope("landmark_spawn", res.get("success", False), res.get("data", {}),
                     errors=res.get("errors", []), warnings=res.get("warnings", []))


@op("landscape_inspect_layers", reversibility="read-only")
def landscape_inspect_layers(args):
    """Per paint layer of the landscape: layer info asset, mean weight and dominant fraction (engine weightmaps)."""
    if not hasattr(unreal, "GameForgeLandscapeLibrary") or             not hasattr(unreal.GameForgeLandscapeLibrary, "inspect_landscape_layers"):
        return _envelope("landscape_inspect_layers", False,
                         errors=["GameForgeLandscapeLibrary.inspect_landscape_layers not loaded (rebuild the plugin)"])
    res = json.loads(unreal.GameForgeLandscapeLibrary.inspect_landscape_layers())
    return _envelope("landscape_inspect_layers", res.get("success", False), res.get("data", {}),
                     errors=res.get("errors", []), warnings=res.get("warnings", []))


@op("procedural_world_inspect", reversibility="read-only")
def procedural_world_inspect(args):
    if not hasattr(unreal, "GameForgeLandscapeLibrary"):
        return _envelope("procedural_world_inspect", False, errors=["GameForgeLandscapeLibrary not loaded in editor"])
    res_raw = unreal.GameForgeLandscapeLibrary.inspect_procedural_world()
    res = json.loads(res_raw)
    return _envelope("procedural_world_inspect", res.get("success", False), res.get("data", {}),
                     errors=res.get("errors", []), warnings=res.get("warnings", []), reversibility="read-only")

def _configure_fbx_skeletal_import(options, scale: float) -> None:
    options.set_editor_property("import_as_skeletal", True)
    options.set_editor_property("import_mesh", True)
    options.set_editor_property("import_materials", True)
    options.set_editor_property("import_textures", True)
    options.set_editor_property("import_animations", False)
    options.set_editor_property("create_physics_asset", True)
    skel_data = options.get_editor_property("skeletal_mesh_import_data")
    skel_data.set_editor_property("import_content_type", unreal.FBXImportContentType.FBXICT_ALL)
    skel_data.set_editor_property("import_uniform_scale", scale)


@op("character_import_skeletal_mesh", mutates=True, reversibility="snapshot-only")
def character_import_skeletal_mesh(args):
    src = args["source_file"]
    if not os.path.isfile(src):
        return _envelope("character_import_skeletal_mesh", False, errors=["source file not found: " + src])
    dest_path = args.get("destination_path", "/Game/Quarantine/Characters")
    dest_name = args.get("destination_name", "")
    is_gltf = src.lower().endswith((".gltf", ".glb"))

    options = None if is_gltf else unreal.FbxImportUI()  # glTF goes through Interchange's default pipeline
    if options is not None:
        _configure_fbx_skeletal_import(options, float(args.get("scale", 1.0)))
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", src)
    task.set_editor_property("destination_path", dest_path)
    if dest_name:
        task.set_editor_property("destination_name", dest_name)
    task.set_editor_property("automated", True)
    task.set_editor_property("save", True)
    task.set_editor_property("replace_existing", bool(args.get("replace_existing", True)))
    if options is not None:
        task.set_editor_property("options", options)

    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    imported = [str(p) for p in task.get_editor_property("imported_object_paths")]
    if not imported:
        # Interchange may not fill imported_object_paths; read the destination folder instead.
        imported = [p for p in unreal.EditorAssetLibrary.list_assets(dest_path, recursive=True, include_folder=False)]

    skel_mesh_path = ""
    skeleton_path = ""
    for p in imported:
        clean = p.split(".")[0]
        asset = unreal.EditorAssetLibrary.load_asset(clean)
        if isinstance(asset, unreal.SkeletalMesh):
            skel_mesh_path = clean
            skel_obj = asset.get_editor_property("skeleton")
            if skel_obj:
                skeleton_path = skel_obj.get_path_name().split(".")[0]
        elif isinstance(asset, unreal.Skeleton) and not skeleton_path:
            skeleton_path = clean

    ok = bool(skel_mesh_path and unreal.EditorAssetLibrary.does_asset_exist(skel_mesh_path))
    return _envelope(
        "character_import_skeletal_mesh",
        ok,
        {
            "imported": imported,
            "skeletal_mesh_path": skel_mesh_path,
            "skeleton_path": skeleton_path,
            "destination_path": dest_path,
        },
        affected=imported,
        reversibility="snapshot-only",
        errors=[] if ok else ["Skeletal mesh import produced no valid USkeletalMesh"],
    )


@op("character_inspect_skeletal_mesh", reversibility="read-only")
def character_inspect_skeletal_mesh(args):
    if hasattr(unreal, "GameForgeCharacterLibrary"):
        res_raw = unreal.GameForgeCharacterLibrary.inspect_skeletal_mesh(json.dumps(args))
        res = json.loads(res_raw)
        return _envelope(
            "character_inspect_skeletal_mesh",
            res.get("ok", False),
            res.get("data", {}),
            errors=res.get("errors", []),
            reversibility="read-only",
        )
    mesh_path = args.get("skeletal_mesh_path", "")
    asset = unreal.EditorAssetLibrary.load_asset(mesh_path)
    if not isinstance(asset, unreal.SkeletalMesh):
        return _envelope("character_inspect_skeletal_mesh", False, errors=["Asset is not a USkeletalMesh: " + mesh_path])
    skel = asset.get_editor_property("skeleton")
    return _envelope("character_inspect_skeletal_mesh", True, {
        "mesh_path": mesh_path,
        "asset_name": asset.get_name(),
        "has_skeleton": skel is not None,
        "skeleton_path": skel.get_path_name() if skel else "None",
    }, reversibility="read-only")


@op("character_spawn_preview", mutates=True, reversibility="transactional")
def character_spawn_preview(args):
    if hasattr(unreal, "GameForgeCharacterLibrary"):
        res_raw = unreal.GameForgeCharacterLibrary.spawn_character_preview_actor(json.dumps(args))
        res = json.loads(res_raw)
        return _envelope(
            "character_spawn_preview",
            res.get("ok", False),
            res.get("data", {}),
            errors=res.get("errors", []),
            reversibility="transactional",
        )
    return _envelope("character_spawn_preview", False, errors=["GameForgeCharacterLibrary not loaded in editor"])

@op("anim_inspect_sequence", reversibility="read-only")
def anim_inspect_sequence(args):
    if hasattr(unreal, "GameForgeAnimationLibrary"):
        res_raw = unreal.GameForgeAnimationLibrary.inspect_animation_sequence(json.dumps(args))
        res = json.loads(res_raw)
        return _envelope(
            "anim_inspect_sequence",
            res.get("ok", False),
            res.get("data", {}),
            errors=res.get("errors", []),
            reversibility="read-only",
        )
    return _envelope("anim_inspect_sequence", False, errors=["GameForgeAnimationLibrary not loaded in editor"])


@op("anim_inspect_blueprint", reversibility="read-only")
def anim_inspect_blueprint(args):
    if hasattr(unreal, "GameForgeAnimationLibrary"):
        res_raw = unreal.GameForgeAnimationLibrary.inspect_animation_blueprint(json.dumps(args))
        res = json.loads(res_raw)
        return _envelope(
            "anim_inspect_blueprint",
            res.get("ok", False),
            res.get("data", {}),
            errors=res.get("errors", []),
            reversibility="read-only",
        )
    return _envelope("anim_inspect_blueprint", False, errors=["GameForgeAnimationLibrary not loaded in editor"])


@op("anim_create_locomotion_blueprint", mutates=True, reversibility="snapshot-only")
def anim_create_locomotion_blueprint(args):
    if hasattr(unreal, "GameForgeAnimationLibrary"):
        res_raw = unreal.GameForgeAnimationLibrary.create_locomotion_anim_blueprint(json.dumps(args))
        res = json.loads(res_raw)
        return _envelope(
            "anim_create_locomotion_blueprint",
            res.get("ok", False),
            res.get("data", {}),
            errors=res.get("errors", []),
            reversibility="snapshot-only",
        )
    return _envelope("anim_create_locomotion_blueprint", False, errors=["GameForgeAnimationLibrary not loaded in editor"])


@op("anim_import_motion_clip", mutates=True, reversibility="snapshot-only")
def anim_import_motion_clip(args):
    if not hasattr(unreal, "GameForgeAnimationLibrary"):
        return _envelope("anim_import_motion_clip", False, errors=["GameForgeAnimationLibrary not loaded in editor"])
    res = json.loads(unreal.GameForgeAnimationLibrary.import_motion_clip(json.dumps(args)))
    return _envelope("anim_import_motion_clip", res.get("ok", False), res.get("data", {}),
                     errors=res.get("errors", []), affected=[args.get("destination_path", "")],
                     reversibility="snapshot-only")


@op("anim_sample_bone_pose", reversibility="read-only")
def anim_sample_bone_pose(args):
    """Reads bone-local transforms from an AnimSequence at given times (the engine's own evaluation)."""
    seq = unreal.EditorAssetLibrary.load_asset(args["anim_sequence_path"])
    if not isinstance(seq, unreal.AnimSequence):
        return _envelope("anim_sample_bone_pose", False, errors=["not an AnimSequence: " + args["anim_sequence_path"]])
    out = []
    for bone in args.get("bones", []):
        for t in args.get("times", [0.0]):
            pose = unreal.AnimationLibrary.get_bone_pose_for_time(seq, bone, float(t), False)
            q = pose.rotation
            loc = pose.translation
            out.append({"bone": bone, "time": t, "rotation_quat": [q.x, q.y, q.z, q.w],
                        "location": [loc.x, loc.y, loc.z]})
    return _envelope("anim_sample_bone_pose", True, {"samples": out, "play_length_s": seq.get_play_length()},
                     reversibility="read-only")


@op("anim_sample_world_pose", reversibility="read-only")
def anim_sample_world_pose(args):
    """Component-space (world, actor at origin) bone transforms of an AnimSequence at given times, evaluated by
    the engine's AnimPose library, plus the same bones in the skeleton's reference pose."""
    seq = unreal.EditorAssetLibrary.load_asset(args["anim_sequence_path"])
    if not isinstance(seq, unreal.AnimSequence):
        return _envelope("anim_sample_world_pose", False, errors=["not an AnimSequence: " + args["anim_sequence_path"]])
    ext, world = unreal.AnimPoseExtensions, unreal.AnimPoseSpaces.WORLD
    bones = args.get("bones", [])

    def read(pose, getter):
        out = {}
        for bone in bones:
            t = getter(pose, bone, world)
            out[bone] = [t.translation.x, t.translation.y, t.translation.z]
        return out

    frames = []
    for t in args.get("times", [0.0]):
        pose = ext.get_anim_pose_at_time(seq, float(t), unreal.AnimPoseEvaluationOptions())
        frames.append({"time": t, "positions": read(pose, ext.get_bone_pose)})
    ref = read(ext.get_anim_pose_at_time(seq, 0.0, unreal.AnimPoseEvaluationOptions()), ext.get_ref_bone_pose)
    return _envelope("anim_sample_world_pose", True, {"frames": frames, "reference": ref,
                                                      "skeleton": seq.get_editor_property("skeleton").get_path_name(),
                                                      "play_length_s": seq.get_play_length()},
                     reversibility="read-only")


def _blendspace_record(bs):
    rec = {"path": bs.get_path_name(), "class": bs.get_class().get_name()}
    try:
        params = bs.get_editor_property("blend_parameters")
        rec["axes"] = [{"name": str(p.get_editor_property("display_name")), "min": p.get_editor_property("min"),
                        "max": p.get_editor_property("max"), "grid": p.get_editor_property("grid_num")}
                       for p in list(params)[:1 if isinstance(bs, unreal.BlendSpace1D) else 2]]
    except Exception as exc:
        rec["axes_error"] = f"{type(exc).__name__}: {exc}"
    try:
        rec["samples"] = [{"animation": s.get_editor_property("animation").get_path_name()
                           if s.get_editor_property("animation") else None,
                           "value": round(s.get_editor_property("sample_value").x, 3)}
                          for s in bs.get_editor_property("sample_data")]
    except Exception as exc:
        rec["samples_error"] = f"{type(exc).__name__}: {exc}"
    try:
        rec["skeleton"] = bs.get_editor_property("skeleton").get_path_name()
    except Exception:
        pass
    return rec


@op("anim_create_blendspace_1d", mutates=True, reversibility="snapshot-only")
def anim_create_blendspace_1d(args):
    """Creates a BlendSpace1D on a skeleton with one axis and samples [{animation, value}] (e.g. Speed 0/150/450)."""
    path = args["asset_path"]
    skeleton = unreal.EditorAssetLibrary.load_asset(args["skeleton_path"])
    if not isinstance(skeleton, unreal.Skeleton):
        return _envelope("anim_create_blendspace_1d", False, errors=["not a Skeleton: " + args["skeleton_path"]])
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        unreal.EditorAssetLibrary.delete_asset(path)
    package_path, name = path.rsplit("/", 1)
    factory = unreal.BlendSpaceFactory1D()
    factory.set_editor_property("target_skeleton", skeleton)
    bs = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, package_path, unreal.BlendSpace1D, factory)
    if bs is None:
        return _envelope("anim_create_blendspace_1d", False, errors=["create_asset returned None"])
    errors = []
    try:
        params = list(bs.get_editor_property("blend_parameters"))
        axis = params[0]
        axis.set_editor_property("display_name", args.get("axis_name", "Speed"))
        axis.set_editor_property("min", float(args.get("min", 0.0)))
        axis.set_editor_property("max", float(args.get("max", 600.0)))
        axis.set_editor_property("grid_num", int(args.get("grid", 4)))
        params[0] = axis
        bs.set_editor_property("blend_parameters", params)
    except Exception as exc:
        errors.append(f"axis: {type(exc).__name__}: {exc}")
    try:
        samples = []
        for spec in args.get("samples", []):
            sample = unreal.BlendSample()
            sample.set_editor_property("animation", unreal.EditorAssetLibrary.load_asset(spec["animation"]))
            sample.set_editor_property("sample_value", unreal.Vector(float(spec["value"]), 0.0, 0.0))
            samples.append(sample)
        bs.set_editor_property("sample_data", samples)
    except Exception as exc:
        errors.append(f"samples: {type(exc).__name__}: {exc}")
    # Property edits do not rebuild the runtime segments; without them the blend space evaluates to no samples.
    runtime = {}
    if hasattr(unreal, "GameForgeAnimationLibrary") and hasattr(unreal.GameForgeAnimationLibrary, "finalize_blend_space"):
        fin = json.loads(unreal.GameForgeAnimationLibrary.finalize_blend_space(bs.get_path_name()))
        runtime = fin.get("data", {})
        errors.extend(fin.get("errors", []))
    else:
        errors.append("GameForgeAnimationLibrary.finalize_blend_space unavailable (plugin build older than m10v2)")
    unreal.EditorAssetLibrary.save_loaded_asset(bs)
    rec = _blendspace_record(bs) | {"runtime": runtime}
    got = [s["value"] for s in rec.get("samples", [])]
    want = [round(float(s["value"]), 3) for s in args.get("samples", [])]
    if got != want:
        errors.append(f"sample read-back {got} != requested {want}")
    return _envelope("anim_create_blendspace_1d", not errors, rec, errors=errors, affected=[path],
                     reversibility="snapshot-only")


@op("anim_inspect_blendspace", reversibility="read-only")
def anim_inspect_blendspace(args):
    bs = unreal.EditorAssetLibrary.load_asset(args["blendspace_path"])
    if not isinstance(bs, unreal.BlendSpace):
        return _envelope("anim_inspect_blendspace", False, errors=["not a BlendSpace: " + args["blendspace_path"]])
    return _envelope("anim_inspect_blendspace", True, _blendspace_record(bs))


@op("anim_start_locomotion_test", mutates=True, reversibility="transient")
def anim_start_locomotion_test(args):
    if not hasattr(unreal, "GameForgeAnimationLibrary"):
        return _envelope("anim_start_locomotion_test", False, errors=["GameForgeAnimationLibrary not loaded in editor"])
    res = json.loads(unreal.GameForgeAnimationLibrary.start_locomotion_test(json.dumps(args)))
    return _envelope("anim_start_locomotion_test", res.get("ok", False), res.get("data", {}), errors=res.get("errors", []),
                     reversibility="transient")


@op("anim_locomotion_test_result", reversibility="read-only")
def anim_locomotion_test_result(args):
    res = json.loads(unreal.GameForgeAnimationLibrary.get_locomotion_test_result())
    return _envelope("anim_locomotion_test_result", res.get("ok", False), res.get("data", {}), errors=res.get("errors", []),
                     reversibility="read-only")


@op("character_measure_deformation", mutates=True, reversibility="transactional")
def character_measure_deformation(args):
    if not hasattr(unreal, "GameForgeCharacterLibrary"):
        return _envelope("character_measure_deformation", False, errors=["GameForgeCharacterLibrary not loaded in editor"])
    res = json.loads(unreal.GameForgeCharacterLibrary.measure_skin_deformation(json.dumps(args)))
    return _envelope("character_measure_deformation", res.get("ok", False), res.get("data", {}), errors=res.get("errors", []))


def _new_asset(name, folder, cls, factory):
    path = f"{folder}/{name}"
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        unreal.EditorAssetLibrary.delete_asset(path)
    return unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, folder, cls, factory)


@op("anim_ik_retarget", mutates=True, reversibility="snapshot-only")
def anim_ik_retarget(args):
    """Real IK retargeting: IK Rigs for source and target meshes (named chains), an IK Retargeter
    mapping chains by name, then IKRetargetBatchOperation.duplicate_and_retarget."""
    folder = args.get("destination_path", "/Game/Audit/Retarget")
    src_mesh = unreal.EditorAssetLibrary.load_asset(args["source_mesh"])
    tgt_mesh = unreal.EditorAssetLibrary.load_asset(args["target_mesh"])
    if not isinstance(src_mesh, unreal.SkeletalMesh) or not isinstance(tgt_mesh, unreal.SkeletalMesh):
        return _envelope("anim_ik_retarget", False, errors=["source_mesh/target_mesh must be SkeletalMesh assets"])
    rigs = {}
    errors = []
    for side, mesh, spec in (("Source", src_mesh, args["source_rig"]), ("Target", tgt_mesh, args["target_rig"])):
        rig = _new_asset(f"IK_{side}", folder, unreal.IKRigDefinition, unreal.IKRigDefinitionFactory())
        ctrl = unreal.IKRigController.get_controller(rig)
        if not ctrl.set_skeletal_mesh(mesh):
            errors.append(f"{side}: set_skeletal_mesh failed")
        if not ctrl.set_retarget_root(spec["root"]):
            errors.append(f"{side}: set_retarget_root({spec['root']}) failed")
        for chain, (start, end) in spec["chains"].items():
            if str(ctrl.add_retarget_chain(chain, start, end, "")) in ("", "None"):
                errors.append(f"{side}: chain {chain} ({start}->{end}) rejected")
        unreal.EditorAssetLibrary.save_loaded_asset(rig)
        rigs[side] = rig
    rtg = _new_asset("RTG_Audit", folder, unreal.IKRetargeter, unreal.IKRetargetFactory())
    rc = unreal.IKRetargeterController.get_controller(rtg)
    rc.set_ik_rig(unreal.RetargetSourceOrTarget.SOURCE, rigs["Source"])
    rc.set_ik_rig(unreal.RetargetSourceOrTarget.TARGET, rigs["Target"])
    rc.set_preview_mesh(unreal.RetargetSourceOrTarget.SOURCE, src_mesh)
    rc.set_preview_mesh(unreal.RetargetSourceOrTarget.TARGET, tgt_mesh)
    try:
        rc.add_default_ops()
        rc.assign_ik_rig_to_all_ops(unreal.RetargetSourceOrTarget.SOURCE, rigs["Source"])
        rc.assign_ik_rig_to_all_ops(unreal.RetargetSourceOrTarget.TARGET, rigs["Target"])
    except Exception as exc:  # older op-stack APIs
        errors.append(f"op stack setup: {exc}")
    rc.auto_map_chains(unreal.AutoMapChainType.EXACT, True)
    unreal.EditorAssetLibrary.save_loaded_asset(rtg)

    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    assets = [registry.get_asset_by_object_path(p) for p in args["animations"]]
    out = unreal.IKRetargetBatchOperation.duplicate_and_retarget(assets, src_mesh, tgt_mesh, rtg, "", "", "RTG_", "", False, True)
    created = []
    # duplicate_and_retarget takes no output folder and writes next to the project root; move the results
    # into destination_path so they land where the caller asked.
    for a in out:
        path = str(a.package_name)
        dest = f"{folder}/{path.rsplit('/', 1)[-1]}"
        if path != dest:
            if unreal.EditorAssetLibrary.does_asset_exist(dest):
                errors.append(f"destination already exists, left at {path}: {dest}")
            elif unreal.EditorAssetLibrary.rename_asset(path, dest):
                path = dest
            else:
                errors.append(f"could not move {path} to {dest}")
        created.append(path)
    tgt_skel = tgt_mesh.get_editor_property("skeleton")
    on_target = [p for p in created
                 if isinstance(unreal.EditorAssetLibrary.load_asset(p), unreal.AnimSequence)
                 and unreal.EditorAssetLibrary.load_asset(p).get_editor_property("skeleton") == tgt_skel]
    ok = bool(created) and len(on_target) == len(args["animations"]) and not errors
    return _envelope("anim_ik_retarget", ok, {"retargeter": rtg.get_path_name(), "created": created,
                                              "on_target_skeleton": on_target}, errors=errors)


@op("pie_character_diagnostics", reversibility="read-only")
def pie_character_diagnostics(args):
    """Movement + animation state of every ACharacter in the PIE world (read-only)."""
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world()
    if not world:
        return _envelope("pie_character_diagnostics", False, errors=["no PIE world"])
    out = []
    for ch in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Character):
        mv = ch.character_movement
        mesh = ch.get_editor_property("mesh")
        anim = mesh.get_anim_instance() if mesh else None
        v = mv.velocity
        a = mv.get_current_acceleration()
        entry = {"name": ch.get_name(), "location": [round(x, 1) for x in (ch.get_actor_location().x, ch.get_actor_location().y, ch.get_actor_location().z)],
                 "velocity": [round(v.x, 1), round(v.y, 1), round(v.z, 1)], "acceleration": [round(a.x, 1), round(a.y, 1), round(a.z, 1)],
                 "movement_mode": str(mv.movement_mode), "max_walk_speed": mv.max_walk_speed,
                 "controller": ch.get_controller().get_class().get_name() if ch.get_controller() else None,
                 "anim_instance": anim.get_class().get_name() if anim else None}
        if anim:
            for prop in ("idle_clip", "walk_clip", "run_clip"):
                try:
                    clip = anim.get_editor_property(prop)
                    entry[prop] = clip.get_path_name() if clip else None
                except Exception as exc:
                    entry[prop] = f"n/a ({exc})"
        out.append(entry)
    return _envelope("pie_character_diagnostics", True, {"characters": out}, reversibility="read-only")


@op("pie_view_from", mutates=True, reversibility="transient")
def pie_view_from(args):
    """Points the PIE player's view at a fixed camera (for framing evidence screenshots)."""
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world()
    if not world:
        return _envelope("pie_view_from", False, errors=["no PIE world"])
    pc = unreal.GameplayStatics.get_player_controller(world, 0)
    if pc is None:
        return _envelope("pie_view_from", False, errors=["no player controller in PIE"])
    if hasattr(unreal.GameplayStatics, "begin_deferred_actor_spawn_from_class"):
        xf = unreal.Transform(_vec(args["location"]), _rot(args["rotation"]), unreal.Vector(1, 1, 1))
        cam = unreal.GameplayStatics.begin_deferred_actor_spawn_from_class(world, unreal.CameraActor, xf)
        cam = unreal.GameplayStatics.finish_spawning_actor(cam, xf)
        pc.set_view_target_with_blend(cam, 0.0)
        return _envelope("pie_view_from", True, {"camera": cam.get_name(), "mode": "camera_actor"},
                         reversibility="transient")
    # UE 5.7 Python does not expose deferred spawning; move the player's pawn to the viewpoint instead (this
    # changes the pawn's position, so use it for evidence framing only).
    pawn = pc.get_controlled_pawn()
    if pawn is None:
        return _envelope("pie_view_from", False, errors=["no camera spawn API and no controlled pawn"])
    pawn.set_actor_location(_vec(args["location"]), False, True)
    pc.set_control_rotation(_rot(args["rotation"]))
    loc = pawn.get_actor_location()
    return _envelope("pie_view_from", True, {"mode": "pawn_teleport", "pawn": pawn.get_name(),
                                             "location": {"x": loc.x, "y": loc.y, "z": loc.z}},
                     warnings=["pawn moved to the viewpoint"], reversibility="transient")


@op("pcg_scatter", mutates=True, reversibility="snapshot-only")
def pcg_scatter(args):
    """Builds a PCG graph (Create Points Grid -> Static Mesh Spawner), places a PCG Volume and generates it.
    Grid sampling only; there is no Surface Sampler yet. Check the result with pcg_verify_authenticity."""
    folder = args.get("graph_folder", "/Game/Audit/PCG")
    graph = _new_asset(args.get("graph_name", "PCG_AuditScatter"), folder, unreal.PCGGraph, unreal.PCGGraphFactory())
    grid_node, grid = graph.add_node_of_type(unreal.PCGCreatePointsGridSettings)
    grid.set_editor_property("grid_extents", unreal.Vector(2000.0, 2000.0, 50.0))
    grid.set_editor_property("cell_size", unreal.Vector(200.0, 200.0, 100.0))
    spawner_node, spawner = graph.add_node_of_type(unreal.PCGStaticMeshSpawnerSettings)
    selector = spawner.get_editor_property("mesh_selector_parameters")
    entry = unreal.PCGMeshSelectorWeightedEntry()
    desc = entry.get_editor_property("descriptor")
    desc.set_editor_property("static_mesh", unreal.EditorAssetLibrary.load_asset(args.get("mesh", "/Engine/BasicShapes/Cone.Cone")))
    entry.set_editor_property("descriptor", desc)
    entry.set_editor_property("weight", 1)
    selector.set_editor_property("mesh_entries", [entry])
    edges = [graph.add_edge(grid_node, "Out", spawner_node, "In")]
    unreal.EditorAssetLibrary.save_loaded_asset(graph)

    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    center = args.get("center", {"x": 0, "y": 0, "z": 0})
    extent = args.get("extent", {"x": 3000, "y": 3000, "z": 2000})
    vol = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.PCGVolume, _vec(center))
    vol.set_actor_label(args.get("label", "GF_PCGScatter"))
    vol.set_actor_scale3d(unreal.Vector(extent["x"] / 100.0, extent["y"] / 100.0, extent["z"] / 100.0))
    comp = vol.get_component_by_class(unreal.PCGComponent)
    comp.set_graph(graph)
    comp.generate_local(True)
    return _envelope("pcg_scatter", all(e is not None for e in edges),
                     {"graph": graph.get_path_name(), "volume": vol.get_actor_label(), "generation_requested": True},
                     errors=[] if all(e is not None for e in edges) else ["PCG graph edge creation failed"])


def _pcg_value(value):
    """JSON → Unreal value for PCG settings props: {"__enum__": "Type.MEMBER"}, {"__struct__": "Type", field: ...}
    (recursive), {"x","y","z"} vectors; anything else unchanged."""
    if isinstance(value, dict) and "__enum__" in value:
        enum_name, member = value["__enum__"].split(".", 1)
        return getattr(getattr(unreal, enum_name), member)
    if isinstance(value, dict) and "__struct__" in value:
        struct = getattr(unreal, value["__struct__"])()
        for key, field in value.items():
            if key != "__struct__":
                struct.set_editor_property(key, _pcg_value(field))
        return struct
    if isinstance(value, dict) and set(value) == {"x", "y", "z"}:
        return _vec(value)
    return value


@op("pcg_build_graph", mutates=True, reversibility="snapshot-only")
def pcg_build_graph(args):
    """Builds a PCG graph from nodes [{id, settings, props, meshes}] and edges [{from, from_pin, to, to_pin}]
    ("input"/"output" name the graph's own IO nodes), places an unbounded-height PCG Volume and generates it.
    Example chain: PCGGetLandscapeSettings -> PCGSurfaceSamplerSettings -> PCGDensityFilterSettings ->
    PCGStaticMeshSpawnerSettings. Struct/enum props use _pcg_value's JSON forms. Verify with pcg_verify_authenticity."""
    folder, name = args["graph_path"].rsplit("/", 1)
    graph = _new_asset(name, folder, unreal.PCGGraph, unreal.PCGGraphFactory())
    nodes, errors = {"input": graph.get_input_node(), "output": graph.get_output_node()}, []
    for spec in args.get("nodes", []):
        cls = getattr(unreal, spec["settings"], None)
        if cls is None:
            errors.append(f"unknown PCG settings class {spec['settings']}")
            continue
        node, settings = graph.add_node_of_type(cls)
        for key, value in (spec.get("props") or {}).items():
            try:
                settings.set_editor_property(key, _pcg_value(value))
            except Exception as exc:
                errors.append(f"{spec['id']}.{key}: {exc}")
        if spec.get("meshes"):
            selector = settings.get_editor_property("mesh_selector_parameters")
            entries = []
            for m in spec["meshes"]:
                entry = unreal.PCGMeshSelectorWeightedEntry()
                desc = entry.get_editor_property("descriptor")
                desc.set_editor_property("static_mesh", unreal.EditorAssetLibrary.load_asset(m["mesh"]))
                entry.set_editor_property("descriptor", desc)
                entry.set_editor_property("weight", int(m.get("weight", 1)))
                entries.append(entry)
            selector.set_editor_property("mesh_entries", entries)
        nodes[spec["id"]] = node
    edges = []
    for e in args.get("edges", []):
        edge = graph.add_edge(nodes.get(e["from"]), e.get("from_pin", "Out"), nodes.get(e["to"]), e.get("to_pin", "In"))
        edges.append({**e, "ok": edge is not None})
        if edge is None:
            errors.append(f"edge failed: {e}")
    unreal.EditorAssetLibrary.save_loaded_asset(graph)
    center, extent = args.get("center", {"x": 0, "y": 0, "z": 0}), args.get("extent", {"x": 5000, "y": 5000, "z": 5000})
    label = args.get("label", "GF_PCGGraph")
    old = _find_actor(label)
    if old is not None:
        old.destroy_actor()
    vol = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.PCGVolume, _vec(center))
    vol.set_actor_label(label)
    vol.set_actor_scale3d(unreal.Vector(extent["x"] / 100.0, extent["y"] / 100.0, extent["z"] / 100.0))
    comp = vol.get_component_by_class(unreal.PCGComponent)
    if args.get("seed") is not None:
        comp.set_editor_property("seed", int(args["seed"]))
    comp.set_graph(graph)
    comp.generate_local(True)
    return _envelope("pcg_build_graph", not errors, {"graph": graph.get_path_name(), "volume": label, "edges": edges},
                     errors=errors, affected=[graph.get_path_name()], reversibility="snapshot-only")


@op("pcg_inspect", reversibility="read-only")
def pcg_inspect(args):
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    label = args.get("label", "GF_PCGScatter")
    total, comps, generating = 0, 0, False
    for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.PCGVolume):
        if actor.get_actor_label() != label:
            continue
        pcg = actor.get_component_by_class(unreal.PCGComponent)
        generating = False
        if pcg:
            try:
                generating = bool(pcg.get_editor_property('bGenerationInProgress'))
            except Exception:
                pass
        # In UE 5.7 PCG static mesh spawner creates components on the volume actor
        # Check both InstancedStaticMeshComponent and HierarchicalInstancedStaticMeshComponent
        for c in actor.get_components_by_class(unreal.InstancedStaticMeshComponent):
            comps += 1
            total += c.get_instance_count()
        # Also check all actors in world in case instances were spawned on a separate target actor
        if total == 0:
            for ismc in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor):
                for c in ismc.get_components_by_class(unreal.InstancedStaticMeshComponent):
                    if c.component_has_tag(pcg.get_fname() if pcg else 'PCG') or 'PCG' in c.get_name():
                        comps += 1
                        total += c.get_instance_count()
    return _envelope("pcg_inspect", total > 0, {"instances": total, "ism_components": comps, "generating": generating},
                     errors=[] if total > 0 else ["no PCG instances generated"], reversibility="read-only")


@op("pcg_verify_authenticity", reversibility="read-only")
def pcg_verify_authenticity(args):
    """Proves instances came from a PCG graph: lists the graph's node settings classes and counts only ISM
    components on the PCG volume that carry PCG's generated-component tag."""
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    label = args.get("label", "GF_PCGScatter")
    tag = args.get("generated_tag", "PCG Generated Component")
    for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.PCGVolume):
        if actor.get_actor_label() != label:
            continue
        pcg = actor.get_component_by_class(unreal.PCGComponent)
        graph, notes = None, []
        for getter in (lambda: pcg.get_graph(), lambda: pcg.get_editor_property("graph_instance").get_graph(),
                       lambda: pcg.get_editor_property("graph_instance").get_editor_property("graph"),
                       lambda: pcg.get_editor_property("graph")):
            try:
                graph = getter()
                if graph:
                    break
            except Exception as exc:  # accessor names differ between engine versions
                notes.append(f"{type(exc).__name__}: {exc}")
        nodes = []
        if graph:
            for node in graph.get_editor_property("nodes"):
                settings = node.get_settings()
                nodes.append(settings.get_class().get_name() if settings else "None")
        tagged, untagged, heights = [], [], []
        # Optional footprints [{center: [x, y], half: [hx, hy]}] (world XY boxes): count every instance inside.
        boxes = args.get("exclusion_boxes") or []
        inside = [0] * len(boxes)
        for c in actor.get_components_by_class(unreal.InstancedStaticMeshComponent):
            entry = {"name": c.get_name(), "class": c.get_class().get_name(), "instances": c.get_instance_count(),
                     "mesh": c.static_mesh.get_path_name() if c.static_mesh else None}
            is_pcg = c.component_has_tag(tag)
            (tagged if is_pcg else untagged).append(entry)
            if is_pcg:
                step = max(1, entry["instances"] // 200)
                for i in range(0, entry["instances"], step):
                    heights.append(c.get_instance_transform(i, True).translation.z)
                if boxes:
                    for i in range(entry["instances"]):
                        t = c.get_instance_transform(i, True).translation
                        for b, box in enumerate(boxes):
                            if abs(t.x - box["center"][0]) <= box["half"][0] and abs(t.y - box["center"][1]) <= box["half"][1]:
                                inside[b] += 1
        instances = sum(e["instances"] for e in tagged)
        if heights:
            mean = sum(heights) / len(heights)
            height_stats = {"sampled": len(heights), "min_z": round(min(heights), 1), "max_z": round(max(heights), 1),
                            "std_z": round((sum((h - mean) ** 2 for h in heights) / len(heights)) ** 0.5, 1)}
        else:
            height_stats = {"sampled": 0}
        ok = bool(graph) and instances > 0
        return _envelope("pcg_verify_authenticity", ok,
                         {"graph": graph.get_path_name() if graph else None, "node_settings": nodes,
                          "pcg_tagged_components": tagged, "untagged_ism_components": untagged,
                          "pcg_instances": instances, "instance_heights": height_stats,
                          "instances_inside_exclusion_boxes": inside if boxes else None,
                          "graph_accessor_notes": notes},
                         errors=[] if ok else ["no PCG-tagged instances on the volume"], reversibility="read-only")
    return _envelope("pcg_verify_authenticity", False, errors=[f"no PCGVolume labelled {label}"],
                     reversibility="read-only")


@op("nav_find_path", reversibility="read-only")
def nav_find_path(args):
    """Queries the real NavMesh (RecastNavMesh) for a path between two points."""
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if args.get("in_pie"):
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world() or world
    path = unreal.NavigationSystemV1.find_path_to_location_synchronously(world, _vec(args["start"]), _vec(args["end"]))
    pts = [[p.x, p.y, p.z] for p in (path.path_points if path else [])]
    length = sum(((b[0]-a[0])**2 + (b[1]-a[1])**2 + (b[2]-a[2])**2) ** 0.5 for a, b in zip(pts, pts[1:]))
    valid = bool(path) and path.is_valid() and not path.is_partial() and len(pts) >= 2
    return _envelope("nav_find_path", valid, {"points": len(pts), "length_cm": length, "partial": bool(path and path.is_partial()),
                                              "first": pts[0] if pts else None, "last": pts[-1] if pts else None},
                     errors=[] if valid else ["no complete NavMesh path"], reversibility="read-only")


@op("nav_rebuild", mutates=True, reversibility="transient")
def nav_rebuild(args):
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    unreal.SystemLibrary.execute_console_command(world, "RebuildNavigation")
    return _envelope("nav_rebuild", True, {"requested": True}, reversibility="transient")


@op("pie_move_player_to", mutates=True, reversibility="transient")
def pie_move_player_to(args):
    """Sends the PIE player's pawn along a NavMesh path (UAIBlueprintHelperLibrary::SimpleMoveToLocation)."""
    loc = args["location"]
    lib = unreal.GameForgeAnimationLibrary
    # UE's Python name for MovePIEPlayerTo depends on its acronym splitting; resolve it.
    names = [n for n in dir(lib) if "player" in n.lower() and "move" in n.lower()]
    if not names:
        return _envelope("pie_move_player_to", False, errors=["MovePIEPlayerTo not exposed; library has: "
                                                              + ", ".join(n for n in dir(lib) if not n.startswith("_"))])
    res = json.loads(getattr(lib, names[0])(json.dumps(loc)))
    return _envelope("pie_move_player_to", res.get("ok", False), res.get("data", {}), errors=res.get("errors", []),
                     reversibility="transient")


@op("landscape_height_at", reversibility="read-only")
def landscape_height_at(args):
    """Ground height under each [x, y] point (downward line trace against world-static geometry)."""
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    out = []
    for x, y in args.get("points", []):
        hit = unreal.SystemLibrary.line_trace_single(world, unreal.Vector(x, y, 50000), unreal.Vector(x, y, -50000),
                                                     unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, False, [],
                                                     unreal.DrawDebugTrace.NONE, True)
        parts = hit.to_tuple() if hit else None
        out.append(round(parts[4].z, 1) if parts and parts[0] else None)
    return _envelope("landscape_height_at", all(z is not None for z in out), {"heights": out},
                     errors=[] if all(z is not None for z in out) else ["some points hit nothing"])


_GENERATED_CLASSES = ("Landscape", "LandscapeStreamingProxy", "PCGVolume")


@op("world_clear_generated", mutates=True, reversibility="transactional")
def world_clear_generated(args):
    """Deletes generated content only. With `data_layer_asset` (World Partition levels), "generated" means
    membership of that Data Layer, so user actors are kept whatever their label (roadmap AD-7). Without it,
    the interim rule applies: labels with a generator prefix (default "GF_") plus generated landscape/PCG classes."""
    deleted, kept = [], []
    if args.get("data_layer_asset"):
        inst, err = _data_layer_instance(args["data_layer_asset"])
        if inst is None:
            return _envelope("world_clear_generated", False, errors=[err])
        # World Partition only has loaded cells in memory; iterating loaded actors would silently skip unloaded
        # generated actors. Use the actor descriptors (all actors), load exactly the layer's members, delete them.
        descs = _wp_actor_descs() or []
        layer_path = inst.get_asset().get_path_name()
        member_descs = [d for d in descs if layer_path in _desc_layers(d)]
        unreal.WorldPartitionBlueprintLibrary.load_actors([d.get_editor_property("guid") for d in member_descs])
        members = set(_dl_sub().get_actors_from_data_layer(inst))
        with unreal.ScopedEditorTransaction("GameForge world_clear_generated"):
            for actor in list(members):
                deleted.append(actor.get_actor_label())
                actor.destroy_actor()
        kept = [str(d.get_editor_property("label")) for d in descs if layer_path not in _desc_layers(d)]
        # Destroyed actors keep their descriptor (and external-actor file) until the level is saved; read back the
        # live layer instead, and report how many descriptor deletions the next save will commit.
        remaining = [a.get_actor_label() for a in _dl_sub().get_actors_from_data_layer(inst)]
        missed = len(member_descs) - len(deleted)
        ok = not remaining and missed <= 0
        return _envelope("world_clear_generated", ok,
                         {"deleted": deleted, "kept": kept, "rule": "data_layer", "members_by_descriptor": len(member_descs),
                          "descriptors_pending_save": len(deleted)},
                         errors=[] if ok else [f"still in layer: {remaining}; members not loaded/deleted: {max(missed, 0)}"],
                         reversibility="transactional")
    prefixes = tuple(args.get("prefixes", ["GF_"]))
    with unreal.ScopedEditorTransaction("GameForge world_clear_generated"):
        for actor in _actor_sub().get_all_level_actors():
            label, cls = actor.get_actor_label(), actor.get_class().get_name()
            if label.startswith(prefixes) or cls in _GENERATED_CLASSES:
                deleted.append(label)
                actor.destroy_actor()
            else:
                kept.append(label)
    remaining = [a.get_actor_label() for a in _actor_sub().get_all_level_actors()
                 if a.get_actor_label().startswith(prefixes) or a.get_class().get_name() in _GENERATED_CLASSES]
    return _envelope("world_clear_generated", not remaining, {"deleted": deleted, "kept": kept, "rule": "label_prefix"},
                     errors=[] if not remaining else [f"still present: {remaining}"], reversibility="transactional")


# ── World Partition Data Layers (generated-content ownership, roadmap AD-7) ──────────────────────────────

def _dl_sub():
    return unreal.get_editor_subsystem(unreal.DataLayerEditorSubsystem)


def _world_is_partitioned():
    world = unreal.EditorLevelLibrary.get_editor_world()
    try:
        return world.get_world_settings().get_editor_property("world_partition") is not None
    except Exception:
        return False


def _wp_actor_descs():
    """All actor descriptors of the editor world's World Partition (loaded or not; only saved actors have one);
    None if the world is not partitioned. In 5.7 Python the call returns the descriptor array itself."""
    if not _world_is_partitioned():
        return None
    res = unreal.WorldPartitionBlueprintLibrary.get_actor_descs()
    if isinstance(res, tuple):  # (bool, array) on engine versions that keep the return value
        res = next((x for x in res if not isinstance(x, bool)), [])
    return list(res)


def _desc_layers(desc):
    # str() of a SoftObjectPath struct is its repr; export_text() gives the "/Game/...Asset.Asset" path.
    return {p.export_text().strip("'\"") for p in desc.get_editor_property("data_layer_assets")}


def _data_layer_instance(asset_path):
    asset = unreal.EditorAssetLibrary.load_asset(asset_path)
    if not isinstance(asset, unreal.DataLayerAsset):
        return None, "not a DataLayerAsset: " + asset_path
    inst = _dl_sub().get_data_layer_instance(asset)
    return (inst, "") if inst else (None, "no instance of this Data Layer in the current (partitioned) world")


@op("datalayer_ensure", mutates=True, reversibility="snapshot-only")
def datalayer_ensure(args):
    """Creates (or reuses) a DataLayerAsset and its instance in the current World Partition level."""
    path = args["asset_path"]
    asset = unreal.EditorAssetLibrary.load_asset(path) if unreal.EditorAssetLibrary.does_asset_exist(path) else None
    if asset is None:
        folder, name = path.rsplit("/", 1)
        asset = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, folder, unreal.DataLayerAsset,
                                                                         unreal.DataLayerFactory())
        if asset is None:
            return _envelope("datalayer_ensure", False, errors=["could not create DataLayerAsset " + path])
        unreal.EditorAssetLibrary.save_loaded_asset(asset)
    inst = _dl_sub().get_data_layer_instance(asset)
    created = False
    if inst is None:
        params = unreal.DataLayerCreationParameters()
        params.set_editor_property("data_layer_asset", asset)
        inst = _dl_sub().create_data_layer_instance(params)
        created = inst is not None
    if inst is None:
        return _envelope("datalayer_ensure", False, errors=["create_data_layer_instance failed (is the level partitioned?)"])
    return _envelope("datalayer_ensure", True, {"asset_path": asset.get_path_name(), "instance": inst.get_name(),
                                                "created_instance": created}, affected=[path])


@op("datalayer_add_actors", mutates=True, reversibility="transactional")
def datalayer_add_actors(args):
    inst, err = _data_layer_instance(args["asset_path"])
    if inst is None:
        return _envelope("datalayer_add_actors", False, errors=[err])
    actors, missing = [], []
    for label in args["labels"]:
        a = _find_actor(label)
        (actors.append(a) if a is not None else missing.append(label))
    ok = bool(actors) and _dl_sub().add_actors_to_data_layer(actors, inst)
    members = {a.get_actor_label() for a in _dl_sub().get_actors_from_data_layer(inst)}
    not_in = [a.get_actor_label() for a in actors if a.get_actor_label() not in members]
    return _envelope("datalayer_add_actors", bool(ok) and not missing and not not_in,
                     {"added": len(actors) - len(not_in), "missing": missing, "not_in_layer_after": not_in},
                     errors=[] if (ok and not missing and not not_in) else ["read-back: some actors not in the layer"],
                     reversibility="transactional")


@op("datalayer_list_actors", reversibility="read-only")
def datalayer_list_actors(args):
    inst, err = _data_layer_instance(args["asset_path"])
    if inst is None:
        return _envelope("datalayer_list_actors", False, errors=[err])
    loaded = sorted(a.get_actor_label() for a in _dl_sub().get_actors_from_data_layer(inst))
    descs = _wp_actor_descs()
    if descs is None:
        return _envelope("datalayer_list_actors", True, {"instance": inst.get_name(), "actors": loaded, "source": "loaded"})
    # World Partition: membership from actor descriptors, so unloaded members are listed too.
    layer_path = inst.get_asset().get_path_name()
    labels = sorted(str(d.get_editor_property("label")) for d in descs if layer_path in _desc_layers(d))
    # Unsaved members have no descriptor yet; report them from the loaded set so nothing is missed.
    labels = sorted(set(labels) | set(loaded))
    return _envelope("datalayer_list_actors", True, {"instance": inst.get_name(), "actors": labels,
                                                     "loaded": loaded, "source": "actor_descriptors+loaded",
                                                     "descriptor_count": len(descs)})


@op("world_generation_digest", reversibility="read-only")
def world_generation_digest(args):
    """SHA-256 over the generated world: landscape heights sampled by line traces on a grid plus
    every HISM/ISM instance transform. Same seed must give the same digest."""
    import hashlib
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    h = hashlib.sha256()
    half = float(args.get("half_extent", 6000)); step = float(args.get("step", 500))
    heights = 0
    y = -half
    while y <= half:
        x = -half
        while x <= half:
            hit = unreal.SystemLibrary.line_trace_single(world, unreal.Vector(x, y, 50000), unreal.Vector(x, y, -50000),
                                                         unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, False, [],
                                                         unreal.DrawDebugTrace.NONE, True)
            z = hit.to_tuple()[4].z if hit and hit.to_tuple()[0] else None
            h.update(f"{x:.0f},{y:.0f},{'none' if z is None else f'{z:.1f}'};".encode())
            heights += 1
            x += step
        y += step
    instances = 0
    for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor):
        for c in actor.get_components_by_class(unreal.InstancedStaticMeshComponent):
            for i in range(c.get_instance_count()):
                t = c.get_instance_transform(i, True)
                l = t.translation
                h.update(f"{actor.get_actor_label()}:{l.x:.1f},{l.y:.1f},{l.z:.1f};".encode())
                instances += 1
    return _envelope("world_generation_digest", heights > 0, {"digest": h.hexdigest(), "height_samples": heights,
                                                              "instances": instances}, reversibility="read-only")


@op("anim_retarget_sequence", mutates=True, reversibility="snapshot-only")
def anim_retarget_sequence(args):
    if hasattr(unreal, "GameForgeAnimationLibrary"):
        res_raw = unreal.GameForgeAnimationLibrary.retarget_animation_sequence(json.dumps(args))
        res = json.loads(res_raw)
        return _envelope(
            "anim_retarget_sequence",
            res.get("ok", False),
            res.get("data", {}),
            errors=res.get("errors", []),
            reversibility="snapshot-only",
        )
    return _envelope("anim_retarget_sequence", False, errors=["GameForgeAnimationLibrary not loaded in editor"])


# ── Dispatcher ──────────────────────────────────────────────────────────────

def dispatch(request_json):
    try:
        req = json.loads(request_json)
        name = req.get("op")
        entry = _OPS.get(name)
        if entry is None:
            res = _envelope(name, False, errors=["unknown operation: %s" % name])
        else:
            err = _check_token(req.get("token"))
            if err:
                res = _envelope(name, False, errors=["unauthorized: " + err])
            else:
                res = entry["fn"](req.get("args") or {})
    except Exception as exc:  # never let an exception escape into the editor
        res = _envelope(locals().get("name"), False, errors=["%s: %s" % (type(exc).__name__, exc)],
                        warnings=[traceback.format_exc(limit=3)])
    line = RESULT_SENTINEL + json.dumps(res, default=str)
    print(line)
    return line
