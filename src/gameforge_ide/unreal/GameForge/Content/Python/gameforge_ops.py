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
    ok = unreal.EditorAssetLibrary.delete_asset(path)
    gone = not unreal.EditorAssetLibrary.does_asset_exist(path)
    return _envelope("delete_asset", bool(ok) and gone, {"asset_path": path, "deleted": gone},
                     affected=[path], reversibility="snapshot-only")


@op("viewport_screenshot")
def viewport_screenshot(args):
    out = args["output_path"]
    res = args.get("resolution", [1280, 720])
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
