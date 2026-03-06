<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAgentsStore } from '@/stores/agents'
import { useChatStore } from '@/stores/chat'
import type { AgentInstallation, AgentPersona, ScopeType } from '@/types'

const props = defineProps<{ sessionId?: string }>()

const chatStore = useChatStore()
const agentsStore = useAgentsStore()
const route = useRoute()
const router = useRouter()

const messageInput = ref('')
const messagesContainer = ref<HTMLElement | null>(null)
const showNewSession = ref(false)
const newSessionForm = ref({
  scope_type: 'freeform' as ScopeType,
  title: '',
  working_directory: '',
  agent_id: '',
  persona_id: '',
})
const filterScope = ref<ScopeType | ''>('')

/* @mention autocomplete */
const showMentionDropdown = ref(false)
const mentionQuery = ref('')
const mentionCursorPos = ref(0)

const mentionCandidates = computed<AgentPersona[]>(() => {
  const q = mentionQuery.value.toLowerCase()
  const allPersonas: AgentPersona[] = []
  for (const agent of agentsStore.agents) {
    for (const p of agent.personas) {
      allPersonas.push(p)
    }
  }
  if (!q) return allPersonas.slice(0, 8)
  return allPersonas.filter((p) => p.name.toLowerCase().includes(q)).slice(0, 8)
})

const filteredSessions = computed(() => {
  if (!filterScope.value) return chatStore.sessions
  return chatStore.sessions.filter((s) => s.scope_type === filterScope.value)
})

/** Online agents available for selection */
const onlineAgents = computed<AgentInstallation[]>(() =>
  agentsStore.agents.filter((a) => a.status === 'online' || a.status === 'busy'),
)

/** Personas for the currently selected agent in the new session form */
const selectedAgentPersonas = computed<AgentPersona[]>(() => {
  const agentId = newSessionForm.value.agent_id
  if (!agentId) return []
  const agent = agentsStore.agents.find((a) => a.id === agentId)
  return agent?.personas ?? []
})

/** Whether the new session form is valid */
const canCreateSession = computed(() => {
  if (newSessionForm.value.agent_id && !newSessionForm.value.persona_id) return false
  if (newSessionForm.value.agent_id && selectedAgentPersonas.value.length === 0) return false
  return true
})

/** Agent name for the currently selected session */
const currentAgentName = computed(() => {
  const agentId = chatStore.currentSession?.agent_id
  if (!agentId) return null
  const agent = agentsStore.agents.find((a) => a.id === agentId)
  return agent?.name ?? agentId
})

onMounted(async () => {
  await Promise.all([chatStore.fetchSessions(), agentsStore.fetchAgents()])
  if (props.sessionId) {
    await chatStore.selectSession(props.sessionId)
    scrollToBottom()
  }
})

onUnmounted(() => {
  chatStore.disconnectChatWs()
})

watch(
  () => route.params.sessionId,
  async (newId) => {
    if (newId && typeof newId === 'string') {
      await chatStore.selectSession(newId)
      scrollToBottom()
    }
  },
)

/* Auto-scroll when streaming content changes */
watch(
  () => chatStore.streamingContent,
  () => {
    scrollToBottom()
  },
)

function scrollToBottom(): void {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

async function handleSend(): Promise<void> {
  const content = messageInput.value.trim()
  if (!content || !chatStore.currentSession) return

  /* Extract mentions from @Name patterns */
  const mentionRegex = /@(\w+)/g
  const mentions: Array<{ mention_type: string; target_id: string }> = []
  let match: RegExpExecArray | null
  while ((match = mentionRegex.exec(content)) !== null) {
    const name = match[1].toLowerCase()
    for (const agent of agentsStore.agents) {
      for (const p of agent.personas) {
        if (p.name.toLowerCase() === name) {
          mentions.push({ mention_type: 'persona', target_id: p.id })
        }
      }
    }
  }

  messageInput.value = ''
  showMentionDropdown.value = false
  await chatStore.sendMessage(chatStore.currentSession.id, content, mentions.length > 0 ? mentions : undefined)
  scrollToBottom()
}

function handleInputKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    handleSend()
  }
}

