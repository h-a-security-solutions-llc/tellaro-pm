import type {
  AgentBinary,
  AgentInstallation,
  AgentLog,
  AgentPersona,
  AuthDiscoveryResponse,
  ChatMessage,
  ChatSession,
  DeviceSession,
  DomainAuthConfig,
  Paginated,
  Project,
  ProvisioningToken,
  ProvisioningTokenCreated,
  Task,
  TaskStatus,
  TokenResponse,
  User,
  WorkItem,
  WorkItemStatus,
  WorkRequest,
} from '@/types'

/* ------------------------------------------------------------------ */
/*  Low-level fetch helper                                            */
/* ------------------------------------------------------------------ */

const API_BASE = '/api/v1'

let _token: string | null = localStorage.getItem('auth_token')
let _refreshToken: string | null = localStorage.getItem('refresh_token')
let _refreshPromise: Promise<boolean> | null = null

export function setToken(token: string | null): void {
  _token = token
  if (token) {
    localStorage.setItem('auth_token', token)
  } else {
    localStorage.removeItem('auth_token')
  }
}

export function setRefreshToken(token: string | null): void {
  _refreshToken = token
  if (token) {
    localStorage.setItem('refresh_token', token)
  } else {
    localStorage.removeItem('refresh_token')
  }
}

export function getToken(): string | null {
  return _token
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public statusText: string,
    public body?: unknown,
  ) {
    super(`API error: ${status} ${statusText}`)
    this.name = 'ApiError'
  }
}

/** Attempt to refresh the access token. Returns true on success. */
async function tryRefresh(): Promise<boolean> {
  if (!_refreshToken) return false

  try {
    const response = await fetch(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: _refreshToken }),
    })

    if (!response.ok) {
      return false
    }

    const data = (await response.json()) as TokenResponse
    setToken(data.access_token)
    setRefreshToken(data.refresh_token)
    return true
  } catch {
    return false
  }
}

/**
 * Centralized logout: clears tokens and redirects to login.
 * Called when both access and refresh tokens are invalid.
 */
function forceLogout(): void {
  setToken(null)
  setRefreshToken(null)
  // Only redirect if not already on the login page
  if (!window.location.pathname.startsWith('/login')) {
    window.location.href = '/login'
  }
}

export async function apiFetch<T>(
  path: string,
  options?: RequestInit & { _isRetry?: boolean },
): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options?.headers as Record<string, string> | undefined),
  }

  if (_token) {
    headers['Authorization'] = `Bearer ${_token}`
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  })

  // Handle 401: try refresh once, then force logout
  if (response.status === 401 && !options?._isRetry) {
    // Deduplicate concurrent refresh attempts
    if (!_refreshPromise) {
      _refreshPromise = tryRefresh().finally(() => {
        _refreshPromise = null
      })
    }

    const refreshed = await _refreshPromise
    if (refreshed) {
      // Retry the original request with the new token
      return apiFetch<T>(path, { ...options, _isRetry: true })
    }

    // Refresh failed — force logout
    forceLogout()
    throw new ApiError(401, 'Unauthorized')
  }

  if (!response.ok) {
    let body: unknown
    try {
      body = await response.json()
    } catch {
      /* empty */
    }
    throw new ApiError(response.status, response.statusText, body)
  }

  /* 204 No Content */
  if (response.status === 204) {
    return undefined as unknown as T
  }

  return response.json() as Promise<T>
}

/* ------------------------------------------------------------------ */
/*  Helper to build query strings                                     */
/* ------------------------------------------------------------------ */

function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const entries = Object.entries(params).filter(
    (e): e is [string, string | number | boolean] => e[1] != null,
  )
  if (entries.length === 0) return ''
  return '?' + entries.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join('&')
}

/* ------------------------------------------------------------------ */
/*  API client object                                                 */
/* ------------------------------------------------------------------ */

