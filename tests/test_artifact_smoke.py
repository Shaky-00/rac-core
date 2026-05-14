"""Lightweight checks for artifact evaluation (no TraceBench bundle required)."""

from __future__ import annotations

import pytest

from rac_core.action_semantics.registry import ActionSemanticsRegistry
from rac_core.action_semantics.taxonomy import default_semantics_yaml_path
from rac_core.checker import RACPreCommitChecker
from rac_core.models import DecisionType
from rac_core.store import InMemoryBasisStore, InMemoryCausalLineageStore
from rac_core.validation import TraceRunner, build_taxonomy_traces
from rac_core.validation.rac_tracebench_loader import load_rac_tracebench, resolve_rac_tracebench_root


def _runner() -> TraceRunner:
    return TraceRunner(
        RACPreCommitChecker(
            lineage_store=InMemoryCausalLineageStore(),
            basis_store=InMemoryBasisStore(),
            action_semantics_registry=ActionSemanticsRegistry.load_from_yaml(
                default_semantics_yaml_path()
            ),
        )
    )


def test_taxonomy_benign_trace_allows() -> None:
    trace = next(t for t in build_taxonomy_traces() if t.name == "combined_benign_complex_summarize_chain")
    result = _runner().run(trace)
    assert result.passed
    assert result.step_results[-1].decision.decision == DecisionType.ALLOW


def test_taxonomy_drift_trace_blocks() -> None:
    trace = next(t for t in build_taxonomy_traces() if t.name == "action_escalation_read_external")
    result = _runner().run(trace)
    assert result.passed
    assert result.step_results[-1].decision.decision == DecisionType.BLOCK


def test_tracebench_bundle_loads_if_present() -> None:
    root = resolve_rac_tracebench_root()
    if root is None:
        pytest.skip("RAC-TraceBench bundle not present")
    bundle = load_rac_tracebench(root)
    assert bundle.get("traces")
