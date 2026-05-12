<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowLeftRight,
  Archive,
  BookOpenText,
  Check,
  CirclePlus,
  Clock,
  Copy,
  History,
  Layers3,
  LoaderCircle,
  PenLine,
  Rocket,
  RotateCcw,
  Search,
  Send,
  Trash2,
} from 'lucide-vue-next'
import * as promptTemplateApi from '@/api/promptTemplate'
import type { PromptTemplate, PromptTemplateSaveDTO, PromptTemplateVersion } from '@/api/promptTemplate'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useToast } from '@/composables/useToast'
import { formatDateTime } from '@/utils/date'
import ConfirmDialog from '@/components/ConfirmDialog.vue'

type Filter = 'ALL' | promptTemplateApi.PromptTemplateStatus

const toast = useToast()
const router = useRouter()
const templates = ref<PromptTemplate[]>([])
const selectedId = ref<number | null>(null)
const filter = ref<Filter>('ALL')
const query = ref('')
const loading = ref(false)
const saving = ref(false)
const actionLoading = ref(false)
const showCreateDialog = ref(false)
const createForm = ref<PromptTemplateSaveDTO>({ name: '', description: '', content: '' })
const editForm = ref<PromptTemplateSaveDTO>({ name: '', description: '', content: '' })

type PromptExample = PromptTemplateSaveDTO & {
  id: string
  scenario: string
  question: string
}

const promptExamples: PromptExample[] = [
  {
    id: 'customer-support',
    name: '客服答疑',
    description: '适合售前、售后和制度咨询，统一先给结论再给处理步骤。',
    scenario: '客服、售后、制度咨询',
    question: '会员到期后还能导出数据吗？',
    content: `你是企业客服助手，请使用简洁、友好的中文回答。
回答顺序：
1. 先直接给出结论；
2. 再列出最多 5 个处理步骤；
3. 使用知识库资料时标明来源；
4. 资料不足时明确说明“现有资料不足”，不要猜测；
5. 涉及退款、权限或人工审批时，提醒用户联系人工客服。`,
  },
  {
    id: 'document-summary',
    name: '文档总结',
    description: '把长文整理成重点、风险和下一步行动，适合内部资料阅读。',
    scenario: '会议纪要、制度、方案总结',
    question: '请总结这份产品发布方案，并列出上线前必须确认的事项。',
    content: `你是文档整理助手，请严格依据用户提供的资料回答，不补充资料中没有的信息。
请按以下结构输出：
1. 一句话结论；
2. 关键要点（3 到 6 条）；
3. 风险或待确认事项；
4. 下一步行动。
内容较长时优先使用分组标题和项目符号，保持表达清晰。`,
  },
  {
    id: 'code-review',
    name: '代码审查',
    description: '统一代码评审格式，优先发现安全、正确性和维护性问题。',
    scenario: '代码评审、缺陷排查、重构建议',
    question: '请审查这段代码，重点关注并发安全和异常处理。',
    content: `你是资深代码审查助手，请先指出影响正确性或安全性的高风险问题。
请按以下结构输出：
1. 问题等级：严重、高、中、低；
2. 问题位置和原因；
3. 修改建议，必要时给出简短代码示例；
4. 没有发现问题的方面也要明确说明。
不要为了凑数量而提出无关紧要的建议。`,
  },
]

// ── Version history ──────────────────────────────────────────────────

const showVersionHistory = ref(false)
const versions = ref<PromptTemplateVersion[]>([])
const versionsLoading = ref(false)
const versionsError = ref('')
const selectedVersion = ref<PromptTemplateVersion | null>(null)
const rollbackLoading = ref(false)
const deleteTarget = ref<PromptTemplate | null>(null)
const confirmDeleteOpen = ref(false)
const confirmDeleteLoading = ref(false)
const rollbackTarget = ref<PromptTemplateVersion | null>(null)
const confirmRollbackOpen = ref(false)
const confirmRollbackLoading = ref(false)

