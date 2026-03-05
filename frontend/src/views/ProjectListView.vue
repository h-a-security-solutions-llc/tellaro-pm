<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { useProjectsStore } from '@/stores/projects'

const store = useProjectsStore()
const showCreate = ref(false)
const form = ref({ name: '', description: '' })
const formError = ref('')

onMounted(() => {
  store.fetchProjects()
})

async function handleCreate(): Promise<void> {
  formError.value = ''
  if (!form.value.name.trim()) {
    formError.value = 'Project name is required.'
    return
  }
  try {
    await store.createProject(form.value)
    showCreate.value = false
    form.value = { name: '', description: '' }
  } catch {
    formError.value = 'Failed to create project.'
  }
}
</script>

<template>
  <div>
    <div class="page-header">
      <h1>Projects</h1>
      <button class="btn btn-primary" @click="showCreate = true">New Project</button>
    </div>

    <div v-if="store.isLoading" class="loading-spinner">Loading...</div>

    <div v-else-if="store.projects.length === 0" class="empty-state">
      <p>No projects yet. Create one to get started.</p>
    </div>

    <div v-else class="projects-grid">
      <RouterLink
        v-for="project in store.projects"
        :key="project.id"
        :to="`/projects/${project.id}`"
        class="card project-card"
      >
        <h3>{{ project.name }}</h3>
        <p>{{ project.description || 'No description' }}</p>
        <div class="project-meta">
          Created {{ new Date(project.created_at).toLocaleDateString() }}
        </div>
      </RouterLink>
    </div>

    <!-- Create modal -->
    <div v-if="showCreate" class="modal-overlay" @click.self="showCreate = false">
      <div class="modal">
        <h2>New Project</h2>
        <div v-if="formError" class="login-error">{{ formError }}</div>
        <form @submit.prevent="handleCreate">
          <div class="form-group">
            <label for="proj-name">Name</label>
            <input id="proj-name" v-model="form.name" class="form-input" placeholder="Project name" />
          </div>
          <div class="form-group">
            <label for="proj-desc">Description</label>
            <textarea
              id="proj-desc"
              v-model="form.description"
              class="form-input"
              placeholder="Optional description"
            />
          </div>
          <div class="modal-actions">
            <button type="button" class="btn" @click="showCreate = false">Cancel</button>
            <button type="submit" class="btn btn-primary">Create</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<style scoped>
.projects-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}

.project-card {
  cursor: pointer;
  transition: box-shadow 0.15s;
  color: inherit;
}

.project-card:hover {
  box-shadow: var(--shadow);
}

.project-card h3 {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 6px;
}

.project-card p {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-bottom: 12px;
}

.project-meta {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.login-error {
  background: #fee2e2;
  color: #991b1b;
  padding: 10px 14px;
  border-radius: var(--radius);
  font-size: 13px;
  margin-bottom: 16px;
}
</style>
