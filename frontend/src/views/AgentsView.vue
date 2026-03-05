<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { api } from '@/api/client'
import { useAgentsStore } from '@/stores/agents'
import type { AgentPersona, ProvisioningTokenCreated } from '@/types'

const store = useAgentsStore()

const activeTab = ref<'agents' | 'work-items' | 'requests' | 'provisioning' | 'downloads'>(
  'agents',
)
const expandedAgent = ref<string | null>(null)
const showPersonaForm = ref(false)
const editingPersona = ref<AgentPersona | null>(null)
const personaForm = ref({ name: '', role_description: '', skills: '' })
const personaAgentId = ref('')

// Provisioning
const showTokenForm = ref(false)
const tokenLabel = ref('')
const tokenExpires = ref(24)
const createdToken = ref<ProvisioningTokenCreated | null>(null)
const copiedToken = ref(false)
const installPlatform = ref<'windows' | 'macos' | 'linux'>('windows')

// Derive server URL from current browser location (what the agent should connect to)
const serverUrl = window.location.origin

// Detect user's likely platform for default tab
if (navigator.userAgent.includes('Mac')) {
  installPlatform.value = 'macos'
} else if (navigator.userAgent.includes('Linux')) {
  installPlatform.value = 'linux'
}

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

// -- Provisioning tab
async function switchToProvisioning(): Promise<void> {
  activeTab.value = 'provisioning'
  await store.fetchProvisioningTokens()
}

async function switchToDownloads(): Promise<void> {
  activeTab.value = 'downloads'
  await store.fetchBinaries()
}

async function handleCreateToken(): Promise<void> {
  createdToken.value = await store.createProvisioningToken({
    label: tokenLabel.value || undefined,
    expires_hours: tokenExpires.value,
  })
  copiedToken.value = false
  showTokenForm.value = false
  tokenLabel.value = ''
  tokenExpires.value = 24
}

async function handleRevokeToken(tokenId: string): Promise<void> {
  await store.revokeProvisioningToken(tokenId)
}

function copyToken(): void {
  if (createdToken.value) {
    navigator.clipboard.writeText(createdToken.value.token)
    copiedToken.value = true
  }
}

function dismissCreatedToken(): void {
  createdToken.value = null
}

