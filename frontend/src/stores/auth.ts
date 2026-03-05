import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { api, ApiError, setToken } from '@/api/client'
import type { AuthDiscoveryResponse, User } from '@/types'

export const useAuthStore = defineStore('auth', () => {
  /* ---- state ----------------------------------------------------- */
  const user = ref<User | null>(null)
  const token = ref<string | null>(localStorage.getItem('auth_token'))
  const isLoading = ref(false)

  /* ---- getters --------------------------------------------------- */
  const isAuthenticated = computed(() => !!token.value)
  const isAdmin = computed(() => user.value?.role === 'admin')

  /* ---- actions --------------------------------------------------- */

  async function discover(email: string): Promise<AuthDiscoveryResponse> {
    isLoading.value = true
    try {
      return await api.auth.discover(email)
    } finally {
      isLoading.value = false
    }
  }

  async function loginLocal(email: string, password: string): Promise<void> {
    isLoading.value = true
    try {
      const res = await api.auth.login(email, password)
      token.value = res.access_token
      setToken(res.access_token)
      await fetchMe()
    } finally {
      isLoading.value = false
    }
  }

  async function handleOAuthCallback(
    provider: 'github' | 'oidc',
    code: string,
    state?: string,
  ): Promise<void> {
    isLoading.value = true
    try {
      const res =
        provider === 'github'
          ? await api.auth.githubCallback(code)
          : await api.auth.oidcCallback(code, state)
      token.value = res.access_token
      setToken(res.access_token)
      await fetchMe()
    } finally {
      isLoading.value = false
    }
  }

  async function fetchMe(): Promise<void> {
    isLoading.value = true
    try {
      user.value = await api.auth.me()
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout()
      }
      throw err
    } finally {
      isLoading.value = false
    }
  }

  function logout(): void {
    user.value = null
    token.value = null
    setToken(null)
  }

  /* ---- init: if we have a stored token, try to fetch user -------- */
  async function init(): Promise<void> {
    if (token.value) {
      setToken(token.value)
      try {
        await fetchMe()
      } catch {
        /* token invalid, clear it silently */
        logout()
      }
    }
  }

  return {
    user,
    token,
    isLoading,
    isAuthenticated,
    isAdmin,
    discover,
    loginLocal,
    handleOAuthCallback,
    fetchMe,
    logout,
    init,
  }
})
