<script setup lang="ts">
import { onMounted } from 'vue'
import { RouterLink, RouterView, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()

onMounted(async () => {
  await auth.init()
})

function handleLogout(): void {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <div v-if="auth.isAuthenticated" class="app-layout">
    <!-- Sidebar -->
    <aside class="sidebar">
      <div class="sidebar-brand">
        <h2>Tellaro PM</h2>
      </div>
      <nav class="sidebar-nav">
        <RouterLink to="/" class="nav-link">
          <span class="nav-icon">&#9632;</span>
          Dashboard
        </RouterLink>
        <RouterLink to="/projects" class="nav-link">
          <span class="nav-icon">&#9776;</span>
          Projects
        </RouterLink>
        <RouterLink to="/chat" class="nav-link">
          <span class="nav-icon">&#9993;</span>
          Chat
        </RouterLink>
        <RouterLink to="/agents" class="nav-link">
          <span class="nav-icon">&#9881;</span>
          Agents
        </RouterLink>
        <RouterLink v-if="auth.isAdmin" to="/admin" class="nav-link">
          <span class="nav-icon">&#9874;</span>
          Admin
        </RouterLink>
      </nav>
    </aside>

    <!-- Main content -->
    <div class="main-wrapper">
      <header class="top-bar">
        <div class="top-bar-left">
          <!-- breadcrumb slot could go here -->
        </div>
        <div class="top-bar-right">
          <span class="user-info">{{ auth.user?.display_name ?? auth.user?.username }}</span>
          <button class="btn btn-sm" @click="handleLogout">Logout</button>
        </div>
      </header>
      <main class="main-content">
        <RouterView />
      </main>
    </div>
  </div>

  <!-- Unauthenticated: render route directly (login page) -->
  <RouterView v-else />
</template>

<style>
/* ------------------------------------------------------------------ */
/*  CSS Variables / Theming                                           */
/* ------------------------------------------------------------------ */
:root {
  --color-bg: #f5f6fa;
  --color-surface: #ffffff;
  --color-sidebar: #1a1d23;
  --color-sidebar-text: #b0b4c0;
  --color-sidebar-active: #ffffff;
  --color-sidebar-hover-bg: rgba(255, 255, 255, 0.06);
  --color-primary: #4f6ef7;
  --color-primary-hover: #3b5de7;
  --color-text: #1a1d23;
  --color-text-secondary: #6b7280;
  --color-border: #e5e7eb;
  --color-danger: #ef4444;
  --color-success: #22c55e;
  --color-warning: #f59e0b;
  --color-topbar-bg: #ffffff;
  --radius: 6px;
  --radius-lg: 10px;
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.05);
  --shadow: 0 1px 3px rgba(0, 0, 0, 0.1), 0 1px 2px rgba(0, 0, 0, 0.06);
  --sidebar-width: 240px;
  --topbar-height: 56px;
  --font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

/* dark theme toggle */
:root.dark {
  --color-bg: #111318;
  --color-surface: #1a1d23;
  --color-sidebar: #0d0f13;
  --color-text: #e5e7eb;
  --color-text-secondary: #9ca3af;
  --color-border: #2d3139;
  --color-topbar-bg: #1a1d23;
}

/* ------------------------------------------------------------------ */
/*  Global resets                                                     */
/* ------------------------------------------------------------------ */
*,
*::before,
*::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

html,
body,
#app {
  height: 100%;
}

body {
  font-family: var(--font-family);
  background: var(--color-bg);
  color: var(--color-text);
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}

a {
  color: var(--color-primary);
  text-decoration: none;
}

/* ------------------------------------------------------------------ */
/*  Layout                                                            */
/* ------------------------------------------------------------------ */
.app-layout {
  display: flex;
  height: 100%;
}

/* Sidebar */
.sidebar {
  width: var(--sidebar-width);
  min-width: var(--sidebar-width);
  background: var(--color-sidebar);
  color: var(--color-sidebar-text);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

.sidebar-brand {
  padding: 20px 20px 12px;
}

.sidebar-brand h2 {
  font-size: 18px;
  font-weight: 700;
  color: #ffffff;
  letter-spacing: -0.3px;
}

.sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
}

.nav-link {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: var(--radius);
  color: var(--color-sidebar-text);
  font-size: 14px;
  font-weight: 500;
  transition: background 0.15s, color 0.15s;
}

.nav-link:hover {
  background: var(--color-sidebar-hover-bg);
  color: var(--color-sidebar-active);
}

.nav-link.router-link-active {
  background: var(--color-primary);
  color: #ffffff;
}

.nav-icon {
  font-size: 14px;
  width: 20px;
  text-align: center;
}

/* Main wrapper */
.main-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* Top bar */
.top-bar {
  height: var(--topbar-height);
  min-height: var(--topbar-height);
  background: var(--color-topbar-bg);
  border-bottom: 1px solid var(--color-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
}

.top-bar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user-info {
  font-size: 14px;
  color: var(--color-text-secondary);
}

/* Main content */
.main-content {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

/* ------------------------------------------------------------------ */
/*  Shared utility classes                                            */
/* ------------------------------------------------------------------ */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 16px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  color: var(--color-text);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.btn:hover {
  background: var(--color-bg);
}

.btn-primary {
  background: var(--color-primary);
  color: #ffffff;
  border-color: var(--color-primary);
}

.btn-primary:hover {
  background: var(--color-primary-hover);
}

.btn-danger {
  background: var(--color-danger);
  color: #ffffff;
  border-color: var(--color-danger);
}

.btn-sm {
  padding: 4px 10px;
  font-size: 13px;
}

.card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 20px;
  box-shadow: var(--shadow-sm);
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 16px;
}

.form-group label {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-secondary);
}

.form-input {
  padding: 8px 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  color: var(--color-text);
  font-size: 14px;
  font-family: inherit;
  outline: none;
  transition: border-color 0.15s;
}

.form-input:focus {
  border-color: var(--color-primary);
}

.form-input::placeholder {
  color: var(--color-text-secondary);
}

textarea.form-input {
  min-height: 80px;
  resize: vertical;
}

.badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

.badge-backlog { background: #e5e7eb; color: #374151; }
.badge-assigned { background: #dbeafe; color: #1d4ed8; }
.badge-in_progress { background: #fef3c7; color: #92400e; }
.badge-review { background: #ede9fe; color: #6d28d9; }
.badge-done { background: #d1fae5; color: #065f46; }

.badge-low { background: #e5e7eb; color: #374151; }
.badge-medium { background: #dbeafe; color: #1d4ed8; }
.badge-high { background: #fef3c7; color: #92400e; }
.badge-critical { background: #fee2e2; color: #991b1b; }

.badge-online { background: #d1fae5; color: #065f46; }
.badge-offline { background: #e5e7eb; color: #374151; }
.badge-busy { background: #fef3c7; color: #92400e; }

.badge-pending { background: #fef3c7; color: #92400e; }
.badge-approved { background: #d1fae5; color: #065f46; }
.badge-rejected { background: #fee2e2; color: #991b1b; }
.badge-completed { background: #d1fae5; color: #065f46; }
.badge-failed { background: #fee2e2; color: #991b1b; }
.badge-cancelled { background: #e5e7eb; color: #374151; }

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}

.page-header h1 {
  font-size: 24px;
  font-weight: 700;
}

.loading-spinner {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
  color: var(--color-text-secondary);
  font-size: 14px;
}

.empty-state {
  text-align: center;
  padding: 40px 20px;
  color: var(--color-text-secondary);
}

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: var(--color-surface);
  border-radius: var(--radius-lg);
  padding: 24px;
  width: 100%;
  max-width: 480px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2);
}

.modal h2 {
  margin-bottom: 16px;
  font-size: 18px;
}

.modal-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 20px;
}

.tabs {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--color-border);
  margin-bottom: 20px;
}

.tab {
  padding: 10px 20px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text-secondary);
  border-bottom: 2px solid transparent;
  transition: color 0.15s, border-color 0.15s;
  background: none;
  border-top: none;
  border-left: none;
  border-right: none;
}

.tab:hover {
  color: var(--color-text);
}

.tab.active {
  color: var(--color-primary);
  border-bottom-color: var(--color-primary);
}
</style>
