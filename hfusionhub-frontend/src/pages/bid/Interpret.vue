<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as bidApi from '@/api/bid'
import type {
  BidProjectStatus,
  TenderElement,
  BidScoringMethod,
  BidRequirement,
} from '@/api/bid'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Select } from '@/components/ui/select'
import { AlertTriangle, ArrowLeft, CheckCircle2, FileSearch, Loader2, PenLine, RefreshCw, ShieldCheck } from 'lucide-vue-next'
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
const interpreting = ref(false)

const STATUS_LABELS: Record<BidProjectStatus, string> = {
  interpreting: '解读中',
  requirements: '需求清单',
  drafting: '撰写中',
  checking: '自检中',
  submitted: '已投标',
  archived: '已归档',
}

const STATUS_OPTIONS = Object.entries(STATUS_LABELS).map(([value, label]) => ({ value, label }))

const ELEMENT_LABELS: Record<string, string> = {
  tender_number: '招标编号',
  budget: '预算金额',
  qualification_requirements: '资质要求',
  deadline: '投标截止',
  bid_bond: '投标保证金',
  bid_currency: '币种',
  contact: '联系方式',
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
const elements = computed(() => detail.value?.elements ?? [])
const scoringMethods = computed(() => detail.value?.scoringMethods ?? [])
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
    groups.push({
      category,
      label: REQUIREMENT_CATEGORY_LABELS[category] || category,
      items,
    })
  }
  return groups
})
const manualReviewCount = computed(() =>
  requirements.value.filter(r => r.satisfiedStatus === 'manual_review').length,
)

const elementLabel = (element: TenderElement) => ELEMENT_LABELS[element.elementKey] || element.elementKey
const formatConfidence = (confidence?: number | null) =>
  confidence === null || confidence === undefined ? null : `${Math.round(confidence * 100)}%`

/** evidence_chunk_ids 存 JSON 数组字符串，拆成可展示的证据引用 */
const parseEvidence = (element: TenderElement): string[] => {
  if (!element.evidenceChunkIds) return []
  const raw = element.evidenceChunkIds
  try {
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) return parsed.map(String)
  } catch {
    /* 单值字符串 */
  }
  return raw.split(',').map(s => s.trim()).filter(Boolean)
}

/** points_json 存 JSON 数组 [{name, score}] */
const parsePoints = (method: BidScoringMethod): Array<{ name: string; score: string }> => {
  if (!method.pointsJson) return []
  try {
    const parsed = JSON.parse(method.pointsJson)
    if (Array.isArray(parsed)) {
      return parsed.map((p: Record<string, unknown>) => ({
        name: String(p.name ?? p.point ?? ''),
        score: String(p.score ?? ''),
      })).filter(p => p.name || p.score)
    }
  } catch {
    /* 非法 JSON */
  }
  return []
}

const loadDetail = async () => {
  loading.value = true
  loadError.value = false
  try {
    detail.value = (await bidApi.getBidProjectDetail(projectId.value)).data
  } catch (error) {
    loadError.value = true
    toast.error(error instanceof Error ? error.message : '加载解读详情失败')
  } finally {
    loading.value = false
  }
}

const runInterpret = async () => {
  interpreting.value = true
  try {
    const res = await bidApi.interpretBidProject(projectId.value)
    detail.value = res.data
    toast.success('解读完成，请核对需求清单')
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '解读失败')
  } finally {
    interpreting.value = false
  }
}

const changeStatus = async (status: string) => {
  try {
    const res = await bidApi.updateBidProjectStatus(projectId.value, status as BidProjectStatus)
    if (detail.value) {
      detail.value = { ...detail.value, project: res.data }
    }
    toast.success(`项目状态已更新为「${STATUS_LABELS[status as BidProjectStatus]}」`)
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '更新状态失败')
  }
}

const changeRequirementStatus = async (requirement: BidRequirement, status: BidRequirement['satisfiedStatus']) => {
  try {
    await bidApi.updateBidRequirementStatus(projectId.value, requirement.id, status)
    requirement.satisfiedStatus = status
    toast.success('需求状态已更新')
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '更新需求状态失败')
  }
}

onMounted(loadDetail)
</script>

