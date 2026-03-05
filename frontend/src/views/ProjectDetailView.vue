<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'

import { useChatStore } from '@/stores/chat'
import { useProjectsStore } from '@/stores/projects'
import { useTasksStore } from '@/stores/tasks'
import type { TaskPriority, TaskStatus } from '@/types'

const props = defineProps<{ id: string }>()

const projectsStore = useProjectsStore()
const tasksStore = useTasksStore()
const chatStore = useChatStore()
const router = useRouter()

const activeTab = ref<'tasks' | 'chat' | 'settings'>('tasks')
const showCreateTask = ref(false)
const showEditProject = ref(false)
const taskForm = ref({ title: '', description: '', priority: 'medium' as TaskPriority })
const editForm = ref({ name: '', description: '' })

const project = computed(() => projectsStore.currentProject)

onMounted(async () => {
  await projectsStore.fetchProject(props.id)
  await tasksStore.fetchTasks(props.id)
  await chatStore.fetchSessions('project', props.id)
  if (project.value) {
    editForm.value = {
      name: project.value.name,
      description: project.value.description,
    }
  }
})

const statusLabels: Record<TaskStatus, string> = {
  backlog: 'Backlog',
  assigned: 'Assigned',
  in_progress: 'In Progress',
  review: 'Review',
  done: 'Done',
}

async function handleCreateTask(): Promise<void> {
  if (!taskForm.value.title.trim()) return
  await tasksStore.createTask({
    project_id: props.id,
    title: taskForm.value.title,
    description: taskForm.value.description,
    priority: taskForm.value.priority,
    status: 'backlog',
  })
  showCreateTask.value = false
  taskForm.value = { title: '', description: '', priority: 'medium' }
}

async function handleUpdateProject(): Promise<void> {
  await projectsStore.updateProject(props.id, editForm.value)
  showEditProject.value = false
}

async function handleDeleteProject(): Promise<void> {
  if (!confirm('Are you sure you want to delete this project?')) return
  await projectsStore.deleteProject(props.id)
  await router.push('/projects')
}
</script>

