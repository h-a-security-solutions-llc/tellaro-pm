"""Chat CRUD service backed by OpenSearch."""

import re
from datetime import UTC, datetime
from uuid import uuid4

from tellaro_pm.chat.schemas import Mention, MentionType
from tellaro_pm.core.opensearch import CHAT_MESSAGES_INDEX, CHAT_SESSIONS_INDEX, CRUDService

_MENTION_RE = re.compile(r"@([\w-]+)")


def _parse_mentions(content: str) -> list[dict[str, object]]:
    """Extract @mentions from message content and return structured mention dicts.

    Each raw ``@name`` token is mapped to a :class:`Mention` with its type
    inferred from a simple prefix convention (``agent-*`` -> agent,
    ``skill-*`` -> skill, ``persona-*`` -> persona, everything else -> user).
    The ``target_id`` is left as ``None`` here because resolving real IDs
    requires a lookup that the caller (or a downstream enrichment step) can
    perform.
    """
    seen: set[str] = set()
    mentions: list[dict[str, object]] = []
    for match in _MENTION_RE.finditer(content):
        name = match.group(1)
        if name in seen:
            continue
        seen.add(name)

        if name.startswith("agent-") or name.startswith("agent_"):
            mention_type = MentionType.agent
        elif name.startswith("skill-") or name.startswith("skill_"):
            mention_type = MentionType.skill
        elif name.startswith("persona-") or name.startswith("persona_"):
            mention_type = MentionType.persona
        else:
            mention_type = MentionType.user

        mentions.append(Mention(type=mention_type, name=name, target_id=None).model_dump())
    return mentions


class ChatService:
    """High-level operations for chat sessions and messages."""

    def __init__(self) -> None:
        self._sessions = CRUDService(CHAT_SESSIONS_INDEX)
        self._messages = CRUDService(CHAT_MESSAGES_INDEX)

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    def create_session(self, creator_id: str, data: dict[str, object]) -> dict[str, object]:
        now = datetime.now(UTC).isoformat()
        session_id = str(uuid4())

        session: dict[str, object] = {
            "id": session_id,
            "scope_type": data.get("scope_type"),
            "scope_id": data.get("scope_id"),
            "title": data.get("title", ""),
            "working_directory": data.get("working_directory"),
            "agent_id": data.get("agent_id"),
            "persona_id": data.get("persona_id"),
            "participant_ids": [creator_id],
            "is_archived": False,
            "created_at": now,
            "updated_at": now,
        }

        self._sessions.create(session_id, session)
        return session

    def get_session(self, session_id: str) -> dict[str, object] | None:
        return self._sessions.get(session_id)

    def list_sessions(
        self,
        *,
        scope_type: str | None = None,
        scope_id: str | None = None,
        user_id: str | None = None,
    ) -> tuple[list[dict[str, object]], int]:
        filters: list[dict[str, object]] = []

        if scope_type is not None:
            filters.append({"term": {"scope_type": scope_type}})
        if scope_id is not None:
            filters.append({"term": {"scope_id": scope_id}})
        if user_id is not None:
            filters.append({"term": {"participant_ids": user_id}})

        if filters:
            query: dict[str, object] = {"query": {"bool": {"filter": filters}}}
        else:
            query = {"query": {"match_all": {}}}

        total = self._sessions.count(query)

        query["sort"] = [{"updated_at": {"order": "desc"}}]
        results = self._sessions.search(query, size=100)
        return results, total

    def update_session(self, session_id: str, data: dict[str, object]) -> dict[str, object] | None:
        existing = self._sessions.get(session_id)
        if existing is None:
            return None

        update_fields: dict[str, object] = {k: v for k, v in data.items() if v is not None}
        update_fields["updated_at"] = datetime.now(UTC).isoformat()

        self._sessions.update(session_id, update_fields)
        existing.update(update_fields)
        return existing

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    def send_message(
        self,
        session_id: str,
        sender_id: str,
        sender_type: str,
        content: str,
    ) -> dict[str, object]:
        now = datetime.now(UTC).isoformat()
        message_id = str(uuid4())

        mentions = _parse_mentions(content)

        message: dict[str, object] = {
            "id": message_id,
            "session_id": session_id,
            "sender_type": sender_type,
            "sender_id": sender_id,
            "content": content,
            "mentions": mentions,
            "created_at": now,
        }

        self._messages.create(message_id, message)

        # Touch the session so it floats to the top of listings.
        self._sessions.update(session_id, {"updated_at": now})

        return message

    def list_messages(
        self,
        session_id: str,
        *,
        limit: int = 50,
        before_id: str | None = None,
    ) -> tuple[list[dict[str, object]], int]:
        filters: list[dict[str, object]] = [{"term": {"session_id": session_id}}]

        if before_id is not None:
            before_msg = self._messages.get(before_id)
            if before_msg is not None:
                filters.append({"range": {"created_at": {"lt": before_msg["created_at"]}}})

        query: dict[str, object] = {"query": {"bool": {"filter": filters}}}
        total = self._messages.count(query)

        query["sort"] = [{"created_at": {"order": "desc"}}]
        results = self._messages.search(query, size=limit)
        return results, total

    def search_messages(
        self,
        query_text: str,
        *,
        session_id: str | None = None,
    ) -> list[dict[str, object]]:
        must: list[dict[str, object]] = [
            {"match": {"content": {"query": query_text, "fuzziness": "AUTO"}}},
        ]
        if session_id is not None:
            must.append({"term": {"session_id": session_id}})

        query: dict[str, object] = {"query": {"bool": {"must": must}}}
        return self._messages.search(query, size=50)


chat_service = ChatService()
