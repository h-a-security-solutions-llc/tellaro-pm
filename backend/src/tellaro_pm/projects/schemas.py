"""Pydantic schemas for project management endpoints."""

from enum import StrEnum

from pydantic import BaseModel, Field


class ProjectStatus(StrEnum):
    """Project lifecycle status."""

    ACTIVE = "active"
    ARCHIVED = "archived"


class GitHubRepoLink(BaseModel):
    """Reference to a linked GitHub repository."""

    owner: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=128)
    full_name: str = Field(min_length=1, max_length=256)
    url: str = Field(min_length=1)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    description: str = Field(default="", max_length=4096)
    github_repos: list[GitHubRepoLink] = Field(default_factory=lambda: list[GitHubRepoLink]())


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=256)
    description: str | None = Field(default=None, max_length=4096)
    status: ProjectStatus | None = None
    github_repos: list[GitHubRepoLink] | None = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str
    owner_id: str
    member_ids: list[str]
    github_repos: list[GitHubRepoLink]
    status: ProjectStatus
    created_at: str
    updated_at: str


class ProjectListResponse(BaseModel):
    items: list[ProjectResponse]
    total: int
