"""TQL (Tellaro Query Language) integration for OpenSearch queries.

Provides a unified way to convert human-friendly TQL queries into
OpenSearch Query DSL. All list/search endpoints should use this
instead of hand-building OpenSearch queries.

Usage:
    from tellaro_pm.core.tql_service import tql_to_opensearch

    # Convert a TQL query string to OpenSearch DSL
    os_query = tql_to_opensearch(
        "role eq 'admin' AND is_active eq true",
        index="users",
    )
    # os_query == {"query": {"bool": {"must": [{"term": {"role": "admin"}}, ...]}}}
"""

from __future__ import annotations

import logging
from typing import Any

from tql import TQL, OpenSearchBackend  # pyright: ignore[reportMissingTypeStubs]
from tql.exceptions import TQLParseError  # pyright: ignore[reportMissingTypeStubs]

from tellaro_pm.core.opensearch import INDEX_MAPPINGS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Build field mappings from OpenSearch index definitions
# ---------------------------------------------------------------------------


def _extract_field_types(properties: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Recursively extract field names and their OpenSearch types from index mappings."""
    result: dict[str, Any] = {}
    for field_name, field_def in properties.items():
        full_name = f"{prefix}{field_name}" if not prefix else f"{prefix}.{field_name}"
        field_type = field_def.get("type")

        if field_type:
            # Check for multi-fields (e.g., text with keyword sub-field)
            sub_fields = field_def.get("fields", {})
            if sub_fields:
                mapping: dict[str, str] = {full_name: field_type}
                for sub_name, sub_def in sub_fields.items():
                    sub_type = sub_def.get("type")
                    if sub_type:
                        mapping[f"{full_name}.{sub_name}"] = sub_type
                result[full_name] = mapping
            else:
                result[full_name] = field_type

        # Recurse into nested/object fields
        nested_props = field_def.get("properties")
        if nested_props:
            result.update(_extract_field_types(nested_props, full_name))

    return result


# Cache of index → field mappings
_field_mapping_cache: dict[str, dict[str, Any]] = {}


def get_field_mappings(index_name: str) -> dict[str, Any]:
    """Get TQL-compatible field mappings for an OpenSearch index."""
    if index_name in _field_mapping_cache:
        return _field_mapping_cache[index_name]

    index_def: Any = INDEX_MAPPINGS.get(index_name, {})
    properties: dict[str, Any] = index_def.get("mappings", {}).get("properties", {})
    mappings = _extract_field_types(properties)

    _field_mapping_cache[index_name] = mappings
    return mappings


def get_field_schema(index_name: str) -> list[dict[str, str]]:
    """Get field schema suitable for the frontend TqlInput component.

    Returns a list of {name, type} objects that the @tellaro/tql
    TqlInput component uses for autocomplete suggestions.
    """
    mappings = get_field_mappings(index_name)
    schema: list[dict[str, str]] = []
    for field_name, mapping in mappings.items():
        if isinstance(mapping, dict):
            # Multi-field — use the base field type
            multi: dict[str, Any] = mapping  # pyright: ignore[reportUnknownVariableType]
            schema.append({"name": field_name, "type": str(multi.get(field_name, "text"))})
        else:
            schema.append({"name": field_name, "type": str(mapping)})
    return schema


# ---------------------------------------------------------------------------
# TQL → OpenSearch DSL conversion
# ---------------------------------------------------------------------------

_tql_parser = TQL()


def tql_to_opensearch(
    query: str,
    index: str,
    extra_filters: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Convert a TQL query string to OpenSearch Query DSL.

    Args:
        query: TQL query string (e.g., "role eq 'admin' AND is_active eq true")
        index: OpenSearch index name (used to look up field mappings)
        extra_filters: Additional OpenSearch filter clauses to AND with the TQL query

    Returns:
        OpenSearch query body dict (e.g., {"query": {...}})

    Raises:
        TQLParseError: If the query string has invalid TQL syntax
    """
    field_mappings = get_field_mappings(index)
    backend = OpenSearchBackend(field_mappings)

    ast = _tql_parser.parse(query)
    os_query = backend.convert(ast)

    # Merge extra filters if provided
    if extra_filters:
        existing_query = os_query.get("query", {})
        os_query["query"] = {
            "bool": {
                "must": [existing_query, *extra_filters],
            }
        }

    return os_query


def validate_tql(query: str, index: str | None = None) -> dict[str, Any]:
    """Validate a TQL query string.

    Returns:
        {"valid": True} or {"valid": False, "error": "...", "position": N}
    """
    try:
        _tql_parser.parse(query)
        return {"valid": True}
    except TQLParseError as e:
        return {"valid": False, "error": str(e)}
