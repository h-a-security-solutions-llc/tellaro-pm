/* ------------------------------------------------------------------ */
/*  Enums / union types                                               */
/* ------------------------------------------------------------------ */

export type TaskStatus = 'backlog' | 'assigned' | 'in_progress' | 'review' | 'done'
export type TaskPriority = 'low' | 'medium' | 'high' | 'critical'
export type AgentStatus = 'online' | 'offline' | 'busy'
export type ScopeType = 'project' | 'task' | 'subtask' | 'freeform'
export type SenderType = 'user' | 'agent' | 'system'
export type MentionType = 'agent' | 'persona' | 'user'
export type WorkItemStatus = 'pending' | 'in_progress' | 'completed' | 'failed' | 'cancelled'
export type WorkRequestStatus = 'pending' | 'approved' | 'rejected'

/* ------------------------------------------------------------------ */
/*  Core domain models                                                */
/* ------------------------------------------------------------------ */

export interface User {
  id: string
  username: string
  display_name: string
  email: string
  avatar_url?: string
  role?: string
  created_at?: string
  updated_at?: string
}

export interface Project {
  id: string
  name: string
  description: string
  owner_id?: string
  members?: User[]
  created_at: string
  updated_at: string
}

export interface Task {
  id: string
  project_id: string
  parent_task_id?: string
  title: string
  description: string
  status: TaskStatus
  priority: TaskPriority
  assignee_id?: string
  assignee?: User
  subtasks?: Task[]
  chat_session_id?: string
  created_at: string
  updated_at: string
}

/* ------------------------------------------------------------------ */
/*  Agents                                                            */
/* ------------------------------------------------------------------ */

export interface AgentMachineInfo {
  os: string
  arch: string
  hostname: string
  home_directory?: string
}

export interface AgentInstallation {
  id: string
  user_id: string
  name: string
  status: AgentStatus
  machine_info: AgentMachineInfo
  capabilities: string[]
  personas: AgentPersona[]
  last_heartbeat?: string
  created_at?: string
}

export interface AgentLog {
  id: string
  agent_id: string
  user_id: string
  level: string
  message: string
  target: string
  timestamp: string
}

export interface AgentPersona {
  id: string
  agent_id: string
  name: string
  role_description: string
  skills: string[]
  created_at?: string
  updated_at?: string
}

/* ------------------------------------------------------------------ */
/*  Chat                                                              */
/* ------------------------------------------------------------------ */

export interface ChatSession {
  id: string
  scope_type: ScopeType
  scope_id?: string
  title?: string
  working_directory?: string
  agent_id?: string
  persona_id?: string
  created_by?: string
  created_at: string
  updated_at?: string
}

export interface Mention {
  id: string
  message_id: string
  mention_type: MentionType
  target_id: string
  target_name?: string
}

export interface ChatMessage {
  id: string
  session_id: string
  sender_type: SenderType
  sender_id: string
  sender_name?: string
  content: string
  mentions?: Mention[]
  created_at: string
}

/* ------------------------------------------------------------------ */
/*  Work items & requests                                             */
/* ------------------------------------------------------------------ */

export interface WorkItem {
  id: string
  task_id?: string
  agent_id?: string
  persona_id?: string
  title: string
  description?: string
  status: WorkItemStatus
  result?: string
  created_at: string
  updated_at: string
}

export interface WorkRequest {
  id: string
  work_item_id?: string
  agent_id?: string
  persona_id?: string
  request_type: string
  description: string
  status: WorkRequestStatus
  reviewed_by?: string
  reviewed_at?: string
  created_at: string
}

/* ------------------------------------------------------------------ */
/*  Auth                                                              */
/* ------------------------------------------------------------------ */

export interface AuthDiscoveryResponse {
  provider: 'local' | 'github' | 'oidc'
  redirect_url?: string
  display_name?: string
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface DeviceSession {
  id: string
  device_name: string
  browser: string
  browser_version: string
  os: string
  os_version: string
  device_type: string
  ip_address: string
  last_ip: string
  is_current: boolean
  last_used_at: string
  created_at: string
}

/* ------------------------------------------------------------------ */
/*  Pagination                                                        */
/* ------------------------------------------------------------------ */

export interface Paginated<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

/* ------------------------------------------------------------------ */
/*  Agent provisioning                                                */
/* ------------------------------------------------------------------ */

export interface ProvisioningToken {
  id: string
  user_id: string
  label: string
  is_used: boolean
  is_revoked: boolean
  used_at?: string
  expires_hours: number
  created_at: string
}

export interface ProvisioningTokenCreated {
  id: string
  token: string
  label: string
  expires_hours: number
  created_at: string
}

export interface AgentBinary {
  platform: string
  arch: string
  version: string
  filename: string
  size_bytes?: number
  sha256?: string
}

/* ------------------------------------------------------------------ */
/*  Domain auth config (admin)                                        */
/* ------------------------------------------------------------------ */

export interface DomainAuthConfig {
  id: string
  domain: string
  provider: 'local' | 'github' | 'oidc'
  oidc_issuer?: string
  client_id?: string
  created_at?: string
}