<template>
  <div v-if="project">
    <div class="page-header">
      <div>
        <h1>{{ project.name }}</h1>
        <p class="project-desc">{{ project.description }}</p>
      </div>
      <div class="header-actions">
        <RouterLink :to="`/projects/${id}/board`" class="btn">Kanban Board</RouterLink>
        <button class="btn" @click="showEditProject = true">Edit</button>
      </div>
    </div>

    <!-- Tabs -->
    <div class="tabs">
      <button
        class="tab"
        :class="{ active: activeTab === 'tasks' }"
        @click="activeTab = 'tasks'"
      >
        Tasks ({{ tasksStore.tasks.length }})
      </button>
      <button
        class="tab"
        :class="{ active: activeTab === 'chat' }"
        @click="activeTab = 'chat'"
      >
        Chat
      </button>
      <button
        class="tab"
        :class="{ active: activeTab === 'settings' }"
        @click="activeTab = 'settings'"
      >
        Settings
      </button>
    </div>

    <!-- Tasks tab -->
    <div v-if="activeTab === 'tasks'">
      <div class="tasks-toolbar">
        <button class="btn btn-primary btn-sm" @click="showCreateTask = true">New Task</button>
      </div>

      <div v-if="tasksStore.tasks.length === 0" class="empty-state">No tasks yet.</div>
      <div v-else class="tasks-list">
        <RouterLink
          v-for="task in tasksStore.tasks"
          :key="task.id"
          :to="`/tasks/${task.id}`"
          class="card task-row"
        >
          <div class="task-info">
            <span class="task-title">{{ task.title }}</span>
            <span :class="['badge', `badge-${task.status}`]">{{ statusLabels[task.status] }}</span>
            <span :class="['badge', `badge-${task.priority}`]">{{ task.priority }}</span>
          </div>
        </RouterLink>
      </div>
    </div>

    <!-- Chat tab -->
    <div v-if="activeTab === 'chat'">
      <div v-if="chatStore.sessions.length === 0" class="empty-state">
        No chat sessions for this project.
      </div>
      <div v-else class="chat-sessions-list">
        <RouterLink
          v-for="session in chatStore.sessions"
          :key="session.id"
          :to="`/chat/${session.id}`"
          class="card task-row"
        >
          <span>{{ session.title || session.id }}</span>
          <span class="session-date">
            {{ new Date(session.created_at).toLocaleDateString() }}
          </span>
        </RouterLink>
      </div>
    </div>

    <!-- Settings tab -->
    <div v-if="activeTab === 'settings'" class="settings-content">
      <div class="card">
        <h3>Project Settings</h3>
        <p class="text-secondary">Created: {{ new Date(project.created_at).toLocaleString() }}</p>
        <p class="text-secondary">Updated: {{ new Date(project.updated_at).toLocaleString() }}</p>
        <div class="settings-actions">
          <button class="btn btn-danger" @click="handleDeleteProject">Delete Project</button>
        </div>
      </div>
    </div>

    <!-- Create task modal -->
    <div v-if="showCreateTask" class="modal-overlay" @click.self="showCreateTask = false">
      <div class="modal">
        <h2>New Task</h2>
        <form @submit.prevent="handleCreateTask">
          <div class="form-group">
            <label for="task-title">Title</label>
            <input id="task-title" v-model="taskForm.title" class="form-input" placeholder="Task title" />
          </div>
          <div class="form-group">
            <label for="task-desc">Description</label>
            <textarea
              id="task-desc"
              v-model="taskForm.description"
              class="form-input"
              placeholder="Optional description"
            />
          </div>
          <div class="form-group">
            <label for="task-priority">Priority</label>
            <select id="task-priority" v-model="taskForm.priority" class="form-input">
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
              <option value="critical">Critical</option>
            </select>
          </div>
          <div class="modal-actions">
            <button type="button" class="btn" @click="showCreateTask = false">Cancel</button>
            <button type="submit" class="btn btn-primary">Create</button>
          </div>
        </form>
      </div>
    </div>

    <!-- Edit project modal -->
    <div v-if="showEditProject" class="modal-overlay" @click.self="showEditProject = false">
      <div class="modal">
        <h2>Edit Project</h2>
        <form @submit.prevent="handleUpdateProject">
          <div class="form-group">
            <label for="edit-name">Name</label>
            <input id="edit-name" v-model="editForm.name" class="form-input" />
          </div>
          <div class="form-group">
            <label for="edit-desc">Description</label>
            <textarea id="edit-desc" v-model="editForm.description" class="form-input" />
          </div>
          <div class="modal-actions">
            <button type="button" class="btn" @click="showEditProject = false">Cancel</button>
            <button type="submit" class="btn btn-primary">Save</button>
          </div>
        </form>
      </div>
    </div>
  </div>

  <div v-else class="loading-spinner">Loading project...</div>
</template>

<style scoped>
.project-desc {
  font-size: 14px;
  color: var(--color-text-secondary);
  margin-top: 4px;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.tasks-toolbar {
  margin-bottom: 16px;
}

.tasks-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.task-row {
  display: flex;
  align-items: center;
  padding: 14px 16px;
  color: inherit;
  transition: box-shadow 0.15s;
  cursor: pointer;
}

.task-row:hover {
  box-shadow: var(--shadow);
}

.task-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.task-title {
  font-weight: 500;
}

.chat-sessions-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.session-date {
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-left: auto;
}

.text-secondary {
  color: var(--color-text-secondary);
  font-size: 13px;
  margin-top: 8px;
}

.settings-content {
  max-width: 600px;
}

.settings-content h3 {
  margin-bottom: 8px;
}

.settings-actions {
  margin-top: 24px;
}
</style>
