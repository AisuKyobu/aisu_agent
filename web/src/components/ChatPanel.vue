<script setup lang="ts">
import { ref, nextTick, watch, onMounted } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import type { useWebSocket } from '../composables/useWebSocket'
import { useAuth } from '../composables/useAuth'

// 配置 marked: 不处理换行转 br (由 CSS white-space 处理)，代码块高亮
marked.setOptions({ breaks: false, gfm: true })

const props = defineProps<{ ws: ReturnType<typeof useWebSocket> }>()
const auth = useAuth()

interface Session { id: string; title: string; created_at?: number }
interface Message { role: string; content: string; time?: string }

const sessions = ref<Session[]>([])
const activeSid = ref<string>('')
const msgs = ref<Message[]>([])
const input = ref('')
const streaming = ref(false)
const streamingBuf = ref('')
const msgContainer = ref<HTMLElement | null>()
const renamingId = ref<string>('')
const renameText = ref('')

function now() { return new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }
function authHeaders(): Record<string, string> {
  const t = auth.token()
  return t ? { 'Content-Type': 'application/json', Authorization: `Bearer ${t}` } : { 'Content-Type': 'application/json' }
}

function renderContent(text: string): string {
  if (!text) return ''
  const html = marked.parse(text) as string
  return DOMPurify.sanitize(html)
}

async function loadSessions() {
  try {
    const r = await fetch('/api/sessions', { headers: authHeaders() })
    const data = await r.json()
    sessions.value = (data.sessions || []).sort((a: any, b: any) => (b.updated_at || 0) - (a.updated_at || 0))
  } catch {}
}

async function loadHistory(sid: string) {
  try {
    const r = await fetch(`/api/sessions/${sid}/history`)
    const data = await r.json()
    if (data.ok && data.messages) {
      msgs.value = data.messages.map((m: any) => ({ role: m.role, content: m.content || '', time: '' }))
    }
  } catch {}
}

function selectSession(sid: string) {
  activeSid.value = sid
  msgs.value = []
  loadHistory(sid)
}

async function newSession() {
  try {
    const r = await fetch('/api/sessions', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ title: '新对话' }),
    })
    const data = await r.json()
    if (data.session) {
      sessions.value.unshift(data.session)
      selectSession(data.session.id)
    }
  } catch {}
}

async function deleteSession(sid: string) {
  try {
    await fetch(`/api/sessions/${sid}`, { method: 'DELETE', headers: authHeaders() })
    sessions.value = sessions.value.filter(s => s.id !== sid)
    if (activeSid.value === sid) { activeSid.value = ''; msgs.value = [] }
  } catch {}
}

function startRename(s: Session) {
  renamingId.value = s.id
  renameText.value = s.title || s.id.slice(0, 12)
  nextTick(() => {
    const el = document.querySelector<HTMLInputElement>('.rename-input')
    el?.focus(); el?.select()
  })
}

async function commitRename(sid: string) {
  const title = renameText.value.trim()
  if (title) {
    try {
      await fetch(`/api/sessions/${sid}`, {
        method: 'PATCH',
        headers: authHeaders(),
        body: JSON.stringify({ title }),
      })
      const s = sessions.value.find(x => x.id === sid)
      if (s) s.title = title
    } catch {}
  }
  renamingId.value = ''
}

function sendChat() {
  const text = input.value.trim()
  if (!text || streaming.value) return
  if (!activeSid.value) { newSession(); return }
  msgs.value.push({ role: 'human', content: text, time: now() })
  streaming.value = true
  streamingBuf.value = ''
  props.ws.send({ type: 'message', content: text, session_id: activeSid.value, source: 'web' })
  input.value = ''
}

function scrollBottom() {
  nextTick(() => { const el = msgContainer.value; if (el) el.scrollTop = el.scrollHeight })
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); sendChat() }
}

// ── WS handlers ──
props.ws.on('token', (msg: any) => {
  streamingBuf.value += msg.content || ''
  const last = msgs.value[msgs.value.length - 1]
  if (last && last.role === 'ai' && streaming.value) {
    last.content = streamingBuf.value
  } else {
    msgs.value.push({ role: 'ai', content: streamingBuf.value, time: now() })
  }
})

