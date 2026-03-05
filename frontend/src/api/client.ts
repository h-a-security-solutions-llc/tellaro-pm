import type {
  AgentInstallation,
  AgentPersona,
  AuthDiscoveryResponse,
  ChatMessage,
  ChatSession,
  DomainAuthConfig,
  Paginated,
  Project,
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

export function setToken(token: string | null): void {
  _token = token
  if (token) {
    localStorage.setItem('auth_token', token)
  } else {
    localStorage.removeItem('auth_token')
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

export async function apiFetch<T>(
  path: string,
  options?: RequestInit,
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

    githubCallback(code: string) {
      return apiFetch<TokenResponse>(`/auth/github/callback${qs({ code })}`)
    },

    oidcCallback(code: string, state?: string) {
      return apiFetch<TokenResponse>(`/auth/oidc/callback${qs({ code, state })}`)
    },

    me() {
      return apiFetch<User>('/auth/me')
    },
  },

  /* ------ users --------------------------------------------------- */

  users: {
    list(page = 1, pageSize = 50) {
      return apiFetch<Paginated<User>>(`/users${qs({ page, page_size: pageSize })}`)
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
    sessions(scopeType?: string, scopeId?: string) {
      return apiFetch<ChatSession[]>(`/chat/sessions${qs({ scope_type: scopeType, scope_id: scopeId })}`)
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

    messages(sessionId: string, limit = 100, before?: string) {
      return apiFetch<ChatMessage[]>(
        `/chat/sessions/${sessionId}/messages${qs({ limit, before })}`,
      )
    },

    sendMessage(sessionId: string, content: string, mentions?: Array<{ mention_type: string; target_id: string }>) {
      return apiFetch<ChatMessage>(`/chat/sessions/${sessionId}/messages`, {
        method: 'POST',
        body: JSON.stringify({ content, mentions }),
      })
    },

    search(query: string) {
      return apiFetch<ChatMessage[]>(`/chat/search${qs({ q: query })}`)
    },
  },

  /* ------ agents -------------------------------------------------- */

  agents: {
    list() {
      return apiFetch<AgentInstallation[]>('/agents')
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
