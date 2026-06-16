<script setup lang="ts">
import { ref, onMounted, inject, computed } from 'vue'
import { useAuth } from '../composables/useAuth'

const auth = useAuth()
const addToast = inject<(type: string, text: string) => void>('addToast', () => {})
const isAdmin = computed(() => auth.user.value?.role === 'admin')

function authHeaders(): Record<string, string> {
  const t = auth.token()
  return t ? { Authorization: `Bearer ${t}` } : {}
}

async function apiCall(url: string, options?: RequestInit): Promise<{ ok: boolean; data: any }> {
  try {
    const r = await fetch(url, options)
    const data = await r.json().catch(() => ({}))
    if (!r.ok) {
      throw new Error((data as any).detail || `请求失败 (${r.status})`)
    }
    return { ok: true, data }
  } catch (e: any) {
    addToast('warn', e.message)
    return { ok: false, data: null }
  }
}

interface Skill { name: string; description: string; enabled: boolean }

const skills = ref<Skill[]>([])
const installing = ref(false)
const installMsg = ref('')
const installOk = ref(true)

async function load() {
  const { data } = await apiCall('/api/skills')
  skills.value = data?.skills || []
}

async function toggleSkill(name: string, enabled: boolean) {
  const { ok } = await apiCall(`/api/skills/${name}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ enabled }),
  })
  if (ok) load()
}

async function installSkill(file: File) {
  if (!file.name.endsWith('.zip')) {
    installMsg.value = '仅支持 .zip 文件'
    installOk.value = false
    return
  }
  installing.value = true
  installMsg.value = ''
  try {
    const form = new FormData()
    form.append('file', file)
    const { ok, data } = await apiCall('/api/skills/install', { method: 'POST', headers: authHeaders(), body: form })
    if (ok) {
      installMsg.value = `已安装 ${(data?.installed_names || []).length} 个技能`
      installOk.value = true
      load()
    } else {
      installMsg.value = data?.error || '安装失败'
      installOk.value = false
    }
  } finally {
    installing.value = false
  }
}

function handleFileInput(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files?.length) {
    installSkill(input.files[0])
    input.value = ''
  }
}

onMounted(load)
</script>

<template>
  <div class="skills-grid">
    <div v-for="s in skills" :key="s.name" class="skill-card">
      <div class="skill-card-name">{{ s.name }}</div>
      <div class="skill-card-desc">{{ s.description }}</div>
      <div class="skill-card-toggle">
        <label class="toggle" :class="{ locked: !isAdmin }" :title="isAdmin ? '' : '需要管理员权限'">
          <input type="checkbox" :checked="s.enabled" :disabled="!isAdmin" @change="isAdmin && toggleSkill(s.name, !s.enabled)" />
          <span class="toggle-slider" />
        </label>
        <span>{{ s.enabled ? '已启用' : '已禁用' }}</span>
      </div>
    </div>

    <label class="skill-card install-card" :class="{ loading: installing, locked: !isAdmin }" :title="isAdmin ? '上传 .zip 技能包安装' : '需要管理员权限才能安装技能'">
      <input type="file" accept=".zip" @change="handleFileInput" :disabled="installing || !isAdmin" />
      <template v-if="!isAdmin">
        <div class="install-icon">🔒</div>
        <div class="install-label">需要管理员权限</div>
      </template>
      <template v-else-if="installing">
        <div class="install-icon spinning">⟳</div>
        <div class="install-label">安装中...</div>
        <div v-if="installMsg" class="install-sub" :class="{ error: !installOk }">{{ installMsg }}</div>
      </template>
      <template v-else-if="installMsg">
        <div class="install-icon">✓</div>
        <div class="install-label">{{ installMsg }}</div>
      </template>
      <template v-else>
        <div class="install-icon">+</div>
        <div class="install-label">安装新技能</div>
        <div class="install-sub">上传 .zip 技能包</div>
      </template>
    </label>
  </div>
</template>

<style scoped>
.toggle.locked { opacity: 0.45; cursor: not-allowed; }
.install-card.locked { opacity: 0.5; cursor: not-allowed; border-color: var(--border-light); }
.install-card.locked:hover { border-color: var(--border-light); color: var(--ink-muted); }
</style>