function formatBytes(bytes: number | undefined): string {
  if (!bytes) return 'N/A'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function downloadUrl(version: string, filename: string): string {
  return api.provisioning.binaryDownloadUrl(version, filename)
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
      <button
        class="tab"
        :class="{ active: activeTab === 'provisioning' }"
        @click="switchToProvisioning"
      >
        Provisioning
      </button>
      <button
        class="tab"
        :class="{ active: activeTab === 'downloads' }"
        @click="switchToDownloads"
      >
        Downloads
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

    <!-- Provisioning tokens -->
    <div v-else-if="activeTab === 'provisioning'" class="provisioning-section">
      <div class="section-header">
        <h3>Provisioning Tokens</h3>
        <button class="btn btn-primary" @click="showTokenForm = true">Generate Token</button>
      </div>

      <p class="section-desc">
        Provisioning tokens allow agent binaries to authenticate and register. Each token is
        single-use and expires after the configured duration.
      </p>

      <!-- Just-created token alert -->
      <div v-if="createdToken" class="token-created-alert">
        <div class="token-created-header">
          <strong>Token created — copy it now, it won't be shown again</strong>
          <button class="link-btn" @click="dismissCreatedToken">Dismiss</button>
        </div>
        <div class="token-display">
          <code class="token-value">{{ createdToken.token }}</code>
          <button class="btn btn-sm" @click="copyToken">
            {{ copiedToken ? 'Copied!' : 'Copy' }}
          </button>
        </div>
        <div class="token-usage">
          <p><strong>Install &amp; run the agent:</strong></p>
          <div class="platform-tabs">
            <button
              class="platform-tab"
              :class="{ active: installPlatform === 'windows' }"
              @click="installPlatform = 'windows'"
            >Windows</button>
            <button
              class="platform-tab"
              :class="{ active: installPlatform === 'macos' }"
              @click="installPlatform = 'macos'"
            >macOS</button>
            <button
              class="platform-tab"
              :class="{ active: installPlatform === 'linux' }"
              @click="installPlatform = 'linux'"
            >Linux</button>
          </div>

          <div v-if="installPlatform === 'windows'" class="install-commands">
            <p class="install-step">PowerShell (x86_64):</p>
            <code class="token-cmd">Invoke-WebRequest -Uri "{{ serverUrl }}/api/v1/agents/provisioning/binaries/latest/tellaro-pm-agent-x86_64-pc-windows-msvc.exe" -OutFile "tellaro-pm-agent.exe"</code>
            <code class="token-cmd">.\tellaro-pm-agent.exe start --server {{ serverUrl }} --token {{ createdToken.token }}</code>
            <p class="install-step">PowerShell (ARM64):</p>
            <code class="token-cmd">Invoke-WebRequest -Uri "{{ serverUrl }}/api/v1/agents/provisioning/binaries/latest/tellaro-pm-agent-aarch64-pc-windows-msvc.exe" -OutFile "tellaro-pm-agent.exe"</code>
            <code class="token-cmd">.\tellaro-pm-agent.exe start --server {{ serverUrl }} --token {{ createdToken.token }}</code>
          </div>

          <div v-if="installPlatform === 'macos'" class="install-commands">
            <p class="install-step">Apple Silicon (M1/M2/M3/M4):</p>
            <code class="token-cmd">curl -fSL "{{ serverUrl }}/api/v1/agents/provisioning/binaries/latest/tellaro-pm-agent-aarch64-apple-darwin" -o tellaro-pm-agent &amp;&amp; chmod +x tellaro-pm-agent</code>
            <code class="token-cmd">./tellaro-pm-agent start --server {{ serverUrl }} --token {{ createdToken.token }}</code>
            <p class="install-step">Intel:</p>
            <code class="token-cmd">curl -fSL "{{ serverUrl }}/api/v1/agents/provisioning/binaries/latest/tellaro-pm-agent-x86_64-apple-darwin" -o tellaro-pm-agent &amp;&amp; chmod +x tellaro-pm-agent</code>
            <code class="token-cmd">./tellaro-pm-agent start --server {{ serverUrl }} --token {{ createdToken.token }}</code>
          </div>

          <div v-if="installPlatform === 'linux'" class="install-commands">
            <p class="install-step">x86_64:</p>
            <code class="token-cmd">curl -fSL "{{ serverUrl }}/api/v1/agents/provisioning/binaries/latest/tellaro-pm-agent-x86_64-unknown-linux-musl" -o tellaro-pm-agent &amp;&amp; chmod +x tellaro-pm-agent</code>
            <code class="token-cmd">./tellaro-pm-agent start --server {{ serverUrl }} --token {{ createdToken.token }}</code>
            <p class="install-step">ARM64 / aarch64:</p>
            <code class="token-cmd">curl -fSL "{{ serverUrl }}/api/v1/agents/provisioning/binaries/latest/tellaro-pm-agent-aarch64-unknown-linux-musl" -o tellaro-pm-agent &amp;&amp; chmod +x tellaro-pm-agent</code>
            <code class="token-cmd">./tellaro-pm-agent start --server {{ serverUrl }} --token {{ createdToken.token }}</code>
          </div>
        </div>
      </div>

      <div v-if="store.provisioningTokens.length === 0" class="empty-state">
        No provisioning tokens. Generate one to register an agent.
      </div>
      <div class="tokens-list">
        <div
          v-for="token in store.provisioningTokens"
          :key="token.id"
          class="card token-card"
          :class="{ 'token-inactive': token.is_used || token.is_revoked }"
        >
          <div class="token-info">
            <div class="token-label">
              {{ token.label || 'Unnamed token' }}
              <span
                v-if="token.is_used"
                class="badge badge-completed"
                >Used</span
              >
              <span v-else-if="token.is_revoked" class="badge badge-failed">Revoked</span>
              <span v-else class="badge badge-online">Active</span>
            </div>
            <div class="token-meta">
              Created {{ new Date(token.created_at).toLocaleString() }}
              &middot; Expires in {{ token.expires_hours }}h
              <template v-if="token.used_at">
                &middot; Used {{ new Date(token.used_at).toLocaleString() }}
              </template>
            </div>
          </div>
          <button
            v-if="!token.is_used && !token.is_revoked"
            class="btn btn-sm btn-danger"
            @click="handleRevokeToken(token.id)"
          >
            Revoke
          </button>
        </div>
      </div>
    </div>

    <!-- Downloads -->
    <div v-else-if="activeTab === 'downloads'" class="downloads-section">
      <div class="section-header">
        <h3>Agent Downloads</h3>
      </div>
      <p class="section-desc">
        Download the Tellaro agent binary for your platform. After downloading, run it with a
        provisioning token to connect to this server.
      </p>

      <div v-if="store.binaries.length === 0" class="empty-state">
        No agent binaries available yet.
      </div>
      <div v-else class="binaries-list">
        <div v-for="binary in store.binaries" :key="`${binary.version}-${binary.filename}`" class="card binary-card">
          <div class="binary-info">
            <div class="binary-platform">
              <span class="platform-icon">
                {{ binary.platform === 'windows' ? '&#x1F5A5;' : binary.platform === 'macos' ? '&#xF8FF;' : '&#x1F427;' }}
              </span>
              <strong>{{ binary.platform }}</strong>
              <span class="binary-arch">{{ binary.arch }}</span>
            </div>
            <div class="binary-meta">
              v{{ binary.version }}
              <template v-if="binary.size_bytes"> &middot; {{ formatBytes(binary.size_bytes) }}</template>
            </div>
          </div>
          <a
            :href="downloadUrl(binary.version, binary.filename)"
            class="btn btn-sm btn-primary"
            download
          >
            Download
          </a>
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

    <!-- Token form modal -->
    <div v-if="showTokenForm" class="modal-overlay" @click.self="showTokenForm = false">
      <div class="modal">
        <h2>Generate Provisioning Token</h2>
        <form @submit.prevent="handleCreateToken">
          <div class="form-group">
            <label for="token-label">Label (optional)</label>
            <input
              id="token-label"
              v-model="tokenLabel"
              class="form-input"
              placeholder="e.g., Dev machine, CI runner"
            />
          </div>
          <div class="form-group">
            <label for="token-expires">Expires in (hours)</label>
            <select id="token-expires" v-model="tokenExpires" class="form-input">
              <option :value="1">1 hour</option>
              <option :value="4">4 hours</option>
              <option :value="24">24 hours (default)</option>
              <option :value="72">3 days</option>
              <option :value="168">1 week</option>
              <option :value="720">30 days</option>
            </select>
          </div>
          <div class="modal-actions">
            <button type="button" class="btn" @click="showTokenForm = false">Cancel</button>
            <button type="submit" class="btn btn-primary">Generate</button>
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

/* Provisioning */

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.section-header h3 {
  font-size: 16px;
  font-weight: 600;
}

.section-desc {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-bottom: 20px;
}

.token-created-alert {
  background: #ecfdf5;
  border: 1px solid #a7f3d0;
  border-radius: var(--radius);
  padding: 16px;
  margin-bottom: 20px;
}

.token-created-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  font-size: 14px;
  color: #065f46;
}

.token-display {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.token-value {
  flex: 1;
  background: #d1fae5;
  padding: 8px 12px;
  border-radius: var(--radius);
  font-size: 13px;
  word-break: break-all;
  color: #065f46;
}

.token-usage {
  font-size: 13px;
  color: #065f46;
}

.token-usage p {
  margin-bottom: 4px;
}

.token-cmd {
  display: block;
  background: #d1fae5;
  padding: 8px 12px;
  border-radius: var(--radius);
  font-size: 12px;
  word-break: break-all;
  margin-bottom: 6px;
}

.platform-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 12px;
}

.platform-tab {
  padding: 4px 14px;
  border: 1px solid #a7f3d0;
  border-radius: var(--radius);
  background: transparent;
  color: #065f46;
  cursor: pointer;
  font-size: 13px;
  font-family: inherit;
  transition: background 0.1s;
}

.platform-tab.active {
  background: #d1fae5;
  font-weight: 600;
}

.platform-tab:hover:not(.active) {
  background: #ecfdf5;
}

.install-commands {
  display: flex;
  flex-direction: column;
}

.install-step {
  font-size: 12px;
  font-weight: 600;
  margin: 8px 0 4px;
  color: #065f46;
}

.install-step:first-child {
  margin-top: 0;
}

.tokens-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.token-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
}

.token-inactive {
  opacity: 0.6;
}

.token-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
  font-size: 14px;
}

.token-meta {
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-top: 2px;
}

/* Downloads */

.binaries-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.binary-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
}

.binary-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.binary-platform {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

.platform-icon {
  font-size: 18px;
}

.binary-arch {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.binary-meta {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.link-btn {
  background: none;
  border: none;
  color: var(--color-primary);
  cursor: pointer;
  font-size: 13px;
  font-family: inherit;
}

.link-btn:hover {
  text-decoration: underline;
}
</style>
