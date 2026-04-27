from __future__ import annotations

import pytest

from rac_core.models import DecisionType
from rac_core.validation import TraceRunner
from rac_core.validation.benign_fp_traces import build_benign_fp_checker, build_benign_fp_traces


def _final_decision(result) -> DecisionType:
    assert result.step_results
    return result.step_results[-1].decision.decision


@pytest.mark.parametrize("trace", build_benign_fp_traces(), ids=lambda t: t.name)
def test_benign_fp_trace_all_allow(trace) -> None:
    checker = build_benign_fp_checker()
    result = TraceRunner(checker).run(trace)
    assert result.passed
    assert _final_decision(result) == DecisionType.ALLOW
