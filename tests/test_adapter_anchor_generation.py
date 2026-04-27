from __future__ import annotations

from rac_core.demo.local_controller import LocalRACController
from rac_core.demo.models import DemoToolResult
from rac_core.demo.tools import LocalToolRuntime
from rac_core.models import (
    DecisionType,
    GrantConditions,
    GrantEnvelope,
    GrantSubject,
    PendingToolCall,
    ResourceScope,
    SessionContext,
)


class _Plan:
    def __init__(self, calls: list[PendingToolCall]) -> None:
        self._calls = calls

    def plan(self, scenario_name: str) -> list[PendingToolCall]:
        _ = scenario_name
        return self._calls


def _session() -> SessionContext:
    return SessionContext(
        session_id="sess_adapter",
        user_id="user_1",
        effective_subject="user_1",
        tenant="tenant_X",
        roles={"analyst"},
    )


def _grant(
    *,
    tools: set[str],
    actions: set[str],
    ids: set[str],
) -> GrantEnvelope:
    return GrantEnvelope(
        grant_id="grant_adapter",
        session_id="sess_adapter",
        subject=GrantSubject(user_id="user_1", effective_subject="user_1"),
        allowed_actions=actions,
        allowed_tools=tools,
        resource_scope=ResourceScope(type="file", allowed_ids=ids),
        purpose_scope={"internal_summarization"},
        conditions=GrantConditions(
            environment="trusted_workspace",
            tenant="tenant_X",
            runtime_labels={"internal"},
        ),
    )


def test_search_then_read_is_allow_with_verified_anchor_chain() -> None:
    planner = _Plan(
        [
            PendingToolCall(
                tool_name="search_documents",
                arguments={"query": "find q2 docs", "results": ["file_B", "file_C"]},
            ),
            PendingToolCall(
                tool_name="read_file",
                arguments={"file_id": "file_B", "input_anchor": "previous"},
            ),
        ]
    )
    ctrl = LocalRACController(
        grant_envelope=_grant(
            tools={"search_documents", "read_file"},
            actions={"read"},
            ids={"file_B", "file_C"},
        ),
        session_context=_session(),
        tool_runtime=LocalToolRuntime({"file_A": "a", "file_B": "b", "file_C": "c"}),
        planner=planner,
    )
    result = ctrl.run_scenario("search_read_chain")
    assert result.final_decision == DecisionType.ALLOW
    assert len(result.steps) == 2
    assert all(s.decision.decision == DecisionType.ALLOW for s in result.steps)
    assert result.steps[0].verified_anchor is not None
    assert "file_B" in result.steps[0].verified_anchor.resource_ids


def test_create_then_read_new_file_is_allow_with_anchor_chain() -> None:
    planner = _Plan(
        [
            PendingToolCall(
                tool_name="create_file",
                arguments={"file_path": "new_file", "content": "hello world"},
            ),
            PendingToolCall(
                tool_name="read_file",
                arguments={"file_id": "new_file", "input_anchor": "previous"},
            ),
        ]
    )
    ctrl = LocalRACController(
        grant_envelope=_grant(
            tools={"create_file", "read_file"},
            actions={"write", "read"},
            ids={"new_file"},
        ),
        session_context=_session(),
        tool_runtime=LocalToolRuntime({"file_A": "a", "file_B": "b"}),
        planner=planner,
    )
    result = ctrl.run_scenario("create_read_chain")
    assert result.final_decision == DecisionType.ALLOW
    assert len(result.steps) == 2
    assert all(s.decision.decision == DecisionType.ALLOW for s in result.steps)
    assert result.steps[0].verified_anchor is not None
    assert "new_file" in result.steps[0].verified_anchor.resource_ids


def test_search_anchor_missing_resource_then_read_is_blocked() -> None:
    class TamperedRuntime(LocalToolRuntime):
        def search_documents(self, query: str, event_id: str) -> DemoToolResult:
            base = super().search_documents(query, event_id)
            # Simulate incomplete anchor provenance: only file_C is carried forward.
            base.actual_output = {"query": query, "results": ["file_C"]}
            base.observed_resource_ids = {"file_C"}
            base.anchor_claim.resource_ids = {"file_C"}
            base.anchor_claim.content_hash = self._hash.compute_content_hash(base.actual_output)
            return base

    planner = _Plan(
        [
            PendingToolCall(
                tool_name="search_documents",
                arguments={"query": "find q2 docs", "results": ["file_C"]},
            ),
            PendingToolCall(
                tool_name="read_file",
                arguments={"file_id": "file_B", "input_anchor": "previous"},
            ),
        ]
    )
    ctrl = LocalRACController(
        grant_envelope=_grant(
            tools={"search_documents", "read_file"},
            actions={"read"},
            ids={"file_C"},
        ),
        session_context=_session(),
        tool_runtime=TamperedRuntime({"file_A": "a", "file_B": "b", "file_C": "c"}),
        planner=planner,
    )
    result = ctrl.run_scenario("search_missing_origin")
    assert result.final_decision == DecisionType.BLOCK
    assert result.steps[-1].decision.decision == DecisionType.BLOCK
    rules = [v.rule for v in result.steps[-1].decision.violations]
    assert "RESOURCE_ORIGIN_UNVERIFIABLE" in rules
