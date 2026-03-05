import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { api, ApiError, setRefreshToken, setToken } from '@/api/client'
import type { AuthDiscoveryResponse, DeviceSession, User } from '@/types'

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
      setRefreshToken(res.refresh_token)
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
      setRefreshToken(res.refresh_token)
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
      // 401 is handled by the apiFetch interceptor (auto-refresh + force logout)
      // If we still get here with a 401, the token was already cleared
      if (err instanceof ApiError && err.status === 401) {
        user.value = null
        token.value = null
      }
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function logout(): Promise<void> {
    try {
      await api.auth.logout()
    } catch {
      // Best effort — server may be unreachable
    }
    user.value = null
    token.value = null
    setToken(null)
    setRefreshToken(null)
  }

  /* ---- device sessions ------------------------------------------- */

  async function listSessions(): Promise<DeviceSession[]> {
    return api.auth.sessions()
  }

  async function deleteSession(sessionId: string): Promise<void> {
    await api.auth.deleteSession(sessionId)
  }

  async function revokeAllSessions(): Promise<number> {
    const res = await api.auth.revokeAllSessions()
    return res.revoked
  }

  /* ---- init: if we have a stored token, try to fetch user -------- */
  async function init(): Promise<void> {
    if (token.value) {
      setToken(token.value)
      // Also restore refresh token
      const storedRefresh = localStorage.getItem('refresh_token')
      if (storedRefresh) {
        setRefreshToken(storedRefresh)
      }
      try {
        await fetchMe()
      } catch {
        /* token invalid — apiFetch interceptor handles logout */
        user.value = null
        token.value = null
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
    listSessions,
    deleteSession,
    revokeAllSessions,
    init,
  }
})
