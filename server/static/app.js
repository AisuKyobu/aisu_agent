let currentSession = null;
let sessions = [];
let ws = null;

function setStatus(text, cls) {
  const el = document.getElementById('status-bar');
  if (!el) return;
  el.textContent = text;
  el.className = cls || '';
}

function toast(msg, dur = 2000) {
  const el = document.getElementById('toast');
  el.textContent = msg; el.style.display = 'block';
  setTimeout(() => el.style.display = 'none', dur);
}

function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = s; return d.innerHTML;
}

// ── Tab switching ──
document.querySelectorAll('.tabs button').forEach(btn => {
  btn.onclick = () => {
    document.querySelectorAll('.tabs button, .tab').forEach(el => el.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
  };
});

// ── WebSocket ──
function connectWs() {
  const proto = location.protocol === 'https:' ? 'wss://' : 'ws://';
  ws = new WebSocket(proto + location.host + '/ws');
  let streamBuffer = '';
  let streamEl = null;

  ws.onmessage = (e) => {
    const data = JSON.parse(e.data);

    // 校验事件是否属于当前会话，防止 A 会话的回复渲染到 B 窗口
    if (data.session_id && data.session_id !== currentSession) return;

    if (data.type === 'token') {
      setStatus('▸ 生成回复中...', 'active');
      if (!streamEl) {
        const el = document.getElementById('chat-msgs');
        streamEl = document.createElement('div');
        streamEl.className = 'msg-ai';
        const bubble = document.createElement('div');
        bubble.className = 'bubble';
        streamEl.appendChild(bubble);
        el.appendChild(streamEl);
      }
      streamBuffer += data.content;
      streamEl.firstChild.innerHTML = marked ? marked.parse(streamBuffer, {breaks:true, gfm:true}) : escapeHtml(streamBuffer);
      scrollChat();
    }
    else if (data.type === 'tool_call') {
      flushStream();
      chatLogTool(data.tools, data.args);
      const cleanArgs = data.args ? data.args.replace(/\{|\}|'/g,'').slice(0,60) : '';
      setStatus('⚙ ' + data.tools.join(', ') + (cleanArgs ? ' ' + cleanArgs : '') + ' 执行中...', 'active');
    }
    else if (data.type === 'tool_result') {
      if (streamEl) flushStream();
      chatLogResult(data.content);
      setStatus('✓ 工具已返回', 'done');
      setTimeout(() => setStatus('就绪'), 2000);
    }
    else if (data.type === 'error') {
      flushStream();
      appendMsg('ai', '错误: ' + data.content);
      removeLoading();
      unlockInput();
      setStatus('✗ 错误', '');
    }
    else if (data.type === 'system_error') {
      flushStream();
      appendMsg('ai', data.content);
      removeLoading();
      unlockInput();
      setStatus('✗ 系统错误', '');
    }
    else if (data.type === 'cron_result') {
      const err = data.error ? ': ' + data.error : '';
      toast('\u23F0 ' + data.task + (data.status === 'completed' ? ' 已完成' : ' 失败' + err));
    }
    else if (data.type === 'agent_status' || data.type === 'monitor_global') {
      updateMonitor(data);
      if (data.limit_hit) {
        toast('\u26A0 ' + data.limit_hit, 5000);
      }
    }
    else if (data.type === 'done') {
      flushStream();
      removeLoading();
      unlockInput();
      setStatus('就绪', 'done');
      setTimeout(() => setStatus('就绪'), 1000);
    }
  };

  function flushStream() {
    if (streamEl) {
      streamEl.firstChild.innerHTML = renderMd(streamBuffer);
      streamEl = null;
      streamBuffer = '';
    }
  }
  ws.onclose = () => {
    if (_sending) {
      appendMsg('ai', '⚠ 连接断开，正在自动重连...');
      unlockInput();
    }
    setStatus('重连中...', '');
    setTimeout(connectWs, 3000);
  };
  ws.onerror = () => { setStatus('连接异常', ''); };
}

let _scrollPending = false;
function scrollChat() {
  if (_scrollPending) return;
  _scrollPending = true;
  requestAnimationFrame(() => {
    const el = document.getElementById('chat-msgs');
    if (el) el.scrollTop = el.scrollHeight;
    _scrollPending = false;
  });
}

function chatLogTool(tools, args) {
  const el = document.getElementById('chat-msgs');
  const d = document.createElement('div');
  d.className = 'msg-tool';
  let text = '⚙ ' + tools.join(', ');
  if (args) {
    const clean = args.replace(/\{|\}/g, '').replace(/'/g, '');
    text += '  ' + escapeHtml(clean.slice(0, 120));
  }
  d.innerHTML = '<span style="color:#fb7299">' + text + '</span>';
  el.appendChild(d);
  scrollChat();
}

function chatLogResult(content) {
  if (!content) return;
  const el = document.getElementById('chat-msgs');
  const d = document.createElement('div');
  d.className = 'msg-tool';
  d.innerHTML = '<span style="color:#636d83">  ↳ ' + escapeHtml(content).slice(0,200) + '</span>';
  el.appendChild(d);
  scrollChat();
}

// ── Sessions ──
function sessionLabel(s) {
  if (s.title && s.title !== s.id) return s.title;
  if (s.id.startsWith('cli_')) return 'CLI 会话';
  if (s.id.startsWith('qq_')) return 'QQ-' + s.id.slice(3);
  if (s.id.startsWith('web_')) return 'Web 会话';
  return s.title || s.id;
}

function renderSessions() {
  const el = document.getElementById('session-list');
  el.innerHTML = sessions.map(s => {
    const active = currentSession === s.id ? ' active' : '';
    return `
      <div class="sidebar-item${active}" data-sid="${s.id}" ondblclick="startRename('${s.id}')">
        <span class="sname">${escapeHtml(sessionLabel(s))}</span>
        <span class="del" onclick="event.stopPropagation();deleteSession('${s.id}')">×</span>
      </div>
    `;
  }).join('');
  el.querySelectorAll('.sidebar-item').forEach(item => {
    item.onclick = (e) => {
      if (e.target.classList.contains('del')) return;
      let t;
      if (item.clickTimer) { clearTimeout(item.clickTimer); item.clickTimer = null; return; }
      item.clickTimer = setTimeout(() => { item.clickTimer = null; switchSession(item.dataset.sid); }, 200);
    };
  });
}

function startRename(id) {
  const item = document.querySelector(`.sidebar-item[data-sid="${id}"] .sname`);
  const old = item.textContent;
  const input = document.createElement('input');
  input.value = old;
  input.style.cssText = 'background:#0d1117;border:1px solid #fb7299;border-radius:4px;padding:2px 6px;color:#e6edf3;font-size:13px;width:100%';
  item.replaceWith(input);
  input.focus();
  input.select();
  input.onblur = () => finishRename(id, input.value);
  input.onkeydown = (e) => { if (e.key === 'Enter') input.blur(); if (e.key === 'Escape') { input.value = old; input.blur(); } };
}

async function finishRename(id, title) {
  if (!title.trim()) { renderSessions(); return; }
  await fetch('/api/sessions/' + id, {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({title: title.trim()})});
  const s = sessions.find(x => x.id === id);
  if (s) s.title = title.trim();
  renderSessions();
}

async function newSession() {
  const r = await fetch('/api/sessions', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({title:'新会话'})});
  const data = await r.json();
  sessions.unshift(data.session);
  currentSession = data.session.id;
  renderSessions();
  loadHistory(currentSession);
  toast('已创建新会话');
}

async function switchSession(id) {
  currentSession = id;
  _sending = false;
  streamEl = null;
  streamBuffer = '';
  renderSessions();
  loadHistory(id);
  unlockInput();
}

async function deleteSession(id) {
  await fetch('/api/sessions/' + id, {method:'DELETE'});
  sessions = sessions.filter(s => s.id !== id);
  if (currentSession === id) {
    currentSession = null;
    document.getElementById('chat-msgs').innerHTML = '<div class="chat-empty">选择一个会话开始聊天</div>';
  }
  renderSessions();
}

async function loadHistory(id) {
  const el = document.getElementById('chat-msgs');
  el.innerHTML = '<div style="text-align:center;color:#636d83;padding:20px">加载中...</div>';
  const r = await fetch('/api/sessions/' + id + '/history');
  const data = await r.json();
  el.innerHTML = '';
  if (!data.messages || data.messages.length === 0) {
    el.innerHTML = '<div class="chat-empty">新对话，发送第一条消息</div>'; return;
  }
  for (const m of data.messages) {
    if (m.role === 'system') continue;
    if (m.role === 'ai' && !m.content) continue;
    if (m.role === 'tool') {
      if (!m.content) continue;
      const d = document.createElement('div');
      d.className = 'msg-tool';
      const name = m.name ? '⏎ ' + m.name + ' ' : '';
      d.innerHTML = '<span style="color:#636d83">  ↳ ' + name + escapeHtml(m.content).slice(0, 300) + '</span>';
      el.appendChild(d);
      continue;
    }
    appendMsg(m.role, m.content);
  }
}

// ── Chat ──
function renderMd(text) {
  return marked ? marked.parse(text, {breaks:true, gfm:true}) : escapeHtml(text);
}

function appendMsg(role, content) {
  const el = document.getElementById('chat-msgs');
  const cls = role === 'human' ? 'msg-human' : 'msg-ai';
  const d = document.createElement('div');
  d.className = cls;
  if (role === 'human')
    d.innerHTML = '<div class="bubble">' + escapeHtml(content) + '</div>';
  else
    d.innerHTML = '<div class="bubble">' + renderMd(content) + '</div>';
  el.appendChild(d);
  scrollChat();
}

function chatLoading() {
  const d = document.createElement('div'); d.id = 'chat-loading';
  d.innerHTML = '<span style="color:#636d83">⚡ 处理中...</span>'; d.style.padding = '4px 0';
  return d;
}
function removeLoading() {
  const el = document.getElementById('chat-loading');
  if (el) el.remove();
}

let _sending = false;

function sendChat() {
  if (_sending) return;
  const input = document.getElementById('chat-input');
  const text = input.value.trim();
  if (!text || !currentSession) { if(!currentSession) toast('请先选择或创建一个会话'); return; }
  _sending = true;
  input.disabled = true;
  input.value = '';
  streamEl = null;
  streamBuffer = '';
  appendMsg('human', text);
  chatLoading();
  setStatus('◉ 发送中...', 'active');
  if (!ws || ws.readyState !== WebSocket.OPEN) { appendMsg('ai', '错误: 连接断开'); unlockInput(); return; }
  ws.send(JSON.stringify({type:'message', content: text, session_id: currentSession}));
}

function unlockInput() {
  _sending = false;
  const input = document.getElementById('chat-input');
  input.disabled = false;
  input.focus();
}

// ── Monitor ──
let _monitorData = [];

const STATUS_COLORS = {thinking: '#FF9800', executing: '#FF9800', idle: '#81c784', error: '#ef4444', completed: '#81c784'};
const STATUS_LABELS = {thinking: '● 思考中', executing: '● 执行中', idle: '○ 空闲', error: '✗ 错误', completed: '✓ 完成'};
const SOURCE_LABELS = {web: '🖥 Web', qq: '💬 QQ', cron: '⏰ Cron'};

function _timeAgo(ts) {
  if (!ts) return '未知';
  const s = Math.floor(Date.now()/1000 - ts);
  if (s < 10) return '刚刚';
  if (s < 60) return s + '秒前';
  if (s < 3600) return Math.floor(s/60) + '分钟前';
  return Math.floor(s/3600) + '小时前';
}

function _renderMonitorTable() {
  const tbody = document.getElementById('monitor-tbody');
  if (!_monitorData.length) {
    tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--text-dim);padding:40px">暂无活跃会话</td></tr>';
    return;
  }
  tbody.innerHTML = _monitorData.map((d, i) => {
    const ls = d.last_state || {};
    const st = d.status || 'idle';
    const color = STATUS_COLORS[st] || '#81c784';
    const label = STATUS_LABELS[st] || st;
    const srcIcon = d.source === 'sub' ? '📦' : (d.source_icon || '❓');
    const srcLabel = d.source === 'sub' ? 'Sub' : (SOURCE_LABELS[d.source] || d.source || '?');
    const mode = d.execution_mode || ls.execution_mode || '';
    const task = ls.task_type || '-';
    const step = ls.step != null ? ls.step + '/' + (ls.max_steps || '?') : '-';
    const tools = (ls.tools_used || []).join(', ') || '-';
    const ago = _timeAgo(d.updated_at);
    const name = d.title && d.title !== d.id ? d.title : '';
    const isSub = d.source === 'sub' || d.id.startsWith('sub_');
    return `<tr style="border-bottom:1px solid rgba(255,255,255,.03);cursor:pointer;transition:background .15s${isSub ? ';opacity:0.7' : ''}"
          onmouseover="this.style.background='rgba(255,255,255,.03)'"
          onmouseout="this.style.background='none'"
          onclick="showMonitorDetail(${i})">
      <td style="padding:6px 8px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escapeHtml(d.id)}">
        ${isSub ? '<span style="color:var(--text-dim);margin-right:4px">└─</span>' : ''}
        <span style="font-family:monospace;font-size:11px">${escapeHtml(d.id.slice(0,12))}</span>
        ${name ? `<br>${isSub ? '<span style="color:var(--text-dim);margin-right:4px">└─</span>' : ''}<span style="font-size:11px;color:var(--text-dim)">${escapeHtml(name)}</span>` : ''}
      </td>
      <td style="padding:6px 8px;text-align:center;width:70px">${srcIcon} ${srcLabel}</td>
      <td style="padding:6px 8px;color:${color};width:80px">${label}</td>
      <td style="padding:6px 8px;width:75px;font-size:11px">${mode ? escapeHtml(mode) : '-'}</td>
      <td style="padding:6px 8px;width:80px">${task}</td>
      <td style="padding:6px 8px;width:70px">${step}</td>
      <td style="padding:6px 8px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:120px">${tools}</td>
      <td style="padding:6px 8px;color:var(--text-dim);font-size:11px;width:80px;white-space:nowrap">${ago}</td>
    </tr>`;
  }).join('');
}

function showMonitorDetail(idx) {
  const d = _monitorData[idx];
  if (!d) return;
  const ls = d.last_state || {};
  document.getElementById('monitor-detail').style.display = 'block';
  document.getElementById('monitor-detail-title').textContent = '会话: ' + d.id;
  document.getElementById('monitor-detail-body').innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px">
      <div><span style="color:var(--text-dim)">ID:</span> ${escapeHtml(d.id)}</div>
      <div><span style="color:var(--text-dim)">来源:</span> ${SOURCE_LABELS[d.source] || d.source || '?'}</div>
      <div><span style="color:var(--text-dim)">状态:</span> <span style="color:${STATUS_COLORS[d.status||'idle']}">${STATUS_LABELS[d.status||'idle']}</span></div>
      <div><span style="color:var(--text-dim)">执行模式:</span> ${d.execution_mode || ls.execution_mode || '-'}</div>
      <div><span style="color:var(--text-dim)">任务类型:</span> ${ls.task_type || '-'}</div>
      <div><span style="color:var(--text-dim)">步数:</span> ${ls.step||0}/${ls.max_steps||'?'}</div>
      <div><span style="color:var(--text-dim)">校验级别:</span> ${ls.verifier_level || '-'}</div>
      <div><span style="color:var(--text-dim)">工具:</span> ${(ls.tools_used||[]).join(', ') || '-'}</div>
      <div><span style="color:var(--text-dim)">名称:</span> ${escapeHtml(d.title || '-')}</div>
      <div><span style="color:var(--text-dim)">最后活跃:</span> ${_timeAgo(d.updated_at)}</div>
    </div>
    ${d.summary ? `<div style="margin-top:10px;padding-top:10px;border-top:1px solid rgba(255,255,255,.05)"><span style="color:var(--text-dim);font-size:11px">摘要</span><div style="margin-top:4px;line-height:1.6;white-space:pre-wrap;word-break:break-word">${escapeHtml(d.summary)}</div></div>` : ''}
  `;
}

function updateMonitor(data) {
  if (data.type === 'monitor_global') {
    _monitorData = data.sessions || [];
    _renderMonitorTable();
  }
}

// ── Skills ──
async function toggleSkill(name, enable) {
  const r = await fetch('/api/skills/' + name, {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({enabled: enable})});
  if (r.ok) {
    const tag = document.querySelector(`[data-skill-name="${name}"]`);
    if (tag) { tag.textContent = enable ? '已启用' : '已禁用'; tag.onclick = function(){ toggleSkill(name, !enable); }; }
  }
}

async function installSkillZip() {
  const input = document.getElementById('skill-zip-input');
  const file = input.files[0];
  if (!file) return;
  const form = new FormData();
  form.append('file', file);
  toast('正在安装技能...');
  const r = await fetch('/api/skills/install', {method:'POST', body: form});
  const data = await r.json();
  if (data.ok) {
    const names = data.names || [];
    const msg = names.length > 0
      ? '已安装 ' + names.length + ' 个技能: ' + names.join(', ')
      : '没有新技能可安装（同名已存在）';
    toast(msg, 5000);
    setTimeout(() => location.reload(), 1500);
  } else {
    toast('安装失败: ' + (data.error || '未知错误'));
  }
  input.value = '';
}

// ── Workspace ──
let wsCurrentFile = 'AGENTS.md';

async function openWsFile(filename) {
  wsCurrentFile = filename;
  document.getElementById('ws-filename').textContent = filename;
  const hints = {
    'AGENTS.md': '💡 设定 Agent 的行为规则、回答风格和工作方式。支持 Markdown 格式，每次对话自动注入。',
    'USER.md': '💡 记录用户信息（姓名、偏好、习惯等）。Agent 会在对话中参考这些信息提供个性化回复。',
  };
  document.getElementById('ws-hint').textContent = hints[filename] || '';
  document.querySelectorAll('#ws-file-list .sidebar-item').forEach(el => el.classList.remove('active'));
  const item = document.querySelector(`#ws-file-list [data-file="${filename}"]`);
  if (item) item.classList.add('active');
  const r = await fetch('/api/workspace/' + filename);
  const data = await r.json();
  document.getElementById('ws-editor').value = data.content || '';
}

async function saveWorkspace() {
  const content = document.getElementById('ws-editor').value;
  await fetch('/api/workspace', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({filename: wsCurrentFile, content})});
  toast('已保存 ' + wsCurrentFile);
}

// ── Cron ──
async function removeCron(jobId) {
  await fetch('/api/cron/remove', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({job_id: jobId})});
  const el = document.getElementById('cron-container');
  const cards = el.querySelectorAll('[data-job-id]');
  for (const card of cards) {
    if (card.dataset.jobId === jobId) { card.remove(); break; }
  }
  if (!el.querySelector('[data-job-id]')) {
    el.innerHTML = '<div class="empty-state" style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center"><div class="icon">⏰</div><p>暂无定时任务</p></div>';
  }
}

// Init
(async () => {
  connectWs();
  const r = await fetch('/api/sessions');
  const data = await r.json();
  sessions = data.sessions || [];
  if (sessions.length > 0) currentSession = sessions[0].id;
  renderSessions();
  if (currentSession) loadHistory(currentSession);

  // 初始化 Monitor：从 sessions/ 目录加载全量历史 → WS 实时覆盖
  try {
    const mr = await fetch('/api/monitor/sessions');
    const md = await mr.json();
    _monitorData = md.sessions || [];
    _renderMonitorTable();
  } catch (e) { /* ignore */ }
})();
