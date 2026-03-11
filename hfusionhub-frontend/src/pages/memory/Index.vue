<script setup lang="ts">
import { onMounted, ref } from 'vue'
import * as memoryApi from '@/api/memory'
import { useToast } from '@/composables/useToast'
const toast = useToast(); const memories = ref<memoryApi.MemoryEntry[]>([]); const draft = ref(''); const loading = ref(false)
const load = async () => { loading.value = true; try { memories.value = (await memoryApi.listMemories()).data } catch (e) { toast.error(e instanceof Error ? e.message : '加载记忆失败') } finally { loading.value = false } }
const add = async () => { if (!draft.value.trim()) return; await memoryApi.createMemory({ type: 'user_preference', content: draft.value.trim(), importance: 0.7 }); draft.value = ''; toast.success('记忆已保存'); await load() }
const remove = async (id: number) => { await memoryApi.deleteMemory(id); toast.success('记忆已删除'); await load() }
onMounted(load)
</script>
<template><div class="space-y-6"><div><h2 class="text-2xl font-semibold">长期记忆</h2><p class="mt-1 text-sm text-muted-foreground">管理 Agent 可用于后续任务的用户偏好与事实</p></div><div class="flex gap-2"><input v-model="draft" class="min-w-0 flex-1 rounded-lg border border-border bg-card px-3 py-2 text-sm" placeholder="例如：我偏好简洁的中文回答" @keyup.enter="add"><button class="rounded-lg bg-primary px-4 py-2 text-sm" @click="add">保存</button></div><div class="rounded-xl border border-border bg-card p-4"><div v-if="loading" class="py-8 text-center text-muted-foreground">加载中…</div><div v-else-if="!memories.length" class="py-8 text-center text-muted-foreground">暂无长期记忆</div><div v-for="memory in memories" :key="memory.id" class="flex items-start justify-between gap-4 border-b border-border py-3 last:border-0"><div><p class="text-sm">{{ memory.content }}</p><p class="mt-1 text-xs text-muted-foreground">{{ memory.type }} · 重要度 {{ memory.importance }}<span v-if="memory.expiresAt"> · 到期 {{ memory.expiresAt }}</span></p></div><button class="text-xs text-destructive" @click="remove(memory.id)">删除</button></div></div></div></template>
