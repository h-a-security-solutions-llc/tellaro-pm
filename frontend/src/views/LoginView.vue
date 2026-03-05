<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { setRefreshToken, setToken } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import type { AuthDiscoveryResponse } from '@/types'

const props = defineProps<{
  provider?: 'github' | 'oidc'
  code?: string
  state?: string
}>()

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const email = ref('')
const password = ref('')
const error = ref('')
const step = ref<'email' | 'password' | 'oauth'>('email')
const discovery = ref<AuthDiscoveryResponse | null>(null)

onMounted(async () => {
  /* Handle OAuth callback — props from callback routes, or query params as fallback */
  const code = props.code || (route.query.code as string | undefined)
  const provider = props.provider || (route.query.provider as 'github' | 'oidc' | undefined)
  const state = props.state || (route.query.state as string | undefined)

  if (code && provider && !auth.isAuthenticated) {
    // Clear any existing local tokens before attempting OAuth exchange —
    // a failed callback must never leave old tokens around.
    // Don't call backend logout (no valid token may exist yet).
    setToken(null)
    setRefreshToken(null)
    step.value = 'oauth'
    try {
      await auth.handleOAuthCallback(provider, code, state)
      await router.replace('/')
    } catch {
      error.value = 'OAuth login failed. Please try again.'
      step.value = 'email'
    }
  } else if (code && provider && auth.isAuthenticated) {
    // Already authenticated (remount from v-if/v-else RouterView switch) — just navigate away
    await router.replace('/')
  }
})

async function handleDiscover(): Promise<void> {
  error.value = ''
  if (!email.value.trim()) {
    error.value = 'Please enter your email address.'
    return
  }
  try {
    discovery.value = await auth.discover(email.value)
    if (discovery.value.provider === 'local') {
      step.value = 'password'
    } else {
      step.value = 'oauth'
    }
  } catch {
    error.value = 'Could not determine login method. Please try again.'
  }
}

async function handleLogin(): Promise<void> {
  error.value = ''
  try {
    await auth.loginLocal(email.value, password.value)
    const redirect = (route.query.redirect as string) || '/'
    await router.push(redirect)
  } catch {
    error.value = 'Invalid email or password.'
  }
}

function handleOAuthRedirect(): void {
  if (discovery.value?.redirect_url) {
    window.location.href = discovery.value.redirect_url
  }
}

function resetFlow(): void {
  step.value = 'email'
  password.value = ''
  discovery.value = null
  error.value = ''
}
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <h1 class="login-title">Tellaro PM</h1>
      <p class="login-subtitle">Sign in to continue</p>

      <div v-if="error" class="login-error">{{ error }}</div>

      <!-- Step 1: Email -->
      <form v-if="step === 'email'" @submit.prevent="handleDiscover">
        <div class="form-group">
          <label for="email">Email</label>
          <input
            id="email"
            v-model="email"
            type="email"
            class="form-input"
            placeholder="you@company.com"
            autofocus
          />
        </div>
        <button type="submit" class="btn btn-primary login-btn" :disabled="auth.isLoading">
          {{ auth.isLoading ? 'Checking...' : 'Continue' }}
        </button>
      </form>

      <!-- Step 2a: Password (local) -->
      <form v-else-if="step === 'password'" @submit.prevent="handleLogin">
        <div class="login-email-display">
          {{ email }}
          <button type="button" class="link-btn" @click="resetFlow">Change</button>
        </div>
        <div class="form-group">
          <label for="password">Password</label>
          <input
            id="password"
            v-model="password"
            type="password"
            class="form-input"
            placeholder="Enter your password"
            autofocus
          />
        </div>
        <button type="submit" class="btn btn-primary login-btn" :disabled="auth.isLoading">
          {{ auth.isLoading ? 'Signing in...' : 'Sign In' }}
        </button>
      </form>

      <!-- Step 2b: OAuth redirect -->
      <div v-else-if="step === 'oauth'">
        <div class="login-email-display">
          {{ email }}
          <button type="button" class="link-btn" @click="resetFlow">Change</button>
        </div>
        <button class="btn btn-primary login-btn" @click="handleOAuthRedirect">
          Continue with {{ discovery?.display_name ?? discovery?.provider }}
        </button>
        <button type="button" class="link-btn login-fallback" @click="step = 'password'">
          Sign in with password instead
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: var(--color-bg);
}

.login-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 40px;
  width: 100%;
  max-width: 400px;
  box-shadow: var(--shadow);
}

.login-title {
  font-size: 24px;
  font-weight: 700;
  margin-bottom: 4px;
}

.login-subtitle {
  color: var(--color-text-secondary);
  font-size: 14px;
  margin-bottom: 24px;
}

.login-error {
  background: #fee2e2;
  color: #991b1b;
  padding: 10px 14px;
  border-radius: var(--radius);
  font-size: 13px;
  margin-bottom: 16px;
}

.login-btn {
  width: 100%;
  padding: 10px;
}

.login-email-display {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: var(--color-bg);
  border-radius: var(--radius);
  font-size: 14px;
  margin-bottom: 16px;
}

.link-btn {
  background: none;
  border: none;
  color: var(--color-primary);
  cursor: pointer;
  font-size: 13px;
  font-family: inherit;
}

.link-btn:hover {
  text-decoration: underline;
}

.login-fallback {
  display: block;
  width: 100%;
  text-align: center;
  margin-top: 12px;
}
</style>
