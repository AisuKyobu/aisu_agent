<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  demoMode?: boolean
  demoRemaining?: number
  demoMax?: number
}>()

const emit = defineEmits<{
  start: []
  send: [prompt: string]
}>()

const demoExhausted = computed(() => props.demoMode && (props.demoRemaining ?? 0) <= 0)

const demoPrompts = [
  { icon: 'M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8', text: '搜索 2026 年 AI Agent 工程师的核心技能要求' },
  { icon: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z', text: '读取 workspace/简历.md 并给出优化建议' },
  { icon: 'M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8', text: '搜索目标公司最新的 AI 产品动态' },
  { icon: 'M12 20h9 M12 20V10m0 10l-7-7m7 7V4m0 6l7-7', text: '帮我准备一段 1 分钟 AI 岗位自我介绍' },
  { icon: 'M8 7h12M8 12h12M8 17h12M3 7h.01M3 12h.01M3 17h.01', text: '对比 RAG 与 Fine-tuning 的适用场景' },
]

const fullPrompts = [
  { icon: 'M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8', text: '搜索 2026 年 AI Agent 工程师的核心技能要求' },
  { icon: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z', text: '读取 workspace/简历.md 并给出优化建议' },
  { icon: 'M4 17l6-6 4 4 8-10', text: '写一个 Python 脚本抓取知乎热榜前 10' },
  { icon: 'M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z', text: '打开浏览器搜索 Kimi 最新发布并截图' },
  { icon: 'M12 20h9 M12 20V10m0 10l-7-7m7 7V4m0 6l7-7', text: '帮我准备一段 1 分钟 AI 岗位自我介绍' },
  { icon: 'M8 7h12M8 12h12M8 17h12M3 7h.01M3 12h.01M3 17h.01', text: '对比 RAG 与 Fine-tuning 的适用场景' },
]

const prompts = computed(() => props.demoMode ? demoPrompts : fullPrompts)
</script>

<template>
  <div class="welcome-card">
    <div class="welcome-logo">&gt;_</div>
    <div class="welcome-title">让 Aisu 帮你准备下一场面试</div>
    <div class="welcome-subtitle">
      直接描述目标，Aisu 会自己决定搜索、读文件、写代码还是浏览网页。
      <template v-if="demoMode">
        <br>演示模式仅开放搜索与读取工具，登录后可解锁完整能力。
      </template>
    </div>

    <div class="prompt-chips">
      <button
        v-for="(p, i) in prompts" :key="i"
        class="prompt-chip"
        :disabled="demoExhausted"
        @click="emit('send', p.text)"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path :d="p.icon" /></svg>
        {{ p.text }}
      </button>
    </div>

    <button class="btn btn-primary" :disabled="demoExhausted" @click="emit('start')">
      ＋ 开始新对话
    </button>

    <div class="welcome-hint">
      Enter 发送 · Shift+Enter 换行
    </div>
  </div>
</template>
