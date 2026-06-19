<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ArrowRight, CalendarDays, ClipboardList, Layers, RefreshCw, ScrollText, User } from 'lucide-vue-next'
import * as auditApi from '@/api/audit'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import LoadingSkeleton from '@/components/LoadingSkeleton.vue'
import EmptyState from '@/components/EmptyState.vue'
import { useToast } from '@/composables/useToast'
import { formatDateTime } from '@/utils/date'
import { friendlyErrorMessage } from '@/utils/errorMessage'

const toast = useToast()
const tab = ref<'operations' | 'crossTenant'>('operations')
const loading = ref(false)
const operations = ref<auditApi.AuditLogEntry[]>([])
const crossTenant = ref<auditApi.CrossTenantAuditEntry[]>([])
const actionFilter = ref('')

const load = async () => {
  loading.value = true
  try {
    if (tab.value === 'operations') {
      const res = await auditApi.listOperationAudits({
        limit: 100,
        action: actionFilter.value || undefined,
      })
      operations.value = res.data || []
    } else {
      const res = await auditApi.listCrossTenantAudits(100)
      crossTenant.value = res.data || []
    }
  } catch (e) {
    toast.error(friendlyErrorMessage(e, '加载审计日志失败'))
  } finally {
    loading.value = false
  }
}

const switchTab = (t: 'operations' | 'crossTenant') => {
  tab.value = t
  load()
}

// ── 统计概览 ──
const todayPrefix = new Date().toISOString().slice(0, 10)
const todayCount = computed(() => {
  const list = tab.value === 'operations' ? operations.value : crossTenant.value
  return list.filter((log) => String(log.createdAt || '').startsWith(todayPrefix)).length
})
const actionTypeCount = computed(() => {
  const list = tab.value === 'operations' ? operations.value : crossTenant.value
  return new Set(list.map((log) => log.action)).size
})

// ── 动作分类配色（前缀 → 色调）──
const ACTION_TONES: Array<{ prefix: string; dot: string; chip: string }> = [
  { prefix: 'app', dot: 'bg-blue-500', chip: 'border-blue-400/30 bg-blue-400/[0.08] text-blue-700 dark:text-blue-300' },
  { prefix: 'apikey', dot: 'bg-violet-500', chip: 'border-violet-400/30 bg-violet-400/[0.08] text-violet-700 dark:text-violet-300' },
  { prefix: 'kb', dot: 'bg-emerald-500', chip: 'border-emerald-400/30 bg-emerald-400/[0.08] text-emerald-700 dark:text-emerald-300' },
  { prefix: 'notice', dot: 'bg-cyan-500', chip: 'border-cyan-400/30 bg-cyan-400/[0.08] text-cyan-700 dark:text-cyan-300' },
  { prefix: 'user', dot: 'bg-amber-500', chip: 'border-amber-400/30 bg-amber-400/[0.08] text-amber-700 dark:text-amber-300' },
  { prefix: 'tenant', dot: 'bg-rose-500', chip: 'border-rose-400/30 bg-rose-400/[0.08] text-rose-700 dark:text-rose-300' },
]
function actionTone(action: string) {
  const lower = (action || '').toLowerCase()
  return ACTION_TONES.find((tone) => lower.startsWith(tone.prefix)) ?? {
    dot: 'bg-zinc-400',
    chip: 'border-zinc-400/30 bg-zinc-400/[0.08] text-zinc-600 dark:text-zinc-300',
  }
}

/** 归一化展示行：两种审计条目合并为统一结构，模板无需收窄联合类型 */
interface DisplayLog {
  id: number
  action: string
  detail: string
  operatorId?: number
  createdAt: string
  crossTenant: boolean
  fromTenant?: number
  toTenant?: number
}
const displayLogs = computed<DisplayLog[]>(() => {
  if (tab.value === 'operations') {
    return operations.value.map((log) => ({
      id: log.id,
      action: log.action ?? '',
      detail: log.detail || (log.targetType ?? '') + (log.targetId ? ' #' + log.targetId : ''),
      operatorId: log.operatorId,
      createdAt: log.createdAt ?? '',
      crossTenant: false,
    }))
  }
  return crossTenant.value.map((log) => ({
    id: log.id,
    action: log.action ?? '',
    detail: '跨租户代操作',
    operatorId: log.operatorId,
    createdAt: log.createdAt ?? '',
    crossTenant: true,
    fromTenant: log.fromTenant,
    toTenant: log.toTenant,
  }))
})

