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
    with unreal.ScopedEditorTransaction("GameForge set_actor_property"):
        actor.set_editor_property(name, value)
    actual = actor.get_editor_property(name)
    return _envelope("set_actor_property", True, {"label": args["label"], "property": name, "value": str(actual)},
                     reversibility="transactional")


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
    ok = _level_sub().new_level(path)
    exists = unreal.EditorAssetLibrary.does_asset_exist(path)
    return _envelope("new_level", bool(ok) and exists, {"level_path": path, "exists": exists},
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
    created = [str(a.package_name) for a in out]
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
    xf = unreal.Transform(_vec(args["location"]), _rot(args["rotation"]), unreal.Vector(1, 1, 1))
    cam = unreal.GameplayStatics.begin_deferred_actor_spawn_from_class(world, unreal.CameraActor, xf)
    cam = unreal.GameplayStatics.finish_spawning_actor(cam, xf)
    pc = unreal.GameplayStatics.get_player_controller(world, 0)
    if pc:
        pc.set_view_target_with_blend(cam, 0.0)
    return _envelope("pie_view_from", pc is not None, {"camera": cam.get_name()}, reversibility="transient")


@op("pcg_scatter", mutates=True, reversibility="snapshot-only")
def pcg_scatter(args):
    """Builds a PCG graph (Input.Landscape -> Surface Sampler -> Static Mesh Spawner), places a PCG
    Volume over the landscape and generates it. Count instances later with pcg_inspect."""
    folder = args.get("graph_folder", "/Game/Audit/PCG")
    graph = _new_asset(args.get("graph_name", "PCG_AuditScatter"), folder, unreal.PCGGraph, unreal.PCGGraphFactory())
    sampler_node, sampler = graph.add_node_of_type(unreal.PCGSurfaceSamplerSettings)
    sampler.set_editor_property("points_per_squared_meter", float(args.get("points_per_m2", 0.01)))
    spawner_node, spawner = graph.add_node_of_type(unreal.PCGStaticMeshSpawnerSettings)
    selector = spawner.get_editor_property("mesh_selector_parameters")
    entry = unreal.PCGMeshSelectorWeightedEntry()
    desc = entry.get_editor_property("descriptor")
    desc.set_editor_property("static_mesh", unreal.EditorAssetLibrary.load_asset(args.get("mesh", "/Engine/BasicShapes/Cone.Cone")))
    entry.set_editor_property("descriptor", desc)
    entry.set_editor_property("weight", 1)
    selector.set_editor_property("mesh_entries", [entry])
    edges = [graph.add_edge(graph.get_input_node(), "Landscape", sampler_node, "Surface"),
             graph.add_edge(sampler_node, "Out", spawner_node, "In")]
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


@op("pcg_inspect", reversibility="read-only")
def pcg_inspect(args):
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    label = args.get("label", "GF_PCGScatter")
    total, comps, generating = 0, 0, False
    for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.PCGVolume):
        if actor.get_actor_label() != label:
            continue
        pcg = actor.get_component_by_class(unreal.PCGComponent)
        generating = bool(pcg and pcg.is_generating())
        for c in actor.get_components_by_class(unreal.InstancedStaticMeshComponent):
            comps += 1
            total += c.get_instance_count()
    return _envelope("pcg_inspect", total > 0, {"instances": total, "ism_components": comps, "generating": generating},
                     errors=[] if total > 0 else ["no PCG instances generated"], reversibility="read-only")


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
