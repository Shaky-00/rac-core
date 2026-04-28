from __future__ import annotations

import pytest

from rac_core.models import DecisionType
from rac_core.validation.ablation import AblationMode, AblationRunner, COMPONENT_ABLATION_MODES
from rac_core.validation.component_ablation_cases import (
    build_component_ablation_cases,
    component_attack_checker_factory,
)


EXPECTED_MISS_MODE: dict[str, AblationMode | None] = {
    "o1_origin_only_unverifiable_text": AblationMode.RAC_WITHOUT_RESOURCE_ORIGIN,
    "l1_lineage_only_forged_hash": AblationMode.RAC_WITHOUT_LINEAGE,
    "p1_purpose_only_external": AblationMode.RAC_WITHOUT_PURPOSE,
    "a1_action_only_external_email": AblationMode.RAC_WITHOUT_ACTION,
    "c1_condition_only_tenant_change": AblationMode.RAC_WITHOUT_CONDITIONS,
    "d1_delegation_only_introduced": AblationMode.RAC_WITHOUT_DELEGATION,
    "an1_anchor_only_unverified_output": AblationMode.RAC_WITHOUT_ANCHOR,
    "benign_control_single_read": None,
}


def _runner() -> AblationRunner:
    return AblationRunner(checker_factory=component_attack_checker_factory)


@pytest.mark.parametrize("trace", build_component_ablation_cases(), ids=lambda t: t.name)
def test_component_ablation_matrix_contract(trace) -> None:
    runner = _runner()
    own_miss = EXPECTED_MISS_MODE[trace.name]
    is_benign = own_miss is None

    for mode in COMPONENT_ABLATION_MODES:
        result = runner.run_trace(trace, mode)
        blocked = result.blocked_at_step is not None
        if is_benign:
            assert not blocked, f"{trace.name} should ALLOW under {mode.value}"
            assert all(sr.observed_decision == DecisionType.ALLOW for sr in result.step_results)
            continue
        if mode == own_miss:
            assert not blocked, f"{trace.name} should MISS under {mode.value}"
            assert all(sr.observed_decision == DecisionType.ALLOW for sr in result.step_results)
        else:
            assert blocked, f"{trace.name} should BLOCK under {mode.value}"
            last = result.step_results[-1]
            assert last.observed_decision == DecisionType.BLOCK