const selected = computed(() => templates.value.find((template) => template.id === selectedId.value) || null)
const filteredTemplates = computed(() => {
  const keyword = query.value.trim().toLowerCase()
  return templates.value.filter((template) => {
    const matchesFilter = filter.value === 'ALL' || template.status === filter.value
    const matchesQuery = !keyword || [template.name, template.description, template.content]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(keyword))
    return matchesFilter && matchesQuery
  })
})
const publishedCount = computed(() => templates.value.filter((template) => template.status === 'PUBLISHED').length)
const draftCount = computed(() => templates.value.filter((template) => template.status === 'DRAFT').length)
const hasChanges = computed(() => selected.value !== null && (
  selected.value.name !== editForm.value.name.trim()
  || (selected.value.description || '') !== (editForm.value.description?.trim() || '')
  || selected.value.content !== editForm.value.content.trim()
))

const openCreateDialog = (example?: PromptExample) => {
  createForm.value = example
    ? { name: example.name, description: example.description, content: example.content }
    : { name: '', description: '', content: '' }
  showCreateDialog.value = true
}

// ── Version display helpers ──────────────────────────────────────────

const opLabel = (op: promptTemplateApi.VersionOperation) => {
  const map: Record<string, string> = {
    CREATE: '创建',
    EDIT: '编辑',
    PUBLISH: '发布',
    UNPUBLISH: '撤回',
    ROLLBACK: '回滚',
  }
  return map[op] || op
}

const opClass = (op: promptTemplateApi.VersionOperation) => {
  const map: Record<string, string> = {
    CREATE: 'border-emerald-400/25 bg-emerald-400/10 text-emerald-300',
    EDIT: 'border-cyan-400/25 bg-cyan-400/10 text-cyan-200',
    PUBLISH: 'border-emerald-400/25 bg-emerald-400/10 text-emerald-300',
    UNPUBLISH: 'border-amber-400/25 bg-amber-400/10 text-amber-200',
    ROLLBACK: 'border-violet-400/25 bg-violet-400/10 text-violet-200',
  }
  return map[op] || 'border-border bg-muted text-muted-foreground'
}

const isDifferentFromCurrent = (version: PromptTemplateVersion) => {
  if (!selected.value) return false
  return version.content !== selected.value.content
      || version.name !== selected.value.name
      || (version.description || '') !== (selected.value.description || '')
}

const selectTemplate = (template: PromptTemplate) => {
  selectedId.value = template.id
  editForm.value = {
    name: template.name,
    description: template.description || '',
    content: template.content,
  }
}

const loadTemplates = async () => {
  loading.value = true
  try {
    const response = await promptTemplateApi.listPromptTemplates()
    templates.value = response.data
    const active = response.data.find((template) => template.id === selectedId.value) || response.data[0]
    if (active) selectTemplate(active)
    else selectedId.value = null
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '加载提示词模板失败')
  } finally {
    loading.value = false
  }
}

const createTemplate = async () => {
  const payload = normalize(createForm.value)
  if (!payload.name || !payload.content || saving.value) return
  saving.value = true
  try {
    const response = await promptTemplateApi.createPromptTemplate(payload)
    templates.value.unshift(response.data)
    selectTemplate(response.data)
    showCreateDialog.value = false
    createForm.value = { name: '', description: '', content: '' }
    toast.success('回答方案草稿已创建。测试并发布后可在新建对话中使用。')
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '创建提示词模板失败')
  } finally {
    saving.value = false
  }
}

const saveTemplate = async () => {
  if (!selected.value || !hasChanges.value || saving.value) return
  saving.value = true
  try {
    const payload = { ...normalize(editForm.value), expectedVersion: selected.value.version }
    const response = await promptTemplateApi.updatePromptTemplate(selected.value.id, payload)
    replaceTemplate(response.data)
    selectTemplate(response.data)
    toast.success(`回答方案已保存为草稿，当前为版本 ${response.data.version}`)
  } catch (error) {
    handleVersionConflict(error, '保存提示词模板失败')
  } finally {
    saving.value = false
  }
}

const togglePublished = async () => {
  if (!selected.value || actionLoading.value) return
  actionLoading.value = true
  try {
    const expectedVersion = selected.value.version
    const response = selected.value.status === 'PUBLISHED'
      ? await promptTemplateApi.unpublishPromptTemplate(selected.value.id, expectedVersion)
      : await promptTemplateApi.publishPromptTemplate(selected.value.id, expectedVersion)
    replaceTemplate(response.data)
    selectTemplate(response.data)
    toast.success(response.data.status === 'PUBLISHED'
      ? '回答方案已发布，可在新建对话时选择。'
      : '回答方案已撤回，之后的回答将不再加载它。')
  } catch (error) {
    handleVersionConflict(error, '更新发布状态失败')
  } finally {
    actionLoading.value = false
  }
}

