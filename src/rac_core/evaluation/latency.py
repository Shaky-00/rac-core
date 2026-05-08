"""Latency / overhead sampling for the demo RAC pre-commit path (Stage 9A).

The scenario execution loop mirrors ``LocalRACController.run_scenario`` so each
step measures the same adapter → tools → anchor verify → checker path without
changing checker or adapter semantics.
"""

from __future__ import annotations

import csv
import io
import json
import statistics
from dataclasses import asdict, dataclass, field
from pathlib import Path
from time import perf_counter_ns
from typing import Any, Literal

from rac_core.adapter import EventConstructionError
from rac_core.demo.local_controller import LocalRACController
from rac_core.demo.scripted_planner import ScriptedPlanner
from rac_core.demo.models import DemoRunResult, DemoStepResult
from rac_core.demo.reporting import (
    _action_escalation_grant,
    _default_grant,
    _demo_files,
    _demo_session,
)
from rac_core.demo.tools import LocalToolRuntime
from rac_core.models import (
    Decision,
    DecisionType,
    GrantEnvelope,
    InputAnchorRef,
    PendingToolCall,
    RuntimeTraceContext,
    SessionContext,
    Violation,
)


def _block_decision(rule: str, reason: str) -> Decision:
    return Decision(
        decision=DecisionType.BLOCK,
        violations=[Violation(rule=rule, reason=reason)],
    )


@dataclass
class LatencySample:
    scenario: str
    decision: str
    total_ms: float
    workflow_length: int | None = None
    predecessor_count: int | None = None
    event_construction_ms: float | None = None
    output_anchor_verification_ms: float | None = None
    precommit_check_ms: float | None = None
    persistence_ms: float | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class LatencySummary:
    scenario: str
    n: int
    mean_ms: float
    median_ms: float
    p95_ms: float
    p99_ms: float
    min_ms: float
    max_ms: float
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class _StepTiming:
    step_index: int
    total_ms: float
    event_construction_ms: float | None
    tool_execution_ms: float | None
    output_anchor_verification_ms: float | None
    precommit_check_ms: float | None
    persistence_ms: float | None
    decision: str


def percentile(values: list[float], q: float) -> float:
    """Nearest-rank / linear interpolation percentile for ``q`` in ``[0, 1]``."""
    if not values:
        raise ValueError("percentile requires a non-empty list")
    if not 0.0 <= q <= 1.0:
        raise ValueError("q must be in [0, 1]")
    xs = sorted(float(x) for x in values)
    n = len(xs)
    if n == 1:
        return xs[0]
    pos = (n - 1) * q
    lo = int(pos)
    hi = min(lo + 1, n - 1)
    if lo == hi:
        return xs[lo]
    frac = pos - lo
    return xs[lo] + frac * (xs[hi] - xs[lo])


def summarize_latency(samples: list[LatencySample], scenario: str) -> LatencySummary:
    rows = [s for s in samples if s.scenario == scenario]
    totals = [s.total_ms for s in rows]
    if not totals:
        raise ValueError(f"No samples for scenario={scenario!r}")
    meta: dict[str, object] = {}
    wf = {s.workflow_length for s in rows if s.workflow_length is not None}
    if len(wf) == 1:
        meta["workflow_length"] = next(iter(wf))
    pred = {s.predecessor_count for s in rows if s.predecessor_count is not None}
    if len(pred) == 1:
        meta["predecessor_count"] = next(iter(pred))
    return LatencySummary(
        scenario=scenario,
        n=len(totals),
        mean_ms=float(statistics.mean(totals)),
        median_ms=float(statistics.median(totals)),
        p95_ms=percentile(totals, 0.95),
        p99_ms=percentile(totals, 0.99),
        min_ms=min(totals),
        max_ms=max(totals),
        metadata=meta,
    )


