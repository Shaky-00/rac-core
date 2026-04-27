"""Generate adapter/anchor strategy evidence table for paper."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SRC = ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from pydantic import BaseModel

from rac_core.demo.reporting import make_demo_controller_for_scenario
from rac_core.models import DecisionType
from rac_core.validation import to_csv, to_latex_tabular, to_markdown_table


class AdapterStrategyRow(BaseModel):
    tool_class: str
    example_tools: str
    anchor_generation_strategy: str
    tool_modification_required: str
    supported_in_prototype: str


class AdapterDemoRow(BaseModel):
    workflow: str
    observed_decision: str
    blocked_at_step: str


def main() -> None:
    out_dir = ROOT / "artifacts" / "tables"
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = [
        AdapterStrategyRow(
            tool_class="read/retrieve",
            example_tools="read_file",
            anchor_generation_strategy="Hash returned content; record observed resource_ids",
            tool_modification_required="No",
            supported_in_prototype="Yes",
        ),
        AdapterStrategyRow(
            tool_class="transform/summarize",
            example_tools="summarize_file",
            anchor_generation_strategy="Derive from input anchors; hash transformed output",
            tool_modification_required="No",
            supported_in_prototype="Yes",
        ),
        AdapterStrategyRow(
            tool_class="search/list",
            example_tools="search_documents",
            anchor_generation_strategy="Parse returned resource_ids into verified anchor",
            tool_modification_required="No (adapter parses output)",
            supported_in_prototype="Yes",
        ),
        AdapterStrategyRow(
            tool_class="write/create",
            example_tools="create_file",
            anchor_generation_strategy="Extract new resource from args; hash created content",
            tool_modification_required="No",
            supported_in_prototype="Yes",
        ),
        AdapterStrategyRow(
            tool_class="external action",
            example_tools="create_email_draft",
            anchor_generation_strategy="Enforce lattice pre-commit; no downstream anchor on block",
            tool_modification_required="No",
            supported_in_prototype="Yes",
        ),
    ]

    (out_dir / "adapter_strategy.csv").write_text(to_csv(rows), encoding="utf-8")
    (out_dir / "adapter_strategy.md").write_text(to_markdown_table(rows), encoding="utf-8")
    (out_dir / "adapter_strategy.tex").write_text(to_latex_tabular(rows), encoding="utf-8")
    print(out_dir / "adapter_strategy.csv")
    print(out_dir / "adapter_strategy.md")
    print(out_dir / "adapter_strategy.tex")

    demo = make_demo_controller_for_scenario("search_read_summarize").run_scenario(
        "search_read_summarize"
    )
    demo_row = [
        AdapterDemoRow(
            workflow="search -> read -> summarize",
            observed_decision=demo.final_decision.value,
            blocked_at_step=demo.blocked_at_step or "None",
        )
    ]
    (out_dir / "adapter_strategy_demo.csv").write_text(to_csv(demo_row), encoding="utf-8")
    (out_dir / "adapter_strategy_demo.md").write_text(
        to_markdown_table(demo_row), encoding="utf-8"
    )
    (out_dir / "adapter_strategy_demo.tex").write_text(
        to_latex_tabular(demo_row), encoding="utf-8"
    )
    print(out_dir / "adapter_strategy_demo.csv")
    print(out_dir / "adapter_strategy_demo.md")
    print(out_dir / "adapter_strategy_demo.tex")

    if demo.final_decision != DecisionType.ALLOW:
        raise SystemExit("search_read_summarize demo expected ALLOW")


if __name__ == "__main__":
    main()
