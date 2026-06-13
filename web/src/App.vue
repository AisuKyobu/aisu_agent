<script setup lang="ts">
import { ref } from 'vue'
import ChatPanel from './components/ChatPanel.vue'
import MonitorPanel from './components/MonitorPanel.vue'
import SkillsPanel from './components/SkillsPanel.vue'
import WorkspacePanel from './components/WorkspacePanel.vue'
import CronPanel from './components/CronPanel.vue'
import SettingsPanel from './components/SettingsPanel.vue'
import ToastNotification from './components/ToastNotification.vue'
import { useWebSocket } from './composables/useWebSocket'

const tabs = [
  { id: 'chat', label: '聊天' },
  { id: 'monitor', label: '监控' },
  { id: 'skills', label: '技能' },
  { id: 'workspace', label: '指令' },
  { id: 'cron', label: '定时' },
  { id: 'settings', label: '设置' },
] as const

const activeTab = ref<string>('chat')
const toasts = ref<{ id: number; type: string; text: string }[]>([])
let _toastId = 0

const ws = useWebSocket()

function addToast(type: string, text: string) {
  const id = ++_toastId
  toasts.value.push({ id, type, text })
  setTimeout(() => {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }, 4000)
}

ws.on('limit_hit', (msg) => {
  addToast('warn', `限制命中: ${msg.reason || '步数/搜索已达上限'}`)
})
</script>

<template>
  <div class="app-header">
    <span class="app-logo">&gt;_ Aisu</span>
    <span style="font-size:11px;color:var(--text-dim)">
      {{ ws.connected ? '● 已连接' : '○ 连接中...' }}
    </span>
  </div>

  <div class="tab-bar">
    <button
      v-for="t in tabs" :key="t.id"
      class="tab-btn"
      :class="{ active: activeTab === t.id }"
      @click="activeTab = t.id"
    >{{ t.label }}</button>
  </div>

  <div class="app-main">
    <ChatPanel v-if="activeTab === 'chat'" :ws="ws" />
    <MonitorPanel v-else-if="activeTab === 'monitor'" :ws="ws" />
    <SkillsPanel v-else-if="activeTab === 'skills'" />
    <WorkspacePanel v-else-if="activeTab === 'workspace'" />
    <CronPanel v-else-if="activeTab === 'cron'" />
    <SettingsPanel v-else-if="activeTab === 'settings'" />
  </div>

  <ToastNotification :toasts="toasts" @remove="(id) => toasts = toasts.filter(t => t.id !== id)" />
</template>
