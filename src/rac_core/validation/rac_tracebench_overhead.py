"""Runtime overhead microbenchmark for RAC-TraceBench v0.6 (pre-commit replay path, no MCP / LLM)."""

from __future__ import annotations

import csv
import json
import math
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from rac_core.action_semantics.registry import ActionSemanticsRegistry
from rac_core.action_semantics.taxonomy import default_semantics_yaml_path
from rac_core.checker import RACPreCommitChecker
from rac_core.models import DecisionType
from rac_core.store import InMemoryBasisStore, InMemoryCausalLineageStore
from rac_core.store.lineage_store import event_requires_tracebench_producer_event_id
from rac_core.validation.rac_tracebench_loader import (
    convert_trace_case_to_controlled_trace,
    load_rac_tracebench,
)
from rac_core.validation.trace import (
    ControlledTrace,
    effective_event_for_trace_step,
    infer_grant_templates_for_trace,
    initial_basis_from_grant_templates,
)
from rac_core.verification.output_anchor import output_anchor_integrity_precheck

# CSV columns (resource_origin / action_coverage are not split — see summary JSON).
CSV_FIELDNAMES = [
    "iteration",
    "trace_id",
    "trace_family",
    "step_index",
    "step_name",
    "output_anchor_precheck_ms",
    "lineage_resolution_ms",
    "resource_origin_verification_ms",
    "action_coverage_check_ms",
    "precommit_check_ms",
    "total_step_ms",
    "total_trace_ms",
    "replay_total_ms",
]

_COARSE_NOTE = (
    "Fine-grained: output_anchor_precheck_ms, lineage_resolution_ms (outer resolve_predecessor only, "
    "same as TraceRunner), precommit_check_ms (entire RACPreCommitChecker.check), total_step_ms, "
    "total_trace_ms / replay_total_ms. "
    "Coarse / not instrumented separately: resource_origin_verification_ms and action_coverage_check_ms "
    "(both are included in precommit_check_ms); internal lineage resolve inside check() is not subtracted "
    "from lineage_resolution_ms."
)


def default_checker_factory() -> RACPreCommitChecker:
    return RACPreCommitChecker(
        lineage_store=InMemoryCausalLineageStore(),
        basis_store=InMemoryBasisStore(),
        action_semantics_registry=ActionSemanticsRegistry.load_from_yaml(default_semantics_yaml_path()),
    )


def resolve_tracebench_root(explicit: Path | None = None) -> Path | None:
    """Same discovery order as :mod:`rac_core.validation.rac_tracebench_experiment`."""
    from rac_core.validation.rac_tracebench_experiment import resolve_tracebench_root as _r

    return _r(explicit)


def _percentile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    xs = sorted_vals
    n = len(xs)
    if n == 1:
        return xs[0]
    idx = (n - 1) * (q / 100.0)
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return xs[lo]
    return xs[lo] + (xs[hi] - xs[lo]) * (idx - lo)


def _trace_family(trace: ControlledTrace) -> str:
    meta = trace.metadata.get("rac_tracebench") if isinstance(trace.metadata, dict) else None
    if isinstance(meta, dict):
        fam = meta.get("trace_family")
        return str(fam) if fam is not None else ""
    return ""


