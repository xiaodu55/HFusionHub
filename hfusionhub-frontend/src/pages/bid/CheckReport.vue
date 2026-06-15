<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import * as bidApi from '@/api/bid'
import type { BidCheckReport } from '@/api/bid'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { AlertOctagon, CheckCheck, FileSearch, Loader2, ShieldAlert, ShieldCheck, Wrench } from 'lucide-vue-next'
import { formatDateTime } from '@/utils/date'
import { useToast } from '@/composables/useToast'
import EmptyState from '@/components/EmptyState.vue'
import LoadingSkeleton from '@/components/LoadingSkeleton.vue'
import ErrorState from '@/components/ErrorState.vue'

const props = defineProps<{ projectId: number }>()
const toast = useToast()

const reports = ref<BidCheckReport[]>([])
const loading = ref(false)
const loadError = ref(false)
const checking = ref(false)

const SEVERITY_LABELS: Record<BidCheckReport['severity'], string> = {
  critical: '严重',
  warning: '警告',
  info: '提示',
}

const SEVERITY_CLASS: Record<BidCheckReport['severity'], string> = {
  critical: 'bg-red-100 text-red-700',
  warning: 'bg-amber-50 text-amber-700 dark:bg-amber-400/15 dark:text-amber-300',
  info: 'bg-slate-50 text-slate-600 dark:bg-slate-400/15 dark:text-slate-300',
}

const STATUS_LABELS: Record<BidCheckReport['status'], string> = {
  open: '待处理',
  confirmed: '已确认',
  fixed: '已修复',
}

const STATUS_CLASS: Record<BidCheckReport['status'], string> = {
  open: 'bg-red-50 text-red-600',
  confirmed: 'bg-amber-50 text-amber-700',
  fixed: 'bg-emerald-50 text-emerald-700',
}

const CATEGORY_LABELS: Record<string, string> = {
  disqualification: '废标条款',
  substantive: '实质性响应',
  format: '格式要求',
  bond: '保证金',
  deadline: '截止/开标',
  qualification: '资质文件',
  technical: '技术方案',
}

const summary = computed(() => ({
  total: reports.value.length,
  critical: reports.value.filter(r => r.severity === 'critical').length,
  warning: reports.value.filter(r => r.severity === 'warning').length,
  info: reports.value.filter(r => r.severity === 'info').length,
}))

/** evidence 存 JSON 数组字符串，拆成可展示的证据引用 */
const parseEvidence = (report: BidCheckReport): string[] => {
  if (!report.evidence) return []
  const raw = report.evidence
  try {
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) return parsed.map(String)
  } catch {
    /* 单值字符串 */
  }
  return raw.split(',').map(s => s.trim()).filter(Boolean)
}

const loadReports = async () => {
  loading.value = true
  loadError.value = false
  try {
    const res = await bidApi.listBidCheckReports(props.projectId)
    reports.value = res.data
  } catch (error) {
    loadError.value = true
    toast.error(error instanceof Error ? error.message : '加载自检报告失败')
  } finally {
    loading.value = false
  }
}

const runCheck = async () => {
  checking.value = true
  try {
    const res = await bidApi.runBidCheck(props.projectId)
    const s = res.data
    toast.success(
      `自检完成：共 ${s.total} 项，其中严重 ${s.critical}、警告 ${s.warning}、提示 ${s.info}`,
    )
    await loadReports()
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '自检失败')
  } finally {
    checking.value = false
  }
}

const updateReportStatus = async (report: BidCheckReport, status: BidCheckReport['status']) => {
  try {
    await bidApi.updateBidCheckReportStatus(report.id, status)
    report.status = status
    toast.success(status === 'fixed' ? '已标记修复' : '已确认该风险')
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '更新报告状态失败')
  }
}

onMounted(loadReports)
</script>

