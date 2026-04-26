"""
Record DeepSeek tool plans into examples/llm_raw_outputs and examples/llm_plans.

Requires openai SDK and DEEPSEEK_API_KEY for non-dry-run (never commit keys).

Run from repository root:
  python scripts/record_deepseek_llm_plan.py --scenario benign_read_summarize --dry-run
  python scripts/record_deepseek_llm_plan.py --all
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SRC = ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from rac_core.demo.deepseek_record import (  # noqa: E402
    ALL_SCENARIOS,
    dry_run_record,
    record_scenario_live,
)


def _resolve_under_repo(repo: Path, arg: str | None, default: Path) -> Path:
    if arg is None:
        return default
    p = Path(arg)
    return p if p.is_absolute() else (repo / p)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record DeepSeek LLM tool plans (OpenAI-compatible API).")
    parser.add_argument("--scenario", type=str, help="Scenario stem (e.g. benign_read_summarize).")
    parser.add_argument("--all", action="store_true", help="Record all known scenarios.")
    parser.add_argument("--model", type=str, default="deepseek-chat", help="DeepSeek model name.")
    parser.add_argument("--prompt-dir", type=str, default=None, help="Override prompt directory.")
    parser.add_argument("--raw-output-dir", type=str, default=None, help="Override raw output directory.")
    parser.add_argument("--plan-dir", type=str, default=None, help="Override replay plan directory.")
    parser.add_argument("--dry-run", action="store_true", help="Print paths only; no API calls.")
    args = parser.parse_args(argv)

    if not args.scenario and not args.all:
        parser.error("Provide --scenario NAME or --all")

    prompt_root = _resolve_under_repo(ROOT, args.prompt_dir, ROOT / "examples" / "llm_prompts")
    raw_root = _resolve_under_repo(ROOT, args.raw_output_dir, ROOT / "examples" / "llm_raw_outputs")
    plan_root = _resolve_under_repo(ROOT, args.plan_dir, ROOT / "examples" / "llm_plans")

    valid = set(ALL_SCENARIOS)
    if args.all:
        scenarios = list(ALL_SCENARIOS)
    else:
        if args.scenario not in valid:
            parser.error(
                f"Unknown scenario {args.scenario!r}; expected one of {sorted(valid)}"
            )
        scenarios = [args.scenario]

    if args.dry_run:
        for sc in scenarios:
            lines, paths = dry_run_record(
                ROOT,
                sc,
                prompt_dir=prompt_root,
                raw_output_dir=raw_root,
                plan_dir=plan_root,
            )
            for line in lines:
                print(line)
            for p in paths:
                print(p)
        return 0

    written: list[Path] = []
    for sc in scenarios:
        raw_path, plan_path = record_scenario_live(
            ROOT,
            sc,
            model=args.model,
            prompt_dir=prompt_root,
            raw_output_dir=raw_root,
            plan_dir=plan_root,
        )
        written.extend([raw_path, plan_path])
    for p in written:
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
