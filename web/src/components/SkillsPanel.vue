<script setup lang="ts">
import { ref, onMounted } from 'vue'

interface Skill { name: string; description: string; enabled: boolean }

const skills = ref<Skill[]>([])
const installing = ref(false)
const installMsg = ref('')
const installOk = ref(true)

async function load() {
  try {
    const r = await fetch('/api/skills')
    const data = await r.json()
    skills.value = data.skills || []
  } catch {}
}

async function toggle(name: string, enabled: boolean) {
  try {
    await fetch(`/api/skills/${name}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled }),
    })
    load()
  } catch {}
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
    const r = await fetch('/api/skills/install', { method: 'POST', body: form })
    const data = await r.json()
    if (data.ok) {
      installMsg.value = `已安装 ${(data.names || []).length} 个技能`
      installOk.value = true
      load()
    } else {
      installMsg.value = data.error || '安装失败'
      installOk.value = false
    }
  } catch {
    installMsg.value = '网络错误，请重试'
    installOk.value = false
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
        <label class="toggle">
          <input type="checkbox" :checked="s.enabled" @change="toggle(s.name, !s.enabled)" />
          <span class="toggle-slider" />
        </label>
        <span>{{ s.enabled ? '已启用' : '已禁用' }}</span>
      </div>
    </div>

    <label class="skill-card install-card" :class="{ loading: installing }">
      <input type="file" accept=".zip" @change="handleFileInput" :disabled="installing" />
      <template v-if="installing">
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
