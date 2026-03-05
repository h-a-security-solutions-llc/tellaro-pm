"""Pydantic schemas for agent provisioning tokens."""

from pydantic import BaseModel, Field


class ProvisioningTokenCreate(BaseModel):
    """Request to generate a new provisioning token."""

    label: str = Field(default="", max_length=256)
    expires_hours: int = Field(default=24, ge=1, le=720)


class ProvisioningTokenResponse(BaseModel):
    """Public representation of a provisioning token (no raw token)."""

    id: str
    user_id: str
    label: str
    is_used: bool
    is_revoked: bool
    used_at: str | None = None
    expires_hours: int
    created_at: str


class ProvisioningTokenCreated(BaseModel):
    """Response when a token is first created (includes the raw token)."""

    id: str
    token: str
    label: str
    expires_hours: int
    created_at: str


class ProvisioningTokenExchange(BaseModel):
    """Request to exchange a provisioning token for an agent JWT."""

    token: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=128)
    machine_info: dict[str, object] = Field(default_factory=dict)
    capabilities: list[str] = Field(default_factory=list)


class ProvisioningTokenExchangeResponse(BaseModel):
    """Response from exchanging a provisioning token."""

    access_token: str
    agent_id: str
    expires_in: int


class AgentBinaryInfo(BaseModel):
    """Information about an available agent binary."""

    platform: str
    arch: str
    version: str
    filename: str
    size_bytes: int | None = None
    sha256: str | None = None