const deleteTemplate = () => {
  if (!selected.value) return
  deleteTarget.value = selected.value
  confirmDeleteOpen.value = true
}

const confirmDelete = async () => {
  const target = deleteTarget.value
  if (!target || actionLoading.value) return
  actionLoading.value = true
  confirmDeleteLoading.value = true
  try {
    await promptTemplateApi.deletePromptTemplate(target.id)
    templates.value = templates.value.filter((template) => template.id !== target.id)
    const next = templates.value[0]
    if (next) selectTemplate(next)
    else selectedId.value = null
    toast.success('回答方案已移入回收站，可在回收站恢复或永久删除')
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '删除提示词模板失败')
  } finally {
    actionLoading.value = false
    confirmDeleteLoading.value = false
    confirmDeleteOpen.value = false
    deleteTarget.value = null
  }
}

const duplicateTemplate = () => {
  if (!selected.value) return
  createForm.value = {
    name: `${selected.value.name}（副本）`,
    description: selected.value.description || '',
    content: selected.value.content,
  }
  showCreateDialog.value = true
}

// ── Version history ──────────────────────────────────────────────────

const openVersionHistory = async () => {
  if (!selected.value) return
  showVersionHistory.value = true
  selectedVersion.value = null
  versionsLoading.value = true
  versionsError.value = ''
  try {
    const res = await promptTemplateApi.listPromptTemplateVersions(selected.value.id)
    versions.value = res.data
  } catch (error) {
    versionsError.value = error instanceof Error ? error.message : '无法加载版本历史'
  } finally {
    versionsLoading.value = false
  }
}

const rollbackToVersion = () => {
  if (!selected.value || !selectedVersion.value) return
  rollbackTarget.value = selectedVersion.value
  confirmRollbackOpen.value = true
}

const confirmRollback = async () => {
  if (!selected.value || !rollbackTarget.value || rollbackLoading.value) return
  const targetVersion = rollbackTarget.value.version
  const versionId = rollbackTarget.value.id
  rollbackLoading.value = true
  confirmRollbackLoading.value = true
  try {
    const response = await promptTemplateApi.rollbackPromptTemplate(selected.value.id, versionId, selected.value.version)
    replaceTemplate(response.data)
    selectTemplate(response.data)
    showVersionHistory.value = false
    toast.success(`已回滚到 v${targetVersion}，当前为草稿（v${response.data.version}）。请确认内容后重新发布。`)
  } catch (error) {
    handleVersionConflict(error, '回滚失败')
  } finally {
    rollbackLoading.value = false
    confirmRollbackLoading.value = false
    confirmRollbackOpen.value = false
    rollbackTarget.value = null
  }
}

const handleVersionConflict = async (error: unknown, fallbackMessage: string) => {
  const msg = error instanceof Error ? error.message : ''
  if (msg.includes('已被其他操作更新')) {
    // Refresh to get the latest version from server
    await loadTemplates()
    // Also refresh version history if the dialog is open
    if (showVersionHistory.value && selected.value) {
      try {
        const res = await promptTemplateApi.listPromptTemplateVersions(selected.value.id)
        versions.value = res.data
      } catch { /* silently ignore — versions refresh is best-effort */ }
    }
    toast.error(`${msg} 已自动刷新为最新内容，请重新操作。`)
  } else {
    toast.error(msg || fallbackMessage)
  }
}

const replaceTemplate = (next: PromptTemplate) => {
  const index = templates.value.findIndex((template) => template.id === next.id)
  if (index !== -1) templates.value[index] = next
}

const normalize = (form: PromptTemplateSaveDTO): PromptTemplateSaveDTO => ({
  name: form.name.trim(),
  description: form.description?.trim() || undefined,
  content: form.content.trim(),
})

onMounted(loadTemplates)
</script>

