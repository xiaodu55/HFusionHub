<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  ArrowLeftRight,
  BookOpenText,
  Check,
  CirclePlus,
  Clock,
  Copy,
  FileText,
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

type Filter = 'ALL' | promptTemplateApi.PromptTemplateStatus

const toast = useToast()
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

// ── Version history ──────────────────────────────────────────────────

const showVersionHistory = ref(false)
const versions = ref<PromptTemplateVersion[]>([])
const versionsLoading = ref(false)
const versionsError = ref('')
const selectedVersion = ref<PromptTemplateVersion | null>(null)
const rollbackLoading = ref(false)

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
    toast.success('草稿已创建。发布后可在新建对话中使用。')
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
    const response = await promptTemplateApi.updatePromptTemplate(selected.value.id, normalize(editForm.value))
    replaceTemplate(response.data)
    selectTemplate(response.data)
    toast.success(`模板已保存为草稿，当前为版本 ${response.data.version}`)
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '保存提示词模板失败')
  } finally {
    saving.value = false
  }
}

const togglePublished = async () => {
  if (!selected.value || actionLoading.value) return
  actionLoading.value = true
  try {
    const response = selected.value.status === 'PUBLISHED'
      ? await promptTemplateApi.unpublishPromptTemplate(selected.value.id)
      : await promptTemplateApi.publishPromptTemplate(selected.value.id)
    replaceTemplate(response.data)
    selectTemplate(response.data)
    toast.success(response.data.status === 'PUBLISHED'
      ? '模板已发布，可在新建对话时选择。'
      : '模板已撤回，已有对话将不再使用它。')
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '更新发布状态失败')
  } finally {
    actionLoading.value = false
  }
}

