<script setup lang="ts">
import { reactive, ref, onMounted } from 'vue'

interface ProfileItem { id: string; label: string }

const profiles = ref<ProfileItem[]>([{ id: 'dev', label: '开发助手' }])
const activeProfile = ref('dev')

const fields = [
  { key: 'MAX_STEPS', label: '最大步数', desc: '单轮对话最多工具调用次数', def: 20 },
  { key: 'MAX_SEARCH_COUNT', label: '最大搜索次数', desc: '搜索任务最多搜索次数', def: 7 },
  { key: 'REASONING_MAX_STEPS', label: '推理最大步数', desc: '推理任务最大步数', def: 20 },
  { key: 'REASONING_MAX_TOOL_CALLS', label: '推理最大工具调用', desc: '推理任务工具调用上限', def: 15 },
  { key: 'REASONING_MAX_FILE_READS', label: '推理最大文件读取', desc: '推理任务文件读取上限', def: 20 },
  { key: 'REASONING_MAX_SEARCH', label: '推理最大搜索', desc: '推理任务搜索次数上限', def: 3 },
  { key: 'MAX_MESSAGES', label: '消息压缩阈值', desc: '超过此条数触发上下文压缩（旧逻辑，token预算模式下辅助判断）', def: 120 },
  { key: 'COMPRESSION_THRESHOLD', label: '压缩比例阈值', desc: 'token 占比超过此比例触发压缩', def: 0.75 },
  { key: 'CONTEXT_LENGTH', label: '上下文长度', desc: '模型的 context window 大小 (tokens)', def: 128000 },
  { key: 'KEEP_MESSAGES', label: '保留消息数', desc: '压缩后保留的最近消息数', def: 80 },
  { key: 'MAX_RETRIES', label: '最大重试次数', desc: 'LLM 调用失败重试次数', def: 3 },
  { key: 'RETRY_DELAY', label: '重试间隔 (秒)', desc: 'LLM 调用重试间隔', def: 2 },
  { key: 'TOOL_TIMEOUT', label: '工具超时 (秒)', desc: '单次工具执行超时时间', def: 30 },
]

const settings = reactive<Record<string, number>>(
  Object.fromEntries(fields.map(f => [f.key, f.def]))
)

const saved = ref(false)

async function loadProfiles() {
  try {
    const r = await fetch('/api/profiles')
    const data = await r.json()
    if (data.profiles) profiles.value = data.profiles
  } catch {}
}

async function load() {
  try {
    const r = await fetch(`/api/settings?profile=${activeProfile.value}`)
    const data = await r.json()
    if (data.settings) {
      for (const f of fields) {
        if (data.settings[f.key] !== undefined) {
          settings[f.key] = data.settings[f.key]
        }
      }
    }
  } catch {}
}

async function save() {
  try {
    const payload = Object.fromEntries(
      fields.map(f => [f.key, settings[f.key]])
    )
    const r = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ data: payload, profile: activeProfile.value }),
    })
    const data = await r.json()
    if (data.ok) {
      saved.value = true
      setTimeout(() => saved.value = false, 2000)
    }
  } catch {}
}

async function switchProfile(id: string) {
  activeProfile.value = id
  await load()
}

function resetAll() {
  if (!confirm('恢复所有设置为默认值？')) return
  for (const f of fields) {
    settings[f.key] = f.def
  }
  save()
}

onMounted(async () => { await loadProfiles(); await load() })
</script>

<template>
  <div class="settings-panel">
    <div class="settings-toolbar">
      <select v-model="activeProfile" @change="switchProfile(($event.target as HTMLSelectElement).value)" class="profile-select">
        <option v-for="p in profiles" :key="p.id" :value="p.id">{{ p.label }}</option>
      </select>
      <button class="btn btn-sm btn-primary" @click="save">{{ saved ? '已保存 ✓' : '保存设置' }}</button>
      <button class="btn btn-sm" @click="resetAll">恢复默认</button>
      <span style="font-size:11px;color:var(--text-dim);margin-left:auto">修改后即时生效，无需重启</span>
    </div>
    <div class="settings-grid">
      <div v-for="f in fields" :key="f.key" class="settings-field">
        <label>{{ f.label }}</label>
        <input type="number" v-model.number="settings[f.key]" :step="f.key === 'COMPRESSION_THRESHOLD' ? 0.05 : 1" />
        <span class="field-desc">{{ f.desc }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.settings-panel { padding: 12px; height: 100%; display: flex; flex-direction: column; }
.settings-toolbar { display: flex; gap: 8px; margin-bottom: 16px; align-items: center; }
.settings-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; overflow-y: auto; }
.settings-field { display: flex; flex-direction: column; gap: 4px; }
.settings-field label { font-size: 13px; color: var(--ink); font-weight: 500; }
.settings-field input {
  background: var(--surface-hover); color: var(--ink);
  border: 1px solid var(--border); border-radius: 4px; padding: 6px 8px; font-size: 13px;
  width: 100%; box-sizing: border-box;
}
.settings-field input:focus { border-color: var(--accent); outline: none; }
.field-desc { font-size: 11px; color: var(--text-dim); }
</style>
