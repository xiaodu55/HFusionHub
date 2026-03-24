<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  BookOpenText,
  Check,
  CirclePlus,
  Copy,
  FileText,
  Layers3,
  LoaderCircle,
  PenLine,
  Rocket,
  Search,
  Send,
  Trash2,
} from 'lucide-vue-next'
import * as promptTemplateApi from '@/api/promptTemplate'
import type { PromptTemplate, PromptTemplateSaveDTO } from '@/api/promptTemplate'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
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
          <CardHeader class="border-b border-border/70 p-5 sm:p-6"><div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between"><div><div class="flex flex-wrap items-center gap-2"><Badge variant="outline" :class="selected.status === 'PUBLISHED' ? 'border-emerald-400/25 bg-emerald-400/10 text-emerald-300' : 'border-violet-400/25 bg-violet-400/10 text-violet-200'">{{ selected.status === 'PUBLISHED' ? '已发布' : '草稿' }}</Badge><span class="text-xs text-muted-foreground">版本 {{ selected.version }}</span></div><CardTitle class="mt-3 text-xl">{{ selected.name }}</CardTitle><CardDescription class="mt-2">上次修改：{{ formatDateTime(selected.updatedAt) }}</CardDescription></div><div class="flex shrink-0 flex-wrap gap-2"><Button variant="outline" size="sm" class="gap-1.5" @click="duplicateTemplate"><Copy class="h-3.5 w-3.5" />复制</Button><Button variant="outline" size="sm" :disabled="actionLoading" class="gap-1.5" @click="togglePublished"><LoaderCircle v-if="actionLoading" class="h-3.5 w-3.5 animate-spin" /><Rocket v-else class="h-3.5 w-3.5" />{{ selected.status === 'PUBLISHED' ? '撤回' : '发布' }}</Button><Button variant="ghost" size="icon" :disabled="actionLoading" title="删除模板" class="h-9 w-9 hover:bg-rose-400/10" @click="deleteTemplate"><Trash2 class="h-4 w-4 text-destructive" /></Button></div></div></CardHeader>
          <CardContent class="space-y-5 p-5 sm:p-6"><div class="grid gap-4 sm:grid-cols-2"><div class="space-y-2"><Label for="prompt-name">模板名称</Label><Input id="prompt-name" v-model="editForm.name" maxlength="100" /></div><div class="space-y-2"><Label for="prompt-description">用途说明</Label><Input id="prompt-description" v-model="editForm.description" maxlength="500" placeholder="例如：客服知识库回答" /></div></div><div class="space-y-2"><div class="flex items-center justify-between"><Label for="prompt-content">系统指令</Label><span class="text-xs text-muted-foreground">{{ editForm.content.length }} / 8000</span></div><textarea id="prompt-content" v-model="editForm.content" rows="15" maxlength="8000" class="block w-full resize-y rounded-xl border border-input bg-background/60 px-3.5 py-3 font-mono text-sm leading-6 outline-none placeholder:text-muted-foreground focus:border-primary/50 focus:ring-2 focus:ring-primary/20" placeholder="例如：请使用简洁、清晰的中文回答；优先给出结论，并在引用资料时说明来源。" /></div><div class="flex flex-col gap-3 rounded-xl border border-primary/15 bg-primary/[0.04] p-4 text-sm leading-6 text-muted-foreground sm:flex-row sm:items-start"><Send class="mt-0.5 h-4 w-4 shrink-0 text-primary" /><p>发布后，在“新建对话”中选择此模板。编辑已发布模板会生成新草稿；需要再次发布后才会影响之后的回答。</p></div><div class="flex items-center justify-between gap-3 border-t border-border/70 pt-5"><span class="text-xs text-muted-foreground">保存内容变更会自动递增版本号，并转为草稿。</span><Button :disabled="!hasChanges || saving" class="gap-2" @click="saveTemplate"><LoaderCircle v-if="saving" class="h-4 w-4 animate-spin" /><Check v-else class="h-4 w-4" />保存版本</Button></div></CardContent>
        </template>
      </Card>
    </div>

    <Dialog v-model:open="showCreateDialog"><DialogContent><DialogHeader><DialogTitle>新建提示词模板</DialogTitle><DialogDescription>先保存为草稿；确认效果后再发布给新建对话使用。</DialogDescription></DialogHeader><div class="space-y-4"><div class="space-y-2"><Label for="new-prompt-name">模板名称 *</Label><Input id="new-prompt-name" v-model="createForm.name" placeholder="例如：严谨的知识库助手" maxlength="100" /></div><div class="space-y-2"><Label for="new-prompt-description">用途说明</Label><Input id="new-prompt-description" v-model="createForm.description" placeholder="说明适用的场景（可选）" maxlength="500" /></div><div class="space-y-2"><Label for="new-prompt-content">系统指令 *</Label><textarea id="new-prompt-content" v-model="createForm.content" rows="8" maxlength="8000" class="block w-full resize-y rounded-xl border border-input bg-background/60 px-3.5 py-3 text-sm leading-6 outline-none focus:border-primary/50 focus:ring-2 focus:ring-primary/20" placeholder="请说明 AI 的角色、回答风格、边界与引用要求。" /></div></div><DialogFooter><Button variant="outline" @click="showCreateDialog = false">取消</Button><Button :disabled="!createForm.name.trim() || !createForm.content.trim() || saving" @click="createTemplate">{{ saving ? '创建中…' : '创建草稿' }}</Button></DialogFooter></DialogContent></Dialog>
  </div>
</template>
