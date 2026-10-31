from gameforge_ide.unreal import op_catalog


def test_every_dispatcher_op_is_catalogued_with_readback():
    assert op_catalog.catalog_problems() == []


def test_mutating_op_without_readback_is_rejected(monkeypatch):
    bad = dict(op_catalog.CATALOG)
    bad["spawn_actor"] = op_catalog.OpSpec("spawn_actor", "level", "project")
    monkeypatch.setattr(op_catalog, "CATALOG", bad)
    assert any("spawn_actor" in p for p in op_catalog.catalog_problems())


def test_uncatalogued_op_is_reported():
    problems = op_catalog.catalog_problems(op_catalog.discover_ops() + ["brand_new_op"])
    assert "op 'brand_new_op' has no catalogue entry" in problems


def test_every_op_decorator_wraps_the_function_of_the_same_name():
    # A helper inserted between "@op(...)" and its def silently becomes the op (2026-10-31: pcg_build_graph
    # echoed its arguments back instead of building a graph).
    import re
    wrong = []
    for src in op_catalog.op_sources():
        lines = src.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            m = re.match(r'@op\("([^"]+)"', line)
            if m:
                nxt = next(l for l in lines[i + 1:] if l.strip() and not l.lstrip().startswith("@"))
                if not (nxt.startswith(f"def {m.group(1)}(") or nxt.startswith(f"def {m.group(1)}_op(")):
                    wrong.append((m.group(1), nxt.strip()))
    assert wrong == []


def test_agent_surface_comes_from_the_catalogue():
    from gameforge_ide.backend.tools.game_tools import AGENT_EDITOR_OPS, READ_ONLY_EDITOR_OPS
    assert READ_ONLY_EDITOR_OPS == op_catalog.read_only_ops()
    # Reads added after the old hand-kept list must no longer need approval.
    assert {"anim_inspect_sequence", "pcg_inspect", "material_readback_graph", "gameplay_objectives"} <= READ_ONLY_EDITOR_OPS
    assert not {"spawn_actor", "landscape_create", "metasound_build_source"} & READ_ONLY_EDITOR_OPS
    # Diagnostics and legacy ops are never offered to the model.
    assert "widget_trigger_delegate_diagnostic" not in AGENT_EDITOR_OPS
    assert "anim_retarget_sequence" not in AGENT_EDITOR_OPS
    assert {"pcg_build_graph", "sequence_build", "datalayer_ensure"} <= AGENT_EDITOR_OPS


def test_unreal_editor_tool_rejects_unknown_ops_before_dispatch(tmp_path):
    from gameforge_ide.backend.tools.game_tools import GameTools
    uproject = tmp_path / "P.uproject"
    uproject.write_text("{}")
    tools = GameTools.__new__(GameTools)  # no editor link is created for a rejected op
    for bad in ("make_whole_game", "anim_retarget_sequence"):
        res = tools.unreal_editor(str(uproject), bad, {})
        assert res["status"] == "ERROR" and "unknown or non-agent editor op" in res["error"]


def test_tool_schema_enumerates_agent_ops_and_reads_skip_approval(tmp_path):
    from gameforge_ide.backend.tools.gateway import ToolGateway
    gw = ToolGateway(tmp_path)
    tool = next(t for t in gw.get_definitions() if t.name == "unreal_editor")
    assert tool.parameters["properties"]["op"]["enum"] == op_catalog.agent_ops()
    assert "pcg_build_graph" in tool.description
    assert gw.tool_requires_approval("unreal_editor", {"op": "pcg_inspect"}) is False
    assert gw.tool_requires_approval("unreal_editor", {"op": "pcg_build_graph"}) is True


def test_markdown_lists_every_op():
    text = op_catalog.render_markdown()
    assert all(f"`{name}`" in text for name in op_catalog.CATALOG)


def test_ops_package_is_importable_offline():
    """P0 WI-0.6: the split package registers every op (fake ``unreal`` module, no editor)."""
    import importlib
    import sys
    import types

    class _Any:
        def __getattr__(self, name):
            if name.startswith("__"):  # keep inspect/pytest from unwrapping the fake forever
                raise AttributeError(name)
            return _Any()

        def __call__(self, *a, **k):
            return _Any()

    saved = {k: v for k, v in sys.modules.items() if k == "unreal" or k.startswith("gameforge_ops")}
    fake = types.ModuleType("unreal")
    def _mod_getattr(name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _Any()

    fake.__getattr__ = _mod_getattr
    sys.modules["unreal"] = fake
    sys.path.insert(0, str(op_catalog.OPS_SOURCE.parent))
    try:
        for k in [k for k in sys.modules if k.startswith("gameforge_ops")]:
            del sys.modules[k]
        pkg = importlib.import_module("gameforge_ops")
        assert len(pkg._OPS) == len(op_catalog.CATALOG) == 126
    finally:
        sys.path.remove(str(op_catalog.OPS_SOURCE.parent))
        for k in [k for k in sys.modules if k == "unreal" or k.startswith("gameforge_ops")]:
            del sys.modules[k]
        sys.modules.update(saved)
