"""OpenSearch client, CRUD service, and index management."""

from opensearchpy import NotFoundError, OpenSearch

from tellaro_pm.core.settings import settings

INDEX_PREFIX = f"{settings.OPENSEARCH_INDEX_PREFIX}-" if settings.OPENSEARCH_INDEX_PREFIX else ""

# Index names
USERS_INDEX = f"{INDEX_PREFIX}tellaro-pm-users"
PROJECTS_INDEX = f"{INDEX_PREFIX}tellaro-pm-projects"
TASKS_INDEX = f"{INDEX_PREFIX}tellaro-pm-tasks"
CHAT_SESSIONS_INDEX = f"{INDEX_PREFIX}tellaro-pm-chat-sessions"
CHAT_MESSAGES_INDEX = f"{INDEX_PREFIX}tellaro-pm-chat-messages"
AGENTS_INDEX = f"{INDEX_PREFIX}tellaro-pm-agents"
PERSONAS_INDEX = f"{INDEX_PREFIX}tellaro-pm-personas"
WORK_ITEMS_INDEX = f"{INDEX_PREFIX}tellaro-pm-work-items"
WORK_REQUESTS_INDEX = f"{INDEX_PREFIX}tellaro-pm-work-requests"
ACTIVITY_INDEX = f"{INDEX_PREFIX}tellaro-pm-activity"
AUTH_DOMAINS_INDEX = f"{INDEX_PREFIX}tellaro-pm-auth-domains"
DEVICE_SESSIONS_INDEX = f"{INDEX_PREFIX}tellaro-pm-device-sessions"
PROVISIONING_TOKENS_INDEX = f"{INDEX_PREFIX}tellaro-pm-provisioning-tokens"
AGENT_LOGS_INDEX = f"{INDEX_PREFIX}tellaro-pm-agent-logs"

_client: OpenSearch | None = None


def get_opensearch_client() -> OpenSearch:
    """Get or create the singleton OpenSearch client."""
    global _client
    if _client is None:
        auth = None
        if settings.OPENSEARCH_USERNAME and settings.OPENSEARCH_PASSWORD:
            auth = (settings.OPENSEARCH_USERNAME, settings.OPENSEARCH_PASSWORD)
        _client = OpenSearch(
            hosts=settings.OPENSEARCH_HOSTS,
            http_auth=auth,
            use_ssl=settings.OPENSEARCH_USE_SSL,
            verify_certs=settings.OPENSEARCH_VERIFY_SSL,
            ca_certs=settings.OPENSEARCH_CA_CERTS,
            timeout=settings.OPENSEARCH_TIMEOUT,
        )
    return _client


class CRUDService:
    """Reusable CRUD operations for an OpenSearch index."""

    def __init__(self, index_name: str) -> None:
        self.index = index_name

    @property
    def client(self) -> OpenSearch:
        return get_opensearch_client()

    def create(self, doc_id: str, body: dict[str, object]) -> str:
        self.client.index(index=self.index, id=doc_id, body=body, refresh="wait_for")  # pyright: ignore[reportCallIssue]
        return doc_id

    def get(self, doc_id: str) -> dict[str, object] | None:
        try:
            result = self.client.get(index=self.index, id=doc_id)
            source: dict[str, object] = result["_source"]
            return source
        except NotFoundError:
            return None

    def update(self, doc_id: str, body: dict[str, object]) -> None:
        self.client.update(index=self.index, id=doc_id, body={"doc": body}, refresh="wait_for")  # pyright: ignore[reportCallIssue]

    def delete(self, doc_id: str) -> bool:
        try:
            self.client.delete(index=self.index, id=doc_id, refresh="wait_for")  # pyright: ignore[reportCallIssue]
        except NotFoundError:
            return False
        return True

    def search(self, query: dict[str, object], size: int = 50) -> list[dict[str, object]]:
        result = self.client.search(index=self.index, body=query, size=size)  # pyright: ignore[reportCallIssue,reportUnknownVariableType]
        hits: list[dict[str, object]] = [hit["_source"] for hit in result["hits"]["hits"]]  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType,reportIndexIssue]
        return hits

    def exists(self, doc_id: str) -> bool:
        return bool(self.client.exists(index=self.index, id=doc_id))

    def search_one(self, query: dict[str, object]) -> dict[str, object] | None:
        results = self.search(query, size=1)
        return results[0] if results else None

    def count(self, query: dict[str, object] | None = None) -> int:
        body = query or {"query": {"match_all": {}}}
        result = self.client.count(index=self.index, body=body)
        return int(result["count"])


