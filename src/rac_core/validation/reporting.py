from __future__ import annotations

import csv
import io
import json
from typing import Any

from pydantic import BaseModel

from rac_core.models import DecisionType

from .ablation import AblationMode, AblationStepResult, AblationSummary, AblationTraceResult
from .trace import ControlledTraceResult

_RULE_ABBREV: dict[str, str] = {
    "ACTION_ESCALATION": "ACT",
    "RESOURCE_ORIGIN_UNVERIFIABLE": "ORG",
    "RESOURCE_EXPANSION": "RES",
    "PURPOSE_DRIFT": "PUR",
    "DELEGATION_AMPLIFICATION": "DEL",
    "CONDITION_WEAKENING": "COND",
    "LINEAGE_INVALID": "LIN",
    "MULTI_PREDECESSOR_UNSUPPORTED": "MP",
    "LOCAL_DENY": "LOCAL",
    "SESSION_MISMATCH": "SESS",
    "BASIS_NOT_FOUND": "BASIS",
    "BASIS_EMPTY_AFTER_UPDATE": "EMPTY",
}


def abbreviate_rule(rule: str | None) -> str:
    if rule is None:
        return "—"
    return _RULE_ABBREV.get(rule, rule)


def format_decision(decision: DecisionType) -> str:
    if decision == DecisionType.ALLOW:
        return "ALLOW"
    if decision == DecisionType.BLOCK:
        return "BLOCK"
    if decision == DecisionType.ALLOW_WITH_ALERT:
        return "ALERT"
    return str(decision.value)


def format_decision_short(decision: DecisionType) -> str:
    if decision == DecisionType.ALLOW:
        return "A"
    if decision == DecisionType.BLOCK:
        return "B"
    if decision == DecisionType.ALLOW_WITH_ALERT:
        return "W"
    return str(decision.value)


class TraceValidationRow(BaseModel):
    trace_id: str
    trace: str
    workflow: str
    expected: str
    full_rac: str
    rule: str
    result: str


def build_trace_validation_rows(
    results: list[ControlledTraceResult],
    trace_labels: dict[str, tuple[str, str]] | None = None,
) -> list[TraceValidationRow]:
    rows: list[TraceValidationRow] = []
    labels = trace_labels or {}
    for i, result in enumerate(results):
        tid = f"T{i + 1}"
        if not result.step_results:
            rows.append(
                TraceValidationRow(
                    trace_id=tid,
                    trace=result.name,
                    workflow="—",
                    expected="—",
                    full_rac="—",
                    rule="—",
                    result="✗",
                )
            )
            continue
        short_trace, workflow = labels.get(result.name, (result.name, "—"))
        last = result.step_results[-1]
        obs_rules = last.observed_rules
        rule_cell = abbreviate_rule(obs_rules[0]) if obs_rules else "—"
        rows.append(
            TraceValidationRow(
                trace_id=tid,
                trace=short_trace,
                workflow=workflow,
                expected=format_decision(last.expected_decision),
                full_rac=format_decision(last.decision.decision),
                rule=rule_cell,
                result="✓" if result.passed else "✗",
            )
        )
    return rows


class AblationMatrixRow(BaseModel):
    trace: str
    no_rac: str
    entry_only: str
    no_lineage: str
    no_origin: str
    full_rac: str


def format_ablation_cell(step_result: AblationStepResult) -> str:
    if step_result.false_negative:
        return "FN"
    if step_result.false_positive:
        return "FP"
    obs = step_result.observed_decision
    if obs == DecisionType.ALLOW_WITH_ALERT:
        return "W"
    if obs == DecisionType.ALLOW:
        return "A"
    if obs == DecisionType.BLOCK:
        if step_result.observed_rules:
            return f"B({abbreviate_rule(step_result.observed_rules[0])})"
        return "B"
    return format_decision_short(obs)


def build_ablation_matrix_rows(
    results: list[AblationTraceResult],
    trace_order: list[str] | None = None,
    trace_labels: dict[str, str] | None = None,
) -> list[AblationMatrixRow]:
    by_trace: dict[str, dict[AblationMode, AblationTraceResult]] = {}
    for r in results:
        by_trace.setdefault(r.trace_name, {})[r.mode] = r

    names_in_data = list(by_trace.keys())
    if trace_order is not None:
        ordered = list(trace_order)
        for n in names_in_data:
            if n not in ordered:
                ordered.append(n)
        trace_names = ordered
    else:
        trace_names = sorted(names_in_data)

    tlabels = trace_labels or {}
    out: list[AblationMatrixRow] = []

    def cell_for(trace_name: str, mode: AblationMode) -> str:
        tr = by_trace.get(trace_name, {}).get(mode)
        if tr is None or not tr.step_results:
            return "—"
        return format_ablation_cell(tr.step_results[-1])

    for tn in trace_names:
        display = tlabels.get(tn, tn)
        out.append(
            AblationMatrixRow(
                trace=display,
                no_rac=cell_for(tn, AblationMode.NO_RAC),
                entry_only=cell_for(tn, AblationMode.ENTRY_ONLY_CHECK),
                no_lineage=cell_for(tn, AblationMode.RAC_WITHOUT_LINEAGE),
                no_origin=cell_for(tn, AblationMode.RAC_WITHOUT_RESOURCE_ORIGIN),
                full_rac=cell_for(tn, AblationMode.FULL_RAC),
            )
        )
    return out


