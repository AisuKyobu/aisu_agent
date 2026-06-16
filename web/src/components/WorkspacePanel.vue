<script setup lang="ts">
import { ref, onMounted, inject } from 'vue'
import { useAuth } from '../composables/useAuth'

const auth = useAuth()
const addToast = inject<(type: string, text: string) => void>('addToast', () => {})

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

function authHeaders(): Record<string, string> {
  const t = auth.token()
  return t ? { Authorization: `Bearer ${t}` } : {}
}

const files = ref<string[]>([])
const activeFile = ref<string>('')
const content = ref<string>('')

async function loadFiles() {
  const { data } = await apiCall('/api/workspace', { headers: authHeaders() })
  files.value = data?.files || []
}

async function openFile(filename: string) {
  activeFile.value = filename
  const { data } = await apiCall(`/api/workspace/${filename}`, { headers: authHeaders() })
  content.value = data?.content || ''
}

const saved = ref(false)

async function saveFile() {
  if (!activeFile.value) return
  const { ok } = await apiCall('/api/workspace', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ filename: activeFile.value, content: content.value }),
  })
  if (ok) {
    saved.value = true
    setTimeout(() => saved.value = false, 2000)
  }
}

onMounted(loadFiles)
</script>

<template>
  <div class="workspace-layout">
    <div class="workspace-files">
      <div v-for="f in files" :key="f" class="workspace-file" :class="{ active: f === activeFile }" @click="openFile(f)">
        {{ f }}
      </div>
    </div>
    <div class="workspace-editor">
      <div class="workspace-toolbar">
        <button class="btn btn-sm" @click="saveFile">{{ saved ? '已保存 ✓' : '保存' }}</button>
        <span v-if="activeFile" style="font-size:12px;color:var(--ink-muted);align-self:center">{{ activeFile }}</span>
      </div>
      <textarea v-model="content" placeholder="选择一个文件开始编辑..." spellcheck="false" />
    </div>
  </div>
</template>
