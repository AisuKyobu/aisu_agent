<script setup lang="ts">
import { ref, onMounted } from 'vue'

const files = ref<string[]>([])
const activeFile = ref<string>('')
const content = ref<string>('')

async function loadFiles() {
  try {
    const r = await fetch('/api/workspace')
    const data = await r.json()
    files.value = data.files || []
  } catch {}
}

async function openFile(filename: string) {
  activeFile.value = filename
  try {
    const r = await fetch(`/api/workspace/${filename}`)
    const data = await r.json()
    content.value = data.content || ''
  } catch {}
}

const saved = ref(false)

async function saveFile() {
  if (!activeFile.value) return
  try {
    await fetch('/api/workspace', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename: activeFile.value, content: content.value }),
    })
    saved.value = true
    setTimeout(() => saved.value = false, 2000)
  } catch {}
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
        <span v-if="activeFile" style="font-size:12px;color:var(--text-dim);align-self:center">{{ activeFile }}</span>
      </div>
      <textarea v-model="content" placeholder="选择一个文件开始编辑..." spellcheck="false" />
    </div>
  </div>
</template>
