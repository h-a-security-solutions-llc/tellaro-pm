<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'

import { useTasksStore } from '@/stores/tasks'
import type { Task, TaskPriority, TaskStatus } from '@/types'

const props = defineProps<{ id: string }>()

const tasksStore = useTasksStore()
const router = useRouter()

const isEditing = ref(false)
const subtasks = ref<Task[]>([])
const editForm = ref({ title: '', description: '', priority: 'medium' as TaskPriority })

const task = computed(() => tasksStore.currentTask)

const statusLabels: Record<TaskStatus, string> = {
  backlog: 'Backlog',
  assigned: 'Assigned',
  in_progress: 'In Progress',
  review: 'Review',
  done: 'Done',
}

const allStatuses: TaskStatus[] = ['backlog', 'assigned', 'in_progress', 'review', 'done']

onMounted(async () => {
  await tasksStore.fetchTask(props.id)
  subtasks.value = await tasksStore.fetchSubtasks(props.id)
  if (task.value) {
    editForm.value = {
      title: task.value.title,
      description: task.value.description,
      priority: task.value.priority,
    }
  }
})

async function handleStatusChange(status: TaskStatus): Promise<void> {
  await tasksStore.updateStatus(props.id, status)
}

async function handleSave(): Promise<void> {
  await tasksStore.updateTask(props.id, editForm.value)
  isEditing.value = false
}

async function handleDelete(): Promise<void> {
  if (!confirm('Delete this task?')) return
  const projectId = task.value?.project_id
  await tasksStore.deleteTask(props.id)
  if (projectId) {
    await router.push(`/projects/${projectId}`)
  } else {
    await router.push('/')
  }
}
</script>

<template>
  <div v-if="task">
    <div class="page-header">
      <div>
        <RouterLink
          v-if="task.project_id"
          :to="`/projects/${task.project_id}`"
          class="back-link"
        >
          &larr; Back to project
        </RouterLink>
        <h1 v-if="!isEditing">{{ task.title }}</h1>
        <input
          v-else
          v-model="editForm.title"
          class="form-input title-input"
        />
      </div>
      <div class="header-actions">
        <button v-if="!isEditing" class="btn btn-sm" @click="isEditing = true">Edit</button>
        <template v-else>
          <button class="btn btn-sm" @click="isEditing = false">Cancel</button>
          <button class="btn btn-sm btn-primary" @click="handleSave">Save</button>
        </template>
        <button class="btn btn-sm btn-danger" @click="handleDelete">Delete</button>
      </div>
    </div>

    <div class="task-layout">
      <!-- Main content -->
      <div class="task-main">
        <section class="card">
          <h3>Description</h3>
          <p v-if="!isEditing" class="description">
            {{ task.description || 'No description provided.' }}
          </p>
          <textarea
            v-else
            v-model="editForm.description"
            class="form-input"
            rows="5"
          />
        </section>

        <!-- Subtasks -->
        <section v-if="subtasks.length > 0" class="card subtasks-section">
          <h3>Subtasks ({{ subtasks.length }})</h3>
          <div class="subtasks-list">
            <RouterLink
              v-for="sub in subtasks"
              :key="sub.id"
              :to="`/tasks/${sub.id}`"
              class="subtask-row"
            >
              <span :class="['badge', `badge-${sub.status}`]">{{ statusLabels[sub.status] }}</span>
              <span>{{ sub.title }}</span>
            </RouterLink>
          </div>
        </section>

        <!-- Chat link -->
        <section v-if="task.chat_session_id" class="card">
          <h3>Linked Chat</h3>
          <RouterLink :to="`/chat/${task.chat_session_id}`" class="btn btn-sm">
            Open Chat Session
          </RouterLink>
        </section>
      </div>

      <!-- Sidebar -->
      <div class="task-sidebar">
        <div class="card sidebar-card">
          <div class="sidebar-field">
            <label>Status</label>
            <div class="status-buttons">
              <button
                v-for="s in allStatuses"
                :key="s"
                :class="['btn', 'btn-sm', { 'btn-primary': task.status === s }]"
                @click="handleStatusChange(s)"
              >
                {{ statusLabels[s] }}
              </button>
            </div>
          </div>

          <div class="sidebar-field">
            <label>Priority</label>
            <span v-if="!isEditing" :class="['badge', `badge-${task.priority}`]">
              {{ task.priority }}
            </span>
            <select v-else v-model="editForm.priority" class="form-input">
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
              <option value="critical">Critical</option>
            </select>
          </div>

          <div class="sidebar-field">
            <label>Assignee</label>
            <span>{{ task.assignee?.display_name ?? 'Unassigned' }}</span>
          </div>

          <div class="sidebar-field">
            <label>Created</label>
            <span>{{ new Date(task.created_at).toLocaleString() }}</span>
          </div>

          <div class="sidebar-field">
            <label>Updated</label>
            <span>{{ new Date(task.updated_at).toLocaleString() }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div v-else class="loading-spinner">Loading task...</div>
</template>

<style scoped>
.back-link {
  font-size: 13px;
  color: var(--color-text-secondary);
  display: inline-block;
  margin-bottom: 4px;
}

.back-link:hover {
  color: var(--color-primary);
}

.header-actions {
  display: flex;
  gap: 8px;
}

.title-input {
  font-size: 24px;
  font-weight: 700;
  width: 100%;
}

.task-layout {
  display: grid;
  grid-template-columns: 1fr 300px;
  gap: 24px;
  align-items: start;
}

@media (max-width: 860px) {
  .task-layout {
    grid-template-columns: 1fr;
  }
}

.task-main {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.task-main h3 {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 10px;
}

.description {
  font-size: 14px;
  color: var(--color-text-secondary);
  white-space: pre-wrap;
}

.subtasks-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.subtask-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  font-size: 14px;
  color: inherit;
  border-bottom: 1px solid var(--color-border);
}

.subtask-row:last-child {
  border-bottom: none;
}

.task-sidebar {
  position: sticky;
  top: 24px;
}

.sidebar-card {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.sidebar-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.sidebar-field label {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  color: var(--color-text-secondary);
  letter-spacing: 0.3px;
}

.sidebar-field span {
  font-size: 14px;
}

.status-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
</style>
