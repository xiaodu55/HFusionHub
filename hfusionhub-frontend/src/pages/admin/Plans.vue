<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Archive, Package, Pencil, Plus, RefreshCw } from 'lucide-vue-next'
import * as planApi from '@/api/plan'
import type { BidSubscription } from '@/api/plan'
import { BID_MODULE_LABELS, formatCents, parseModuleFlags } from '@/api/plan'
import { useToast } from '@/composables/useToast'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import LoadingSkeleton from '@/components/LoadingSkeleton.vue'
import EmptyState from '@/components/EmptyState.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'

const toast = useToast()
const loading = ref(false)
const plans = ref<BidSubscription[]>([])
const saving = ref(false)
const archiveTarget = ref<BidSubscription | null>(null)
const confirmArchiveOpen = ref(false)
const archiveLoading = ref(false)
const editOpen = ref(false)

const emptyForm = () => ({
  id: undefined as number | undefined,
  planCode: '',
  planName: '',
  planType: 'tier' as 'tier' | 'industry',
  priceCents: 0,
  maxProjects: 3,
  maxSeats: 3,
  charQuota: 100000,
  moduleFlags: '{"draft":1,"check":1,"docx":0,"openapi":0}',
})

const form = ref(emptyForm())

const planTypeOptions = [
  { label: '基础档位', value: 'tier' },
  { label: '行业方案包', value: 'industry' },
]

const editing = computed(() => form.value.id != null)

function moduleEnabled(plan: BidSubscription, module: planApi.BidModule): boolean {
  return parseModuleFlags(plan.moduleFlags)[module] ?? false
}

async function load() {
  loading.value = true
  try {
    const response = await planApi.listAllPlans()
    plans.value = response.data
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '加载套餐失败')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  form.value = emptyForm()
  editOpen.value = true
}

function openEdit(plan: BidSubscription) {
  form.value = {
    id: plan.id,
    planCode: plan.planCode,
    planName: plan.planName,
    planType: plan.planType,
    priceCents: plan.priceCents,
    maxProjects: plan.maxProjects,
    maxSeats: plan.maxSeats,
    charQuota: plan.charQuota,
    moduleFlags: plan.moduleFlags,
  }
  editOpen.value = true
}

async function handleSave() {
  if (!form.value.planName.trim() || !form.value.planCode.trim()) {
    toast.error('套餐名称与代码不能为空')
    return
  }
  try {
    JSON.parse(form.value.moduleFlags)
  } catch {
    toast.error('模块开关必须是合法 JSON，如 {"draft":1,"check":1,"docx":0,"openapi":0}')
    return
  }
  saving.value = true
  try {
    if (editing.value) {
      await planApi.updatePlan(form.value)
      toast.success('套餐已更新')
    } else {
      await planApi.createPlan(form.value)
      toast.success('套餐已创建')
    }
    editOpen.value = false
    await load()
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '保存套餐失败')
  } finally {
    saving.value = false
  }
}

