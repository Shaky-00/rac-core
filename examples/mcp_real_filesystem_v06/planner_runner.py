"""Execute deterministic planner JSON plans against GuardedRealFilesystemClient."""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import shutil
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from rac_core.models import (
    DelegationConstraint,
    GrantConditions,
    GrantEnvelope,
    GrantSubject,
    ResourceScope,
    SessionContext,
)

from examples.mcp_real_filesystem_v06.guarded_real_filesystem_client import (
    GuardedFilesystemResult,
    GuardedRealFilesystemClient,
)
from examples.mcp_real_filesystem_v06.planner_results_export import (
    build_planner_summary,
    write_planner_results_csv,
    write_planner_summary_json,
)
from examples.mcp_real_filesystem_v06.real_filesystem_adapter import validate_required_tools_present
from examples.mcp_real_filesystem_v06.run_real_filesystem_case import (
    prepare_sandbox,
    server_argv_from_env,
)

PLANS_DIR = Path(__file__).resolve().parent / "plans"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[2] / "results"
DEFAULT_CSV_NAME = "mcp_real_filesystem_planner_v06_results.csv"
DEFAULT_SUMMARY_NAME = "mcp_real_filesystem_planner_v06_summary.json"

VARIANT_FULL_RAC = "FULL_RAC"
VARIANT_NO_RAC = "NO_RAC"
DEFAULT_VARIANTS = (VARIANT_FULL_RAC, VARIANT_NO_RAC)


def parse_variants_arg(raw: str | None) -> tuple[str, ...]:
    """Parse comma-separated variant list (e.g. ``FULL_RAC,NO_RAC``)."""
    if raw is None or not str(raw).strip():
        return DEFAULT_VARIANTS
    parts = [p.strip().upper() for p in str(raw).split(",") if p.strip()]
    allowed = {VARIANT_FULL_RAC, VARIANT_NO_RAC}
    for p in parts:
        if p not in allowed:
            raise ValueError(f"Unknown variant {p!r}; allowed: {sorted(allowed)}")
    return tuple(parts)


def describe_server_argv_for_summary(argv: list[str]) -> str:
    """Human-readable launch line: prefix tokens + ``<sandbox_root>`` (each plan uses its own temp dir)."""
    if not argv:
        return ""
    if len(argv) >= 2:
        return " ".join(shlex.quote(x) for x in argv[:-1]) + " <sandbox_root>"
    return " ".join(shlex.quote(x) for x in argv)


def apply_sandbox_template(obj: Any, sandbox_root: Path) -> Any:
    root = str(sandbox_root.resolve())
    if isinstance(obj, str):
        return obj.replace("{{sandbox}}", root)
    if isinstance(obj, dict):
        return {k: apply_sandbox_template(v, sandbox_root) for k, v in obj.items()}
    if isinstance(obj, list):
        return [apply_sandbox_template(x, sandbox_root) for x in obj]
    return obj


def build_plan_grant(session_id: str, extra_resource_ids: list[str] | None) -> GrantEnvelope:
    extra = set(extra_resource_ids or [])
    allowed = {"file_A"} | extra
    return GrantEnvelope(
        grant_id=f"grant:{session_id}",
        session_id=session_id,
        subject=GrantSubject(user_id="analyst_1", tenant="acme", roles={"analyst"}),
        allowed_actions={"read"},
        allowed_tools={
            "read_file",
            "write_file",
            "list_directory",
            "search_files",
            "read_multiple_files",
        },
        resource_scope=ResourceScope(type="file", allowed_ids=allowed),
        purpose_scope={"internal_analysis"},
        delegation=DelegationConstraint(allow_delegation=False),
        conditions=GrantConditions(environment="trusted_workspace", tenant="acme"),
    )


def build_session(session_id: str) -> SessionContext:
    return SessionContext(
        session_id=session_id,
        user_id="analyst_1",
        effective_subject="analyst_1",
        tenant="acme",
        roles={"analyst"},
    )


