<script setup lang="ts">
import { onMounted, ref } from 'vue'
import * as agentApi from '@/api/agent'
import { useToast } from '@/composables/useToast'

const toast = useToast()
const loading = ref(false)
const tasks = ref<agentApi.AgentTaskSummary[]>([])
const selected = ref<agentApi.AgentTaskDetail | null>(null)
const events = ref<agentApi.AgentStatusEvent[]>([])
const metrics = ref<agentApi.AgentMetrics | null>(null)

const load = async () => {
  loading.value = true
  try { tasks.value = (await agentApi.listTasks({ page: 1, pageSize: 50 })).data.records } catch (e) { toast.error(e instanceof Error ? e.message : '加载 Agent 任务失败') } finally { loading.value = false }
}
const open = async (task: agentApi.AgentTaskSummary) => {
  try {
    selected.value = (await agentApi.getTask(task.id)).data
    events.value = (await agentApi.getTaskEvents(task.id)).data
    metrics.value = (await agentApi.getTaskMetrics(task.id)).data
  } catch (e) { toast.error(e instanceof Error ? e.message : '加载任务详情失败') }
}
const retry = async () => { if (!selected.value) return; await agentApi.retryTask(selected.value.id); toast.success('任务已重新排队'); await load() }
const cancel = async () => { if (!selected.value) return; await agentApi.cancelTask(selected.value.id); toast.success('已发送取消请求'); await load() }
onMounted(load)
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between"><div><h2 class="text-2xl font-semibold">Agent 任务工作台</h2><p class="mt-1 text-sm text-muted-foreground">查看计划执行、状态事件、指标并处理失败任务</p></div><button class="rounded-lg bg-primary px-4 py-2 text-sm" @click="load">刷新</button></div>
    <div class="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
      <section class="rounded-xl border border-border bg-card p-4"><div v-if="loading" class="py-8 text-center text-muted-foreground">加载中…</div><div v-else-if="!tasks.length" class="py-8 text-center text-muted-foreground">暂无 Agent 任务</div><button v-for="task in tasks" :key="task.id" class="mb-2 w-full rounded-lg border border-border p-3 text-left hover:bg-accent" :class="selected?.id === task.id ? 'ring-2 ring-primary' : ''" @click="open(task)"><div class="flex justify-between gap-3"><span class="font-medium">#{{ task.id }} {{ task.query }}</span><span class="text-xs text-muted-foreground">{{ task.status }}</span></div><div class="mt-1 text-xs text-muted-foreground">{{ task.createdAt }}</div></button></section>
      <section class="rounded-xl border border-border bg-card p-5"><div v-if="!selected" class="py-12 text-center text-muted-foreground">选择一个任务查看详情</div><template v-else><div class="flex items-start justify-between gap-3"><div><h3 class="text-lg font-semibold">任务 #{{ selected.id }}</h3><p class="mt-1 text-sm text-muted-foreground">{{ selected.query }}</p></div><div class="flex gap-2"><button v-if="['FAILED','TIMEOUT','DEAD_LETTER'].includes(selected.status)" class="rounded border px-3 py-1 text-xs" @click="retry">重试</button><button v-if="['RUNNING','QUEUED','PROCESSING'].includes(selected.status)" class="rounded border px-3 py-1 text-xs" @click="cancel">取消</button></div></div><div class="mt-5 grid grid-cols-2 gap-3 text-sm"><div class="rounded bg-muted p-3"><p class="text-muted-foreground">状态</p><p class="font-medium">{{ selected.status }}</p></div><div class="rounded bg-muted p-3"><p class="text-muted-foreground">更新时间</p><p>{{ selected.updatedAt }}</p></div></div><h4 class="mt-6 font-medium">指标</h4><pre class="mt-2 overflow-auto rounded bg-muted p-3 text-xs">{{ JSON.stringify(metrics, null, 2) }}</pre><h4 class="mt-6 font-medium">状态事件</h4><div class="mt-2 space-y-2"> <div v-for="event in events" :key="event.id" class="rounded border border-border p-2 text-xs"><span class="font-medium">{{ event.eventType }}</span> {{ event.message || event.status }} <span class="text-muted-foreground">{{ event.createdAt }}</span></div><p v-if="!events.length" class="text-sm text-muted-foreground">暂无事件</p></div></template></section>
    </div>
  </div>
</template>