<template>
  <div class="space-y-6 pb-4">
    <section class="relative overflow-hidden rounded-2xl border border-border bg-card/80 shadow-[0_18px_45px_rgba(0,0,0,0.18)]">
      <div class="pointer-events-none absolute -right-12 -top-16 h-48 w-48 rounded-full bg-violet-400/10 blur-3xl" />
      <div class="relative flex flex-col gap-5 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
        <div class="flex gap-4">
          <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-violet-400/25 bg-violet-400/10 text-violet-200"><PenLine class="h-5 w-5" /></div>
          <div>
            <p class="text-xs font-medium tracking-[0.16em] text-violet-200/90">PROMPT STUDIO</p>
            <h1 class="mt-1 text-2xl font-semibold tracking-tight">回答方案</h1>
            <p class="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">提前设置 AI 怎样回答，例如语气、结构和边界。发布后，新建对话时选择一次，整个对话都会遵循。</p>
          </div>
        </div>
        <div class="flex shrink-0 flex-wrap gap-2">
          <Button variant="outline" class="gap-2" @click="router.push('/builder/prompts/recycle-bin')"><Archive class="h-4 w-4" />回收站</Button>
          <Button class="gap-2" @click="openCreateDialog()"><CirclePlus class="h-4 w-4" />新建回答方案</Button>
        </div>
      </div>
    </section>

    <section class="border-y border-border/70 bg-muted/[0.12] px-5 py-5 sm:px-6">
      <div class="flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p class="text-sm font-semibold">这页有什么用？</p>
          <p class="mt-1 max-w-3xl text-sm leading-6 text-muted-foreground">当多个对话需要用同一种方式回答时，把规则保存成回答方案。它不保存知识库资料，资料仍然来自新建对话时选择的知识库。</p>
        </div>
        <span class="shrink-0 text-xs text-muted-foreground">草稿只供编辑和测试，发布后才可使用</span>
      </div>
      <div class="mt-5 grid gap-3 md:grid-cols-3">
        <div class="flex items-start gap-3 rounded-lg border border-border bg-card/60 p-3.5">
          <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-sm font-semibold text-primary">1</span>
          <div><p class="text-sm font-medium">写回答规则</p><p class="mt-1 text-xs leading-5 text-muted-foreground">说明角色、语气、格式和不能做什么。</p></div>
        </div>
        <div class="flex items-start gap-3 rounded-lg border border-border bg-card/60 p-3.5">
          <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-sm font-semibold text-primary">2</span>
          <div><p class="text-sm font-medium">测试真实问题</p><p class="mt-1 text-xs leading-5 text-muted-foreground">到“提示词测试台”查看回答和引用来源。</p></div>
        </div>
        <div class="flex items-start gap-3 rounded-lg border border-border bg-card/60 p-3.5">
          <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-sm font-semibold text-primary">3</span>
          <div><p class="text-sm font-medium">发布并选用</p><p class="mt-1 text-xs leading-5 text-muted-foreground">新建对话时选择它，之后的回答就会按规则执行。</p></div>
        </div>
      </div>
      <div class="mt-5 border-t border-border/70 pt-4">
        <div class="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
          <div><p class="text-sm font-semibold">不知道怎么写？从示例开始</p><p class="mt-1 text-xs text-muted-foreground">点击“套用示例”会自动填好名称、用途和回答规则，你只需要按业务修改。</p></div>
          <span class="text-xs text-muted-foreground">每个示例都附有可用于测试的真实问题</span>
        </div>
        <div class="mt-3 grid gap-3 lg:grid-cols-3">
          <div v-for="example in promptExamples" :key="example.id" class="rounded-lg border border-border bg-card/60 p-3.5">
            <p class="font-medium">{{ example.name }}</p>
            <p class="mt-1 text-xs text-primary/90">适用：{{ example.scenario }}</p>
            <p class="mt-2 line-clamp-2 text-xs leading-5 text-muted-foreground">{{ example.description }}</p>
            <p class="mt-3 line-clamp-2 border-t border-border/60 pt-3 text-xs text-muted-foreground">例如：{{ example.question }}</p>
            <Button variant="outline" size="sm" class="mt-3 w-full" @click="openCreateDialog(example)">套用示例</Button>
          </div>
        </div>
      </div>
    </section>

    <section class="grid gap-3 sm:grid-cols-3">
      <div class="rounded-xl border border-border bg-card/70 p-4"><p class="text-sm text-muted-foreground">全部方案</p><p class="mt-2 text-2xl font-semibold">{{ templates.length }}</p></div>
      <div class="rounded-xl border border-emerald-400/15 bg-emerald-400/[0.04] p-4"><p class="text-sm text-muted-foreground">已发布</p><p class="mt-2 text-2xl font-semibold text-emerald-200">{{ publishedCount }}</p></div>
      <div class="rounded-xl border border-violet-400/15 bg-violet-400/[0.04] p-4"><p class="text-sm text-muted-foreground">草稿</p><p class="mt-2 text-2xl font-semibold text-violet-200">{{ draftCount }}</p></div>
    </section>

    <div class="grid items-start gap-6 xl:grid-cols-[minmax(19rem,0.78fr)_minmax(0,1.55fr)]">
      <Card class="overflow-hidden border-border bg-card/80">
        <CardHeader class="border-b border-border/70 p-5">
          <div class="flex items-center justify-between gap-3"><div><CardTitle class="text-base">我的回答方案</CardTitle><CardDescription class="mt-1">按名称、用途或回答规则查找。</CardDescription></div><span class="rounded-full bg-muted px-2.5 py-1 text-xs text-muted-foreground">{{ filteredTemplates.length }}</span></div>
          <div class="relative mt-4"><Search class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" /><Input v-model="query" class="pl-10" placeholder="搜索回答方案" /></div>
          <div class="mt-4 flex gap-1 overflow-x-auto rounded-lg bg-muted/45 p-1"><button v-for="item in [{ value: 'ALL', label: '全部' }, { value: 'PUBLISHED', label: '已发布' }, { value: 'DRAFT', label: '草稿' }]" :key="item.value" class="shrink-0 rounded-md px-2.5 py-1.5 text-xs transition-colors" :class="filter === item.value ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'" @click="filter = item.value as Filter">{{ item.label }}</button></div>
        </CardHeader>
        <CardContent class="max-h-[42rem] space-y-2 overflow-y-auto p-3">
          <div v-if="loading" class="flex min-h-64 items-center justify-center"><LoaderCircle class="h-6 w-6 animate-spin text-primary" /></div>
          <div v-else-if="!filteredTemplates.length" class="flex min-h-64 flex-col items-center justify-center px-6 text-center"><BookOpenText class="h-9 w-9 text-muted-foreground/60" /><p class="mt-4 font-medium">{{ templates.length ? '没有匹配的回答方案' : '还没有回答方案' }}</p><p class="mt-1 text-sm leading-6 text-muted-foreground">{{ templates.length ? '调整搜索或状态筛选后再试。' : '先套用上面的示例，或创建一套自己的回答规则。' }}</p><Button v-if="!templates.length" variant="outline" class="mt-4" @click="openCreateDialog()">创建第一套回答方案</Button></div>
          <button v-for="template in filteredTemplates" :key="template.id" class="w-full rounded-xl border p-3.5 text-left transition-colors" :class="selectedId === template.id ? 'border-primary/45 bg-primary/[0.07]' : 'border-transparent hover:border-border hover:bg-muted/40'" @click="selectTemplate(template)"><div class="flex items-start justify-between gap-3"><div class="min-w-0"><p class="truncate text-sm font-medium">{{ template.name }}</p><p class="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{{ template.description || '暂未填写模板用途。' }}</p></div><Badge variant="outline" :class="template.status === 'PUBLISHED' ? 'border-emerald-400/25 bg-emerald-400/10 text-emerald-300' : 'border-violet-400/25 bg-violet-400/10 text-violet-200'">{{ template.status === 'PUBLISHED' ? '已发布' : '草稿' }}</Badge></div><div class="mt-3 flex items-center justify-between text-xs text-muted-foreground"><span>v{{ template.version }}</span><span>{{ formatDateTime(template.updatedAt) }}</span></div></button>
        </CardContent>
      </Card>

      <Card class="min-h-[38rem] overflow-hidden border-border bg-card/80">
        <div v-if="!selected" class="flex min-h-[38rem] flex-col items-center justify-center px-6 text-center"><div class="flex h-14 w-14 items-center justify-center rounded-2xl border border-violet-400/25 bg-violet-400/10 text-violet-200"><Layers3 class="h-6 w-6" /></div><h2 class="mt-5 text-lg font-semibold">选择或新建一套回答方案</h2><p class="mt-2 max-w-md text-sm leading-6 text-muted-foreground">回答方案只控制 AI 怎样表达，不会替代知识库。新建对话时可以同时选择知识库和回答方案。</p></div>
        <template v-else>
          <CardHeader class="border-b border-border/70 p-5 sm:p-6"><div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between"><div><div class="flex flex-wrap items-center gap-2"><Badge variant="outline" :class="selected.status === 'PUBLISHED' ? 'border-emerald-400/25 bg-emerald-400/10 text-emerald-300' : 'border-violet-400/25 bg-violet-400/10 text-violet-200'">{{ selected.status === 'PUBLISHED' ? '已发布' : '草稿' }}</Badge><span class="text-xs text-muted-foreground">版本 {{ selected.version }}</span></div><CardTitle class="mt-3 text-xl">{{ selected.name }}</CardTitle><CardDescription class="mt-2">上次修改：{{ formatDateTime(selected.updatedAt) }}</CardDescription></div><div class="flex shrink-0 flex-wrap gap-2"><Button variant="outline" size="sm" class="gap-1.5" @click="openVersionHistory"><History class="h-3.5 w-3.5" />版本历史</Button><Button variant="outline" size="sm" class="gap-1.5" @click="duplicateTemplate"><Copy class="h-3.5 w-3.5" />复制</Button><Button variant="outline" size="sm" :disabled="actionLoading" class="gap-1.5" @click="togglePublished"><LoaderCircle v-if="actionLoading" class="h-3.5 w-3.5 animate-spin" /><Rocket v-else class="h-3.5 w-3.5" />{{ selected.status === 'PUBLISHED' ? '撤回' : '发布' }}</Button><Button variant="ghost" size="icon" :disabled="actionLoading" title="删除回答方案" class="h-9 w-9 hover:bg-rose-400/10" @click="deleteTemplate"><Trash2 class="h-4 w-4 text-destructive" /></Button></div></div></CardHeader>
          <CardContent class="space-y-5 p-5 sm:p-6"><div class="grid gap-4 sm:grid-cols-2"><div class="space-y-2"><Label for="prompt-name">方案名称</Label><Input id="prompt-name" v-model="editForm.name" maxlength="100" placeholder="例如：客服答疑" /><p class="text-xs text-muted-foreground">新建对话时会看到这个名称。</p></div><div class="space-y-2"><Label for="prompt-description">适用场景</Label><Input id="prompt-description" v-model="editForm.description" maxlength="500" placeholder="例如：售前、售后和制度咨询" /><p class="text-xs text-muted-foreground">说明什么时候应该选择这套方案。</p></div></div><div class="space-y-2"><div class="flex items-center justify-between"><div><Label for="prompt-content">回答规则</Label><p class="mt-1 text-xs text-muted-foreground">写清楚回答顺序、语气、格式和边界。用户问题会自动传入，不需要填写变量占位符。</p></div><span class="text-xs text-muted-foreground">{{ editForm.content.length }} / 8000</span></div><textarea id="prompt-content" v-model="editForm.content" rows="15" maxlength="8000" class="block w-full resize-y rounded-xl border border-input bg-background/60 px-3.5 py-3 font-mono text-sm leading-6 outline-none placeholder:text-muted-foreground focus:border-primary/50 focus:ring-2 focus:ring-primary/20" placeholder="例如：你是企业客服助手。先直接给出结论，再列出处理步骤；引用知识库资料时标明来源；资料不足时不要猜测。" /></div><div class="flex flex-col gap-3 rounded-xl border border-primary/15 bg-primary/[0.04] p-4 text-sm leading-6 text-muted-foreground sm:flex-row sm:items-start"><Send class="mt-0.5 h-4 w-4 shrink-0 text-primary" /><p><strong class="font-medium text-foreground">怎么生效：</strong>先保存，到“回答方案测试”用真实问题验证，再点击“发布”。之后在“新建对话 → 回答方案”中选择它。</p></div><div class="flex items-center justify-between gap-3 border-t border-border/70 pt-5"><span class="text-xs text-muted-foreground">保存后是草稿，不会立即影响用户；发布后才会出现在新建对话中。</span><Button :disabled="!hasChanges || saving" class="gap-2" @click="saveTemplate"><LoaderCircle v-if="saving" class="h-4 w-4 animate-spin" /><Check v-else class="h-4 w-4" />保存草稿</Button></div></CardContent>
        </template>
      </Card>
    </div>

    <!-- Create Dialog -->
    <Dialog v-model:open="showCreateDialog">
      <DialogContent class="max-w-2xl">
        <DialogHeader>
          <DialogTitle>新建回答方案</DialogTitle>
          <DialogDescription>先保存为草稿，用真实问题测试满意后再发布。发布前不会影响任何对话。</DialogDescription>
        </DialogHeader>
        <div class="space-y-5">
          <div class="space-y-2">
            <Label>快速套用示例</Label>
            <div class="grid gap-2 sm:grid-cols-3">
              <Button v-for="example in promptExamples" :key="example.id" type="button" variant="outline" size="sm" @click="openCreateDialog(example)">{{ example.name }}</Button>
            </div>
          </div>
          <div class="grid gap-4 sm:grid-cols-2">
            <div class="space-y-2"><Label for="new-prompt-name">方案名称 *</Label><Input id="new-prompt-name" v-model="createForm.name" placeholder="例如：客服答疑" maxlength="100" /><p class="text-xs text-muted-foreground">用户新建对话时看到的名称。</p></div>
            <div class="space-y-2"><Label for="new-prompt-description">适用场景</Label><Input id="new-prompt-description" v-model="createForm.description" placeholder="例如：售前、售后和制度咨询" maxlength="500" /><p class="text-xs text-muted-foreground">帮助用户判断什么时候选择它。</p></div>
          </div>
          <div class="space-y-2">
            <div class="flex items-center justify-between"><Label for="new-prompt-content">回答规则 *</Label><span class="text-xs text-muted-foreground">{{ createForm.content.length }} / 8000</span></div>
            <textarea id="new-prompt-content" v-model="createForm.content" rows="10" maxlength="8000" class="block w-full resize-y rounded-xl border border-input bg-background/60 px-3.5 py-3 text-sm leading-6 outline-none focus:border-primary/50 focus:ring-2 focus:ring-primary/20" placeholder="例如：你是企业客服助手。先给结论，再列处理步骤；资料不足时明确说明，不要猜测。" />
            <p class="text-xs leading-5 text-muted-foreground">只写通用规则，不要把某一个具体问题写在这里。用户每次发送的问题会自动交给 AI。</p>
          </div>
        </div>
        <DialogFooter><Button variant="outline" @click="showCreateDialog = false">取消</Button><Button :disabled="!createForm.name.trim() || !createForm.content.trim() || saving" @click="createTemplate">{{ saving ? '创建中…' : '保存为草稿' }}</Button></DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Version History Dialog -->
    <Dialog v-model:open="showVersionHistory">
      <DialogContent class="max-w-3xl">
        <DialogHeader>
          <DialogTitle>版本历史 — {{ selected?.name }}</DialogTitle>
          <DialogDescription>
            每次编辑、发布、撤回和回滚都会产生一条快照。点击版本可预览内容；回滚后的版本必须重新发布。
          </DialogDescription>
        </DialogHeader>

        <div class="grid gap-0 sm:grid-cols-[1fr_minmax(0,1.4fr)] sm:gap-0 max-h-[32rem] min-h-0">
          <!-- Version list (left) -->
          <div class="overflow-y-auto border-r border-border/60 pr-3 max-h-[32rem] min-h-0 space-y-1.5">
            <div v-if="versionsLoading" class="flex items-center justify-center py-10">
              <LoaderCircle class="h-5 w-5 animate-spin text-primary" />
            </div>
            <div v-else-if="versionsError" class="rounded-lg border border-rose-400/20 bg-rose-400/[0.06] p-3 text-xs text-rose-100/85">
              {{ versionsError }}
            </div>
            <div v-else-if="!versions.length" class="py-10 text-center text-xs text-muted-foreground">
              暂无版本记录
            </div>
            <button
              v-for="v in versions"
              :key="v.id"
              class="w-full rounded-lg border p-3 text-left transition-colors"
              :class="selectedVersion?.id === v.id
                ? 'border-primary/45 bg-primary/[0.07]'
                : 'border-transparent hover:border-border hover:bg-muted/40'"
              @click="selectedVersion = v"
            >
              <div class="flex items-center justify-between gap-2">
                <span class="text-sm font-medium">v{{ v.version }}</span>
                <Badge variant="outline" :class="opClass(v.operation)">{{ opLabel(v.operation) }}</Badge>
              </div>
              <p class="mt-1 flex items-center gap-1.5 text-[11px] text-muted-foreground">
                <Clock class="h-3 w-3" />
                {{ formatDateTime(v.createdAt) }}
              </p>
            </button>
          </div>

          <!-- Version preview (right) -->
          <div class="overflow-y-auto pl-3 max-h-[32rem] min-h-0">
            <div v-if="!selectedVersion" class="flex flex-col items-center justify-center py-14 text-center">
              <History class="h-8 w-8 text-muted-foreground/40" />
              <p class="mt-3 text-sm text-muted-foreground">选择一个版本查看内容</p>
            </div>
            <div v-else class="space-y-4">
              <!-- Diff notice -->
              <div v-if="isDifferentFromCurrent(selectedVersion)" class="flex items-start gap-2 rounded-lg border border-amber-400/20 bg-amber-400/[0.06] p-3 text-xs text-amber-100/85">
                <ArrowLeftRight class="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>此版本与当前内容不同。回滚会保存当前版本为历史记录，恢复此版本内容。</span>
              </div>
              <div v-else class="flex items-start gap-2 rounded-lg border border-emerald-400/20 bg-emerald-400/[0.06] p-3 text-xs text-emerald-100/85">
                <Check class="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>此版本内容与当前一致。</span>
              </div>

              <!-- Metadata -->
              <div class="space-y-1 text-xs text-muted-foreground">
                <div class="flex justify-between">
                  <span>操作</span>
                  <Badge variant="outline" :class="opClass(selectedVersion.operation)">{{ opLabel(selectedVersion.operation) }}</Badge>
                </div>
                <div class="flex justify-between">
                  <span>版本号</span>
                  <span class="font-mono">v{{ selectedVersion.version }}</span>
                </div>
                <div class="flex justify-between">
                  <span>状态</span>
                  <span>{{ selectedVersion.status === 'PUBLISHED' ? '已发布' : '草稿' }}</span>
                </div>
                <div class="flex justify-between">
                  <span>时间</span>
                  <span>{{ formatDateTime(selectedVersion.createdAt) }}</span>
                </div>
              </div>

              <Separator />

              <!-- Content preview -->
              <div class="space-y-2">
                <Label class="text-xs">版本内容</Label>
                <pre class="max-h-64 overflow-y-auto whitespace-pre-wrap rounded-lg border border-border bg-muted/30 p-3 font-mono text-xs leading-relaxed text-foreground/85">{{ selectedVersion.content }}</pre>
              </div>

              <!-- Rollback button -->
              <Button
                variant="outline"
                size="sm"
                class="w-full gap-1.5"
                :disabled="rollbackLoading || (selectedVersion.version === selected?.version && !isDifferentFromCurrent(selectedVersion))"
                @click="rollbackToVersion"
              >
                <LoaderCircle v-if="rollbackLoading" class="h-3.5 w-3.5 animate-spin" />
                <RotateCcw v-else class="h-3.5 w-3.5" />
                {{ rollbackLoading ? '回滚中…' : `回滚到 v${selectedVersion.version}` }}
              </Button>
              <p class="text-center text-[11px] text-muted-foreground">
                回滚后生成新草稿版本，需重新发布才影响对话。
              </p>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>

    <ConfirmDialog
      v-model:open="confirmDeleteOpen"
      title="删除确认"
      :description="`确定要删除回答方案「${deleteTarget?.name}」吗？关联对话之后将使用系统默认回答方式。`"
      confirm-text="删除"
      destructive
      :loading="confirmDeleteLoading"
      @confirm="confirmDelete"
    />
    <ConfirmDialog
      v-model:open="confirmRollbackOpen"
      title="回滚确认"
      :description="`确定要回滚到 v${rollbackTarget?.version} 吗？当前内容将被保存为历史版本，恢复后的内容为草稿，需重新发布。`"
      confirm-text="回滚"
      :loading="confirmRollbackLoading"
      @confirm="confirmRollback"
    />
  </div>
</template>