props.ws.on('tool_call', (msg: any) => {
  streamingBuf.value = ''  // 切断流式积累，下一轮 LLM 调用从零开始
  const names = (msg.tools || []).join(', ')
  msgs.value.push({ role: 'system', content: `⚙ ${names} ${(msg.args || '').slice(0, 120)}` })
  scrollBottom()
})

props.ws.on('tool_result', () => {
  streamingBuf.value = ''  // 同上，工具结果后也是新一轮 LLM
})

props.ws.on('node_enter', () => {
  streamingBuf.value = ''  // 节点切换也切断，防止跨节点 token 粘连
})

props.ws.on('done', () => {
  streaming.value = false; streamingBuf.value = ''
  loadSessions()
  setTimeout(() => loadHistory(activeSid.value), 600)
})

props.ws.on('cron_result', (msg: any) => {
  const sid = msg.session_id || ''
  if (sid && sid !== activeSid.value) return
  const status = msg.status === 'completed' ? '✓' : '✗'
  msgs.value.push({ role: 'system', content: `${status} 定时任务: ${msg.task || ''} ${msg.error ? '— ' + msg.error : ''}` })
  loadSessions()
  setTimeout(() => loadHistory(activeSid.value), 600)
})

props.ws.on('error', (msg: any) => {
  msgs.value.push({ role: 'system', content: `⚠ ${msg.content || 'Error'}` })
  streaming.value = false
})

watch(msgs, scrollBottom, { deep: true })
watch(() => auth.user.value, (u) => {
  if (!u) {
    activeSid.value = ''
    msgs.value = []
    loadSessions()
  }
})
onMounted(() => {
  const check = () => {
    if (auth.loading.value) { setTimeout(check, 50); return }
    loadSessions()
  }
  check()
})
</script>

<template>
  <div class="chat-layout">
    <!-- Sidebar -->
    <aside class="sidebar">
      <div class="sidebar-header">
        <button class="btn-new" @click="newSession">＋ 新对话</button>
      </div>
      <nav class="sidebar-list">
        <div v-if="!sessions.length" class="sidebar-empty">暂无会话</div>
        <div
          v-for="s in sessions" :key="s.id"
          class="session-row"
          :class="{ active: s.id === activeSid }"
          @click="selectSession(s.id)"
          @dblclick="startRename(s)"
        >
          <template v-if="renamingId === s.id">
            <input
              class="rename-input"
              v-model="renameText"
              @keydown.enter="commitRename(s.id)"
              @blur="commitRename(s.id)"
              @click.stop
            />
          </template>
          <template v-else>
            <span class="session-title">{{ s.title || s.id.slice(0, 12) }}</span>
            <button class="session-del" @click.stop="deleteSession(s.id)" title="删除">×</button>
          </template>
        </div>
      </nav>
    </aside>

    <!-- Chat area -->
    <main class="chat-main">
      <div class="chat-msgs" ref="msgContainer">
        <div v-if="!msgs.length && !activeSid" class="chat-empty">
          <div class="empty-icon">⊳</div>
          <div class="empty-text">选择会话或创建新对话</div>
        </div>
        <template v-for="(m, i) in msgs" :key="i">
          <div class="msg-row" :class="m.role === 'human' ? 'is-user' : m.role === 'ai' ? 'is-ai' : 'is-sys'">
            <template v-if="m.role === 'human'">
              <div class="msg-bubble user-bubble">{{ m.content }}</div>
            </template>
            <template v-else-if="m.role === 'ai'">
              <div class="ai-avatar">AI</div>
              <div class="msg-bubble ai-bubble" v-html="renderContent(m.content)" />
            </template>
            <template v-else>
              <div class="sys-msg">{{ m.content }}</div>
            </template>
          </div>
        </template>
        <div v-if="streaming" class="typing-dots"><span /><span /><span /></div>
      </div>

      <div class="chat-foot">
        <textarea
          v-model="input"
          placeholder="输入消息... Enter 发送 / Shift+Enter 换行"
          rows="1"
          @keydown="onKeydown"
          :disabled="streaming"
        />
        <button class="btn-send" @click="sendChat" :disabled="streaming || !input.trim()">↑</button>
      </div>
    </main>
  </div>
</template>
