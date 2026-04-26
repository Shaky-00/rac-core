from __future__ import annotations

import json
from pathlib import Path

import pytest

from rac_core.demo.deepseek_record import (
    ALL_SCENARIOS,
    build_replay_fixture_dict,
    canonicalize_plan_for_replay,
    canonicalize_steps_for_replay,
    dry_run_record,
    parse_llm_json_raw_content,
    validate_parsed_steps,
)
from rac_core.demo.llm_planner import LLMPlanFixture

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_dry_run_does_not_require_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    lines, paths = dry_run_record(REPO_ROOT, "benign_read_summarize")
    assert any("dry-run" in line for line in lines)
    assert paths and all(Path(p).suffix in (".txt", ".json") for p in paths)


def test_parse_json_content_plain() -> None:
    inner = {"steps": [{"tool_name": "read_file", "arguments": {"file_id": "file_A"}}]}
    raw = json.dumps(inner)
    assert parse_llm_json_raw_content(raw) == inner


def test_parse_json_content_fenced() -> None:
    inner = {"steps": [{"tool_name": "read_file", "arguments": {"file_id": "file_A"}}]}
    raw = "```json\n" + json.dumps(inner) + "\n```"
    assert parse_llm_json_raw_content(raw) == inner


def test_validate_steps_rejects_security_fields() -> None:
    bad = {
        "steps": [
            {"tool_name": "read_file", "arguments": {"file_id": "file_A"}, "action": "read"},
        ]
    }
    with pytest.raises(ValueError, match="forbidden"):
        validate_parsed_steps(bad)


def test_build_plan_fixture_from_raw_roundtrip() -> None:
    raw_inner = {
        "steps": [
            {"tool_name": "read_file", "arguments": {"file_id": "file_A"}},
            {"tool_name": "summarize_file", "arguments": {"input_anchor": "previous"}},
        ]
    }
    raw_content = json.dumps(raw_inner)
    parsed = parse_llm_json_raw_content(raw_content)
    steps = validate_parsed_steps(parsed)
    doc = build_replay_fixture_dict(
        "benign_read_summarize",
        steps=steps,
        prompt_file="examples/llm_prompts/benign_read_summarize.txt",
        raw_output_file="examples/llm_raw_outputs/benign_read_summarize.json",
        recorded_from="test",
        provider="test",
        model="unit",
        notes="unit test",
    )
    fx = LLMPlanFixture.model_validate(doc)
    assert fx.expected_decision is not None
    assert fx.raw_output_file.endswith(".json")
    assert fx.prompt_file.endswith(".txt")


def test_all_scenarios_have_oracle() -> None:
    assert set(ALL_SCENARIOS) == {
        "benign_read_summarize",
        "action_escalation_external_email",
        "resource_expansion_file_b",
        "forged_predecessor",
        "purpose_drift",
    }


def test_internal_report_selected_purpose_removed_for_benign() -> None:
    parsed = {
        "steps": [
            {"tool_name": "read_file", "arguments": {"file_id": "file_A"}},
            {
                "tool_name": "summarize_file",
                "arguments": {
                    "input_anchor": "previous",
                    "selected_purpose": "internal report",
                },
            },
        ]
    }
    out = canonicalize_plan_for_replay(scenario_name="benign_read_summarize", parsed=parsed)
    summ = out["steps"][1]
    assert "selected_purpose" not in summ["arguments"]


def test_external_sharing_selected_purpose_canonicalized_for_purpose_drift() -> None:
    parsed = {
        "steps": [
            {"tool_name": "read_file", "arguments": {"file_id": "file_A"}},
            {
                "tool_name": "summarize_file",
                "arguments": {
                    "input_anchor": "previous",
                    "selected_purpose": "external sharing",
                },
            },
        ]
    }
    out = canonicalize_plan_for_replay(scenario_name="purpose_drift", parsed=parsed)
    assert out["steps"][1]["arguments"]["selected_purpose"] == "external_sharing"


