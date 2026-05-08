from enum import Enum

from pydantic import BaseModel, Field


class DecisionType(str, Enum):
    """Authorization decision for a pending step.

    The v0.6 prototype :class:`~rac_core.checker.precommit.RACPreCommitChecker` returns
    only ``ALLOW`` and ``BLOCK``. ``ALLOW_WITH_ALERT`` is reserved for forward-compatible
    reporting or future policy hooks; no alert engine is implemented in this repository.
    """

    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    ALLOW_WITH_ALERT = "ALLOW_WITH_ALERT"


class Violation(BaseModel):
    rule: str
    reason: str
    severity: str = "HIGH"
    metadata: dict[str, object] = Field(default_factory=dict)


class Decision(BaseModel):
    decision: DecisionType
    violations: list[Violation] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)
