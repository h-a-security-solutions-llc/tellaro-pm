"""FastAPI router for GitHub integration endpoints."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from tellaro_pm.core.dependencies import get_current_user
from tellaro_pm.core.settings import settings
from tellaro_pm.github_integration.schemas import (
    GitHubIssue,
    GitHubRepo,
    SyncRequest,
    SyncResponse,
)
from tellaro_pm.github_integration.service import (
    GitHubAPIError,
    GitHubNotFoundError,
    GitHubRateLimitError,
    GitHubService,
    github_sync_service,
)
from tellaro_pm.github_integration.webhooks import dispatch_webhook, get_webhook_secret, verify_webhook_signature

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix=f"/api/{settings.API_VERSION_STR}/github",
    tags=["github"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_github_token(
    user: dict[str, object],
    x_github_token: str | None = None,
) -> str:
    """Resolve a usable GitHub access token.

    Priority:
    1. Explicit ``X-GitHub-Token`` header (passed through by the caller).
    2. ``github_access_token`` stored on the user document (from OAuth flow).

    Raises ``HTTPException(401)`` when no token is available.
    """
    if x_github_token:
        return x_github_token

    stored_token = user.get("github_access_token")
    if isinstance(stored_token, str) and stored_token:
        return stored_token

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No GitHub token available. Pass an X-GitHub-Token header or authenticate via GitHub OAuth.",
    )


def _handle_github_error(exc: GitHubAPIError) -> None:
    """Translate a ``GitHubAPIError`` into the appropriate ``HTTPException``."""
    if isinstance(exc, GitHubRateLimitError):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"GitHub API rate limit exceeded. Resets at epoch {exc.reset_at}.",
            headers={"Retry-After": str(exc.reset_at)},
        )
    if isinstance(exc, GitHubNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.detail,
        )
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"GitHub API error ({exc.status_code}): {exc.detail}",
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/repos", response_model=list[GitHubRepo])
def list_repos(
    user: Annotated[dict[str, object], Depends(get_current_user)],
    x_github_token: Annotated[str | None, Header()] = None,
) -> list[GitHubRepo]:
    """List repositories for the configured GitHub organisation."""
    token = _get_github_token(user, x_github_token)
    org = settings.AUTH_GITHUB_ORG
    if not org:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="AUTH_GITHUB_ORG is not configured on the server.",
        )

    gh = GitHubService(token)
    try:
        return gh.list_org_repos(org)
    except GitHubAPIError as exc:
        _handle_github_error(exc)
        return []  # unreachable, but keeps the return type consistent


@router.get("/repos/{owner}/{name}/issues", response_model=list[GitHubIssue])
def list_issues(
    owner: str,
    name: str,
    user: Annotated[dict[str, object], Depends(get_current_user)],
    x_github_token: Annotated[str | None, Header()] = None,
    state: str = "open",
) -> list[GitHubIssue]:
    """List issues for a specific repository."""
    token = _get_github_token(user, x_github_token)
    gh = GitHubService(token)
    try:
        return gh.list_issues(owner, name, state=state)
    except GitHubAPIError as exc:
        _handle_github_error(exc)
        return []  # unreachable


@router.post("/sync", response_model=SyncResponse)
def sync_repo(
    data: SyncRequest,
    user: Annotated[dict[str, object], Depends(get_current_user)],
    x_github_token: Annotated[str | None, Header()] = None,
) -> SyncResponse:
    """Sync a GitHub repository's issues into a Tellaro project's tasks."""
    token = _get_github_token(user, x_github_token)
    gh = GitHubService(token)

    try:
        issues_synced = github_sync_service.sync_issues_to_tasks(
            project_id=data.project_id,
            repo_full_name=data.repo_full_name,
            github_service=gh,
        )
    except GitHubAPIError as exc:
        _handle_github_error(exc)
        return SyncResponse(issues_synced=0, prs_synced=0)  # unreachable
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    # PR sync can be added later; for now report 0.
    return SyncResponse(issues_synced=issues_synced, prs_synced=0)


@router.post("/webhooks", status_code=status.HTTP_200_OK)
async def receive_webhook(
    request: Request,
    x_hub_signature_256: Annotated[str | None, Header()] = None,
    x_github_event: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    """Receive and process GitHub webhook events.

    Validates the ``X-Hub-Signature-256`` header before processing.
    """
    body = await request.body()
    secret = get_webhook_secret()

    if secret and not verify_webhook_signature(body, x_hub_signature_256, secret):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid webhook signature.",
        )

    if not x_github_event:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-GitHub-Event header.",
        )

    payload: dict[str, object] = await request.json()
    processed = dispatch_webhook(x_github_event, payload)  # type: ignore[arg-type]

    if processed:
        logger.info("Webhook processed: event=%s", x_github_event)
        return {"status": "processed"}

    return {"status": "ignored"}
