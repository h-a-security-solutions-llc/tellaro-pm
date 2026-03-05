# TQL (Tellaro Query Language) Integration

TQL is the standard query language for searching and filtering data in Tellaro PM.
It replaces hand-built OpenSearch DSL and provides a human-friendly syntax with
intellisense support in the frontend.

## Packages

| Package | Where | Purpose |
|---|---|---|
| `tellaro-query-language` (PyPI) | Backend | Parse TQL → AST, convert AST → OpenSearch Query DSL |
| `@tellaro/tql` (NPM) | Frontend | TqlInput component with autocomplete, validation, parsing |

## Backend Usage

### Import

```python
from tql import TQL, OpenSearchBackend
```

The import is `tql`, not `tellaro_query_language`.

### Converting TQL to OpenSearch DSL

Use the helper in `tellaro_pm.core.tql_service`:

```python
from tellaro_pm.core.tql_service import tql_to_opensearch

# Convert TQL query to OpenSearch DSL for a specific index
os_query = tql_to_opensearch(
    "role eq 'admin' AND is_active eq true",
    index="tellaro-pm-users",
)
# Result: {"query": {"bool": {"must": [{"term": {"role": "admin"}}, {"term": {"is_active": True}}]}}}

# With extra filters (e.g., scoping to a project)
os_query = tql_to_opensearch(
    "status eq 'open'",
    index="tellaro-pm-tasks",
    extra_filters=[{"term": {"project_id": "abc123"}}],
)
```

### Direct TQL Usage

```python
from tql import TQL, OpenSearchBackend

tql = TQL()

# Parse a query string into an AST
ast = tql.parse("username eq 'admin'")

# Convert AST to OpenSearch DSL with field mappings
backend = OpenSearchBackend({
    "username": "keyword",
    "email": "keyword",
    "display_name": {"display_name": "text", "display_name.keyword": "keyword"},
})
os_query = backend.convert(ast)
```

### TQL Operators

| Operator | Example | OpenSearch DSL |
|---|---|---|
| `eq` | `role eq 'admin'` | `{"term": {"role": "admin"}}` |
| `ne` | `role ne 'admin'` | `{"bool": {"must_not": {"term": ...}}}` |
| `gt`, `lt`, `gte`, `lte` | `age gt 25` | `{"range": {"age": {"gt": 25}}}` |
| `contains` | `email contains 'tellaro'` | `{"wildcard": {"email": "*tellaro*"}}` |
| `startswith` | `name startswith 'J'` | `{"prefix": {"name": "J"}}` |
| `endswith` | `name endswith 'son'` | `{"wildcard": {"name": "*son"}}` |
| `exists` | `email exists` | `{"exists": {"field": "email"}}` |
| `AND` / `OR` | `a eq 'x' AND b eq 'y'` | `{"bool": {"must": [...]}}` |
| `NOT` | `NOT role eq 'admin'` | `{"bool": {"must_not": ...}}` |

### Field Mappings

TQL uses OpenSearch field mappings to choose the right query type:
- `keyword` fields → `term` queries (exact match)
- `text` fields → `match` queries (full-text search)
- Multi-fields (e.g., `display_name` with both `text` and `keyword` sub-fields) →
  TQL automatically selects the right sub-field based on the operator

Field mappings are auto-extracted from the `INDEX_MAPPINGS` in `core/opensearch.py`.

## Frontend Usage

### TqlInput Component

The `@tellaro/tql` package provides `TqlInput`, a Vue 3 component with:
- Syntax highlighting
- Autocomplete for field names, operators, and values
- Real-time validation with error messages
- Submit on Enter

```vue
<script setup>
import { TqlInput } from '@tellaro/tql/vue'
import type { TqlFieldSchema } from '@tellaro/tql'

const query = ref('')
const fieldSchema: TqlFieldSchema[] = [
  { name: 'username', type: 'keyword' },
  { name: 'email', type: 'keyword' },
  { name: 'role', type: 'keyword' },
]
</script>

<template>
  <TqlInput
    v-model="query"
    :field-schema="fieldSchema"
    :autocomplete="true"
    :show-validation="true"
    placeholder="Search..."
    @submit="onSearch"
  />
</template>
```

### TellaroTable Component

`TellaroTable` (`@/components/TellaroTable.vue`) integrates TqlInput for search.
Pass `fieldSchema` to enable TQL intellisense:

```vue
<TellaroTable
  :columns="columns"
  :rows="data"
  :field-schema="fieldSchema"
  :server-side="true"
  @query="handleQuery"
>
  <template #actions="{ row }">
    <button @click="edit(row)">Edit</button>
  </template>
</TellaroTable>
```

### Field Schema from Backend

The backend provides field schemas via `GET /api/v1/tql/field-schema?index=INDEX_NAME`.
This returns the field names and types that TqlInput uses for autocomplete.

## Rules for Claude Code

1. **Always use TQL** for user-facing search/filter endpoints. Do not hand-build OpenSearch DSL for queries that come from user input.
2. **Use `tql_to_opensearch()`** from `tellaro_pm.core.tql_service` to convert TQL strings to OpenSearch queries.
3. **Use `TellaroTable`** with `fieldSchema` prop for all data tables in the frontend.
4. **Field schemas** should match the OpenSearch index mappings. Use `get_field_schema(index)` on the backend.
5. The Python import is `from tql import TQL, OpenSearchBackend` — the package installs as `tql`, not `tellaro_query_language`.
