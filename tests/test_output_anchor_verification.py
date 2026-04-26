from rac_core.models import (
    CausalLineageRecord,
    ResourceMetadata,
    TypedAuthorizationEvent,
    TypedEventResourceScope,
    TypedEventSubject,
)
from rac_core.registry import InMemoryResourceRegistry
from rac_core.store import InMemoryCausalLineageStore
from rac_core.verification import OutputAnchorVerifier, ToolOutputAnchorClaim


def build_event() -> TypedAuthorizationEvent:
    return TypedAuthorizationEvent(
        event_id="evt_1",
        session_id="sess_1",
        step_id="step_1",
        step_seq=1,
        subject=TypedEventSubject(user_id="user_1", effective_subject="user_1"),
        tool_name="summarize_file",
        action="summarize",
        resource_scope=TypedEventResourceScope(type="file", ids={"file_A"}),
        purpose="internal_summarization",
    )


def test_compute_content_hash_deterministic_for_string() -> None:
    verifier = OutputAnchorVerifier()
    output = "summary of file_A"
    assert verifier.compute_content_hash(output) == verifier.compute_content_hash(output)


def test_compute_content_hash_deterministic_for_json_object() -> None:
    verifier = OutputAnchorVerifier()
    obj1 = {"b": 2, "a": 1}
    obj2 = {"a": 1, "b": 2}
    assert verifier.compute_content_hash(obj1) == verifier.compute_content_hash(obj2)


def test_valid_output_anchor_verification_passes() -> None:
    verifier = OutputAnchorVerifier()
    event = build_event()
    actual_output = "summary of file_A"
    observed_resource_ids = {"file_A"}
    claim = ToolOutputAnchorClaim(
        anchor_id="out_1",
        producer_event_id="evt_1",
        content_hash=verifier.compute_content_hash(actual_output),
        resource_ids={"file_A"},
        output_type="file_summary",
    )
    result = verifier.verify_output_anchor(
        anchor_claim=claim,
        actual_output=actual_output,
        event=event,
        observed_resource_ids=observed_resource_ids,
    )
    assert result.valid is True
    assert result.verified_anchor is not None
    assert result.verified_anchor.verified_by_controller is True
    assert result.verified_anchor.session_id == "sess_1"
    assert result.verified_anchor.content_hash == verifier.compute_content_hash(actual_output)
    assert result.verified_anchor.resource_ids == {"file_A"}


def test_content_hash_mismatch_fails() -> None:
    verifier = OutputAnchorVerifier()
    event = build_event()
    actual_output = "summary of file_A"
    claim = ToolOutputAnchorClaim(
        anchor_id="out_1",
        producer_event_id="evt_1",
        content_hash="fake_hash",
        resource_ids={"file_A"},
    )
    result = verifier.verify_output_anchor(
        anchor_claim=claim,
        actual_output=actual_output,
        event=event,
        observed_resource_ids={"file_A"},
    )
    assert result.valid is False
    assert result.rule == "OUTPUT_ANCHOR_INVALID"
    assert result.reason is not None and "content_hash mismatch" in result.reason
    assert result.expected_content_hash is not None
    assert result.claimed_content_hash == "fake_hash"


def test_resource_ids_mismatch_fails() -> None:
    verifier = OutputAnchorVerifier()
    event = build_event()
    actual_output = "summary of file_A"
    claim = ToolOutputAnchorClaim(
        anchor_id="out_1",
        producer_event_id="evt_1",
        content_hash=verifier.compute_content_hash(actual_output),
        resource_ids={"file_A", "file_B"},
    )
    result = verifier.verify_output_anchor(
        anchor_claim=claim,
        actual_output=actual_output,
        event=event,
        observed_resource_ids={"file_A"},
    )
    assert result.valid is False
    assert result.rule == "OUTPUT_ANCHOR_INVALID"
    assert result.reason is not None and "resource_ids mismatch" in result.reason
    assert result.expected_resource_ids == {"file_A"}
    assert result.claimed_resource_ids == {"file_A", "file_B"}


def test_producer_event_id_mismatch_fails() -> None:
    verifier = OutputAnchorVerifier()
    event = build_event()
    actual_output = "summary of file_A"
    claim = ToolOutputAnchorClaim(
        anchor_id="out_1",
        producer_event_id="evt_fake",
        content_hash=verifier.compute_content_hash(actual_output),
        resource_ids={"file_A"},
    )
    result = verifier.verify_output_anchor(
        anchor_claim=claim,
        actual_output=actual_output,
        event=event,
        observed_resource_ids={"file_A"},
    )
    assert result.valid is False
    assert result.reason is not None and "producer_event_id mismatch" in result.reason


def test_unregistered_observed_resource_fails_when_registry_provided() -> None:
    registry = InMemoryResourceRegistry()
    registry.register(ResourceMetadata(resource_id="file_A", resource_type="file"))
    verifier = OutputAnchorVerifier(resource_registry=registry)
    event = build_event()
    actual_output = "summary of file_B"
    claim = ToolOutputAnchorClaim(
        anchor_id="out_1",
        producer_event_id="evt_1",
        content_hash=verifier.compute_content_hash(actual_output),
        resource_ids={"file_B"},
    )
    result = verifier.verify_output_anchor(
        anchor_claim=claim,
        actual_output=actual_output,
        event=event,
        observed_resource_ids={"file_B"},
    )
    assert result.valid is False
    assert result.reason is not None and "observed resource not registered" in result.reason


def test_verified_anchor_can_be_appended_to_lineage_store() -> None:
    verifier = OutputAnchorVerifier()
    event = build_event()
    actual_output = "summary of file_A"
    claim = ToolOutputAnchorClaim(
        anchor_id="out_1",
        producer_event_id="evt_1",
        content_hash=verifier.compute_content_hash(actual_output),
        resource_ids={"file_A"},
    )
    result = verifier.verify_output_anchor(
        anchor_claim=claim,
        actual_output=actual_output,
        event=event,
        observed_resource_ids={"file_A"},
    )
    assert result.valid is True
    assert result.verified_anchor is not None

    store = InMemoryCausalLineageStore()
    record = CausalLineageRecord(
        session_id=event.session_id,
        step_seq=0,
        step_id=event.step_id,
        event_id=event.event_id,
        tool_name=event.tool_name,
        action=event.action,
        resource_ids=set(event.resource_scope.ids),
        resource_type=event.resource_scope.type,
        purpose=event.purpose,
        output_anchor=result.verified_anchor,
        basis_id="basis_1",
    )
    store.append_step(record)
    assert store.get_by_output_anchor("out_1") == record
