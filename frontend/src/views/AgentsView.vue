<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { useAgentsStore } from '@/stores/agents'
import type { AgentPersona } from '@/types'

const store = useAgentsStore()

const activeTab = ref<'agents' | 'work-items' | 'requests'>('agents')
const expandedAgent = ref<string | null>(null)
const showPersonaForm = ref(false)
const editingPersona = ref<AgentPersona | null>(null)
const personaForm = ref({ name: '', role_description: '', skills: '' })
const personaAgentId = ref('')

onMounted(async () => {
  await Promise.all([
    store.fetchAgents(),
    store.fetchWorkItems(),
    store.fetchWorkRequests(),
  ])
})

function toggleAgent(agentId: string): void {
  if (expandedAgent.value === agentId) {
    expandedAgent.value = null
  } else {
    expandedAgent.value = agentId
    store.fetchPersonas(agentId)
  }
}

function openCreatePersona(agentId: string): void {
  personaAgentId.value = agentId
  editingPersona.value = null
  personaForm.value = { name: '', role_description: '', skills: '' }
  showPersonaForm.value = true
}

function openEditPersona(persona: AgentPersona): void {
  personaAgentId.value = persona.agent_id
  editingPersona.value = persona
  personaForm.value = {
    name: persona.name,
    role_description: persona.role_description,
    skills: persona.skills.join(', '),
  }
  showPersonaForm.value = true
}

async function handleSavePersona(): Promise<void> {
  const data = {
    name: personaForm.value.name,
    role_description: personaForm.value.role_description,
    skills: personaForm.value.skills
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean),
  }

  if (editingPersona.value) {
    await store.updatePersona(editingPersona.value.id, data)
  } else {
    await store.createPersona(personaAgentId.value, data)
  }
  showPersonaForm.value = false
}

async function handleApprove(id: string): Promise<void> {
  await store.approveRequest(id)
}

async function handleReject(id: string): Promise<void> {
  await store.rejectRequest(id)
}
</script>

