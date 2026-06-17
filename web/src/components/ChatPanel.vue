<script setup lang="ts">
import { ref, nextTick, watch, onMounted, onUnmounted, onUpdated, inject } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import type { useWebSocket } from '../composables/useWebSocket'
import { useAuth } from '../composables/useAuth'
import WelcomeCard from './WelcomeCard.vue'
import ToolCard from './ToolCard.vue'

// 配置 marked: 不处理换行转 br (由 CSS white-space 处理)，代码块高亮
marked.setOptions({ breaks: false, gfm: true })

const props = defineProps<{ ws: ReturnType<typeof useWebSocket>; demoMode?: boolean; demoRemaining?: number; demoMax?: number }>()
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

interface FileAttachment { filename: string; path: string; url: string; mime_type: string; is_image: boolean; tool_name: string }
interface Session { id: string; title: string; created_at?: number }
interface Message { role: string; content?: string; time?: string; file?: FileAttachment }

const sessions = ref<Session[]>([])
const activeSid = ref<string>('')
const msgs = ref<Message[]>([])
const input = ref('')
const streaming = ref(false)
const streamingBuf = ref('')
const msgContainer = ref<HTMLElement | null>()
const renamingId = ref<string>('')
const renameText = ref('')
const demoBlocked = ref(false)

function now() { return new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }
function authHeaders(): Record<string, string> {
  const t = auth.token()
  return t ? { 'Content-Type': 'application/json', Authorization: `Bearer ${t}` } : { 'Content-Type': 'application/json' }
}