function handleInput(event: Event): void {
  const textarea = event.target as HTMLTextAreaElement
  const value = textarea.value
  const cursor = textarea.selectionStart

  /* Detect if we are in an @mention */
  const beforeCursor = value.slice(0, cursor)
  const atIdx = beforeCursor.lastIndexOf('@')
  if (atIdx !== -1 && !beforeCursor.slice(atIdx).includes(' ')) {
    mentionQuery.value = beforeCursor.slice(atIdx + 1)
    mentionCursorPos.value = atIdx
    showMentionDropdown.value = true
  } else {
    showMentionDropdown.value = false
  }
}

function insertMention(persona: AgentPersona): void {
  const before = messageInput.value.slice(0, mentionCursorPos.value)
  const after = messageInput.value.slice(mentionCursorPos.value + mentionQuery.value.length + 1)
  messageInput.value = `${before}@${persona.name} ${after}`
  showMentionDropdown.value = false
}

async function selectSession(sessionId: string): Promise<void> {
  await router.push(`/chat/${sessionId}`)
}

function onAgentSelected(): void {
  const agentId = newSessionForm.value.agent_id
  // Reset persona selection
  newSessionForm.value.persona_id = ''

  if (agentId) {
    const agent = agentsStore.agents.find((a) => a.id === agentId)
    // Auto-populate working directory with agent's home directory
    if (agent?.machine_info?.home_directory) {
      newSessionForm.value.working_directory = agent.machine_info.home_directory
    }
    // Auto-select first persona if only one exists
    const personas = agent?.personas ?? []
    if (personas.length === 1) {
      newSessionForm.value.persona_id = personas[0].id
    }
  } else {
    newSessionForm.value.working_directory = ''
  }
}

async function handleCreateSession(): Promise<void> {
  // Require persona when agent is selected
  if (newSessionForm.value.agent_id && !newSessionForm.value.persona_id) {
    return
  }

  const session = await chatStore.createSession({
    scope_type: newSessionForm.value.scope_type,
    title: newSessionForm.value.title || undefined,
    working_directory: newSessionForm.value.working_directory || undefined,
    agent_id: newSessionForm.value.agent_id || undefined,
    persona_id: newSessionForm.value.persona_id || undefined,
  })
  showNewSession.value = false
  newSessionForm.value = { scope_type: 'freeform', title: '', working_directory: '', agent_id: '', persona_id: '' }
  await router.push(`/chat/${session.id}`)
}

function senderClass(senderType: string): string {
  if (senderType === 'user') return 'msg-user'
  if (senderType === 'agent') return 'msg-agent'
  return 'msg-system'
}
</script>