def samples_to_csv(samples: list[LatencySample]) -> str:
    buf = io.StringIO()
    fieldnames = [
        "scenario",
        "workflow_length",
        "predecessor_count",
        "decision",
        "total_ms",
        "event_construction_ms",
        "output_anchor_verification_ms",
        "precommit_check_ms",
        "persistence_ms",
        "metadata_json",
    ]
    w = csv.DictWriter(buf, fieldnames=fieldnames)
    w.writeheader()
    for s in samples:
        w.writerow(
            {
                "scenario": s.scenario,
                "workflow_length": s.workflow_length if s.workflow_length is not None else "",
                "predecessor_count": s.predecessor_count if s.predecessor_count is not None else "",
                "decision": s.decision,
                "total_ms": f"{s.total_ms:.6f}",
                "event_construction_ms": ""
                if s.event_construction_ms is None
                else f"{s.event_construction_ms:.6f}",
                "output_anchor_verification_ms": ""
                if s.output_anchor_verification_ms is None
                else f"{s.output_anchor_verification_ms:.6f}",
                "precommit_check_ms": ""
                if s.precommit_check_ms is None
                else f"{s.precommit_check_ms:.6f}",
                "persistence_ms": ""
                if s.persistence_ms is None
                else f"{s.persistence_ms:.6f}",
                "metadata_json": json.dumps(s.metadata, sort_keys=True),
            }
        )
    return buf.getvalue()


def summaries_to_csv(summaries: list[LatencySummary]) -> str:
    buf = io.StringIO()
    fieldnames = [
        "scenario",
        "n",
        "mean_ms",
        "median_ms",
        "p95_ms",
        "p99_ms",
        "min_ms",
        "max_ms",
        "metadata_json",
    ]
    w = csv.DictWriter(buf, fieldnames=fieldnames)
    w.writeheader()
    for s in summaries:
        w.writerow(
            {
                "scenario": s.scenario,
                "n": s.n,
                "mean_ms": f"{s.mean_ms:.6f}",
                "median_ms": f"{s.median_ms:.6f}",
                "p95_ms": f"{s.p95_ms:.6f}",
                "p99_ms": f"{s.p99_ms:.6f}",
                "min_ms": f"{s.min_ms:.6f}",
                "max_ms": f"{s.max_ms:.6f}",
                "metadata_json": json.dumps(s.metadata, sort_keys=True),
            }
        )
    return buf.getvalue()


