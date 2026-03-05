import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api } from '@/api/client'
import type { Project } from '@/types'

export const useProjectsStore = defineStore('projects', () => {
  const projects = ref<Project[]>([])
  const currentProject = ref<Project | null>(null)
  const isLoading = ref(false)

  async function fetchProjects(): Promise<void> {
    isLoading.value = true
    try {
      const res = await api.projects.list()
      projects.value = res.items
    } finally {
      isLoading.value = false
    }
  }

  async function fetchProject(id: string): Promise<void> {
    isLoading.value = true
    try {
      currentProject.value = await api.projects.get(id)
    } finally {
      isLoading.value = false
    }
  }

  async function createProject(data: Partial<Project>): Promise<Project> {
    isLoading.value = true
    try {
      const project = await api.projects.create(data)
      projects.value.push(project)
      return project
    } finally {
      isLoading.value = false
    }
  }

  async function updateProject(id: string, data: Partial<Project>): Promise<void> {
    isLoading.value = true
    try {
      const updated = await api.projects.update(id, data)
      const idx = projects.value.findIndex((p) => p.id === id)
      if (idx !== -1) projects.value[idx] = updated
      if (currentProject.value?.id === id) currentProject.value = updated
    } finally {
      isLoading.value = false
    }
  }

  async function deleteProject(id: string): Promise<void> {
    isLoading.value = true
    try {
      await api.projects.delete(id)
      projects.value = projects.value.filter((p) => p.id !== id)
      if (currentProject.value?.id === id) currentProject.value = null
    } finally {
      isLoading.value = false
    }
  }

  return {
    projects,
    currentProject,
    isLoading,
    fetchProjects,
    fetchProject,
    createProject,
    updateProject,
    deleteProject,
  }
})
