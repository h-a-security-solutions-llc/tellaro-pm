"""User CRUD service backed by OpenSearch."""

from datetime import UTC, datetime

from tellaro_pm.core.auth import hash_password
from tellaro_pm.core.opensearch import USERS_INDEX, CRUDService


class UserService:
    def __init__(self) -> None:
        self._crud = CRUDService(USERS_INDEX)

    def get_by_id(self, user_id: str) -> dict[str, object] | None:
        return self._crud.get(user_id)

    def get_by_email(self, email: str) -> dict[str, object] | None:
        query: dict[str, object] = {"query": {"term": {"email": email.lower()}}}
        return self._crud.search_one(query)

    def get_by_username(self, username: str) -> dict[str, object] | None:
        query: dict[str, object] = {"query": {"term": {"username": username}}}
        return self._crud.search_one(query)

    def list_users(
        self, *, skip: int = 0, limit: int = 50, role: str | None = None
    ) -> tuple[list[dict[str, object]], int]:
        filters: list[dict[str, object]] = []
        if role:
            filters.append({"term": {"role": role}})

        if filters:
            query: dict[str, object] = {"query": {"bool": {"filter": filters}}}
        else:
            query = {"query": {"match_all": {}}}

        total = self._crud.count(query)

        query["from"] = skip
        query["sort"] = [{"created_at": {"order": "desc"}}]
        results = self._crud.search(query, size=limit)
        return results, total

    def create(self, data: dict[str, object]) -> dict[str, object]:
        from uuid import uuid4

        now = datetime.now(UTC).isoformat()
        user_id = str(uuid4())

        if "email" in data and isinstance(data["email"], str):
            data["email"] = data["email"].lower()

        raw_password = data.pop("password", None)
        if isinstance(raw_password, str):
            data["password_hash"] = hash_password(raw_password)

        user: dict[str, object] = {
            "id": user_id,
            "is_active": True,
            **data,
            "created_at": now,
            "updated_at": now,
        }

        self._crud.create(user_id, user)
        return user

    def update(self, user_id: str, data: dict[str, object]) -> dict[str, object] | None:
        existing = self._crud.get(user_id)
        if existing is None:
            return None

        update_fields: dict[str, object] = {k: v for k, v in data.items() if v is not None}

        if "email" in update_fields and isinstance(update_fields["email"], str):
            update_fields["email"] = update_fields["email"].lower()

        raw_password = update_fields.pop("password", None)
        if isinstance(raw_password, str):
            update_fields["password_hash"] = hash_password(raw_password)

        update_fields["updated_at"] = datetime.now(UTC).isoformat()

        self._crud.update(user_id, update_fields)
        existing.update(update_fields)
        return existing

    def delete(self, user_id: str) -> bool:
        return self._crud.delete(user_id)

    def search(self, query_text: str, *, limit: int = 20) -> list[dict[str, object]]:
        query: dict[str, object] = {
            "query": {
                "multi_match": {
                    "query": query_text,
                    "fields": ["username", "email", "display_name"],
                    "type": "best_fields",
                    "fuzziness": "AUTO",
                }
            }
        }
        return self._crud.search(query, size=limit)


user_service = UserService()