def _fmt_side_effect(val: bool | str) -> str:
    if isinstance(val, bool):
        return "true" if val else "false"
    return str(val)


def expected_side_effect_exists_field(expected_decision: str, tool_name: str) -> str:
    if tool_name != "write_file":
        return "n/a"
    if expected_decision == "BLOCK":
        return "false"
    return "true"


def row_matched_full_rac(
    *,
    expected_decision: str,
    rac_decision: str,
    server_call_issued: bool,
    expected_side_effect: bool | str,
    actual_side_effect: bool | str,
) -> bool:
    if rac_decision != expected_decision:
        return False
    if expected_decision == "BLOCK":
        if server_call_issued:
            return False
    else:
        if not server_call_issued:
            return False
    if expected_side_effect != "n/a":
        return _fmt_side_effect(actual_side_effect) == _fmt_side_effect(expected_side_effect)
    return True


def security_violation_materialized_field(
    *,
    variant: str,
    expected_decision: str,
    tool_name: str,
    side_effect_exists: bool | str,
) -> str:
    if variant != VARIANT_NO_RAC:
        return "false"
    if expected_decision != "BLOCK" or tool_name != "write_file":
        return "false"
    return "true" if _fmt_side_effect(side_effect_exists) == "true" else "false"


def build_full_rac_row(
    *,
    variant: str,
    plan_id: str,
    step_id: str,
    arguments: dict[str, Any],
    expected_decision: str,
    r: GuardedFilesystemResult,
    side_effect_exists: bool | str,
) -> dict[str, Any]:
    if expected_decision == "BLOCK" and r.tool_name == "write_file":
        expected_side_effect_inner: bool | str = False
    else:
        expected_side_effect_inner = "n/a"
    matched = row_matched_full_rac(
        expected_decision=expected_decision,
        rac_decision=r.rac_decision,
        server_call_issued=r.server_call_issued,
        expected_side_effect=expected_side_effect_inner,
        actual_side_effect=side_effect_exists,
    )
    ese = expected_side_effect_exists_field(expected_decision, r.tool_name)
    svm = security_violation_materialized_field(
        variant=variant,
        expected_decision=expected_decision,
        tool_name=r.tool_name,
        side_effect_exists=side_effect_exists,
    )
    return {
        "variant": variant,
        "plan_id": plan_id,
        "step_id": step_id,
        "tool_name": r.tool_name,
        "arguments": json.dumps(arguments, ensure_ascii=False, sort_keys=True),
        "expected_decision": expected_decision,
        "rac_decision": r.rac_decision,
        "matched_expected": "true" if matched else "false",
        "server_call_issued": "true" if r.server_call_issued else "false",
        "violation_rules": ";".join(r.violation_rules) if r.violation_rules else "",
        "expected_side_effect_exists": ese,
        "side_effect_exists": _fmt_side_effect(side_effect_exists),
        "security_violation_materialized": svm,
    }


def build_no_rac_row(
    *,
    variant: str,
    plan_id: str,
    step_id: str,
    arguments: dict[str, Any],
    expected_decision: str,
    tool_name: str,
    side_effect_exists: bool | str,
    server_call_issued: bool,
) -> dict[str, Any]:
    matched = expected_decision == "ALLOW" and server_call_issued
    ese = expected_side_effect_exists_field(expected_decision, tool_name)
    svm = security_violation_materialized_field(
        variant=variant,
        expected_decision=expected_decision,
        tool_name=tool_name,
        side_effect_exists=side_effect_exists,
    )
    return {
        "variant": variant,
        "plan_id": plan_id,
        "step_id": step_id,
        "tool_name": tool_name,
        "arguments": json.dumps(arguments, ensure_ascii=False, sort_keys=True),
        "expected_decision": expected_decision,
        "rac_decision": "NO_RAC_ALLOW",
        "matched_expected": "true" if matched else "false",
        "server_call_issued": "true" if server_call_issued else "false",
        "violation_rules": "",
        "expected_side_effect_exists": ese,
        "side_effect_exists": _fmt_side_effect(side_effect_exists),
        "security_violation_materialized": svm,
    }


