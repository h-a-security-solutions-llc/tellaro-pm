"""FastAPI router for admin endpoints (domain auth configs, system health, TQL)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from tellaro_pm.core.dependencies import require_admin
from tellaro_pm.core.opensearch import AUTH_DOMAINS_INDEX, CRUDService
from tellaro_pm.core.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix=f"/api/{settings.API_VERSION_STR}/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)

_crud = CRUDService(AUTH_DOMAINS_INDEX)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class DomainConfigOut(BaseModel):
    id: str
    domain: str
    provider: str
    oidc_issuer: str | None = None
    client_id: str | None = None
    is_active: bool = True
    created_at: str | None = None
    updated_at: str | None = None


class DomainConfigCreate(BaseModel):
    domain: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    oidc_issuer: str | None = None
    client_id: str | None = None


class DomainConfigUpdate(BaseModel):
    domain: str | None = None
    provider: str | None = None
    oidc_issuer: str | None = None
    client_id: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/domain-configs", response_model=list[DomainConfigOut])
def list_domain_configs(
    _user: Annotated[dict[str, object], Depends(require_admin)],
) -> list[DomainConfigOut]:
    """List all domain auth configurations."""
    docs = _crud.search({"query": {"match_all": {}}}, size=200)
    return [_doc_to_out(d) for d in docs]


@router.post("/domain-configs", response_model=DomainConfigOut, status_code=status.HTTP_201_CREATED)
def create_domain_config(
    data: DomainConfigCreate,
    _user: Annotated[dict[str, object], Depends(require_admin)],
) -> DomainConfigOut:
    """Create a new domain auth configuration."""
    now = datetime.now(UTC).isoformat()
    doc_id = str(uuid4())
    doc: dict[str, object] = {
        "id": doc_id,
        "domain": data.domain,
        "provider": data.provider,
        "provider_config": {},
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }
    if data.oidc_issuer:
        doc["provider_config"] = {"oidc_issuer": data.oidc_issuer, "client_id": data.client_id or ""}
    _crud.create(doc_id, doc)
    return _doc_to_out(doc)


@router.patch("/domain-configs/{config_id}", response_model=DomainConfigOut)
def update_domain_config(
    config_id: str,
    data: DomainConfigUpdate,
    _user: Annotated[dict[str, object], Depends(require_admin)],
) -> DomainConfigOut:
    """Update a domain auth configuration."""
    existing = _crud.get(config_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain config not found")

    updates: dict[str, object] = {"updated_at": datetime.now(UTC).isoformat()}
    if data.domain is not None:
        updates["domain"] = data.domain
    if data.provider is not None:
        updates["provider"] = data.provider
    if data.oidc_issuer is not None or data.client_id is not None:
        raw_config: object = existing.get("provider_config") or {}
        existing_config: dict[str, object] = (
            cast("dict[str, object]", raw_config) if isinstance(raw_config, dict) else {}
        )
        if data.oidc_issuer is not None:
            existing_config["oidc_issuer"] = data.oidc_issuer
        if data.client_id is not None:
            existing_config["client_id"] = data.client_id
        updates["provider_config"] = existing_config

    _crud.update(config_id, updates)
    merged = {**existing, **updates}
    return _doc_to_out(merged)


@router.delete("/domain-configs/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_domain_config(
    config_id: str,
    _user: Annotated[dict[str, object], Depends(require_admin)],
) -> None:
    """Delete a domain auth configuration."""
    if not _crud.delete(config_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain config not found")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _doc_to_out(doc: dict[str, object]) -> DomainConfigOut:
    config = doc.get("provider_config")
    oidc_issuer = None
    client_id = None
    if isinstance(config, dict):
        cfg = cast("dict[str, object]", config)
        oidc_issuer = str(cfg["oidc_issuer"]) if "oidc_issuer" in cfg else None
        client_id = str(cfg["client_id"]) if "client_id" in cfg else None
    return DomainConfigOut(
        id=str(doc.get("id", "")),
        domain=str(doc.get("domain", "")),
        provider=str(doc.get("provider", "")),
        oidc_issuer=oidc_issuer,
        client_id=client_id,
        is_active=bool(doc.get("is_active", True)),
        created_at=str(doc.get("created_at", "")) or None,
        updated_at=str(doc.get("updated_at", "")) or None,
    )
