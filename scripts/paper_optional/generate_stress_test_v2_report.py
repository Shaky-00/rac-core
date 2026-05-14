"""Generate stress-test v2 replay tables and overwrite canonical outputs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_SRC = ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from pydantic import BaseModel

from rac_core.demo.llm_planner import ReplayLLMPlanner
from rac_core.demo.local_controller import LocalRACController
from rac_core.demo.tools import LocalToolRuntime
from rac_core.models import (
    DecisionType,
    GrantConditions,
    GrantEnvelope,
    GrantSubject,
    ResourceScope,
    SessionContext,
)
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
    blocked_checker: int
    false_positives: int
    false_negatives: int
    event_construction_errors: int


def _load_oracle(path: Path) -> dict[str, dict[str, str]]:
    return json.loads(path.read_text(encoding="utf-8"))


def _collect_rules(run_result) -> list[str]:
    out: list[str] = []
    for step in run_result.steps:
        for v in step.decision.violations:
            out.append(v.rule)
    return out


def _build_grant_for_category(category: str) -> GrantEnvelope:
    allowed_ids = {"file_A", "external@example.com", "internal@example.com"}
    if category == "indirect_resource":
        # Keep file_B out of scope to force checker-side origin failure.
        allowed_ids = {"file_A", "external@example.com", "internal@example.com"}
    return GrantEnvelope(
        grant_id="grant_stress_v2",
        session_id="sess_demo",
        subject=GrantSubject(user_id="user_1", effective_subject="user_1"),
        allowed_actions={"read", "summarize", "external_disclosure"},
        allowed_tools={"read_file", "summarize_file", "create_email_draft"},
        resource_scope=ResourceScope(type="file", allowed_ids=allowed_ids),
        purpose_scope={"internal_summarization", "external_sharing"},
        conditions=GrantConditions(
            environment="trusted_workspace",
            tenant="tenant_X",
            runtime_labels={"internal"},
        ),
    )


def _build_controller(category: str, planner: ReplayLLMPlanner) -> LocalRACController:
    session = SessionContext(
        session_id="sess_demo",
        user_id="user_1",
        agent_id="agent_demo",
        tenant="tenant_X",
        roles={"analyst"},
        effective_subject="user_1",
    )
    files = {
        "file_A": "alpha content for internal report",
        "file_B": "secret other file",
        "file_C": "q2 addendum",
    }
    return LocalRACController(
        grant_envelope=_build_grant_for_category(category),
        session_context=session,
        tool_runtime=LocalToolRuntime(files),
        planner=planner,
    )


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
        ctrl = _build_controller(expected_category, planner)
        run = ctrl.run_scenario(name)
        rules = _collect_rules(run)
        row = StressResultRow(
            plan_name=name,
            category=expected_category,
            num_steps=len(run.steps),
            canonicalization_ok="EVENT_CONSTRUCTION_ERROR" not in set(rules),
            blocked_at_step=run.blocked_at_step,
            observed_decision=run.final_decision.value,
            triggered_rules=";".join(rules),
            expected_category=expected_category,
            expected_outcome=expected_outcome,
        )
        result_rows.append(row)
        per_cat.setdefault(expected_category, []).append(row)

    summary_rows: list[StressSummaryRow] = []
    for category in sorted(per_cat):
        rows = per_cat[category]
        fp = fn = allowed_benign = blocked_checker = ece = 0
        for r in rows:
            benign = r.expected_outcome == "ALLOW"
            obs_allow = r.observed_decision == DecisionType.ALLOW.value
            has_ece = "EVENT_CONSTRUCTION_ERROR" in set(filter(None, r.triggered_rules.split(";")))
            if has_ece:
                ece += 1
            if benign:
                if obs_allow:
                    allowed_benign += 1
                else:
                    fp += 1
            else:
                if obs_allow:
                    fn += 1
                else:
                    blocked_checker += 0 if has_ece else 1
        summary_rows.append(
            StressSummaryRow(
                category=category,
                total_plans=len(rows),
                allowed_benign=allowed_benign,
                blocked_checker=blocked_checker,
                false_positives=fp,
                false_negatives=fn,
                event_construction_errors=ece,
            )
        )

    return result_rows, summary_rows


def main() -> None:
    fixture_dir = ROOT / "examples" / "llm_plans" / "stress_test_v2"
    oracle_path = fixture_dir / "oracle.json"
    out_dir = ROOT / "artifacts" / "generated" / "tables"
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

