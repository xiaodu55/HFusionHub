<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, BarChart3, Bot, CircleDollarSign, MessageSquare, RefreshCw, Zap } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { useToast } from '@/composables/useToast'
import * as costApi from '@/api/cost'
import type { CostSummary, DailyCost, ModelBreakdown } from '@/api/cost'

const router = useRouter()
const toast = useToast()
const days = ref(30)
const loading = ref(false)
const summary = ref<CostSummary | null>(null)
const dailyCosts = ref<DailyCost[]>([])
const modelBreakdown = ref<ModelBreakdown[]>([])

const timeRanges = [{ label: '7 天', value: 7 }, { label: '30 天', value: 30 }, { label: '90 天', value: 90 }]
const hasUsage = computed(() => Boolean(summary.value?.totalRequests || modelBreakdown.value.length))
const totalModelTokens = computed(() => modelBreakdown.value.reduce((sum, model) => sum + model.totalTokens, 0))
const maxDailyCost = computed(() => Math.max(...dailyCosts.value.map(item => item.totalCost), 0.01))
const avgCostPerRequest = computed(() => summary.value?.totalRequests
  ? summary.value.totalCost / summary.value.totalRequests
  : 0)

function modelPercentage(tokens: number) {
  return totalModelTokens.value ? tokens / totalModelTokens.value * 100 : 0
}

async function loadData() {
  loading.value = true
  try {
    const [summaryRes, dailyRes, modelsRes] = await Promise.all([
      costApi.getCostSummary(days.value),
      costApi.getDailyCosts(days.value),
      costApi.getModelBreakdown(days.value),
    ])
    summary.value = summaryRes.data
    dailyCosts.value = dailyRes.data
    modelBreakdown.value = modelsRes.data
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
  <div class="mx-auto max-w-7xl space-y-5 pb-8">
    <header class="flex flex-col gap-4 border-b border-border pb-5 lg:flex-row lg:items-end lg:justify-between">
      <div>
        <p class="text-sm font-medium text-primary">模型用量</p>
        <h1 class="mt-1 text-2xl font-semibold">用量与费用</h1>
        <p class="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">查看您实际调用了哪些模型、消耗多少 Token，以及产生的费用。这里只统计已经完成的 AI 请求。</p>
      </div>
      <div class="flex items-center gap-2">
        <div class="flex rounded-md border border-border p-1">
          <button v-for="range in timeRanges" :key="range.value" class="rounded px-3 py-1.5 text-sm" :class="days === range.value ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted'" @click="changeRange(range.value)">{{ range.label }}</button>
        </div>
        <Button variant="outline" size="icon" title="刷新用量" :disabled="loading" @click="loadData"><RefreshCw class="h-4 w-4" :class="loading && 'animate-spin'" /></Button>
      </div>
    </header>

    <div v-if="loading && !summary" class="py-20 text-center text-sm text-muted-foreground">正在统计用量...</div>

    <template v-else-if="summary">
      <section class="grid overflow-hidden rounded-lg border border-border bg-card/40 sm:grid-cols-2 xl:grid-cols-4">
        <div class="border-b border-border p-4 sm:border-r xl:border-b-0"><p class="flex items-center gap-2 text-sm text-muted-foreground"><CircleDollarSign class="h-4 w-4" />当前费用</p><p class="mt-2 text-2xl font-semibold">${{ summary.totalCost.toFixed(4) }}</p><p class="mt-1 text-xs text-muted-foreground">最近 {{ days }} 天</p></div>
        <div class="border-b border-border p-4 xl:border-b-0 xl:border-r"><p class="flex items-center gap-2 text-sm text-muted-foreground"><BarChart3 class="h-4 w-4" />预估月费</p><p class="mt-2 text-2xl font-semibold">${{ summary.estimatedMonthCost.toFixed(4) }}</p><p class="mt-1 text-xs text-muted-foreground">按当前使用速度估算</p></div>
        <div class="border-b border-border p-4 sm:border-b-0 sm:border-r"><p class="flex items-center gap-2 text-sm text-muted-foreground"><Zap class="h-4 w-4" />Token 用量</p><p class="mt-2 text-2xl font-semibold">{{ summary.totalTokens.toLocaleString() }}</p><p class="mt-1 text-xs text-muted-foreground">模型处理的文本单位</p></div>
        <div class="p-4"><p class="flex items-center gap-2 text-sm text-muted-foreground"><Bot class="h-4 w-4" />AI 请求</p><p class="mt-2 text-2xl font-semibold">{{ summary.totalRequests.toLocaleString() }}</p><p class="mt-1 text-xs text-muted-foreground">平均 ${{ avgCostPerRequest.toFixed(6) }} / 次</p></div>
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
            <div class="mt-6 flex h-44 items-end gap-1">
              <div v-for="item in dailyCosts" :key="item.statDate" class="min-w-[5px] flex-1 rounded-t bg-primary/60 hover:bg-primary" :style="{ height: `${Math.max(item.totalCost / maxDailyCost * 100, 2)}%` }" :title="`${item.statDate}: $${item.totalCost.toFixed(4)}`" />
            </div>
            <div class="mt-2 flex justify-between text-xs text-muted-foreground"><span>{{ dailyCosts[0]?.statDate }}</span><span>{{ dailyCosts[dailyCosts.length - 1]?.statDate }}</span></div>
          </div>
          <div class="rounded-lg border border-border bg-card/35 p-5">
            <h2 class="font-medium">模型占比</h2><p class="mt-1 text-sm text-muted-foreground">了解用量主要来自哪个模型</p>
            <div class="mt-6 space-y-4">
              <div v-for="model in modelBreakdown" :key="model.model">
                <div class="flex justify-between gap-4 text-sm"><span class="truncate font-medium">{{ model.model }}</span><span class="shrink-0 text-muted-foreground">{{ modelPercentage(model.totalTokens).toFixed(0) }}%</span></div>
                <div class="mt-2 h-2 overflow-hidden rounded-full bg-muted"><div class="h-full rounded-full bg-primary" :style="{ width: `${modelPercentage(model.totalTokens)}%` }" /></div>
              </div>
            </div>
          </div>
        </section>

        <section class="overflow-hidden rounded-lg border border-border bg-card/35">
          <div class="border-b border-border p-5"><h2 class="font-medium">模型用量明细</h2><p class="mt-1 text-sm text-muted-foreground">用于核对具体模型的 Token 和费用</p></div>
          <div class="overflow-x-auto"><table class="w-full min-w-[620px] text-sm"><thead class="bg-muted/20 text-left text-xs text-muted-foreground"><tr><th class="px-5 py-3">模型</th><th class="px-5 py-3 text-right">Token</th><th class="px-5 py-3 text-right">费用</th><th class="px-5 py-3 text-right">占比</th></tr></thead><tbody><tr v-for="model in modelBreakdown" :key="model.model" class="border-t border-border/70"><td class="px-5 py-4 font-medium">{{ model.model }}</td><td class="px-5 py-4 text-right">{{ model.totalTokens.toLocaleString() }}</td><td class="px-5 py-4 text-right">${{ model.totalCost.toFixed(6) }}</td><td class="px-5 py-4 text-right">{{ modelPercentage(model.totalTokens).toFixed(1) }}%</td></tr></tbody></table></div>
        </section>
      </template>
    </template>

    <div v-else class="py-16 text-center"><p class="text-sm text-muted-foreground">暂时无法读取用量数据</p><Button variant="outline" class="mt-4 gap-2" @click="loadData"><RefreshCw class="h-4 w-4" />重新加载</Button></div>
  </div>
</template>
