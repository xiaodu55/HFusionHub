<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Diff,
  FlaskConical,
  History,
  Layers,
  LoaderCircle,
  Minus,
  Play,
  Plus,
  RefreshCw,
  Save,
  Scale,
  Trash2,
  XCircle,
  Zap,
} from 'lucide-vue-next'
import * as promptTemplateApi from '@/api/promptTemplate'
import * as promptTestSetApi from '@/api/promptTestSet'
import * as knowledgeBaseApi from '@/api/knowledgeBase'
import type { PromptTemplate } from '@/api/promptTemplate'
import type {
  PromptTestCase,
  PromptTestCaseResult,
  PromptTestSet,
  PromptTestSetCompareResponse,
  PromptTestSetDetail,
  PromptTestSetRun,
  PromptTestSetRunDetail,
  PromptTestSetRunResponse,
  PromptTestSetRunStatusDTO,
} from '@/api/promptTestSet'
import type { KnowledgeBase } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import { useToast } from '@/composables/useToast'

// ── State ──────────────────────────────────────────────────────────

const toast = useToast()

const sets = ref<PromptTestSet[]>([])
const selectedId = ref<number | null>(null)
const detail = ref<PromptTestSetDetail | null>(null)
const templates = ref<PromptTemplate[]>([])
const knowledgeBases = ref<KnowledgeBase[]>([])
const loading = ref(false)
const saving = ref(false)
const running = ref(false)
const creatingExample = ref(false)
const deleteSetTarget = ref<PromptTestSet | null>(null)
const confirmDeleteSetOpen = ref(false)
const confirmDeleteSetLoading = ref(false)
const deleteCaseTarget = ref<PromptTestCase | null>(null)
const confirmDeleteCaseOpen = ref(false)
const confirmDeleteCaseLoading = ref(false)

// new / edit set form
const setForm = ref({ name: '', description: '' })
const editingSetId = ref<number | null>(null)
const showSetEditor = ref(false)

// new / edit case form
const caseForm = ref({ question: '', variables: '', expectedKeywords: '', requiredDocumentIds: '' })
const editingCaseId = ref<number | null>(null)
const showCaseEditor = ref(false)

// run config
const runTemplateContent = ref('')
const runKbId = ref<number | undefined>(undefined)
const runResult = ref<PromptTestSetRunResponse | null>(null)
const runStatus = ref<PromptTestSetRunStatusDTO | null>(null)
const selectedTemplate = ref<{ id: number; version: number; name: string } | null>(null)
const selectedTemplateId = ref<number>(0)
let pollTimer: number | null = null
const cancelling = ref(false)
const retrying = ref(false)

// run history & comparison
const runs = ref<PromptTestSetRun[]>([])
const compareA = ref<number | undefined>(undefined)
const compareB = ref<number | undefined>(undefined)
const comparison = ref<PromptTestSetCompareResponse | null>(null)
const comparing = ref(false)

// expanded case ids in the run report
const expandedResults = ref<Set<number>>(new Set())
const expandedCompare = ref<Set<number>>(new Set())

const caseExamples = [
  {
    name: '普通问候',
    description: '检查回答是否自然、简洁',
    question: '你好，请用一句话介绍你能提供什么帮助。',
    expectedKeywords: '帮助',
  },
  {
    name: '业务咨询',
    description: '检查回答是否覆盖核心主题',
    question: '我想申请退款，需要提前准备什么信息？',
    expectedKeywords: '退款',
  },
  {
    name: '分步说明',
    description: '检查复杂问题是否讲清楚',
    question: '请把申请退款的处理流程分成 3 步说明。',
    expectedKeywords: '退款',
  },
]

// ── Computed ───────────────────────────────────────────────────────

const selectedSet = computed(() => sets.value.find((s) => s.id === selectedId.value) || null)

const publishedTemplates = computed(() => templates.value.filter((t) => t.status === 'PUBLISHED'))

const draftTemplates = computed(() => templates.value.filter((t) => t.status === 'DRAFT'))

const canRun = computed(
  () => selectedSet.value !== null && detail.value !== null && detail.value.cases.length > 0
    && runTemplateContent.value.trim().length > 0 && !running.value,
)

const canSaveSet = computed(() => setForm.value.name.trim().length > 0 && !saving.value)

const canSaveCase = computed(() => caseForm.value.question.trim().length > 0 && !saving.value)

const isPlainObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const caseVariables = computed<Record<string, string | number | boolean> | null>(() => {
  const raw = caseForm.value.variables.trim()
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw)
    return isPlainObject(parsed) ? (parsed as Record<string, string | number | boolean>) : null
  } catch {
    return null
  }
})

const caseVariablesValid = computed(() => {
  const raw = caseForm.value.variables.trim()
  if (!raw) return true
  try {
    const parsed = JSON.parse(raw)
    return isPlainObject(parsed)
  } catch {
    return false
  }
})

