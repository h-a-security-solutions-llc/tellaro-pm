import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api } from '@/api/client'
import type { ChatMessage, ChatSession, ScopeType } from '@/types'

export const useChatStore = defineStore('chat', () => {
  const sessions = ref<ChatSession[]>([])
  const currentSession = ref<ChatSession | null>(null)
  const messages = ref<ChatMessage[]>([])
  const isLoading = ref(false)

  /** Streaming state — accumulates partial output from agent */
  const streamingContent = ref('')
  const isStreaming = ref(false)
  const streamingWorkItemId = ref<string | null>(null)

  /** Active WebSocket connection for the current session */
  let chatWs: WebSocket | null = null

  async function fetchSessions(
    scopeType?: ScopeType,
    scopeId?: string,
  ): Promise<void> {
    isLoading.value = true
    try {
      sessions.value = await api.chat.sessions(scopeType, scopeId)
    } finally {
      isLoading.value = false
    }
  }

  async function createSession(data: Partial<ChatSession>): Promise<ChatSession> {
    isLoading.value = true
    try {
      const session = await api.chat.createSession(data)
      sessions.value.unshift(session)
      return session
    } finally {
      isLoading.value = false
    }
  }

  async function selectSession(sessionId: string): Promise<void> {
    isLoading.value = true
    try {
      currentSession.value = await api.chat.getSession(sessionId)
      messages.value = await api.chat.messages(sessionId)

      // Connect chat WebSocket if session is agent-bound
      disconnectChatWs()
      if (currentSession.value.agent_id) {
        connectChatWs(sessionId)
      }
    } finally {
      isLoading.value = false
    }
  }

  async function fetchMessages(
    sessionId: string,
    limit?: number,
  ): Promise<void> {
    isLoading.value = true
    try {
      messages.value = await api.chat.messages(sessionId, limit)
    } finally {
      isLoading.value = false
    }
  }

  async function sendMessage(
    sessionId: string,
    content: string,
    mentions?: Array<{ mention_type: string; target_id: string }>,
  ): Promise<ChatMessage> {
    const msg = await api.chat.sendMessage(sessionId, content, mentions)
    messages.value.push(msg)
    return msg
  }

  async function searchMessages(query: string): Promise<ChatMessage[]> {
    isLoading.value = true
    try {
      return await api.chat.search(query)
    } finally {
      isLoading.value = false
    }
  }

  function connectChatWs(sessionId: string): void {
    const url = api.chat.streamUrl(sessionId)
    chatWs = new WebSocket(url)

    chatWs.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        handleWsMessage(data)
      } catch {
        // ignore non-JSON
      }
    }

    chatWs.onclose = () => {
      chatWs = null
    }

    chatWs.onerror = () => {
      chatWs = null
    }
  }

  function disconnectChatWs(): void {
    if (chatWs) {
      chatWs.close()
      chatWs = null
    }
    streamingContent.value = ''
    isStreaming.value = false
    streamingWorkItemId.value = null
  }

  function handleWsMessage(data: Record<string, unknown>): void {
    switch (data.type) {
      case 'stream_start':
        isStreaming.value = true
        streamingContent.value = ''
        streamingWorkItemId.value = (data.work_item_id as string) ?? null
        break

      case 'stream_chunk':
        streamingContent.value += (data.content as string) ?? ''
        break

      case 'stream_end': {
        isStreaming.value = false
        const finalContent = (data.content as string) ?? streamingContent.value

        // Add the agent's response as a message in the local list
        if (finalContent) {
          const agentMsg: ChatMessage = {
            id: `stream-${Date.now()}`,
            session_id: currentSession.value?.id ?? '',
            sender_type: 'agent',
            sender_id: currentSession.value?.agent_id ?? '',
            sender_name: 'Agent',
            content: finalContent,
            created_at: new Date().toISOString(),
          }
          messages.value.push(agentMsg)
        }

        streamingContent.value = ''
        streamingWorkItemId.value = null
        break
      }

      case 'message': {
        // A new message from another participant
        const msg = data.message as ChatMessage | undefined
        if (msg && !messages.value.find((m) => m.id === msg.id)) {
          messages.value.push(msg)
        }
        break
      }

      case 'work_item_update':
        // Could show status indicator — ignored for now
        break
    }
  }

  return {
    sessions,
    currentSession,
    messages,
    isLoading,
    streamingContent,
    isStreaming,
    streamingWorkItemId,
    fetchSessions,
    createSession,
    selectSession,
    fetchMessages,
    sendMessage,
    searchMessages,
    disconnectChatWs,
  }
})
