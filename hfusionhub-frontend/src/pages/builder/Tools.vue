<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  AlertTriangle,
  CheckCircle2,
  CircleAlert,
  Clock,
  ExternalLink,
  Eye,
  FileWarning,
  Globe,
  LoaderCircle,
  Radio,
  RefreshCw,
  Search,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Wrench,
  XCircle,
} from 'lucide-vue-next'
import * as toolsApi from '@/api/tools'
import type { ToolCallRecord, ToolEntry } from '@/api/tools'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

const registry = ref<toolsApi.ToolRegistryResponse | null>(null)
const calls = ref<toolsApi.ToolCallsResponse | null>(null)
const registryLoading = ref(false)
const callsLoading = ref(false)
const registryError = ref('')
const callsError = ref('')

// ── Risk helpers ───────────────────────────────────────────────────────

const riskMeta = (level: string) => {
  const map: Record<string, { label: string; icon: typeof ShieldCheck; class: string }> = {
    read_only: { label: '只读', icon: Eye, class: 'border-cyan-400/25 bg-cyan-400/10 text-cyan-200' },
    read_write: { label: '读写', icon: FileWarning, class: 'border-amber-400/25 bg-amber-400/10 text-amber-200' },
    external: { label: '外部', icon: Globe, class: 'border-violet-400/25 bg-violet-400/10 text-violet-200' },
  }
  return map[level] || { label: level, icon: Radio, class: 'border-border bg-muted text-muted-foreground' }
}

const statusMeta = (status: string) => {
  const map: Record<string, { label: string; class: string }> = {
    active: { label: '已激活', class: 'border-emerald-400/25 bg-emerald-400/10 text-emerald-300' },
    beta: { label: '需审批', class: 'border-amber-400/25 bg-amber-400/10 text-amber-200' },
    experimental: { label: '实验性', class: 'border-violet-400/25 bg-violet-400/10 text-violet-200' },
  }
  return map[status] || { label: status, class: 'border-border bg-muted text-muted-foreground' }
}

const permLabel = (perm: string) => {
  const map: Record<string, string> = {
    'knowledge_base:read': '知识库读取',
    'knowledge_base:write': '知识库写入',
    'system:time': '系统时间',
    'external:http': '外部 HTTP',
  }
  return map[perm] || perm
}

// ── Data fetching ──────────────────────────────────────────────────────

const loadRegistry = async () => {
  registryLoading.value = true
  registryError.value = ''
  try {
    const res = await toolsApi.getToolRegistry()
    registry.value = res.data
  } catch (e) {
    registryError.value = e instanceof Error ? e.message : '无法加载工具注册表'
  } finally {
    registryLoading.value = false
  }
}

const loadCalls = async () => {
  callsLoading.value = true
  callsError.value = ''
  try {
    const res = await toolsApi.getToolCalls(1, 30)
    calls.value = res.data
  } catch (e) {
    callsError.value = e instanceof Error ? e.message : '无法加载调用记录'
  } finally {
    callsLoading.value = false
  }
}

// ── Derived ────────────────────────────────────────────────────────────

const riskSummary = computed(() => registry.value?.risk_summary)

const formatMs = (ms: number | null) => {
  if (ms == null) return '—'
  if (ms < 1000) return `${ms} ms`
  return `${(ms / 1000).toFixed(2)} s`
}

const formatTime = (value?: string) => {
  if (!value) return '刚刚'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '刚刚'
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(date)
}

const truncate = (text: string | null, max = 80) => {
  if (!text) return '—'
  return text.length > max ? `${text.slice(0, max)}…` : text
}

const taskStatusLabel = (status: string) => {
  const map: Record<string, string> = {
    succeeded: '已完成',
    failed: '已失败',
    running: '执行中',
    waiting_approval: '待审批',
    pending: '排队中',
    cancelled: '已取消',
    timed_out: '已超时',
  }
  return map[status] || status
}

onMounted(() => {
  loadRegistry()
  loadCalls()
})
</script>

