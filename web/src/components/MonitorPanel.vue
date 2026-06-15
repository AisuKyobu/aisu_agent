<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import type { useWebSocket } from '../composables/useWebSocket'
import { useAuth } from '../composables/useAuth'

const props = defineProps<{ ws: ReturnType<typeof useWebSocket> }>()
const auth = useAuth()

function authHeaders(): Record<string, string> {
  const t = auth.token()
  return t ? { Authorization: `Bearer ${t}` } : {}
}

interface SessionState {
  id: string
  title?: string
  source?: string
  source_icon?: string
  status?: string
  execution_mode?: string
  task_type?: string
  current_step?: number
  max_steps?: number
  tools_used?: string[]
  updated_at?: number
  summary?: string
  last_state?: any
  active?: boolean
  sub?: boolean
}

const sessions = ref<SessionState[]>([])
const selected = ref<SessionState | null>(null)
let _timer: ReturnType<typeof setInterval> | null = null

async function fetchSessions() {
  try {
    const r = await fetch('/api/monitor/sessions', { headers: authHeaders() })
    const data = await r.json()
    sessions.value = data.sessions || []
  } catch {}
}

function selectSession(s: SessionState) {
  selected.value = selected.value?.id === s.id ? null : s
}

function formatTime(ts: number): string {
  if (!ts) return '-'
  const d = new Date(ts * 1000)
  return `${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}`
}

function statusClass(status?: string): string {
  const m: Record<string, string> = { thinking: 'status-thinking', running: 'status-thinking', idle: 'status-idle', error: 'status-error' }
  return m[status || ''] || 'status-idle'
}

function sourceIcon(src?: string): string {
  const m: Record<string, string> = { web: '🖥', qq: '💬', cron: '⏰', sub: '📦' }
  return m[src || ''] || '💬'
}

props.ws.on('monitor_global', (msg: any) => {
  if (msg.sessions) sessions.value = msg.sessions
})

onMounted(() => {
  fetchSessions()
  _timer = setInterval(fetchSessions, 5000)
})
onUnmounted(() => { if (_timer) clearInterval(_timer) })
</script>

<template>
  <div class="monitor-layout">
    <div class="monitor-table-wrap">
      <table class="monitor-table">
        <thead>
          <tr>
            <th style="width:180px">会话</th>
            <th style="width:50px;text-align:center">来源</th>
            <th style="width:80px">状态</th>
            <th style="width:70px">模式</th>
            <th style="width:80px">任务</th>
            <th style="width:55px">步数</th>
            <th>工具</th>
            <th style="width:70px">活跃</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="s in sessions" :key="s.id"
            :class="{ selected: selected?.id === s.id, 'sub-row': s.sub }"
            @click="selectSession(s)"
          >
            <td :title="s.id">{{ s.sub ? '└─ ' : '' }}{{ s.id.slice(0,16) }}</td>
            <td style="text-align:center">{{ sourceIcon(s.source) }}</td>
            <td><span class="status-dot" :class="statusClass(s.status)" />{{ s.status || 'idle' }}</td>
            <td>{{ s.last_state?.execution_mode || '-' }}</td>
            <td>{{ s.last_state?.task_type || '-' }}</td>
            <td>{{ (s.last_state?.current_step ?? '-') }}/{{ (s.last_state?.max_steps ?? '-') }}</td>
            <td style="font-size:11px">{{ (s.last_state?.tools_used || []).slice(0, 3).join(', ') || '-' }}</td>
            <td style="font-size:11px">{{ formatTime(s.updated_at || 0) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="selected" class="detail-panel">
      <div class="card-title" style="margin-bottom:10px">会话详情: {{ selected.id }}</div>
      <div class="detail-grid">
        <div><div class="detail-label">ID</div><div class="detail-value">{{ selected.id }}</div></div>
        <div><div class="detail-label">来源</div><div class="detail-value">{{ selected.source || '-' }}</div></div>
        <div><div class="detail-label">状态</div><div class="detail-value">{{ selected.status || '-' }}</div></div>
        <div><div class="detail-label">模式</div><div class="detail-value">{{ selected.last_state?.execution_mode || '-' }}</div></div>
        <div><div class="detail-label">任务类型</div><div class="detail-value">{{ selected.last_state?.task_type || '-' }}</div></div>
        <div><div class="detail-label">步数</div><div class="detail-value">{{ selected.last_state?.current_step ?? '-' }} / {{ selected.last_state?.max_steps ?? '-' }}</div></div>
        <div><div class="detail-label">工具</div><div class="detail-value">{{ (selected.last_state?.tools_used || []).join(', ') || '-' }}</div></div>
        <div><div class="detail-label">摘要</div><div class="detail-value">{{ (selected.summary || '').slice(0, 200) || '-' }}</div></div>
      </div>
    </div>
  </div>
</template>
