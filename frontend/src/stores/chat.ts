import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api } from '@/api/client'
import type { ChatMessage, ChatSession, ScopeType } from '@/types'

export const useChatStore = defineStore('chat', () => {
  const sessions = ref<ChatSession[]>([])
  const currentSession = ref<ChatSession | null>(null)
  const messages = ref<ChatMessage[]>([])
  const isLoading = ref(false)

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

  return {
    sessions,
    currentSession,
    messages,
    isLoading,
    fetchSessions,
    createSession,
    selectSession,
    fetchMessages,
    sendMessage,
    searchMessages,
  }
})