async def run_single_plan(
    plan: dict[str, Any],
    *,
    variant: str,
    output_trace_path: Path | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Run one plan in an isolated temp sandbox with its own MCP stdio session."""
    rows: list[dict[str, Any]] = []
    argv: list[str] = []
    tmp = Path(tempfile.mkdtemp(prefix=f"rac_planner_{plan['plan_id']}_"))
    try:
        sandbox_root, _fa, _fb, _leak = prepare_sandbox(tmp)
        argv = server_argv_from_env(sandbox_root)
        plan_id = str(plan["plan_id"])
        extra = list(plan.get("grant_extra_resource_ids") or [])
        session_token = uuid.uuid4().hex[:8]
        sid = f"planner:{plan_id}:{session_token}"
        grant = build_plan_grant(sid, extra)
        sess = build_session(sid)
        params = StdioServerParameters(command=argv[0], args=argv[1:])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools_res = await session.list_tools()
                names = [t.name for t in tools_res.tools]
                validate_required_tools_present(names)
                if variant == VARIANT_FULL_RAC:
                    client = GuardedRealFilesystemClient(
                        session=session,
                        sandbox_root=sandbox_root,
                        session_context=sess,
                        grant_envelope=grant,
                        trace_jsonl_path=output_trace_path,
                        grant_template_ids=("read_only_retrieval",),
                    )
                    for step in plan["steps"]:
                        step_id = str(step["step_id"])
                        tool_name = str(step["tool_name"])
                        raw_args = dict(step["arguments"])
                        args = apply_sandbox_template(raw_args, sandbox_root)
                        expected_decision = str(step["expected_decision"])
                        case_id = f"{plan_id}:{step_id}"
                        r = await client.guarded_tool_call(
                            case_id=case_id,
                            scenario=str(plan.get("description", plan_id))[:500],
                            expected=expected_decision,
                            tool_name=tool_name,
                            arguments=args,
                            selected_purpose="internal_analysis",
                        )
                        if tool_name == "write_file":
                            pth = Path(str(args.get("path", "")))
                            side_effect_exists: bool | str = pth.exists()
                        else:
                            side_effect_exists = "n/a"
                        rows.append(
                            build_full_rac_row(
                                variant=VARIANT_FULL_RAC,
                                plan_id=plan_id,
                                step_id=step_id,
                                arguments=args,
                                expected_decision=expected_decision,
                                r=r,
                                side_effect_exists=side_effect_exists,
                            )
                        )
                else:
                    for step in plan["steps"]:
                        step_id = str(step["step_id"])
                        tool_name = str(step["tool_name"])
                        raw_args = dict(step["arguments"])
                        args = apply_sandbox_template(raw_args, sandbox_root)
                        expected_decision = str(step["expected_decision"])
                        issued = False
                        try:
                            await session.call_tool(tool_name, arguments=args)
                            issued = True
                        except Exception:
                            issued = False
                        if tool_name == "write_file":
                            pth = Path(str(args.get("path", "")))
                            se = pth.exists()
                        else:
                            se = "n/a"
                        rows.append(
                            build_no_rac_row(
                                variant=VARIANT_NO_RAC,
                                plan_id=plan_id,
                                step_id=step_id,
                                arguments=args,
                                expected_decision=expected_decision,
                                tool_name=tool_name,
                                side_effect_exists=se,
                                server_call_issued=issued,
                            )
                        )
    finally:
        try:
            shutil.rmtree(tmp, ignore_errors=True)
        except OSError:
            pass
    return rows, argv


def load_plans(plans_dir: Path) -> list[dict[str, Any]]:
    paths = sorted(plans_dir.glob("*.json"))
    out: list[dict[str, Any]] = []
    for p in paths:
        out.append(json.loads(p.read_text(encoding="utf-8")))
    return out


async def run_planner_pipeline(
    *,
    output_dir: Path,
    plans_dir: Path | None = None,
    csv_name: str = DEFAULT_CSV_NAME,
    summary_name: str = DEFAULT_SUMMARY_NAME,
    trace_jsonl: Path | None = None,
    variants: tuple[str, ...] | list[str] | None = None,
) -> dict[str, Any]:
    """Run all JSON plans under ``plans_dir`` for each variant; write CSV + summary under ``output_dir``."""
    variants_list = list(variants) if variants is not None else list(DEFAULT_VARIANTS)
    plans_dir = plans_dir or PLANS_DIR
    plans = load_plans(plans_dir)
    all_rows: list[dict[str, Any]] = []
    last_argv: list[str] = []
    if trace_jsonl is not None:
        trace_jsonl.parent.mkdir(parents=True, exist_ok=True)
        trace_jsonl.unlink(missing_ok=True)
    for variant in variants_list:
        trace_for_plan = trace_jsonl if variant == VARIANT_FULL_RAC else None
        for plan in plans:
            rows, argv = await run_single_plan(plan, variant=variant, output_trace_path=trace_for_plan)
            all_rows.extend(rows)
            last_argv = argv
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_p = output_dir / csv_name
    json_p = output_dir / summary_name
    write_planner_results_csv(csv_p, all_rows)
    notes = (
        "Deterministic planner JSON → real filesystem MCP (stdio). "
        "FULL_RAC uses GuardedRealFilesystemClient; NO_RAC bypasses RAC and calls tools directly. "
        "Compare security_violation_materialized and side_effect_exists across variants."
    )
    summary = build_planner_summary(
        all_rows,
        total_plans=len(plans),
        variants=variants_list,
        server_command=describe_server_argv_for_summary(last_argv),
        notes=notes,
    )
    write_planner_summary_json(json_p, summary)
    return {"csv_path": csv_p, "summary_path": json_p, "summary": summary, "rows": all_rows}


def main_sync(
    output_dir: Path | None = None,
    plans_dir: Path | None = None,
    *,
    variants: tuple[str, ...] | list[str] | None = None,
) -> int:
    out = output_dir or DEFAULT_OUTPUT_DIR
    trace = Path(__file__).resolve().parent / "traces" / "mcp_real_filesystem_planner_v06_trace.jsonl"
    v_list = list(variants) if variants is not None else list(DEFAULT_VARIANTS)
    asyncio.run(
        run_planner_pipeline(
            output_dir=out,
            plans_dir=plans_dir,
            trace_jsonl=trace if VARIANT_FULL_RAC in v_list else None,
            variants=tuple(v_list),
        )
    )
    return 0


def cli_entry() -> None:
    """CLI when RAC_REAL_MCP_SERVER_CMD is set (see ``server_argv_from_env``)."""
    import argparse

    p = argparse.ArgumentParser(description="Run planner JSON plans against real filesystem MCP")
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--plans-dir", type=Path, default=None)
    p.add_argument(
        "--variants",
        type=str,
        default=",".join(DEFAULT_VARIANTS),
        help="Comma-separated: FULL_RAC, NO_RAC (default: both).",
    )
    args = p.parse_args()
    if not os.environ.get("RAC_REAL_MCP_SERVER_CMD"):
        print(
            "ERROR: Set RAC_REAL_MCP_SERVER_CMD (and optional RAC_REAL_MCP_SERVER_ARGS).\n",
            file=sys.stderr,
        )
        raise SystemExit(2)
    try:
        v = parse_variants_arg(args.variants)
    except ValueError as e:
        print(f"ERROR: {e}\n", file=sys.stderr)
        raise SystemExit(2) from e
    raise SystemExit(
        main_sync(output_dir=args.output_dir, plans_dir=args.plans_dir, variants=v)
    )
