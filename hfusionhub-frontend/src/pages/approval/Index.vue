<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  AlertTriangle,
  CheckCircle2,
  CheckCircle,
  Clock3,
  FileText,
  Fingerprint,
  Hourglass,
  Inbox,
  RefreshCw,
  Search,
  ShieldCheck,
  ShieldAlert,
  ShieldQuestion,
  XCircle,
} from 'lucide-vue-next'
import * as approvalApi from '@/api/approval'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import LoadingSkeleton from '@/components/LoadingSkeleton.vue'
import { useToast } from '@/composables/useToast'

type StatusTone = 'success' | 'danger' | 'warning' | 'progress' | 'neutral'

const route = useRoute()
const router = useRouter()
const toast = useToast()

const loading = ref(false)
const approving = ref(false)
const approvals = ref<approvalApi.AgentApproval[]>([])
const statusFilter = ref<approvalApi.ApprovalStatus | 'all'>('all')
const riskFilter = ref('all')
const selected = ref<approvalApi.AgentApproval | null>(null)
const dialogOpen = ref(false)
const rejectReason = ref('')
const connected = ref(false)
const reconnectAttempts = ref(0)
let closeStream: (() => void) | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null

const taskFilter = computed(() => {
  const raw = route.query.taskId
  const id = Number(raw)
  return raw && Number.isFinite(id) ? id : null
})

const statusFilters: { value: approvalApi.ApprovalStatus | 'all'; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'pending', label: '待审批' },
  { value: 'approved', label: '已批准' },
  { value: 'denied', label: '已拒绝' },
  { value: 'expired', label: '已过期' },
  { value: 'executed', label: '已执行' },
  { value: 'failed', label: '执行失败' },
]

const riskFilters = [
  { value: 'all', label: '全部风险' },
  { value: 'read_only', label: '只读' },
  { value: 'read_write', label: '读写' },
  { value: 'external', label: '外部调用' },
]

const statusMeta = (status?: string) => {
  const normalized = (status || '').toUpperCase()
  if (['PENDING', 'WAITING'].includes(normalized)) return { label: '待审批', tone: 'warning' as StatusTone }
  if (['APPROVED'].includes(normalized)) return { label: '已批准', tone: 'progress' as StatusTone }
  if (['DENIED', 'REJECTED'].includes(normalized)) return { label: '已拒绝', tone: 'danger' as StatusTone }
  if (['EXPIRED'].includes(normalized)) return { label: '已过期', tone: 'neutral' as StatusTone }
  if (['EXECUTED'].includes(normalized)) return { label: '已执行', tone: 'success' as StatusTone }
  if (['FAILED'].includes(normalized)) return { label: '执行失败', tone: 'danger' as StatusTone }
  return { label: status || '未知状态', tone: 'neutral' as StatusTone }
}

const statusBadgeClass = (status?: string) => {
  const tone = statusMeta(status).tone
  return {
    success: 'border-emerald-400/25 bg-emerald-400/10 text-emerald-300',
    danger: 'border-rose-400/25 bg-rose-400/10 text-rose-300',
    warning: 'border-amber-400/25 bg-amber-400/10 text-amber-200',
    progress: 'border-cyan-400/25 bg-cyan-400/10 text-cyan-200',
    neutral: 'border-white/10 bg-white/5 text-muted-foreground',
  }[tone]
}

const riskLabel = (risk?: string) => {
  if (risk === 'read_write') return '读写'
  if (risk === 'external') return '外部调用'
  return '只读'
}

const riskIcon = (risk?: string) => {
  if (risk === 'read_write') return ShieldAlert
  if (risk === 'external') return AlertTriangle
  return ShieldQuestion
}

const pendingCount = computed(() => approvals.value.filter((a) => a.status === 'pending').length)
const executedCount = computed(() => approvals.value.filter((a) => a.status === 'executed').length)
const deniedCount = computed(() => approvals.value.filter((a) => a.status === 'denied').length)

