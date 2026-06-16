<script setup lang="ts">
import { ref, computed } from 'vue'

const props = defineProps<{ content: string }>()

const expanded = ref(false)

const parsed = computed(() => {
  const raw = props.content || ''
  const m = raw.match(/^⚙\s*(\S+)(?:\s+(.*))?$/s)
  if (!m) return { name: '', args: raw }
  return { name: m[1], args: m[2] || '' }
})
</script>

<template>
  <div class="tool-card" @click="expanded = !expanded">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">
      <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
    </svg>
    <span class="tool-card-name">{{ parsed.name }}</span>
    <span v-if="parsed.args" class="tool-card-args">{{ parsed.args }}</span>
  </div>
  <div v-if="expanded && parsed.args" class="tool-card-detail">{{ parsed.args }}</div>
</template>
