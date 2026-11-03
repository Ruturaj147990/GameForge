"""GameForge in-editor operation library (runs inside UnrealEditor's embedded Python).

Every operation is a named function taking a JSON-compatible dict and returning the
Blueprint envelope: ok, op, data, warnings, errors, affected_paths, reversibility.

Rules enforced here (Master Blueprint v2, section 4):
  * Calls must carry the session token written by the GameForge supervisor to
    <Project>/Saved/GameForge/session.token. No token, no call (fail closed).
  * Level and property mutations run inside ScopedEditorTransaction (Blueprint graph edits use FScopedTransaction
    natively); asset-level mutations have no in-editor undo and rely on project checkpoints. The host reports
    the audited value per op (op_catalog.OpSpec.undo); envelopes' own reversibility fields may over-claim.
  * Every mutation returns read-back data queried from the editor after the write.
  * Assets are moved/created only through AssetTools / EditorAssetLibrary.

The host invokes ``dispatch(request_json)``; the result is printed as a single line
prefixed with RESULT_SENTINEL so the host can parse it from the command output.
"""

import json
import os
import traceback
import unreal


LIBRARY_VERSION = "2.1.0"


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
        "tags": [str(t) for t in getattr(actor, "tags", [])],
    }


def _load_class(class_path):
    if "." not in class_path and "/" not in class_path:
        cls = getattr(unreal, class_path, None)
        if cls is None and class_path.startswith("A"):
            cls = getattr(unreal, class_path[1:], None)
        if cls is not None:
            # Python wrapper types must be converted to the reflected UClass.
            return cls.static_class() if hasattr(cls, "static_class") else cls
        # Check GameForgeRuntime module
        cand_name = class_path[1:] if class_path.startswith("A") and len(class_path) > 1 else class_path
        gf_cls = unreal.load_class(None, f"/Script/GameForgeRuntime.{cand_name}")
        if gf_cls is not None:
            return gf_cls
        class_path = "/Script/Engine." + class_path
    cls = unreal.load_class(None, class_path)
    if cls is None and "/Script/GameForgeRuntime." not in class_path:
        stem = class_path.split("/")[-1].split(".")[-1]
        if stem.startswith("A") and len(stem) > 1:
            stem = stem[1:]
        cls = unreal.load_class(None, f"/Script/GameForgeRuntime.{stem}")
    if cls is None:
        bp = unreal.EditorAssetLibrary.load_blueprint_class(class_path)
        cls = bp
    return cls


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


def _exposure_record(vol):
    st = vol.get_editor_property("settings")
    return {"label": vol.get_actor_label(), "unbound": bool(vol.get_editor_property("unbound")),
            "method": _enum_name(st.get_editor_property("auto_exposure_method")),
            "bias": round(st.get_editor_property("auto_exposure_bias"), 3),
            "override_method": bool(st.get_editor_property("override_auto_exposure_method")),
            "override_bias": bool(st.get_editor_property("override_auto_exposure_bias"))}


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


_COLLISION_SHAPES = {"box": "BOX", "sphere": "SPHERE", "capsule": "CAPSULE", "convex": "NDOP26"}


_NIAGARA_TEMPLATES = "/Niagara/DefaultAssets/Templates"


def _vfx_lib():
    if not hasattr(unreal, "GameForgeVFXLibrary"):
        raise RuntimeError("GameForgeVFXLibrary not loaded (rebuild/install the plugin)")
    return unreal.GameForgeVFXLibrary


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


def _attenuation_record(att):
    st = att.get_editor_property("attenuation")
    ext = st.get_editor_property("attenuation_shape_extents")
    return {"path": att.get_path_name(), "spatialize": bool(st.get_editor_property("spatialize")),
            "attenuate": bool(st.get_editor_property("attenuate")),
            "inner_radius": round(ext.x, 2), "falloff_distance": round(st.get_editor_property("falloff_distance"), 2),
            "function": _enum_name(st.get_editor_property("distance_algorithm"))}


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


_MS_NODE_HANDLES = {}


def _binding_id(seq, binding):
    for getter in (lambda: seq.get_portable_binding_id(seq, binding), lambda: seq.get_binding_id(binding),
                   lambda: unreal.MovieSceneSequenceExtensions.get_binding_id(seq, binding)):
        try:
            return getter()
        except Exception:
            continue
    raise RuntimeError("no binding-id accessor on this engine version")


def _section_range(section):
    return [section.get_start_frame(), section.get_end_frame()]


_MRQ_JOB = {}


_PERF_COMMANDS = ("csvprofile start", "csvprofile stop", "stat unit", "stat fps", "stat none")


def _csv_dir():
    return os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()), "Profiling", "CSV")


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


def _new_asset(name, folder, cls, factory):
    path = f"{folder}/{name}"
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        unreal.EditorAssetLibrary.delete_asset(path)
    return unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, folder, cls, factory)


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


_GENERATED_CLASSES = ("Landscape", "LandscapeStreamingProxy", "PCGVolume")


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



__all__ = ['LIBRARY_VERSION', 'RESULT_SENTINEL', '_AUDIO_COMPONENTS', '_COLLISION_SHAPES', '_GENERATED_CLASSES', '_MRQ_JOB', '_MS_NODE_HANDLES', '_NIAGARA_TEMPLATES', '_OPS', '_PERF_COMMANDS', '_READBACK_PROPERTIES', '_SAMPLERS', '_TEXTURE_ROLES', '_active_log_path', '_actor_record', '_actor_sub', '_append_part', '_attenuation_record', '_binding_id', '_blendspace_record', '_check_token', '_configure_fbx_skeletal_import', '_csv_dir', '_data_layer_instance', '_desc_layers', '_dl_sub', '_enum_name', '_envelope', '_exposure_record', '_expr_props', '_expr_summary', '_find_actor', '_gs', '_gs_transform', '_level_sub', '_load_asset_pie_safe', '_load_class', '_lod_triangles', '_lod_triangles_via_geometry_script', '_log_since', '_log_size', '_ms_class', '_ms_graph_spec_check', '_ms_ok', '_new_asset', '_pcg_value', '_pie_world', '_rot', '_section_range', '_sm_sub', '_sound_record', '_state_value', '_static_mesh_record', '_texture_record', '_token_path', '_triangles', '_vec', '_vfx_lib', '_world_is_partitioned', '_wp_actor_descs', 'dispatch', 'feature_detect', 'op']
