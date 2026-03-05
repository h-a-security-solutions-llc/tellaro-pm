import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api } from '@/api/client'
import type {
  AgentInstallation,
  AgentPersona,
  WorkItem,
  WorkItemStatus,
  WorkRequest,
} from '@/types'

export const useAgentsStore = defineStore('agents', () => {
  const agents = ref<AgentInstallation[]>([])
  const personas = ref<AgentPersona[]>([])
  const workItems = ref<WorkItem[]>([])
  const workRequests = ref<WorkRequest[]>([])
  const isLoading = ref(false)

  /* -- agents ------------------------------------------------------ */

  async function fetchAgents(): Promise<void> {
    isLoading.value = true
    try {
      agents.value = await api.agents.list()
    } finally {
      isLoading.value = false
    }
  }

  /* -- personas ---------------------------------------------------- */

  async function fetchPersonas(agentId: string): Promise<void> {
    isLoading.value = true
    try {
      personas.value = await api.agents.personas(agentId)
    } finally {
      isLoading.value = false
    }
  }

  async function createPersona(
    agentId: string,
    data: Partial<AgentPersona>,
  ): Promise<AgentPersona> {
    isLoading.value = true
    try {
      const persona = await api.agents.createPersona(agentId, data)
      personas.value.push(persona)
      return persona
    } finally {
      isLoading.value = false
    }
  }

  async function updatePersona(
    id: string,
    data: Partial<AgentPersona>,
  ): Promise<void> {
    isLoading.value = true
    try {
      const updated = await api.agents.updatePersona(id, data)
      const idx = personas.value.findIndex((p) => p.id === id)
      if (idx !== -1) personas.value[idx] = updated
    } finally {
      isLoading.value = false
    }
  }

  /* -- work items -------------------------------------------------- */

  async function fetchWorkItems(filters?: {
    status?: WorkItemStatus
    agent_id?: string
    task_id?: string
  }): Promise<void> {
    isLoading.value = true
    try {
      workItems.value = await api.workItems.list(filters)
    } finally {
      isLoading.value = false
    }
  }

  /* -- work requests ----------------------------------------------- */

  async function fetchWorkRequests(): Promise<void> {
    isLoading.value = true
    try {
      workRequests.value = await api.workRequests.list()
    } finally {
      isLoading.value = false
    }
  }

  async function approveRequest(id: string): Promise<void> {
    const updated = await api.workRequests.approve(id)
    const idx = workRequests.value.findIndex((r) => r.id === id)
    if (idx !== -1) workRequests.value[idx] = updated
  }

  async function rejectRequest(id: string, reason?: string): Promise<void> {
    const updated = await api.workRequests.reject(id, reason)
    const idx = workRequests.value.findIndex((r) => r.id === id)
    if (idx !== -1) workRequests.value[idx] = updated
  }

  return {
    agents,
    personas,
    workItems,
    workRequests,
    isLoading,
    fetchAgents,
    fetchPersonas,
    createPersona,
    updatePersona,
    fetchWorkItems,
    fetchWorkRequests,
    approveRequest,
    rejectRequest,
  }
})
