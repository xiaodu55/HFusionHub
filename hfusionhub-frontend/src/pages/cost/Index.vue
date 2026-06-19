<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, BarChart3, Bot, CircleDollarSign, MessageSquare, RefreshCw, Zap } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { useToast } from '@/composables/useToast'
import * as costApi from '@/api/cost'
import type { CostSummary, DailyCost, ModelBreakdown } from '@/api/cost'
import * as quotaApi from '@/api/quota'
import type { QuotaSummary } from '@/api/quota'
import LoadingSkeleton from '@/components/LoadingSkeleton.vue'

const router = useRouter()
const toast = useToast()
const days = ref(30)
const loading = ref(false)
const summary = ref<CostSummary | null>(null)
const dailyCosts = ref<DailyCost[]>([])
const modelBreakdown = ref<ModelBreakdown[]>([])
const quotas = ref<QuotaSummary[]>([])

/** 配额用量条颜色：>=90% 红，>=70% 琥珀，其余绿 */
function quotaBarClass(percent: number) {
  if (percent >= 90) return 'bg-rose-500'
  if (percent >= 70) return 'bg-amber-500'
  return 'bg-primary'
}

function formatQuota(value: number, unit: string) {
  return `${value.toLocaleString()} ${unit}`
}

const timeRanges = [{ label: '7 天', value: 7 }, { label: '30 天', value: 30 }, { label: '90 天', value: 90 }]
const hasUsage = computed(() => Boolean(summary.value?.totalRequests || modelBreakdown.value.length))
const totalModelTokens = computed(() => modelBreakdown.value.reduce((sum, model) => sum + model.totalTokens, 0))
const maxDailyCost = computed(() => Math.max(...dailyCosts.value.map(item => item.totalCost), 0.01))
const avgCostPerRequest = computed(() => summary.value?.totalRequests
  ? summary.value.totalCost / summary.value.totalRequests
  : 0)

/** 金额展示：避免超长小数；按大小自适应精度并去掉多余的 0 */
function formatCost(value: number) {
  if (!Number.isFinite(value)) return '$0'
  if (value === 0) return '$0'
  if (value >= 1) return `$${value.toFixed(2)}`
  if (value >= 0.01) return `$${value.toFixed(3)}`
  return `$${value.toFixed(4).replace(/0+$/, '').replace(/\.$/, '')}`
}

function modelPercentage(tokens: number) {
  return totalModelTokens.value ? tokens / totalModelTokens.value * 100 : 0
}

/** 每个模型一个稳定的强调色（多彩但不刺眼） */
const MODEL_COLORS = [
  'bg-emerald-500', 'bg-cyan-500', 'bg-violet-500', 'bg-amber-500',
  'bg-rose-500', 'bg-blue-500', 'bg-teal-500', 'bg-orange-500',
]
function modelColor(index: number) {
  return MODEL_COLORS[index % MODEL_COLORS.length]
}

/** 柱状图最高的那一天高亮 */
const maxDailyDate = computed(() => {
  let best = ''
  let bestCost = -1
  for (const item of dailyCosts.value) {
    if (item.totalCost > bestCost) {
      bestCost = item.totalCost
      best = item.statDate
    }
  }
  return best
})

async function loadData() {
  loading.value = true
  try {
    const [summaryRes, dailyRes, modelsRes, quotaRes] = await Promise.all([
      costApi.getCostSummary(days.value),
      costApi.getDailyCosts(days.value),
      costApi.getModelBreakdown(days.value),
      quotaApi.getQuotaSummary(),
    ])
    summary.value = summaryRes.data
    dailyCosts.value = dailyRes.data
    modelBreakdown.value = modelsRes.data
    quotas.value = quotaRes.data ?? []
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '加载用量数据失败')
  } finally {
    loading.value = false
  }
}

function changeRange(value: number) {
  days.value = value
  void loadData()
}