const filteredApprovals = computed(() =>
  approvals.value.filter((a) => {
    if (statusFilter.value !== 'all' && a.status !== statusFilter.value) return false
    if (riskFilter.value !== 'all' && (a.riskLevel || 'read_only') !== riskFilter.value) return false
    if (taskFilter.value != null && a.taskId !== taskFilter.value) return false
    return true
  }),
)

const isPending = computed(() => selected.value?.status === 'pending')
const isExpired = computed(() => selected.value?.status === 'expired')
const canDecide = computed(() => isPending.value && !approving.value)

const formatDate = (value?: string) => (value ? value.replace('T', ' ').slice(0, 16) : '—')
const formatExpires = (value?: string) => (value ? value.replace('T', ' ').slice(0, 16) : '—')
const isExpiredRow = (a: approvalApi.AgentApproval) =>
  a.status === 'pending' && a.expiresAt != null && new Date(a.expiresAt).getTime() < Date.now()

const load = async () => {
  loading.value = true
  try {
    if (taskFilter.value != null) {
      // Audit view: load ALL approvals for this task (pending, terminal, etc.)
      const res = await approvalApi.listApprovalsByTask(taskFilter.value)
      approvals.value = res.data
    } else {
      // Default view: current user's pending approvals.
      const res = await approvalApi.listPendingApprovals()
      const pending = res.data
      const all: approvalApi.AgentApproval[] = []
      const seen = new Set<number>()
      for (const item of [...approvals.value, ...pending]) {
        if (!seen.has(item.id)) {
          seen.add(item.id)
          all.push(item)
        }
      }
      approvals.value = all
    }
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '加载审批列表失败')
  } finally {
    loading.value = false
  }
}

const upsertApproval = (incoming: approvalApi.AgentApproval) => {
  const idx = approvals.value.findIndex((a) => a.id === incoming.id)
  if (idx >= 0) approvals.value[idx] = incoming
  else approvals.value.unshift(incoming)
}

const subscribe = () => {
  closeStream?.()
  connected.value = false
  closeStream = approvalApi.subscribeApprovalStream({
    onSnapshot: (snapshot) => {
      connected.value = true
      reconnectAttempts.value = 0
      if (taskFilter.value == null) {
        approvals.value = snapshot
        return
      }
      // The user-scoped SSE snapshot must not replace the task audit query,
      // which includes terminal approvals for the requested task.
      snapshot
        .filter((approval) => approval.taskId === taskFilter.value)
        .forEach(upsertApproval)
    },
    onApproval: (approval) => {
      connected.value = true
      reconnectAttempts.value = 0
      upsertApproval(approval)
      if (selected.value?.id === approval.id) selected.value = approval
      const meta = statusMeta(approval.status)
      if (['denied', 'expired', 'executed', 'failed'].includes(approval.status)) {
        toast.success(`审批 #${approval.approvalId.slice(0, 8)} 状态已更新为「${meta.label}」`)
      }
    },
    onError: () => {
      connected.value = false
      scheduleReconnect()
    },
  })
}

const scheduleReconnect = () => {
  if (reconnectTimer) return
  reconnectAttempts.value += 1
  const delay = Math.min(1000 * reconnectAttempts.value, 8000)
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    if (connected.value) return
    subscribe()
  }, delay)
}

const open = (approval: approvalApi.AgentApproval) => {
  selected.value = approval
  rejectReason.value = ''
  dialogOpen.value = true
}

const decide = async (decision: 'approved' | 'denied') => {
  const approval = selected.value
  if (!approval || !canDecide.value || !approval.taskId) return
  if (decision === 'denied' && !rejectReason.value.trim()) {
    toast.error('拒绝时必须填写原因')
    return
  }
  approving.value = true
  try {
    const res = await approvalApi.decideApproval(approval.taskId, {
      approvalId: approval.approvalId,
      decision,
      reason: decision === 'denied' ? rejectReason.value.trim() : undefined,
    })
    upsertApproval(res.data)
    if (selected.value?.id === res.data.id) selected.value = res.data
    dialogOpen.value = false
    toast.success(decision === 'approved' ? '已批准，工具将执行一次' : '已拒绝工具调用')
    await load()
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '提交审批决定失败')
  } finally {
    approving.value = false
  }
}

