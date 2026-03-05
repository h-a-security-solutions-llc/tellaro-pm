"""Pydantic schemas for the GitHub integration module."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GitHubRepo(BaseModel):
    """A GitHub repository summary."""

    id: int
    name: str
    full_name: str
    description: str | None = None
    url: str
    default_branch: str = "main"
    is_private: bool = False


class GitHubIssue(BaseModel):
    """A GitHub issue."""

    id: int
    number: int
    title: str
    body: str | None = None
    state: str
    labels: list[str] = Field(default_factory=list)
    assignees: list[str] = Field(default_factory=list)
    url: str
    created_at: str
    updated_at: str


class GitHubPR(BaseModel):
    """A GitHub pull request."""

    id: int
    number: int
    title: str
    body: str | None = None
    state: str
    url: str
    head_branch: str
    base_branch: str
    created_at: str


class WebhookEvent(BaseModel):
    """Generic GitHub webhook payload."""

    action: str
    repository: dict[str, object] = Field(default_factory=dict)
    issue: dict[str, object] | None = None
    pull_request: dict[str, object] | None = None
    sender: dict[str, object] = Field(default_factory=dict)


class SyncRequest(BaseModel):
    """Request body for triggering a repo-to-project sync."""

    repo_full_name: str = Field(min_length=1)
    project_id: str = Field(min_length=1)


class SyncResponse(BaseModel):
    """Result summary from a sync operation."""

    issues_synced: int
    prs_synced: int