<template>
  <div class="chat-layout">
    <!-- Sessions sidebar -->
    <aside class="chat-sidebar">
      <div class="chat-sidebar-header">
        <h3>Sessions</h3>
        <button class="btn btn-sm btn-primary" @click="showNewSession = true">New</button>
      </div>
      <div class="chat-sidebar-filter">
        <select v-model="filterScope" class="form-input">
          <option value="">All</option>
          <option value="freeform">Freeform</option>
          <option value="project">Project</option>
          <option value="task">Task</option>
        </select>
      </div>
      <div class="sessions-list">
        <button
          v-for="session in filteredSessions"
          :key="session.id"
          :class="['session-item', { active: chatStore.currentSession?.id === session.id }]"
          @click="selectSession(session.id)"
        >
          <span class="session-title">{{ session.title || session.scope_type }}</span>
          <span class="session-date">
            {{ new Date(session.created_at).toLocaleDateString() }}
          </span>
        </button>
        <div v-if="filteredSessions.length === 0" class="empty-state">No sessions</div>
      </div>
    </aside>

    <!-- Messages area -->
    <div class="chat-main">
      <template v-if="chatStore.currentSession">
        <div class="chat-header">
          <h2>{{ chatStore.currentSession.title || 'Chat Session' }}</h2>
          <span :class="['badge', `badge-${chatStore.currentSession.scope_type}`]">
            {{ chatStore.currentSession.scope_type }}
          </span>
          <span v-if="currentAgentName" class="badge badge-agent">
            {{ currentAgentName }}
          </span>
        </div>

        <div ref="messagesContainer" class="messages-container">
          <div v-if="chatStore.isLoading" class="loading-spinner">Loading messages...</div>
          <div
            v-for="msg in chatStore.messages"
            :key="msg.id"
            :class="['message', senderClass(msg.sender_type)]"
          >
            <div class="message-header">
              <span class="message-sender">
                {{ msg.sender_name || msg.sender_type }}
              </span>
              <span class="message-time">
                {{ new Date(msg.created_at).toLocaleTimeString() }}
              </span>
            </div>
            <div class="message-content">{{ msg.content }}</div>
          </div>

          <!-- Streaming response -->
          <div v-if="chatStore.isStreaming" class="message msg-agent streaming">
            <div class="message-header">
              <span class="message-sender">Agent</span>
              <span class="streaming-indicator">streaming...</span>
            </div>
            <div class="message-content">{{ chatStore.streamingContent }}<span class="cursor-blink">|</span></div>
          </div>

          <div v-if="chatStore.messages.length === 0 && !chatStore.isLoading && !chatStore.isStreaming" class="empty-state">
            No messages yet. Start the conversation.
          </div>
        </div>

        <!-- Input area -->
        <div class="chat-input-area">
          <div v-if="showMentionDropdown && mentionCandidates.length > 0" class="mention-dropdown">
            <button
              v-for="persona in mentionCandidates"
              :key="persona.id"
              class="mention-item"
              @mousedown.prevent="insertMention(persona)"
            >
              <span class="mention-name">@{{ persona.name }}</span>
              <span class="mention-role">{{ persona.role_description }}</span>
            </button>
          </div>
          <textarea
            v-model="messageInput"
            class="form-input chat-textarea"
            placeholder="Type a message... Use @name to mention an agent"
            rows="2"
            :disabled="chatStore.isStreaming"
            @input="handleInput"
            @keydown="handleInputKeydown"
          />
          <button
            class="btn btn-primary send-btn"
            :disabled="chatStore.isStreaming"
            @click="handleSend"
          >
            Send
          </button>
        </div>
      </template>

      <div v-else class="chat-empty">
        <p>Select a session or create a new one to start chatting.</p>
      </div>
    </div>

    <!-- New session modal -->
    <div v-if="showNewSession" class="modal-overlay" @click.self="showNewSession = false">
      <div class="modal">
        <h2>New Chat Session</h2>
        <form @submit.prevent="handleCreateSession">
          <div class="form-group">
            <label for="session-title">Title (optional)</label>
            <input
              id="session-title"
              v-model="newSessionForm.title"
              class="form-input"
              placeholder="Session title"
            />
          </div>
          <div class="form-group">
            <label for="session-scope">Scope</label>
            <select id="session-scope" v-model="newSessionForm.scope_type" class="form-input">
              <option value="freeform">Freeform</option>
              <option value="project">Project</option>
              <option value="task">Task</option>
            </select>
          </div>

          <!-- Agent selector -->
          <div class="form-group">
            <label for="session-agent">Agent</label>
            <select
              id="session-agent"
              v-model="newSessionForm.agent_id"
              class="form-input"
              @change="onAgentSelected"
            >
              <option value="">No agent (manual chat)</option>
              <option
                v-for="agent in onlineAgents"
                :key="agent.id"
                :value="agent.id"
              >
                {{ agent.name }} ({{ agent.machine_info?.hostname ?? 'unknown' }})
              </option>
            </select>
            <div v-if="onlineAgents.length === 0" class="form-hint">
              No agents online. Start an agent daemon to enable AI chat.
            </div>
          </div>

          <!-- Persona selector (when agent is selected) -->
          <div v-if="newSessionForm.agent_id && selectedAgentPersonas.length > 0" class="form-group">
            <label for="session-persona">Persona</label>
            <select id="session-persona" v-model="newSessionForm.persona_id" class="form-input" required>
              <option value="" disabled>Select a persona</option>
              <option
                v-for="persona in selectedAgentPersonas"
                :key="persona.id"
                :value="persona.id"
              >
                {{ persona.name }} — {{ persona.role_description }}
              </option>
            </select>
          </div>
          <div v-if="newSessionForm.agent_id && selectedAgentPersonas.length === 0" class="form-group">
            <div class="form-hint">
              This agent has no personas configured. Create a persona in the Agents page first.
            </div>
          </div>

          <div v-if="newSessionForm.scope_type === 'freeform'" class="form-group">
            <label for="session-wd">Working Directory</label>
            <input
              id="session-wd"
              v-model="newSessionForm.working_directory"
              class="form-input"
              placeholder="/path/to/project"
            />
            <div v-if="newSessionForm.working_directory" class="form-hint">
              The agent will run commands in this directory.
            </div>
          </div>

          <div class="modal-actions">
            <button type="button" class="btn" @click="showNewSession = false">Cancel</button>
            <button type="submit" class="btn btn-primary" :disabled="!canCreateSession">Create</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat-layout {
  display: flex;
  height: calc(100vh - var(--topbar-height) - 48px);
  margin: -24px;
}

