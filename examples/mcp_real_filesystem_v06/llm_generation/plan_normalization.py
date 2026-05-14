"""Validate and normalize DeepSeek-style planner JSON for ``planner_runner`` replay."""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any

from rac_core.adapter import EventConstructionError

from examples.mcp_real_filesystem_v06.real_filesystem_adapter import (
    SandboxResourceMapper,
    build_fs_manifest_registry,
)
from examples.mcp_real_filesystem_v06.run_real_filesystem_case import prepare_sandbox

RUNNER_PLAN_KEYS = frozenset(
    {
        "plan_id",
        "description",
        "expected_final_decision",
        "grant_extra_resource_ids",
        "steps",
    }
)
RUNNER_STEP_KEYS = frozenset({"step_id", "tool_name", "arguments", "expected_decision"})

ALLOWED_GRANT_EXTRAS = frozenset({"dir_out"})

# Path substrings after {{sandbox}}/ that SandboxResourceMapper accepts (relative keys).
_ALLOWED_REL_KEYS = frozenset(
    {
        "file_A.txt",
        "file_B.txt",
        "out/leak.txt",
        "out/leak2.txt",
        "out",
        "",
        ".",
    }
)

# Documented for DeepSeek prompts (must use {{sandbox}} template in JSON).
ALLOWED_PATH_TEMPLATES_FOR_PROMPTS: tuple[str, ...] = (
    "{{sandbox}}/file_A.txt",
    "{{sandbox}}/file_B.txt",
    "{{sandbox}}/out",
    "{{sandbox}}/out/leak.txt",
    "{{sandbox}}/out/leak2.txt",
    "{{sandbox}}",
)


def filesystem_runner_tool_names() -> list[str]:
    return build_fs_manifest_registry().list_tool_names()


def _sandbox_rel_path(path_val: str, sandbox_root: Path) -> str:
    """Relative path under sandbox (posix-style) or raise."""
    root = sandbox_root.resolve()
    if "{{sandbox}}" in path_val:
        resolved = path_val.replace("{{sandbox}}", str(root))
    else:
        resolved = path_val
    p = Path(resolved).resolve()
    rel = str(p.relative_to(root)).replace("\\", "/").lstrip("./")
    if rel == ".":
        return ""
    return rel


def validate_arguments_map_to_sandbox(
    tool_name: str,
    arguments: dict[str, Any],
    sandbox_root: Path,
) -> None:
    mapper = SandboxResourceMapper(sandbox_root)
    if tool_name in ("read_file", "write_file", "list_directory"):
        raw = arguments.get("path") or arguments.get("file_path") or arguments.get("directory")
        if raw is None or not isinstance(raw, str):
            raise ValueError(f"{tool_name} requires a string path-like argument")
        if "{{sandbox}}" not in raw:
            raise ValueError(f"{tool_name} path must use {{{{sandbox}}}} template, got {raw!r}")
        rel = _sandbox_rel_path(raw, sandbox_root)
        if rel not in _ALLOWED_REL_KEYS:
            raise ValueError(f"path not in allowed replay corpus templates: {raw!r} (rel={rel!r})")
        mapper.path_to_resource_ids(raw.replace("{{sandbox}}", str(sandbox_root.resolve())))
        return
    if tool_name == "search_files":
        raw = arguments.get("path") or arguments.get("directory") or arguments.get("rootPath")
        if raw is None:
            raw = "{{sandbox}}"
        if not isinstance(raw, str):
            raise ValueError("search_files path must be str")
        if "{{sandbox}}" not in raw:
            raise ValueError("search_files path must use {{sandbox}} template for corpus plans")
        rel = _sandbox_rel_path(raw, sandbox_root)
        if rel not in _ALLOWED_REL_KEYS:
            raise ValueError(f"search_files path not allowed: {raw!r} (rel={rel!r})")
        mapper.path_to_resource_ids(raw.replace("{{sandbox}}", str(sandbox_root.resolve())))
        return
    if tool_name == "read_multiple_files":
        paths_val = arguments.get("paths") or arguments.get("files")
        if not isinstance(paths_val, list) or not paths_val:
            raise ValueError("read_multiple_files needs non-empty paths/files list")
        resolved_paths: list[str] = []
        for item in paths_val:
            if not isinstance(item, str):
                raise ValueError("read_multiple_files paths must be strings")
            if "{{sandbox}}" not in item:
                raise ValueError("each read_multiple_files path must use {{sandbox}} template")
            rel = _sandbox_rel_path(item, sandbox_root)
            if rel not in _ALLOWED_REL_KEYS:
                raise ValueError(f"read_multiple_files path not allowed: {item!r}")
            resolved_paths.append(item.replace("{{sandbox}}", str(sandbox_root.resolve())))
        mapper.paths_to_resource_ids(resolved_paths)
        return
    raise ValueError(f"unsupported tool_name for corpus validation: {tool_name}")


