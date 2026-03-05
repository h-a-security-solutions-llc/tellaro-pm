<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { useAgentsStore } from '@/stores/agents'
import { useProjectsStore } from '@/stores/projects'

const projectsStore = useProjectsStore()
const agentsStore = useAgentsStore()
const isLoading = ref(true)

onMounted(async () => {
  try {
    await Promise.all([
      projectsStore.fetchProjects(),
      agentsStore.fetchAgents(),
      agentsStore.fetchWorkRequests(),
    ])
  } finally {
    isLoading.value = false
  }
})

const recentProjects = computed(() => projectsStore.projects.slice(0, 6))
const onlineAgents = computed(() => agentsStore.agents.filter((a) => a.status === 'online').length)
const totalAgents = computed(() => agentsStore.agents.length)
const pendingRequests = computed(
  () => agentsStore.workRequests.filter((r) => r.status === 'pending').length,
)
</script>

<template>
  <div>
    <div class="page-header">
      <h1>Dashboard</h1>
    </div>

    <div v-if="isLoading" class="loading-spinner">Loading...</div>

    <template v-else>
      <!-- Stats -->
      <div class="stats-grid">
        <div class="card stat-card">
          <div class="stat-value">{{ projectsStore.projects.length }}</div>
          <div class="stat-label">Projects</div>
        </div>
        <div class="card stat-card">
          <div class="stat-value">{{ onlineAgents }} / {{ totalAgents }}</div>
          <div class="stat-label">Agents Online</div>
        </div>
        <div class="card stat-card">
          <div class="stat-value">{{ pendingRequests }}</div>
          <div class="stat-label">Pending Requests</div>
        </div>
      </div>

      <!-- Recent Projects -->
      <section class="section">
        <div class="section-header">
          <h2>Recent Projects</h2>
          <RouterLink to="/projects" class="btn btn-sm">View All</RouterLink>
        </div>
        <div v-if="recentProjects.length === 0" class="empty-state">
          No projects yet. Create your first project to get started.
        </div>
        <div v-else class="projects-grid">
          <RouterLink
            v-for="project in recentProjects"
            :key="project.id"
            :to="`/projects/${project.id}`"
            class="card project-card"
          >
            <h3>{{ project.name }}</h3>
            <p>{{ project.description || 'No description' }}</p>
            <div class="project-meta">
              Updated {{ new Date(project.updated_at).toLocaleDateString() }}
            </div>
          </RouterLink>
        </div>
      </section>

      <!-- Pending Work Requests -->
      <section v-if="pendingRequests > 0" class="section">
        <div class="section-header">
          <h2>Pending Work Requests</h2>
          <RouterLink to="/agents" class="btn btn-sm">View All</RouterLink>
        </div>
        <div class="requests-list">
          <div
            v-for="req in agentsStore.workRequests.filter((r) => r.status === 'pending').slice(0, 5)"
            :key="req.id"
            class="card request-row"
          >
            <div>
              <strong>{{ req.request_type }}</strong>
              <p class="request-desc">{{ req.description }}</p>
            </div>
            <div class="request-actions">
              <button class="btn btn-sm btn-primary" @click="agentsStore.approveRequest(req.id)">
                Approve
              </button>
              <button class="btn btn-sm btn-danger" @click="agentsStore.rejectRequest(req.id)">
                Reject
              </button>
            </div>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 16px;
  margin-bottom: 32px;
}

.stat-card {
  text-align: center;
  padding: 24px;
}

.stat-value {
  font-size: 32px;
  font-weight: 700;
  color: var(--color-primary);
}

.stat-label {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-top: 4px;
}

.section {
  margin-bottom: 32px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.section-header h2 {
  font-size: 18px;
  font-weight: 600;
}

.projects-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
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

.requests-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.request-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px;
}

.request-desc {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-top: 2px;
}

.request-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
</style>