onMounted(loadData)
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-6 p-6">
    <div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div>
        <h1 class="flex items-center gap-2 text-xl font-semibold">
          <BarChart3 class="h-5 w-5 text-primary" />
          用量与费用
        </h1>
        <p class="mt-1 text-sm text-muted-foreground">
          查看您实际调用了哪些模型、消耗多少 Token，以及产生的费用。这里只统计已经完成的 AI 请求。
        </p>
      </div>
      <div class="flex items-center gap-2">
        <div class="flex rounded-md border border-border p-1">
          <button v-for="range in timeRanges" :key="range.value" class="rounded px-3 py-1.5 text-sm" :class="days === range.value ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted'" @click="changeRange(range.value)">{{ range.label }}</button>
        </div>
        <Button variant="outline" size="icon" title="刷新用量" :disabled="loading" @click="loadData"><RefreshCw class="h-4 w-4" :class="loading && 'animate-spin'" /></Button>
      </div>
    </div>

    <LoadingSkeleton v-if="loading && !summary" type="card" :count="4" />

    <template v-else-if="summary">
      <section class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div v-for="card in [
          { icon: CircleDollarSign, tone: 'bg-emerald-500/12 text-emerald-600 dark:text-emerald-400', label: '累计费用', value: formatCost(summary.totalCost), caption: '最近 ' + days + ' 天实际产生' },
          { icon: BarChart3, tone: 'bg-cyan-500/12 text-cyan-600 dark:text-cyan-400', label: '预估月费', value: formatCost(summary.estimatedMonthCost), caption: '按当前使用速度估算' },
          { icon: Zap, tone: 'bg-violet-500/12 text-violet-600 dark:text-violet-400', label: 'Token 用量', value: summary.totalTokens.toLocaleString(), caption: '模型处理的文本单位' },
          { icon: Bot, tone: 'bg-amber-500/12 text-amber-600 dark:text-amber-400', label: 'AI 请求', value: summary.totalRequests.toLocaleString(), caption: '平均 ' + formatCost(avgCostPerRequest) + ' / 次' },
        ]" :key="card.label" class="group rounded-xl border border-border bg-card/80 p-5 transition-all hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-lg">
          <div class="flex items-center justify-between">
            <span class="text-sm text-muted-foreground">{{ card.label }}</span>
            <span class="flex h-8 w-8 items-center justify-center rounded-lg transition-transform group-hover:scale-105" :class="card.tone"><component :is="card.icon" class="h-4 w-4" /></span>
          </div>
          <p class="mt-3 text-3xl font-semibold tabular-nums tracking-tight text-foreground">{{ card.value }}</p>
          <p class="mt-1.5 text-xs text-muted-foreground">{{ card.caption }}</p>
        </div>
      </section>

      <!-- 租户配额（今日）：读 usage_ledger 预占/结算与 usage_quota 日限额 -->
      <section v-if="quotas.length" class="rounded-lg border border-border bg-card/35 p-5">
        <div class="flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 class="font-medium">今日配额</h2>
            <p class="mt-1 text-sm text-muted-foreground">当前租户今日各项用量与日限额，超限时相关请求会被拒绝。</p>
          </div>
          <span class="text-xs text-muted-foreground">每日 00:00 重置</span>
        </div>
        <div class="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <div v-for="quota in quotas" :key="quota.meter" class="rounded-xl border border-border/70 bg-muted/20 p-4 transition-colors hover:border-primary/25">
            <div class="flex items-baseline justify-between gap-3 text-sm">
              <span class="font-medium">{{ quota.label }}</span>
              <span class="rounded-full bg-muted px-2 py-0.5 text-xs tabular-nums text-muted-foreground">{{ Math.round(quota.percent) }}%</span>
            </div>
            <div class="mt-3 h-2 overflow-hidden rounded-full bg-muted">
              <div class="h-full rounded-full transition-all" :class="quotaBarClass(quota.percent)" :style="{ width: `${Math.min(quota.percent, 100)}%` }" />
            </div>
            <p class="mt-2.5 text-xs tabular-nums text-muted-foreground">
              {{ formatQuota(quota.used, quota.unit) }} / {{ formatQuota(quota.dailyLimit, quota.unit) }}
              <span v-if="quota.reserved > 0">· 预占 {{ formatQuota(quota.reserved, quota.unit) }}</span>
              <span v-if="quota.percent >= 90" class="font-medium text-rose-500">· 即将超限</span>
            </p>
          </div>
        </div>
      </section>

      <section v-if="!hasUsage" class="grid overflow-hidden rounded-lg border border-border bg-card/35 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div class="flex flex-col justify-center p-6 sm:p-8">
          <div class="flex h-11 w-11 items-center justify-center rounded-md border border-primary/25 bg-primary/10 text-primary"><MessageSquare class="h-5 w-5" /></div>
          <h2 class="mt-5 text-xl font-semibold">还没有产生模型用量</h2>
          <p class="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">完成一次智能对话后，这里会显示使用模型、Token、请求次数和费用。目前显示 0 是正常状态，不是服务故障。</p>
          <div class="mt-5 flex flex-wrap gap-2">
            <Button class="gap-2" @click="router.push('/chat')">开始智能对话<ArrowRight class="h-4 w-4" /></Button>
            <Button variant="outline" @click="router.push('/builder/models')">检查我的模型</Button>
          </div>
        </div>
        <div class="border-t border-border bg-muted/20 p-6 lg:border-l lg:border-t-0">
          <p class="text-sm font-medium">使用步骤</p>
          <ol class="mt-4 space-y-4 text-sm text-muted-foreground">
            <li class="flex gap-3"><span class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs text-primary">1</span><span>在“我的模型”中选择供应商并测试连接。</span></li>
            <li class="flex gap-3"><span class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs text-primary">2</span><span>进入“智能对话”发送一个问题。</span></li>
            <li class="flex gap-3"><span class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs text-primary">3</span><span>返回本页查看本次调用的用量记录。</span></li>
          </ol>
        </div>
      </section>

      <template v-else>
        <section class="grid gap-5 lg:grid-cols-2">
          <div class="rounded-lg border border-border bg-card/35 p-5">
            <h2 class="font-medium">每日费用</h2><p class="mt-1 text-sm text-muted-foreground">观察哪几天的模型调用较多</p>
            <div class="mt-6 flex h-44 items-end gap-1.5 border-b border-border/70 pb-px">
              <div
                v-for="item in dailyCosts"
                :key="item.statDate"
                class="min-w-[6px] flex-1 cursor-default rounded-t-md transition-all hover:opacity-100"
                :class="item.statDate === maxDailyDate
                  ? 'bg-gradient-to-t from-primary to-emerald-400 opacity-100'
                  : 'bg-primary/45 hover:bg-primary/80'"
                :style="{ height: `${Math.max(item.totalCost / maxDailyCost * 100, 3)}%` }"
                :title="`${item.statDate}：${formatCost(item.totalCost)}${item.statDate === maxDailyDate ? '（峰值）' : ''}`"
              />
            </div>
            <div class="mt-2 flex items-center justify-between text-xs text-muted-foreground">
              <span>{{ dailyCosts[0]?.statDate }}</span>
              <span v-if="maxDailyDate" class="rounded-full bg-muted px-2.5 py-1">峰值 {{ maxDailyDate }} · {{ formatCost(maxDailyCost) }}</span>
              <span>{{ dailyCosts[dailyCosts.length - 1]?.statDate }}</span>
            </div>
          </div>
          <div class="rounded-lg border border-border bg-card/35 p-5">
            <h2 class="font-medium">模型占比</h2><p class="mt-1 text-sm text-muted-foreground">了解用量主要来自哪个模型</p>
            <div class="mt-6 space-y-4">
              <div v-for="(model, index) in modelBreakdown" :key="model.model">
                <div class="flex items-center justify-between gap-4 text-sm">
                  <span class="flex min-w-0 items-center gap-2">
                    <span class="h-2.5 w-2.5 shrink-0 rounded-full" :class="modelColor(index)" />
                    <span class="truncate font-medium">{{ model.model }}</span>
                  </span>
                  <span class="shrink-0 text-muted-foreground"><span class="tabular-nums">{{ model.totalTokens.toLocaleString() }}</span> tok · {{ modelPercentage(model.totalTokens).toFixed(0) }}%</span>
                </div>
                <div class="mt-2 h-2 overflow-hidden rounded-full bg-muted"><div class="h-full rounded-full transition-all" :class="modelColor(index)" :style="{ width: `${modelPercentage(model.totalTokens)}%` }" /></div>
              </div>
            </div>
          </div>
        </section>

        <section class="overflow-hidden rounded-lg border border-border bg-card/35">
          <div class="border-b border-border p-5"><h2 class="font-medium">模型用量明细</h2><p class="mt-1 text-sm text-muted-foreground">用于核对具体模型的 Token 和费用</p></div>
          <div class="overflow-x-auto"><table class="w-full min-w-[620px] text-sm"><thead class="bg-muted/30 text-left text-xs uppercase tracking-wider text-muted-foreground"><tr><th class="px-5 py-3 font-medium">模型</th><th class="px-5 py-3 text-right font-medium">Token</th><th class="px-5 py-3 text-right font-medium">费用</th><th class="px-5 py-3 text-right font-medium">占比</th></tr></thead><tbody>
            <tr v-for="(model, index) in modelBreakdown" :key="model.model" class="border-t border-border/60 transition-colors odd:bg-muted/10 hover:bg-primary/5">
              <td class="px-5 py-3.5"><span class="inline-flex items-center gap-2"><span class="h-2 w-2 rounded-full" :class="modelColor(index)" /><span class="font-mono text-[13px] font-medium">{{ model.model }}</span></span></td>
              <td class="px-5 py-3.5 text-right tabular-nums">{{ model.totalTokens.toLocaleString() }}</td>
              <td class="px-5 py-3.5 text-right tabular-nums font-medium">{{ formatCost(model.totalCost) }}</td>
              <td class="px-5 py-3.5 text-right tabular-nums text-muted-foreground">{{ modelPercentage(model.totalTokens).toFixed(1) }}%</td>
            </tr>
          </tbody></table></div>
        </section>
      </template>
    </template>

    <div v-else class="py-16 text-center"><p class="text-sm text-muted-foreground">暂时无法读取用量数据</p><Button variant="outline" class="mt-4 gap-2" @click="loadData"><RefreshCw class="h-4 w-4" />重新加载</Button></div>
  </div>
</template>