# Index mappings
INDEX_MAPPINGS: dict[str, dict[str, object]] = {
    USERS_INDEX: {
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "username": {"type": "keyword"},
                "email": {"type": "keyword"},
                "display_name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "avatar_url": {"type": "keyword", "index": False},
                "password_hash": {"type": "keyword", "index": False},
                "role": {"type": "keyword"},
                "auth_provider": {"type": "keyword"},
                "auth_provider_id": {"type": "keyword"},
                "is_active": {"type": "boolean"},
                "created_at": {"type": "date"},
                "updated_at": {"type": "date"},
            }
        }
    },
    PROJECTS_INDEX: {
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "description": {"type": "text"},
                "owner_id": {"type": "keyword"},
                "member_ids": {"type": "keyword"},
                "github_repos": {
                    "type": "nested",
                    "properties": {
                        "owner": {"type": "keyword"},
                        "name": {"type": "keyword"},
                        "full_name": {"type": "keyword"},
                        "url": {"type": "keyword", "index": False},
                    },
                },
                "status": {"type": "keyword"},
                "created_at": {"type": "date"},
                "updated_at": {"type": "date"},
            }
        }
    },
    TASKS_INDEX: {
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "project_id": {"type": "keyword"},
                "parent_task_id": {"type": "keyword"},
                "title": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "description": {"type": "text"},
                "status": {"type": "keyword"},
                "priority": {"type": "keyword"},
                "assignee_id": {"type": "keyword"},
                "labels": {"type": "keyword"},
                "github_issue_url": {"type": "keyword", "index": False},
                "github_issue_number": {"type": "integer"},
                "github_pr_urls": {"type": "keyword", "index": False},
                "order": {"type": "float"},
                "created_at": {"type": "date"},
                "updated_at": {"type": "date"},
            }
        }
    },
    CHAT_SESSIONS_INDEX: {
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "scope_type": {"type": "keyword"},
                "scope_id": {"type": "keyword"},
                "title": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "working_directory": {"type": "keyword", "index": False},
                "participant_ids": {"type": "keyword"},
                "is_archived": {"type": "boolean"},
                "created_at": {"type": "date"},
                "updated_at": {"type": "date"},
            }
        }
    },
    CHAT_MESSAGES_INDEX: {
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "session_id": {"type": "keyword"},
                "sender_type": {"type": "keyword"},
                "sender_id": {"type": "keyword"},
                "content": {"type": "text"},
                "mentions": {
                    "type": "nested",
                    "properties": {
                        "type": {"type": "keyword"},
                        "name": {"type": "keyword"},
                        "target_id": {"type": "keyword"},
                    },
                },
                "attachments": {"type": "object", "enabled": False},
                "created_at": {"type": "date"},
            }
        }
    },
    AGENTS_INDEX: {
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "user_id": {"type": "keyword"},
                "name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "status": {"type": "keyword"},
                "machine_info": {"type": "object", "enabled": False},
                "last_heartbeat": {"type": "date"},
                "capabilities": {"type": "keyword"},
                "created_at": {"type": "date"},
                "updated_at": {"type": "date"},
            }
        }
    },
    PERSONAS_INDEX: {
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "agent_id": {"type": "keyword"},
                "user_id": {"type": "keyword"},
                "name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "role_description": {"type": "text"},
                "system_prompt": {"type": "text", "index": False},
                "skills": {"type": "keyword"},
                "claude_profile": {"type": "keyword"},
                "is_active": {"type": "boolean"},
                "created_at": {"type": "date"},
                "updated_at": {"type": "date"},
            }
        }
    },
    WORK_ITEMS_INDEX: {
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "task_id": {"type": "keyword"},
                "chat_session_id": {"type": "keyword"},
                "chat_message_id": {"type": "keyword"},
                "agent_id": {"type": "keyword"},
                "persona_id": {"type": "keyword"},
                "status": {"type": "keyword"},
                "instruction": {"type": "text"},
                "working_directory": {"type": "keyword", "index": False},
                "output": {"type": "text", "index": False},
                "artifacts": {"type": "object", "enabled": False},
                "started_at": {"type": "date"},
                "completed_at": {"type": "date"},
                "created_at": {"type": "date"},
                "updated_at": {"type": "date"},
            }
        }
    },
    WORK_REQUESTS_INDEX: {
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "requester_id": {"type": "keyword"},
                "target_user_id": {"type": "keyword"},
                "task_id": {"type": "keyword"},
                "instruction": {"type": "text"},
                "status": {"type": "keyword"},
                "response_message": {"type": "text"},
                "created_at": {"type": "date"},
                "updated_at": {"type": "date"},
            }
        }
    },
    ACTIVITY_INDEX: {
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "actor_type": {"type": "keyword"},
                "actor_id": {"type": "keyword"},
                "action": {"type": "keyword"},
                "entity_type": {"type": "keyword"},
                "entity_id": {"type": "keyword"},
                "project_id": {"type": "keyword"},
                "details": {"type": "object", "enabled": False},
                "created_at": {"type": "date"},
            }
        }
    },
    AUTH_DOMAINS_INDEX: {
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "domain": {"type": "keyword"},
                "provider": {"type": "keyword"},
                "provider_config": {"type": "object", "enabled": False},
                "is_active": {"type": "boolean"},
                "created_at": {"type": "date"},
                "updated_at": {"type": "date"},
            }
        }
    },
    DEVICE_SESSIONS_INDEX: {
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "user_id": {"type": "keyword"},
                "device_id": {"type": "keyword"},
                "refresh_token_hash": {"type": "keyword"},
                "device_name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "browser": {"type": "keyword"},
                "browser_version": {"type": "keyword"},
                "os": {"type": "keyword"},
                "os_version": {"type": "keyword"},
                "device_type": {"type": "keyword"},
                "ip_address": {"type": "ip"},
                "last_ip": {"type": "ip"},
                "is_active": {"type": "boolean"},
                "last_used_at": {"type": "date"},
                "created_at": {"type": "date"},
            }
        }
    },
    PROVISIONING_TOKENS_INDEX: {
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "user_id": {"type": "keyword"},
                "label": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "token_hash": {"type": "keyword"},
                "expires_hours": {"type": "integer"},
                "is_used": {"type": "boolean"},
                "is_revoked": {"type": "boolean"},
                "used_at": {"type": "date"},
                "created_at": {"type": "date"},
            }
        }
    },
    AGENT_LOGS_INDEX: {
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "agent_id": {"type": "keyword"},
                "user_id": {"type": "keyword"},
                "level": {"type": "keyword"},
                "message": {"type": "text"},
                "target": {"type": "keyword"},
                "timestamp": {"type": "date"},
            }
        }
    },
}


def ensure_indices() -> None:
    """Create all indices if they don't exist."""
    client = get_opensearch_client()
    shard_settings = {
        "settings": {
            "number_of_shards": settings.OPENSEARCH_NUMBER_OF_SHARDS,
            "number_of_replicas": settings.OPENSEARCH_NUMBER_OF_REPLICAS,
        }
    }
    for index_name, mapping in INDEX_MAPPINGS.items():
        if not client.indices.exists(index=index_name):
            body = {**shard_settings, **mapping}
            client.indices.create(index=index_name, body=body)