<template>
  <div>
    <div class="page-header">
      <h1>Agents</h1>
    </div>

    <div class="tabs">
      <button
        class="tab"
        :class="{ active: activeTab === 'agents' }"
        @click="activeTab = 'agents'"
      >
        Agents ({{ store.agents.length }})
      </button>
      <button
        class="tab"
        :class="{ active: activeTab === 'work-items' }"
        @click="activeTab = 'work-items'"
      >
        Work Items ({{ store.workItems.length }})
      </button>
      <button
        class="tab"
        :class="{ active: activeTab === 'requests' }"
        @click="activeTab = 'requests'"
      >
        Requests ({{ store.workRequests.filter((r) => r.status === 'pending').length }} pending)
      </button>
    </div>

    <div v-if="store.isLoading" class="loading-spinner">Loading...</div>

    <!-- Agents list -->
    <div v-else-if="activeTab === 'agents'" class="agents-list">
      <div v-if="store.agents.length === 0" class="empty-state">No agents registered.</div>
      <div v-for="agent in store.agents" :key="agent.id" class="card agent-card">
        <div class="agent-header" @click="toggleAgent(agent.id)">
          <div class="agent-info">
            <span class="agent-name">{{ agent.name }}</span>
            <span :class="['badge', `badge-${agent.status}`]">{{ agent.status }}</span>
          </div>
          <div class="agent-meta">
            <span class="agent-machine">{{ agent.machine_info }}</span>
            <span class="expand-icon">{{ expandedAgent === agent.id ? '&#9650;' : '&#9660;' }}</span>
          </div>
        </div>

        <div v-if="expandedAgent === agent.id" class="agent-details">
          <div class="personas-header">
            <h4>Personas ({{ agent.personas.length }})</h4>
            <button class="btn btn-sm btn-primary" @click="openCreatePersona(agent.id)">
              Add Persona
            </button>
          </div>
          <div v-if="agent.personas.length === 0" class="empty-state">No personas configured.</div>
          <div v-for="persona in agent.personas" :key="persona.id" class="persona-row">
            <div class="persona-info">
              <span class="persona-name">{{ persona.name }}</span>
              <span class="persona-role">{{ persona.role_description }}</span>
              <div class="persona-skills">
                <span v-for="skill in persona.skills" :key="skill" class="skill-tag">
                  {{ skill }}
                </span>
              </div>
            </div>
            <button class="btn btn-sm" @click="openEditPersona(persona)">Edit</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Work items -->
    <div v-else-if="activeTab === 'work-items'" class="work-items-list">
      <div v-if="store.workItems.length === 0" class="empty-state">No work items.</div>
      <div v-for="item in store.workItems" :key="item.id" class="card work-item-row">
        <div class="work-item-info">
          <span class="work-item-title">{{ item.title }}</span>
          <span :class="['badge', `badge-${item.status}`]">{{ item.status }}</span>
        </div>
        <p v-if="item.description" class="work-item-desc">{{ item.description }}</p>
        <div class="work-item-meta">
          Created {{ new Date(item.created_at).toLocaleString() }}
        </div>
      </div>
    </div>

    <!-- Work requests -->
    <div v-else-if="activeTab === 'requests'" class="requests-list">
      <div v-if="store.workRequests.length === 0" class="empty-state">No work requests.</div>
      <div v-for="req in store.workRequests" :key="req.id" class="card request-row">
        <div class="request-info">
          <div>
            <strong>{{ req.request_type }}</strong>
            <span :class="['badge', `badge-${req.status}`]" style="margin-left: 8px">
              {{ req.status }}
            </span>
          </div>
          <p class="request-desc">{{ req.description }}</p>
          <div class="request-meta">
            {{ new Date(req.created_at).toLocaleString() }}
          </div>
        </div>
        <div v-if="req.status === 'pending'" class="request-actions">
          <button class="btn btn-sm btn-primary" @click="handleApprove(req.id)">Approve</button>
          <button class="btn btn-sm btn-danger" @click="handleReject(req.id)">Reject</button>
        </div>
      </div>
    </div>

    <!-- Persona form modal -->
    <div v-if="showPersonaForm" class="modal-overlay" @click.self="showPersonaForm = false">
      <div class="modal">
        <h2>{{ editingPersona ? 'Edit Persona' : 'New Persona' }}</h2>
        <form @submit.prevent="handleSavePersona">
          <div class="form-group">
            <label for="persona-name">Name</label>
            <input id="persona-name" v-model="personaForm.name" class="form-input" placeholder="Persona name" />
          </div>
          <div class="form-group">
            <label for="persona-role">Role Description</label>
            <textarea
              id="persona-role"
              v-model="personaForm.role_description"
              class="form-input"
              placeholder="What this persona does"
            />
          </div>
          <div class="form-group">
            <label for="persona-skills">Skills (comma-separated)</label>
            <input
              id="persona-skills"
              v-model="personaForm.skills"
              class="form-input"
              placeholder="python, testing, code-review"
            />
          </div>
          <div class="modal-actions">
            <button type="button" class="btn" @click="showPersonaForm = false">Cancel</button>
            <button type="submit" class="btn btn-primary">
              {{ editingPersona ? 'Save' : 'Create' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<style scoped>
.agents-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.agent-card {
  padding: 0;
  overflow: hidden;
}

.agent-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  cursor: pointer;
  transition: background 0.1s;
}

.agent-header:hover {
  background: var(--color-bg);
}

.agent-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.agent-name {
  font-weight: 600;
  font-size: 15px;
}

.agent-meta {
  display: flex;
  align-items: center;
  gap: 12px;
}

.agent-machine {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.expand-icon {
  font-size: 10px;
  color: var(--color-text-secondary);
}

.agent-details {
  border-top: 1px solid var(--color-border);
  padding: 16px 20px;
}

.personas-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.personas-header h4 {
  font-size: 14px;
  font-weight: 600;
}

.persona-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 12px 0;
  border-bottom: 1px solid var(--color-border);
}

.persona-row:last-child {
  border-bottom: none;
}

.persona-name {
  font-weight: 600;
  font-size: 14px;
}

.persona-role {
  display: block;
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-top: 2px;
}

.persona-skills {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 6px;
}

.skill-tag {
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: 999px;
  padding: 2px 8px;
  font-size: 11px;
  color: var(--color-text-secondary);
}

.work-items-list,
.requests-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.work-item-row {
  padding: 16px;
}

.work-item-info {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 4px;
}

.work-item-title {
  font-weight: 500;
}

.work-item-desc {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin: 4px 0;
}

.work-item-meta {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.request-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 16px;
}

.request-desc {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin: 4px 0;
}

.request-meta {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.request-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
  margin-left: 16px;
}
</style>