def validate_plan_with_temp_sandbox(plan: dict[str, Any]) -> list[str]:
    """Return a list of human-readable errors (empty if valid)."""
    errors: list[str] = []
    allowed_tools = frozenset(filesystem_runner_tool_names())

    pid = plan.get("plan_id")
    if not isinstance(pid, str) or not pid.startswith("llm_norm_"):
        errors.append("plan_id must be a string starting with llm_norm_")

    desc = plan.get("description")
    if desc is not None and not isinstance(desc, str):
        errors.append("description must be a string if present")

    extras = plan.get("grant_extra_resource_ids", [])
    if not isinstance(extras, list):
        errors.append("grant_extra_resource_ids must be a list")
    else:
        for e in extras:
            if e not in ALLOWED_GRANT_EXTRAS:
                errors.append(f"unsupported grant_extra_resource_ids entry: {e!r}")

    steps = plan.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append("steps must be a non-empty list")
        return errors

    step_ids: list[str] = []
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append(f"step {i} must be an object")
            continue
        sid = step.get("step_id")
        if not isinstance(sid, str) or not sid.strip():
            errors.append(f"step {i}: step_id must be a non-empty string")
        else:
            step_ids.append(sid)
        tool = step.get("tool_name")
        if not isinstance(tool, str) or tool not in allowed_tools:
            errors.append(f"step {i}: invalid tool_name {tool!r}")
        args = step.get("arguments")
        if not isinstance(args, dict):
            errors.append(f"step {i}: arguments must be an object")
            continue
        exp = step.get("expected_decision")
        if exp not in ("ALLOW", "BLOCK"):
            errors.append(f"step {i}: expected_decision must be ALLOW or BLOCK")
        if isinstance(tool, str) and tool == "write_file":
            if "content" not in args:
                errors.append(f"step {i}: write_file requires content")

    if len(step_ids) != len(set(step_ids)):
        errors.append("step_id values must be unique")

    if errors:
        return errors

    tmp = Path(tempfile.mkdtemp(prefix="rac_norm_validate_"))
    try:
        sandbox_root, *_ = prepare_sandbox(tmp / "wrap")
        for i, step in enumerate(steps):
            tool = str(step["tool_name"])
            args = dict(step["arguments"])
            try:
                validate_arguments_map_to_sandbox(tool, args, sandbox_root)
            except (ValueError, EventConstructionError) as exc:
                errors.append(f"step {i} path/tool args: {exc}")
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)

    return errors


def normalize_plan_dict(
    raw: dict[str, Any],
    *,
    scenario_id: str,
    manual_semantic_edit: bool = False,
) -> tuple[dict[str, Any], list[str], bool]:
    """Strip unknown fields; enforce plan_id ``llm_norm_<scenario_id>``.

    Returns ``(normalized_plan, auto_fix_notes, manual_semantic_edit_flag)``.
    """
    fixes: list[str] = []
    expected_pid = f"llm_norm_{scenario_id}"
    src = dict(raw)
    if src.get("plan_id") != expected_pid:
        fixes.append(f"plan_id corrected to {expected_pid!r}")
        src["plan_id"] = expected_pid

    out: dict[str, Any] = {
        "plan_id": expected_pid,
        "description": str(src.get("description") or f"LLM-shaped corpus scenario {scenario_id}"),
        "expected_final_decision": str(src.get("expected_final_decision") or "ALLOW"),
        "grant_extra_resource_ids": list(src.get("grant_extra_resource_ids") or []),
        "steps": [],
    }
    if out["expected_final_decision"] not in ("ALLOW", "BLOCK"):
        out["expected_final_decision"] = "ALLOW"
        fixes.append("expected_final_decision coerced to ALLOW")

    steps = src.get("steps") or []
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        st_out: dict[str, Any] = {
            "step_id": str(step.get("step_id") or f"S{i+1:02d}"),
            "tool_name": str(step["tool_name"]),
            "arguments": dict(step.get("arguments") or {}),
            "expected_decision": str(step.get("expected_decision") or "ALLOW"),
        }
        if st_out["expected_decision"] not in ("ALLOW", "BLOCK"):
            st_out["expected_decision"] = "ALLOW"
            fixes.append(f"step {st_out['step_id']}: expected_decision coerced to ALLOW")
        # Normalize path strings: ensure {{sandbox}} prefix when pointing at known files
        args = st_out["arguments"]
        for key, val in list(args.items()):
            if key in ("path", "file_path", "directory", "rootPath") and isinstance(val, str):
                if val.startswith("sandbox/"):
                    args[key] = "{{sandbox}}/" + val[len("sandbox/") :]
                    fixes.append(f"step {st_out['step_id']}: prefixed {{sandbox}} for {key}")
                m = re.match(r"^file_([AB])\.txt$", val)
                if m:
                    args[key] = f"{{{{sandbox}}}}/file_{m.group(1)}.txt"
                    fixes.append(f"step {st_out['step_id']}: expanded bare filename for {key}")
        out["steps"].append(st_out)

    manual_flag = bool(src.get("manual_semantic_edit")) or manual_semantic_edit
    return out, fixes, manual_flag


def strip_runner_only_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON-serializable dict containing only keys accepted for replay JSON files."""
    cleaned: dict[str, Any] = {
        "plan_id": plan["plan_id"],
        "description": plan["description"],
        "expected_final_decision": plan["expected_final_decision"],
        "grant_extra_resource_ids": list(plan.get("grant_extra_resource_ids") or []),
        "steps": [
            {
                "step_id": s["step_id"],
                "tool_name": s["tool_name"],
                "arguments": dict(s["arguments"]),
                "expected_decision": s["expected_decision"],
            }
            for s in plan["steps"]
        ],
    }
    return cleaned


def extract_plan_from_raw_envelope(envelope: dict[str, Any]) -> dict[str, Any] | None:
    """Obtain candidate plan dict from a saved generation envelope."""
    if isinstance(envelope.get("parsed_plan"), dict):
        return dict(envelope["parsed_plan"])
    raw_txt = envelope.get("raw_response_text")
    if isinstance(raw_txt, str) and raw_txt.strip():
        try:
            return json.loads(raw_txt.strip())
        except json.JSONDecodeError:
            return None
    return None
