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

interface CronJob { id: string; interval: number; task: string; next_run?: number; session_id?: string }

const jobs = ref<CronJob[]>([])

async function load() {
  const { data } = await apiCall('/api/cron')
  jobs.value = data?.jobs || []
}

async function removeJob(id: string) {
  const { ok } = await apiCall('/api/cron/remove', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ job_id: id }),
  })
  if (ok) load()
}

function formatInterval(sec: number): string {
  if (sec >= 86400) return `${Math.floor(sec / 86400)} 天`
  if (sec >= 3600) return `${Math.floor(sec / 3600)} 小时`
  if (sec >= 60) return `${Math.floor(sec / 60)} 分钟`
  return `${sec} 秒`
}

function formatNext(ts?: number): string {
  if (!ts) return '-'
  return new Date(ts * 1000).toLocaleString()
}

onMounted(load)
</script>

<template>
  <div class="cron-layout">
    <div v-if="!jobs.length" class="chat-empty">暂无定时任务</div>
    <div v-else class="cron-list">
      <div v-for="j in jobs" :key="j.id" class="cron-item">
        <div class="cron-item-info">
          <div class="cron-item-task">{{ j.task }}</div>
          <div class="cron-item-meta">间隔: {{ formatInterval(j.interval) }} · 下次: {{ formatNext(j.next_run) }} · {{ j.session_id || '' }}</div>
        </div>
        <button v-if="isAdmin" class="btn btn-sm" @click="removeJob(j.id)">删除</button>
        <span v-else class="cron-admin-hint">仅管理员可操作</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cron-admin-hint { font-size: 11px; color: var(--ink-muted); padding: 4px 8px; }
</style>
