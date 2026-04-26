from pydantic import BaseModel, Field


DEFAULT_ACTION_LATTICE: dict[str, set[str]] = {
    "read": {"read", "summarize", "derived_compute"},
    "summarize": {"summarize", "derived_compute"},
    "derived_compute": {"derived_compute"},
    "write": {"write"},
    "external_disclosure": {"external_disclosure"},
    "delete": {"delete"},
}


class ActionLattice(BaseModel):
    lattice: dict[str, set[str]] = Field(
        default_factory=lambda: {k: set(v) for k, v in DEFAULT_ACTION_LATTICE.items()}
    )

    def downstream_allowed_actions(self, action: str) -> set[str]:
        return set(self.lattice.get(action, {action}))

    def is_action_allowed(self, event_action: str, inherited_actions: set[str]) -> bool:
        for action in inherited_actions:
            if event_action in self.downstream_allowed_actions(action):
                return True
        return False
