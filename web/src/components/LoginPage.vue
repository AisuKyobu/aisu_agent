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
      <h2>登录</h2>
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
.auth-card { background:var(--bg-card); border-radius:12px; padding:32px; width:100%; max-width:380px; border:1px solid rgba(255,255,255,.05) }
.auth-card h2 { margin:0 0 20px; font-size:20px }
.auth-card label { display:block; font-size:13px; color:var(--text-dim); margin-bottom:4px; margin-top:12px }
.auth-card input { width:100%; padding:10px 12px; background:rgba(255,255,255,.04); border:1px solid rgba(255,255,255,.08); border-radius:6px; color:var(--text-primary); font-size:14px; outline:none; box-sizing:border-box }
.auth-card input:focus { border-color:var(--pink) }
.auth-card .btn { width:100%; margin-top:20px; padding:12px }
.auth-error { color:#ff6b6b; font-size:13px; margin:12px 0 0 }
.auth-switch { margin-top:16px; text-align:center; font-size:13px; color:var(--text-dim) }
.auth-switch a { color:var(--pink) }
</style>
