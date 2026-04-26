"""Reproducible evaluation harnesses (latency, scaling, etc.)."""

from rac_core.evaluation.cli_config import (
    LatencyEvalConfig,
    build_latency_eval_config,
    format_latency_eval_config,
)
from rac_core.evaluation.reporting import generate_all_latency_reports
from rac_core.evaluation.latency import (
    LatencySample,
    LatencySummary,
    percentile,
    run_component_breakdown_benchmark,
    run_decision_path_benchmark,
    run_predecessor_resolution_benchmark,
    run_workflow_length_benchmark,
    samples_to_csv,
    summarize_latency,
    summaries_to_csv,
    write_json,
    write_text,
)

__all__ = [
    "LatencyEvalConfig",
    "LatencySample",
    "LatencySummary",
    "build_latency_eval_config",
    "format_latency_eval_config",
    "generate_all_latency_reports",
    "percentile",
    "run_component_breakdown_benchmark",
    "run_decision_path_benchmark",
    "run_predecessor_resolution_benchmark",
    "run_workflow_length_benchmark",
    "samples_to_csv",
    "summarize_latency",
    "summaries_to_csv",
    "write_json",
    "write_text",
]
