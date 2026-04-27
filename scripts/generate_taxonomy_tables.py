"""Generate drift taxonomy validation tables for paper layout.

Run from repository root:
  python scripts/generate_taxonomy_tables.py
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SRC = ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from pydantic import BaseModel

from rac_core.checker import RACPreCommitChecker
from rac_core.models import DecisionType
from rac_core.store import InMemoryBasisStore, InMemoryCausalLineageStore
from rac_core.validation import (
    TraceRunner,
    build_taxonomy_traces,
    format_decision,
    to_csv,
    to_latex_tabular,
    to_markdown_table,
)


class TaxonomyValidationRow(BaseModel):
    case_id: str
    category: str
    case_name: str
    num_steps: int
    expected_decision: str
    observed_decision: str
    match: str
    expected_rule: str
    triggered_rule: str


class TaxonomySummaryRow(BaseModel):
    category: str
    total: int
    allowed: int
    blocked: int
    mismatches: int
    false_positives: int
    false_negatives: int


def _last_observed_decision(result) -> DecisionType:
    if not result.step_results:
        return DecisionType.BLOCK
    return result.step_results[-1].decision.decision


def _last_triggered_rule(result) -> str:
    if not result.step_results:
        return "—"
    last = result.step_results[-1]
    if last.decision.violations:
        return last.decision.violations[0].rule
    return "—"


def _expected_final(trace) -> DecisionType:
    if trace.expected_final_decision is not None:
        return trace.expected_final_decision
    if trace.steps:
        return trace.steps[-1].expected_decision
    return DecisionType.BLOCK


def _expected_rule_final(trace) -> str:
    if not trace.steps:
        return "—"
    r = trace.steps[-1].expected_rule
    return r if r else "—"


def run_taxonomy_validation() -> tuple[list, list, int, int]:
    traces = build_taxonomy_traces()
    val_rows: list[TaxonomyValidationRow] = []
    cat_stats: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "total": 0,
            "allowed": 0,
            "blocked": 0,
            "mismatches": 0,
            "false_positives": 0,
            "false_negatives": 0,
        }
    )

    fp = fn = 0
    for i, trace in enumerate(traces):
        checker = RACPreCommitChecker(
            lineage_store=InMemoryCausalLineageStore(),
            basis_store=InMemoryBasisStore(),
        )
        runner = TraceRunner(checker)
        result = runner.run(trace)
        exp = _expected_final(trace)
        obs = _last_observed_decision(result)
        exp_rule = _expected_rule_final(trace)
        trig = _last_triggered_rule(result)
        cat = str(trace.metadata.get("category", "?"))

        cat_stats[cat]["total"] += 1
        if obs == DecisionType.ALLOW:
            cat_stats[cat]["allowed"] += 1
        else:
            cat_stats[cat]["blocked"] += 1

        match = "✓" if result.passed and obs == exp else "✗"
        if obs != exp:
            cat_stats[cat]["mismatches"] += 1
        if exp == DecisionType.ALLOW and obs == DecisionType.BLOCK:
            fp += 1
            cat_stats[cat]["false_positives"] += 1
        if exp == DecisionType.BLOCK and obs == DecisionType.ALLOW:
            fn += 1
            cat_stats[cat]["false_negatives"] += 1

        val_rows.append(
            TaxonomyValidationRow(
                case_id=f"TX{i + 1:03d}",
                category=cat,
                case_name=trace.name,
                num_steps=len(trace.steps),
                expected_decision=format_decision(exp),
                observed_decision=format_decision(obs),
                match=match,
                expected_rule=exp_rule,
                triggered_rule=trig,
            )
        )

    summary_rows: list[TaxonomySummaryRow] = []
    for cat in sorted(cat_stats.keys()):
        s = cat_stats[cat]
        summary_rows.append(
            TaxonomySummaryRow(
                category=cat,
                total=s["total"],
                allowed=s["allowed"],
                blocked=s["blocked"],
                mismatches=s["mismatches"],
                false_positives=s["false_positives"],
                false_negatives=s["false_negatives"],
            )
        )

    return val_rows, summary_rows, fp, fn


def main() -> None:
    out_dir = ROOT / "artifacts" / "tables"
    out_dir.mkdir(parents=True, exist_ok=True)

    val_rows, summary_rows, fp, fn = run_taxonomy_validation()

    def write_triplet(base: str, rows: list) -> None:
        for ext, fn_write in (
            ("md", to_markdown_table),
            ("csv", to_csv),
            ("tex", lambda r: to_latex_tabular(r)),
        ):
            p = out_dir / f"{base}.{ext}"
            p.write_text(fn_write(rows), encoding="utf-8")
            print(p)

    write_triplet("drift_taxonomy_validation", val_rows)
    write_triplet("drift_taxonomy_summary", summary_rows)
    json_path = out_dir / "drift_taxonomy_summary.json"
    payload = {
        "summary_rows": [r.model_dump() for r in summary_rows],
        "false_positives": fp,
        "false_negatives": fn,
        "trace_count": len(val_rows),
    }
    json_path.write_text(
        __import__("json").dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json_path)


if __name__ == "__main__":
    main()
