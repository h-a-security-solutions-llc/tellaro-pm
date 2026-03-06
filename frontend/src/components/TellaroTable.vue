<script setup lang="ts" generic="T extends Record<string, unknown>">
import { TqlInput } from '@tellaro/tql/vue'
import type { TqlFieldSchema } from '@tellaro/tql'
import { computed, ref, watch } from 'vue'

export interface Column<R> {
  key: keyof R & string
  label: string
  sortable?: boolean
  searchable?: boolean
  render?: (value: unknown, row: R) => string
}

const props = withDefaults(
  defineProps<{
    columns: Column<T>[]
    rows: T[]
    total?: number
    loading?: boolean
    pageSize?: number
    rowKey?: keyof T & string
    searchable?: boolean
    serverSide?: boolean
    fieldSchema?: TqlFieldSchema[]
  }>(),
  {
    total: undefined,
    loading: false,
    pageSize: 25,
    rowKey: 'id' as never,
    searchable: true,
    serverSide: false,
    fieldSchema: () => [],
  },
)

const emit = defineEmits<{
  query: [params: { skip: number; limit: number; q?: string; sort?: string; order?: string }]
  rowClick: [row: T]
}>()

defineSlots<{
  actions?: (props: { row: T }) => unknown
  empty?: () => unknown
  toolbar?: () => unknown
}>()

/* -- Search -- */
const searchText = ref('')

/* -- Pagination -- */
const currentPage = ref(1)

const effectiveTotal = computed(() => {
  if (props.serverSide) return props.total ?? props.rows.length
  return filteredRows.value.length
})

const totalPages = computed(() => Math.max(1, Math.ceil(effectiveTotal.value / props.pageSize)))

/* -- Sorting -- */
const sortKey = ref<string | null>(null)
const sortOrder = ref<'asc' | 'desc'>('asc')

function toggleSort(key: string): void {
  if (sortKey.value === key) {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortOrder.value = 'asc'
  }
  if (props.serverSide) emitQuery()
}

/* -- Client-side filtering (TQL-aware) -- */
const filteredRows = computed(() => {
  if (props.serverSide) return props.rows

  let result = [...props.rows]

  // Client-side: simple text filter across all fields
  const text = searchText.value.trim().toLowerCase()
  if (text) {
    // Check if it looks like a TQL query (has an operator)
    const tqlOps = /\b(eq|ne|gt|lt|gte|lte|contains|startswith|endswith)\b/i
    if (tqlOps.test(text)) {
      // Try to parse as TQL for client-side filtering
      result = clientTqlFilter(result, searchText.value.trim())
    } else {
      // Plain text search across all fields
      result = result.filter((row) =>
        props.columns.some((col) => {
          const val = row[col.key]
          return val != null && String(val).toLowerCase().includes(text)
        }),
      )
    }
  }

  // Sort
  if (sortKey.value) {
    const key = sortKey.value as keyof T
    const dir = sortOrder.value === 'asc' ? 1 : -1
    result.sort((a, b) => {
      const av = a[key]
      const bv = b[key]
      if (av == null && bv == null) return 0
      if (av == null) return dir
      if (bv == null) return -dir
      if (av < bv) return -dir
      if (av > bv) return dir
      return 0
    })
  }

  return result
})