function renderContent(text: string): string {
  if (!text) return ''
  // 将项目文件路径渲染为下载链接
  // 支持 workspace/ skills/ tests/ agent/ server/ tools/ web/ 等目录下的文件
  // 要求必须有常见文件扩展名，避免把普通单词/目录误识别为路径
  // 排除反引号、<> 以及常见中文标点，避免在代码片段中生成未渲染的 <a>
  const PATH_RE = /(?<![\w\/\`])(?:workspace|skills|tests|agent|server|tools|web)\/[^\s\n\r,，。；;<>「」【】`]+\.(?:py|md|txt|json|yaml|yml|js|ts|css|vue|html|sh|ps1|bat|pdf|csv|toml|cfg|ini|sql|xml|svg|png|jpg|jpeg|gif|env|example|lock)(?![\w\/\`])/gi
  text = text.replace(PATH_RE, (m) => {
    const safe = m.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    return `<a href="/api/files/${encodeURI(m)}" target="_blank" class="file-link">${safe}</a>`
  })
  const html = marked.parse(text) as string
  return DOMPurify.sanitize(html)
}

async function loadSessions() {
  const { data } = await apiCall('/api/sessions', { headers: authHeaders() })
  sessions.value = (data?.sessions || []).sort((a: any, b: any) => (b.updated_at || 0) - (a.updated_at || 0))
}

const _savedAttachments: Message[] = []

async function loadHistory(sid: string) {
  const { ok, data } = await apiCall(`/api/sessions/${sid}/history`, { headers: authHeaders() })
  if (ok && data.messages) {
    msgs.value = data.messages.map((m: any) => ({ role: m.role, content: m.content || '', time: '' }))
  } else if (!ok) {
    msgs.value = [{ role: 'system', content: '⚠ 无法加载历史' }]
  }
  for (const a of _savedAttachments) {
    msgs.value.push(a)
  }
}

function selectSession(sid: string) {
  activeSid.value = sid
  msgs.value = []
  _savedAttachments.length = 0
  loadHistory(sid)
}

async function newSession() {
  const { ok, data } = await apiCall('/api/sessions', {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ title: '新对话' }),
  })
  if (ok && data?.session) {
    sessions.value.unshift(data.session)
    selectSession(data.session.id)
  }
}

async function deleteSession(sid: string) {
  const { ok } = await apiCall(`/api/sessions/${sid}`, { method: 'DELETE', headers: authHeaders() })
  if (ok) {
    sessions.value = sessions.value.filter(s => s.id !== sid)
    if (activeSid.value === sid) { activeSid.value = ''; msgs.value = [] }
  }
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
    const { ok } = await apiCall(`/api/sessions/${sid}`, {
      method: 'PATCH',
      headers: authHeaders(),
      body: JSON.stringify({ title }),
    })
    if (ok) {
      const s = sessions.value.find(x => x.id === sid)
      if (s) s.title = title
    }
  }
  renamingId.value = ''
}

function sendChat() {
  const text = input.value.trim()
  if (!text || streaming.value) return
  if (!activeSid.value) { newSession(); return }
  msgs.value.push({ role: 'human', content: text, time: now() })
  _savedAttachments.length = 0  // 新对话轮次清空旧附件
  streaming.value = true
  streamingBuf.value = ''
  props.ws.send({ type: 'message', content: text, session_id: activeSid.value, source: 'web' })
  input.value = ''
}

async function startWithPrompt(prompt: string) {
  if (streaming.value || demoBlocked.value) return
  if (!activeSid.value) await newSession()
  if (!activeSid.value) return
  input.value = prompt
  sendChat()
}

function scrollBottom() {
  nextTick(() => { const el = msgContainer.value; if (el) el.scrollTop = el.scrollHeight })
}

function attachCopyButtons() {
  nextTick(() => {
    const container = msgContainer.value
    if (!container) return
    container.querySelectorAll('.ai-bubble pre').forEach(pre => {
      if (pre.parentElement?.classList.contains('pre-wrap')) return
      const wrapper = document.createElement('div')
      wrapper.className = 'pre-wrap'
      pre.parentNode?.insertBefore(wrapper, pre)
      wrapper.appendChild(pre)
      const btn = document.createElement('button')
      btn.className = 'btn-copy'
      btn.textContent = '复制'
      btn.type = 'button'
      wrapper.appendChild(btn)
    })
  })
}

function onChatClick(e: MouseEvent) {
  const btn = (e.target as HTMLElement).closest('.btn-copy')
  if (!btn) return
  const pre = btn.parentElement?.querySelector('pre')
  if (!pre) return
  navigator.clipboard.writeText(pre.textContent || '').then(() => {
    const original = btn.textContent
    btn.textContent = '已复制'
    setTimeout(() => { btn.textContent = original }, 1500)
  }).catch(() => {})
}

function openUrl(url: string) {

  window.open(url, '_blank')
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
  msgs.value.push({ role: 'system', content: `⚠ ${msg.content || '发生未知错误'}` })
  streaming.value = false
  streamingBuf.value = ''
})

props.ws.on('system_error', (msg: any) => {
  msgs.value.push({ role: 'system', content: `⚠ ${msg.content || '系统错误'}` })
  streaming.value = false
  streamingBuf.value = ''
})

props.ws.on('demo_limit', (msg: any) => {
  msgs.value.push({ role: 'system', content: msg.message || '演示模式次数已用完' })
  streaming.value = false
  streamingBuf.value = ''
  demoBlocked.value = true
})

const fileHandler = (msg: any) => {
  const entry: Message = {
    role: 'attachment',
    time: now(),
    file: {
      filename: msg.filename || '',
      path: msg.path || '',
      url: msg.url || '',
      mime_type: msg.mime_type || '',
      is_image: msg.is_image || false,
      tool_name: msg.tool_name || '',
    },
  }
  _savedAttachments.push(entry)
  // 最多保留 20 个，防止内存无限增长
  if (_savedAttachments.length > 20) _savedAttachments.shift()
  msgs.value.push(entry)
}
props.ws.on('file_attachment', fileHandler)
onUnmounted(() => {
  props.ws.off('file_attachment', fileHandler)
})

watch(msgs, () => { scrollBottom(); attachCopyButtons() }, { deep: true })
onUpdated(attachCopyButtons)
watch(() => auth.user.value, (u) => {
  if (!u) {
    activeSid.value = ''
    msgs.value = []
    _savedAttachments.length = 0
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
      <div class="chat-msgs" ref="msgContainer" @click="onChatClick">
        <WelcomeCard
          v-if="!msgs.length && !activeSid"
          :demo-mode="props.demoMode"
          :demo-remaining="props.demoRemaining"
          :demo-max="props.demoMax"
          @start="newSession"
          @send="startWithPrompt"
        />
        <template v-for="(m, i) in msgs" :key="i">
          <div class="msg-row" :class="m.role === 'human' ? 'is-user' : m.role === 'ai' ? 'is-ai' : 'is-sys'">
            <template v-if="m.role === 'human'">
              <div class="msg-bubble user-bubble">{{ m.content }}</div>
            </template>
            <template v-else-if="m.role === 'ai'">
              <div class="ai-avatar">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z"/>
                  <path d="M8 10h.01 M16 10h.01 M9.5 15a3.5 3.5 0 0 0 5 0"/>
                  <path d="M12 2v2 M12 20v2 M2 12h2 M20 12h2"/>
                </svg>
              </div>
              <div class="msg-bubble ai-bubble" v-html="renderContent(m.content)" />
            </template>
            <template v-else-if="m.role === 'attachment' && m.file">
              <div class="attachment-block">
                <div class="attachment-label">{{ m.file.tool_name }}</div>
                <template v-if="m.file.is_image">
                  <img :src="m.file.url" :alt="m.file.filename" class="attachment-image" @click="openUrl(m.file.url)" />
                </template>
                <template v-else>
                  <a :href="m.file.url" target="_blank" class="file-link">{{ m.file.filename }}</a>
                </template>
              </div>
            </template>
            <template v-else-if="m.role === 'system' && (m.content || '').startsWith('⚙')">
              <ToolCard :content="m.content || ''" />
            </template>
            <template v-else>
              <div class="sys-msg">{{ m.content }}</div>
            </template>
          </div>
        </template>
        <div v-if="streaming" class="typing-dots"><span /><span /><span /></div>
      </div>

      <div class="chat-foot">
        <div v-if="props.demoMode" class="demo-remaining" :class="{ exhausted: demoBlocked }">
          {{ demoBlocked ? '演示次数已用完' : `剩余 ${props.demoRemaining ?? '?'}/${props.demoMax ?? '?'} 次对话` }}
        </div>
        <textarea
          v-model="input"
          placeholder="例如：搜索 2026 年 AI Agent 岗位技能要求并整理成清单"
          rows="1"
          @keydown="onKeydown"
          :disabled="streaming || demoBlocked"
        />
        <button class="btn-send" @click="sendChat" :disabled="streaming || !input.trim() || demoBlocked">↑</button>
      </div>
    </main>
  </div>
</template>
