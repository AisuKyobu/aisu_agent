<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import ChatPanel from './components/ChatPanel.vue'
import MonitorPanel from './components/MonitorPanel.vue'
import SkillsPanel from './components/SkillsPanel.vue'
import WorkspacePanel from './components/WorkspacePanel.vue'
import CronPanel from './components/CronPanel.vue'
import SettingsPanel from './components/SettingsPanel.vue'
import ToastNotification from './components/ToastNotification.vue'
import LoginPage from './components/LoginPage.vue'
import RegisterPage from './components/RegisterPage.vue'
import { useWebSocket } from './composables/useWebSocket'
import { useAuth } from './composables/useAuth'

const tabs = [
  { id: 'chat', label: '聊天' },
  { id: 'monitor', label: '监控', authOnly: true },
  { id: 'skills', label: '技能' },
  { id: 'workspace', label: '指令', authOnly: true },
  { id: 'cron', label: '定时' },
  { id: 'settings', label: '设置', adminOnly: true },
] as const

const activeTab = ref<string>('chat')
const toasts = ref<{ id: number; type: string; text: string }[]>([])
let _toastId = 0

const ws = useWebSocket()
const auth = useAuth()
const authPage = ref<string>('')

onMounted(() => auth.fetchMe())

watch(() => auth.user.value, (u) => {
  if (u) authPage.value = ''
  else {
    const current = tabs.find(t => t.id === activeTab.value)
    if (current && ((current as any).adminOnly || (current as any).authOnly)) activeTab.value = 'chat'
  }
})

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
    <div style="display:flex;align-items:center;gap:12px">
      <span style="font-size:11px;color:var(--text-dim)">
        {{ ws.connected ? '● 已连接' : '○ 连接中...' }}
      </span>
      <template v-if="auth.user.value">
        <span style="font-size:12px;color:var(--pink)">{{ auth.user.value.username }}</span>
        <button class="btn-auth" @click="auth.logout()">登出</button>
      </template>
      <template v-else>
        <button class="btn-auth" @click="authPage = 'login'">登录</button>
      </template>
    </div>
  </div>

  <template v-if="authPage === 'login'">
    <LoginPage @switch-page="(p: string) => authPage = p" />
  </template>
  <template v-else-if="authPage === 'register'">
    <RegisterPage @switch-page="(p: string) => authPage = p" />
  </template>
  <template v-else>
    <div class="tab-bar">
      <button
        v-for="t in tabs.filter(x => (!(x as any).authOnly && !(x as any).adminOnly) || ((x as any).authOnly && auth.user.value) || ((x as any).adminOnly && auth.user.value?.role === 'admin'))" :key="t.id"
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
  </template>

  <ToastNotification :toasts="toasts" @remove="(id: number) => toasts = toasts.filter(t => t.id !== id)" />
</template>
