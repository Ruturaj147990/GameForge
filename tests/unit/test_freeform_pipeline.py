"""Offline tests for free-form authoring: parsing, safety gate, titles, framework, proposals, repair loop."""

from pathlib import Path

import pytest

from src.gameforge_ide.backend.tools.game_tools import GameTools
from src.gameforge_ide.pipeline.authoring import parse_files, safety_scan
from src.gameforge_ide.pipeline.freeform import FREEFORM_STAGES, FreeformGamePipeline, derive_title, pascal
from tests.fixtures.legacy_recipes.freeform_host.framework import api_doc, framework_sources, reference_impl

GOOD_H = '#pragma once\n#include "CoreMinimal.h"\n#include "GFGameBase.h"\n#include "GFGameImpl.generated.h"\nUCLASS()\nclass X_API AGFGameImpl : public AGFGameBase { GENERATED_BODY() public: virtual bool RunSelfTest(FString& R) override; };\n'
GOOD_CPP = '#include "GFGameImpl.h"\nbool AGFGameImpl::RunSelfTest(FString& R) { return true; }\n'


def test_parse_file_blocks_and_fenced_fallback():
    text = f"blah\n=== FILE: GFGameImpl.h ===\n{GOOD_H}=== END FILE ===\n=== FILE: GFGameImpl.cpp ===\n```cpp\n{GOOD_CPP}```\n=== END FILE ===\n=== FILE: Evil.cpp ===\nx\n=== END FILE ==="
    files = parse_files(text)
    assert set(files) == {"GFGameImpl.h", "GFGameImpl.cpp"}  # unexpected files are dropped
    assert not files["GFGameImpl.cpp"].startswith("```")
    fenced = parse_files(f"**GFGameImpl.h**\n```cpp\n{GOOD_H}```\n\nGFGameImpl.cpp:\n```cpp\n{GOOD_CPP}```")
    assert set(fenced) == {"GFGameImpl.h", "GFGameImpl.cpp"}


@pytest.mark.parametrize("snippet,why", [
    ("system(\"del /q *\");", "process"), ("FPlatformProcess::CreateProc(", "process"),
    ("IFileManager::Get().Delete(", "file"), ("FHttpModule::Get()", "network"),
    ("FPlatformMisc::RequestExit(true);", "process control"),
])
def test_safety_scan_blocks_dangerous_code(snippet, why):
    issues = safety_scan({"GFGameImpl.h": GOOD_H, "GFGameImpl.cpp": GOOD_CPP + snippet})
    assert any(why in i for i in issues)


def test_safety_scan_accepts_clean_code_and_requires_contract():
    assert safety_scan({"GFGameImpl.h": GOOD_H, "GFGameImpl.cpp": GOOD_CPP}) == []
    issues = safety_scan({"GFGameImpl.h": "class A {};", "GFGameImpl.cpp": "int x;"})
    assert any("generated.h" in i for i in issues) and any("RunSelfTest" in i for i in issues)


@pytest.mark.parametrize("prompt,title", [
    ("create a whack-a-mole game in unreal engine", "Whack A Mole"),
    ("build me an endless runner game in unreal engine 5", "Endless Runner"),
    ("create a game called Star Hopper with jumping", "Star Hopper"),
])
def test_derive_title(prompt, title):
    assert derive_title(prompt) == title
    assert pascal(title).isalnum()


def test_framework_sources_are_project_specific():
    files = framework_sources("Demo", 'Bad "Title"\\')
    joined = "\n".join(files.values())
    assert "DEMO_API" in joined and "__API__" not in joined
    assert 'TEXT("Bad Title")' in files["Source/Demo/GFTitle.h"]
    assert "CaptureEvidence" in files["Source/Demo/GFHost.cpp"]
    assert "bAutoManageActiveCameraTarget = false" in files["Source/Demo/GFHost.cpp"]
    impl = reference_impl("Demo")
    assert safety_scan({Path(k).name: v for k, v in impl.items()}) == []
    assert "DEMO_API" in api_doc("Demo")


def test_unmatched_game_prompt_proposes_freeform(tmp_path):
    from unittest.mock import patch
    from src.gameforge_ide.design.prompt_to_gds import PromptToGdsResult
    with patch("src.gameforge_ide.backend.tools.game_tools.prompt_to_gds", return_value=PromptToGdsResult(status="ERROR", gds=None)):
        rec = GameTools(tmp_path, projects_root=tmp_path / "Games").propose_create_game("create a whack-a-mole game")
        assert rec["tool"] == "create_game_freeform" and rec["stages"] == FREEFORM_STAGES
    assert "Experimental" in rec["consequence"] and rec["args"]["title"] == "Whack A Mole"


class _FakeAuthor:
    """Scripted model: first answer fails to compile, the repair answer compiles."""

    def __init__(self):
        self.calls = 0
        self.prompts = []

    def describe(self):
        return "fake"

    def complete(self, system, messages, label, max_tokens=0):
        self.calls += 1
        self.prompts.append((label, messages[-1]["content"]))
        if label.startswith("build_fix"):
            return f"=== FILE: GFGameImpl.h ===\n{GOOD_H}=== END FILE ===\n=== FILE: GFGameImpl.cpp ===\n{GOOD_CPP}=== END FILE ==="
        return "design"


def test_repair_feeds_diagnostics_and_rewrites_files(tmp_path):
    src = tmp_path / "Source" / "X"
    src.mkdir(parents=True)
    (src / "GFGameImpl.h").write_text("broken", encoding="utf-8")
    (src / "GFGameImpl.cpp").write_text("broken", encoding="utf-8")
    pipe = FreeformGamePipeline(tmp_path, tmp_path)
    author = _FakeAuthor()
    ok = pipe._repair(author, src, "X", {}, "The build failed. Compiler diagnostics:\n- error C2065 ...", "build_fix_0")
    assert ok and (src / "GFGameImpl.cpp").read_text(encoding="utf-8") == GOOD_CPP
    assert "C2065" in author.prompts[0][1] and "broken" in author.prompts[0][1]


def test_repair_rejects_unsafe_fix(tmp_path):
    src = tmp_path / "S"
    src.mkdir()
    (src / "GFGameImpl.h").write_text(GOOD_H, encoding="utf-8")
    (src / "GFGameImpl.cpp").write_text(GOOD_CPP, encoding="utf-8")

    class Evil(_FakeAuthor):
        def complete(self, *a, **k):
            return f"=== FILE: GFGameImpl.h ===\n{GOOD_H}=== END FILE ===\n=== FILE: GFGameImpl.cpp ===\n{GOOD_CPP}system(\"x\");\n=== END FILE ==="

    assert FreeformGamePipeline(tmp_path, tmp_path)._repair(Evil(), src, "X", {}, "p", "build_fix_0") is False
    assert (src / "GFGameImpl.cpp").read_text(encoding="utf-8") == GOOD_CPP  # unchanged
