"""Oracle validation for drift taxonomy controlled traces."""

from __future__ import annotations

import pytest

from rac_core.checker import RACPreCommitChecker
from rac_core.models import DecisionType
from rac_core.store import InMemoryBasisStore, InMemoryCausalLineageStore
from rac_core.validation import TraceRunner, build_taxonomy_traces


def _fresh_runner() -> TraceRunner:
    return TraceRunner(
        RACPreCommitChecker(
            lineage_store=InMemoryCausalLineageStore(),
            basis_store=InMemoryBasisStore(),
        )
    )


@pytest.mark.parametrize("trace", build_taxonomy_traces(), ids=lambda t: t.name)
def test_taxonomy_trace_oracle(trace) -> None:
    runner = _fresh_runner()
    result = runner.run(trace)
    assert result.passed is True, f"{trace.name}: trace runner reported failure"
    for sr in result.step_results:
        assert sr.decision.decision == sr.expected_decision, (
            f"{trace.name} step {sr.name}: expected {sr.expected_decision}, "
            f"got {sr.decision.decision}"
        )
        if sr.expected_rule is not None:
            assert sr.expected_rule in sr.observed_rules, (
                f"{trace.name} step {sr.name}: expected rule {sr.expected_rule!r} "
                f"among {sr.observed_rules}"
            )
    if trace.expected_final_decision is not None and result.step_results:
        assert (
            result.step_results[-1].decision.decision == trace.expected_final_decision
        ), f"{trace.name}: final decision mismatch"


def test_taxonomy_trace_count() -> None:
    traces = build_taxonomy_traces()
    assert len(traces) >= 40


def test_g8_multi_violation_has_multiple_rules() -> None:
    """G8 should surface more than one violation rule on the blocking step."""
    trace = next(t for t in build_taxonomy_traces() if t.name == "combined_multi_violation_external_step")
    runner = _fresh_runner()
    result = runner.run(trace)
    assert result.blocked_at_step == "s1"
    last = result.step_results[-1]
    assert last.decision.decision == DecisionType.BLOCK
    rules = {v.rule for v in last.decision.violations}
    assert len(rules) >= 2
    assert "ACTION_ESCALATION" in rules
