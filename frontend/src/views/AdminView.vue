<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { api } from '@/api/client'
import TellaroTable from '@/components/TellaroTable.vue'
import type { Column } from '@/components/TellaroTable.vue'
import type { DomainAuthConfig, User } from '@/types'

const activeTab = ref<'users' | 'domains' | 'health'>('users')

/* -- Users state -- */
const users = ref<User[]>([])
const usersLoading = ref(false)
const showUserForm = ref(false)
const editingUser = ref<User | null>(null)
const userForm = ref({ username: '', display_name: '', email: '', role: 'member', password: '' })

const userColumns: Column<User>[] = [
  { key: 'username', label: 'Username' },
  { key: 'display_name', label: 'Name' },
  { key: 'email', label: 'Email' },
  { key: 'role', label: 'Role' },
]

const userFieldSchema = [
  { name: 'username', type: 'keyword' as const },
  { name: 'email', type: 'keyword' as const },
  { name: 'display_name', type: 'text' as const },
  { name: 'role', type: 'keyword' as const },
  { name: 'is_active', type: 'boolean' as const },
]

/* -- Domain configs state -- */
const domains = ref<DomainAuthConfig[]>([])
const domainsLoading = ref(false)
const showDomainForm = ref(false)
const editingDomain = ref<DomainAuthConfig | null>(null)
const domainForm = ref({ domain: '', provider: 'local' as 'local' | 'github' | 'oidc', oidc_issuer: '', client_id: '' })

const domainColumns: Column<DomainAuthConfig>[] = [
  { key: 'domain', label: 'Domain' },
  { key: 'provider', label: 'Provider' },
  { key: 'oidc_issuer', label: 'OIDC Issuer', render: (v) => (v as string) ?? '-' },
]

const domainFieldSchema = [
  { name: 'domain', type: 'keyword' as const },
  { name: 'provider', type: 'keyword' as const },
]

onMounted(async () => {
  await loadUsers()
  await loadDomains()
})

/* -- Users -- */

async function loadUsers(): Promise<void> {
  usersLoading.value = true
  try {
    const res = await api.users.list()
    users.value = res.users ?? []
  } catch (e) {
    console.error('Failed to load users:', e)
    users.value = []
  } finally {
    usersLoading.value = false
  }
}

function openCreateUser(): void {
  editingUser.value = null
  userForm.value = { username: '', display_name: '', email: '', role: 'member', password: '' }
  showUserForm.value = true
}

function openEditUser(u: User): void {
  editingUser.value = u
  userForm.value = {
    username: u.username,
    display_name: u.display_name,
    email: u.email,
    role: u.role ?? 'member',
    password: '',
  }
  showUserForm.value = true
}

async function handleSaveUser(): Promise<void> {
  if (editingUser.value) {
    const data: Partial<User> = {
      username: userForm.value.username,
      display_name: userForm.value.display_name,
      email: userForm.value.email,
      role: userForm.value.role,
    }
    await api.users.update(editingUser.value.id, data)
  } else {
    await api.users.create({
      username: userForm.value.username,
      display_name: userForm.value.display_name,
      email: userForm.value.email,
      role: userForm.value.role,
      password: userForm.value.password,
    })
  }
  showUserForm.value = false
  await loadUsers()
}

async function handleDeleteUser(id: string): Promise<void> {
  if (!confirm('Delete this user?')) return
  await api.users.delete(id)
  await loadUsers()
}

/* -- Domain configs -- */

async function loadDomains(): Promise<void> {
  domainsLoading.value = true
  try {
    domains.value = await api.admin.domainConfigs()
  } catch (e) {
    console.error('Failed to load domain configs:', e)
    domains.value = []
  } finally {
    domainsLoading.value = false
  }
}

function openCreateDomain(): void {
  editingDomain.value = null
  domainForm.value = { domain: '', provider: 'local', oidc_issuer: '', client_id: '' }
  showDomainForm.value = true
}

function openEditDomain(d: DomainAuthConfig): void {
  editingDomain.value = d
  domainForm.value = {
    domain: d.domain,
    provider: d.provider,
    oidc_issuer: d.oidc_issuer ?? '',
    client_id: d.client_id ?? '',
  }
  showDomainForm.value = true
}

async function handleSaveDomain(): Promise<void> {
  const data: Partial<DomainAuthConfig> = {
    domain: domainForm.value.domain,
    provider: domainForm.value.provider,
    oidc_issuer: domainForm.value.oidc_issuer || undefined,
    client_id: domainForm.value.client_id || undefined,
  }
  if (editingDomain.value) {
    await api.admin.updateDomainConfig(editingDomain.value.id, data)
  } else {
    await api.admin.createDomainConfig(data)
  }
  showDomainForm.value = false
  await loadDomains()
}

async function handleDeleteDomain(id: string): Promise<void> {
  if (!confirm('Delete this domain config?')) return
  await api.admin.deleteDomainConfig(id)
  await loadDomains()
}
</script>

