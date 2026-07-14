<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Activity, BarChart3, CircleDollarSign, Database, RefreshCw, Zap } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { useToast } from '@/composables/useToast'
import * as analyticsApi from '@/api/analytics'
import type {
  AnalyticsCostDaily,
  AnalyticsEvalQuality,
  AnalyticsModelShare,
  AnalyticsOverview,
  AnalyticsRealtimeMetric,
  AnalyticsToolSuccess,
} from '@/api/analytics'

const toast = useToast()
const loading = ref(false)
const days = ref(7)
const overview = ref<AnalyticsOverview | null>(null)
const costDaily = ref<AnalyticsCostDaily[]>([])
const modelShare = ref<AnalyticsModelShare[]>([])
const toolSuccess = ref<AnalyticsToolSuccess[]>([])
const evalQuality = ref<AnalyticsEvalQuality[]>([])
const realtime = ref<AnalyticsRealtimeMetric[]>([])

const timeRanges = [{ label: '7 天', value: 7 }, { label: '14 天', value: 14 }, { label: '30 天', value: 30 }]
const REFRESH_INTERVAL_MS = 30_000
let refreshTimer: ReturnType<typeof setInterval> | null = null

/** 分析扩展包未启用时 ADS 表为空 —— 明确的空态而非报错 */
const analyticsEnabled = computed(() =>
  costDaily.value.length > 0 || modelShare.value.length > 0
  || realtime.value.length > 0 || toolSuccess.value.length > 0)

function formatCost(value: number | null | undefined) {
  const v = Number(value ?? 0)
  if (!Number.isFinite(v) || v === 0) return '$0'
  if (v >= 1) return `$${v.toFixed(2)}`
  return `$${v.toFixed(4).replace(/0+$/, '').replace(/\.$/, '')}`
}

function formatTokens(value: number | null | undefined) {
  const v = Number(value ?? 0)
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}M`
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)}K`
  return String(v)
}

function formatRate(rate: number | null | undefined) {
  return `${((Number(rate ?? 0)) * 100).toFixed(1)}%`
}

const maxDailyCost = computed(() =>
  Math.max(...costDaily.value.map(item => Number(item.costUsd ?? 0)), 0.0001))

/** 按步骤类型聚合近 N 天成功率 */
const toolSuccessAgg = computed(() => {
  const byType = new Map<string, { step: number; error: number }>()
  for (const row of toolSuccess.value) {
    const entry = byType.get(row.stepType) ?? { step: 0, error: 0 }
    entry.step += Number(row.stepCount ?? 0)
    entry.error += Number(row.errorCount ?? 0)
    byType.set(row.stepType, entry)
  }
  return [...byType.entries()]
    .map(([stepType, agg]) => ({
      stepType,
      stepCount: agg.step,
      errorCount: agg.error,
      successRate: agg.step > 0 ? 1 - agg.error / agg.step : 1,
    }))
    .sort((a, b) => a.successRate - b.successRate)
})

const evalQualityRows = computed(() =>
  [...evalQuality.value].sort((a, b) => b.statDate.localeCompare(a.statDate)).slice(0, 10))

async function loadAll() {
  loading.value = true
  try {
    const [overviewRes, costRes, shareRes, toolRes, evalRes, realtimeRes] = await Promise.all([
      analyticsApi.getOverview(days.value),
      analyticsApi.getCostDaily(days.value),
      analyticsApi.getModelShare(undefined),
      analyticsApi.getToolSuccess(days.value),
      analyticsApi.getEvalQuality(30),
      analyticsApi.getRealtime(60),
    ])
    overview.value = overviewRes.data
    costDaily.value = costRes.data ?? []
    modelShare.value = shareRes.data ?? []
    toolSuccess.value = toolRes.data ?? []
    evalQuality.value = evalRes.data ?? []
    realtime.value = realtimeRes.data ?? []
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '加载运营分析数据失败')
  } finally {
    loading.value = false
  }
}

function startAutoRefresh() {
  if (refreshTimer) return
  refreshTimer = setInterval(loadRealtime, REFRESH_INTERVAL_MS)
}