function clientTqlFilter(rows: T[], query: string): T[] {
  // Simple client-side TQL evaluation for basic patterns
  const match = query.match(/^(\w+)\s+(eq|ne|contains|startswith|endswith)\s+['"](.+)['"]$/i)
  if (!match) return rows

  const [, field, op, value] = match
  const lowerValue = value.toLowerCase()

  return rows.filter((row) => {
    const cellValue = row[field as keyof T]
    if (cellValue == null) return op.toLowerCase() === 'ne'
    const strVal = String(cellValue).toLowerCase()

    switch (op.toLowerCase()) {
      case 'eq':
        return strVal === lowerValue
      case 'ne':
        return strVal !== lowerValue
      case 'contains':
        return strVal.includes(lowerValue)
      case 'startswith':
        return strVal.startsWith(lowerValue)
      case 'endswith':
        return strVal.endsWith(lowerValue)
      default:
        return true
    }
  })
}

const pagedRows = computed(() => {
  if (props.serverSide) return props.rows
  const start = (currentPage.value - 1) * props.pageSize
  return filteredRows.value.slice(start, start + props.pageSize)
})

/* -- Server-side query emission -- */
function emitQuery(): void {
  const q = searchText.value.trim() || undefined
  emit('query', {
    skip: (currentPage.value - 1) * props.pageSize,
    limit: props.pageSize,
    q,
    sort: sortKey.value ?? undefined,
    order: sortKey.value ? sortOrder.value : undefined,
  })
}

function onSearch(): void {
  currentPage.value = 1
  if (props.serverSide) emitQuery()
}

function goToPage(page: number): void {
  currentPage.value = Math.max(1, Math.min(page, totalPages.value))
  if (props.serverSide) emitQuery()
}

watch(
  () => props.rows,
  () => {
    if (!props.serverSide && currentPage.value > totalPages.value) {
      currentPage.value = totalPages.value
    }
  },
)

function cellValue(row: T, col: Column<T>): string {
  const raw = row[col.key]
  if (col.render) return col.render(raw, row)
  return raw == null ? '' : String(raw)
}
</script>

<template>
  <div class="tellaro-table-wrapper">
    <!-- Toolbar -->
    <div class="table-toolbar">
      <div v-if="searchable" class="table-search">
        <TqlInput
          v-model="searchText"
          :field-schema="fieldSchema"
          :autocomplete="fieldSchema.length > 0"
          :show-validation="true"
          placeholder="Search... (e.g. role eq 'admin')"
          @submit="onSearch"
        />
      </div>
      <div class="table-toolbar-actions">
        <slot name="toolbar" />
      </div>
    </div>

    <!-- Table -->
    <div class="table-container">
      <table class="tellaro-table">
        <thead>
          <tr>
            <th
              v-for="col in columns"
              :key="col.key"
              :class="{ sortable: col.sortable !== false, sorted: sortKey === col.key }"
              @click="col.sortable !== false ? toggleSort(col.key) : undefined"
            >
              {{ col.label }}
              <span v-if="sortKey === col.key" class="sort-indicator">
                {{ sortOrder === 'asc' ? '▲' : '▼' }}
              </span>
            </th>
            <th v-if="$slots.actions" class="actions-header">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td :colspan="columns.length + ($slots.actions ? 1 : 0)" class="table-loading">
              Loading...
            </td>
          </tr>
          <tr v-else-if="pagedRows.length === 0">
            <td :colspan="columns.length + ($slots.actions ? 1 : 0)" class="table-empty">
              <slot name="empty">No results found.</slot>
            </td>
          </tr>
          <tr
            v-for="row in pagedRows"
            v-else
            :key="String((row as Record<string, unknown>)[props.rowKey ?? 'id'])"
            class="table-row"
            @click="$emit('rowClick', row)"
          >
            <td v-for="col in columns" :key="col.key">
              {{ cellValue(row, col) }}
            </td>
            <td v-if="$slots.actions" class="actions-cell" @click.stop>
              <slot name="actions" :row="row" />
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Pagination -->
    <div v-if="totalPages > 1" class="table-pagination">
      <span class="pagination-info">
        {{ (currentPage - 1) * pageSize + 1 }}–{{ Math.min(currentPage * pageSize, effectiveTotal) }}
        of {{ effectiveTotal }}
      </span>
      <div class="pagination-controls">
        <button class="page-btn" :disabled="currentPage <= 1" @click="goToPage(1)">«</button>
        <button class="page-btn" :disabled="currentPage <= 1" @click="goToPage(currentPage - 1)">‹</button>
        <span class="page-number">{{ currentPage }} / {{ totalPages }}</span>
        <button class="page-btn" :disabled="currentPage >= totalPages" @click="goToPage(currentPage + 1)">›</button>
        <button class="page-btn" :disabled="currentPage >= totalPages" @click="goToPage(totalPages)">»</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tellaro-table-wrapper {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.table-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.table-search {
  flex: 1;
  max-width: 600px;
}

.table-toolbar-actions {
  display: flex;
  gap: 8px;
}

.table-container {
  overflow-x: auto;
}

.tellaro-table {
  width: 100%;
  border-collapse: collapse;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.tellaro-table th,
.tellaro-table td {
  text-align: left;
  padding: 10px 16px;
  border-bottom: 1px solid var(--color-border);
  font-size: 13px;
}

.tellaro-table th {
  background: var(--color-bg);
  font-weight: 600;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  color: var(--color-text-secondary);
  user-select: none;
  white-space: nowrap;
}

.tellaro-table th.sortable {
  cursor: pointer;
}

.tellaro-table th.sortable:hover {
  color: var(--color-text);
}

.tellaro-table th.sorted {
  color: var(--color-primary);
}

.sort-indicator {
  font-size: 9px;
  margin-left: 4px;
}

.tellaro-table tbody tr:last-child td {
  border-bottom: none;
}

.table-row {
  cursor: pointer;
}

.table-row:hover {
  background: var(--color-bg);
}

.actions-cell {
  display: flex;
  gap: 6px;
}

.actions-header {
  width: 1%;
  white-space: nowrap;
}

.table-loading,
.table-empty {
  text-align: center;
  padding: 32px 16px;
  color: var(--color-text-secondary);
  font-size: 14px;
}

.table-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 0;
  font-size: 13px;
  color: var(--color-text-secondary);
}

.pagination-controls {
  display: flex;
  align-items: center;
  gap: 4px;
}

.page-btn {
  padding: 4px 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
  cursor: pointer;
  font-size: 13px;
}

.page-btn:hover:not(:disabled) {
  background: var(--color-bg);
}

.page-btn:disabled {
  opacity: 0.4;
  cursor: default;
}

.page-number {
  padding: 0 8px;
  font-weight: 500;
}
</style>