def run_timed_trace(
    trace: ControlledTrace,
    checker: RACPreCommitChecker,
    *,
    skip_output_anchor_integrity: bool = False,
) -> list[dict[str, Any]]:
    """Replay one trace with wall-clock splits aligned with :class:`~rac_core.validation.trace.TraceRunner`.

    Empty-string columns ``resource_origin_verification_ms`` and ``action_coverage_check_ms`` mean
    not measured separately (work is inside ``precommit_check_ms``).
    """
    rows: list[dict[str, Any]] = []
    trace_t0 = time.perf_counter()

    first_ib = None
    if not trace.legacy_rac_trace:
        if trace.initial_basis is not None:
            first_ib = trace.initial_basis
        else:
            tpl = infer_grant_templates_for_trace(trace)
            if tpl:
                first_ib = initial_basis_from_grant_templates(trace.steps[0].grant, tpl)

    require_pid = event_requires_tracebench_producer_event_id

    for step_index, step in enumerate(trace.steps):
        event = effective_event_for_trace_step(step)
        step_t0 = time.perf_counter()

        t_a = time.perf_counter()
        integ = output_anchor_integrity_precheck(
            step.output_anchor,
            skip_integrity=skip_output_anchor_integrity,
        )
        t_b = time.perf_counter()
        output_anchor_precheck_ms = (t_b - t_a) * 1000.0

        if integ is not None:
            total_step_ms = (time.perf_counter() - step_t0) * 1000.0
            rows.append(
                {
                    "step_index": step_index,
                    "step_name": step.name,
                    "output_anchor_precheck_ms": output_anchor_precheck_ms,
                    "lineage_resolution_ms": "",
                    "resource_origin_verification_ms": "",
                    "action_coverage_check_ms": "",
                    "precommit_check_ms": "",
                    "total_step_ms": total_step_ms,
                }
            )
            break

        t_c = time.perf_counter()
        pred = checker.lineage_store.resolve_predecessor(
            event.input_anchors,
            event.advisory_predecessor_hints,
            event.session_id,
            require_producer_event_id_on_inputs=require_pid(event.metadata),
        )
        t_d = time.perf_counter()
        lineage_resolution_ms = (t_d - t_c) * 1000.0

        init = first_ib if (first_ib is not None and pred.status == "NO_PREDECESSOR") else None

        t_e = time.perf_counter()
        decision = checker.check(
            event=event,
            grant_envelope=step.grant,
            local_allow=step.local_allow,
            output_anchor=step.output_anchor,
            persist=step.persist,
            initial_basis=init,
        )
        t_f = time.perf_counter()
        precommit_check_ms = (t_f - t_e) * 1000.0
        total_step_ms = (t_f - step_t0) * 1000.0

        if skip_output_anchor_integrity:
            decision = decision.model_copy(
                update={
                    "metadata": {
                        **dict(decision.metadata),
                        "output_anchor_integrity_check": "skipped_by_variant",
                    }
                }
            )

        rows.append(
            {
                "step_index": step_index,
                "step_name": step.name,
                "output_anchor_precheck_ms": output_anchor_precheck_ms,
                "lineage_resolution_ms": lineage_resolution_ms,
                "resource_origin_verification_ms": "",
                "action_coverage_check_ms": "",
                "precommit_check_ms": precommit_check_ms,
                "total_step_ms": total_step_ms,
            }
        )

        if decision.decision == DecisionType.BLOCK:
            break

    trace_ms = (time.perf_counter() - trace_t0) * 1000.0
    for r in rows:
        r["total_trace_ms"] = trace_ms
        r["replay_total_ms"] = trace_ms

    return rows


def collect_overhead_rows(
    bench_root: Path,
    iterations: int,
    *,
    checker_factory: Callable[[], RACPreCommitChecker] | None = None,
    skip_output_anchor_integrity: bool = False,
) -> tuple[list[dict[str, Any]], int]:
    """Run all TraceBench traces ``iterations`` times; return flat row dicts and trace count."""
    bundle = load_rac_tracebench(bench_root)
    cases: list[dict[str, Any]] = bundle["traces"]
    factory = checker_factory or default_checker_factory
    flat: list[dict[str, Any]] = []

    br = str(bundle["root"].resolve())
    prev = os.environ.get("RAC_TRACEBENCH_ROOT")
    os.environ["RAC_TRACEBENCH_ROOT"] = br
    try:
        for it in range(iterations):
            for case in cases:
                trace = convert_trace_case_to_controlled_trace(case)
                checker = factory()
                base_rows = run_timed_trace(
                    trace,
                    checker,
                    skip_output_anchor_integrity=skip_output_anchor_integrity,
                )
                tid = trace.name
                fam = _trace_family(trace)
                for step_row in base_rows:
                    row = {
                        "iteration": it,
                        "trace_id": tid,
                        "trace_family": fam,
                        **step_row,
                    }
                    flat.append(row)
    finally:
        if prev is None:
            os.environ.pop("RAC_TRACEBENCH_ROOT", None)
        else:
            os.environ["RAC_TRACEBENCH_ROOT"] = prev

    return flat, len(cases)


