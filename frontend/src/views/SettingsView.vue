<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { useAuthStore } from '@/stores/auth'
import type { DeviceSession } from '@/types'

const auth = useAuthStore()
const sessions = ref<DeviceSession[]>([])
const sessionsLoading = ref(false)

onMounted(async () => {
  await loadSessions()
})

async function loadSessions(): Promise<void> {
  sessionsLoading.value = true
  try {
    sessions.value = await auth.listSessions()
  } catch (e) {
    console.error('Failed to load sessions:', e)
    sessions.value = []
  } finally {
    sessionsLoading.value = false
  }
}

async function handleDeleteSession(sessionId: string): Promise<void> {
  if (!confirm('Revoke this device session? The device will need to log in again.')) return
  await auth.deleteSession(sessionId)
  await loadSessions()
}

async function handleRevokeAll(): Promise<void> {
  if (!confirm('Revoke all other sessions? All other devices will be logged out.')) return
  const count = await auth.revokeAllSessions()
  alert(`Revoked ${count} session(s).`)
  await loadSessions()
}

function deviceIcon(deviceType: string): string {
  switch (deviceType) {
    case 'mobile':
      return '📱'
    case 'tablet':
      return '📱'
    default:
      return '💻'
  }
}

function formatDate(iso: string): string {
  if (!iso) return '-'
  const d = new Date(iso)
  const now = new Date()
  const diff = now.getTime() - d.getTime()

  if (diff < 60_000) return 'Just now'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`
  if (diff < 604_800_000) return `${Math.floor(diff / 86_400_000)}d ago`
  return d.toLocaleDateString()
}
</script>

<template>
  <div>
    <div class="page-header">
      <h1>Settings</h1>
    </div>

    <div class="settings-section">
      <div class="section-header">
        <h2>Device Sessions</h2>
        <button
          v-if="sessions.length > 1"
          class="btn btn-sm btn-danger"
          @click="handleRevokeAll"
        >
          Revoke All Other Sessions
        </button>
      </div>
      <p class="text-secondary">
        These are the devices currently logged into your account.
        You can have up to 10 active sessions.
      </p>

      <div v-if="sessionsLoading" class="sessions-loading">Loading sessions...</div>

      <div v-else class="sessions-list">
        <div
          v-for="session in sessions"
          :key="session.id"
          class="session-card"
          :class="{ 'session-current': session.is_current }"
        >
          <div class="session-icon">{{ deviceIcon(session.device_type) }}</div>
          <div class="session-info">
            <div class="session-device">
              {{ session.device_name }}
              <span v-if="session.is_current" class="current-badge">This device</span>
            </div>
            <div class="session-details">
              <span>{{ session.ip_address }}</span>
              <span class="session-dot" />
              <span>Last active {{ formatDate(session.last_used_at) }}</span>
            </div>
            <div class="session-details">
              <span>Signed in {{ formatDate(session.created_at) }}</span>
              <span v-if="session.last_ip !== session.ip_address" class="session-dot" />
              <span v-if="session.last_ip !== session.ip_address">
                Last IP: {{ session.last_ip }}
              </span>
            </div>
          </div>
          <div class="session-actions">
            <button
              v-if="!session.is_current"
              class="btn btn-sm"
              @click="handleDeleteSession(session.id)"
            >
              Revoke
            </button>
          </div>
        </div>

        <div v-if="sessions.length === 0" class="sessions-empty">
          No active sessions found.
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.settings-section {
  max-width: 700px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}

.section-header h2 {
  margin: 0;
  font-size: 18px;
}

.text-secondary {
  color: var(--color-text-secondary);
  font-size: 14px;
  margin-bottom: 20px;
}

.sessions-loading {
  color: var(--color-text-secondary);
  padding: 24px 0;
  font-size: 14px;
}

.sessions-list {
  display: flex;
  flex-direction: column;
  gap: 1px;
  background: var(--color-border);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.session-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px 20px;
  background: var(--color-surface);
}

.session-current {
  background: var(--color-bg);
}

.session-icon {
  font-size: 24px;
  width: 40px;
  text-align: center;
  flex-shrink: 0;
}

.session-info {
  flex: 1;
  min-width: 0;
}

.session-device {
  font-size: 14px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}

.current-badge {
  font-size: 11px;
  font-weight: 500;
  color: var(--color-primary);
  background: rgba(59, 130, 246, 0.1);
  padding: 2px 8px;
  border-radius: 10px;
}

.session-details {
  font-size: 12px;
  color: var(--color-text-secondary);
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 3px;
}

.session-dot {
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: var(--color-text-secondary);
}

.session-actions {
  flex-shrink: 0;
}

.sessions-empty {
  padding: 32px;
  text-align: center;
  color: var(--color-text-secondary);
  background: var(--color-surface);
  font-size: 14px;
}
</style>