<template>
  <div class="space-y-6 pb-4">
    <!-- ── Hero ────────────────────────────────────────────────────── -->
    <section class="relative overflow-hidden rounded-2xl border border-border bg-card/80 shadow-[0_18px_45px_rgba(0,0,0,0.18)]">
      <div class="pointer-events-none absolute -right-12 -top-16 h-48 w-48 rounded-full bg-amber-400/10 blur-3xl" />
      <div class="relative flex flex-col gap-5 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
        <div class="flex gap-4">
          <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-amber-400/25 bg-amber-400/10 text-amber-200">
            <Wrench class="h-5 w-5" />
          </div>
          <div>
            <p class="text-xs font-medium tracking-[0.16em] text-amber-200/90">TOOL CENTER</p>
            <h1 class="mt-1 text-2xl font-semibold tracking-tight">工具中心</h1>
            <p class="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">
              查看 Agent 当前可调用的所有工具及其能力边界。工具列表来自后端注册表，不写死在前端。
              写入类工具仍需在 Agent 任务页走人工审批。
            </p>
          </div>
        </div>
        <div class="flex items-center gap-3">
          <Badge v-if="registry" variant="outline" class="border-emerald-400/25 bg-emerald-400/10 text-emerald-300">
            {{ registry.total }} 个工具
          </Badge>
          <Button variant="outline" :disabled="registryLoading" class="gap-2" @click="loadRegistry">
            <LoaderCircle v-if="registryLoading" class="h-4 w-4 animate-spin" />
            <RefreshCw v-else class="h-4 w-4" />
            刷新
          </Button>
        </div>
      </div>
    </section>

    <!-- ── Registry Error ──────────────────────────────────────────── -->
    <div v-if="registryError" class="flex items-start gap-3 rounded-xl border border-rose-400/20 bg-rose-400/[0.06] p-4 text-sm leading-6 text-rose-100/90">
      <CircleAlert class="mt-0.5 h-4 w-4 shrink-0" />
      <div>
        <p class="font-medium">无法加载工具注册表</p>
        <p class="mt-1">{{ registryError }}</p>
      </div>
    </div>

    <template v-if="registry">
      <!-- ── Risk Summary ──────────────────────────────────────────── -->
      <section class="grid gap-3 sm:grid-cols-3">
        <article class="rounded-xl border border-cyan-400/20 bg-cyan-400/[0.04] p-4">
          <div class="flex items-center justify-between gap-3">
            <span class="text-sm text-muted-foreground">只读工具</span>
            <Eye class="h-4 w-4 text-cyan-200" />
          </div>
          <p class="mt-3 text-2xl font-semibold tabular-nums">{{ riskSummary?.read_only ?? 0 }}</p>
          <p class="mt-1 text-xs text-muted-foreground">仅读取知识库或系统信息，无副作用</p>
        </article>
        <article class="rounded-xl border border-amber-400/20 bg-amber-400/[0.04] p-4">
          <div class="flex items-center justify-between gap-3">
            <span class="text-sm text-muted-foreground">读写工具</span>
            <FileWarning class="h-4 w-4 text-amber-200" />
          </div>
          <p class="mt-3 text-2xl font-semibold tabular-nums">{{ riskSummary?.read_write ?? 0 }}</p>
          <p class="mt-1 text-xs text-muted-foreground">可能修改数据，必须走人工审批</p>
        </article>
        <article class="rounded-xl border border-violet-400/20 bg-violet-400/[0.04] p-4">
          <div class="flex items-center justify-between gap-3">
            <span class="text-sm text-muted-foreground">外部工具</span>
            <Globe class="h-4 w-4 text-violet-200" />
          </div>
          <p class="mt-3 text-2xl font-semibold tabular-nums">{{ riskSummary?.external ?? 0 }}</p>
          <p class="mt-1 text-xs text-muted-foreground">调用外部服务，需额外权限</p>
        </article>
      </section>

      <!-- ── Tool Registry Cards ───────────────────────────────────── -->
      <Card class="border-border bg-card/80">
        <CardHeader class="border-b border-border/70 p-5">
          <div class="flex items-center gap-2">
            <Search class="h-4 w-4 text-primary" />
            <div>
              <CardTitle class="text-base">已注册工具</CardTitle>
              <CardDescription class="mt-1">
                以下工具由 Python Tool Registry 在启动时注册。Agent 能否调用取决于版本门控（agent_version）和运行时的权限上下文。
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent class="grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-3">
          <article
            v-for="tool in registry.tools"
            :key="tool.name"
            class="flex flex-col rounded-xl border border-border bg-muted/20 p-4"
          >
            <!-- Header -->
            <div class="flex items-start justify-between gap-3">
              <p class="text-sm font-semibold">{{ tool.name }}</p>
              <div class="flex shrink-0 items-center gap-1.5">
                <Badge variant="outline" :class="riskMeta(tool.risk_level).class">
                  {{ riskMeta(tool.risk_level).label }}
                </Badge>
                <Badge variant="outline" :class="statusMeta(tool.status).class">
                  {{ statusMeta(tool.status).label }}
                </Badge>
              </div>
            </div>

            <!-- Description -->
            <p class="mt-2 text-sm leading-5 text-muted-foreground">{{ tool.description }}</p>

            <!-- Details -->
            <div class="mt-3 space-y-1.5">
              <div class="flex items-center gap-2 text-xs text-muted-foreground">
                <Clock class="h-3 w-3" />
                <span>超时 {{ tool.timeout_seconds }}s</span>
              </div>
              <div class="flex items-start gap-2 text-xs text-muted-foreground">
                <Shield class="mt-0.5 h-3 w-3 shrink-0" />
                <span v-if="tool.required_permissions.length">
                  {{ tool.required_permissions.map(permLabel).join('、') }}
                </span>
                <span v-else class="italic">无额外权限要求</span>
              </div>
            </div>

            <!-- Input params (collapsed list) -->
            <div v-if="Object.keys(tool.input_schema.properties).length" class="mt-3 border-t border-border/60 pt-3">
              <p class="mb-1.5 text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">参数</p>
              <div class="space-y-1">
                <div
                  v-for="(prop, key) in tool.input_schema.properties"
                  :key="key"
                  class="flex items-baseline gap-2 text-xs"
                >
                  <code class="rounded bg-muted px-1 py-px font-mono text-[11px] text-foreground/80">{{ key }}</code>
                  <span class="text-muted-foreground">{{ prop.description || prop.type }}</span>
                  <span v-if="tool.input_schema.required.includes(key as string)" class="text-amber-300/80">必填</span>
                </div>
              </div>
            </div>

            <!-- Agent version badge -->
            <p class="mt-auto pt-3 text-[11px] text-muted-foreground">
              Agent 版本门控：{{ tool.agent_version === '1.0' ? 'V1 默认可用' : tool.agent_version === '1.1' ? 'V1.1（需审批配置开启）' : '仅 MCP / 开发中' }}
            </p>
          </article>
        </CardContent>
      </Card>

      <!-- ── Registry Notice ───────────────────────────────────────── -->
      <div v-if="registry.notice" class="flex items-start gap-3 rounded-xl border border-amber-400/20 bg-amber-400/[0.06] p-4 text-sm leading-6 text-amber-100/90">
        <AlertTriangle class="mt-0.5 h-4 w-4 shrink-0" />
        <div>
          <p class="font-medium">工具注册表提示</p>
          <p class="mt-1">{{ registry.notice }}</p>
        </div>
      </div>
    </template>

    <div v-else-if="!registryError" class="flex min-h-72 items-center justify-center rounded-2xl border border-border bg-card/60">
      <LoaderCircle class="h-6 w-6 animate-spin text-primary" />
    </div>

    <!-- ── Recent Calls ────────────────────────────────────────────── -->
    <Card class="border-border bg-card/80">
      <CardHeader class="border-b border-border/70 p-5">
        <div class="flex items-center justify-between gap-3">
          <div class="flex items-center gap-2">
            <Radio class="h-4 w-4 text-primary" />
            <div>
              <CardTitle class="text-base">最近调用记录</CardTitle>
              <CardDescription class="mt-1">
                来自 Agent 任务的工具调用步骤，按时间倒序。包含所属任务、耗时和成功/失败状态。
              </CardDescription>
            </div>
          </div>
          <Button variant="outline" size="sm" :disabled="callsLoading" class="gap-2 shrink-0" @click="loadCalls">
            <LoaderCircle v-if="callsLoading" class="h-4 w-4 animate-spin" />
            <RefreshCw v-else class="h-4 w-4" />
            刷新
          </Button>
        </div>
      </CardHeader>
      <CardContent class="p-0">
        <!-- Loading -->
        <div v-if="callsLoading && !calls" class="flex min-h-48 items-center justify-center">
          <LoaderCircle class="h-6 w-6 animate-spin text-primary" />
        </div>

        <!-- Error -->
        <div v-else-if="callsError" class="flex items-start gap-3 p-5 text-sm text-rose-100/90">
          <CircleAlert class="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <p class="font-medium">无法加载调用记录</p>
            <p class="mt-1">{{ callsError }}</p>
          </div>
        </div>

        <!-- Empty -->
        <div v-else-if="!calls?.calls.length" class="flex flex-col items-center justify-center py-14 text-center">
          <Radio class="h-8 w-8 text-muted-foreground/50" />
          <p class="mt-3 text-sm font-medium">暂无工具调用记录</p>
          <p class="mt-1 text-xs text-muted-foreground">Agent 执行任务并调用工具后，记录会出现在这里。</p>
        </div>

        <!-- Table -->
        <div v-else class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b border-border text-left text-xs font-medium uppercase tracking-[0.06em] text-muted-foreground">
                <th class="px-5 py-3">工具</th>
                <th class="px-5 py-3 hidden sm:table-cell">所属任务</th>
                <th class="px-5 py-3">耗时</th>
                <th class="px-5 py-3">结果</th>
                <th class="px-5 py-3 hidden md:table-cell">时间</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="call in calls.calls"
                :key="call.id"
                class="border-b border-border/60 transition-colors hover:bg-muted/30"
              >
                <!-- Tool name -->
                <td class="px-5 py-3">
                  <span class="font-mono text-xs font-medium">{{ call.tool_name }}</span>
                </td>

                <!-- Task context -->
                <td class="px-5 py-3 hidden sm:table-cell">
                  <div class="max-w-[20rem]">
                    <p class="truncate text-xs">{{ truncate(call.task.query, 60) }}</p>
                    <p class="mt-0.5 text-[11px] text-muted-foreground">
                      {{ taskStatusLabel(call.task.status) }} · 任务 #{{ call.task.id }}
                    </p>
                  </div>
                </td>

                <!-- Duration -->
                <td class="px-5 py-3 font-mono text-xs tabular-nums text-muted-foreground">
                  {{ formatMs(call.duration_ms) }}
                </td>

                <!-- Result -->
                <td class="px-5 py-3">
                  <div class="flex items-center gap-1.5">
                    <CheckCircle2 v-if="call.success" class="h-4 w-4 text-emerald-300" />
                    <XCircle v-else class="h-4 w-4 text-rose-300" />
                    <span class="text-xs">{{ call.success ? '成功' : '失败' }}</span>
                  </div>
                  <p v-if="!call.success && call.error_summary" class="mt-1 max-w-[16rem] truncate text-[11px] text-rose-200/70">
                    {{ truncate(call.error_summary, 40) }}
                  </p>
                </td>

                <!-- Time -->
                <td class="px-5 py-3 hidden md:table-cell text-xs text-muted-foreground whitespace-nowrap">
                  {{ formatTime(call.created_at) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Footer -->
        <div v-if="calls?.calls.length" class="flex items-center justify-between border-t border-border px-5 py-3 text-xs text-muted-foreground">
          <span>共 {{ calls.total }} 条调用记录{{ calls.has_more ? '，显示最近 ' + calls.calls.length + ' 条' : '' }}</span>
          <span v-if="calls.has_more" class="text-muted-foreground/60">仅展示最近记录，更多历史请在「Agent 任务」中查看</span>
        </div>
      </CardContent>
    </Card>

    <!-- ── Security Notice ──────────────────────────────────────────── -->
    <Card class="border-primary/20 bg-primary/[0.055]">
      <CardHeader class="p-5 pb-3">
        <div class="flex items-center gap-2">
          <ShieldAlert class="h-4 w-4 text-primary" />
          <CardTitle class="text-base">安全边界</CardTitle>
        </div>
      </CardHeader>
      <CardContent class="space-y-3 p-5 pt-2 text-sm leading-6 text-muted-foreground">
        <p>此页面仅展示工具元数据与历史调用记录，<strong class="text-foreground/80">不提供工具执行入口</strong>。</p>
        <p>读写类工具（risk_level = read_write）必须通过 Agent 任务页的审批流程才能执行，前端无法绕过。</p>
        <p>工具列表来自 Python Tool Registry 的动态注册，前端不写死任何工具定义。新增工具只需在 Python 端注册即可在此页可见。</p>
      </CardContent>
    </Card>
  </div>
</template>
