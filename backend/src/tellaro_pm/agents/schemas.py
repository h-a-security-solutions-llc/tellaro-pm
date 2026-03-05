"""Pydantic schemas for agent management, personas, work items, and work requests."""

from enum import StrEnum

from pydantic import BaseModel, Field

# --- Agent ---


class AgentStatus(StrEnum):
    """Agent connection/availability status."""

    ONLINE = "online"
    OFFLINE = "offline"
    BUSY = "busy"


class AgentRegister(BaseModel):
    """Payload sent by an agent daemon when it first connects."""

    name: str = Field(min_length=1, max_length=128)
    machine_info: dict[str, object] = Field(default_factory=dict)
    capabilities: list[str] = Field(default_factory=list)


class AgentHeartbeat(BaseModel):
    """Periodic heartbeat sent by an agent to report status."""

    status: AgentStatus
    active_work_item_ids: list[str] = Field(default_factory=list)


class AgentResponse(BaseModel):
    """Public representation of a registered agent."""

    id: str
    user_id: str
    name: str
    status: AgentStatus
    machine_info: dict[str, object]
    last_heartbeat: str | None = None
    capabilities: list[str]
    personas: list["PersonaResponse"] = []
    created_at: str
    updated_at: str


class AgentListResponse(BaseModel):
    """Paginated list of agents."""

    items: list[AgentResponse]
    total: int


# --- Persona ---


class PersonaCreate(BaseModel):
    """Create a new persona configuration for an agent."""

    name: str = Field(min_length=1, max_length=128)
    role_description: str = Field(min_length=1, max_length=4096)
    system_prompt: str = Field(default="", max_length=32768)
    skills: list[str] = Field(default_factory=list)
    claude_profile: str = Field(default="", max_length=256)


class PersonaUpdate(BaseModel):
    """Partial update to an existing persona."""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    role_description: str | None = Field(default=None, min_length=1, max_length=4096)
    system_prompt: str | None = Field(default=None, max_length=32768)
    skills: list[str] | None = None
    claude_profile: str | None = Field(default=None, max_length=256)
    is_active: bool | None = None


class PersonaResponse(BaseModel):
    """Public representation of a persona."""

    id: str
    agent_id: str
    user_id: str
    name: str
    role_description: str
    system_prompt: str
    skills: list[str]
    claude_profile: str
    is_active: bool
    created_at: str
    updated_at: str


# --- Work Item ---


class WorkItemStatus(StrEnum):
    """Lifecycle status of a dispatched work item."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkItemCreate(BaseModel):
    """Dispatch a new work item to an agent."""

    task_id: str | None = None
    instruction: str = Field(min_length=1, max_length=65536)
    agent_id: str = Field(min_length=1)
    persona_id: str = Field(min_length=1)
    working_directory: str | None = None
    chat_session_id: str | None = None
    chat_message_id: str | None = None


class WorkItemUpdate(BaseModel):
    """Update a work item's status, output, or artifacts."""

    status: WorkItemStatus | None = None
    output: str | None = None
    artifacts: list[dict[str, object]] | None = None


class WorkItemResponse(BaseModel):
    """Public representation of a work item."""

    id: str
    task_id: str | None = None
    chat_session_id: str | None = None
    chat_message_id: str | None = None
    agent_id: str
    persona_id: str
    status: WorkItemStatus
    instruction: str
    working_directory: str | None = None
    output: str | None = None
    artifacts: list[dict[str, object]] = []
    started_at: str | None = None
    completed_at: str | None = None
    created_at: str
    updated_at: str


class WorkItemListResponse(BaseModel):
    """Paginated list of work items."""

    items: list[WorkItemResponse]
    total: int


# --- Work Request (cross-user) ---


class WorkRequestStatus(StrEnum):
    """Approval status of a cross-user work request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"


class WorkRequestCreate(BaseModel):
    """Request work on another user's agent."""

    target_user_id: str = Field(min_length=1)
    task_id: str | None = None
    instruction: str = Field(min_length=1, max_length=65536)


class WorkRequestReject(BaseModel):
    """Body for rejecting a work request."""

    message: str = Field(default="", max_length=4096)


class WorkRequestResponse(BaseModel):
    """Public representation of a cross-user work request."""

    id: str
    requester_id: str
    target_user_id: str
    task_id: str | None = None
    instruction: str
    status: WorkRequestStatus
    response_message: str | None = None
    work_item_id: str | None = None
    created_at: str
    updated_at: str


class WorkRequestListResponse(BaseModel):
    """Paginated list of work requests."""

    items: list[WorkRequestResponse]
    total: int


# Rebuild forward refs for AgentResponse → PersonaResponse
AgentResponse.model_rebuild()
