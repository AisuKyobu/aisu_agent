<script setup lang="ts">
import { ref, onMounted } from 'vue'

interface CronJob { id: string; interval: number; task: string; next_run?: number; session_id?: string }

const jobs = ref<CronJob[]>([])

async function load() {
  try {
    const r = await fetch('/api/cron')
    const data = await r.json()
    jobs.value = data.jobs || []
  } catch {}
}

async function removeJob(id: string) {
  try {
    await fetch('/api/cron/remove', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: id }),
    })
    load()
  } catch {}
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
        <button class="btn btn-sm" @click="removeJob(j.id)">删除</button>
      </div>
    </div>
  </div>
</template>