.chat-sidebar {
  width: 280px;
  min-width: 280px;
  border-right: 1px solid var(--color-border);
  background: var(--color-surface);
  display: flex;
  flex-direction: column;
}

.chat-sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px;
  border-bottom: 1px solid var(--color-border);
}

.chat-sidebar-header h3 {
  font-size: 15px;
  font-weight: 600;
}

.chat-sidebar-filter {
  padding: 8px 16px;
}

.chat-sidebar-filter .form-input {
  width: 100%;
  font-size: 13px;
  padding: 6px 10px;
}

.sessions-list {
  flex: 1;
  overflow-y: auto;
}

.session-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 12px 16px;
  border: none;
  background: none;
  cursor: pointer;
  text-align: left;
  font-family: inherit;
  font-size: 14px;
  color: var(--color-text);
  border-bottom: 1px solid var(--color-border);
  transition: background 0.1s;
}

.session-item:hover {
  background: var(--color-bg);
}

.session-item.active {
  background: var(--color-bg);
  border-left: 3px solid var(--color-primary);
}

.session-title {
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-date {
  font-size: 11px;
  color: var(--color-text-secondary);
  flex-shrink: 0;
  margin-left: 8px;
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.chat-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--color-border);
}

.chat-header h2 {
  font-size: 16px;
  font-weight: 600;
}

.badge-agent {
  background: var(--color-success, #22c55e);
  color: #fff;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 12px;
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.message {
  max-width: 720px;
  padding: 10px 14px;
  border-radius: var(--radius);
}

.msg-user {
  align-self: flex-end;
  background: var(--color-primary);
  color: #ffffff;
}

.msg-user .message-sender,
.msg-user .message-time {
  color: rgba(255, 255, 255, 0.7);
}

.msg-agent {
  align-self: flex-start;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
}

.msg-agent.streaming {
  border-color: var(--color-primary);
  border-style: dashed;
}

.msg-system {
  align-self: center;
  background: var(--color-bg);
  font-size: 13px;
  color: var(--color-text-secondary);
}

.message-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.message-sender {
  font-size: 12px;
  font-weight: 600;
}

.message-time {
  font-size: 11px;
  color: var(--color-text-secondary);
}

.streaming-indicator {
  font-size: 11px;
  color: var(--color-primary);
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.cursor-blink {
  animation: blink 1s step-end infinite;
  color: var(--color-primary);
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

.message-content {
  font-size: 14px;
  white-space: pre-wrap;
  word-break: break-word;
}

.chat-input-area {
  padding: 12px 20px;
  border-top: 1px solid var(--color-border);
  display: flex;
  gap: 8px;
  align-items: flex-end;
  position: relative;
}

.chat-textarea {
  flex: 1;
  resize: none;
  min-height: 40px;
  max-height: 120px;
}

.send-btn {
  flex-shrink: 0;
  height: 40px;
}

.chat-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-secondary);
}

/* Mention dropdown */
.mention-dropdown {
  position: absolute;
  bottom: 100%;
  left: 20px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  max-height: 200px;
  overflow-y: auto;
  min-width: 220px;
}

.mention-item {
  display: flex;
  flex-direction: column;
  width: 100%;
  padding: 8px 12px;
  border: none;
  background: none;
  cursor: pointer;
  text-align: left;
  font-family: inherit;
  color: var(--color-text);
  transition: background 0.1s;
}

.mention-item:hover {
  background: var(--color-bg);
}

.mention-name {
  font-weight: 600;
  font-size: 13px;
}

.mention-role {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.form-hint {
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-top: 4px;
}
</style>
