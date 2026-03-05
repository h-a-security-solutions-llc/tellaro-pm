import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api } from '@/api/client'
import type { Task, TaskStatus } from '@/types'

export const useTasksStore = defineStore('tasks', () => {
  const tasks = ref<Task[]>([])
  const currentTask = ref<Task | null>(null)
  const isLoading = ref(false)

  async function fetchTasks(
    projectId: string,
    filters?: { status?: TaskStatus; assignee_id?: string },
  ): Promise<void> {
    isLoading.value = true
    try {
      const res = await api.tasks.list(projectId, filters)
      tasks.value = res.items
    } finally {
      isLoading.value = false
    }
  }

  async function fetchTask(id: string): Promise<void> {
    isLoading.value = true
    try {
      currentTask.value = await api.tasks.get(id)
    } finally {
      isLoading.value = false
    }
  }

  async function createTask(data: Partial<Task>): Promise<Task> {
    isLoading.value = true
    try {
      const task = await api.tasks.create(data)
      tasks.value.push(task)
      return task
    } finally {
      isLoading.value = false
    }
  }

  async function updateTask(id: string, data: Partial<Task>): Promise<void> {
    isLoading.value = true
    try {
      const updated = await api.tasks.update(id, data)
      _replaceInList(id, updated)
    } finally {
      isLoading.value = false
    }
  }

  async function updateStatus(id: string, status: TaskStatus): Promise<void> {
    isLoading.value = true
    try {
      const updated = await api.tasks.updateStatus(id, status)
      _replaceInList(id, updated)
    } finally {
      isLoading.value = false
    }
  }

  async function assignTask(id: string, userId: string): Promise<void> {
    isLoading.value = true
    try {
      const updated = await api.tasks.assign(id, userId)
      _replaceInList(id, updated)
    } finally {
      isLoading.value = false
    }
  }

  async function deleteTask(id: string): Promise<void> {
    isLoading.value = true
    try {
      await api.tasks.delete(id)
      tasks.value = tasks.value.filter((t) => t.id !== id)
      if (currentTask.value?.id === id) currentTask.value = null
    } finally {
      isLoading.value = false
    }
  }

  async function fetchSubtasks(taskId: string): Promise<Task[]> {
    isLoading.value = true
    try {
      return await api.tasks.subtasks(taskId)
    } finally {
      isLoading.value = false
    }
  }

  function _replaceInList(id: string, updated: Task): void {
    const idx = tasks.value.findIndex((t) => t.id === id)
    if (idx !== -1) tasks.value[idx] = updated
    if (currentTask.value?.id === id) currentTask.value = updated
  }

  return {
    tasks,
    currentTask,
    isLoading,
    fetchTasks,
    fetchTask,
    createTask,
    updateTask,
    updateStatus,
    assignTask,
    deleteTask,
    fetchSubtasks,
  }
})