<template>
  <div>
    <!-- 自检入口 + 统计 -->
    <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
      <p class="text-sm text-muted-foreground">
        对当前标书草稿逐节执行废标风险自检（保证金 / 截止开标 / 废标条款 / ★实质性 / 评分点），
        critical 级风险必须人工确认后才能放行。
      </p>
      <Button :disabled="checking" @click="runCheck">
        <Loader2 v-if="checking" class="mr-1 h-4 w-4 animate-spin" />
        <ShieldCheck v-else class="mr-1 h-4 w-4" />
        {{ checking ? '自检中…' : '执行废标自检' }}
      </Button>
    </div>

    <div v-if="reports.length" class="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
      <div class="rounded-lg border border-border bg-card p-4 text-center">
        <p class="text-2xl font-bold">{{ summary.total }}</p>
        <p class="text-xs text-muted-foreground">发现项</p>
      </div>
      <div class="rounded-lg border border-red-400/60 bg-red-50 p-4 text-center dark:border-red-400/25 dark:bg-red-400/10">
        <p class="text-2xl font-bold text-red-600">{{ summary.critical }}</p>
        <p class="text-xs text-red-500">严重</p>
      </div>
      <div class="rounded-lg border border-amber-400/60 bg-amber-50 p-4 text-center dark:border-amber-400/25 dark:bg-amber-400/10">
        <p class="text-2xl font-bold text-amber-600">{{ summary.warning }}</p>
        <p class="text-xs text-amber-500">警告</p>
      </div>
      <div class="rounded-lg border border-slate-200 bg-slate-50 p-4 text-center">
        <p class="text-2xl font-bold text-slate-500">{{ summary.info }}</p>
        <p class="text-xs text-slate-400">提示</p>
      </div>
    </div>

    <LoadingSkeleton v-if="loading" type="card" :count="3" />
    <ErrorState
      v-else-if="loadError"
      title="加载失败"
      message="无法加载自检报告，请稍后重试"
      @retry="loadReports"
    />
    <EmptyState
      v-else-if="reports.length === 0"
      :icon="FileSearch"
      title="尚无自检报告"
      description="点击「执行废标自检」，AI 将逐节对照招标文件检查废标风险"
    />

    <div v-else class="space-y-3">
      <!-- critical 优先分组 -->
      <template v-for="severity in (['critical', 'warning', 'info'] as const)" :key="severity">
        <div
          v-for="report in reports.filter(r => r.severity === severity)"
          :key="report.id"
          class="rounded-lg border p-4"
          :class="{
            'border-red-400/60 bg-red-50/40': severity === 'critical',
            'border-amber-400/60 bg-amber-50/40': severity === 'warning',
            'border-border bg-card': severity === 'info',
          }"
        >
          <div class="flex items-start justify-between gap-3">
            <div class="flex min-w-0 items-start gap-3">
              <AlertOctagon
                v-if="severity === 'critical'"
                class="mt-0.5 h-5 w-5 shrink-0 text-red-500"
              />
              <ShieldAlert v-else-if="severity === 'warning'" class="mt-0.5 h-5 w-5 shrink-0 text-amber-500" />
              <Wrench v-else class="mt-0.5 h-5 w-5 shrink-0 text-slate-400" />
              <div class="min-w-0">
                <div class="mb-1 flex flex-wrap items-center gap-2">
                  <Badge :class="SEVERITY_CLASS[report.severity]">
                    {{ SEVERITY_LABELS[report.severity] }}
                  </Badge>
                  <Badge variant="outline" class="text-xs">
                    {{ CATEGORY_LABELS[report.category] || report.category }}
                  </Badge>
                  <span v-if="report.sectionKey" class="text-xs text-muted-foreground">
                    {{ bidApi.BID_SECTION_LABELS[report.sectionKey] || report.sectionKey }}
                  </span>
                  <Badge :class="STATUS_CLASS[report.status]">{{ STATUS_LABELS[report.status] }}</Badge>
                </div>
                <p class="break-words text-sm font-medium">{{ report.finding }}</p>
                <p v-if="report.suggestedFix" class="mt-1.5 break-words text-xs text-muted-foreground">
                  建议：{{ report.suggestedFix }}
                </p>
                <div v-if="parseEvidence(report).length" class="mt-2 flex flex-wrap gap-1">
                  <span
                    v-for="chunkId in parseEvidence(report)"
                    :key="chunkId"
                    class="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground"
                    :title="`证据来源：${chunkId}`"
                  >
                    {{ chunkId }}
                  </span>
                </div>
                <p class="mt-1.5 text-[11px] text-muted-foreground">
                  {{ formatDateTime(report.createdAt) }}
                </p>
              </div>
            </div>
            <div class="flex shrink-0 items-center gap-2">
              <Button
                v-if="report.status === 'open'"
                variant="outline"
                size="sm"
                @click="updateReportStatus(report, 'confirmed')"
              >
                确认风险
              </Button>
              <Button
                v-if="report.status !== 'fixed'"
                size="sm"
                @click="updateReportStatus(report, 'fixed')"
              >
                <CheckCheck class="mr-1 h-4 w-4" /> 已修复
              </Button>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>
