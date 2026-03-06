"""Agent log storage and retrieval."""

from datetime import UTC, datetime
from uuid import uuid4

from tellaro_pm.core.opensearch import AGENT_LOGS_INDEX, CRUDService

_logs_crud = CRUDService(AGENT_LOGS_INDEX)


def store_log_batch(agent_id: str, user_id: str, entries: list[dict[str, object]]) -> int:
    """Store a batch of log entries. Returns the count stored."""
    stored = 0
    for entry in entries:
        log_id = str(uuid4())
        doc: dict[str, object] = {
            "id": log_id,
            "agent_id": agent_id,
            "user_id": user_id,
            "level": entry.get("level", "INFO"),
            "message": entry.get("message", ""),
            "target": entry.get("target", ""),
            "timestamp": entry.get("timestamp") or datetime.now(UTC).isoformat(),
        }
        _logs_crud.create(log_id, doc)
        stored += 1
    return stored


def query_logs(
    agent_id: str | None = None,
    user_id: str | None = None,
    level: str | None = None,
    limit: int = 100,
    since: str | None = None,
) -> list[dict[str, object]]:
    """Query agent logs with optional filters."""
    filters: list[dict[str, object]] = []
    if agent_id:
        filters.append({"term": {"agent_id": agent_id}})
    if user_id:
        filters.append({"term": {"user_id": user_id}})
    if level:
        filters.append({"term": {"level": level.upper()}})
    if since:
        filters.append({"range": {"timestamp": {"gte": since}}})

    query: dict[str, object] = {
        "query": {"bool": {"filter": filters}} if filters else {"match_all": {}},
        "sort": [{"timestamp": {"order": "desc"}}],
    }
    return _logs_crud.search(query, size=limit)
