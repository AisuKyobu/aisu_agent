<script setup lang="ts">
import { ref } from 'vue'
import { useAuth } from '../composables/useAuth'

const emit = defineEmits<{ switchPage: [page: string] }>()
const auth = useAuth()

const username = ref('')
const email = ref('')
const password = ref('')
const password2 = ref('')
const loading = ref(false)
const localError = ref('')

async function doRegister() {
  localError.value = ''
  if (password.value !== password2.value) { localError.value = '两次密码不一致'; return }
  if (password.value.length < 6) { localError.value = '密码至少 6 个字符'; return }
  if (username.value.length < 3) { localError.value = '用户名至少 3 个字符'; return }
  loading.value = true
  const ok = await auth.register(username.value, password.value, email.value)
  loading.value = false
  if (!ok) return
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-card">
      <h2>注册</h2>
      <form @submit.prevent="doRegister">
        <label>用户名</label>
        <input v-model="username" type="text" autocomplete="username" placeholder="不少于 3 个字符" />
        <label>邮箱（可选）</label>
        <input v-model="email" type="email" autocomplete="email" placeholder="用于验证和找回密码" />
        <label>密码</label>
        <input v-model="password" type="password" autocomplete="new-password" placeholder="至少 6 个字符" />
        <label>确认密码</label>
        <input v-model="password2" type="password" autocomplete="new-password" placeholder="再次输入密码" />
        <p v-if="localError" class="auth-error">{{ localError }}</p>
        <p v-if="auth.error.value" class="auth-error">{{ auth.error.value }}</p>
        <button type="submit" class="btn btn-primary" :disabled="loading">
          {{ loading ? '注册中...' : '注册' }}
        </button>
      </form>
      <p class="auth-switch">
        已有账号？<a href="#" @click.prevent="emit('switchPage', 'login')">返回登录</a>
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
