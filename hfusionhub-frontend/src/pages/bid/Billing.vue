<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  BadgeCheck, BookTemplate, CircleDollarSign, FileSearch, Package,
  Plus, RefreshCw, Sparkles, Unplug, Users,
} from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import * as planApi from '@/api/plan'
import type { BidSubscription, BidTemplate, PlanCurrent } from '@/api/plan'
import { BID_MODULE_LABELS, formatCents, parseModuleFlags } from '@/api/plan'
import * as quotaApi from '@/api/quota'
import type { QuotaSummary } from '@/api/quota'
import * as demoApi from '@/api/demo'
import { useUserStore } from '@/stores/user'
import { useToast } from '@/composables/useToast'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select } from '@/components/ui/select'
import LoadingSkeleton from '@/components/LoadingSkeleton.vue'
import EmptyState from '@/components/EmptyState.vue'

const router = useRouter()
const toast = useToast()
const userStore = useUserStore()
const isAdmin = computed(() => userStore.isAdmin)

const loading = ref(false)
const plans = ref<BidSubscription[]>([])
const current = ref<PlanCurrent | null>(null)
const quotas = ref<QuotaSummary[]>([])
const templates = ref<BidTemplate[]>([])
const activeTab = ref<'catalog' | 'templates'>('catalog')
const templateIndustry = ref('')
const bindingBusy = ref<number | null>(null)
const trialBusy = ref<string | null>(null)
const templateLoading = ref(false)
const savingTemplate = ref(false)
const templateDialogOpen = ref(false)

const tierLabel = (tier: string) =>
  ({ free: '免费版', pro: '专业版', enterprise: '企业版', industry_construction: '工程施工行业方案包', industry_it: 'IT 集成行业方案包' })[tier] ?? tier

const quotaBarClass = (percent: number) => {
  if (percent >= 90) return 'bg-rose-500'
  if (percent >= 70) return 'bg-amber-500'
  return 'bg-primary'
}

const industryFilterOptions = [
  { label: '全部行业', value: '' },
  { label: '工程施工', value: 'construction' },
  { label: 'IT 集成', value: 'it' },
]

const templateForm = ref({
  name: '',
  description: '',
  industry: 'construction',
  sectionDefs: '[{"key":"commercial","title":"商务标"},{"key":"technical","title":"技术标"}]',
})

function moduleEnabled(plan: BidSubscription, module: planApi.BidModule): boolean {
  return parseModuleFlags(plan.moduleFlags)[module] ?? false
}

function moduleEnabledCurrent(module: planApi.BidModule): boolean {
  return Boolean(current.value?.modules?.[module])
}

function planBoundIds(): Set<number> {
  return new Set((current.value?.bindings ?? [])
    .filter(b => b.status === 'active')
    .map(b => b.subscriptionId))
}

const boundIds = computed(() => planBoundIds())

function sectionCount(template: BidTemplate): number {
  try {
    const sections = JSON.parse(template.sectionDefs)
    return Array.isArray(sections) ? sections.length : 0
  } catch {
    return 0
  }
}

async function loadAll() {
  loading.value = true
  try {
    const [plansRes, currentRes, quotaRes] = await Promise.all([
      planApi.listPlatformPlans(),
      planApi.getPlanCurrent(),
      quotaApi.getQuotaSummary(),
    ])
    plans.value = plansRes.data
    current.value = currentRes.data
    quotas.value = quotaRes.data ?? []
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '加载套餐信息失败')
  } finally {
    loading.value = false
  }
}

async function loadTemplates() {
  templateLoading.value = true
  try {
    const response = await planApi.listBidTemplates(templateIndustry.value || undefined)
    templates.value = response.data
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '加载模板列表失败')
  } finally {
    templateLoading.value = false
  }
}

function changeTemplateIndustry(value: string) {
  templateIndustry.value = value
  void loadTemplates()
}

async function handleBind(plan: BidSubscription) {
  bindingBusy.value = plan.id
  try {
    await planApi.bindPlan(plan.id)
    toast.success(`已绑定套餐「${plan.planName}」`)
    await loadAll()
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '绑定套餐失败')
  } finally {
    bindingBusy.value = null
  }
}