def build_summary(
    rows: list[dict[str, Any]],
    *,
    iterations: int,
    num_traces: int,
) -> dict[str, Any]:
    """Aggregate percentiles and per-family means for JSON summary."""
    step_ms = [float(r["total_step_ms"]) for r in rows if r.get("total_step_ms") != ""]
    step_ms_sorted = sorted(step_ms)

    # One total per (iteration, trace_id): max replay_total_ms on that trace's rows (constant per row).
    trace_totals: list[float] = []
    by_run: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_run[(int(r["iteration"]), str(r["trace_id"]))].append(r)
    for _k, rs in by_run.items():
        if rs:
            trace_totals.append(float(rs[0]["total_trace_ms"]))

    trace_totals_sorted = sorted(trace_totals)

    per_family: defaultdict[str, list[float]] = defaultdict(list)
    for r in rows:
        if r.get("total_step_ms") == "":
            continue
        fam = str(r.get("trace_family") or "")
        per_family[fam].append(float(r["total_step_ms"]))

    per_family_mean_ms = {
        fam: (sum(vals) / len(vals) if vals else 0.0) for fam, vals in per_family.items()
    }

    # Histogram: how many traces have N steps (from iteration 0 row counts per trace_id).
    rows_iter0 = [r for r in rows if int(r["iteration"]) == 0]
    steps_per_tid: defaultdict[str, int] = defaultdict(int)
    for r in rows_iter0:
        steps_per_tid[str(r["trace_id"])] += 1
    per_step_count: dict[str, int] = defaultdict(int)
    for n in steps_per_tid.values():
        per_step_count[str(n)] += 1

    total_runs = iterations * num_traces
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    return {
        "iterations": iterations,
        "total_runs": total_runs,
        "total_step_records": len(rows),
        "num_traces": num_traces,
        "p50_step_ms": _percentile(step_ms_sorted, 50),
        "p95_step_ms": _percentile(step_ms_sorted, 95),
        "p99_step_ms": _percentile(step_ms_sorted, 99),
        "mean_step_ms": (sum(step_ms) / len(step_ms)) if step_ms else 0.0,
        "max_step_ms": max(step_ms) if step_ms else 0.0,
        "mean_trace_ms": (sum(trace_totals) / len(trace_totals)) if trace_totals else 0.0,
        "p95_trace_ms": _percentile(trace_totals_sorted, 95),
        "per_family_mean_ms": dict(sorted(per_family_mean_ms.items())),
        "per_step_count": dict(sorted(per_step_count.items(), key=lambda x: int(x[0]))),
        "coarse_grained_measurement_notes": _COARSE_NOTE,
        "generated_at": now,
    }


def write_overhead_results(
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
    output_dir: Path,
    *,
    csv_name: str = "rac_tracebench_v06_overhead.csv",
    json_name: str = "rac_tracebench_v06_overhead_summary.json",
) -> tuple[Path, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / csv_name
    json_path = output_dir / json_name

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            out = {k: r.get(k, "") for k in CSV_FIELDNAMES}
            w.writerow(out)

    json_path.write_text(json.dumps(summary, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return csv_path, json_path


def run_overhead_and_write(
    bench_root: Path,
    output_dir: Path,
    iterations: int,
    *,
    checker_factory: Callable[[], RACPreCommitChecker] | None = None,
    skip_output_anchor_integrity: bool = False,
) -> tuple[Path, Path, dict[str, Any]]:
    rows, n_tr = collect_overhead_rows(
        bench_root,
        iterations,
        checker_factory=checker_factory,
        skip_output_anchor_integrity=skip_output_anchor_integrity,
    )
    summary = build_summary(rows, iterations=iterations, num_traces=n_tr)
    csv_p, json_p = write_overhead_results(rows, summary, output_dir)
    return csv_p, json_p, summary