export const api = {
  /* ------ health -------------------------------------------------- */

  health() {
    return apiFetch<{ status: string; version: string }>('/health')
  },

  /* ------ auth ---------------------------------------------------- */

  auth: {
    discover(email: string) {
      return apiFetch<AuthDiscoveryResponse>('/auth/discover', {
        method: 'POST',
        body: JSON.stringify({ email }),
      })
    },

    login(email: string, password: string) {
      return apiFetch<TokenResponse>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      })
    },

    refresh(refreshToken: string) {
      return apiFetch<TokenResponse>('/auth/refresh', {
        method: 'POST',
        body: JSON.stringify({ refresh_token: refreshToken }),
      })
    },

    githubCallback(code: string) {
      return apiFetch<TokenResponse>('/auth/github/callback', {
        method: 'POST',
        body: JSON.stringify({ code, state: 'x', provider: 'github' }),
      })
    },

    oidcCallback(code: string, state?: string) {
      return apiFetch<TokenResponse>('/auth/oidc/callback', {
        method: 'POST',
        body: JSON.stringify({ code, state: state ?? 'x', provider: 'oidc' }),
      })
    },

    me() {
      return apiFetch<User>('/auth/me')
    },

    logout() {
      return apiFetch<void>('/auth/logout', { method: 'POST' })
    },

    sessions() {
      return apiFetch<DeviceSession[]>('/auth/sessions')
    },

    deleteSession(sessionId: string) {
      return apiFetch<void>(`/auth/sessions/${sessionId}`, { method: 'DELETE' })
    },

    revokeAllSessions() {
      return apiFetch<{ revoked: number }>('/auth/sessions/revoke-all', { method: 'POST' })
    },
  },

  /* ------ users --------------------------------------------------- */

  users: {
    list(params?: { skip?: number; limit?: number; role?: string; q?: string }) {
      return apiFetch<{ users: User[]; total: number }>(`/users${qs(params ?? {})}`)
    },

    get(id: string) {
      return apiFetch<User>(`/users/${id}`)
    },

    create(data: Partial<User> & { password?: string }) {
      return apiFetch<User>('/users', {
        method: 'POST',
        body: JSON.stringify(data),
      })
    },

    update(id: string, data: Partial<User>) {
      return apiFetch<User>(`/users/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      })
    },

    delete(id: string) {
      return apiFetch<void>(`/users/${id}`, { method: 'DELETE' })
    },
  },

  /* ------ projects ------------------------------------------------ */

  projects: {
    list(page = 1, pageSize = 50) {
      return apiFetch<Paginated<Project>>(`/projects${qs({ page, page_size: pageSize })}`)
    },

    get(id: string) {
      return apiFetch<Project>(`/projects/${id}`)
    },

    create(data: Partial<Project>) {
      return apiFetch<Project>('/projects', {
        method: 'POST',
        body: JSON.stringify(data),
      })
    },

    update(id: string, data: Partial<Project>) {
      return apiFetch<Project>(`/projects/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      })
    },

    delete(id: string) {
      return apiFetch<void>(`/projects/${id}`, { method: 'DELETE' })
    },
  },

  /* ------ tasks --------------------------------------------------- */

  tasks: {
    list(
      projectId: string,
      filters?: { status?: TaskStatus; assignee_id?: string; page?: number; page_size?: number },
    ) {
      return apiFetch<Paginated<Task>>(
        `/projects/${projectId}/tasks${qs(filters ?? {})}`,
      )
    },

    get(id: string) {
      return apiFetch<Task>(`/tasks/${id}`)
    },

    create(data: Partial<Task>) {
      return apiFetch<Task>(`/projects/${data.project_id}/tasks`, {
        method: 'POST',
        body: JSON.stringify(data),
      })
    },

    update(id: string, data: Partial<Task>) {
      return apiFetch<Task>(`/tasks/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      })
    },

    updateStatus(id: string, status: TaskStatus) {
      return apiFetch<Task>(`/tasks/${id}/status`, {
        method: 'PATCH',
        body: JSON.stringify({ status }),
      })
    },

    assign(id: string, userId: string) {
      return apiFetch<Task>(`/tasks/${id}/assign`, {
        method: 'POST',
        body: JSON.stringify({ assignee_id: userId }),
      })
    },

    delete(id: string) {
      return apiFetch<void>(`/tasks/${id}`, { method: 'DELETE' })
    },

    subtasks(taskId: string) {
      return apiFetch<Task[]>(`/tasks/${taskId}/subtasks`)
    },
  },

  /* ------ chat ---------------------------------------------------- */

  chat: {
    async sessions(scopeType?: string, scopeId?: string) {
      const resp = await apiFetch<{ items: ChatSession[]; total: number }>(
        `/chat/sessions${qs({ scope_type: scopeType, scope_id: scopeId })}`,
      )
      return resp.items
    },

    getSession(id: string) {
      return apiFetch<ChatSession>(`/chat/sessions/${id}`)
    },

    createSession(data: Partial<ChatSession>) {
      return apiFetch<ChatSession>('/chat/sessions', {
        method: 'POST',
        body: JSON.stringify(data),
      })
    },

    async messages(sessionId: string, limit = 100, before?: string) {
      const resp = await apiFetch<{ items: ChatMessage[]; total: number }>(
        `/chat/sessions/${sessionId}/messages${qs({ limit, before })}`,
      )
      return resp.items
    },

    sendMessage(sessionId: string, content: string, mentions?: Array<{ mention_type: string; target_id: string }>) {
      return apiFetch<ChatMessage>(`/chat/sessions/${sessionId}/messages`, {
        method: 'POST',
        body: JSON.stringify({ content, mentions }),
      })
    },

    async search(query: string) {
      const resp = await apiFetch<{ items: ChatMessage[]; total: number }>(
        `/chat/search${qs({ q: query })}`,
      )
      return resp.items
    },

    /** Build a WebSocket URL for streaming chat session events. */
    streamUrl(sessionId: string): string {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const token = _token ?? ''
      return `${protocol}//${window.location.host}/ws/chat/${sessionId}?token=${encodeURIComponent(token)}`
    },
  },

  /* ------ agents -------------------------------------------------- */

  agents: {
    async list() {
      const resp = await apiFetch<{ items: AgentInstallation[]; total: number }>('/agents')
      return resp.items
    },

    get(id: string) {
      return apiFetch<AgentInstallation>(`/agents/${id}`)
    },

    personas(agentId: string) {
      return apiFetch<AgentPersona[]>(`/agents/${agentId}/personas`)
    },

    createPersona(agentId: string, data: Partial<AgentPersona>) {
      return apiFetch<AgentPersona>(`/agents/${agentId}/personas`, {
        method: 'POST',
        body: JSON.stringify(data),
      })
    },

    updatePersona(id: string, data: Partial<AgentPersona>) {
      return apiFetch<AgentPersona>(`/personas/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      })
    },

    deletePersona(id: string) {
      return apiFetch<void>(`/personas/${id}`, { method: 'DELETE' })
    },

    logs(agentId: string, params?: { level?: string; limit?: number; since?: string }) {
      return apiFetch<AgentLog[]>(`/agents/${agentId}/logs${qs(params ?? {})}`)
    },

    allLogs(params?: { agent_id?: string; level?: string; limit?: number; since?: string }) {
      return apiFetch<AgentLog[]>(`/agents/logs/all${qs(params ?? {})}`)
    },
  },

  /* ------ agent provisioning --------------------------------------- */

  provisioning: {
    createToken(data: { label?: string; expires_hours?: number }) {
      return apiFetch<ProvisioningTokenCreated>('/agents/provisioning/tokens', {
        method: 'POST',
        body: JSON.stringify(data),
      })
    },

    listTokens() {
      return apiFetch<ProvisioningToken[]>('/agents/provisioning/tokens')
    },

    revokeToken(tokenId: string) {
      return apiFetch<void>(`/agents/provisioning/tokens/${tokenId}`, {
        method: 'DELETE',
      })
    },

    listBinaries() {
      return apiFetch<AgentBinary[]>('/agents/provisioning/binaries')
    },

    binaryDownloadUrl(version: string, filename: string) {
      return `${API_BASE}/agents/provisioning/binaries/${version}/${filename}`
    },
  },

  /* ------ work items ---------------------------------------------- */

  workItems: {
    list(filters?: { status?: WorkItemStatus; agent_id?: string; task_id?: string }) {
      return apiFetch<WorkItem[]>(`/work-items${qs(filters ?? {})}`)
    },

    get(id: string) {
      return apiFetch<WorkItem>(`/work-items/${id}`)
    },
  },

  /* ------ work requests ------------------------------------------- */

  workRequests: {
    list() {
      return apiFetch<WorkRequest[]>('/work-requests')
    },

    approve(id: string) {
      return apiFetch<WorkRequest>(`/work-requests/${id}/approve`, {
        method: 'POST',
      })
    },

    reject(id: string, reason?: string) {
      return apiFetch<WorkRequest>(`/work-requests/${id}/reject`, {
        method: 'POST',
        body: JSON.stringify({ reason }),
      })
    },
  },

  /* ------ admin --------------------------------------------------- */

  admin: {
    domainConfigs() {
      return apiFetch<DomainAuthConfig[]>('/admin/domain-configs')
    },

    createDomainConfig(data: Partial<DomainAuthConfig>) {
      return apiFetch<DomainAuthConfig>('/admin/domain-configs', {
        method: 'POST',
        body: JSON.stringify(data),
      })
    },

    updateDomainConfig(id: string, data: Partial<DomainAuthConfig>) {
      return apiFetch<DomainAuthConfig>(`/admin/domain-configs/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      })
    },

    deleteDomainConfig(id: string) {
      return apiFetch<void>(`/admin/domain-configs/${id}`, { method: 'DELETE' })
    },
  },
} as const
