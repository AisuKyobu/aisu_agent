<script setup lang="ts">
import { ref, onMounted, watch, provide, computed } from 'vue'
import ChatPanel from './components/ChatPanel.vue'
import MonitorPanel from './components/MonitorPanel.vue'
import SkillsPanel from './components/SkillsPanel.vue'
import WorkspacePanel from './components/WorkspacePanel.vue'
import CronPanel from './components/CronPanel.vue'
import SettingsPanel from './components/SettingsPanel.vue'
import ToastNotification from './components/ToastNotification.vue'
import LoginPage from './components/LoginPage.vue'
import RegisterPage from './components/RegisterPage.vue'
import LogoIcon from './components/LogoIcon.vue'
import { useWebSocket } from './composables/useWebSocket'
import { useAuth } from './composables/useAuth'

interface Tab { id: string; label: string; authOnly?: boolean; adminOnly?: boolean }

const tabs: Tab[] = [
  { id: 'chat', label: '聊天' },
  { id: 'monitor', label: '监控' },
  { id: 'skills', label: '技能', authOnly: true },
  { id: 'workspace', label: '指令', authOnly: true },
  { id: 'cron', label: '定时', authOnly: true },
  { id: 'settings', label: '设置', adminOnly: true },
]

const tabIcon: Record<string, string> = {
  chat: 'M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7A8.38 8.38 0 0 1 4 11.5a8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z',
  monitor: 'M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9 M13.73 21a2 2 0 0 1-3.46 0',
  skills: 'M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z',
  workspace: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z M14 2v6h6 M16 13H8 M16 17H8 M10 9H8',
  cron: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z M12 6v6l4 2',
  settings: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1.51 1H15a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z',
}

const activeTab = ref<string>('chat')
const toasts = ref<{ id: number; type: string; text: string }[]>([])
let _toastId = 0

const ws = useWebSocket()
const auth = useAuth()
const authPage = ref<string>('')

const demoMode = ref(false)
const demoRemaining = ref(5)
const demoMax = ref(5)

onMounted(async () => {
  auth.fetchMe()
  try {
    const r = await fetch('/api/demo/status')
    const data = await r.json()
    demoMode.value = data.demo || false
    demoRemaining.value = data.remaining || 0
    demoMax.value = data.max || 5
  } catch {}
})

watch(() => auth.user.value, (u) => {
  if (u) authPage.value = ''
  else {
    const current = tabs.find(t => t.id === activeTab.value)
    if (current && (current.adminOnly || current.authOnly)) activeTab.value = 'chat'
  }
})

function addToast(type: string, text: string) {
  const id = ++_toastId
  toasts.value.push({ id, type, text })
  setTimeout(() => {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }, 4000)
}
provide('addToast', addToast)

ws.on('limit_hit', (msg) => {
  addToast('warn', `限制命中: ${msg.reason || '步数/搜索已达上限'}`)
})

ws.on('demo_remaining', (msg) => {
  demoRemaining.value = msg.remaining ?? 0
})

const visibleTabs = computed(() => tabs.filter(t =>
  (!t.authOnly && !t.adminOnly) ||
  (t.authOnly && auth.user.value) ||
  (t.adminOnly && auth.user.value?.role === 'admin')
))

const demoExhausted = computed(() => demoMode.value && demoRemaining.value <= 0)
</script>

<template>
  <div class="app-header">
    <div style="display:flex;align-items:center;gap:10px">
      <span class="app-logo"><LogoIcon :size="18" />Aisu</span>
      <a href="https://github.com/AisuKyobu/aisu_agent" target="_blank" rel="noopener" class="gh-badge" title="GitHub">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23a11.49 11.49 0 0 1 3-.405c1.02 0 2.04.135 3 .405 2.28-1.56 3.285-1.23 3.285-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/></svg>
        GitHub
      </a>
    </div>

    <div style="display:flex;align-items:center;gap:12px">
      <div v-if="demoMode" class="demo-chip" :class="{ exhausted: demoExhausted }" title="演示模式限制">
        演示 · {{ demoExhausted ? '已用完' : `${demoRemaining}/${demoMax}` }}
      </div>

      <span style="display:inline-flex;align-items:center;gap:5px;font-size:12px;color:var(--ink-muted)">
        <span class="header-dot" :class="{ offline: !ws.connected }" />
        {{ ws.connected ? '已连接' : '连接中' }}
      </span>

      <template v-if="auth.user.value">
        <span style="font-size:12px;color:var(--ink)">{{ auth.user.value.username }}</span>
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
        v-for="t in visibleTabs" :key="t.id"
        class="tab-btn"
        :class="{ active: activeTab === t.id }"
        @click="activeTab = t.id"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path :d="tabIcon[t.id]" /></svg>
        {{ t.label }}
      </button>
    </div>

    <div class="app-main">
      <ChatPanel v-if="activeTab === 'chat'" :ws="ws" :demo-mode="demoMode" :demo-remaining="demoRemaining" :demo-max="demoMax" />
      <MonitorPanel v-else-if="activeTab === 'monitor'" :ws="ws" />
      <SkillsPanel v-else-if="activeTab === 'skills'" />
      <WorkspacePanel v-else-if="activeTab === 'workspace'" />
      <CronPanel v-else-if="activeTab === 'cron'" />
      <SettingsPanel v-else-if="activeTab === 'settings'" />
    </div>
  </template>

  <footer class="app-footer">
    <a href="https://beian.miit.gov.cn/" target="_blank" rel="noopener">备案中</a>
  </footer>

  <ToastNotification :toasts="toasts" @remove="(id: number) => toasts = toasts.filter(t => t.id !== id)" />
</template>