<template>
  <div>
    <div class="page-header">
      <h1>Admin</h1>
    </div>

    <div class="tabs">
      <button class="tab" :class="{ active: activeTab === 'users' }" @click="activeTab = 'users'">
        Users
      </button>
      <button class="tab" :class="{ active: activeTab === 'domains' }" @click="activeTab = 'domains'">
        Auth Domains
      </button>
      <button class="tab" :class="{ active: activeTab === 'health' }" @click="activeTab = 'health'">
        System Health
      </button>
    </div>

    <!-- Users tab -->
    <div v-if="activeTab === 'users'">
      <TellaroTable
        :columns="userColumns"
        :rows="users"
        :loading="usersLoading"
        :field-schema="userFieldSchema"
        :page-size="25"
      >
        <template #toolbar>
          <button class="btn btn-primary btn-sm" @click="openCreateUser">Add User</button>
        </template>
        <template #actions="{ row }">
          <button class="btn btn-sm" @click="openEditUser(row as User)">Edit</button>
          <button class="btn btn-sm btn-danger" @click="handleDeleteUser((row as User).id)">Delete</button>
        </template>
      </TellaroTable>
    </div>

    <!-- Auth Domains tab -->
    <div v-if="activeTab === 'domains'">
      <TellaroTable
        :columns="domainColumns"
        :rows="domains"
        :loading="domainsLoading"
        :field-schema="domainFieldSchema"
        :page-size="25"
      >
        <template #toolbar>
          <button class="btn btn-primary btn-sm" @click="openCreateDomain">Add Domain</button>
        </template>
        <template #actions="{ row }">
          <button class="btn btn-sm" @click="openEditDomain(row as DomainAuthConfig)">Edit</button>
          <button class="btn btn-sm btn-danger" @click="handleDeleteDomain((row as DomainAuthConfig).id)">Delete</button>
        </template>
      </TellaroTable>
    </div>

    <!-- System Health tab -->
    <div v-if="activeTab === 'health'">
      <div class="card health-card">
        <h3>System Health</h3>
        <p class="text-secondary">
          Health monitoring dashboard is a placeholder. Future versions will show API latency,
          database status, agent connectivity, and queue depths.
        </p>
        <div class="health-indicators">
          <div class="health-item">
            <span class="health-dot health-dot-green" />
            <span>API Server</span>
          </div>
          <div class="health-item">
            <span class="health-dot health-dot-green" />
            <span>Database</span>
          </div>
          <div class="health-item">
            <span class="health-dot health-dot-green" />
            <span>WebSocket Hub</span>
          </div>
        </div>
      </div>
    </div>

    <!-- User form modal -->
    <div v-if="showUserForm" class="modal-overlay" @click.self="showUserForm = false">
      <div class="modal">
        <h2>{{ editingUser ? 'Edit User' : 'Create User' }}</h2>
        <form @submit.prevent="handleSaveUser">
          <div class="form-group">
            <label for="user-username">Username</label>
            <input id="user-username" v-model="userForm.username" class="form-input" />
          </div>
          <div class="form-group">
            <label for="user-name">Display Name</label>
            <input id="user-name" v-model="userForm.display_name" class="form-input" />
          </div>
          <div class="form-group">
            <label for="user-email">Email</label>
            <input id="user-email" v-model="userForm.email" type="email" class="form-input" />
          </div>
          <div class="form-group">
            <label for="user-role">Role</label>
            <select id="user-role" v-model="userForm.role" class="form-input">
              <option value="member">Member</option>
              <option value="admin">Admin</option>
            </select>
          </div>
          <div v-if="!editingUser" class="form-group">
            <label for="user-password">Password</label>
            <input id="user-password" v-model="userForm.password" type="password" class="form-input" />
          </div>
          <div class="modal-actions">
            <button type="button" class="btn" @click="showUserForm = false">Cancel</button>
            <button type="submit" class="btn btn-primary">
              {{ editingUser ? 'Save' : 'Create' }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- Domain form modal -->
    <div v-if="showDomainForm" class="modal-overlay" @click.self="showDomainForm = false">
      <div class="modal">
        <h2>{{ editingDomain ? 'Edit Domain Config' : 'Add Domain Config' }}</h2>
        <form @submit.prevent="handleSaveDomain">
          <div class="form-group">
            <label for="domain-name">Domain</label>
            <input id="domain-name" v-model="domainForm.domain" class="form-input" placeholder="company.com" />
          </div>
          <div class="form-group">
            <label for="domain-provider">Provider</label>
            <select id="domain-provider" v-model="domainForm.provider" class="form-input">
              <option value="local">Local</option>
              <option value="github">GitHub</option>
              <option value="oidc">OIDC</option>
            </select>
          </div>
          <template v-if="domainForm.provider === 'oidc'">
            <div class="form-group">
              <label for="domain-issuer">OIDC Issuer URL</label>
              <input id="domain-issuer" v-model="domainForm.oidc_issuer" class="form-input" />
            </div>
            <div class="form-group">
              <label for="domain-client">Client ID</label>
              <input id="domain-client" v-model="domainForm.client_id" class="form-input" />
            </div>
          </template>
          <div class="modal-actions">
            <button type="button" class="btn" @click="showDomainForm = false">Cancel</button>
            <button type="submit" class="btn btn-primary">
              {{ editingDomain ? 'Save' : 'Create' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<style scoped>
.text-secondary {
  color: var(--color-text-secondary);
  font-size: 14px;
}

.health-card {
  max-width: 600px;
}

.health-card h3 {
  margin-bottom: 8px;
}

.health-indicators {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 20px;
}

.health-item {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
}

.health-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.health-dot-green {
  background: var(--color-success);
}

.health-dot-yellow {
  background: var(--color-warning);
}
</style>
