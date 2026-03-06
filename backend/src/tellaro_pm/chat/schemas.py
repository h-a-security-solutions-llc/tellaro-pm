"""Pydantic schemas for chat session and message endpoints."""

from enum import StrEnum

from pydantic import BaseModel, Field


class ScopeType(StrEnum):
    """Scope types that a chat session can be bound to."""

    project = "project"
    task = "task"
    subtask = "subtask"
    freeform = "freeform"


class SenderType(StrEnum):
    """Who sent a chat message."""

    user = "user"
    agent = "agent"
    system = "system"


class MentionType(StrEnum):
    """Types of @-mention targets."""

    user = "user"
    agent = "agent"
    persona = "persona"
    skill = "skill"


# ---------------------------------------------------------------------------
# Chat Sessions
# ---------------------------------------------------------------------------


class ChatSessionCreate(BaseModel):
    scope_type: ScopeType
    scope_id: str | None = None
    title: str = ""
    working_directory: str | None = None
    agent_id: str | None = None
    persona_id: str | None = None


class ChatSessionUpdate(BaseModel):
    title: str | None = None
    is_archived: bool | None = None


class ChatSessionResponse(BaseModel):
    id: str
    scope_type: ScopeType
    scope_id: str | None = None
    title: str
    working_directory: str | None = None
    agent_id: str | None = None
    persona_id: str | None = None
    participant_ids: list[str] = Field(default_factory=list)
    is_archived: bool
    created_at: str
    updated_at: str


class ChatSessionListResponse(BaseModel):
    items: list[ChatSessionResponse]
    total: int


# ---------------------------------------------------------------------------
# Chat Messages
# ---------------------------------------------------------------------------


class Mention(BaseModel):
    type: MentionType
    name: str
    target_id: str | None = None


class ChatMessageCreate(BaseModel):
    session_id: str
    content: str = Field(min_length=1)
    sender_type: SenderType = SenderType.user


class ChatMessageResponse(BaseModel):
    id: str
    session_id: str
    sender_type: SenderType
    sender_id: str
    content: str
    mentions: list[Mention] = Field(default_factory=lambda: list[Mention]())
    created_at: str


class ChatMessageListResponse(BaseModel):
    items: list[ChatMessageResponse]
    total: int
