<script setup lang="ts">
import { ref } from 'vue'
import { useAuth } from '../composables/useAuth'

const emit = defineEmits<{ switchPage: [page: string] }>()
const auth = useAuth()

const username = ref('')
const password = ref('')
const loading = ref(false)

async function doLogin() {
  loading.value = true
  const ok = await auth.login(username.value, password.value)
  loading.value = false
  if (!ok) return
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-card">
      <div class="auth-header">
        <button type="button" class="btn-back" @click="emit('switchPage', '')">← 返回</button>
        <h2>登录</h2>
      </div>
      <form @submit.prevent="doLogin">
        <label>用户名</label>
        <input v-model="username" type="text" autocomplete="username" placeholder="输入用户名" />
        <label>密码</label>
        <input v-model="password" type="password" autocomplete="current-password" placeholder="输入密码" />
        <p v-if="auth.error.value" class="auth-error">{{ auth.error.value }}</p>
        <button type="submit" class="btn btn-primary" :disabled="loading">
          {{ loading ? '登录中...' : '登录' }}
        </button>
      </form>
      <p class="auth-switch">
        还没有账号？<a href="#" @click.prevent="emit('switchPage', 'register')">立即注册</a>
      </p>
    </div>
  </div>
</template>

<style scoped>
.auth-page { display:flex; align-items:center; justify-content:center; min-height:70vh }
.auth-card { background:var(--paper); border-radius:12px; padding:32px; width:100%; max-width:380px; border:1px solid var(--border) }
.auth-card h2 { margin:0; font-size:20px }
.auth-header { display:flex; align-items:center; gap:12px; margin-bottom:20px }
.btn-back { background:none; border:none; color:var(--ink-muted); font-size:13px; cursor:pointer; padding:4px 8px; border-radius:6px; transition:all 120ms }
.btn-back:hover { color:var(--accent); background:var(--accent-bg) }
.auth-card label { display:block; font-size:13px; color:var(--ink-muted); margin-bottom:4px; margin-top:12px }
.auth-card input { width:100%; padding:10px 12px; background:var(--surface); border:1px solid var(--border); border-radius:6px; color:var(--ink); font-size:14px; outline:none; box-sizing:border-box }
.auth-card input:focus { border-color:var(--accent) }
.auth-card .btn { width:100%; margin-top:20px; padding:12px }
.auth-error { color:var(--red); font-size:13px; margin:12px 0 0 }
.auth-switch { margin-top:16px; text-align:center; font-size:13px; color:var(--ink-muted) }
.auth-switch a { color:var(--accent) }
</style>