const totalElapsed = computed(() => {
  if (!runResult.value) return null
  const ms = runResult.value.totalElapsedMs
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)}s` : `${ms}ms`
})

const progressPercent = computed(() => {
  const s = runStatus.value
  if (!s || s.totalCases <= 0) return 0
  return Math.round((s.progressCount / s.totalCases) * 100)
})

const isRunActive = computed(() => {
  const s = runStatus.value
  return !!s && (s.status === 'pending' || s.status === 'running')
})

const varBraces = '{{变量}}'

// ── Data loading ───────────────────────────────────────────────────

const loadSets = async () => {
  loading.value = true
  try {
    const res = await promptTestSetApi.listPromptTestSets()
    sets.value = res.data
    if (res.data.length > 0 && !selectedId.value) {
      await selectSet(res.data[0].id)
    }
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '加载测试用例集失败')
  } finally {
    loading.value = false
  }
}

const selectSet = async (id: number) => {
  selectedId.value = id
  stopPolling()
  running.value = false
  runResult.value = null
  runStatus.value = null
  comparison.value = null
  compareA.value = undefined
  compareB.value = undefined
  expandedResults.value = new Set()
  expandedCompare.value = new Set()
  try {
    const res = await promptTestSetApi.getPromptTestSet(id)
    detail.value = res.data
    if (detail.value.cases.length > 0) {
      runTemplateContent.value = runTemplateContent.value || '你是一个专业的AI助手，请用中文回答。'
    }
    await loadRuns(id)
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '加载用例集详情失败')
  }
}

const loadRuns = async (id: number) => {
  try {
    const res = await promptTestSetApi.listPromptTestSetRuns(id)
    runs.value = res.data
  } catch (err) {
    console.error('加载运行历史失败:', err)
  }
}

const loadTemplatesAndKbs = async () => {
  try {
    const [tRes, kbRes] = await Promise.all([
      promptTemplateApi.listPromptTemplates(),
      knowledgeBaseApi.getMyKnowledgeBaseList({ page: 1, pageSize: 100 }),
    ])
    templates.value = tRes.data
    knowledgeBases.value = kbRes.data.records.filter((kb) => kb.status === 0)
  } catch (err) {
    console.error('加载模板或知识库失败:', err)
  }
}

// ── Set CRUD ───────────────────────────────────────────────────────

const openCreateSet = () => {
  editingSetId.value = null
  setForm.value = { name: '', description: '' }
  showSetEditor.value = true
}

const createExampleSet = async () => {
  const exampleName = '客服回答检查示例'
  const existing = sets.value.find((item) => item.name === exampleName)
  if (existing) {
    await selectSet(existing.id)
    toast.success('已打开示例问题组')
    return
  }

  creatingExample.value = true
  try {
    const created = await promptTestSetApi.createPromptTestSet({
      name: exampleName,
      description: '用 3 个常见问题检查回答是否自然、准确，并包含必要信息。',
    })
    const setId = created.data.id
    for (const [index, example] of caseExamples.entries()) {
      await promptTestSetApi.addPromptTestCase(setId, {
        question: example.question,
        expectedKeywords: [example.expectedKeywords],
        sortOrder: index + 1,
      })
    }
    await loadSets()
    await selectSet(setId)
    runTemplateContent.value = '你是专业、耐心的客服助手。请直接回答用户问题，信息不确定时明确说明，不要编造。'
    toast.success('示例已创建，可以直接开始检查')
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '创建示例失败，请稍后重试')
  } finally {
    creatingExample.value = false
  }
}

const openEditSet = () => {
  if (!detail.value) return
  editingSetId.value = detail.value.id
  setForm.value = { name: detail.value.name, description: detail.value.description || '' }
  showSetEditor.value = true
}

const saveSet = async () => {
  if (!canSaveSet.value) return
  saving.value = true
  try {
    const payload = { name: setForm.value.name.trim(), description: setForm.value.description.trim() || undefined }
    let res
    if (editingSetId.value) {
      res = await promptTestSetApi.updatePromptTestSet(editingSetId.value, payload)
    } else {
      res = await promptTestSetApi.createPromptTestSet(payload)
    }
    toast.success(editingSetId.value ? '用例集已保存' : '用例集已创建')
    showSetEditor.value = false
    await loadSets()
    if (res.data.id) await selectSet(res.data.id)
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '保存用例集失败')
  } finally {
    saving.value = false
  }
}

const confirmDeleteSet = () => {
  if (!selectedSet.value) return
  deleteSetTarget.value = selectedSet.value
  confirmDeleteSetOpen.value = true
}

const handleConfirmDeleteSet = async () => {
  const target = deleteSetTarget.value
  if (!target) return
  confirmDeleteSetLoading.value = true
  try {
    await promptTestSetApi.deletePromptTestSet(target.id)
    toast.success('用例集已删除')
    selectedId.value = null
    detail.value = null
    runResult.value = null
    await loadSets()
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '删除用例集失败')
  } finally {
    confirmDeleteSetLoading.value = false
    confirmDeleteSetOpen.value = false
    deleteSetTarget.value = null
  }
}

// ── Case CRUD ──────────────────────────────────────────────────────

const openAddCase = () => {
  editingCaseId.value = null
  caseForm.value = { question: '', variables: '', expectedKeywords: '', requiredDocumentIds: '' }
  showCaseEditor.value = true
}

const applyCaseExample = (example: (typeof caseExamples)[number]) => {
  caseForm.value = {
    question: example.question,
    variables: '',
    expectedKeywords: example.expectedKeywords,
    requiredDocumentIds: '',
  }
}

const openEditCase = (tc: PromptTestCase) => {
  editingCaseId.value = tc.id
  caseForm.value = {
    question: tc.question,
    variables: tc.variables && Object.keys(tc.variables).length ? JSON.stringify(tc.variables, null, 2) : '',
    expectedKeywords: tc.expectedKeywords?.length ? tc.expectedKeywords.join(', ') : '',
    requiredDocumentIds: tc.requiredDocumentIds?.length ? tc.requiredDocumentIds.join(', ') : '',
  }
  showCaseEditor.value = true
}

const saveCase = async () => {
  if (!canSaveCase.value || !selectedId.value) return
  if (!caseVariablesValid.value) {
    toast.error('变量值必须是合法的 JSON 对象')
    return
  }
  saving.value = true
  try {
    const keywords = caseForm.value.expectedKeywords
      .split(',')
      .map((k) => k.trim())
      .filter((k) => k.length > 0)
    const docIds = caseForm.value.requiredDocumentIds
      .split(',')
      .map((d) => Number(d.trim()))
      .filter((d) => !Number.isNaN(d) && d > 0)
    const payload = {
      question: caseForm.value.question.trim(),
      variables: caseVariables.value || undefined,
      expectedKeywords: keywords.length ? keywords : undefined,
      requiredDocumentIds: docIds.length ? docIds : undefined,
    }
    if (editingCaseId.value) {
      await promptTestSetApi.updatePromptTestCase(selectedId.value, editingCaseId.value, payload)
    } else {
      await promptTestSetApi.addPromptTestCase(selectedId.value, payload)
    }
    toast.success(editingCaseId.value ? '用例已保存' : '用例已添加')
    showCaseEditor.value = false
    await selectSet(selectedId.value)
    await loadSets()
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '保存用例失败')
  } finally {
    saving.value = false
  }
}

const confirmDeleteCase = (tc: PromptTestCase) => {
  deleteCaseTarget.value = tc
  confirmDeleteCaseOpen.value = true
}

const handleConfirmDeleteCase = async () => {
  const tc = deleteCaseTarget.value
  if (!selectedId.value || !tc) return
  confirmDeleteCaseLoading.value = true
  try {
    await promptTestSetApi.deletePromptTestCase(selectedId.value, tc.id)
    toast.success('用例已删除')
    await selectSet(selectedId.value)
    await loadSets()
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '删除用例失败')
  } finally {
    confirmDeleteCaseLoading.value = false
    confirmDeleteCaseOpen.value = false
    deleteCaseTarget.value = null
  }
}

// ── Batch run (async queue + polling) ───────────────────────────────

const stopPolling = () => {
  if (pollTimer !== null) {
    window.clearInterval(pollTimer)
    pollTimer = null
  }
}

const runAll = async () => {
  if (!canRun.value || !selectedId.value || !detail.value) return
  running.value = true
  runResult.value = null
  runStatus.value = null
  expandedResults.value = new Set()
  try {
    const res = await promptTestSetApi.runPromptTestSet(selectedId.value, {
      templateContent: runTemplateContent.value.trim(),
      knowledgeBaseId: runKbId.value,
      templateId: selectedTemplate.value?.id,
    })
    runStatus.value = res.data
    toast.success(`批量测试已提交（第 ${res.data.attemptNumber} 次尝试），正在排队…`)
    startPolling(res.data.id)
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '提交批量测试失败')
    running.value = false
  }
}

const startPolling = (runId: number) => {
  stopPolling()
  pollTimer = window.setInterval(() => pollRunStatus(runId), 1500)
  pollRunStatus(runId)
}

const pollRunStatus = async (runId: number) => {
  try {
    const res = await promptTestSetApi.getPromptTestSetRunStatus(runId)
    runStatus.value = res.data
    const status = res.data.status
    if (status === 'succeeded' || status === 'failed') {
      stopPolling()
      running.value = false
      await loadRunDetail(res.data.id)
      await loadRuns(selectedId.value ?? 0)
      if (status === 'succeeded') {
        const msg = `${res.data.successCount}/${res.data.totalCases} 成功，通过率 ${res.data.passRate}%`
        if (res.data.failureCount > 0) toast.warning(`批量测试完成：${msg}`)
        else toast.success(`批量测试完成：${msg}`)
      } else {
        toast.error(`批量测试失败：${res.data.errorMessage || '未知原因'}`)
      }
    } else if (status === 'cancelled') {
      stopPolling()
      running.value = false
      await loadRunDetail(res.data.id)
      toast.warning('批量测试已取消')
    }
  } catch (err) {
    console.error('轮询批量运行状态失败:', err)
  }
}

const loadRunDetail = async (runId: number) => {
  try {
    const res = await promptTestSetApi.getPromptTestSetRun(runId)
    applyRunDetail(res.data)
  } catch (err) {
    console.error('加载运行详情失败:', err)
  }
}

const applyRunDetail = (detail: PromptTestSetRunDetail) => {
  runResult.value = {
    setId: selectedId.value ?? 0,
    runId: detail.run.id,
    status: detail.run.status,
    totalCases: detail.run.totalCases,
    successCount: detail.run.successCount,
    failureCount: detail.run.failureCount,
    passCount: detail.run.passCount,
    passRate: detail.run.passRate,
    totalElapsedMs: detail.run.totalElapsedMs,
    results: detail.results,
  }
  expandedResults.value = new Set()
}

const cancelRun = async () => {
  if (!runStatus.value || cancelling.value) return
  cancelling.value = true
  try {
    const res = await promptTestSetApi.cancelPromptTestSetRun(runStatus.value.id)
    runStatus.value = res.data
    toast.success('正在取消批量测试…')
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '取消失败')
  } finally {
    cancelling.value = false
  }
}

const retryRun = async () => {
  if (!runStatus.value || retrying.value) return
  retrying.value = true
  try {
    const res = await promptTestSetApi.retryPromptTestSetRun(runStatus.value.id)
    runStatus.value = res.data
    runResult.value = null
    expandedResults.value = new Set()
    running.value = true
    toast.success('已重新提交，正在排队…')
    startPolling(res.data.id)
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '重试失败')
  } finally {
    retrying.value = false
  }
}

const clearRun = () => {
  stopPolling()
  running.value = false
  runResult.value = null
  runStatus.value = null
  expandedResults.value = new Set()
}

const onTemplateSelect = (id: number) => {
  selectedTemplateId.value = id
  const t = templates.value.find((x) => x.id === id)
  if (t) {
    runTemplateContent.value = t.content
    selectedTemplate.value = { id: t.id, version: t.version, name: t.name }
  }
}

// Manual edits to the template content break the template association:
// the run is then recorded as a custom template, not "某模板 vN".
watch(runTemplateContent, (value) => {
  const t = selectedTemplate.value
  if (t && value !== (templates.value.find((x) => x.id === t.id)?.content ?? '')) {
    selectedTemplate.value = null
    selectedTemplateId.value = 0
  }
})

const clearTemplate = () => {
  runTemplateContent.value = ''
  selectedTemplate.value = null
  selectedTemplateId.value = 0
}

// ── Comparison ─────────────────────────────────────────────────────

const canCompare = computed(
  () => compareA.value !== undefined && compareB.value !== undefined
    && compareA.value !== compareB.value && !comparing.value,
)

const runLabel = (r: PromptTestSetRun): string => {
  if (r.templateName) return `${r.templateName} v${r.templateVersion ?? 0}`
  return '自定义模板'
}

const selectRunForDetail = async (runId: number) => {
  try {
    const res = await promptTestSetApi.getPromptTestSetRun(runId)
    applyRunDetail(res.data)
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '加载运行详情失败')
  }
}

const selectCompare = (side: 'A' | 'B', runId: number) => {
  if (side === 'A') compareA.value = runId
  else compareB.value = runId
}

const doCompare = async () => {
  if (!canCompare.value || compareA.value === undefined || compareB.value === undefined) return
  comparing.value = true
  comparison.value = null
  expandedCompare.value = new Set()
  try {
    const res = await promptTestSetApi.comparePromptTestSetRuns({
      runIdA: compareA.value,
      runIdB: compareB.value,
    })
    comparison.value = res.data
    toast.success(`对比完成：${res.data.comparedCases} 个用例`)
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '对比失败')
  } finally {
    comparing.value = false
  }
}

const toggleCompare = (id: number) => {
  const next = new Set(expandedCompare.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedCompare.value = next
}

const compareToken = (r: PromptTestCaseResult | null): string => {
  if (!r) return '-'
  return String(r.tokenUsage?.total_tokens ?? r.tokenCount ?? 0)
}

const fmtDiff = (a: PromptTestCaseResult | null, b: PromptTestCaseResult | null, field: 'elapsedMs' | 'tokenCount'): string => {
  if (!a || !b) return '-'
  const diff = a[field] - b[field]
  if (diff === 0) return '0'
  return `${diff > 0 ? '+' : ''}${diff}`
}

const toggleResult = (id: number) => {
  const next = new Set(expandedResults.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedResults.value = next
}

const resultToken = (r: PromptTestCaseResult): string => {
  const total = r.tokenUsage?.total_tokens ?? r.tokenCount ?? 0
  return String(total)
}

const resultSourceCount = (r: PromptTestCaseResult): number => r.sources?.length ?? 0

const formatMs = (ms: number): string => (ms >= 1000 ? `${(ms / 1000).toFixed(2)}s` : `${ms}ms`)

// ── Lifecycle ──────────────────────────────────────────────────────

onMounted(() => {
  loadSets()
  loadTemplatesAndKbs()
  document.addEventListener('keydown', closeDialogOnEscape)
})

onBeforeUnmount(() => {
  stopPolling()
  document.removeEventListener('keydown', closeDialogOnEscape)
})

// ESC 关闭当前打开的弹窗（a11y）
const closeDialogOnEscape = (event: KeyboardEvent) => {
  if (event.key !== 'Escape') return
  if (showSetEditor.value) showSetEditor.value = false
  else if (showCaseEditor.value) showCaseEditor.value = false
}
</script>

<template>
  <div class="space-y-6 pb-4">
    <!-- ── Page header ──────────────────────────────────────────── -->
    <section class="rounded-xl border border-border bg-card/80 shadow-[0_18px_45px_rgba(0,0,0,0.18)]">
      <div class="flex flex-col gap-5 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
        <div class="flex gap-4">
          <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-emerald-400/25 bg-emerald-400/10 text-emerald-300">
            <Layers class="h-5 w-5" />
          </div>
          <div>
            <p class="text-xs font-medium text-emerald-300">批量检查</p>
            <h1 class="mt-1 text-2xl font-semibold">批量回答检查</h1>
            <p class="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">把常用问题保存成一组，一次检查回答是否成功、是否包含必要信息，并比较不同回答方案。</p>
          </div>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <Button variant="outline" class="gap-2" :disabled="creatingExample" @click="createExampleSet">
            <LoaderCircle v-if="creatingExample" class="h-4 w-4 animate-spin" />
            <FlaskConical v-else class="h-4 w-4" />
            {{ creatingExample ? '正在创建…' : '使用示例' }}
          </Button>
          <Button class="gap-2" @click="openCreateSet"><Plus class="h-4 w-4" />新建问题组</Button>
        </div>
      </div>
    </section>

    <div class="grid gap-6 xl:grid-cols-[minmax(19rem,0.85fr)_minmax(0,1.6fr)]">
      <!-- ── Left: set list ─────────────────────────────────────── -->
      <Card class="border-border/60 bg-card/50">
        <CardHeader class="flex-row items-center justify-between space-y-0 pb-3">
          <CardTitle class="text-base">问题组</CardTitle>
          <Button size="sm" variant="outline" @click="openCreateSet">
            <Plus class="mr-1 h-4 w-4" /> 新建
          </Button>
        </CardHeader>
        <CardContent class="space-y-2">
          <button
            v-for="s in sets"
            :key="s.id"
            class="w-full rounded-xl border p-3 text-left transition-colors"
            :class="s.id === selectedId ? 'border-violet-400/40 bg-violet-400/10' : 'border-border/60 bg-card hover:bg-accent/40'"
            @click="selectSet(s.id)"
          >
            <div class="flex items-center justify-between">
              <span class="font-medium">{{ s.name }}</span>
              <Badge variant="secondary">{{ s.caseCount }} 个问题</Badge>
            </div>
            <p v-if="s.description" class="mt-1 line-clamp-1 text-xs text-muted-foreground">{{ s.description }}</p>
            <p class="mt-1 text-[11px] text-muted-foreground">{{ s.updatedAt?.slice(0, 10) }}</p>
          </button>

          <div v-if="!loading && sets.length === 0" class="rounded-lg border border-dashed p-5 text-center">
            <p class="text-sm font-medium text-foreground">还没有问题组</p>
            <p class="mt-1 text-xs leading-5 text-muted-foreground">使用示例可立即体验，也可以新建自己的常用问题。</p>
            <Button size="sm" variant="outline" class="mt-3 gap-1.5" :disabled="creatingExample" @click="createExampleSet">
              <FlaskConical class="h-3.5 w-3.5" /> 使用示例
            </Button>
          </div>
        </CardContent>
      </Card>

      <!-- ── Right: detail + run ────────────────────────────────── -->
      <div class="space-y-6">
        <!-- Set detail -->
        <Card class="border-border/60 bg-card/50">
          <CardHeader class="flex-row items-center justify-between space-y-0 pb-3">
            <div>
              <CardTitle class="text-base">{{ detail?.name || '从示例开始，3 步看懂这个页面' }}</CardTitle>
              <CardDescription v-if="detail?.description">{{ detail.description }}</CardDescription>
            </div>
            <div v-if="detail" class="flex gap-2">
              <Button size="sm" variant="outline" @click="openEditSet">
                <Save class="mr-1 h-4 w-4" /> 编辑名称
              </Button>
              <Button size="sm" variant="outline" class="text-destructive hover:text-destructive" @click="confirmDeleteSet">
                <Trash2 class="mr-1 h-4 w-4" /> 删除
              </Button>
            </div>
          </CardHeader>

          <CardContent>
            <template v-if="detail">
              <div class="mb-3 flex items-center justify-between">
                <div>
                  <h3 class="text-sm font-medium">1. 准备测试问题（{{ detail.cases.length }}）</h3>
                  <p class="mt-1 text-xs text-muted-foreground">保存你希望 AI 每次都能答好的问题，并设置必要关键词。</p>
                </div>
                <Button size="sm" variant="outline" @click="openAddCase">
                  <Plus class="mr-1 h-4 w-4" /> 添加问题
                </Button>
              </div>

              <div class="space-y-2">
                <div v-for="(tc, i) in detail.cases" :key="tc.id" class="rounded-xl border border-border/60 bg-card p-3">
                  <div class="flex items-start justify-between gap-2">
                    <div class="min-w-0">
                      <p class="text-sm font-medium">
                        <span class="mr-1.5 text-muted-foreground">#{{ i + 1 }}</span>{{ tc.question }}
                      </p>
                      <p v-if="tc.variables && Object.keys(tc.variables).length" class="mt-1 text-xs text-muted-foreground">
                        变量：{{ JSON.stringify(tc.variables) }}
                      </p>
                      <div v-if="tc.expectedKeywords?.length" class="mt-2 flex flex-wrap gap-1.5">
                        <Badge v-for="keyword in tc.expectedKeywords" :key="keyword" variant="outline" class="border-amber-400/25 bg-amber-400/5 text-[11px] text-amber-200">
                          回答需包含：{{ keyword }}
                        </Badge>
                      </div>
                    </div>
                    <div class="flex shrink-0 gap-1">
                      <Button size="sm" variant="ghost" title="编辑问题" @click="openEditCase(tc)">
                        <Save class="h-3.5 w-3.5" />
                      </Button>
                      <Button size="sm" variant="ghost" title="删除问题" class="text-destructive" @click="confirmDeleteCase(tc)">
                        <Trash2 class="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>
                </div>

                <div v-if="detail.cases.length === 0" class="rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground">
                  还没有测试问题。点击“添加问题”，或重新使用示例快速体验。
                </div>
              </div>
            </template>
            <div v-else class="space-y-5">
              <div class="grid gap-3 sm:grid-cols-3">
                <div class="border-l-2 border-emerald-400/60 pl-3">
                  <p class="text-sm font-medium">1. 保存常用问题</p>
                  <p class="mt-1 text-xs leading-5 text-muted-foreground">例如问候、退款咨询、知识库问答。</p>
                </div>
                <div class="border-l-2 border-cyan-400/60 pl-3">
                  <p class="text-sm font-medium">2. 选择回答方案</p>
                  <p class="mt-1 text-xs leading-5 text-muted-foreground">选择一套规则，也可以直接修改内容。</p>
                </div>
                <div class="border-l-2 border-amber-400/60 pl-3">
                  <p class="text-sm font-medium">3. 查看是否通过</p>
                  <p class="mt-1 text-xs leading-5 text-muted-foreground">逐条查看回答、模型、耗时和未通过原因。</p>
                </div>
              </div>
              <div class="rounded-lg border border-border bg-muted/20 p-4">
                <p class="text-sm font-medium">示例：客服回答检查</p>
                <p class="mt-1 text-xs text-muted-foreground">问题“我想申请退款，需要准备什么信息？” → 回答中包含“退款”即通过。</p>
              </div>
              <div class="flex flex-wrap gap-2">
                <Button class="gap-2" :disabled="creatingExample" @click="createExampleSet">
                  <FlaskConical class="h-4 w-4" /> {{ creatingExample ? '正在创建…' : '创建示例并体验' }}
                </Button>
                <Button variant="outline" class="gap-2" @click="openCreateSet"><Plus class="h-4 w-4" />新建自己的问题组</Button>
              </div>
            </div>
          </CardContent>
        </Card>

        <!-- Run config -->
        <Card v-if="detail" class="border-border/60 bg-card/50">
          <CardHeader class="pb-3">
            <CardTitle class="flex items-center gap-2 text-base"><Play class="h-4 w-4 text-cyan-300" /> 2. 选择回答方案并开始检查</CardTitle>
            <CardDescription>回答方案决定 AI 的身份、语气和格式；需要依据资料回答时，再选择知识库。</CardDescription>
          </CardHeader>
          <CardContent class="space-y-4">
            <div class="space-y-1.5">
              <Label>回答方案</Label>
              <div class="mb-1.5 flex gap-2">
                <select
                  :value="selectedTemplateId"
                  @change="onTemplateSelect(Number(($event.target as HTMLSelectElement).value))"
                  class="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
                >
                  <option :value="0">选择已保存的回答方案，或直接修改下方内容</option>
                  <optgroup v-if="publishedTemplates.length" label="已发布">
                    <option v-for="t in publishedTemplates" :key="t.id" :value="t.id">{{ t.name }} (v{{ t.version }})</option>
                  </optgroup>
                  <optgroup v-if="draftTemplates.length" label="草稿">
                    <option v-for="t in draftTemplates" :key="t.id" :value="t.id">{{ t.name }} (v{{ t.version }})</option>
                  </optgroup>
                </select>
                <Button v-if="selectedTemplateId" variant="outline" size="sm" @click="clearTemplate">清除</Button>
              </div>
              <textarea v-model="runTemplateContent" rows="5" maxlength="8000" class="block w-full resize-y rounded-xl border border-input bg-background/60 px-3.5 py-3 text-sm leading-6 outline-none placeholder:text-muted-foreground focus:border-primary/50 focus:ring-2 focus:ring-primary/20" placeholder="例如：你是专业、耐心的客服助手。请直接回答用户问题，不确定时明确说明。" />
              <p v-if="selectedTemplate" class="text-xs text-cyan-300">当前使用：{{ selectedTemplate.name }} v{{ selectedTemplate.version }}，运行后可与其他版本对比。</p>
              <p v-else class="text-xs text-muted-foreground">可以直接编辑上方规则；修改后会作为临时方案运行。</p>
            </div>

            <div class="space-y-1.5">
              <Label>是否使用知识库</Label>
              <select
                v-model="runKbId"
                class="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
              >
                <option :value="undefined">不使用知识库，只检查回答方式</option>
                <option v-for="kb in knowledgeBases" :key="kb.id" :value="kb.id">使用知识库：{{ kb.name }}</option>
              </select>
              <p class="text-xs text-muted-foreground">普通问候、语气和格式检查无需知识库；资料问答请选择对应知识库。</p>
            </div>

            <!-- Running progress / cancel -->
            <div v-if="isRunActive" class="rounded-xl border border-violet-400/25 bg-violet-400/5 p-3">
              <div class="flex items-center justify-between gap-2">
                <p class="flex items-center gap-2 text-sm text-violet-200">
                  <LoaderCircle class="h-4 w-4 animate-spin" />
                  {{ runStatus?.status === 'pending' ? '排队中…' : `正在运行 ${runStatus?.progressCount ?? 0}/${runStatus?.totalCases ?? 0}` }}
                </p>
                <span class="text-xs text-muted-foreground">第 {{ runStatus?.attemptNumber ?? 1 }} 次尝试</span>
              </div>
              <div class="mt-2 h-2 w-full overflow-hidden rounded-full bg-muted">
                <div class="h-full rounded-full bg-violet-400 transition-all duration-300" :style="{ width: `${progressPercent}%` }" />
              </div>
              <div class="mt-2 flex justify-between text-[11px] text-muted-foreground">
                <span>{{ progressPercent }}%</span>
                <span>通过率 {{ runStatus?.passRate ?? 0 }}%</span>
              </div>
              <div class="mt-3 flex gap-2">
                <Button variant="outline" class="flex-1 text-destructive hover:text-destructive" :disabled="cancelling" @click="cancelRun">
                  <XCircle class="mr-1 h-4 w-4" /> {{ cancelling ? '取消中…' : '取消运行' }}
                </Button>
              </div>
            </div>

            <!-- Terminal failure / cancelled → retry -->
            <div v-else-if="runStatus && (runStatus.status === 'failed' || runStatus.status === 'cancelled')" class="rounded-xl border p-3" :class="runStatus.status === 'cancelled' ? 'border-amber-400/25 bg-amber-400/5' : 'border-red-500/30 bg-red-500/5'">
              <p class="flex items-center gap-2 text-sm" :class="runStatus.status === 'cancelled' ? 'text-amber-200' : 'text-red-300'">
                <XCircle class="h-4 w-4" />
                {{ runStatus.status === 'cancelled' ? `批量测试已取消（第 ${runStatus.attemptNumber} 次尝试）` : `批量测试失败：${runStatus.errorMessage || '未知原因'}` }}
              </p>
              <div class="mt-3 flex gap-2">
                <Button class="flex-1" :disabled="retrying" @click="retryRun">
                  <RefreshCw class="mr-1 h-4 w-4" /> {{ retrying ? '重新提交中…' : '重新运行' }}
                </Button>
              </div>
            </div>

            <div class="flex items-center gap-2">
              <Button :disabled="!canRun" class="flex-1" @click="runAll">
                <LoaderCircle v-if="running" class="mr-2 h-4 w-4 animate-spin" />
                <Play v-else class="mr-2 h-4 w-4" />
                {{ running ? '正在逐个检查…' : `检查全部 ${detail?.cases.length ?? 0} 个问题` }}
              </Button>
              <Button variant="outline" @click="clearRun">
                <RefreshCw class="mr-1 h-4 w-4" /> 重置结果
              </Button>
            </div>
          </CardContent>
        </Card>

        <!-- Run report -->
        <Card v-if="runResult" class="border-border/60 bg-card/50">
          <CardHeader class="pb-3">
            <CardTitle class="flex flex-wrap items-center gap-2 text-base">
              3. 本次检查结果
              <Badge variant="secondary">{{ runResult.successCount }}/{{ runResult.totalCases }} 成功</Badge>
              <Badge variant="outline" class="border-emerald-400/25 text-emerald-300">{{ runResult.passCount }}/{{ runResult.totalCases }} 通过</Badge>
              <Badge variant="outline" class="border-violet-400/25 text-violet-200">通过率 {{ runResult.passRate }}%</Badge>
              <span class="ml-auto flex items-center gap-1 text-xs font-normal text-muted-foreground">
                <Clock class="h-3.5 w-3.5" /> 总耗时 {{ totalElapsed }}
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent class="space-y-2">
            <div v-for="r in runResult.results" :key="r.caseId" class="rounded-xl border p-3" :class="r.passed ? 'border-emerald-500/25 bg-emerald-500/5' : r.success ? 'border-border/60 bg-card' : 'border-red-500/30 bg-red-500/5'">
              <button class="flex w-full items-start gap-2 text-left" @click="toggleResult(r.caseId)">
                <CheckCircle2 v-if="r.passed" class="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
                <XCircle v-else-if="!r.success" class="mt-0.5 h-4 w-4 shrink-0 text-red-400" />
                <AlertTriangle v-else class="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
                <div class="min-w-0 flex-1">
                  <p class="text-sm font-medium">{{ r.question }}</p>
                  <div class="mt-1 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                    <span class="flex items-center gap-1"><Clock class="h-3 w-3" /> {{ formatMs(r.elapsedMs) }}</span>
                    <span v-if="r.model" class="text-cyan-300">{{ r.model }}</span>
                    <span>用量 {{ resultToken(r) }}</span>
                    <span v-if="r.success">来源 {{ resultSourceCount(r) }}</span>
                    <span v-if="r.success && r.passed" class="text-emerald-300">通过</span>
                    <span v-if="r.success && !r.passed" class="text-amber-300">未通过</span>
                    <span v-if="!r.success" class="text-red-400">{{ r.error }}</span>
                  </div>
                  <span v-if="expandedResults.has(r.caseId)" class="mt-0.5 flex items-center gap-0.5 text-[11px] text-violet-300">
                    <ChevronDown class="h-3 w-3" /> 收起
                  </span>
                  <span v-else class="mt-0.5 flex items-center gap-0.5 text-[11px] text-violet-300">
                    <ChevronRight class="h-3 w-3" /> 展开详情
                  </span>
                </div>
              </button>

              <div v-if="expandedResults.has(r.caseId)" class="mt-3 space-y-3 border-t border-border/40 pt-3">
                <div v-if="r.passNotes && r.passNotes.length">
                  <p class="mb-1 text-[11px] font-medium uppercase tracking-wide text-amber-300">未通过原因</p>
                  <ul class="space-y-1">
                    <li v-for="(note, ni) in r.passNotes" :key="ni" class="rounded-md bg-amber-400/10 px-2 py-1 font-mono text-xs text-amber-200">{{ note }}</li>
                  </ul>
                </div>
                <div>
                  <p class="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">实际模板</p>
                  <pre class="max-h-40 overflow-auto whitespace-pre-wrap rounded-lg bg-muted/50 p-2 font-mono text-xs">{{ r.renderedTemplate }}</pre>
                </div>
                <div>
                  <p class="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">AI 回答</p>
                  <p v-if="r.success" class="whitespace-pre-wrap text-sm leading-6">{{ r.content }}</p>
                  <p v-else class="text-sm text-red-400">{{ r.error }}</p>
                </div>
                <div v-if="r.sources && r.sources.length">
                  <p class="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">来源（{{ r.sources.length }}）</p>
                  <div class="space-y-1">
                    <p v-for="(s, idx) in r.sources" :key="idx" class="line-clamp-1 rounded-md bg-muted/50 px-2 py-1 font-mono text-xs text-muted-foreground">
                      {{ String(s.document_name || s.title || s.document_id || '') }}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        <!-- Run history -->
        <Card v-if="detail" class="border-border/60 bg-card/50">
          <CardHeader class="pb-3">
            <CardTitle class="flex items-center gap-2 text-base"><History class="h-4 w-4 text-amber-300" /> 历史结果与方案对比</CardTitle>
            <CardDescription>每次检查都会保存在这里。选择两次结果，可以比较回答内容、速度、用量和通过率。</CardDescription>
          </CardHeader>
          <CardContent class="space-y-4">
            <div v-if="runs.length === 0" class="rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground">
              暂无运行历史。执行一次批量运行后会在此展示。
            </div>

            <template v-else>
              <div class="space-y-2">
                <div v-for="r in runs" :key="r.id" class="flex flex-wrap items-center gap-3 rounded-xl border border-border/60 bg-card px-3 py-2.5">
                  <button class="flex min-w-0 flex-1 items-center gap-3 text-left" @click="selectRunForDetail(r.id)">
                    <div class="min-w-0 flex-1">
                      <p class="truncate text-sm font-medium text-cyan-300">{{ runLabel(r) }}</p>
                      <p class="text-xs text-muted-foreground">{{ r.createdAt?.slice(0, 19).replace('T', ' ') }}</p>
                    </div>
                    <Badge variant="secondary">{{ r.successCount }}/{{ r.totalCases }} 成功</Badge>
                    <Badge variant="outline" class="border-violet-400/25 text-violet-200">通过 {{ r.passRate }}%</Badge>
                    <span class="text-xs text-muted-foreground">{{ formatMs(r.totalElapsedMs) }}</span>
                  </button>
                  <label class="flex items-center gap-1 text-xs text-muted-foreground">
                    <input type="radio" name="compareA" :checked="compareA === r.id" @change="selectCompare('A', r.id)" /> 左侧
                  </label>
                  <label class="flex items-center gap-1 text-xs text-muted-foreground">
                    <input type="radio" name="compareB" :checked="compareB === r.id" @change="selectCompare('B', r.id)" /> 右侧
                  </label>
                </div>
              </div>

              <div class="flex items-center gap-2">
                <Button :disabled="!canCompare" class="flex-1" @click="doCompare">
                  <LoaderCircle v-if="comparing" class="mr-2 h-4 w-4 animate-spin" />
                  <Scale v-else class="mr-2 h-4 w-4" />
                  {{ comparing ? '对比中…' : '对比两次运行' }}
                </Button>
                <Button variant="outline" @click="comparison = null">
                  <RefreshCw class="mr-1 h-4 w-4" /> 清除
                </Button>
              </div>
            </template>
          </CardContent>
        </Card>

        <!-- Comparison result -->
        <Card v-if="comparison" class="border-violet-400/25 bg-violet-400/5">
          <CardHeader class="pb-3">
            <CardTitle class="flex flex-wrap items-center gap-2 text-base">
              <Scale class="h-4 w-4 text-violet-300" /> 版本对比
              <Badge variant="outline" class="border-violet-400/25 text-violet-200">{{ runLabel(comparison.runA) }}</Badge>
              <Badge variant="outline" class="border-violet-400/25 text-violet-200">通过率 {{ comparison.runA.passRate }}%</Badge>
              <span class="text-xs text-muted-foreground">vs</span>
              <Badge variant="outline" class="border-violet-400/25 text-violet-200">{{ runLabel(comparison.runB) }}</Badge>
              <Badge variant="outline" class="border-violet-400/25 text-violet-200">通过率 {{ comparison.runB.passRate }}%</Badge>
              <span class="ml-auto text-xs text-muted-foreground">共 {{ comparison.comparedCases }} 个用例</span>
            </CardTitle>
          </CardHeader>
          <CardContent class="space-y-2">
            <div v-for="c in comparison.comparisons" :key="c.caseId" class="rounded-xl border border-border/60 bg-card p-3">
              <button class="flex w-full items-center gap-2 text-left" @click="toggleCompare(c.caseId)">
                <span v-if="c.answerIdentical === true" class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-400/15 text-emerald-300"><Check class="h-3.5 w-3.5" /></span>
                <span v-else-if="c.answerIdentical === false" class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-amber-400/15 text-amber-300"><Diff class="h-3.5 w-3.5" /></span>
                <span v-else class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground"><Minus class="h-3.5 w-3.5" /></span>
                <span class="min-w-0 flex-1 text-sm font-medium">{{ c.question }}</span>
                <span class="flex items-center gap-3 text-xs text-muted-foreground">
                  <span class="flex items-center gap-1"><Clock class="h-3 w-3" /> 差 {{ fmtDiff(c.resultA, c.resultB, 'elapsedMs') }}ms</span>
                  <span class="flex items-center gap-1"><Zap class="h-3 w-3" /> 用量差 {{ fmtDiff(c.resultA, c.resultB, 'tokenCount') }}</span>
                </span>
                <ChevronDown v-if="expandedCompare.has(c.caseId)" class="h-3.5 w-3.5 text-violet-300" />
                <ChevronRight v-else class="h-3.5 w-3.5 text-violet-300" />
              </button>

              <div v-if="expandedCompare.has(c.caseId)" class="mt-3 grid gap-3 border-t border-border/40 pt-3 sm:grid-cols-2">
                <div class="rounded-xl border p-3" :class="(c.resultA?.success ?? false) ? (c.resultA?.passed ? 'border-emerald-500/20 bg-emerald-500/5' : 'border-amber-500/25 bg-amber-500/5') : 'border-red-500/25 bg-red-500/5'">
                  <p class="mb-1.5 flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                    <span class="text-cyan-300">{{ runLabel(comparison.runA) }}</span>
                    <span v-if="c.resultA?.success === false" class="text-red-400">失败</span>
                    <span v-else-if="c.resultA?.passed" class="text-emerald-300">通过</span>
                    <span v-else-if="c.resultA" class="text-amber-300">未通过</span>
                  </p>
                  <p v-if="c.resultA?.content" class="whitespace-pre-wrap text-sm leading-6">{{ c.resultA.content }}</p>
                  <p v-else-if="c.resultA?.error" class="text-sm text-red-400">{{ c.resultA.error }}</p>
                  <p v-else class="text-sm text-muted-foreground">（无回答）</p>
                  <div v-if="c.resultA?.passNotes?.length" class="mt-2 space-y-1">
                    <p v-for="(note, ni) in c.resultA.passNotes" :key="ni" class="rounded-md bg-amber-400/10 px-2 py-1 font-mono text-[11px] text-amber-200">{{ note }}</p>
                  </div>
                  <div class="mt-2 flex flex-wrap gap-3 text-xs text-muted-foreground">
                    <span>{{ c.resultA ? formatMs(c.resultA.elapsedMs) : '-' }} · 用量 {{ compareToken(c.resultA) }}</span>
                  </div>
                </div>
                <div class="rounded-xl border p-3" :class="(c.resultB?.success ?? false) ? (c.resultB?.passed ? 'border-emerald-500/20 bg-emerald-500/5' : 'border-amber-500/25 bg-amber-500/5') : 'border-red-500/25 bg-red-500/5'">
                  <p class="mb-1.5 flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                    <span class="text-cyan-300">{{ runLabel(comparison.runB) }}</span>
                    <span v-if="c.resultB?.success === false" class="text-red-400">失败</span>
                    <span v-else-if="c.resultB?.passed" class="text-emerald-300">通过</span>
                    <span v-else-if="c.resultB" class="text-amber-300">未通过</span>
                  </p>
                  <p v-if="c.resultB?.content" class="whitespace-pre-wrap text-sm leading-6">{{ c.resultB.content }}</p>
                  <p v-else-if="c.resultB?.error" class="text-sm text-red-400">{{ c.resultB.error }}</p>
                  <p v-else class="text-sm text-muted-foreground">（无回答）</p>
                  <div v-if="c.resultB?.passNotes?.length" class="mt-2 space-y-1">
                    <p v-for="(note, ni) in c.resultB.passNotes" :key="ni" class="rounded-md bg-amber-400/10 px-2 py-1 font-mono text-[11px] text-amber-200">{{ note }}</p>
                  </div>
                  <div class="mt-2 flex flex-wrap gap-3 text-xs text-muted-foreground">
                    <span>{{ c.resultB ? formatMs(c.resultB.elapsedMs) : '-' }} · 用量 {{ compareToken(c.resultB) }}</span>
                  </div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>

    <!-- ── Set editor dialog ────────────────────────────────────── -->
    <div v-if="showSetEditor" role="dialog" aria-modal="true" aria-label="编辑问题组" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" @click.self="showSetEditor = false">
      <Card class="w-full max-w-md">
        <CardHeader>
          <CardTitle class="text-base">{{ editingSetId ? '编辑问题组' : '新建问题组' }}</CardTitle>
        </CardHeader>
        <CardContent class="space-y-3">
          <div class="space-y-1.5">
            <Label>名称</Label>
            <Input v-model="setForm.name" maxlength="100" placeholder="例如：客服回答检查" />
          </div>
          <div class="space-y-1.5">
            <Label>描述（可选）</Label>
            <textarea v-model="setForm.description" rows="2" maxlength="500" class="block w-full resize-y rounded-xl border border-input bg-background/60 px-3.5 py-3 text-sm leading-6 outline-none placeholder:text-muted-foreground focus:border-primary/50 focus:ring-2 focus:ring-primary/20" placeholder="例如：检查问候、退款咨询和投诉回复是否符合客服规范" />
          </div>
          <div class="flex justify-end gap-2 pt-1">
            <Button variant="outline" @click="showSetEditor = false">取消</Button>
            <Button :disabled="!canSaveSet" @click="saveSet">
              <Save class="mr-1 h-4 w-4" /> 保存
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>

    <!-- ── Case editor dialog ───────────────────────────────────── -->
    <div v-if="showCaseEditor" role="dialog" aria-modal="true" aria-label="编辑用例" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" @click.self="showCaseEditor = false">
      <Card class="w-full max-w-lg">
        <CardHeader>
          <CardTitle class="text-base">{{ editingCaseId ? '编辑测试问题' : '添加测试问题' }}</CardTitle>
          <CardDescription v-if="!editingCaseId">可以点击示例自动填写，再按实际业务修改。</CardDescription>
        </CardHeader>
        <CardContent class="space-y-3">
          <div v-if="!editingCaseId" class="grid gap-2 sm:grid-cols-3">
            <button
              v-for="example in caseExamples"
              :key="example.name"
              type="button"
              class="rounded-lg border border-border bg-muted/20 px-3 py-2 text-left transition-colors hover:border-primary/40 hover:bg-primary/[0.05]"
              @click="applyCaseExample(example)"
            >
              <span class="block text-xs font-medium">{{ example.name }}</span>
              <span class="mt-0.5 block text-[11px] leading-4 text-muted-foreground">{{ example.description }}</span>
            </button>
          </div>
          <div class="space-y-1.5">
            <Label>用户会问的问题</Label>
            <textarea v-model="caseForm.question" rows="3" maxlength="4000" class="block w-full resize-y rounded-xl border border-input bg-background/60 px-3.5 py-3 text-sm leading-6 outline-none placeholder:text-muted-foreground focus:border-primary/50 focus:ring-2 focus:ring-primary/20" placeholder="例如：我想申请退款，需要准备什么信息？" />
          </div>
          <div class="space-y-1.5">
            <Label>回答中必须出现的词（可选）</Label>
            <input v-model="caseForm.expectedKeywords" type="text" class="block w-full rounded-xl border border-input bg-background/60 px-3.5 py-2.5 text-sm outline-none placeholder:text-muted-foreground focus:border-primary/50 focus:ring-2 focus:ring-primary/20" placeholder="例如：退款, 处理时间" />
            <p class="text-xs text-muted-foreground">多个词用逗号分开。回答包含全部词时，这个问题才显示“通过”。</p>
          </div>

          <details class="rounded-lg border border-border bg-muted/10 p-3">
            <summary class="cursor-pointer text-sm font-medium">高级设置（变量、指定引用文档）</summary>
            <div class="mt-3 space-y-3 border-t border-border/60 pt-3">
              <div class="space-y-1.5">
                <Label>模板变量（可选）</Label>
                <textarea v-model="caseForm.variables" rows="4" class="block w-full resize-y rounded-xl border border-input bg-background/60 px-3.5 py-3 font-mono text-xs leading-6 outline-none placeholder:text-muted-foreground focus:border-primary/50 focus:ring-2 focus:ring-primary/20" placeholder='{"role":"客服","topic":"退款"}' />
                <p class="text-xs text-muted-foreground" :class="caseVariablesValid ? '' : 'text-red-400'">
                  {{ caseVariablesValid ? `用于替换回答方案中的 ${varBraces}` : '格式错误，请输入 JSON 对象，例如 {"role":"客服"}' }}
                </p>
              </div>
            <div class="space-y-1.5">
              <Label>必须引用的文档 ID（可选）</Label>
              <input v-model="caseForm.requiredDocumentIds" type="text" class="block w-full rounded-xl border border-input bg-background/60 px-3.5 py-2.5 text-sm outline-none placeholder:text-muted-foreground focus:border-primary/50 focus:ring-2 focus:ring-primary/20" placeholder="例如：11, 22" />
              <p class="text-xs text-muted-foreground">仅用于严格检查知识库来源，多个 ID 用逗号分开。</p>
            </div>
            </div>
          </details>
          <div class="flex justify-end gap-2 pt-1">
            <Button variant="outline" @click="showCaseEditor = false">取消</Button>
            <Button :disabled="!canSaveCase" @click="saveCase">
              <Save class="mr-1 h-4 w-4" /> 保存
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>

    <ConfirmDialog
      v-model:open="confirmDeleteSetOpen"
      title="删除确认"
      :description="`确定删除用例集「${deleteSetTarget?.name}」及其全部用例？`"
      confirm-text="删除"
      destructive
      :loading="confirmDeleteSetLoading"
      @confirm="handleConfirmDeleteSet"
    />
    <ConfirmDialog
      v-model:open="confirmDeleteCaseOpen"
      title="删除确认"
      :description="`确定删除用例「${deleteCaseTarget?.question.slice(0, 30)}」？`"
      confirm-text="删除"
      destructive
      :loading="confirmDeleteCaseLoading"
      @confirm="handleConfirmDeleteCase"
    />
  </div>
</template>