const deleteTemplate = async () => {
  if (!selected.value || actionLoading.value) return
  if (!confirm(`确定要删除「${selected.value.name}」吗？关联此模板的对话将不再加载它。`)) return
  actionLoading.value = true
  try {
    await promptTemplateApi.deletePromptTemplate(selected.value.id)
    templates.value = templates.value.filter((template) => template.id !== selected.value?.id)
    const next = templates.value[0]
    if (next) selectTemplate(next)
    else selectedId.value = null
    toast.success('提示词模板已删除')
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '删除提示词模板失败')
  } finally {
    actionLoading.value = false
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

const rollbackToVersion = async () => {
  if (!selected.value || !selectedVersion.value || rollbackLoading.value) return
  const targetVersion = selectedVersion.value.version
  const versionId = selectedVersion.value.id
  if (!confirm(`确定要回滚到 v${targetVersion} 吗？当前内容将被保存为历史版本，恢复后的内容为草稿，需重新发布。`)) return
  rollbackLoading.value = true
  try {
    const response = await promptTemplateApi.rollbackPromptTemplate(selected.value.id, versionId)
    replaceTemplate(response.data)
    selectTemplate(response.data)
    showVersionHistory.value = false
    toast.success(`已回滚到 v${targetVersion}，当前为草稿（v${response.data.version}）。请确认内容后重新发布。`)
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '回滚失败')
  } finally {
    rollbackLoading.value = false
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
            <h1 class="mt-1 text-2xl font-semibold tracking-tight">提示词工作台</h1>
            <p class="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">把常用的回答规则保存为模板；只有已发布模板才能被新建对话使用。</p>
          </div>
        </div>
        <Button class="shrink-0 gap-2" @click="showCreateDialog = true"><CirclePlus class="h-4 w-4" />新建模板</Button>
      </div>
    </section>

    <section class="grid gap-3 sm:grid-cols-3">
      <div class="rounded-xl border border-border bg-card/70 p-4"><p class="text-sm text-muted-foreground">全部模板</p><p class="mt-2 text-2xl font-semibold">{{ templates.length }}</p></div>
      <div class="rounded-xl border border-emerald-400/15 bg-emerald-400/[0.04] p-4"><p class="text-sm text-muted-foreground">已发布</p><p class="mt-2 text-2xl font-semibold text-emerald-200">{{ publishedCount }}</p></div>
      <div class="rounded-xl border border-violet-400/15 bg-violet-400/[0.04] p-4"><p class="text-sm text-muted-foreground">草稿</p><p class="mt-2 text-2xl font-semibold text-violet-200">{{ draftCount }}</p></div>
    </section>

    <div class="grid items-start gap-6 xl:grid-cols-[minmax(19rem,0.78fr)_minmax(0,1.55fr)]">
      <Card class="overflow-hidden border-border bg-card/80">
        <CardHeader class="border-b border-border/70 p-5">
          <div class="flex items-center justify-between gap-3"><div><CardTitle class="text-base">模板库</CardTitle><CardDescription class="mt-1">按名称、说明或指令内容查找。</CardDescription></div><span class="rounded-full bg-muted px-2.5 py-1 text-xs text-muted-foreground">{{ filteredTemplates.length }}</span></div>
          <div class="relative mt-4"><Search class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" /><Input v-model="query" class="pl-10" placeholder="搜索模板" /></div>
          <div class="mt-4 flex gap-1 overflow-x-auto rounded-lg bg-muted/45 p-1"><button v-for="item in [{ value: 'ALL', label: '全部' }, { value: 'PUBLISHED', label: '已发布' }, { value: 'DRAFT', label: '草稿' }]" :key="item.value" class="shrink-0 rounded-md px-2.5 py-1.5 text-xs transition-colors" :class="filter === item.value ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'" @click="filter = item.value as Filter">{{ item.label }}</button></div>
        </CardHeader>
        <CardContent class="max-h-[42rem] space-y-2 overflow-y-auto p-3">
          <div v-if="loading" class="flex min-h-64 items-center justify-center"><LoaderCircle class="h-6 w-6 animate-spin text-primary" /></div>
          <div v-else-if="!filteredTemplates.length" class="flex min-h-64 flex-col items-center justify-center px-6 text-center"><BookOpenText class="h-9 w-9 text-muted-foreground/60" /><p class="mt-4 font-medium">{{ templates.length ? '没有匹配的模板' : '还没有提示词模板' }}</p><p class="mt-1 text-sm leading-6 text-muted-foreground">{{ templates.length ? '调整搜索或状态筛选后再试。' : '保存常用的回答规则，减少每次重复说明。' }}</p><Button v-if="!templates.length" variant="outline" class="mt-4" @click="showCreateDialog = true">创建第一个模板</Button></div>
          <button v-for="template in filteredTemplates" :key="template.id" class="w-full rounded-xl border p-3.5 text-left transition-colors" :class="selectedId === template.id ? 'border-primary/45 bg-primary/[0.07]' : 'border-transparent hover:border-border hover:bg-muted/40'" @click="selectTemplate(template)"><div class="flex items-start justify-between gap-3"><div class="min-w-0"><p class="truncate text-sm font-medium">{{ template.name }}</p><p class="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{{ template.description || '暂未填写模板用途。' }}</p></div><Badge variant="outline" :class="template.status === 'PUBLISHED' ? 'border-emerald-400/25 bg-emerald-400/10 text-emerald-300' : 'border-violet-400/25 bg-violet-400/10 text-violet-200'">{{ template.status === 'PUBLISHED' ? '已发布' : '草稿' }}</Badge></div><div class="mt-3 flex items-center justify-between text-xs text-muted-foreground"><span>v{{ template.version }}</span><span>{{ formatDateTime(template.updatedAt) }}</span></div></button>
        </CardContent>
      </Card>

      <Card class="min-h-[38rem] overflow-hidden border-border bg-card/80">
        <div v-if="!selected" class="flex min-h-[38rem] flex-col items-center justify-center px-6 text-center"><div class="flex h-14 w-14 items-center justify-center rounded-2xl border border-violet-400/25 bg-violet-400/10 text-violet-200"><Layers3 class="h-6 w-6" /></div><h2 class="mt-5 text-lg font-semibold">选择或新建一个模板</h2><p class="mt-2 max-w-md text-sm leading-6 text-muted-foreground">发布后的模板会作为对话的回答规则，由服务端在每次请求时安全加载。</p></div>
        <template v-else>
          <CardHeader class="border-b border-border/70 p-5 sm:p-6"><div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between"><div><div class="flex flex-wrap items-center gap-2"><Badge variant="outline" :class="selected.status === 'PUBLISHED' ? 'border-emerald-400/25 bg-emerald-400/10 text-emerald-300' : 'border-violet-400/25 bg-violet-400/10 text-violet-200'">{{ selected.status === 'PUBLISHED' ? '已发布' : '草稿' }}</Badge><span class="text-xs text-muted-foreground">版本 {{ selected.version }}</span></div><CardTitle class="mt-3 text-xl">{{ selected.name }}</CardTitle><CardDescription class="mt-2">上次修改：{{ formatDateTime(selected.updatedAt) }}</CardDescription></div><div class="flex shrink-0 flex-wrap gap-2"><Button variant="outline" size="sm" class="gap-1.5" @click="openVersionHistory"><History class="h-3.5 w-3.5" />版本历史</Button><Button variant="outline" size="sm" class="gap-1.5" @click="duplicateTemplate"><Copy class="h-3.5 w-3.5" />复制</Button><Button variant="outline" size="sm" :disabled="actionLoading" class="gap-1.5" @click="togglePublished"><LoaderCircle v-if="actionLoading" class="h-3.5 w-3.5 animate-spin" /><Rocket v-else class="h-3.5 w-3.5" />{{ selected.status === 'PUBLISHED' ? '撤回' : '发布' }}</Button><Button variant="ghost" size="icon" :disabled="actionLoading" title="删除模板" class="h-9 w-9 hover:bg-rose-400/10" @click="deleteTemplate"><Trash2 class="h-4 w-4 text-destructive" /></Button></div></div></CardHeader>
          <CardContent class="space-y-5 p-5 sm:p-6"><div class="grid gap-4 sm:grid-cols-2"><div class="space-y-2"><Label for="prompt-name">模板名称</Label><Input id="prompt-name" v-model="editForm.name" maxlength="100" /></div><div class="space-y-2"><Label for="prompt-description">用途说明</Label><Input id="prompt-description" v-model="editForm.description" maxlength="500" placeholder="例如：客服知识库回答" /></div></div><div class="space-y-2"><div class="flex items-center justify-between"><Label for="prompt-content">系统指令</Label><span class="text-xs text-muted-foreground">{{ editForm.content.length }} / 8000</span></div><textarea id="prompt-content" v-model="editForm.content" rows="15" maxlength="8000" class="block w-full resize-y rounded-xl border border-input bg-background/60 px-3.5 py-3 font-mono text-sm leading-6 outline-none placeholder:text-muted-foreground focus:border-primary/50 focus:ring-2 focus:ring-primary/20" placeholder="例如：请使用简洁、清晰的中文回答；优先给出结论，并在引用资料时说明来源。" /></div><div class="flex flex-col gap-3 rounded-xl border border-primary/15 bg-primary/[0.04] p-4 text-sm leading-6 text-muted-foreground sm:flex-row sm:items-start"><Send class="mt-0.5 h-4 w-4 shrink-0 text-primary" /><p>发布后，在"新建对话"中选择此模板。编辑已发布模板会生成新草稿；需要再次发布后才会影响之后的回答。</p></div><div class="flex items-center justify-between gap-3 border-t border-border/70 pt-5"><span class="text-xs text-muted-foreground">保存内容变更会自动递增版本号，并转为草稿。</span><Button :disabled="!hasChanges || saving" class="gap-2" @click="saveTemplate"><LoaderCircle v-if="saving" class="h-4 w-4 animate-spin" /><Check v-else class="h-4 w-4" />保存版本</Button></div></CardContent>
        </template>
      </Card>
    </div>

    <!-- Create Dialog -->
    <Dialog v-model:open="showCreateDialog"><DialogContent><DialogHeader><DialogTitle>新建提示词模板</DialogTitle><DialogDescription>先保存为草稿；确认效果后再发布给新建对话使用。</DialogDescription></DialogHeader><div class="space-y-4"><div class="space-y-2"><Label for="new-prompt-name">模板名称 *</Label><Input id="new-prompt-name" v-model="createForm.name" placeholder="例如：严谨的知识库助手" maxlength="100" /></div><div class="space-y-2"><Label for="new-prompt-description">用途说明</Label><Input id="new-prompt-description" v-model="createForm.description" placeholder="说明适用的场景（可选）" maxlength="500" /></div><div class="space-y-2"><Label for="new-prompt-content">系统指令 *</Label><textarea id="new-prompt-content" v-model="createForm.content" rows="8" maxlength="8000" class="block w-full resize-y rounded-xl border border-input bg-background/60 px-3.5 py-3 text-sm leading-6 outline-none focus:border-primary/50 focus:ring-2 focus:ring-primary/20" placeholder="请说明 AI 的角色、回答风格、边界与引用要求。" /></div></div><DialogFooter><Button variant="outline" @click="showCreateDialog = false">取消</Button><Button :disabled="!createForm.name.trim() || !createForm.content.trim() || saving" @click="createTemplate">{{ saving ? '创建中…' : '创建草稿' }}</Button></DialogFooter></DialogContent></Dialog>

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
  </div>
</template>
