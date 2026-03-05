"""GitHub webhook signature validation and event handling."""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
from datetime import UTC, datetime
from typing import Any

from tellaro_pm.core.models import BaseDocument
from tellaro_pm.core.opensearch import TASKS_INDEX, CRUDService
from tellaro_pm.core.settings import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Signature validation
# ---------------------------------------------------------------------------


def verify_webhook_signature(payload_body: bytes, signature_header: str | None, secret: str) -> bool:
    """Validate the ``X-Hub-Signature-256`` header using HMAC-SHA256.

    Returns ``True`` when the signature matches, ``False`` otherwise.
    """
    if not signature_header:
        return False

    if not signature_header.startswith("sha256="):
        return False

    expected = hmac.new(secret.encode(), payload_body, hashlib.sha256).hexdigest()
    received = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, received)


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------

_crud = CRUDService(TASKS_INDEX)

# Map GitHub issue states to Tellaro task statuses.
_GITHUB_STATE_TO_TASK_STATUS: dict[str, str] = {
    "open": "backlog",
    "closed": "done",
}


def _find_task_by_issue_number(
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
    return _crud.search_one(query)


def _find_tasks_for_repo(repo_full_name: str) -> list[dict[str, object]]:
    """Find all tasks whose ``github_issue_url`` matches a repository.

    This is used to discover which project(s) a webhook event relates to.
    """
    query: dict[str, object] = {
        "query": {
            "wildcard": {
                "github_issue_url": {
                    "value": f"*github.com/{repo_full_name}/issues/*",
                },
            },
        },
    }
    return _crud.search(query, size=1)


def _resolve_project_id(repo_full_name: str) -> str | None:
    """Return the ``project_id`` associated with a repo, or ``None``."""
    tasks = _find_tasks_for_repo(repo_full_name)
    if tasks:
        pid = tasks[0].get("project_id")
        return str(pid) if pid is not None else None
    return None


# ---------------------------------------------------------------------------
# Issue events
# ---------------------------------------------------------------------------


def handle_issue_event(payload: dict[str, Any]) -> bool:
    """Process an ``issues`` webhook event.

    Supported actions: ``opened``, ``edited``, ``closed``, ``reopened``.
    Returns ``True`` when a task was created or updated.
    """
    action: str = payload.get("action", "")
    issue: dict[str, Any] | None = payload.get("issue")
    repo: dict[str, Any] | None = payload.get("repository")

    if issue is None or repo is None:
        logger.warning("Received issue event without issue or repository data")
        return False

    repo_full_name: str = repo.get("full_name", "")
    issue_number: int = issue.get("number", 0)
    issue_url: str = issue.get("html_url", "")
    issue_title: str = issue.get("title", "")
    issue_body: str = issue.get("body") or ""
    issue_state: str = issue.get("state", "open")
    labels: list[str] = [label["name"] for label in issue.get("labels", [])]

    project_id = _resolve_project_id(repo_full_name)

    if action == "opened":
        if project_id is None:
            logger.info("No linked project for repo %s; skipping issue #%s", repo_full_name, issue_number)
            return False

        # Only create if not already linked
        existing = _find_task_by_issue_number(project_id, issue_number)
        if existing is not None:
            logger.info("Task already exists for issue #%s in project %s", issue_number, project_id)
            return False

        doc = BaseDocument()
        task: dict[str, object] = {
            **doc.to_opensearch(),
            "project_id": project_id,
            "parent_task_id": None,
            "title": issue_title,
            "description": issue_body,
            "status": _GITHUB_STATE_TO_TASK_STATUS.get(issue_state, "backlog"),
            "priority": "normal",
            "assignee_id": None,
            "labels": labels,
            "github_issue_url": issue_url,
            "github_issue_number": issue_number,
            "github_pr_urls": [],
            "order": 0.0,
        }
        _crud.create(doc.id, task)
        logger.info("Created task %s from webhook for issue #%s", doc.id, issue_number)
        return True

    if action in ("edited", "closed", "reopened"):
        if project_id is None:
            logger.info("No linked project for repo %s; skipping issue #%s", repo_full_name, issue_number)
            return False

        existing = _find_task_by_issue_number(project_id, issue_number)
        if existing is None:
            logger.info("No task found for issue #%s in project %s", issue_number, project_id)
            return False

        task_id = str(existing["id"])
        updates: dict[str, object] = {
            "title": issue_title,
            "description": issue_body,
            "labels": labels,
            "github_issue_url": issue_url,
            "status": _GITHUB_STATE_TO_TASK_STATUS.get(issue_state, "backlog"),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        _crud.update(task_id, updates)
        logger.info("Updated task %s from webhook (action=%s) for issue #%s", task_id, action, issue_number)
        return True

    logger.debug("Ignoring unhandled issue action: %s", action)
    return False


# ---------------------------------------------------------------------------
# Pull-request events
# ---------------------------------------------------------------------------


def handle_pr_event(payload: dict[str, Any]) -> bool:
    """Process a ``pull_request`` webhook event.

    Supported actions: ``opened``, ``closed`` (includes merged).
    Links the PR URL to the related task when the PR body references an issue
    number via ``#<number>`` or ``Fixes #<number>`` etc.
    Returns ``True`` when a task was updated.
    """
    action: str = payload.get("action", "")
    pr: dict[str, Any] | None = payload.get("pull_request")
    repo: dict[str, Any] | None = payload.get("repository")

    if pr is None or repo is None:
        logger.warning("Received PR event without pull_request or repository data")
        return False

    if action not in ("opened", "closed"):
        logger.debug("Ignoring unhandled PR action: %s", action)
        return False

    repo_full_name: str = repo.get("full_name", "")
    pr_url: str = pr.get("html_url", "")
    pr_body: str = pr.get("body") or ""
    is_merged: bool = pr.get("merged", False)

    project_id = _resolve_project_id(repo_full_name)
    if project_id is None:
        logger.info("No linked project for repo %s; skipping PR", repo_full_name)
        return False

    # Attempt to find referenced issue numbers in the PR body.
    issue_refs = re.findall(r"#(\d+)", pr_body)
    if not issue_refs:
        logger.info("PR body contains no issue references; skipping")
        return False

    updated = False
    for ref in issue_refs:
        issue_number = int(ref)
        task_doc = _find_task_by_issue_number(project_id, issue_number)
        if task_doc is None:
            continue

        task_id = str(task_doc["id"])
        existing_pr_urls: list[str] = list(task_doc.get("github_pr_urls") or [])  # type: ignore[arg-type]
        if pr_url not in existing_pr_urls:
            existing_pr_urls.append(pr_url)

        task_updates: dict[str, object] = {
            "github_pr_urls": existing_pr_urls,
            "updated_at": datetime.now(UTC).isoformat(),
        }

        # If the PR was merged, move task to "review" (or "done" if already in review).
        if action == "closed" and is_merged:
            current_status = str(task_doc.get("status", "backlog"))
            if current_status in ("backlog", "assigned", "in_progress"):
                task_updates["status"] = "review"
            elif current_status == "review":
                task_updates["status"] = "done"

        _crud.update(task_id, task_updates)
        logger.info("Linked PR %s to task %s (action=%s, merged=%s)", pr_url, task_id, action, is_merged)
        updated = True

    return updated


# ---------------------------------------------------------------------------
# Top-level dispatcher
# ---------------------------------------------------------------------------


def get_webhook_secret() -> str:
    """Return the webhook secret from settings.

    Falls back to ``AUTH_GITHUB_CLIENT_SECRET`` when no dedicated
    ``GITHUB_WEBHOOK_SECRET`` is configured.
    """
    if settings.GITHUB_WEBHOOK_SECRET:
        return settings.GITHUB_WEBHOOK_SECRET

    # Fall back to the GitHub client secret for convenience.
    return settings.AUTH_GITHUB_CLIENT_SECRET


def dispatch_webhook(event_type: str, payload: dict[str, Any]) -> bool:
    """Route a webhook to the appropriate handler based on the event type.

    Returns ``True`` if the event was processed.
    """
    if event_type == "issues":
        return handle_issue_event(payload)
    if event_type == "pull_request":
        return handle_pr_event(payload)

    logger.debug("Ignoring unhandled webhook event type: %s", event_type)
    return False
