from __future__ import annotations

import json
from pathlib import Path

from rac_core.demo.llm_planner import LLMPlanFixture, ReplayLLMPlanner

REPO_ROOT = Path(__file__).resolve().parents[1]
PLAN_DIR = REPO_ROOT / "examples" / "llm_plans"
RAW_DIR = REPO_ROOT / "examples" / "llm_raw_outputs"

FORBIDDEN_STEP = {
    "action",
    "purpose",
    "purpose_scope",
    "verified_anchor",
    "basis",
    "decision",
    "resource_origin",
    "output_anchor",
}

FORBIDDEN_RAW_SUBSTRINGS = (
    "DEEPSEEK_API_KEY",
    "Authorization",
    "Bearer",
    "sk-",
)


def test_all_llm_plan_fixtures_have_provenance() -> None:
    for path in sorted(PLAN_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data.get("recorded_from") or data.get("provider")
        assert data.get("model")
        assert data.get("raw_output_file")
        assert data.get("prompt_file")
        prompt_path = REPO_ROOT / data["prompt_file"]
        assert prompt_path.is_file(), f"missing prompt: {prompt_path}"
        raw_path = REPO_ROOT / data["raw_output_file"]
        assert raw_path.is_file(), f"missing raw output: {raw_path}"
        LLMPlanFixture.model_validate(data)


def test_llm_plan_steps_are_security_minimal() -> None:
    for path in sorted(PLAN_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for step in data["steps"]:
            assert set(step.keys()) <= {"tool_name", "arguments"}
            for fk in FORBIDDEN_STEP:
                assert fk not in step
            for ak in step.get("arguments", {}):
                assert ak not in FORBIDDEN_STEP


def test_raw_outputs_do_not_contain_api_key() -> None:
    for path in sorted(RAW_DIR.glob("*.json")):
        text = path.read_text(encoding="utf-8")
        for needle in FORBIDDEN_RAW_SUBSTRINGS:
            assert needle not in text, f"{path.name} must not contain {needle!r}"


def test_raw_outputs_include_raw_content_and_parsed() -> None:
    for path in sorted(RAW_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "raw_content" in data and isinstance(data["raw_content"], str)
        assert data.get("parsed") and isinstance(data["parsed"], dict)
        assert isinstance(data["parsed"].get("steps"), list)


def test_replay_planner_still_runs_with_provenance_fields() -> None:
    planner = ReplayLLMPlanner(PLAN_DIR)
    for name in planner.list_scenarios():
        calls = planner.plan(name)
        assert calls and all(c.tool_name for c in calls)


def test_llm_prompts_do_not_include_expected_plan() -> None:
    prompt_dir = REPO_ROOT / "examples" / "llm_prompts"
    forbidden = (
        "Expected plan",
        "Expected decision",
        "Expected rule",
    )
    required = (
        "Available tools",
        "Return only valid JSON",
        "Task:",
    )
    for path in sorted(prompt_dir.glob("*.txt")):
        text = path.read_text(encoding="utf-8")
        lower = text.lower()
        for phrase in forbidden:
            assert phrase.lower() not in lower, f"{path.name} must not contain {phrase!r}"
        for needle in required:
            assert needle in text, f"{path.name} must contain {needle!r}"


def test_benign_fixture_no_free_text_selected_purpose() -> None:
    path = PLAN_DIR / "benign_read_summarize.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for step in data["steps"]:
        if step["tool_name"] == "summarize_file":
            assert step["arguments"].get("selected_purpose") != "internal report"
            assert "internal report" not in json.dumps(step["arguments"])


def test_recorded_forged_predecessor_fixture_is_canonical() -> None:
    path = PLAN_DIR / "forged_predecessor.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    summ = next(s for s in data["steps"] if s["tool_name"] == "summarize_file")
    assert summ["arguments"]["input_anchor"] == "out:fake"
    mro = summ["arguments"].get("malicious_resource_override")
    assert mro is None or mro != "out:fake"


def test_recorded_resource_expansion_fixture_is_canonical() -> None:
    path = PLAN_DIR / "resource_expansion_file_b.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    summ = next(s for s in data["steps"] if s["tool_name"] == "summarize_file")
    assert summ["arguments"]["input_anchor"] == "previous"
    assert summ["arguments"].get("malicious_resource_override") == "file_B"
