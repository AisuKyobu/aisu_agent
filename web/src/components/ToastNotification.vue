<script setup lang="ts">
defineProps<{
  toasts: { id: number; type: string; text: string }[]
}>()

defineEmits<{ (e: 'remove', id: number): void }>()
</script>

<template>
  <div class="toast-container">
    <div v-for="t in toasts" :key="t.id" class="toast" :class="'toast-' + t.type" @click="$emit('remove', t.id)">
      {{ t.text }}
    </div>
  </div>
</template>
