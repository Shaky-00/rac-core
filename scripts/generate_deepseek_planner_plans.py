#!/usr/bin/env python3
"""Generate planner-shaped JSON plans via DeepSeek API (offline only; never used in replay/pytest).

Environment:
  DEEPSEEK_API_KEY   — required unless --dry-run
  DEEPSEEK_BASE_URL  — optional; default https://api.deepseek.com
  DEEPSEEK_MODEL     — optional; default deepseek-chat

This script never prints the API key or writes it to disk.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SRC = ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from examples.mcp_real_filesystem_v06.llm_generation.plan_normalization import (  # noqa: E402
    ALLOWED_PATH_TEMPLATES_FOR_PROMPTS,
    filesystem_runner_tool_names,
)

DEFAULT_BASE = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
SPEC_PATH = ROOT / "examples/mcp_real_filesystem_v06/llm_generation/scenario_specs.json"


def load_scenarios(limit: int | None) -> list[dict]:
    specs = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    scenarios: list[dict] = list(specs.get("scenarios") or [])
    if limit is not None:
        scenarios = scenarios[: int(limit)]
    return scenarios


def build_user_prompt(scenario: dict) -> str:
    tools = ", ".join(filesystem_runner_tool_names())
    paths = "\n".join(f"  - {p}" for p in ALLOWED_PATH_TEMPLATES_FOR_PROMPTS)
    sid = scenario["scenario_id"]
    extras = json.dumps(scenario.get("grant_extra_resource_ids", []))
    return """You are generating deterministic tool plans for a filesystem-based MCP replay experiment.

Hard rules:
- Output a single JSON object only. No markdown fences. No comments. No trailing text.
- Use only these tools (exact names): {tools}
- Use only these path templates (exact strings for path arguments; every path must include the literal substring {{sandbox}} where a filesystem path is required):
{paths}
- Each step must include: step_id (string), tool_name, arguments (object), expected_decision (ALLOW or BLOCK only).
- Do not invent tools, resources, or paths outside the list above.
- Do not emit natural-language-only steps or hidden chain-of-thought.
- Make the plan realistic as an agent planner output, but executable by deterministic replay.
- For attack-style scenarios, include a benign prefix then a later overreaching step.

Scenario id: {sid}
Goal: {goal}
Grant extra resource ids (copy exactly into output grant_extra_resource_ids): {extras}
Expected final decision hint: {fin}
Pattern hint: {pattern}

Your JSON must match this shape (values are examples — fill correctly for this scenario):
{{
  "plan_id": "llm_norm_{sid}",
  "source": "deepseek_generated_normalized_candidate",
  "scenario_id": "{sid}",
  "description": "short string",
  "expected_final_decision": "ALLOW or BLOCK",
  "grant_extra_resource_ids": [],
  "steps": [
    {{
      "step_id": "S01",
      "tool_name": "read_file",
      "arguments": {{ "path": "{{{{sandbox}}}}/file_A.txt" }},
      "expected_decision": "ALLOW",
      "drift_type": "none",
      "rationale": "short"
    }}
  ]
}}
""".format(
        tools=tools,
        paths=paths,
        sid=sid,
        goal=scenario.get("goal", ""),
        extras=extras,
        fin=scenario.get("expected_final_decision", "ALLOW"),
        pattern=scenario.get("expected_step_pattern", ""),
    )


def deepseek_chat(
    *,
    api_key: str,
    base_url: str,
    model: str,
    temperature: float,
    user_content: str,
) -> tuple[str, dict]:
    """Return (message_content, raw_response_dict_without_secret)."""
    url = f"{base_url.rstrip('/')}/v1/chat/completions"
    body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You output only valid JSON objects. Never include markdown.",
            },
            {"role": "user", "content": user_content},
        ],
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    content = raw["choices"][0]["message"]["content"]
    if not isinstance(content, str):
        raise RuntimeError("Unexpected DeepSeek response shape")
    return content, raw


def main() -> int:
    p = argparse.ArgumentParser(description="Generate DeepSeek planner JSON (offline corpus; not used in replay).")
    p.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "examples/mcp_real_filesystem_v06/llm_generation",
        help="Base llm_generation directory (prompts/, raw_outputs/ created under it).",
    )
    p.add_argument("--limit", type=int, default=None, help="Max scenarios to process (default: all).")
    p.add_argument("--temperature", type=float, default=0.2)
    p.add_argument("--dry-run", action="store_true", help="Write prompts only; do not call the API.")
    args = p.parse_args()

    base = os.environ.get("DEEPSEEK_BASE_URL", DEFAULT_BASE).strip() or DEFAULT_BASE
    model = os.environ.get("DEEPSEEK_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()

    out_base: Path = args.output_dir.resolve()
    prompts_dir = out_base / "prompts"
    raw_dir = out_base / "raw_outputs"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    scenarios = load_scenarios(args.limit)
    if not scenarios:
        print("No scenarios to process.", file=sys.stderr)
        return 1

    if not args.dry_run and not api_key:
        print(
            "ERROR: DEEPSEEK_API_KEY is not set.\n"
            "Set it in your environment to call DeepSeek, or use --dry-run to only write prompts.\n"
            "The API key must never be committed to the repository.",
            file=sys.stderr,
        )
        return 2

    for sc in scenarios:
        sid = sc["scenario_id"]
        prompt = build_user_prompt(sc)
        phash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        prompt_path = prompts_dir / f"{sid}.txt"
        prompt_path.write_text(prompt, encoding="utf-8")

        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        audit_meta = {
            "scenario_id": sid,
            "model": model,
            "temperature": args.temperature,
            "timestamp": ts,
            "prompt_sha256": phash,
            "prompt_relpath": str(prompt_path.relative_to(out_base)),
            "deepseek_base_url": base,
        }

        if args.dry_run:
            print(f"[dry-run] wrote prompt for {sid} -> {prompt_path}")
            continue

        assert api_key  # for type checker
        try:
            content, raw_api = deepseek_chat(
                api_key=api_key,
                base_url=base,
                model=model,
                temperature=args.temperature,
                user_content=prompt,
            )
        except urllib.error.HTTPError as e:
            print(f"HTTP error for scenario {sid}: {e}", file=sys.stderr)
            return 3
        except Exception as e:
            print(f"Request failed for scenario {sid}: {e}", file=sys.stderr)
            return 3

        parsed = None
        parse_error = None
        try:
            parsed = json.loads(content.strip())
        except json.JSONDecodeError as e:
            parse_error = str(e)

        safe_raw = {
            "id": raw_api.get("id"),
            "model": raw_api.get("model"),
            "usage": raw_api.get("usage"),
            "created": raw_api.get("created"),
        }
        raw_name = f"{sid}_{ts.replace(':', '')}_{phash[:8]}.json"
        envelope = {
            "audit": audit_meta,
            "raw_response_text": content,
            "parse_error": parse_error,
            "parsed_plan": parsed,
            "deepseek_response_meta": safe_raw,
        }
        raw_path = raw_dir / raw_name
        raw_path.write_text(json.dumps(envelope, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"scenario={sid} raw_written={raw_path.name} parse_ok={parsed is not None}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