async function handleUnbind(bindingId: number, planName: string) {
  bindingBusy.value = bindingId
  try {
    await planApi.unbindPlan(bindingId)
    toast.success(`已解绑套餐「${planName}」`)
    await loadAll()
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '解绑套餐失败')
  } finally {
    bindingBusy.value = null
  }
}

async function handleTrial(industry: string) {
  trialBusy.value = industry
  try {
    const response = await demoApi.importBidIndustrySamples(industry)
    toast.success(response.data.message)
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '导入免费试用样例失败')
  } finally {
    trialBusy.value = null
  }
}

async function handleCreateTemplate() {
  if (!templateForm.value.name.trim()) {
    toast.error('模板名称不能为空')
    return
  }
  try {
    JSON.parse(templateForm.value.sectionDefs)
  } catch {
    toast.error('分节定义必须是合法 JSON 数组，如 [{"key":"commercial","title":"商务标"}]')
    return
  }
  savingTemplate.value = true
  try {
    await planApi.createBidTemplate(templateForm.value)
    toast.success('模板已创建')
    templateDialogOpen.value = false
    templateForm.value.name = ''
    templateForm.value.description = ''
    await loadTemplates()
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '创建模板失败')
  } finally {
    savingTemplate.value = false
  }
}

onMounted(() => {
  void loadAll()
  void loadTemplates()
})
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-6 p-6">
    <div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div>
        <h1 class="flex items-center gap-2 text-xl font-semibold">
          <Package class="h-5 w-5 text-primary" />
          套餐中心
        </h1>
        <p class="mt-1 text-sm text-muted-foreground">
          选择投标套餐（基础档位 / 行业方案包）并按模块生效状态使用标书撰写、废标自检、开放 API 等能力。
        </p>
      </div>
      <div class="flex items-center gap-2">
        <Button variant="outline" size="sm" class="gap-2" @click="router.push('/cost')">
          <CircleDollarSign class="h-4 w-4" />用量与费用
        </Button>
        <Button variant="outline" size="icon" title="刷新套餐信息" :disabled="loading" @click="loadAll">
          <RefreshCw class="h-4 w-4" :class="loading && 'animate-spin'" />
        </Button>
      </div>
    </div>

    <LoadingSkeleton v-if="loading && !current" type="card" :count="3" />

    <template v-else-if="current">
      <!-- 当前套餐概览 -->
      <section class="rounded-lg border border-border bg-card/35 p-5">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p class="flex items-center gap-2 text-sm text-muted-foreground">
              <BadgeCheck class="h-4 w-4 text-emerald-400" />当前档位
            </p>
            <p class="mt-1 text-xl font-semibold">{{ tierLabel(current.tier) }}</p>
          </div>
          <div class="flex flex-wrap gap-2">
            <Badge v-for="module in (Object.keys(BID_MODULE_LABELS) as planApi.BidModule[])" :key="module" :variant="moduleEnabledCurrent(module) ? 'default' : 'outline'">
              {{ BID_MODULE_LABELS[module] }} {{ moduleEnabledCurrent(module) ? '已开通' : '未开通' }}
            </Badge>
          </div>
        </div>

        <div v-if="current.bindings.length" class="mt-5 border-t border-border/70 pt-4">
          <p class="text-sm font-medium">已绑定套餐</p>
          <ul class="mt-3 space-y-2">
            <li v-for="binding in current.bindings" :key="binding.bindingId" class="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border/70 bg-muted/20 px-4 py-3">
              <div class="min-w-0">
                <p class="text-sm font-medium">{{ binding.planName }}</p>
                <p class="mt-0.5 text-xs text-muted-foreground">
                  {{ binding.planType === 'industry' ? '行业方案包' : '基础档位' }} ·
                  最多 {{ binding.maxProjects }} 个项目 · {{ binding.maxSeats }} 坐席 ·
                  月度字符 {{ (binding.charQuota / 10000).toFixed(0) }} 万 · {{ formatCents(binding.priceCents) }}/月
                </p>
              </div>
              <Button variant="outline" size="sm" class="gap-1.5" :disabled="bindingBusy === binding.bindingId" @click="handleUnbind(binding.subscriptionId, binding.planName)">
                <Unplug class="h-3.5 w-3.5" />解绑
              </Button>
            </li>
          </ul>
        </div>
      </section>

      <!-- 今日配额（复用 /cost 账本） -->
      <section v-if="quotas.length" class="rounded-lg border border-border bg-card/35 p-5">
        <div class="flex items-center justify-between">
          <h2 class="text-sm font-medium">今日用量配额</h2>
          <span class="text-xs text-muted-foreground">每日 00:00 重置 · 详见「用量与费用」</span>
        </div>
        <div class="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <div v-for="quota in quotas" :key="quota.meter">
            <div class="flex items-baseline justify-between gap-3 text-sm">
              <span class="font-medium">{{ quota.label }}</span>
              <span class="shrink-0 text-muted-foreground">{{ quota.used.toLocaleString() }} / {{ quota.dailyLimit.toLocaleString() }} {{ quota.unit }}</span>
            </div>
            <div class="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
              <div class="h-full rounded-full" :class="quotaBarClass(quota.percent)" :style="{ width: `${Math.min(quota.percent, 100)}%` }" />
            </div>
          </div>
        </div>
      </section>

      <!-- 选项卡：套餐目录 / 模板商城 -->
      <div class="flex gap-1 rounded-lg border border-border bg-muted/20 p-1 w-fit">
        <button class="rounded-md px-4 py-2 text-sm font-medium" :class="activeTab === 'catalog' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'" @click="activeTab = 'catalog'">套餐目录</button>
        <button class="rounded-md px-4 py-2 text-sm font-medium" :class="activeTab === 'templates' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'" @click="activeTab = 'templates'">模板商城</button>
      </div>

      <!-- 套餐目录 -->
      <section v-if="activeTab === 'catalog'" class="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        <div v-for="plan in plans" :key="plan.id" class="flex flex-col rounded-lg border border-border bg-card/35 p-5">
          <div class="flex items-start justify-between gap-3">
            <div>
              <h3 class="font-semibold">{{ plan.planName }}</h3>
              <p class="mt-0.5 text-xs text-muted-foreground">
                {{ plan.planType === 'industry' ? '行业方案包' : '基础档位' }} · {{ plan.planCode }}
              </p>
            </div>
            <p class="text-lg font-semibold text-primary">{{ formatCents(plan.priceCents) }}<span class="text-xs font-normal text-muted-foreground">/月</span></p>
          </div>

          <ul class="mt-4 space-y-1.5 text-sm text-muted-foreground">
            <li class="flex gap-2"><Users class="h-4 w-4 shrink-0 text-primary/70" />最多 {{ plan.maxProjects }} 个投标项目</li>
            <li class="flex gap-2"><Users class="h-4 w-4 shrink-0 text-primary/70" />{{ plan.maxSeats }} 个协作坐席</li>
            <li class="flex gap-2"><FileSearch class="h-4 w-4 shrink-0 text-primary/70" />标书撰写字符 {{ (plan.charQuota / 10000).toFixed(0) }} 万/月</li>
          </ul>

          <div class="mt-4 flex flex-wrap gap-1.5">
            <Badge v-for="module in (Object.keys(BID_MODULE_LABELS) as planApi.BidModule[])" :key="module" :variant="moduleEnabled(plan, module) ? 'default' : 'outline'">
              {{ BID_MODULE_LABELS[module] }}
            </Badge>
          </div>

          <div class="mt-auto pt-5">
            <template v-if="plan.planType === 'industry' && isAdmin">
              <Button variant="outline" size="sm" class="mb-2 w-full gap-1.5" :disabled="trialBusy === plan.planCode" @click="handleTrial(plan.planCode.replace('industry_', ''))">
                <Sparkles class="h-3.5 w-3.5" />{{ trialBusy === plan.planCode ? '导入中…' : '导入免费试用样例' }}
              </Button>
            </template>
            <Button
              class="w-full gap-1.5"
              :disabled="boundIds.has(plan.id) || bindingBusy === plan.id"
              @click="handleBind(plan)"
            >
              <BadgeCheck class="h-4 w-4" />
              {{ boundIds.has(plan.id) ? '已绑定' : '立即绑定' }}
            </Button>
          </div>
        </div>
      </section>

      <!-- 模板商城 -->
      <section v-else>
        <div class="flex flex-wrap items-center justify-between gap-3">
          <p class="text-sm text-muted-foreground">
            平台预置行业标书模板（工程施工 / IT 集成）+ 本租户私有模板，撰写标书时按分节自动套用。
          </p>
          <div class="flex items-center gap-2">
            <Select :model-value="templateIndustry" placeholder="全部行业" :options="industryFilterOptions" @update:model-value="changeTemplateIndustry" />
            <Dialog v-model:open="templateDialogOpen">
              <DialogTrigger as-child>
                <Button size="sm" class="gap-1.5"><Plus class="h-4 w-4" />新建模板</Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>新建标书模板</DialogTitle>
                  <DialogDescription>创建本租户私有模板；平台级模板由管理员统一维护，只读。</DialogDescription>
                </DialogHeader>
                <div class="space-y-4 py-2">
                  <div class="space-y-2">
                    <Label>模板名称</Label>
                    <Input v-model="templateForm.name" placeholder="如：市政道路标书模板" />
                  </div>
                  <div class="space-y-2">
                    <Label>模板说明</Label>
                    <Input v-model="templateForm.description" placeholder="该模板的适用场景" />
                  </div>
                  <div class="space-y-2">
                    <Label>行业分类</Label>
                    <Select v-model="templateForm.industry" :options="[{ label: '工程施工', value: 'construction' }, { label: 'IT 集成', value: 'it' }]" />
                  </div>
                  <div class="space-y-2">
                    <Label>分节定义（JSON 数组）</Label>
                    <Textarea v-model="templateForm.sectionDefs" :rows="4" class="font-mono text-xs" />
                    <p class="text-xs text-muted-foreground">格式：[{"key":"commercial","title":"商务标"}]，key 对应撰写分节（commercial/technical/qualification/org…）</p>
                  </div>
                </div>
                <DialogFooter>
                  <Button variant="outline" @click="templateDialogOpen = false">取消</Button>
                  <Button :disabled="savingTemplate" @click="handleCreateTemplate">{{ savingTemplate ? '保存中…' : '创建' }}</Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
        </div>

        <LoadingSkeleton v-if="templateLoading" type="card" :count="3" />
        <EmptyState v-else-if="!templates.length" :icon="BookTemplate" title="暂无标书模板" description="可在套餐目录开通行业方案包，或点击「新建模板」创建私有模板。" />
        <div v-else class="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          <div v-for="template in templates" :key="template.id" class="flex flex-col rounded-lg border border-border bg-card/35 p-5">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <h3 class="flex items-center gap-2 font-semibold">
                  <BookTemplate class="h-4 w-4 shrink-0 text-primary/70" />
                  <span class="truncate">{{ template.name }}</span>
                </h3>
                <p class="mt-1 text-xs text-muted-foreground">
                  {{ template.industry === 'construction' ? '工程施工' : template.industry === 'it' ? 'IT 集成' : template.industry || '通用' }} ·
                  {{ template.tenantId == null ? '平台模板' : '本租户' }}
                </p>
              </div>
              <Badge variant="outline">{{ sectionCount(template) }} 分节</Badge>
            </div>
            <p v-if="template.description" class="mt-3 line-clamp-2 text-sm text-muted-foreground">{{ template.description }}</p>
          </div>
        </div>
      </section>
    </template>

    <div v-else class="py-16 text-center">
      <p class="text-sm text-muted-foreground">暂时无法读取套餐信息</p>
      <Button variant="outline" class="mt-4 gap-2" @click="loadAll"><RefreshCw class="h-4 w-4" />重新加载</Button>
    </div>
  </div>
</template>