_MODE_DISPLAY: dict[AblationMode, str] = {
    AblationMode.NO_RAC: "No RAC",
    AblationMode.ENTRY_ONLY_CHECK: "Entry-only",
    AblationMode.RAC_WITHOUT_LINEAGE: "No lineage",
    AblationMode.RAC_WITHOUT_RESOURCE_ORIGIN: "No origin",
    AblationMode.FULL_RAC: "Full RAC",
}


class AblationSummaryRow(BaseModel):
    mode: str
    drift_steps: int
    blocked_drift: int
    fn: int
    fp: int
    blocking_rate: str


def _format_percent(rate: float) -> str:
    pct = int(round(rate * 100))
    pct = max(0, min(100, pct))
    return f"{pct}%"


def build_ablation_summary_rows(summaries: list[AblationSummary]) -> list[AblationSummaryRow]:
    rows: list[AblationSummaryRow] = []
    for s in summaries:
        blocked = max(0, s.oracle_block_steps - s.false_negative_count)
        rows.append(
            AblationSummaryRow(
                mode=_MODE_DISPLAY.get(s.mode, s.mode.value),
                drift_steps=s.oracle_block_steps,
                blocked_drift=blocked,
                fn=s.false_negative_count,
                fp=s.false_positive_count,
                blocking_rate=_format_percent(s.drift_blocking_rate),
            )
        )
    return rows


def rows_to_dicts(rows: list[BaseModel]) -> list[dict[str, Any]]:
    return [r.model_dump() for r in rows]


def to_csv(rows: list[BaseModel]) -> str:
    if not rows:
        return ""
    dicts = rows_to_dicts(rows)
    buf = io.StringIO()
    fieldnames = list(dicts[0].keys())
    w = csv.DictWriter(buf, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(dicts)
    return buf.getvalue()


def to_json(rows: list[BaseModel]) -> str:
    return json.dumps(rows_to_dicts(rows), ensure_ascii=False, indent=2)


def _md_escape_cell(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


def to_markdown_table(rows: list[BaseModel]) -> str:
    if not rows:
        return ""
    dicts = rows_to_dicts(rows)
    keys = list(dicts[0].keys())
    header = "| " + " | ".join(keys) + " |"
    sep = "| " + " | ".join("---" for _ in keys) + " |"
    body_lines = []
    for d in dicts:
        body_lines.append(
            "| " + " | ".join(_md_escape_cell(str(d[k])) for k in keys) + " |"
        )
    return "\n".join([header, sep, *body_lines])


def _latex_escape(s: str) -> str:
    return (
        s.replace("\\", "\\textbackslash{}")
        .replace("_", "\\_")
        .replace("%", "\\%")
        .replace("&", "\\&")
        .replace("#", "\\#")
    )


def to_latex_tabular(
    rows: list[BaseModel],
    *,
    caption: str | None = None,
    label: str | None = None,
) -> str:
    if not rows:
        return ""
    dicts = rows_to_dicts(rows)
    keys = list(dicts[0].keys())
    n = len(keys)
    spec = "l" * n
    lines: list[str] = []
    lines.append(f"\\begin{{tabular}}{{{spec}}}")
    lines.append(" & ".join(_latex_escape(str(k)) for k in keys) + " \\\\")
    for d in dicts:
        lines.append(" & ".join(_latex_escape(str(d[k])) for k in keys) + " \\\\")
    lines.append("\\end{tabular}")
    tabular = "\n".join(lines)
    if caption is None and label is None:
        return tabular
    inner: list[str] = ["\\begin{table}[htbp]", "\\centering"]
    if caption is not None:
        inner.append(f"\\caption{{{_latex_escape(caption)}}}")
    if label is not None:
        inner.append(f"\\label{{{_latex_escape(label)}}}")
    inner.append(tabular)
    inner.append("\\end{table}")
    return "\n".join(inner)
