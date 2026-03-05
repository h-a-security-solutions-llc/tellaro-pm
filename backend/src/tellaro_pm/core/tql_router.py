"""TQL endpoints for query validation and field schema discovery."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from tellaro_pm.core.dependencies import get_current_user
from tellaro_pm.core.opensearch import INDEX_MAPPINGS
from tellaro_pm.core.settings import settings
from tellaro_pm.core.tql_service import get_field_schema, validate_tql

router = APIRouter(
    prefix=f"/api/{settings.API_VERSION_STR}/tql",
    tags=["tql"],
)


@router.get("/field-schema")
def field_schema(
    _user: Annotated[dict[str, object], Depends(get_current_user)],
    index: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    """Return field schema for TQL intellisense.

    If ``index`` is provided, returns the schema for that specific index.
    Otherwise returns schemas for all known indices.
    """
    if index:
        return {"index": index, "fields": get_field_schema(index)}

    result: dict[str, list[dict[str, str]]] = {}
    for index_name in INDEX_MAPPINGS:
        result[index_name] = get_field_schema(index_name)
    return {"indices": result}


@router.post("/validate")
def validate_query(
    body: dict[str, str],
    _user: Annotated[dict[str, object], Depends(get_current_user)],
) -> dict[str, Any]:
    """Validate a TQL query string.

    Request body: {"query": "role eq 'admin'", "index": "optional-index-name"}
    """
    query = body.get("query", "")
    index = body.get("index")
    return validate_tql(query, index)