onMounted(load)
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h1 class="flex items-center gap-2 text-xl font-semibold">
          <ScrollText class="h-5 w-5 text-primary" /> 审计日志
        </h1>
        <p class="mt-1 text-sm text-muted-foreground">敏感操作与跨租户代操作记录（平台管理员）</p>
      </div>
      <Button variant="outline" class="gap-2" :disabled="loading" @click="load">
        <RefreshCw class="h-4 w-4" :class="loading && 'animate-spin'" /> 刷新
      </Button>
    </div>

    <!-- 统计概览 -->
    <section class="grid gap-4 sm:grid-cols-3">
      <div class="rounded-xl border border-border bg-card/80 p-5">
        <div class="flex items-center justify-between">
          <span class="text-sm text-muted-foreground">{{ tab === 'operations' ? '操作审计记录' : '跨租户代操作记录' }}</span>
          <span class="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/12 text-primary"><ScrollText class="h-4 w-4" /></span>
        </div>
        <p class="mt-3 text-3xl font-semibold tabular-nums tracking-tight text-foreground">{{ (tab === 'operations' ? operations : crossTenant).length }}</p>
        <p class="mt-1.5 text-xs text-muted-foreground">最近 100 条范围内</p>
      </div>
      <div class="rounded-xl border border-border bg-card/80 p-5">
        <div class="flex items-center justify-between">
          <span class="text-sm text-muted-foreground">今日新增</span>
          <span class="flex h-8 w-8 items-center justify-center rounded-lg bg-cyan-500/12 text-cyan-600 dark:text-cyan-400"><CalendarDays class="h-4 w-4" /></span>
        </div>
        <p class="mt-3 text-3xl font-semibold tabular-nums tracking-tight text-foreground">{{ todayCount }}</p>
        <p class="mt-1.5 text-xs text-muted-foreground">{{ todayPrefix }} 当天写入</p>
      </div>
      <div class="rounded-xl border border-border bg-card/80 p-5">
        <div class="flex items-center justify-between">
          <span class="text-sm text-muted-foreground">涉及动作类型</span>
          <span class="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-500/12 text-violet-600 dark:text-violet-400"><Layers class="h-4 w-4" /></span>
        </div>
        <p class="mt-3 text-3xl font-semibold tabular-nums tracking-tight text-foreground">{{ actionTypeCount }}</p>
        <p class="mt-1.5 text-xs text-muted-foreground">按动作前缀分类（app / kb / apikey…）</p>
      </div>
    </section>

    <!-- Tab + 过滤 -->
    <div class="flex flex-wrap items-center gap-2">
      <div class="flex rounded-lg border border-border p-1">
        <button
          class="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition-colors"
          :class="tab === 'operations' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted'"
          @click="switchTab('operations')"
        >
          <ClipboardList class="h-3.5 w-3.5" /> 操作审计
        </button>
        <button
          class="rounded-md px-3 py-1.5 text-sm transition-colors"
          :class="tab === 'crossTenant' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted'"
          @click="switchTab('crossTenant')"
        >
          跨租户代操作
        </button>
      </div>
      <Input
        v-if="tab === 'operations'"
        v-model="actionFilter"
        placeholder="按动作过滤，如 app.publish"
        class="ml-auto h-9 max-w-64"
        @keyup.enter="load"
      />
    </div>

    <!-- 日志列表 -->
    <div class="rounded-xl border border-border bg-card/80">
      <div class="border-b border-border/70 px-5 py-4">
        <h2 class="text-sm font-medium">{{ tab === 'operations' ? '操作审计' : '跨租户代操作审计' }}</h2>
        <p class="mt-0.5 text-xs text-muted-foreground">
          {{ tab === 'operations' ? '应用 / API Key / 共享 / 公告等敏感操作的审计记录' : '平台管理员代其他租户执行操作的记录' }}
        </p>
      </div>
      <div class="p-4 sm:p-5">
        <div v-if="loading" class="space-y-2"><LoadingSkeleton type="card" :count="4" /></div>
        <EmptyState
          v-else-if="(tab === 'operations' ? operations : crossTenant).length === 0"
          :icon="ScrollText"
          title="暂无审计记录"
          description="敏感操作（应用发布、API Key 生成、知识库共享、公告发布）会自动记录在这里，无需手动开启。"
        />
        <ol v-else class="relative space-y-2">
          <li
            v-for="log in displayLogs"
            :key="log.id"
            class="group flex items-start gap-3 rounded-xl border border-border/70 bg-muted/20 p-3.5 transition-colors hover:border-primary/25 hover:bg-muted/40"
          >
            <!-- 动作色点 + 分类徽章 -->
            <span class="mt-1.5 h-2 w-2 shrink-0 rounded-full" :class="actionTone(log.action).dot" />
            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-center gap-2">
                <span class="rounded-md border px-2 py-0.5 font-mono text-[11px] font-medium" :class="actionTone(log.action).chip">{{ log.action }}</span>
                <span v-if="log.crossTenant" class="inline-flex items-center gap-1 text-xs text-muted-foreground">
                  租户 {{ log.fromTenant }} <ArrowRight class="h-3 w-3" /> 租户 {{ log.toTenant }}
                </span>
              </div>
              <p class="mt-1 truncate text-sm text-foreground/85">{{ log.detail }}</p>
            </div>
            <!-- 操作人 + 时间 -->
            <div class="flex shrink-0 flex-col items-end gap-1 text-xs text-muted-foreground">
              <span class="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5">
                <User class="h-3 w-3" /> 操作人 {{ log.operatorId }}
              </span>
              <span class="tabular-nums">{{ formatDateTime(log.createdAt || '') }}</span>
            </div>
          </li>
        </ol>
      </div>
    </div>
  </div>
</template>