const auditTask = (taskId?: number) => {
  if (!taskId) return
  dialogOpen.value = false
  router.push({ path: '/approvals', query: { taskId } })
}

const clearTaskFilter = () => {
  router.push('/approvals')
}

watch(
  () => route.query.taskId,
  async () => {
    statusFilter.value = 'all'
    riskFilter.value = 'all'
    await load()
  },
)

onMounted(async () => {
  await load()
  subscribe()
})

onUnmounted(() => {
  closeStream?.()
  if (reconnectTimer) clearTimeout(reconnectTimer)
})
</script>

<template>
  <div class="space-y-6 pb-4">
    <section class="overflow-hidden rounded-2xl border border-border bg-card/80 shadow-[0_18px_45px_rgba(0,0,0,0.18)]">
      <div class="flex flex-col gap-5 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
        <div class="flex gap-4">
          <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-primary/25 bg-primary/10 text-primary">
            <Fingerprint class="h-5 w-5" />
          </div>
          <div>
            <p class="text-xs font-medium tracking-[0.16em] text-primary/90">HUMAN IN THE LOOP</p>
            <h2 class="mt-1 text-2xl font-semibold tracking-tight">工具审批中心</h2>
            <p class="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">高风险工具调用在真正执行前会先征求你的确认。这里只显示与你相关的审批；状态会通过实时流自动刷新。</p>
          </div>
        </div>
        <div class="flex items-center gap-3">
          <span class="flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs"
            :class="connected ? 'border-emerald-400/25 bg-emerald-400/10 text-emerald-300' : 'border-white/10 bg-white/5 text-muted-foreground'">
            <span class="h-1.5 w-1.5 rounded-full" :class="connected ? 'bg-emerald-400' : 'bg-muted-foreground'" />
            {{ connected ? '实时同步中' : '连接已断开，正在重连…' }}
          </span>
          <Button :disabled="loading" class="shrink-0 gap-2" @click="load">
            <RefreshCw class="h-4 w-4" :class="loading && 'animate-spin'" />
            刷新
          </Button>
        </div>
      </div>
    </section>

    <section class="grid gap-3 sm:grid-cols-3 xl:grid-cols-5">
      <div class="rounded-xl border border-amber-400/15 bg-amber-400/[0.04] p-4">
        <p class="text-sm text-muted-foreground">待审批</p>
        <div class="mt-2 flex items-end justify-between"><strong class="text-2xl text-amber-300">{{ pendingCount }}</strong><Hourglass class="h-4 w-4 text-amber-300" /></div>
      </div>
      <div class="rounded-xl border border-cyan-400/15 bg-cyan-400/[0.04] p-4">
        <p class="text-sm text-muted-foreground">已批准待执行</p>
        <div class="mt-2 flex items-end justify-between"><strong class="text-2xl text-cyan-200">{{ approvals.filter(a => a.status === 'approved').length }}</strong><ShieldCheck class="h-4 w-4 text-cyan-200" /></div>
      </div>
      <div class="rounded-xl border border-emerald-400/15 bg-emerald-400/[0.04] p-4">
        <p class="text-sm text-muted-foreground">已执行</p>
        <div class="mt-2 flex items-end justify-between"><strong class="text-2xl text-emerald-300">{{ executedCount }}</strong><CheckCircle2 class="h-4 w-4 text-emerald-300" /></div>
      </div>
      <div class="rounded-xl border border-rose-400/15 bg-rose-400/[0.04] p-4">
        <p class="text-sm text-muted-foreground">已拒绝</p>
        <div class="mt-2 flex items-end justify-between"><strong class="text-2xl text-rose-300">{{ deniedCount }}</strong><XCircle class="h-4 w-4 text-rose-300" /></div>
      </div>
      <div class="rounded-xl border border-border bg-card/70 p-4">
        <p class="text-sm text-muted-foreground">全部记录</p>
        <div class="mt-2 flex items-end justify-between"><strong class="text-2xl">{{ approvals.length }}</strong><Inbox class="h-4 w-4 text-muted-foreground" /></div>
      </div>
    </section>

    <Card class="overflow-hidden border-border bg-card/80">
      <CardHeader class="border-b border-border/70 p-5">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle class="text-base">审批记录</CardTitle>
            <CardDescription class="mt-1">
              {{ taskFilter != null ? `仅显示任务 #${taskFilter} 的审批` : '选择一条记录查看详情并作出决定' }}
              <button v-if="taskFilter != null" class="ml-2 text-xs text-primary underline" @click="clearTaskFilter">清除筛选</button>
            </CardDescription>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <div class="flex gap-1 overflow-x-auto pb-1">
              <button
                v-for="filter in statusFilters"
                :key="filter.value"
                class="shrink-0 rounded-md px-2.5 py-1.5 text-xs transition-colors"
                :class="statusFilter === filter.value ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted hover:text-foreground'"
                @click="statusFilter = filter.value"
              >
                {{ filter.label }}
              </button>
            </div>
            <div class="flex gap-1 overflow-x-auto pb-1">
              <button
                v-for="filter in riskFilters"
                :key="filter.value"
                class="shrink-0 rounded-md px-2.5 py-1.5 text-xs transition-colors"
                :class="riskFilter === filter.value ? 'bg-primary/80 text-primary-foreground' : 'text-muted-foreground hover:bg-muted hover:text-foreground'"
                @click="riskFilter = filter.value"
              >
                {{ filter.label }}
              </button>
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent class="max-h-[42rem] space-y-2 overflow-y-auto p-3">
        <LoadingSkeleton v-if="loading" type="list" :count="5" />
        <div v-else-if="!filteredApprovals.length" class="flex min-h-72 flex-col items-center justify-center px-6 text-center">
          <Search class="h-9 w-9 text-muted-foreground/60" />
          <p class="mt-4 font-medium">没有匹配的审批记录</p>
          <p class="mt-1 text-sm leading-6 text-muted-foreground">当高风险工具调用等待确认时，会实时出现在这里。</p>
        </div>
        <button
          v-for="approval in filteredApprovals"
          :key="approval.id"
          class="w-full rounded-lg border p-3 text-left transition-colors hover:bg-muted/40"
          :class="isExpiredRow(approval) ? 'border-rose-400/30' : 'border-border/80'"
          @click="open(approval)"
        >
          <div class="flex items-center justify-between gap-3">
            <div class="flex min-w-0 items-center gap-2">
              <component :is="riskIcon(approval.riskLevel)" class="h-4 w-4 shrink-0 text-muted-foreground" />
              <span class="truncate font-medium">{{ approval.toolName || '未知工具' }}</span>
              <Badge variant="outline" class="shrink-0 border-primary/25 bg-primary/10 text-primary">{{ riskLabel(approval.riskLevel) }}</Badge>
            </div>
            <span class="shrink-0 rounded-md border px-2 py-0.5 text-xs" :class="statusBadgeClass(approval.status)">
              {{ statusMeta(approval.status).label }}
            </span>
          </div>
          <p class="mt-2 truncate font-mono text-xs text-muted-foreground">{{ approval.argumentsSummary || '—' }}</p>
          <div class="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
            <span class="flex items-center gap-1"><Clock3 class="h-3 w-3" />{{ formatDate(approval.createdAt) }}</span>
            <span v-if="approval.traceId" class="flex min-w-0 items-center gap-1 break-all"><Fingerprint class="h-3 w-3 shrink-0" />trace {{ approval.traceId }}</span>
            <span v-if="isExpiredRow(approval)" class="text-rose-400">已超时，等待过期回收</span>
          </div>
        </button>
      </CardContent>
    </Card>

    <Dialog v-model:open="dialogOpen">
      <DialogContent class="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle class="flex items-center gap-2">
            <component :is="riskIcon(selected?.riskLevel)" class="h-5 w-5 text-primary" />
            审批详情
          </DialogTitle>
          <DialogDescription>确认工具调用内容后再决定；批准后工具只会执行一次。</DialogDescription>
        </DialogHeader>

        <div v-if="selected" class="space-y-4">
          <div class="grid grid-cols-2 gap-3">
            <div>
              <Label>工具</Label>
              <p class="mt-1 flex items-center gap-2"><FileText class="h-4 w-4 text-muted-foreground" />{{ selected.toolName }}</p>
            </div>
            <div>
              <Label>风险等级</Label>
              <p class="mt-1">
                <Badge variant="outline" class="border-primary/25 bg-primary/10 text-primary">{{ riskLabel(selected.riskLevel) }}</Badge>
              </p>
            </div>
            <div>
              <Label>创建时间</Label>
              <p class="mt-1 text-sm">{{ formatDate(selected.createdAt) }}</p>
            </div>
            <div>
              <Label>决策截止时间</Label>
              <p class="mt-1 text-sm" :class="isExpired ? 'text-rose-400' : ''">{{ formatExpires(selected.expiresAt) }}</p>
            </div>
            <div>
              <Label>审批编号</Label>
              <p class="mt-1 font-mono text-xs text-muted-foreground">{{ selected.approvalId }}</p>
            </div>
            <div>
              <Label>Trace ID</Label>
              <p class="mt-1 font-mono text-xs text-muted-foreground">{{ selected.traceId || '—' }}</p>
            </div>
          </div>

          <div>
            <Label>参数摘要（已脱敏）</Label>
            <pre class="mt-1 max-h-40 overflow-auto rounded-lg border border-border/80 bg-muted/40 p-3 font-mono text-xs leading-5 text-muted-foreground">{{ selected.argumentsSummary || '—' }}</pre>
          </div>

          <div v-if="selected.reason">
            <Label>决定原因</Label>
            <p class="mt-1 rounded-lg border border-border/80 bg-muted/40 p-3 text-sm">{{ selected.reason }}</p>
          </div>

          <div v-if="isPending">
            <Label>拒绝原因（拒绝时必填）</Label>
            <Input v-model="rejectReason" class="mt-1" placeholder="例如：参数不符合预期，需要修改后重新申请" />
          </div>

          <div v-if="isExpired" class="rounded-lg border border-rose-400/30 bg-rose-400/10 p-3 text-sm text-rose-300">
            该审批已过期，无法再作出决定。过期审批会被系统自动回收，你可以重新发起请求。
          </div>
          <div v-if="selected.status === 'approved'" class="rounded-lg border border-cyan-400/30 bg-cyan-400/10 p-3 text-sm text-cyan-200">
            已批准，一次性执行令牌已签发。工具只会执行一次，重复调用会被拒绝。
          </div>
          <div v-if="selected.status === 'executed'" class="rounded-lg border border-emerald-400/30 bg-emerald-400/10 p-3 text-sm text-emerald-300">
            已执行完成。你可以在「Agent 任务」中查看该任务的完整轨迹。
          </div>
        </div>

        <DialogFooter class="gap-2 sm:justify-between">
          <div class="flex items-center gap-2">
            <Button v-if="selected?.taskId" variant="ghost" size="sm" @click="auditTask(selected.taskId)">
              查看任务审批记录
            </Button>
          </div>
          <div class="flex items-center gap-2">
            <Button v-if="isPending" variant="outline" :disabled="approving" @click="decide('denied')">
              <XCircle class="h-4 w-4" />拒绝
            </Button>
            <Button v-if="isPending" :disabled="approving" class="gap-2" @click="decide('approved')">
              <CheckCircle class="h-4 w-4" />{{ approving ? '提交中…' : '批准并执行一次' }}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
