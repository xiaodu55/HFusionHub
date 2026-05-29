<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as bidApi from '@/api/bid'
import type { BidRequirement, BidProjectStatus } from '@/api/bid'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { AlertTriangle, ArrowLeft, ArrowRight, CheckCircle2, FileSearch, ShieldCheck } from 'lucide-vue-next'
import { formatDateTime } from '@/utils/date'
import { useToast } from '@/composables/useToast'
import EmptyState from '@/components/EmptyState.vue'
import LoadingSkeleton from '@/components/LoadingSkeleton.vue'
import ErrorState from '@/components/ErrorState.vue'

const route = useRoute()
const router = useRouter()
const toast = useToast()

const projectId = computed(() => Number(route.params.id))

const detail = ref<bidApi.BidProjectDetail | null>(null)
const loading = ref(false)
const loadError = ref(false)

const STATUS_LABELS: Record<BidProjectStatus, string> = {
  interpreting: '解读中',
  requirements: '需求清单',
  drafting: '撰写中',
  checking: '自检中',
  submitted: '已投标',
  archived: '已归档',
}

const REQUIREMENT_CATEGORY_LABELS: Record<string, string> = {
  qualification: '资质要求',
  performance: '业绩要求',
  technical: '技术需求',
  commercial: '商务需求',
  format: '格式要求',
  disqualification_risk: '废标风险',
}

const REQUIREMENT_STATUS_LABELS: Record<BidRequirement['satisfiedStatus'], string> = {
  pending: '待处理',
  drafting: '撰写中',
  checked: '已确认',
  manual_review: '需人工复核',
}

const REQUIREMENT_STATUS_CLASS: Record<BidRequirement['satisfiedStatus'], string> = {
  pending: 'bg-slate-100 text-slate-600',
  drafting: 'bg-blue-100 text-blue-700',
  checked: 'bg-emerald-100 text-emerald-700',
  manual_review: 'bg-amber-100 text-amber-700',
}

const statusBadgeClass = (status: BidProjectStatus) => {
  switch (status) {
    case 'interpreting': return 'bg-blue-100 text-blue-700'
    case 'requirements': return 'bg-amber-100 text-amber-700'
    case 'drafting': return 'bg-purple-100 text-purple-700'
    case 'checking': return 'bg-orange-100 text-orange-700'
    case 'submitted': return 'bg-emerald-100 text-emerald-700'
    case 'archived': return 'bg-slate-100 text-slate-600'
  }
}

const project = computed(() => detail.value?.project ?? null)
const requirements = computed(() => detail.value?.requirements ?? [])
const requirementGroups = computed(() => {
  const groups: Array<{ category: string; label: string; items: BidRequirement[] }> = []
  const byCategory = new Map<string, BidRequirement[]>()
  for (const req of requirements.value) {
    const key = req.category || 'other'
    if (!byCategory.has(key)) byCategory.set(key, [])
    byCategory.get(key)!.push(req)
  }
  for (const [category, items] of byCategory) {
    groups.push({ category, label: REQUIREMENT_CATEGORY_LABELS[category] || category, items })
  }
  return groups
})

const manualReviewCount = computed(() =>
  requirements.value.filter(r => r.satisfiedStatus === 'manual_review').length,
)
const checkedCount = computed(() =>
  requirements.value.filter(r => r.satisfiedStatus === 'checked').length,
)
const confirmProgress = computed(() =>
  requirements.value.length === 0
    ? 0
    : Math.round((checkedCount.value / requirements.value.length) * 100),
)

const loadDetail = async () => {
  loading.value = true
  loadError.value = false
  try {
    detail.value = (await bidApi.getBidProjectDetail(projectId.value)).data
  } catch (error) {
    loadError.value = true
    toast.error(error instanceof Error ? error.message : '加载需求清单失败')
  } finally {
    loading.value = false
  }
}

const changeRequirementStatus = async (
  requirement: BidRequirement,
  status: BidRequirement['satisfiedStatus'],
) => {
  try {
    await bidApi.updateBidRequirementStatus(projectId.value, requirement.id, status)
    requirement.satisfiedStatus = status
    toast.success(status === 'checked' ? '已确认满足该需求' : '已撤销确认')
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '更新需求状态失败')
  }
}

const goDraft = () => router.push(`/bid/projects/${projectId.value}/draft`)

onMounted(loadDetail)
</script>

