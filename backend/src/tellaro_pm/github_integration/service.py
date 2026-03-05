"""Service layer for GitHub API interactions and Tellaro task synchronisation."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
from cryptography.hazmat.primitives import serialization

from tellaro_pm.core.models import BaseDocument
from tellaro_pm.core.opensearch import TASKS_INDEX, CRUDService
from tellaro_pm.core.settings import settings
from tellaro_pm.github_integration.schemas import GitHubIssue, GitHubPR, GitHubRepo

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric.types import PrivateKeyTypes

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class GitHubAPIError(Exception):
    """Raised when the GitHub API returns an unexpected status code."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"GitHub API {status_code}: {detail}")


class GitHubRateLimitError(GitHubAPIError):
    """Raised when the GitHub API rate limit has been exceeded."""

    def __init__(self, reset_at: int) -> None:
        self.reset_at = reset_at
        super().__init__(403, f"Rate limit exceeded. Resets at {reset_at}")


class GitHubNotFoundError(GitHubAPIError):
    """Raised when a GitHub resource is not found."""

    def __init__(self, resource: str) -> None:
        super().__init__(404, f"Resource not found: {resource}")


class GitHubAppNotConfiguredError(Exception):
    """Raised when GitHub App settings are missing."""

    def __init__(self) -> None:
        super().__init__(
            "GitHub App is not configured. Set GITHUB_APP_ID, "
            "GITHUB_APP_PRIVATE_KEY_PATH, and GITHUB_APP_INSTALLATION_ID."
        )


# ---------------------------------------------------------------------------
# GitHub App JWT generation
# ---------------------------------------------------------------------------

_cached_private_key: PrivateKeyTypes | None = None


def _load_private_key() -> PrivateKeyTypes:
    """Load and cache the GitHub App private key from disk."""
    global _cached_private_key
    if _cached_private_key is not None:
        return _cached_private_key

    key_path = Path(settings.GITHUB_APP_PRIVATE_KEY_PATH)
    if not key_path.is_file():
        msg = f"GitHub App private key not found at {key_path}"
        raise FileNotFoundError(msg)

    key_data = key_path.read_bytes()
    _cached_private_key = serialization.load_pem_private_key(key_data, password=None)
    return _cached_private_key


