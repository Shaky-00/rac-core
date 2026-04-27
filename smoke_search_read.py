from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from rac_core.demo.local_controller import LocalRACController
from rac_core.demo.scripted_planner import ScriptedPlanner
from rac_core.demo.tools import LocalToolRuntime
from rac_core.models import PendingToolCall, SessionContext
from rac_core.validation.taxonomy_traces import _make_grant


class _SearchReadPlanner(ScriptedPlanner):
    def plan(self, scenario_name: str):
        _ = scenario_name
        return [
            # Adapter reads `results` for resource scope construction.
            PendingToolCall(
                tool_name="search_documents",
                arguments={"query": "find q2 docs", "results": ["file_B", "file_C"]},
            ),
            PendingToolCall(
                tool_name="read_file",
                arguments={"file_id": "file_B", "input_anchor": "previous"},
            ),
        ]


grant = _make_grant(
    session_id="smoke_sess",
    allowed_tools={"search_documents", "read_file"},
    allowed_actions={"read"},
    allowed_ids={"file_A", "file_B", "file_C"},
    purpose_scope={"internal_summarization"},
    environment="trusted_workspace",
    tenant="tenant_X",
)

session = SessionContext(
    session_id="smoke_sess",
    user_id="user_1",
    effective_subject="user_1",
    tenant="tenant_X",
    roles={"analyst"},
)

runtime = LocalToolRuntime(
    {"file_A": "alpha", "file_B": "beta", "file_C": "gamma"},
)
ctrl = LocalRACController(
    grant_envelope=grant,
    session_context=session,
    tool_runtime=runtime,
    planner=_SearchReadPlanner(),
)

result = ctrl.run_scenario("smoke_search_read")
print("Final decision:", result.final_decision.value)
print("Blocked at:", result.blocked_at_step)
for i, step in enumerate(result.steps):
    rules = [v.rule for v in step.decision.violations]
    print(f"step[{i}]={step.step_name} tool={step.pending_tool_call.tool_name} decision={step.decision.decision.value} rules={rules}")