<template>
  <div class="container mx-auto max-w-6xl px-4 py-6">
    <!-- 步骤导航：解读 → 需求确认 → 撰写 → 自检 -->
    <nav class="mb-6 flex flex-wrap items-center gap-2 text-sm">
      <Button variant="ghost" size="sm" @click="router.push(`/bid/projects/${projectId}/interpret`)">
        <FileSearch class="mr-1 h-4 w-4" /> 解读
      </Button>
      <span class="text-muted-foreground">→</span>
      <span class="inline-flex items-center gap-1 rounded-full bg-primary px-3 py-1 font-medium text-primary-foreground">
        <CheckCircle2 class="h-4 w-4" /> 需求确认
      </span>
      <span class="text-muted-foreground">→</span>
      <Button variant="ghost" size="sm" @click="goDraft">撰写 / 自检</Button>
    </nav>

    <!-- 项目头部 -->
    <div v-if="project" class="mb-6">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="min-w-0">
          <div class="flex items-center gap-2">
            <Button variant="ghost" size="sm" class="-ml-2" @click="router.push('/bid/projects')">
              <ArrowLeft class="mr-1 h-4 w-4" /> 返回列表
            </Button>
            <Badge :class="statusBadgeClass(project.status)">{{ STATUS_LABELS[project.status] }}</Badge>
          </div>
          <h1 class="mt-2 text-2xl font-bold">{{ project.title }}</h1>
          <p class="mt-1 text-sm text-muted-foreground">
            <template v-if="project.tenderNumber">招标编号：{{ project.tenderNumber }} · </template>
            创建于 {{ formatDateTime(project.createdAt) }}
          </p>
        </div>
        <Button :disabled="requirements.length === 0" @click="goDraft">
          进入撰写 <ArrowRight class="ml-1 h-4 w-4" />
        </Button>
      </div>

      <!-- 确认进度 -->
      <div class="mt-4 rounded-lg border border-border bg-card p-4">
        <div class="mb-2 flex items-center justify-between text-sm">
          <span class="font-medium">需求确认进度</span>
          <span class="text-muted-foreground">
            {{ checkedCount }} / {{ requirements.length }} 已确认
            <span v-if="manualReviewCount > 0" class="ml-2 text-amber-600">{{ manualReviewCount }} 项需人工复核</span>
          </span>
        </div>
        <div class="h-2 overflow-hidden rounded-full bg-muted">
          <div
            class="h-full rounded-full bg-emerald-500 transition-all"
            :style="{ width: `${confirmProgress}%` }"
          />
        </div>
      </div>
    </div>

    <!-- 免责声明 -->
    <div
      v-if="project"
      class="mb-6 flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800"
    >
      <ShieldCheck class="mt-0.5 h-4 w-4 shrink-0" />
      <div>
        <p class="font-medium">需求清单以招标文件为准</p>
        <p class="mt-1 text-amber-700/90">
          请逐项核对以下需求，重点复核带「需人工复核」标记的低置信条目。全部确认后进入撰写环节，
          AI 将按已确认需求生成标书。
        </p>
      </div>
    </div>

    <LoadingSkeleton v-if="loading" type="card" :count="4" />
    <ErrorState
      v-else-if="loadError"
      title="加载失败"
      message="无法加载投标项目需求清单，请稍后重试"
      @retry="loadDetail"
    />

    <template v-else>
      <EmptyState
        v-if="requirements.length === 0"
        :icon="FileSearch"
        title="尚未生成需求清单"
        description="请先在「解读」环节触发招标文件解读，生成需求清单后再来确认"
      />
      <div v-else class="space-y-4">
        <Card v-for="group in requirementGroups" :key="group.category">
          <CardHeader class="pb-2">
            <CardTitle class="text-sm">{{ group.label }}</CardTitle>
          </CardHeader>
          <CardContent class="space-y-2">
            <div
              v-for="requirement in group.items"
              :key="requirement.id"
              class="flex items-start justify-between gap-3 rounded-lg border border-border p-3"
              :class="requirement.satisfiedStatus === 'checked' ? 'bg-emerald-50/50' : ''"
            >
              <div class="min-w-0">
                <p class="break-words text-sm">{{ requirement.requirement }}</p>
                <p v-if="requirement.sourceClause" class="mt-1 line-clamp-2 text-xs text-muted-foreground">
                  来源：{{ requirement.sourceClause }}
                </p>
              </div>
              <div class="flex shrink-0 items-center gap-2">
                <span
                  v-if="requirement.satisfiedStatus === 'manual_review'"
                  class="inline-flex items-center gap-1 rounded bg-amber-100 px-1.5 py-0.5 text-[11px] font-medium text-amber-700"
                  title="AI 置信度低于 60%，需人工复核"
                >
                  <AlertTriangle class="h-3 w-3" /> 低置信
                </span>
                <Badge :class="REQUIREMENT_STATUS_CLASS[requirement.satisfiedStatus]">
                  {{ REQUIREMENT_STATUS_LABELS[requirement.satisfiedStatus] }}
                </Badge>
                <Button
                  v-if="requirement.satisfiedStatus !== 'checked'"
                  variant="outline"
                  size="sm"
                  @click="changeRequirementStatus(requirement, 'checked')"
                >
                  确认已满足
                </Button>
                <Button
                  v-else
                  variant="ghost"
                  size="sm"
                  @click="changeRequirementStatus(requirement, 'pending')"
                >
                  撤销确认
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </template>
  </div>
</template>