def _generate_app_jwt() -> str:
    """Generate a short-lived JWT for authenticating as the GitHub App.

    The JWT is valid for 10 minutes (GitHub's maximum).
    Uses RS256 with the App's private key via the cryptography library.
    """
    import base64
    import json

    from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15
    from cryptography.hazmat.primitives.hashes import SHA256

    private_key = _load_private_key()
    now = int(time.time())

    header = {"alg": "RS256", "typ": "JWT"}
    payload = {
        "iat": now - 60,  # 60s clock drift allowance
        "exp": now + (10 * 60),  # 10 minute expiry
        "iss": settings.GITHUB_APP_ID,
    }

    def _b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    header_b64 = _b64url(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = _b64url(json.dumps(payload, separators=(",", ":")).encode())

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature: bytes = private_key.sign(signing_input, PKCS1v15(), SHA256())  # type: ignore[union-attr]

    return f"{header_b64}.{payload_b64}.{_b64url(signature)}"  # pyright: ignore[reportUnknownArgumentType]


# ---------------------------------------------------------------------------
# Installation access token cache
# ---------------------------------------------------------------------------

_installation_token: str = ""
_installation_token_expires_at: float = 0.0


def _get_installation_token() -> str:
    """Obtain (or return cached) installation access token for the GitHub App.

    Tokens are valid for 1 hour; we refresh when < 5 minutes remain.
    """
    global _installation_token, _installation_token_expires_at

    if _installation_token and time.time() < _installation_token_expires_at - 300:
        return _installation_token

    jwt_token = _generate_app_jwt()
    response = httpx.post(
        f"{GITHUB_API_BASE}/app/installations/{settings.GITHUB_APP_INSTALLATION_ID}/access_tokens",
        headers={
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()

    _installation_token = data["token"]
    # Parse the expiry; GitHub returns ISO 8601 e.g. "2024-01-01T00:00:00Z"
    expires_str: str = data.get("expires_at", "")
    if expires_str:
        _installation_token_expires_at = datetime.fromisoformat(expires_str.replace("Z", "+00:00")).timestamp()
    else:
        # Default to 55 minutes from now if parsing fails
        _installation_token_expires_at = time.time() + 3300

    logger.info("Obtained GitHub App installation token (expires %s)", expires_str)
    return _installation_token


def is_github_app_configured() -> bool:
    """Return True if all required GitHub App settings are present."""
    return bool(settings.GITHUB_APP_ID and settings.GITHUB_APP_PRIVATE_KEY_PATH and settings.GITHUB_APP_INSTALLATION_ID)


def get_app_github_service() -> GitHubService:
    """Create a GitHubService authenticated as the GitHub App installation.

    Raises ``GitHubAppNotConfiguredError`` if settings are missing.
    """
    if not is_github_app_configured():
        raise GitHubAppNotConfiguredError
    token = _get_installation_token()
    return GitHubService(token)


# ---------------------------------------------------------------------------
# GitHubService — thin wrapper around the GitHub REST API
# ---------------------------------------------------------------------------


class GitHubService:
    """Communicate with the GitHub REST API using a personal, OAuth, or App installation token."""

    def __init__(self, access_token: str) -> None:
        self._client = httpx.Client(
            base_url=GITHUB_API_BASE,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )

    # -- internal helpers ---------------------------------------------------

    def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        """Execute a request and handle common error codes."""
        response = self._client.request(method, url, **kwargs)

        if response.status_code == 403:
            remaining = response.headers.get("X-RateLimit-Remaining", "")
            if remaining == "0":
                reset_at = int(response.headers.get("X-RateLimit-Reset", "0"))
                raise GitHubRateLimitError(reset_at)
            raise GitHubAPIError(403, response.text)

        if response.status_code == 404:
            raise GitHubNotFoundError(url)

        if response.status_code == 422:
            raise GitHubAPIError(422, response.text)

        response.raise_for_status()
        return response.json()

    def ping(self) -> Any:
        """Quick connectivity check against the GitHub API."""
        return self._request("GET", "/app")

    def _get(self, url: str, **kwargs: Any) -> Any:
        return self._request("GET", url, **kwargs)

    def _post(self, url: str, **kwargs: Any) -> Any:
        return self._request("POST", url, **kwargs)

    def _patch(self, url: str, **kwargs: Any) -> Any:
        return self._request("PATCH", url, **kwargs)

    # -- static helpers -----------------------------------------------------

    @staticmethod
    def _parse_repo(data: dict[str, Any]) -> GitHubRepo:
        return GitHubRepo(
            id=data["id"],
            name=data["name"],
            full_name=data["full_name"],
            description=data.get("description"),
            url=data["html_url"],
            default_branch=data.get("default_branch", "main"),
            is_private=data.get("private", False),
        )

    @staticmethod
    def _parse_issue(data: dict[str, Any]) -> GitHubIssue:
        return GitHubIssue(
            id=data["id"],
            number=data["number"],
            title=data["title"],
            body=data.get("body"),
            state=data["state"],
            labels=[label["name"] for label in data.get("labels", [])],
            assignees=[a["login"] for a in data.get("assignees", [])],
            url=data["html_url"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )

    @staticmethod
    def _parse_pr(data: dict[str, Any]) -> GitHubPR:
        return GitHubPR(
            id=data["id"],
            number=data["number"],
            title=data["title"],
            body=data.get("body"),
            state=data["state"],
            url=data["html_url"],
            head_branch=data["head"]["ref"],
            base_branch=data["base"]["ref"],
            created_at=data["created_at"],
        )

    # -- public API ---------------------------------------------------------

    def list_org_repos(self, org: str) -> list[GitHubRepo]:
        """List all repositories for an organisation (paginated up to 100)."""
        data: list[dict[str, Any]] = self._get(f"/orgs/{org}/repos", params={"per_page": 100, "type": "all"})
        return [self._parse_repo(r) for r in data]

    def get_repo(self, owner: str, name: str) -> GitHubRepo:
        """Retrieve metadata for a single repository."""
        data: dict[str, Any] = self._get(f"/repos/{owner}/{name}")
        return self._parse_repo(data)

    def list_issues(self, owner: str, name: str, state: str = "open") -> list[GitHubIssue]:
        """List issues for a repository (excludes pull requests)."""
        data: list[dict[str, Any]] = self._get(
            f"/repos/{owner}/{name}/issues",
            params={"state": state, "per_page": 100},
        )
        # The GitHub issues endpoint also returns pull requests; filter them out.
        return [self._parse_issue(item) for item in data if "pull_request" not in item]

    def get_issue(self, owner: str, name: str, number: int) -> GitHubIssue:
        """Retrieve a single issue by number."""
        data: dict[str, Any] = self._get(f"/repos/{owner}/{name}/issues/{number}")
        return self._parse_issue(data)

    def create_issue(
        self,
        owner: str,
        name: str,
        title: str,
        body: str | None = None,
        labels: list[str] | None = None,
        assignees: list[str] | None = None,
    ) -> GitHubIssue:
        """Create a new issue in a repository."""
        payload: dict[str, Any] = {"title": title}
        if body is not None:
            payload["body"] = body
        if labels:
            payload["labels"] = labels
        if assignees:
            payload["assignees"] = assignees

        data: dict[str, Any] = self._post(f"/repos/{owner}/{name}/issues", json=payload)
        return self._parse_issue(data)

    def update_issue(self, owner: str, name: str, number: int, updates: dict[str, Any]) -> GitHubIssue:
        """Update an existing issue. *updates* may contain title, body, state, labels, assignees."""
        data: dict[str, Any] = self._patch(f"/repos/{owner}/{name}/issues/{number}", json=updates)
        return self._parse_issue(data)

    def list_pull_requests(self, owner: str, name: str, state: str = "open") -> list[GitHubPR]:
        """List pull requests for a repository."""
        data: list[dict[str, Any]] = self._get(
            f"/repos/{owner}/{name}/pulls",
            params={"state": state, "per_page": 100},
        )
        return [self._parse_pr(pr) for pr in data]

    def get_pull_request(self, owner: str, name: str, number: int) -> GitHubPR:
        """Retrieve a single pull request by number."""
        data: dict[str, Any] = self._get(f"/repos/{owner}/{name}/pulls/{number}")
        return self._parse_pr(data)


# ---------------------------------------------------------------------------
# Status mapping helpers
# ---------------------------------------------------------------------------

_GITHUB_STATE_TO_TASK_STATUS: dict[str, str] = {
    "open": "backlog",
    "closed": "done",
}

_TASK_STATUS_TO_GITHUB_STATE: dict[str, str] = {
    "backlog": "open",
    "assigned": "open",
    "in_progress": "open",
    "review": "open",
    "done": "closed",
}


# ---------------------------------------------------------------------------
# GitHubSyncService — bidirectional sync between GitHub issues and tasks
# ---------------------------------------------------------------------------


class GitHubSyncService:
    """Sync GitHub issues to Tellaro tasks and vice versa."""

    def __init__(self) -> None:
        self._crud = CRUDService(TASKS_INDEX)

    # -- helpers ------------------------------------------------------------

    def _find_task_by_issue_number(
        self,
        project_id: str,
        issue_number: int,
    ) -> dict[str, object] | None:
        """Look up a task by its linked GitHub issue number within a project."""
        query: dict[str, object] = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"project_id": project_id}},
                        {"term": {"github_issue_number": issue_number}},
                    ],
                },
            },
        }
        return self._crud.search_one(query)

    # -- sync inward (GitHub → Tellaro) -------------------------------------

    def sync_issues_to_tasks(
        self,
        project_id: str,
        repo_full_name: str,
        github_service: GitHubService,
    ) -> int:
        """Pull all open issues from *repo_full_name* and create/update matching tasks.

        Returns the number of issues synced (created + updated).
        """
        parts = repo_full_name.split("/", maxsplit=1)
        if len(parts) != 2:
            msg = f"Invalid repo_full_name: {repo_full_name}"
            raise ValueError(msg)

        owner, name = parts
        issues = github_service.list_issues(owner, name, state="all")

        synced = 0
        for issue in issues:
            existing = self._find_task_by_issue_number(project_id, issue.number)

            if existing is not None:
                # Update existing task
                task_id = str(existing["id"])
                updates: dict[str, object] = {
                    "title": issue.title,
                    "description": issue.body or "",
                    "labels": issue.labels,
                    "github_issue_url": issue.url,
                    "status": _GITHUB_STATE_TO_TASK_STATUS.get(issue.state, "backlog"),
                    "updated_at": datetime.now(UTC).isoformat(),
                }
                self._crud.update(task_id, updates)
                logger.info("Updated task %s from GitHub issue #%s", task_id, issue.number)
            else:
                # Create new task
                doc = BaseDocument()
                task: dict[str, object] = {
                    **doc.to_opensearch(),
                    "project_id": project_id,
                    "parent_task_id": None,
                    "title": issue.title,
                    "description": issue.body or "",
                    "status": _GITHUB_STATE_TO_TASK_STATUS.get(issue.state, "backlog"),
                    "priority": "normal",
                    "assignee_id": None,
                    "labels": issue.labels,
                    "github_issue_url": issue.url,
                    "github_issue_number": issue.number,
                    "github_pr_urls": [],
                    "order": 0.0,
                }
                self._crud.create(doc.id, task)
                logger.info("Created task %s from GitHub issue #%s", doc.id, issue.number)

            synced += 1

        return synced

    # -- sync outward (Tellaro → GitHub) ------------------------------------

    def sync_task_to_issue(self, task_id: str, github_service: GitHubService) -> None:
        """Push local task changes back to the linked GitHub issue."""
        task = self._crud.get(task_id)
        if task is None:
            msg = f"Task {task_id} not found"
            raise ValueError(msg)

        issue_url = task.get("github_issue_url")
        issue_number = task.get("github_issue_number")
        if issue_url is None or issue_number is None:
            msg = f"Task {task_id} is not linked to a GitHub issue"
            raise ValueError(msg)

        # Derive owner/name from the issue URL, e.g.
        # https://github.com/owner/name/issues/42
        url_str = str(issue_url)
        segments = url_str.rstrip("/").split("/")
        # segments: [..., owner, name, "issues", number]
        if len(segments) < 4:
            msg = f"Cannot parse repo from issue URL: {url_str}"
            raise ValueError(msg)

        owner = segments[-4]
        name = segments[-3]

        task_status = str(task.get("status", "backlog"))
        github_state = _TASK_STATUS_TO_GITHUB_STATE.get(task_status, "open")

        updates: dict[str, Any] = {
            "title": str(task.get("title", "")),
            "body": str(task.get("description", "")),
            "state": github_state,
        }

        raw_labels = task.get("labels")
        if isinstance(raw_labels, list):
            updates["labels"] = [str(lbl) for lbl in raw_labels]  # type: ignore[union-attr]

        github_service.update_issue(owner, name, int(str(issue_number)), updates)
        logger.info("Pushed task %s changes to GitHub issue #%s", task_id, issue_number)


github_sync_service = GitHubSyncService()
