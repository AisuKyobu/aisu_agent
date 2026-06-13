import { ref } from 'vue'

export interface AuthUser {
  id: string
  username: string
  email: string | null
  email_verified: boolean
  role: string
}

export function useAuth() {
  const user = ref<AuthUser | null>(null)
  const loading = ref(true)
  const error = ref('')

  const token = (): string | null => localStorage.getItem('aisu_token')

  async function fetchMe() {
    loading.value = true
    try {
      const t = token()
      if (!t) { user.value = null; return }
      const r = await fetch('/api/auth/me', { headers: { Authorization: `Bearer ${t}` } })
      const data = await r.json()
      if (data.authenticated) user.value = data.user
      else { user.value = null; localStorage.removeItem('aisu_token') }
    } catch {
      user.value = null
    } finally { loading.value = false }
  }

  async function login(username: string, password: string) {
    error.value = ''
    const r = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })
    const data = await r.json()
    if (!r.ok) { error.value = data.detail || '登录失败'; return false }
    localStorage.setItem('aisu_token', data.token)
    user.value = data.user
    return true
  }

  async function register(username: string, password: string, email: string) {
    error.value = ''
    const r = await fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password, email }),
    })
    const data = await r.json()
    if (!r.ok) { error.value = data.detail || '注册失败'; return false }
    localStorage.setItem('aisu_token', data.token)
    user.value = data.user
    return true
  }

  function logout() {
    localStorage.removeItem('aisu_token')
    user.value = null
  }

  return { user, loading, error, token, fetchMe, login, register, logout }
}