def test_unknown_selected_purpose_rejected() -> None:
    parsed = {
        "steps": [
            {"tool_name": "read_file", "arguments": {"file_id": "file_A"}},
            {
                "tool_name": "summarize_file",
                "arguments": {
                    "input_anchor": "previous",
                    "selected_purpose": "random purpose",
                },
            },
        ]
    }
    with pytest.raises(ValueError, match="Unknown selected_purpose"):
        canonicalize_steps_for_replay("benign_read_summarize", validate_parsed_steps(parsed))


def test_purpose_drift_rejects_internal_selected_purpose() -> None:
    parsed = {
        "steps": [
            {"tool_name": "read_file", "arguments": {"file_id": "file_A"}},
            {
                "tool_name": "summarize_file",
                "arguments": {
                    "input_anchor": "previous",
                    "selected_purpose": "internal report",
                },
            },
        ]
    }
    with pytest.raises(ValueError, match="purpose_drift scenario requires external"):
        canonicalize_plan_for_replay(scenario_name="purpose_drift", parsed=parsed)


def test_forged_predecessor_out_fake_normalized_to_input_anchor() -> None:
    base = {
        "steps": [
            {"tool_name": "read_file", "arguments": {"file_id": "file_A"}},
            {
                "tool_name": "summarize_file",
                "arguments": {
                    "input_anchor": "previous",
                    "malicious_resource_override": "out:fake",
                },
            },
        ]
    }
    out = canonicalize_steps_for_replay(
        "forged_predecessor", validate_parsed_steps(base)
    )
    summ = out[1]["arguments"]
    assert summ["input_anchor"] == "out:fake"
    assert "malicious_resource_override" not in summ

    via_anchor_id = {
        "steps": [
            {"tool_name": "read_file", "arguments": {"file_id": "file_A"}},
            {"tool_name": "summarize_file", "arguments": {"anchor_id": "out:fake"}},
        ]
    }
    out2 = canonicalize_steps_for_replay(
        "forged_predecessor", validate_parsed_steps(via_anchor_id)
    )
    assert out2[1]["arguments"]["input_anchor"] == "out:fake"
    assert "anchor_id" not in out2[1]["arguments"]


def test_forged_predecessor_without_out_fake_rejected() -> None:
    parsed = {
        "steps": [
            {"tool_name": "read_file", "arguments": {"file_id": "file_A"}},
            {
                "tool_name": "summarize_file",
                "arguments": {"input_anchor": "previous"},
            },
        ]
    }
    with pytest.raises(ValueError, match="forged_predecessor plan must reference"):
        canonicalize_steps_for_replay(
            "forged_predecessor", validate_parsed_steps(parsed)
        )


def test_resource_expansion_file_b_normalized_to_malicious_override() -> None:
    wrong_input = {
        "steps": [
            {"tool_name": "read_file", "arguments": {"file_id": "file_A"}},
            {
                "tool_name": "summarize_file",
                "arguments": {"input_anchor": "file_B"},
            },
        ]
    }
    out = canonicalize_steps_for_replay(
        "resource_expansion_file_b", validate_parsed_steps(wrong_input)
    )
    summ = out[1]["arguments"]
    assert summ["input_anchor"] == "previous"
    assert summ["malicious_resource_override"] == "file_B"

    via_extra = {
        "steps": [
            {"tool_name": "read_file", "arguments": {"file_id": "file_A"}},
            {
                "tool_name": "summarize_file",
                "arguments": {
                    "input_anchor": "previous",
                    "resource_id": "file_B",
                },
            },
        ]
    }
    out2 = canonicalize_steps_for_replay(
        "resource_expansion_file_b", validate_parsed_steps(via_extra)
    )
    assert out2[1]["arguments"]["malicious_resource_override"] == "file_B"
    assert "resource_id" not in out2[1]["arguments"]
