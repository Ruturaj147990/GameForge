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
    lines = op_catalog.OPS_SOURCE.read_text(encoding="utf-8").splitlines()
    wrong = []
    for i, line in enumerate(lines):
        m = re.match(r'@op\("([^"]+)"', line)
        if m:
            nxt = next(l for l in lines[i + 1:] if l.strip() and not l.lstrip().startswith("@"))
            if not (nxt.startswith(f"def {m.group(1)}(") or nxt.startswith(f"def {m.group(1)}_op(")):
                wrong.append((m.group(1), nxt.strip()))
    assert wrong == []


def test_markdown_lists_every_op():
    text = op_catalog.render_markdown()
    assert all(f"`{name}`" in text for name in op_catalog.CATALOG)
