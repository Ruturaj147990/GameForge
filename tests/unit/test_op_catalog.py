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


def test_markdown_lists_every_op():
    text = op_catalog.render_markdown()
    assert all(f"`{name}`" in text for name in op_catalog.CATALOG)
