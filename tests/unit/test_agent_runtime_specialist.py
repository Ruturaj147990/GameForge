"""Unit & Regression tests for Agent Runtime Specialist fixes (DEF-092 - DEF-098)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.gameforge_ide.backend.agent.code_verify import (
    extract_unified_diff,
    parse_diagnostics,
    propose_assistant_fix,
    run_code_repair_loop,
)
from src.gameforge_ide.backend.agent.context_manager import ContextManager
from src.gameforge_ide.backend.agent.plan_generator import PlanGenerator
from src.gameforge_ide.backend.agent.runtime import AgentRuntime
from src.gameforge_ide.backend.models import (
    AnimationSpec,
    AssetProvenanceRecord,
    CapabilityRecord,
    CapabilityRegistry,
    CharacterSpec,
    StaticMeshAssetSpec,
)
from src.gameforge_ide.backend.providers.hosted import (
    AnthropicProvider,
    GuardedProvider,
    HostedModel,
    HostedProfile,
    OpenAICompatibleHostedProvider,
)
from src.gameforge_ide.backend.providers.ollama_provider import OllamaProvider
from src.gameforge_ide.backend.security.boundary import BoundaryManager
from src.gameforge_ide.backend.tools.edit_tools import EditTools


# ── 1. DEF-092: Multi-Schema Tool Call Extraction & Argument Parsing ──────────

class DummySessionMgr:
    pass

class DummyRouter:
    pass


@pytest.fixture
def agent_runtime(tmp_path: Path) -> AgentRuntime:
    return AgentRuntime(
        workspace_root=tmp_path,
        session_manager=DummySessionMgr(),  # type: ignore
        model_router=DummyRouter(),  # type: ignore
    )


def test_extract_tool_call_gameforge_native(agent_runtime: AgentRuntime):
    raw = '```json\n{"tool": "propose_edit", "args": {"subpath": "Source/Player.cpp", "replacement_content": "int health = 100;"}}\n```'
    call = agent_runtime._extract_tool_call(raw)
    assert call is not None
    assert call["name"] == "propose_edit"
    assert call["arguments"]["subpath"] == "Source/Player.cpp"


def test_extract_tool_call_openai_tool_calls_array(agent_runtime: AgentRuntime):
    raw = json.dumps({
        "tool_calls": [
            {
                "id": "call_12345",
                "type": "function",
                "function": {
                    "name": "list_dir",
                    "arguments": '{"subpath": "Config", "max_depth": 1}',
                },
            }
        ]
    })
    call = agent_runtime._extract_tool_call(raw)
    assert call is not None
    assert call["name"] == "list_dir"
    assert call["arguments"] == {"subpath": "Config", "max_depth": 1}


def test_extract_tool_call_openai_single_function(agent_runtime: AgentRuntime):
    raw = '```json\n{"type": "function", "function": {"name": "read_file", "arguments": {"subpath": "Source/Game.h"}}}\n```'
    call = agent_runtime._extract_tool_call(raw)
    assert call is not None
    assert call["name"] == "read_file"
    assert call["arguments"]["subpath"] == "Source/Game.h"


def test_extract_tool_call_anthropic_tool_use(agent_runtime: AgentRuntime):
    raw = json.dumps({
        "type": "tool_use",
        "id": "toolu_01A",
        "name": "propose_edit",
        "input": {"subpath": "Source/Weapon.cpp", "target_content": "ammo = 10;", "replacement_content": "ammo = 30;"},
    })
    call = agent_runtime._extract_tool_call(raw)
    assert call is not None
    assert call["name"] == "propose_edit"
    assert call["arguments"]["replacement_content"] == "ammo = 30;"


def test_extract_tool_call_react_action(agent_runtime: AgentRuntime):
    raw = '{"action": "unreal_engine_info", "action_input": {}}'
    call = agent_runtime._extract_tool_call(raw)
    assert call is not None
    assert call["name"] == "unreal_engine_info"


def test_extract_tool_call_xml_tags(agent_runtime: AgentRuntime):
    xml_text = (
        "Let me inspect the directory:\n"
        "<tool_use>\n"
        "<name>list_dir</name>\n"
        "<arguments>{\"subpath\": \"Source\"}</arguments>\n"
        "</tool_use>"
    )
    call = agent_runtime._extract_tool_call(xml_text)
    assert call is not None
    assert call["name"] == "list_dir"
    assert call["arguments"]["subpath"] == "Source"


def test_extract_tool_call_xml_invoke_tags(agent_runtime: AgentRuntime):
    xml_text = (
        "<invoke name=\"read_file\">\n"
        "<parameter name=\"subpath\">Config/DefaultEngine.ini</parameter>\n"
        "</invoke>"
    )
    call = agent_runtime._extract_tool_call(xml_text)
    assert call is not None
    assert call["name"] == "read_file"
    assert call["arguments"]["subpath"] == "Config/DefaultEngine.ini"


def test_extract_tool_call_nested_balanced_braces(agent_runtime: AgentRuntime):
    raw = (
        "Here is the planned edit:\n"
        "```json\n"
        "{\n"
        '  "tool": "propose_edit",\n'
        '  "args": {\n'
        '    "subpath": "Nested/Path/Actor.cpp",\n'
        '    "replacement_content": "void Function() { if (true) { return; } }"\n'
        "  }\n"
        "}\n"
        "```\n"
        "This will resolve the logic error."
    )
    call = agent_runtime._extract_tool_call(raw)
    assert call is not None
    assert call["name"] == "propose_edit"
    assert "void Function()" in call["arguments"]["replacement_content"]


# ── 2. DEF-093: Tool Call Chat Suppression and Narrative Cleansing ────────────

def test_is_tool_call_start_detection():
    assert AgentRuntime._is_tool_call_start('{"tool": "propose_edit"')
    assert AgentRuntime._is_tool_call_start('{"name": "read_file"')
    assert AgentRuntime._is_tool_call_start('{"type": "tool_use"')
    assert AgentRuntime._is_tool_call_start('```json\n{"tool":')
    assert AgentRuntime._is_tool_call_start('<tool_use>\n<name>')
    assert AgentRuntime._is_tool_call_start('<invoke name="read_file">')
    # Normal prose should NOT be detected as tool call start
    assert not AgentRuntime._is_tool_call_start("Hello, I am GameForge assistant!")
    assert not AgentRuntime._is_tool_call_start("To create a game, we define rules in GDS.")


def test_clean_narrative_text():
    mixed = (
        "I will now create the player source file for you.\n\n"
        "```json\n"
        '{"tool": "propose_edit", "args": {"subpath": "Player.cpp"}}\n'
        "```"
    )
    cleaned = AgentRuntime._clean_narrative_text(mixed)
    assert "I will now create the player source file for you." in cleaned
    assert "```json" not in cleaned
    assert "propose_edit" not in cleaned


def test_clean_narrative_text_xml():
    mixed = (
        "Checking existing actors.\n"
        "<tool_use><name>list_dir</name><arguments>{}</arguments></tool_use>"
    )
    cleaned = AgentRuntime._clean_narrative_text(mixed)
    assert cleaned == "Checking existing actors."


# ── 3. DEF-094: Markdown Diff Extraction and Content Cleansing ────────────────

def test_extract_unified_diff_with_preamble_and_fences():
    model_output = (
        "Here is the unified diff to fix the syntax error:\n\n"
        "```diff\n"
        "--- a/Source/Game/Player.cpp\n"
        "+++ b/Source/Game/Player.cpp\n"
        "@@ -10,1 +10,1 @@\n"
        "-int health = 0;\n"
        "+int health = 100;\n"
        "```\n\n"
        "Please let me know if the build passes now!"
    )
    diff = extract_unified_diff(model_output)
    assert not diff.startswith("```")
    assert not diff.endswith("```")
    assert "Here is the unified diff" not in diff
    assert "Please let me know" not in diff
    assert diff.startswith("--- a/Source/Game/Player.cpp")
    assert "+int health = 100;" in diff


def test_propose_edit_strips_markdown_code_fences(tmp_path: Path):
    bm = BoundaryManager(tmp_path)
    et = EditTools(bm)

    wrapped_content = (
        "```cpp\n"
        "#include \"GameFramework/Actor.h\"\n"
        "int main() { return 0; }\n"
        "```"
    )
    res = et.propose_edit(subpath="Source/Main.cpp", replacement_content=wrapped_content)
    assert res["status"] == "PENDING_APPROVAL"
    diff_rec = et.pending_diffs[res["diff_id"]]
    assert "```cpp" not in diff_rec["new_text"]
    assert not diff_rec["new_text"].startswith("```")
    assert not diff_rec["new_text"].endswith("```\n")
    assert "#include \"GameFramework/Actor.h\"" in diff_rec["new_text"]
    assert "```cpp" not in res["diff_patch"]


# ── 4. DEF-095: Multi-Turn Conversation Compaction and Role Alternation ───────

def test_fit_history_to_context_contiguous_window_and_omitted_summary():
    system_prompt = "System instructions."
    messages = [
        {"role": "user", "content": f"Turn {i} question from user about gameplay mechanics with long code blocks and detailed context: " + "abc " * 30}
        if i % 2 == 0
        else {"role": "assistant", "content": f"Turn {i} answer with code explanation and implementation details: " + "def " * 30}
        for i in range(10)
    ]
    pinned = messages[-1]

    # Limit context budget so older messages are omitted
    selected, stats = AgentRuntime.fit_history_to_context(
        system_prompt=system_prompt,
        messages=messages,
        max_context=500,
        output_tokens=100,
        safety_tokens=50,
        pinned_message=pinned,
    )

    assert stats["omitted_history_messages"] > 0
    # Must preserve recency without holes
    assert len(selected) > 0
    # Must have summary of earlier turns
    has_summary = any("Earlier conversation compacted" in m.get("content", "") for m in selected)
    assert has_summary

    # Ensure alternating roles
    for idx in range(len(selected) - 1):
        assert selected[idx]["role"] != selected[idx + 1]["role"], "Consecutive messages must not share role"


def test_fit_history_to_context_fails_closed_on_overflow():
    system_prompt = "Large system prompt " * 200
    messages = [{"role": "user", "content": "Hello"}]
    with pytest.raises(ValueError, match="input budget for this model"):
        AgentRuntime.fit_history_to_context(
            system_prompt=system_prompt,
            messages=messages,
            max_context=100,  # Far too small
        )


# ── 5. DEF-096: Code Repair Loop Bounded Retries & Cycle Detection ─────────────

def test_run_code_repair_loop_success(tmp_path: Path):
    proj_dir = tmp_path / "TestProj"
    proj_dir.mkdir()
    source = proj_dir / "Source"
    source.mkdir()
    actor_cpp = source / "Actor.cpp"
    actor_cpp.write_text("int x = 1;\n", encoding="utf-8")

    diags_reported = [{"file": "Source/Actor.cpp", "line": 1, "message": "syntax error"}]
    build_pass = False

    def get_diags():
        nonlocal build_pass
        return diags_reported if not build_pass else []

    def apply_fix(fix):
        nonlocal build_pass
        build_pass = True
        return True

    def build_verify():
        return build_pass

    res = run_code_repair_loop(
        project_dir=proj_dir,
        diagnostics_fn=get_diags,
        apply_fix_fn=apply_fix,
        build_verify_fn=build_verify,
        max_attempts=3,
    )

    assert res["status"] == "SUCCESS"
    assert res["attempt"] == 1


def test_run_code_repair_loop_cycle_detection(tmp_path: Path):
    proj_dir = tmp_path / "TestProj"
    proj_dir.mkdir()
    source = proj_dir / "Source"
    source.mkdir()
    actor_cpp = source / "Actor.cpp"
    actor_cpp.write_text("int x = 1;\n", encoding="utf-8")

    diags = [{"file": "Source/Actor.cpp", "line": 1, "message": "unresolved symbol"}]

    def get_diags():
        return diags

    def apply_fix(fix):
        return True

    def build_verify():
        return False  # Build keeps failing

    # Mock caller that returns the identical diff every time
    mock_caller = MagicMock(return_value="--- a/Source/Actor.cpp\n+++ b/Source/Actor.cpp\n@@ -1,1 +1,1 @@\n-int x = 1;\n+int x = 2;")

    res = run_code_repair_loop(
        project_dir=proj_dir,
        diagnostics_fn=get_diags,
        apply_fix_fn=apply_fix,
        build_verify_fn=build_verify,
        model_caller=mock_caller,
        max_attempts=4,
    )

    # Must detect cycle on attempt 2 and halt without reaching attempt 4
    assert res["status"] == "BLOCKED"
    assert "Cyclic repair detected" in res["error"]
    assert res["attempt"] == 2


# ── 6. DEF-097: Ollama Provider Think: False and Capability Resolution ────────

def test_ollama_provider_get_capabilities():
    prov = OllamaProvider()
    cap_27b = prov.get_capabilities("gameforge-27b-sft:latest")
    assert cap_27b.supports_tools is True
    assert cap_27b.max_context == 32768

    cap_9b = prov.get_capabilities("gameforge-qwen3.5-9b")
    assert cap_9b.supports_tools is True
    assert cap_9b.max_context == 16384

    cap_default = prov.get_capabilities("custom-small")
    assert cap_default.supports_tools is True
    assert cap_default.max_context == 4096


def test_model_adapter_ollama_payload_enforces_think_false(monkeypatch):
    from src.gameforge_bench.model_adapter import invoke_candidate, ModelRequest
    captured_payload = {}

    class DummyResp:
        def read(self):
            return json.dumps({"response": "ok", "done": True}).encode("utf-8")
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def mock_urlopen(req, timeout=None):
        nonlocal captured_payload
        captured_payload = json.loads(req.data.decode("utf-8"))
        return DummyResp()

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    cand_config = {
        "candidate_id": "test_ollama",
        "runtime_type": "local_inference",
        "provider": "ollama",
        "model_name": "llama3.1:8b",
        "deployment": {"host": "127.0.0.1:11434"},
    }
    request = ModelRequest(
        task_id="t1",
        prompt="Create a game",
        system_prompt="System",
        max_tokens=500,
        temperature=0.2,
    )
    invoke_candidate(cand_config, request)

    assert captured_payload.get("think") is False
    assert captured_payload.get("options", {}).get("num_ctx") == 4096


# ── 7. DEF-098: Hosted Providers chat_with_tools Support ─────────────────────

def test_hosted_providers_have_chat_with_tools():
    profile = HostedProfile(
        provider_id="openai_test",
        kind="openai_compatible",
        base_url="https://api.openai.com/v1",
        models=[HostedModel(id="gpt-4o", display_name="GPT-4o", max_context=128000)],
    )
    openai_prov = OpenAICompatibleHostedProvider(profile)
    assert hasattr(openai_prov, "chat_with_tools")

    anthropic_prof = HostedProfile(
        provider_id="anthropic_test",
        kind="anthropic",
        base_url="https://api.anthropic.com/v1",
        models=[HostedModel(id="claude-3-5-sonnet", display_name="Claude 3.5 Sonnet", max_context=200000)],
    )
    anthropic_prov = AnthropicProvider(anthropic_prof)
    assert hasattr(anthropic_prov, "chat_with_tools")


def test_backend_models_package_exports():
    import src.gameforge_ide.backend.models as backend_models
    assert hasattr(backend_models, "CapabilityRecord")
    assert hasattr(backend_models, "CapabilityRegistry")
    assert hasattr(backend_models, "StaticMeshAssetSpec")
    assert hasattr(backend_models, "AnimationSpec")
    assert hasattr(backend_models, "CharacterSpec")
    assert hasattr(backend_models, "AssetProvenanceRecord")


# ── 8. Autonomous Engineering Assistant Execution & Planning ──────────────────

def test_parse_diagnostics_gcc_msvc_pytest():
    # 1. GCC / Clang
    gcc_out = "Source/Player.cpp:42:15: error: 'UHealthComponent' was not declared in this scope"
    diags = parse_diagnostics(gcc_out)
    assert len(diags) == 1
    assert diags[0]["file"] == "Source/Player.cpp"
    assert diags[0]["line"] == 42
    assert diags[0]["column"] == 15
    assert diags[0]["symbol"] == "UHealthComponent"

    # 2. MSVC
    msvc_out = "Source\\Weapon.cpp(88,4): error C2065: 'MaxAmmo': undeclared identifier"
    diags_m = parse_diagnostics(msvc_out)
    assert len(diags_m) == 1
    assert diags_m[0]["file"] == "Source/Weapon.cpp"
    assert diags_m[0]["line"] == 88
    assert diags_m[0]["symbol"] == "MaxAmmo"

    # 3. Pytest failure line
    pytest_out = "FAILED tests/unit/test_combat.py::test_damage_calc - AssertionError: 50 != 100"
    diags_p = parse_diagnostics(pytest_out)
    assert len(diags_p) == 1
    assert diags_p[0]["file"] == "tests/unit/test_combat.py"
    assert diags_p[0]["symbol"] == "test_damage_calc"


def test_engineering_plan_5_stage_dag_decomposition(tmp_path: Path):
    pg = PlanGenerator(tmp_path)
    plan = pg.generate_engineering_plan(
        goal="Implement stamina and sprinting system",
        target_files=["Source/Game/Player.cpp", "Source/Game/Player.h"],
        test_command="pytest tests/unit/test_stamina.py -q",
    )

    valid, errs = plan.validate()
    assert valid, f"DAG must be valid: {errs}"

    # Verify topological order follows the engineering chain:
    # step1_inspect -> step2_scaffold -> step3_implement -> step4_test -> step5_verify
    order = plan.get_topological_order()
    assert order == ["step1_inspect", "step2_scaffold", "step3_implement", "step4_test", "step5_verify"]

    # Verify dependencies
    assert plan.tasks["step1_inspect"].dependency_ids == []
    assert plan.tasks["step2_scaffold"].dependency_ids == ["step1_inspect"]
    assert plan.tasks["step3_implement"].dependency_ids == ["step2_scaffold"]
    assert plan.tasks["step4_test"].dependency_ids == ["step3_implement"]
    assert plan.tasks["step5_verify"].dependency_ids == ["step4_test"]


def test_plan_generator_prompt_multi_file_creates_engineering_plan(tmp_path: Path):
    pg = PlanGenerator(tmp_path)
    prompt = "Implement sprint ability in Source/Player.cpp and Source/Player.h with tests"
    plan = pg.generate_plan_from_prompt(prompt)

    assert plan.metadata.get("archetype") == "autonomous_engineering"
    assert len(plan.tasks) == 5
    order = plan.get_topological_order()
    assert "step1_inspect" in order
    assert "step4_test" in order


def test_context_manager_compact_conversation_history():
    history = [
        {"role": "user", "content": "Initial prompt: implement weapon system"},
        {"role": "assistant", "content": '{"tool": "list_dir", "args": {}}'},
        {"role": "user", "content": "[Observation for `list_dir`]:\n" + "file.cpp\n" * 50},
        {"role": "assistant", "content": '{"tool": "read_file", "args": {"subpath": "file.cpp"}}'},
        {"role": "user", "content": "[Observation for `read_file`]:\nint health = 100;\n" * 30},
        {"role": "assistant", "content": "I will now edit file.cpp"},
        {"role": "user", "content": "Please continue."},
    ]

    compacted = ContextManager.compact_conversation_history(history, preserve_recent=2)
    assert len(compacted) > 0
    # Older observations should be compacted to single-line summaries
    older_obs = [m["content"] for m in compacted if "[Tool `list_dir`:" in m.get("content", "")]
    assert len(older_obs) == 1
    assert "compacted for context" in older_obs[0]


def test_code_repair_loop_with_rollback_on_failure(tmp_path: Path):
    proj_dir = tmp_path / "Proj"
    proj_dir.mkdir()
    (proj_dir / "Source").mkdir()
    code_file = proj_dir / "Source" / "Code.cpp"
    code_file.write_text("int broken = 0;\n", encoding="utf-8")

    diags = [{"file": "Source/Code.cpp", "line": 1, "message": "fatal error: unresolved"}]
    rolled_back = False

    def get_diags():
        return diags

    def apply_fix(fix):
        return True

    def build_verify():
        return False  # Always fails to trigger exhaustion

    def mock_rollback():
        nonlocal rolled_back
        rolled_back = True
        return True

    res = run_code_repair_loop(
        project_dir=proj_dir,
        diagnostics_fn=get_diags,
        apply_fix_fn=apply_fix,
        build_verify_fn=build_verify,
        max_attempts=2,
        rollback_fn=mock_rollback,
    )

    assert res["status"] in ("EXHAUSTED", "FAILED", "BLOCKED")
    assert rolled_back is True


def test_runtime_proposes_test_command_predicate(agent_runtime: AgentRuntime):
    prompt = "Update Player.cpp and run pytest tests/unit/test_player.py"
    predicates = agent_runtime._propose_acceptance_predicates(prompt)
    types = [p.predicate_type for p in predicates]
    assert "file_exists" in types
    assert "file_changed" in types
    assert "command_exit_code" in types
    cmd_pred = next(p for p in predicates if p.predicate_type == "command_exit_code")
    assert "pytest tests/unit/test_player.py" in cmd_pred.target


# ── 9. Hardening: ReAct, Windows Paths, 5-Stage DAG & Narrative Excuses ───────

def test_parse_diagnostics_windows_paths_and_qualified_symbols():
    # 1. Windows GCC path with drive letter and qualified C++ namespace symbol
    gcc_win = "E:\\gameforge_step1\\Source\\Combat\\HealthComp.cpp:115:8: error: 'GF::FCombatStats' was not declared in this scope"
    diags_gcc = parse_diagnostics(gcc_win)
    assert len(diags_gcc) == 1
    assert "Source/Combat/HealthComp.cpp" in diags_gcc[0]["file"]
    assert diags_gcc[0]["line"] == 115
    assert diags_gcc[0]["symbol"] == "GF::FCombatStats"

    # 2. Windows MSVC path with drive letter
    msvc_win = "C:\\Projects\\GameForge\\Source\\Weapon.cpp(45,12): error C2065: 'MaxClipSize': undeclared identifier"
    diags_msvc = parse_diagnostics(msvc_win)
    assert len(diags_msvc) == 1
    assert "Source/Weapon.cpp" in diags_msvc[0]["file"]
    assert diags_msvc[0]["line"] == 45
    assert diags_msvc[0]["symbol"] == "MaxClipSize"

    # 3. Pytest with class name
    pytest_cls = "FAILED tests/unit/test_gameplay.py::TestInventory::test_stacking - AssertionError: assert 5 == 10"
    diags_py = parse_diagnostics(pytest_cls)
    assert len(diags_py) == 1
    assert diags_py[0]["file"] == "tests/unit/test_gameplay.py"
    assert diags_py[0]["symbol"] == "test_stacking"


def test_extract_tool_call_react_plain_text(agent_runtime: AgentRuntime):
    react_text = (
        "Thought: I need to inspect the Source directory to locate the weapon files.\n"
        "Action: list_dir\n"
        "Action Input: {\"subpath\": \"Source/Weapon\"}\n"
    )
    call = agent_runtime._extract_tool_call(react_text)
    assert call is not None
    assert call["name"] == "list_dir"
    assert call["arguments"] == {"subpath": "Source/Weapon"}


def test_extract_tool_call_anthropic_content_array(agent_runtime: AgentRuntime):
    anthropic_raw = json.dumps({
        "content": [
            {"type": "text", "text": "I will inspect the header file now."},
            {
                "type": "tool_use",
                "id": "toolu_abc123",
                "name": "read_file",
                "input": {"subpath": "Source/Player.h", "start_line": 1, "end_line": 50},
            },
        ]
    })
    call = agent_runtime._extract_tool_call(anthropic_raw)
    assert call is not None
    assert call["name"] == "read_file"
    assert call["arguments"]["subpath"] == "Source/Player.h"


def test_validate_engineering_dag(tmp_path: Path):
    pg = PlanGenerator(tmp_path)
    plan = pg.generate_engineering_plan(
        goal="Implement dash mechanic",
        target_files=["Source/Dash.cpp", "Source/Dash.h"],
    )
    valid, errs = PlanGenerator.validate_engineering_dag(plan)
    assert valid is True
    assert len(errs) == 0

    # Tamper with dependency to verify invalidation
    plan.tasks["step1_inspect"].dependency_ids = ["step5_verify"]
    invalid, errs = PlanGenerator.validate_engineering_dag(plan)
    assert invalid is False
    assert len(errs) > 0


def test_runtime_detects_narrative_excuses():
    assert AgentRuntime._is_narrative_excuse("I apologize, I am unable to modify this file due to an error.")
    assert AgentRuntime._is_narrative_excuse("I'm sorry, I cannot proceed with the requested changes.")
    assert AgentRuntime._is_narrative_excuse("Unfortunately, the build failed and I cannot continue.")
    # Productive explanations or normal instructions are NOT excuses
    assert not AgentRuntime._is_narrative_excuse("I will now inspect the directory and modify Player.cpp.")
    assert not AgentRuntime._is_narrative_excuse("Let me run pytest to verify zero regressions.")


def test_context_manager_compact_preserves_initial_goal_and_bounds_tokens():
    initial_user = {
        "role": "user",
        "content": "Goal: Implement multi-turn weapon system with parameters damage=50, ammo=100. Follow UE 5.7 rules.",
    }
    history = [initial_user]
    for i in range(10):
        history.append({"role": "assistant", "content": f"Turn {i} action: " + "inspecting files " * 20})
        history.append({"role": "user", "content": f"[Observation for `tool_{i}`]:\n" + "long observation data line\n" * 40})
    history.append({"role": "assistant", "content": "I am ready to write the code."})
    history.append({"role": "user", "content": "Please proceed with writing."})

    compacted = ContextManager.compact_conversation_history(history, max_tokens=600, preserve_recent=2)
    assert len(compacted) > 0
    # Initial goal and parameters must be preserved
    assert "Implement multi-turn weapon system with parameters" in compacted[0]["content"]
    # Recent prompt must be preserved
    assert any("Please proceed with writing" in m.get("content", "") for m in compacted)
    # Consecutive turns must strictly alternate roles
    for i in range(len(compacted) - 1):
        assert compacted[i]["role"] != compacted[i + 1]["role"]


def test_code_repair_loop_records_rolled_back_flag(tmp_path: Path):
    proj_dir = tmp_path / "ProjRollback"
    proj_dir.mkdir()
    (proj_dir / "Source").mkdir()
    (proj_dir / "Source" / "Bad.cpp").write_text("int broken;\n", encoding="utf-8")

    diags = [{"file": "Source/Bad.cpp", "line": 1, "message": "fatal compiler error"}]
    rolled_back = False

    def get_diags():
        return diags

    def apply_fix(fix):
        return True

    def build_verify():
        return False

    def mock_rollback():
        nonlocal rolled_back
        rolled_back = True
        return True

    res = run_code_repair_loop(
        project_dir=proj_dir,
        diagnostics_fn=get_diags,
        apply_fix_fn=apply_fix,
        build_verify_fn=build_verify,
        max_attempts=2,
        rollback_fn=mock_rollback,
    )

    assert res["status"] in ("EXHAUSTED", "FAILED", "BLOCKED")
    assert res.get("rolled_back") is True
    assert rolled_back is True