function stopAutoRefresh() {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

async function loadRealtime() {
  try {
    const res = await analyticsApi.getRealtime(60)
    realtime.value = res.data ?? []
  } catch {
    // 静默:轮询失败不打扰用户,下一次重试
  }
}

onMounted(() => {
  loadAll()
  startAutoRefresh()
})

onBeforeUnmount(stopAutoRefresh)
</script>

<template>
  <div class="space-y-6 p-6">
    <!-- 头部 -->
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="flex items-center gap-2">
        <BarChart3 class="h-6 w-6 text-primary" />
        <div>
          <h1 class="text-xl font-semibold">运营分析</h1>
          <p class="text-sm text-muted-foreground">
            HFusionData Analytics — 平台运营数仓(离线 Spark 日结 + 实时 Flink 指标)
          </p>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <div class="flex rounded-md border">
          <button
            v-for="range in timeRanges"
            :key="range.value"
            class="px-3 py-1.5 text-sm"
            :class="days === range.value ? 'bg-primary text-primary-foreground' : 'hover:bg-muted'"
            @click="days = range.value; loadAll()"
          >
            {{ range.label }}
          </button>
        </div>
        <Button variant="outline" size="sm" :disabled="loading" @click="loadAll">
          <RefreshCw class="mr-1 h-4 w-4" :class="{ 'animate-spin': loading }" />
          刷新
        </Button>
      </div>
    </div>

    <!-- 未启用空态 -->
    <div v-if="!loading && !analyticsEnabled" class="rounded-lg border border-dashed p-10 text-center">
      <Database class="mx-auto h-10 w-10 text-muted-foreground/50" />
      <p class="mt-3 font-medium">分析扩展包未启用或暂无数据</p>
      <p class="mt-1 text-sm text-muted-foreground">
        部署 docker-compose.analytics.yml 并执行日结管线后,此处展示租户用量/成本/质量分析。
        详见 docs/BIGDATA_ARCHITECTURE.md
      </p>
    </div>

    <template v-else>
      <!-- 概览卡片 -->
      <div class="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <div class="rounded-lg border p-4">
          <div class="flex items-center gap-2 text-sm text-muted-foreground">
            <Activity class="h-4 w-4" /> 近 {{ days }} 天调用
          </div>
          <p class="mt-2 text-2xl font-semibold">{{ (overview?.totalCalls ?? 0).toLocaleString() }}</p>
        </div>
        <div class="rounded-lg border p-4">
          <div class="flex items-center gap-2 text-sm text-muted-foreground">
            <Zap class="h-4 w-4" /> Token 用量
          </div>
          <p class="mt-2 text-2xl font-semibold">{{ formatTokens(overview?.totalTokens) }}</p>
        </div>
        <div class="rounded-lg border p-4">
          <div class="flex items-center gap-2 text-sm text-muted-foreground">
            <CircleDollarSign class="h-4 w-4" /> 累计成本
          </div>
          <p class="mt-2 text-2xl font-semibold">{{ formatCost(overview?.totalCostUsd) }}</p>
        </div>
        <div class="rounded-lg border p-4">
          <div class="flex items-center gap-2 text-sm text-muted-foreground">
            <Activity class="h-4 w-4" />
            实时速率(近 {{ overview?.realtime?.windowMinutes ?? 5 }} 分钟)
          </div>
          <p class="mt-2 text-2xl font-semibold">
            {{ overview?.realtime?.requests ?? 0 }} 次
            <span class="text-sm font-normal text-muted-foreground">
              {{ formatCost(overview?.realtime?.costUsd) }} ·
              {{ overview?.realtime?.avgLatencyMs ?? 0 }}ms
            </span>
          </p>
        </div>
      </div>

      <div class="grid gap-4 lg:grid-cols-2">
        <!-- 每日成本柱状(纯 CSS,与模型用量页同风格) -->
        <div class="rounded-lg border p-4">
          <h2 class="mb-4 font-medium">每日成本趋势(USD)</h2>
          <div class="flex h-40 items-end gap-1">
            <div
              v-for="item in costDaily"
              :key="item.statDate"
              class="group relative flex-1"
              :style="{ height: `${Math.max(4, Number(item.costUsd ?? 0) / maxDailyCost * 100)}%` }"
            >
              <div class="h-full w-full rounded-t bg-primary/80 transition group-hover:bg-primary" />
              <div class="pointer-events-none absolute bottom-full left-1/2 z-10 mb-1 hidden -translate-x-1/2 whitespace-nowrap rounded border bg-background px-2 py-1 text-xs group-hover:block">
                {{ item.statDate }} · {{ formatCost(item.costUsd) }} · {{ item.callCount }} 次
              </div>
            </div>
          </div>
          <div class="mt-2 flex justify-between text-xs text-muted-foreground">
            <span>{{ costDaily[0]?.statDate }}</span>
            <span>{{ costDaily[costDaily.length - 1]?.statDate }}</span>
          </div>
        </div>

        <!-- 模型占比 -->
        <div class="rounded-lg border p-4">
          <h2 class="mb-4 font-medium">模型成本占比(最近完整日)</h2>
          <div class="space-y-3">
            <div v-for="item in modelShare.slice(0, 6)" :key="`${item.tenantId}-${item.model}`">
              <div class="mb-1 flex justify-between text-sm">
                <span class="truncate">{{ item.model }}</span>
                <span class="text-muted-foreground">
                  {{ formatCost(item.costUsd) }} · {{ formatRate(item.costShare) }}
                </span>
              </div>
              <div class="h-2 rounded-full bg-muted">
                <div
                  class="h-2 rounded-full bg-primary"
                  :style="{ width: `${Math.min(100, Number(item.costShare ?? 0) * 100)}%` }"
                />
              </div>
            </div>
            <p v-if="!modelShare.length" class="text-sm text-muted-foreground">暂无数据</p>
          </div>
        </div>
      </div>

      <div class="grid gap-4 lg:grid-cols-2">
        <!-- 步骤成功率 -->
        <div class="rounded-lg border p-4">
          <h2 class="mb-4 font-medium">Agent 步骤成功率(按类型聚合)</h2>
          <table class="w-full text-sm">
            <thead>
              <tr class="text-left text-muted-foreground">
                <th class="pb-2">步骤类型</th>
                <th class="pb-2">步数</th>
                <th class="pb-2">错误</th>
                <th class="pb-2">成功率</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in toolSuccessAgg" :key="row.stepType" class="border-t">
                <td class="py-2">{{ row.stepType }}</td>
                <td>{{ row.stepCount.toLocaleString() }}</td>
                <td :class="row.errorCount > 0 ? 'text-rose-500' : ''">{{ row.errorCount }}</td>
                <td>
                  <span :class="row.successRate < 0.95 ? 'text-amber-500' : 'text-emerald-500'">
                    {{ formatRate(row.successRate) }}
                  </span>
                </td>
              </tr>
              <tr v-if="!toolSuccessAgg.length">
                <td colspan="4" class="py-3 text-center text-muted-foreground">暂无数据</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- 实时指标 -->
        <div class="rounded-lg border p-4">
          <div class="mb-4 flex items-center justify-between">
            <h2 class="font-medium">实时指标(1 分钟窗口,30s 自动刷新)</h2>
            <span class="inline-flex h-2 w-2 animate-pulse rounded-full bg-emerald-500" />
          </div>
          <table class="w-full text-sm">
            <thead>
              <tr class="text-left text-muted-foreground">
                <th class="pb-2">窗口</th>
                <th class="pb-2">模型</th>
                <th class="pb-2">请求</th>
                <th class="pb-2">Token</th>
                <th class="pb-2">均延迟</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in realtime.slice(0, 8)" :key="`${row.windowStart}-${row.model}`" class="border-t">
                <td class="py-2 font-mono text-xs">{{ row.windowStart.slice(11, 16) }}</td>
                <td class="truncate">{{ row.model }}</td>
                <td>{{ row.requestCount }}</td>
                <td>{{ formatTokens(row.totalTokens) }}</td>
                <td>{{ row.avgLatencyMs }}ms</td>
              </tr>
              <tr v-if="!realtime.length">
                <td colspan="5" class="py-3 text-center text-muted-foreground">
                  暂无实时数据(实时链路未启用或当前无流量)
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 评测质量趋势 -->
      <div v-if="evalQualityRows.length" class="rounded-lg border p-4">
        <h2 class="mb-4 font-medium">检索/评测质量趋势(近 30 天)</h2>
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left text-muted-foreground">
              <th class="pb-2">日期</th>
              <th class="pb-2">评测数</th>
              <th class="pb-2">命中率</th>
              <th class="pb-2">平均延迟</th>
              <th class="pb-2">失败率</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in evalQualityRows" :key="row.statDate" class="border-t">
              <td class="py-2">{{ row.statDate }}</td>
              <td>{{ row.evalCount }}</td>
              <td>{{ row.avgHitRatio == null ? '-' : formatRate(row.avgHitRatio) }}</td>
              <td>{{ row.avgLatencyMs == null ? '-' : `${row.avgLatencyMs}ms` }}</td>
              <td :class="row.failureRate > 0.1 ? 'text-rose-500' : ''">{{ formatRate(row.failureRate) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>
