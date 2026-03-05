<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { RouterLink } from 'vue-router'

import { useProjectsStore } from '@/stores/projects'
import { useTasksStore } from '@/stores/tasks'
import type { TaskStatus } from '@/types'

const props = defineProps<{ id: string }>()

const projectsStore = useProjectsStore()
const tasksStore = useTasksStore()

const columns: { status: TaskStatus; label: string }[] = [
  { status: 'backlog', label: 'Backlog' },
  { status: 'assigned', label: 'Assigned' },
  { status: 'in_progress', label: 'In Progress' },
  { status: 'review', label: 'Review' },
  { status: 'done', label: 'Done' },
]

onMounted(async () => {
  await projectsStore.fetchProject(props.id)
  await tasksStore.fetchTasks(props.id)
})

const tasksByStatus = computed(() => {
  const map: Record<TaskStatus, typeof tasksStore.tasks> = {
    backlog: [],
    assigned: [],
    in_progress: [],
    review: [],
    done: [],
  }
  for (const task of tasksStore.tasks) {
    map[task.status].push(task)
  }
  return map
})

let draggedTaskId: string | null = null

function onDragStart(event: DragEvent, taskId: string): void {
  draggedTaskId = taskId
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', taskId)
  }
}

function onDragOver(event: DragEvent): void {
  event.preventDefault()
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = 'move'
  }
}

async function onDrop(status: TaskStatus): Promise<void> {
  if (!draggedTaskId) return
  await tasksStore.updateStatus(draggedTaskId, status)
  draggedTaskId = null
}
</script>

<template>
  <div>
    <div class="page-header">
      <div>
        <RouterLink :to="`/projects/${id}`" class="back-link">&larr; Back to project</RouterLink>
        <h1>{{ projectsStore.currentProject?.name ?? 'Board' }}</h1>
      </div>
    </div>

    <div v-if="tasksStore.isLoading" class="loading-spinner">Loading board...</div>

    <div v-else class="board">
      <div
        v-for="col in columns"
        :key="col.status"
        class="board-column"
        @dragover="onDragOver"
        @drop="onDrop(col.status)"
      >
        <div class="column-header">
          <span class="column-title">{{ col.label }}</span>
          <span class="column-count">{{ tasksByStatus[col.status].length }}</span>
        </div>
        <div class="column-body">
          <RouterLink
            v-for="task in tasksByStatus[col.status]"
            :key="task.id"
            :to="`/tasks/${task.id}`"
            class="board-card"
            draggable="true"
            @dragstart="onDragStart($event, task.id)"
          >
            <div class="board-card-title">{{ task.title }}</div>
            <div class="board-card-meta">
              <span :class="['badge', `badge-${task.priority}`]">{{ task.priority }}</span>
              <span v-if="task.assignee" class="board-card-assignee">
                {{ task.assignee.display_name }}
              </span>
            </div>
          </RouterLink>
          <div v-if="tasksByStatus[col.status].length === 0" class="column-empty">
            No tasks
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.back-link {
  font-size: 13px;
  color: var(--color-text-secondary);
}

.back-link:hover {
  color: var(--color-primary);
}

.board {
  display: flex;
  gap: 16px;
  overflow-x: auto;
  padding-bottom: 16px;
}

.board-column {
  min-width: 260px;
  width: 260px;
  flex-shrink: 0;
  background: var(--color-bg);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
}

.column-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--color-border);
}

.column-title {
  font-size: 13px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

.column-count {
  font-size: 12px;
  color: var(--color-text-secondary);
  background: var(--color-surface);
  padding: 2px 8px;
  border-radius: 999px;
}

.column-body {
  padding: 10px;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 200px;
}

.column-empty {
  text-align: center;
  padding: 24px 8px;
  color: var(--color-text-secondary);
  font-size: 13px;
}

.board-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: 12px;
  cursor: grab;
  color: inherit;
  transition: box-shadow 0.15s;
}

.board-card:hover {
  box-shadow: var(--shadow);
}

.board-card:active {
  cursor: grabbing;
}

.board-card-title {
  font-size: 14px;
  font-weight: 500;
  margin-bottom: 8px;
}

.board-card-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.board-card-assignee {
  color: var(--color-text-secondary);
  margin-left: auto;
}
</style>
