from rac_core.models import Decision, DecisionType, Violation
from rac_core.validation import (
    AblationMode,
    AblationStepResult,
    AblationSummary,
    AblationTraceResult,
    ControlledTraceResult,
    TraceStepResult,
    TraceValidationRow,
    abbreviate_rule,
    build_ablation_matrix_rows,
    build_ablation_summary_rows,
    build_trace_validation_rows,
    format_ablation_cell,
    to_csv,
    to_json,
    to_latex_tabular,
    to_markdown_table,
)


def test_abbreviate_rule_known_and_none() -> None:
    assert abbreviate_rule("ACTION_ESCALATION") == "ACT"
    assert abbreviate_rule("RESOURCE_ORIGIN_UNVERIFIABLE") == "ORG"
    assert abbreviate_rule(None) == "—"


def test_format_ablation_cell_variants() -> None:
    fn = AblationStepResult(
        trace_name="t",
        step_name="s",
        mode=AblationMode.NO_RAC,
        observed_decision=DecisionType.ALLOW,
        oracle_decision=DecisionType.BLOCK,
        false_negative=True,
    )
    assert format_ablation_cell(fn) == "FN"

    fp = AblationStepResult(
        trace_name="t",
        step_name="s",
        mode=AblationMode.FULL_RAC,
        observed_decision=DecisionType.BLOCK,
        oracle_decision=DecisionType.ALLOW,
        observed_rules=["ACTION_ESCALATION"],
        false_positive=True,
    )
    assert format_ablation_cell(fp) == "FP"

    block = AblationStepResult(
        trace_name="t",
        step_name="s",
        mode=AblationMode.FULL_RAC,
        observed_decision=DecisionType.BLOCK,
        oracle_decision=DecisionType.BLOCK,
        observed_rules=["ACTION_ESCALATION"],
    )
    assert format_ablation_cell(block) == "B(ACT)"

    allow = AblationStepResult(
        trace_name="t",
        step_name="s",
        mode=AblationMode.FULL_RAC,
        observed_decision=DecisionType.ALLOW,
        oracle_decision=DecisionType.ALLOW,
    )
    assert format_ablation_cell(allow) == "A"


def test_build_trace_validation_rows_single_block_passed() -> None:
    result = ControlledTraceResult(
        name="action-escalation",
        passed=True,
        step_results=[
            TraceStepResult(
                name="step_external",
                decision=Decision(
                    decision=DecisionType.BLOCK,
                    violations=[Violation(rule="ACTION_ESCALATION", reason="escalation")],
                ),
                expected_decision=DecisionType.BLOCK,
                expected_rule="ACTION_ESCALATION",
                passed=True,
                observed_rules=["ACTION_ESCALATION"],
            )
        ],
        blocked_at_step="step_external",
    )
    rows = build_trace_validation_rows([result])
    assert len(rows) == 1
    r0 = rows[0]
    assert r0.trace_id == "T1"
    assert r0.expected == "BLOCK"
    assert r0.full_rac == "BLOCK"
    assert r0.rule == "ACT"
    assert r0.result == "✓"


def test_build_ablation_matrix_rows_full_vs_no_rac() -> None:
    trace_name = "action-escalation"
    full = AblationTraceResult(
        trace_name=trace_name,
        mode=AblationMode.FULL_RAC,
        step_results=[
            AblationStepResult(
                trace_name=trace_name,
                step_name="step_external",
                mode=AblationMode.FULL_RAC,
                observed_decision=DecisionType.BLOCK,
                oracle_decision=DecisionType.BLOCK,
                observed_rules=["ACTION_ESCALATION"],
            )
        ],
        blocked_at_step="step_external",
    )
    no = AblationTraceResult(
        trace_name=trace_name,
        mode=AblationMode.NO_RAC,
        step_results=[
            AblationStepResult(
                trace_name=trace_name,
                step_name="step_external",
                mode=AblationMode.NO_RAC,
                observed_decision=DecisionType.ALLOW,
                oracle_decision=DecisionType.BLOCK,
                false_negative=True,
            )
        ],
    )
    matrix = build_ablation_matrix_rows([full, no], trace_order=[trace_name])
    assert len(matrix) == 1
    m0 = matrix[0]
    assert m0.full_rac == "B(ACT)"
    assert m0.no_rac == "FN"


def test_build_ablation_summary_rows_blocking_rate_percent() -> None:
    summary = AblationSummary(
        mode=AblationMode.FULL_RAC,
        total_steps=10,
        oracle_block_steps=4,
        observed_block_steps=4,
        false_positive_count=0,
        false_negative_count=0,
        drift_blocking_rate=1.0,
    )
    rows = build_ablation_summary_rows([summary])
    assert len(rows) == 1
    assert rows[0].mode == "Full RAC"
    assert rows[0].drift_steps == 4
    assert rows[0].blocked_drift == 4
    assert rows[0].fn == 0
    assert rows[0].fp == 0
    assert rows[0].blocking_rate == "100%"


def test_serialization_helpers_non_empty() -> None:
    rows = [
        TraceValidationRow(
            trace_id="T1",
            trace="Benign",
            workflow="read → summarize",
            expected="ALLOW",
            full_rac="ALLOW",
            rule="—",
            result="✓",
        )
    ]
    csv_out = to_csv(rows)
    assert csv_out
    assert "trace_id" in csv_out
    assert "T1" in csv_out

    json_out = to_json(rows)
    assert json_out
    assert "trace_id" in json_out

    md = to_markdown_table(rows)
    assert md
    assert "trace_id" in md


def test_to_latex_tabular_escape_and_caption() -> None:
    rows = [
        TraceValidationRow(
            trace_id="T1",
            trace="trace_with_underscore",
            workflow="read → summarize",
            expected="ALLOW",
            full_rac="ALLOW",
            rule="RESOURCE_ORIGIN_UNVERIFIABLE",
            result="✓",
        )
    ]
    tex = to_latex_tabular(rows)
    assert "\\begin{tabular}" in tex
    assert "\\end{tabular}" in tex
    assert "trace\\_with\\_underscore" in tex

    tex2 = to_latex_tabular(
        rows,
        caption="RAC validation & results #1",
        label="tab:rac_eval",
    )
    assert "\\caption{" in tex2
    assert "\\label{" in tex2
    assert "\\begin{table}" in tex2
    assert "\\end{table}" in tex2
    assert "\\&" in tex2 or "results" in tex2