def write_json(path: Path | str, data: object) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(data, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def write_text(path: Path | str, text: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


class ListPendingCallsPlanner:
    """Deterministic planner returning a fixed tool-call list (bench workflows)."""

    def __init__(self, calls: list[PendingToolCall]) -> None:
        self._calls = list(calls)

    def plan(self, scenario_name: str) -> list[PendingToolCall]:
        return list(self._calls)


def _benign_linear_calls(length: int) -> list[PendingToolCall]:
    if length < 1:
        raise ValueError("workflow length must be >= 1")
    calls: list[PendingToolCall] = [
        PendingToolCall(tool_name="read_file", arguments={"file_id": "file_A"}),
    ]
    for _ in range(1, length):
        calls.append(
            PendingToolCall(
                tool_name="summarize_file",
                arguments={"input_anchor": "previous"},
            )
        )
    return calls


def _ns_to_ms(delta_ns: int) -> float:
    return delta_ns / 1_000_000.0


def _mirrored_run_scenario_loop(
    ctrl: LocalRACController,
    scenario_name: str,
    *,
    timing: Literal["none", "total_per_step", "components"] = "none",
) -> tuple[DemoRunResult, list[_StepTiming]]:
    """Mirror of ``LocalRACController.run_scenario`` with optional per-step timing."""
    calls = ctrl.planner.plan(scenario_name)
    steps: list[DemoStepResult] = []
    last_verified_anchor = None
    last_actual_output: object | None = None
    run_metadata: dict[str, object] = {"scenario_name": scenario_name}
    timings: list[_StepTiming] = []

    for idx, call in enumerate(calls):
        step_name = f"step_{idx}"
        event_id = f"evt:{ctrl.session_context.session_id}:{step_name}"
        t_step0 = perf_counter_ns()
        ec_ms = tool_ms = verify_ms = check_ms = persist_ms = None

        try:
            t0 = perf_counter_ns()
            trace = ctrl._build_runtime_trace(
                idx=idx,
                step_name=step_name,
                call=call,
                last_verified_anchor=last_verified_anchor,
            )
            t1 = perf_counter_ns()
            event = ctrl.event_adapter.construct_event(
                ctrl.session_context,
                ctrl.grant_envelope,
                call,
                trace,
            )
            t2 = perf_counter_ns()
            if timing == "components":
                ec_ms = _ns_to_ms(t2 - t1)
        except (EventConstructionError, ValueError) as exc:
            t_end = perf_counter_ns()
            decision = _block_decision(
                "EVENT_CONSTRUCTION_ERROR", str(exc) or "event construction failed"
            )
            steps.append(
                DemoStepResult(
                    step_name=step_name,
                    pending_tool_call=call,
                    event_id=event_id,
                    decision=decision,
                    blocked_reason=str(exc),
                    metadata={"rac_components": ["event_adapter"]},
                )
            )
            if timing != "none":
                total = _ns_to_ms(t_end - t_step0)
                timings.append(
                    _StepTiming(
                        step_index=idx,
                        total_ms=total,
                        event_construction_ms=ec_ms,
                        tool_execution_ms=None,
                        output_anchor_verification_ms=None,
                        precommit_check_ms=None,
                        persistence_ms=None,
                        decision="BLOCK",
                    )
                )
            return (
                DemoRunResult(
                    scenario_name=scenario_name,
                    steps=steps,
                    final_decision=DecisionType.BLOCK,
                    blocked_at_step=step_name,
                    metadata=run_metadata,
                ),
                timings,
            )

        try:
            t_tool0 = perf_counter_ns()
            tool_result = ctrl._execute_tool(
                call=call,
                event_id=event.event_id,
                last_verified_anchor=last_verified_anchor,
                last_actual_output=last_actual_output,
            )
            t_tool1 = perf_counter_ns()
            if timing == "components":
                tool_ms = _ns_to_ms(t_tool1 - t_tool0)
        except ValueError as exc:
            t_end = perf_counter_ns()
            decision = _block_decision(
                "TOOL_RUNTIME_ERROR", str(exc) or "tool runtime error"
            )
            steps.append(
                DemoStepResult(
                    step_name=step_name,
                    pending_tool_call=call,
                    event_id=event_id,
                    decision=decision,
                    blocked_reason=str(exc),
                    metadata={"rac_components": ["event_adapter", "local_tool_runtime"]},
                )
            )
            if timing != "none":
                timings.append(
                    _StepTiming(
                        step_index=idx,
                        total_ms=_ns_to_ms(t_end - t_step0),
                        event_construction_ms=ec_ms,
                        tool_execution_ms=tool_ms,
                        output_anchor_verification_ms=None,
                        precommit_check_ms=None,
                        persistence_ms=None,
                        decision="BLOCK",
                    )
                )
            return (
                DemoRunResult(
                    scenario_name=scenario_name,
                    steps=steps,
                    final_decision=DecisionType.BLOCK,
                    blocked_at_step=step_name,
                    metadata=run_metadata,
                ),
                timings,
            )

        if tool_result.anchor_claim is None:
            t_end = perf_counter_ns()
            decision = _block_decision(
                "OUTPUT_ANCHOR_INVALID", "Tool did not return an output anchor claim."
            )
            steps.append(
                DemoStepResult(
                    step_name=step_name,
                    pending_tool_call=call,
                    event_id=event_id,
                    decision=decision,
                    blocked_reason="missing anchor claim",
                    metadata={"rac_components": ["event_adapter", "local_tool_runtime"]},
                )
            )
            if timing != "none":
                timings.append(
                    _StepTiming(
                        step_index=idx,
                        total_ms=_ns_to_ms(t_end - t_step0),
                        event_construction_ms=ec_ms,
                        tool_execution_ms=tool_ms,
                        output_anchor_verification_ms=None,
                        precommit_check_ms=None,
                        persistence_ms=None,
                        decision="BLOCK",
                    )
                )
            return (
                DemoRunResult(
                    scenario_name=scenario_name,
                    steps=steps,
                    final_decision=DecisionType.BLOCK,
                    blocked_at_step=step_name,
                    metadata=run_metadata,
                ),
                timings,
            )

        t_v0 = perf_counter_ns()
        verify = ctrl.output_verifier.verify_output_anchor(
            tool_result.anchor_claim,
            tool_result.actual_output,
            event,
            tool_result.observed_resource_ids,
        )
        t_v1 = perf_counter_ns()
        if timing == "components":
            verify_ms = _ns_to_ms(t_v1 - t_v0)

        if not verify.valid or verify.verified_anchor is None:
            t_end = perf_counter_ns()
            rule = verify.rule or "OUTPUT_ANCHOR_INVALID"
            reason = verify.reason or "output anchor verification failed"
            decision = _block_decision(rule, reason)
            steps.append(
                DemoStepResult(
                    step_name=step_name,
                    pending_tool_call=call,
                    event_id=event_id,
                    decision=decision,
                    blocked_reason=reason,
                    metadata={
                        "rac_components": [
                            "event_adapter",
                            "local_tool_runtime",
                            "output_anchor_verifier",
                        ],
                        "output_anchor_verification": verify.model_dump(mode="python"),
                    },
                )
            )
            if timing != "none":
                timings.append(
                    _StepTiming(
                        step_index=idx,
                        total_ms=_ns_to_ms(t_end - t_step0),
                        event_construction_ms=ec_ms,
                        tool_execution_ms=tool_ms,
                        output_anchor_verification_ms=verify_ms,
                        precommit_check_ms=None,
                        persistence_ms=None,
                        decision="BLOCK",
                    )
                )
            return (
                DemoRunResult(
                    scenario_name=scenario_name,
                    steps=steps,
                    final_decision=DecisionType.BLOCK,
                    blocked_at_step=step_name,
                    metadata=run_metadata,
                ),
                timings,
            )

        t_c0 = perf_counter_ns()
        decision = ctrl.checker.check(
            event,
            ctrl.grant_envelope,
            output_anchor=verify.verified_anchor,
            persist=True,
            initial_basis=ctrl._demo_initial_basis if idx == 0 else None,
        )
        t_c1 = perf_counter_ns()
        if timing == "components":
            check_ms = _ns_to_ms(t_c1 - t_c0)
            persist_ms = None

        step_metadata: dict[str, object] = {
            "rac_components": [
                "event_adapter",
                "local_tool_runtime",
                "output_anchor_verifier",
                "rac_precommit_checker",
            ],
            "output_anchor_verified_by_controller": verify.verified_anchor.verified_by_controller,
            "tool_metadata": dict(tool_result.metadata),
        }
        ctrl._attach_demo_attack_metadata(call, step_metadata)

        if decision.decision == DecisionType.BLOCK:
            if call.tool_name == "create_email_draft":
                step_metadata["blocked_before_external_commit"] = True
                step_metadata["draft_staged_only"] = True
            steps.append(
                DemoStepResult(
                    step_name=step_name,
                    pending_tool_call=call,
                    event_id=event.event_id,
                    decision=decision,
                    blocked_reason=decision.violations[0].reason
                    if decision.violations
                    else None,
                    metadata=step_metadata,
                )
            )
            t_end = perf_counter_ns()
            if timing != "none":
                timings.append(
                    _StepTiming(
                        step_index=idx,
                        total_ms=_ns_to_ms(t_end - t_step0),
                        event_construction_ms=ec_ms,
                        tool_execution_ms=tool_ms,
                        output_anchor_verification_ms=verify_ms,
                        precommit_check_ms=check_ms,
                        persistence_ms=persist_ms,
                        decision="BLOCK",
                    )
                )
            return (
                DemoRunResult(
                    scenario_name=scenario_name,
                    steps=steps,
                    final_decision=DecisionType.BLOCK,
                    blocked_at_step=step_name,
                    metadata=run_metadata,
                ),
                timings,
            )

        last_verified_anchor = verify.verified_anchor
        last_actual_output = tool_result.actual_output
        if (
            getattr(ctrl, "_fan_in", 1) > 1
            and hasattr(ctrl, "_read_anchors")
            and call.tool_name == "read_file"
        ):
            ctrl._read_anchors.append(last_verified_anchor)

        steps.append(
            DemoStepResult(
                step_name=step_name,
                pending_tool_call=call,
                event_id=event.event_id,
                decision=decision,
                verified_anchor=verify.verified_anchor,
                metadata=step_metadata,
            )
        )
        t_end = perf_counter_ns()
        if timing == "total_per_step":
            timings.append(
                _StepTiming(
                    step_index=idx,
                    total_ms=_ns_to_ms(t_end - t_step0),
                    event_construction_ms=None,
                    tool_execution_ms=None,
                    output_anchor_verification_ms=None,
                    precommit_check_ms=None,
                    persistence_ms=None,
                    decision="ALLOW",
                )
            )
        elif timing == "components":
            timings.append(
                _StepTiming(
                    step_index=idx,
                    total_ms=_ns_to_ms(t_end - t_step0),
                    event_construction_ms=ec_ms,
                    tool_execution_ms=tool_ms,
                    output_anchor_verification_ms=verify_ms,
                    precommit_check_ms=check_ms,
                    persistence_ms=persist_ms,
                    decision="ALLOW",
                )
            )

    return (
        DemoRunResult(
            scenario_name=scenario_name,
            steps=steps,
            final_decision=DecisionType.ALLOW,
            blocked_at_step=None,
            metadata=run_metadata,
        ),
        timings,
    )


class PredecessorFanInLocalController(LocalRACController):
    """Demo controller variant: N verified reads then summarize with N input anchors."""

    def __init__(self, *args: Any, fan_in: int = 1, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._fan_in = fan_in
        self._read_anchors: list[Any] = []

    def _build_runtime_trace(
        self,
        *,
        idx: int,
        step_name: str,
        call: PendingToolCall,
        last_verified_anchor,
    ) -> RuntimeTraceContext:
        if (
            call.tool_name == "summarize_file"
            and self._fan_in > 1
            and len(self._read_anchors) >= self._fan_in
        ):
            from datetime import datetime as dt_mod

            refs = [
                InputAnchorRef(
                    anchor_id=a.anchor_id,
                    producer_event_id=a.producer_event_id,
                    content_hash=a.content_hash,
                )
                for a in self._read_anchors[: self._fan_in]
            ]
            sp = call.arguments.get("selected_purpose")
            selected = str(sp) if isinstance(sp, str) and sp else None
            return RuntimeTraceContext(
                session_id=self.session_context.session_id,
                step_id=step_name,
                step_seq=idx,
                input_anchors=refs,
                selected_purpose=selected,
                observed_time=dt_mod(2026, 4, 26, 12, 0, 0),
                environment=self.grant_envelope.conditions.environment
                or "trusted_workspace",
                tenant=self.grant_envelope.conditions.tenant
                or self.session_context.tenant
                or "tenant_X",
                runtime_labels=set(self.grant_envelope.conditions.runtime_labels)
                or {"internal"},
            )
        return super()._build_runtime_trace(
            idx=idx,
            step_name=step_name,
            call=call,
            last_verified_anchor=last_verified_anchor,
        )

    def run_scenario(self, scenario_name: str) -> DemoRunResult:
        if self._fan_in <= 1:
            return super().run_scenario(scenario_name)
        self._read_anchors = []
        result, _ = _mirrored_run_scenario_loop(self, scenario_name, timing="none")
        return result


def _bench_session(repeat_tag: int) -> SessionContext:
    base = _demo_session()
    return base.model_copy(update={"session_id": f"{base.session_id}_lat_{repeat_tag}"})


def _grant_for_session(
    grant_template: GrantEnvelope, session: SessionContext
) -> GrantEnvelope:
    return grant_template.model_copy(update={"session_id": session.session_id})


def _timing_to_sample(
    scenario: str,
    st: _StepTiming,
    *,
    workflow_length: int | None = None,
    predecessor_count: int | None = None,
    extra_meta: dict[str, object] | None = None,
) -> LatencySample:
    meta = dict(extra_meta or {})
    meta.setdefault("step_index", st.step_index)
    if st.tool_execution_ms is not None:
        meta["tool_execution_ms"] = st.tool_execution_ms
    return LatencySample(
        scenario=scenario,
        decision=st.decision,
        total_ms=st.total_ms,
        workflow_length=workflow_length,
        predecessor_count=predecessor_count,
        event_construction_ms=st.event_construction_ms,
        output_anchor_verification_ms=st.output_anchor_verification_ms,
        precommit_check_ms=st.precommit_check_ms,
        persistence_ms=st.persistence_ms,
        metadata=meta,
    )


def run_workflow_length_benchmark(
    lengths: list[int] | None = None,
    repeats: int = 100,
    warmup: int = 10,
) -> tuple[list[LatencySample], list[LatencySummary]]:
    lengths = lengths or [1, 5, 10, 20, 50, 100, 200]
    samples: list[LatencySample] = []
    for length in lengths:
        calls = _benign_linear_calls(length)
        scen = f"benign_workflow_scaling_L{length}"
        for r in range(warmup + repeats):
            sess = _bench_session(r)
            ctrl = LocalRACController(
                grant_envelope=_grant_for_session(_default_grant(), sess),
                session_context=sess,
                tool_runtime=LocalToolRuntime(_demo_files()),
                planner=ListPendingCallsPlanner(calls),
            )
            if r < warmup:
                _mirrored_run_scenario_loop(ctrl, "__bench__", timing="none")
                continue
            _, timings = _mirrored_run_scenario_loop(
                ctrl, "__bench__", timing="total_per_step"
            )
            for st in timings:
                samples.append(
                    _timing_to_sample(
                        scen,
                        st,
                        workflow_length=length,
                        extra_meta={"repeat": r - warmup},
                    )
                )
    summaries = [summarize_latency(samples, f"benign_workflow_scaling_L{L}") for L in lengths]
    return samples, summaries


def run_decision_path_benchmark(
    repeats: int = 100,
    warmup: int = 10,
) -> tuple[list[LatencySample], list[LatencySummary]]:
    scenarios = [
        "benign_read_summarize",
        "action_escalation_external_email",
        "resource_expansion_file_b",
        "forged_predecessor",
    ]
    samples: list[LatencySample] = []
    for name in scenarios:
        grant = (
            _action_escalation_grant()
            if name == "action_escalation_external_email"
            else _default_grant()
        )
        scen = f"decision_path_{name}"
        for r in range(warmup + repeats):
            sess = _bench_session(r)
            ctrl = LocalRACController(
                grant_envelope=_grant_for_session(grant, sess),
                session_context=sess,
                tool_runtime=LocalToolRuntime(_demo_files()),
                planner=ScriptedPlanner(),
            )
            if r < warmup:
                _mirrored_run_scenario_loop(ctrl, name, timing="none")
                continue
            t0 = perf_counter_ns()
            result, _ = _mirrored_run_scenario_loop(ctrl, name, timing="none")
            t1 = perf_counter_ns()
            d = "ALLOW" if result.final_decision == DecisionType.ALLOW else "BLOCK"
            samples.append(
                LatencySample(
                    scenario=scen,
                    decision=d,
                    total_ms=_ns_to_ms(t1 - t0),
                    metadata={"repeat": r - warmup, "scenario_name": name},
                )
            )
    summaries = [summarize_latency(samples, f"decision_path_{n}") for n in scenarios]
    return samples, summaries


def run_predecessor_resolution_benchmark(
    predecessor_counts: list[int] | None = None,
    repeats: int = 100,
    warmup: int = 10,
) -> tuple[list[LatencySample], list[LatencySummary]]:
    """Vary how many verified reads precede summarize (fan-in unsupported when count>1)."""
    predecessor_counts = predecessor_counts or [1, 2, 4, 8, 16, 32]
    samples: list[LatencySample] = []
    for n in predecessor_counts:
        scen = f"predecessor_resolution_n{n}"
        if n <= 1:
            calls = _benign_linear_calls(2)
        else:
            calls = [
                PendingToolCall(tool_name="read_file", arguments={"file_id": "file_A"})
            ] * n + [
                PendingToolCall(
                    tool_name="summarize_file",
                    arguments={"input_anchor": "previous"},
                )
            ]
        for r in range(warmup + repeats):
            sess = _bench_session(r)
            kwargs: dict[str, Any] = dict(
                grant_envelope=_grant_for_session(_default_grant(), sess),
                session_context=sess,
                tool_runtime=LocalToolRuntime(_demo_files()),
                planner=ListPendingCallsPlanner(calls),
            )
            if n > 1:
                ctrl = PredecessorFanInLocalController(fan_in=n, **kwargs)
            else:
                ctrl = LocalRACController(**kwargs)
            if r < warmup:
                _mirrored_run_scenario_loop(ctrl, "__bench__", timing="none")
                continue
            t0 = perf_counter_ns()
            result, _ = _mirrored_run_scenario_loop(ctrl, "__bench__", timing="none")
            t1 = perf_counter_ns()
            d = "ALLOW" if result.final_decision == DecisionType.ALLOW else "BLOCK"
            rule = None
            if result.steps and result.steps[-1].decision.violations:
                rule = result.steps[-1].decision.violations[0].rule
            samples.append(
                LatencySample(
                    scenario=scen,
                    decision=d,
                    total_ms=_ns_to_ms(t1 - t0),
                    predecessor_count=n,
                    metadata={
                        "repeat": r - warmup,
                        "blocked_rule": rule,
                        "resolution_note": (
                            "multi_anchor_event_construction"
                            if n > 1
                            else "single_predecessor_allow"
                        ),
                    },
                )
            )
    summaries = [
        summarize_latency(samples, f"predecessor_resolution_n{n}")
        for n in predecessor_counts
    ]
    return samples, summaries


def run_component_breakdown_benchmark(
    repeats: int = 100,
    warmup: int = 10,
) -> tuple[list[LatencySample], list[LatencySummary]]:
    calls = _benign_linear_calls(2)
    samples: list[LatencySample] = []
    scen = "component_breakdown_benign_read_summarize"
    for r in range(warmup + repeats):
        sess = _bench_session(r)
        ctrl = LocalRACController(
            grant_envelope=_grant_for_session(_default_grant(), sess),
            session_context=sess,
            tool_runtime=LocalToolRuntime(_demo_files()),
            planner=ListPendingCallsPlanner(calls),
        )
        if r < warmup:
            _mirrored_run_scenario_loop(ctrl, "__bench__", timing="none")
            continue
        _, timings = _mirrored_run_scenario_loop(
            ctrl, "__bench__", timing="components"
        )
        for st in timings:
            samples.append(
                _timing_to_sample(
                    scen,
                    st,
                    workflow_length=2,
                    extra_meta={"repeat": r - warmup, "tool_step": st.step_index},
                )
            )
    summaries = [summarize_latency(samples, scen)]
    return samples, summaries
