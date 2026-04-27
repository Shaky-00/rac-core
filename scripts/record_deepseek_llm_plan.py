"""
Record DeepSeek tool plans into examples/llm_raw_outputs and examples/llm_plans.

Requires openai SDK and DEEPSEEK_API_KEY for non-dry-run (never commit keys).

Run from repository root:
  python scripts/record_deepseek_llm_plan.py --scenario benign_read_summarize --dry-run
  python scripts/record_deepseek_llm_plan.py --all
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SRC = ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from rac_core.demo.deepseek_record import parse_llm_json_raw_content, validate_parsed_steps
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
    parser.add_argument(
        "--stress-test",
        action="store_true",
        help="Record all prompts under examples/llm_prompts/stress_test.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print paths only; no API calls.")
    args = parser.parse_args(argv)

    if not args.scenario and not args.all and not args.stress_test:
        parser.error("Provide --scenario NAME, --all, or --stress-test")

    prompt_root = _resolve_under_repo(ROOT, args.prompt_dir, ROOT / "examples" / "llm_prompts")
    raw_root = _resolve_under_repo(ROOT, args.raw_output_dir, ROOT / "examples" / "llm_raw_outputs")
    plan_root = _resolve_under_repo(ROOT, args.plan_dir, ROOT / "examples" / "llm_plans")

    valid = set(ALL_SCENARIOS)
    if args.stress_test:
        prompt_root = _resolve_under_repo(
            ROOT, args.prompt_dir, ROOT / "examples" / "llm_prompts" / "stress_test"
        )
        raw_root = _resolve_under_repo(
            ROOT, args.raw_output_dir, ROOT / "examples" / "llm_raw_outputs" / "stress_test"
        )
        plan_root = _resolve_under_repo(
            ROOT, args.plan_dir, ROOT / "examples" / "llm_plans" / "stress_test"
        )
        prompts = sorted(prompt_root.glob("*.txt"))
        if not prompts:
            parser.error(f"No stress-test prompts found in {prompt_root}")
        scenarios = [p.stem for p in prompts]
        if args.dry_run:
            for sc in scenarios:
                print(f"[dry-run][stress] scenario={sc}")
                print(prompt_root / f"{sc}.txt")
                print(raw_root / f"{sc}.json")
                print(plan_root / f"{sc}.json")
            return 0

        if not os.environ.get("DEEPSEEK_API_KEY"):
            parser.error("DEEPSEEK_API_KEY must be set for live --stress-test recording.")
        try:
            from openai import OpenAI  # type: ignore
        except ImportError as exc:
            raise SystemExit("Please install openai: pip install openai") from exc

        raw_root.mkdir(parents=True, exist_ok=True)
        plan_root.mkdir(parents=True, exist_ok=True)
        client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")

        for sc in scenarios:
            prompt_path = prompt_root / f"{sc}.txt"
            prompt_text = prompt_path.read_text(encoding="utf-8")
            raw_path = raw_root / f"{sc}.json"
            plan_path = plan_root / f"{sc}.json"

            completion = client.chat.completions.create(
                model=args.model,
                messages=[{"role": "user", "content": prompt_text}],
                temperature=0,
            )
            raw_content = completion.choices[0].message.content or ""

            parse_error: str | None = None
            steps: list[dict[str, object]] = []
            try:
                parsed = parse_llm_json_raw_content(raw_content)
                steps = validate_parsed_steps(parsed)  # type: ignore[arg-type]
            except Exception as exc:  # noqa: BLE001
                parse_error = str(exc)

            raw_doc = {
                "scenario_name": sc,
                "provider": "deepseek",
                "model": args.model,
                "prompt_file": str(prompt_path.relative_to(ROOT)).replace("\\", "/"),
                "raw_content": raw_content,
                "parse_error": parse_error,
                "parsed": {"steps": steps},
            }
            raw_path.write_text(json.dumps(raw_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            if parse_error is None:
                plan_doc = {
                    "scenario_name": sc,
                    "task": prompt_text.strip(),
                    "planner": "replay",
                    "recorded_from": "deepseek",
                    "model": args.model,
                    "provider": "deepseek",
                    "raw_output_file": str(raw_path.relative_to(ROOT)).replace("\\", "/"),
                    "prompt_file": str(prompt_path.relative_to(ROOT)).replace("\\", "/"),
                    "notes": "Recorded via --stress-test",
                    "steps": steps,
                }
                plan_path.write_text(
                    json.dumps(plan_doc, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )

            print(raw_path)
            if parse_error is None:
                print(plan_path)
            else:
                print(f"[parse_error] {sc}: {parse_error}")
        return 0

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
