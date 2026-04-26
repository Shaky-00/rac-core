from pydantic import BaseModel, Field


class SessionContext(BaseModel):
    session_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    agent_id: str | None = None
    tenant: str | None = None
    organization: str | None = None
    roles: set[str] = Field(default_factory=set)
    effective_subject: str | None = None

    def subject_id(self) -> str:
        if self.effective_subject:
            return self.effective_subject
        return self.user_id
