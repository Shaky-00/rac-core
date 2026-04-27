from __future__ import annotations

import pytest

from rac_core.models import DecisionType
from rac_core.validation.ablation import AblationMode, AblationRunner, COMPONENT_ABLATION_MODES
from rac_core.validation.component_ablation_cases import (
    build_component_ablation_cases,
    component_attack_checker_factory,
)


def _runner() -> AblationRunner:
    return AblationRunner(checker_factory=component_attack_checker_factory)


def _miss_mode(trace) -> AblationMode | None:
    raw = trace.metadata.get("miss_mode")
    if raw is None:
        return None
    return AblationMode(str(raw))


@pytest.mark.parametrize("trace", build_component_ablation_cases(), ids=lambda t: t.name)
def test_component_ablation_full_and_miss(trace) -> None:
    runner = _runner()
    miss = _miss_mode(trace)
    is_control = str(trace.metadata.get("component", "")) == "control"

    full = runner.run_trace(trace, AblationMode.FULL_RAC)
    if is_control:
        assert full.blocked_at_step is None
        for sr in full.step_results:
            assert sr.observed_decision == DecisionType.ALLOW
        return

    assert full.blocked_at_step is not None
    blocked_idx = len(full.step_results) - 1
    blocked_step = trace.steps[blocked_idx]
    assert blocked_step.expected_decision == DecisionType.BLOCK
    fsr = full.step_results[blocked_idx]
    assert fsr.observed_decision == DecisionType.BLOCK
    if blocked_step.expected_rule is not None:
        assert blocked_step.expected_rule in fsr.observed_rules

    assert miss is not None
    ablated = runner.run_trace(trace, miss)
    assert ablated.blocked_at_step is None
    for sr in ablated.step_results:
        assert sr.observed_decision == DecisionType.ALLOW


def test_benign_control_allow_under_all_component_modes() -> None:
    runner = _runner()
    trace = next(t for t in build_component_ablation_cases() if t.name == "benign_control_single_read")
    for mode in COMPONENT_ABLATION_MODES:
        r = runner.run_trace(trace, mode)
        assert r.blocked_at_step is None
        assert all(sr.observed_decision == DecisionType.ALLOW for sr in r.step_results)


@pytest.mark.parametrize(
    "trace_name,miss_mode",
    [
        ("o1_origin_only_unverifiable_text", AblationMode.RAC_WITHOUT_RESOURCE_ORIGIN),
        ("l1_lineage_only_forged_hash", AblationMode.RAC_WITHOUT_LINEAGE),
        ("p1_purpose_only_external", AblationMode.RAC_WITHOUT_PURPOSE),
        ("a1_action_only_external_email", AblationMode.RAC_WITHOUT_ACTION),
        ("c1_condition_only_tenant_change", AblationMode.RAC_WITHOUT_CONDITIONS),
        ("d1_delegation_only_introduced", AblationMode.RAC_WITHOUT_DELEGATION),
        ("an1_anchor_only_unverified_output", AblationMode.RAC_WITHOUT_ANCHOR),
    ],
)
def test_attack_still_blocked_when_wrong_component_ablated(trace_name: str, miss_mode: AblationMode) -> None:
    """Non-target ablation modes must not produce a miss (ALLOW) on attack traces."""
    runner = _runner()
    trace = next(t for t in build_component_ablation_cases() if t.name == trace_name)
    own_miss = _miss_mode(trace)
    assert own_miss is not None
    if miss_mode == own_miss:
        return
    r = runner.run_trace(trace, miss_mode)
    assert r.blocked_at_step is not None
