from __future__ import annotations

from rac_core.verification import OutputAnchorVerifier, ToolOutputAnchorClaim

from .models import DemoToolResult


class LocalToolRuntime:
    """Local deterministic tool execution; RAC decisions live in the controller."""

    def __init__(
        self,
        files: dict[str, str],
        internal_recipients: set[str] | None = None,
        external_recipients: set[str] | None = None,
    ) -> None:
        self._files = dict(files)
        self.internal_recipients = set(internal_recipients or ())
        self.external_recipients = set(external_recipients or ())
        self._hash = OutputAnchorVerifier()

    def read_file(self, file_id: str, event_id: str) -> DemoToolResult:
        if file_id not in self._files:
            raise ValueError(f"Unknown file_id: {file_id}")
        actual_output: dict[str, object] = {
            "file_id": file_id,
            "content": self._files[file_id],
        }
        observed = {file_id}
        claim = ToolOutputAnchorClaim(
            anchor_id=f"out:{event_id}",
            producer_event_id=event_id,
            content_hash=self._hash.compute_content_hash(actual_output),
            resource_ids=observed,
            output_type="file_content",
        )
        return DemoToolResult(
            actual_output=actual_output,
            anchor_claim=claim,
            observed_resource_ids=observed,
        )

    def summarize_file(
        self,
        *,
        source_content: object,
        source_resource_ids: set[str],
        event_id: str,
    ) -> DemoToolResult:
        summary = "summary:" + ",".join(sorted(source_resource_ids))
        actual_output: dict[str, object] = {
            "summary": summary,
            "source_resource_ids": sorted(source_resource_ids),
        }
        observed = set(source_resource_ids)
        claim = ToolOutputAnchorClaim(
            anchor_id=f"out:{event_id}",
            producer_event_id=event_id,
            content_hash=self._hash.compute_content_hash(actual_output),
            resource_ids=observed,
            output_type="summary",
        )
        return DemoToolResult(
            actual_output=actual_output,
            anchor_claim=claim,
            observed_resource_ids=observed,
            metadata={
                "source_shape": type(source_content).__name__,
                "source_resource_ids": sorted(source_resource_ids),
            },
        )

    def create_email_draft(
        self, recipient: str, body: object, event_id: str
    ) -> DemoToolResult:
        actual_output: dict[str, object] = {
            "draft_id": f"draft:{event_id}",
            "recipient": recipient,
            "body": body,
        }
        observed = {recipient}
        claim = ToolOutputAnchorClaim(
            anchor_id=f"out:{event_id}",
            producer_event_id=event_id,
            content_hash=self._hash.compute_content_hash(actual_output),
            resource_ids=observed,
            output_type="email_draft",
        )
        return DemoToolResult(
            actual_output=actual_output,
            anchor_claim=claim,
            observed_resource_ids=observed,
            metadata={"external_side_effect": "none", "delivery": "staged_memory_only"},
        )

    def search_documents(self, query: str, event_id: str) -> DemoToolResult:
        query_l = query.lower()
        if "file_b" in query_l or "q2" in query_l:
            results = ["file_B", "file_C"]
        else:
            results = ["file_A"]
        actual_output: dict[str, object] = {"query": query, "results": results}
        observed = set(results)
        claim = ToolOutputAnchorClaim(
            anchor_id=f"out:{event_id}",
            producer_event_id=event_id,
            content_hash=self._hash.compute_content_hash(actual_output),
            resource_ids=observed,
            output_type="search_results",
        )
        return DemoToolResult(
            actual_output=actual_output,
            anchor_claim=claim,
            observed_resource_ids=observed,
            metadata={"result_count": len(results)},
        )

    def create_file(self, file_path: str, content: str, event_id: str) -> DemoToolResult:
        self._files[file_path] = content
        actual_output: dict[str, object] = {"file_path": file_path, "content": content}
        observed = {file_path}
        claim = ToolOutputAnchorClaim(
            anchor_id=f"out:{event_id}",
            producer_event_id=event_id,
            content_hash=self._hash.compute_content_hash(actual_output),
            resource_ids=observed,
            output_type="file_create",
        )
        return DemoToolResult(
            actual_output=actual_output,
            anchor_claim=claim,
            observed_resource_ids=observed,
            metadata={"created_file_path": file_path},
        )