<template>
  <div class="container mx-auto max-w-6xl px-4 py-6">
    <!-- 步骤导航：解读 → 需求确认 → 撰写 / 自检 -->
    <nav class="mb-6 flex flex-wrap items-center gap-2 text-sm">
      <span class="inline-flex items-center gap-1 rounded-full bg-primary px-3 py-1 font-medium text-primary-foreground">
        <FileSearch class="h-4 w-4" /> 解读
      </span>
      <span class="text-muted-foreground">→</span>
      <Button variant="ghost" size="sm" @click="router.push(`/bid/projects/${projectId}/requirements`)">
        <CheckCircle2 class="mr-1 h-4 w-4" /> 需求确认
      </Button>
      <span class="text-muted-foreground">→</span>
      <Button variant="ghost" size="sm" @click="router.push(`/bid/projects/${projectId}/draft`)">
        <PenLine class="mr-1 h-4 w-4" /> 撰写 / 自检
      </Button>
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
        <div class="flex items-center gap-2">
          <Select
            :model-value="project.status"
            :options="STATUS_OPTIONS"
            class="w-36"
            :disabled="interpreting"
            @update:model-value="changeStatus"
          />
          <Button :disabled="interpreting" @click="runInterpret">
            <Loader2 v-if="interpreting" class="mr-1 h-4 w-4 animate-spin" />
            <RefreshCw v-else class="mr-1 h-4 w-4" />
            重新解读
          </Button>
        </div>
      </div>
    </div>

    <!-- 免责声明（P0-8 风险合规） -->
    <div
      v-if="project"
      class="mb-6 flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800"
    >
      <ShieldCheck class="mt-0.5 h-4 w-4 shrink-0" />
      <div>
        <p class="font-medium">AI 解读结果仅供参考</p>
        <p class="mt-1 text-amber-700/90">
          以下要素、评分办法与需求清单由 AI 依据招标文件生成，可能出错或遗漏。提交标书前请以招标文件原文为准，
          并请具备招投标经验的人员复核带「需人工复核」标记的内容。
        </p>
      </div>
    </div>

    <LoadingSkeleton v-if="loading" type="card" :count="4" />
    <ErrorState
      v-else-if="loadError"
      title="加载失败"
      message="无法加载投标项目解读详情，请稍后重试"
      @retry="loadDetail"
    />

    <template v-else-if="detail">
      <!-- 关键要素 -->
      <section class="mb-8">
        <div class="mb-3 flex items-center justify-between">
          <h2 class="text-lg font-semibold">关键要素</h2>
          <span class="text-xs text-muted-foreground">共 {{ elements.length }} 项</span>
        </div>
        <EmptyState
          v-if="elements.length === 0"
          :icon="FileSearch"
          title="尚未解读要素"
          description="点击右上角「解读」按钮，AI 将从招标文件中抽取关键要素"
        />
        <div v-else class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          <Card v-for="element in elements" :key="element.id">
            <CardContent class="p-4">
              <div class="mb-1 flex items-center justify-between gap-2">
                <h3 class="text-sm font-medium text-muted-foreground">{{ elementLabel(element) }}</h3>
                <span v-if="element.confidence !== null && element.confidence !== undefined"
                      class="text-xs" :class="element.confidence >= 0.6 ? 'text-emerald-600' : 'text-amber-600'">
                  置信 {{ formatConfidence(element.confidence) }}
                </span>
              </div>
              <p class="whitespace-pre-wrap break-words text-sm font-medium">
                {{ element.elementValue || '—' }}
              </p>
              <p v-if="element.sourceClause" class="mt-2 line-clamp-3 text-xs text-muted-foreground">
                原文：{{ element.sourceClause }}
              </p>
              <div v-if="parseEvidence(element).length" class="mt-2 flex flex-wrap gap-1">
                <span
                  v-for="chunkId in parseEvidence(element)"
                  :key="chunkId"
                  class="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground"
                  :title="`证据来源：${chunkId}`"
                >
                  {{ chunkId }}
                </span>
              </div>
            </CardContent>
          </Card>
        </div>
      </section>

      <!-- 评分办法 -->
      <section class="mb-8">
        <div class="mb-3 flex items-center justify-between">
          <h2 class="text-lg font-semibold">评分办法</h2>
          <span class="text-xs text-muted-foreground">共 {{ scoringMethods.length }} 项</span>
        </div>
        <EmptyState
          v-if="scoringMethods.length === 0"
          :icon="FileSearch"
          title="尚未解读评分办法"
          description="解读后此处展示评分方法、总分与分项权重"
        />
        <div v-else class="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card v-for="method in scoringMethods" :key="method.id">
            <CardContent class="p-4">
              <div class="mb-2 flex items-center justify-between">
                <h3 class="text-sm font-medium">
                  {{ method.methodType === 'comprehensive' ? '综合评分法' : method.methodType === 'lowest_price' ? '经评审最低价法' : method.methodType }}
                </h3>
                <span v-if="method.totalScore !== null && method.totalScore !== undefined"
                      class="text-sm font-semibold text-primary">总分 {{ method.totalScore }}</span>
              </div>
              <div v-if="parsePoints(method).length" class="space-y-1.5">
                <div
                  v-for="(point, index) in parsePoints(method)"
                  :key="index"
                  class="flex items-center justify-between gap-3 border-t border-border pt-1.5 text-sm"
                >
                  <span class="min-w-0 break-words">{{ point.name }}</span>
                  <span class="shrink-0 text-muted-foreground">{{ point.score }}</span>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </section>

      <!-- 需求清单 -->
      <section class="mb-8">
        <div class="mb-3 flex items-center justify-between">
          <h2 class="text-lg font-semibold">投标需求清单</h2>
          <span class="text-xs text-muted-foreground">
            共 {{ requirements.length }} 项
            <span v-if="manualReviewCount > 0" class="ml-1 text-amber-600">{{ manualReviewCount }} 项需人工复核</span>
          </span>
        </div>
        <EmptyState
          v-if="requirements.length === 0"
          :icon="FileSearch"
          title="尚未生成需求清单"
          description="解读后此处列出投标须满足的全部需求，便于逐项确认"
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
      </section>
    </template>
  </div>
</template>