async function handleArchive() {
  if (!archiveTarget.value) return
  archiveLoading.value = true
  try {
    await planApi.archivePlan(archiveTarget.value.id)
    toast.success(`套餐「${archiveTarget.value.planName}」已归档`)
    confirmArchiveOpen.value = false
    archiveTarget.value = null
    await load()
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '归档套餐失败')
  } finally {
    archiveLoading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="mx-auto max-w-6xl space-y-6 p-6">
    <div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div>
        <h1 class="flex items-center gap-2 text-xl font-semibold">
          <Package class="h-5 w-5 text-primary" />
          套餐管理
        </h1>
        <p class="mt-1 text-sm text-muted-foreground">
          维护平台套餐目录（基础档位 / 行业方案包）。归档后不再可选，历史绑定不受影响。
        </p>
      </div>
      <div class="flex items-center gap-2">
        <Button variant="outline" size="icon" title="刷新套餐" :disabled="loading" @click="load">
          <RefreshCw class="h-4 w-4" :class="loading && 'animate-spin'" />
        </Button>
        <Button class="gap-1.5" @click="openCreate"><Plus class="h-4 w-4" />新建套餐</Button>
      </div>
    </div>

    <LoadingSkeleton v-if="loading" type="card" :count="3" />
    <EmptyState v-else-if="!plans.length" :icon="Package" title="暂无套餐" description="点击「新建套餐」创建平台套餐目录。" />

    <div v-else class="overflow-hidden rounded-lg border border-border bg-card/35">
      <div class="overflow-x-auto">
        <table class="w-full min-w-[820px] text-sm">
          <thead class="bg-muted/20 text-left text-xs text-muted-foreground">
            <tr>
              <th class="px-5 py-3">套餐</th>
              <th class="px-5 py-3">类型</th>
              <th class="px-5 py-3 text-right">价格/月</th>
              <th class="px-5 py-3 text-right">项目</th>
              <th class="px-5 py-3 text-right">坐席</th>
              <th class="px-5 py-3 text-right">字符额度</th>
              <th class="px-5 py-3">模块</th>
              <th class="px-5 py-3">状态</th>
              <th class="px-5 py-3 text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="plan in plans" :key="plan.id" class="border-t border-border/70">
              <td class="px-5 py-4">
                <p class="font-medium">{{ plan.planName }}</p>
                <p class="mt-0.5 text-xs text-muted-foreground">{{ plan.planCode }}</p>
              </td>
              <td class="px-5 py-4">
                <Badge :variant="plan.planType === 'industry' ? 'default' : 'outline'">
                  {{ plan.planType === 'industry' ? '行业方案包' : '基础档位' }}
                </Badge>
              </td>
              <td class="px-5 py-4 text-right">{{ formatCents(plan.priceCents) }}</td>
              <td class="px-5 py-4 text-right">{{ plan.maxProjects }}</td>
              <td class="px-5 py-4 text-right">{{ plan.maxSeats }}</td>
              <td class="px-5 py-4 text-right">{{ (plan.charQuota / 10000).toFixed(0) }} 万</td>
              <td class="px-5 py-4">
                <div class="flex max-w-[220px] flex-wrap gap-1">
                  <Badge v-for="module in (Object.keys(BID_MODULE_LABELS) as planApi.BidModule[])" :key="module" variant="outline" class="text-[10px]" :class="moduleEnabled(plan, module) ? '' : 'opacity-40'">
                    {{ BID_MODULE_LABELS[module] }}
                  </Badge>
                </div>
              </td>
              <td class="px-5 py-4">
                <Badge :variant="plan.status === 'active' ? 'default' : 'outline'">
                  {{ plan.status === 'active' ? '在售' : '已归档' }}
                </Badge>
              </td>
              <td class="px-5 py-4">
                <div class="flex justify-end gap-1.5">
                  <Button variant="outline" size="icon" title="编辑" @click="openEdit(plan)"><Pencil class="h-4 w-4" /></Button>
                  <Button v-if="plan.status === 'active'" variant="outline" size="icon" title="归档" class="text-rose-400 hover:text-rose-300" @click="archiveTarget = plan; confirmArchiveOpen = true"><Archive class="h-4 w-4" /></Button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 新建 / 编辑套餐 -->
    <Dialog v-model:open="editOpen">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{{ editing ? '编辑套餐' : '新建套餐' }}</DialogTitle>
          <DialogDescription>平台目录套餐对所有租户可见；模块开关控制该套餐授权的投标能力。</DialogDescription>
        </DialogHeader>
        <div class="space-y-4 py-2">
          <div class="grid grid-cols-2 gap-4">
            <div class="space-y-2">
              <Label>套餐名称</Label>
              <Input v-model="form.planName" placeholder="如：专业版" />
            </div>
            <div class="space-y-2">
              <Label>套餐代码</Label>
              <Input v-model="form.planCode" placeholder="如：pro / industry_it" />
            </div>
          </div>
          <div class="grid grid-cols-3 gap-4">
            <div class="space-y-2">
              <Label>类型</Label>
              <Select v-model="form.planType" :options="planTypeOptions" />
            </div>
            <div class="space-y-2">
              <Label>价格（分/月）</Label>
              <Input v-model.number="form.priceCents" type="number" min="0" />
            </div>
            <div class="space-y-2">
              <Label>最大项目数</Label>
              <Input v-model.number="form.maxProjects" type="number" min="0" />
            </div>
          </div>
          <div class="grid grid-cols-2 gap-4">
            <div class="space-y-2">
              <Label>最大坐席数</Label>
              <Input v-model.number="form.maxSeats" type="number" min="0" />
            </div>
            <div class="space-y-2">
              <Label>字符额度（/月）</Label>
              <Input v-model.number="form.charQuota" type="number" min="0" step="10000" />
            </div>
          </div>
          <div class="space-y-2">
            <Label>模块开关（JSON）</Label>
            <Input v-model="form.moduleFlags" class="font-mono text-xs" placeholder="{&quot;draft&quot;:1,&quot;check&quot;:1,&quot;docx&quot;:0,&quot;openapi&quot;:0}" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="editOpen = false">取消</Button>
          <Button :disabled="saving" @click="handleSave">{{ saving ? '保存中…' : '保存' }}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <ConfirmDialog
      v-model:open="confirmArchiveOpen"
      title="归档套餐"
      description="归档后该套餐不再可选，历史绑定不受影响。确定归档「{{ archiveTarget?.planName }}」？"
      confirm-text="归档"
      :loading="archiveLoading"
      @confirm="handleArchive"
    />
  </div>
</template>
