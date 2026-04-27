"""Generate Live LLM planner stress-test replay tables."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SRC = ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from pydantic import BaseModel

from rac_core.demo.llm_planner import ReplayLLMPlanner
from rac_core.demo.reporting import make_demo_controller_for_scenario
from rac_core.models import DecisionType
from rac_core.validation import to_csv, to_latex_tabular, to_markdown_table


class StressResultRow(BaseModel):
    plan_name: str
    category: str
    num_steps: int
    canonicalization_ok: bool
    blocked_at_step: str | None
    observed_decision: str
    triggered_rules: str
    expected_category: str
    expected_outcome: str


class StressSummaryRow(BaseModel):
    category: str
    total_plans: int
    allowed_benign: int
    blocked_drift: int
    false_positives: int
    false_negatives: int
    canonicalization_failures: int


def _load_oracle(path: Path) -> dict[str, dict[str, str]]:
    return json.loads(path.read_text(encoding="utf-8"))


def _collect_rules(result) -> list[str]:
    out: list[str] = []
    for step in result.steps:
        for v in step.decision.violations:
            out.append(v.rule)
    return out


def _is_benign(category: str, expected_outcome: str) -> bool:
    return category == "benign_internal" and expected_outcome == "ALLOW"


def build_stress_rows(
    fixture_dir: Path,
    oracle: dict[str, dict[str, str]],
) -> tuple[list[StressResultRow], list[StressSummaryRow]]:
    planner = ReplayLLMPlanner(fixture_dir)
    names = sorted(k for k in planner.list_scenarios() if k != "oracle")

    result_rows: list[StressResultRow] = []
    per_cat: dict[str, list[StressResultRow]] = {}

    for name in names:
        exp = oracle.get(name, {})
        expected_category = str(exp.get("expected_category", "unknown"))
        expected_outcome = str(exp.get("expected_outcome", "BLOCK"))
        ctrl = make_demo_controller_for_scenario(name, planner=planner)
        run = ctrl.run_scenario(name)
        rules = _collect_rules(run)
        canonical_ok = "EVENT_CONSTRUCTION_ERROR" not in set(rules)
        row = StressResultRow(
            plan_name=name,
            category=expected_category,
            num_steps=len(run.steps),
            canonicalization_ok=canonical_ok,
            blocked_at_step=run.blocked_at_step,
            observed_decision=run.final_decision.value,
            triggered_rules=";".join(rules),
            expected_category=expected_category,
            expected_outcome=expected_outcome,
        )
        result_rows.append(row)
        per_cat.setdefault(expected_category, []).append(row)

    summary_rows: list[StressSummaryRow] = []
    for category in sorted(per_cat.keys()):
        rows = per_cat[category]
        false_positives = 0
        false_negatives = 0
        allowed_benign = 0
        blocked_drift = 0
        canon_fail = 0
        for r in rows:
            benign = _is_benign(r.expected_category, r.expected_outcome)
            obs_allow = r.observed_decision == DecisionType.ALLOW.value
            if not r.canonicalization_ok:
                canon_fail += 1
            if benign:
                if obs_allow:
                    allowed_benign += 1
                else:
                    false_positives += 1
            else:
                if obs_allow:
                    false_negatives += 1
                else:
                    blocked_drift += 1
        summary_rows.append(
            StressSummaryRow(
                category=category,
                total_plans=len(rows),
                allowed_benign=allowed_benign,
                blocked_drift=blocked_drift,
                false_positives=false_positives,
                false_negatives=false_negatives,
                canonicalization_failures=canon_fail,
            )
        )

    return result_rows, summary_rows


def main() -> None:
    fixture_dir = ROOT / "examples" / "llm_plans" / "stress_test"
    oracle_path = fixture_dir / "oracle.json"
    out_dir = ROOT / "artifacts" / "tables"
    out_dir.mkdir(parents=True, exist_ok=True)

    oracle = _load_oracle(oracle_path)
    result_rows, summary_rows = build_stress_rows(fixture_dir, oracle)

    def write_triplet(base: str, rows: list[BaseModel]) -> None:
        (out_dir / f"{base}.csv").write_text(to_csv(rows), encoding="utf-8")
        (out_dir / f"{base}.md").write_text(to_markdown_table(rows), encoding="utf-8")
        (out_dir / f"{base}.tex").write_text(to_latex_tabular(rows), encoding="utf-8")
        print(out_dir / f"{base}.csv")
        print(out_dir / f"{base}.md")
        print(out_dir / f"{base}.tex")

    write_triplet("stress_test_results", result_rows)
    write_triplet("stress_test_summary", summary_rows)
    (out_dir / "stress_test_summary.json").write_text(
        json.dumps([r.model_dump() for r in summary_rows], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(out_dir / "stress_test_summary.json")


if __name__ == "__main__":
    main()
