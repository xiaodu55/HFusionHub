<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { DollarSign, TrendingUp, Zap, BarChart3, RefreshCw } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { useToast } from '@/composables/useToast'
import * as costApi from '@/api/cost'
import type { CostSummary, DailyCost, ModelBreakdown } from '@/api/cost'
import { formatDateTime } from '@/utils/date'

const toast = useToast()

const days = ref(30)
const loading = ref(false)
const summary = ref<CostSummary | null>(null)
const dailyCosts = ref<DailyCost[]>([])
const modelBreakdown = ref<ModelBreakdown[]>([])

const timeRanges = [
  { label: '7 天', value: 7 },
  { label: '30 天', value: 30 },
  { label: '90 天', value: 90 },
]

const maxDailyCost = computed(() => {
  if (!dailyCosts.value.length) return 1
  return Math.max(...dailyCosts.value.map(d => d.cost), 0.01)
})

const totalCostDisplay = computed(() => {
  if (!summary.value) return '$0.00'
  return '$' + summary.value.totalCost.toFixed(4)
})

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
  } catch (e) {
    toast.error(e instanceof Error ? e.message : '加载成本数据失败')
  } finally {
    loading.value = false
  }
}

function changeRange(d: number) {
  days.value = d
  loadData()
}

onMounted(loadData)
</script>

<template>
  <div class="space-y-6 pb-8">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-2xl font-bold tracking-tight">成本仪表板</h2>
        <p class="text-sm text-muted-foreground mt-1">模型使用成本与用量趋势</p>
      </div>
      <div class="flex items-center gap-2">
        <Button
          v-for="r in timeRanges" :key="r.value"
          :variant="days === r.value ? 'default' : 'outline'"
          size="sm"
          @click="changeRange(r.value)"
        >
          {{ r.label }}
        </Button>
        <Button variant="ghost" size="icon" class="h-8 w-8" :disabled="loading" @click="loadData">
          <RefreshCw :class="['h-4 w-4', loading && 'animate-spin']" />
        </Button>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading && !summary" class="text-center py-16 text-muted-foreground">加载中...</div>

    <template v-else-if="summary">
      <!-- Summary cards -->
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader class="pb-2">
            <CardDescription class="flex items-center gap-1.5">
              <DollarSign class="h-3.5 w-3.5" />本月费用
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p class="text-2xl font-bold">{{ totalCostDisplay }}</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader class="pb-2">
            <CardDescription class="flex items-center gap-1.5">
              <TrendingUp class="h-3.5 w-3.5" />预估月费
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p class="text-2xl font-bold">${{ summary.projectedMonthlyCost.toFixed(4) }}</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader class="pb-2">
            <CardDescription class="flex items-center gap-1.5">
              <Zap class="h-3.5 w-3.5" />总 Token
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p class="text-2xl font-bold">{{ summary.totalTokens.toLocaleString() }}</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader class="pb-2">
            <CardDescription class="flex items-center gap-1.5">
              <BarChart3 class="h-3.5 w-3.5" />请求数
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p class="text-2xl font-bold">{{ summary.totalRequests.toLocaleString() }}</p>
            <p class="text-xs text-muted-foreground mt-1">
              均 ${{ summary.avgCostPerRequest.toFixed(6) }}/请求
            </p>
          </CardContent>
        </Card>
      </div>

      <!-- Charts section -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <!-- Daily cost chart (CSS bar chart) -->
        <Card>
          <CardHeader>
            <CardTitle class="text-base">每日费用趋势</CardTitle>
            <CardDescription>最近 {{ days }} 天</CardDescription>
          </CardHeader>
          <CardContent>
            <div v-if="dailyCosts.length === 0" class="text-sm text-muted-foreground text-center py-8">
              暂无数据
            </div>
            <div v-else class="flex items-end gap-[2px] h-40">
              <div
                v-for="d in dailyCosts" :key="d.date"
                class="flex-1 bg-primary/60 hover:bg-primary rounded-t-sm transition-colors min-w-[6px]"
                :style="{ height: (d.cost / maxDailyCost * 100) + '%' }"
                :title="`${d.date}: $${d.cost.toFixed(4)}`"
              />
            </div>
            <div class="flex justify-between mt-2 text-[10px] text-muted-foreground">
              <span>{{ dailyCosts[0]?.date || '' }}</span>
              <span>{{ dailyCosts[dailyCosts.length - 1]?.date || '' }}</span>
            </div>
          </CardContent>
        </Card>

        <!-- Model breakdown -->
        <Card>
          <CardHeader>
            <CardTitle class="text-base">模型用量分布</CardTitle>
            <CardDescription>{{ days }} 天模型费用占比</CardDescription>
          </CardHeader>
          <CardContent>
            <div v-if="modelBreakdown.length === 0" class="text-sm text-muted-foreground text-center py-8">
              暂无数据
            </div>
            <div v-else class="space-y-3">
              <div v-for="m in modelBreakdown" :key="m.model" class="space-y-1">
                <div class="flex items-center justify-between text-sm">
                  <span class="font-medium">{{ m.model }}</span>
                  <span class="text-muted-foreground text-xs">${{ m.cost.toFixed(4) }} ({{ m.percentage.toFixed(0) }}%)</span>
                </div>
                <div class="h-2 bg-muted rounded-full overflow-hidden">
                  <div
                    class="h-full bg-primary rounded-full transition-all"
                    :style="{ width: m.percentage + '%' }"
                  />
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <!-- Recent usage table -->
      <Card>
        <CardHeader>
          <CardTitle class="text-base">最近使用记录</CardTitle>
          <CardDescription>最近 20 条模型调用</CardDescription>
        </CardHeader>
        <CardContent>
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b text-left text-xs text-muted-foreground">
                  <th class="py-2 pr-4">日期</th>
                  <th class="py-2 pr-4">模型</th>
                  <th class="py-2 pr-4 text-right">Token</th>
                  <th class="py-2 pr-4 text-right">费用</th>
                  <th class="py-2">类型</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="dailyCosts.length === 0">
                  <td colspan="5" class="py-8 text-center text-muted-foreground">暂无记录</td>
                </tr>
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </template>

    <!-- Error state -->
    <div v-else-if="!loading" class="text-center py-16">
      <DollarSign class="h-12 w-12 mx-auto text-muted-foreground/50" />
      <p class="mt-4 text-muted-foreground">无法加载成本数据，请检查服务连接</p>
      <Button variant="outline" size="sm" class="mt-4" @click="loadData">
        <RefreshCw class="h-3.5 w-3.5 mr-1.5" />重试
      </Button>
    </div>
  </div>
</template>
