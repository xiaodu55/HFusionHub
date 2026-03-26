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

const confirmDeleteSet = async () => {
  if (!selectedSet.value) return
  if (!confirm(`确定删除用例集「${selectedSet.value.name}」及其全部用例？`)) return
  try {
    await promptTestSetApi.deletePromptTestSet(selectedSet.value.id)
    toast.success('用例集已删除')
    selectedId.value = null
    detail.value = null
    runResult.value = null
    await loadSets()
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '删除用例集失败')
  }
}

// ── Case CRUD ──────────────────────────────────────────────────────

const openAddCase = () => {
  editingCaseId.value = null
  caseForm.value = { question: '', variables: '', expectedKeywords: '', requiredDocumentIds: '' }
  showCaseEditor.value = true
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

const confirmDeleteCase = async (tc: PromptTestCase) => {
  if (!selectedId.value) return
  if (!confirm(`确定删除用例「${tc.question.slice(0, 30)}」？`)) return
  try {
    await promptTestSetApi.deletePromptTestCase(selectedId.value, tc.id)
    toast.success('用例已删除')
    await selectSet(selectedId.value)
    await loadSets()
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '删除用例失败')
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
})

onBeforeUnmount(() => {
  stopPolling()
})
</script>

<template>
  <div class="space-y-6 pb-4">
    <!-- ── Hero banner ──────────────────────────────────────────── -->
    <section class="relative overflow-hidden rounded-2xl border border-border bg-card/80 shadow-[0_18px_45px_rgba(0,0,0,0.18)]">
      <div class="pointer-events-none absolute -right-12 -top-16 h-48 w-48 rounded-full bg-violet-400/10 blur-3xl" />
      <div class="relative flex flex-col gap-5 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
        <div class="flex gap-4">
          <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-violet-400/25 bg-violet-400/10 text-violet-200">
            <Layers class="h-5 w-5" />
          </div>
          <div>
            <p class="text-xs font-medium tracking-[0.16em] text-violet-200/90">PROMPT TEST SUITES</p>
            <h1 class="mt-1 text-2xl font-semibold tracking-tight">提示词测试用例集</h1>
            <p class="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">保存固定问题与变量值，批量运行同一组问题，为不同模板/版本的结果对比打基础。</p>
          </div>
        </div>
        <Badge variant="outline" class="border-violet-400/25 bg-violet-400/10 text-violet-200 shrink-0">
          {{ sets.length }} 个用例集
        </Badge>
      </div>
    </section>

    <div class="grid gap-6 xl:grid-cols-[minmax(19rem,0.85fr)_minmax(0,1.6fr)]">
      <!-- ── Left: set list ─────────────────────────────────────── -->
      <Card class="border-border/60 bg-card/50">
        <CardHeader class="flex-row items-center justify-between space-y-0 pb-3">
          <CardTitle class="text-base">用例集</CardTitle>
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
              <Badge variant="secondary">{{ s.caseCount }} 用例</Badge>
            </div>
            <p v-if="s.description" class="mt-1 line-clamp-1 text-xs text-muted-foreground">{{ s.description }}</p>
            <p class="mt-1 text-[11px] text-muted-foreground">{{ s.updatedAt?.slice(0, 10) }}</p>
          </button>

          <div v-if="!loading && sets.length === 0" class="rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground">
            暂无用例集，点击右上角新建。
          </div>
        </CardContent>
      </Card>

      <!-- ── Right: detail + run ────────────────────────────────── -->
      <div class="space-y-6">
        <!-- Set detail -->
        <Card class="border-border/60 bg-card/50">
          <CardHeader class="flex-row items-center justify-between space-y-0 pb-3">
            <div>
              <CardTitle class="text-base">{{ detail?.name || '选择用例集' }}</CardTitle>
              <CardDescription v-if="detail?.description">{{ detail.description }}</CardDescription>
            </div>
            <div v-if="detail" class="flex gap-2">
              <Button size="sm" variant="outline" @click="openEditSet">
                <Save class="mr-1 h-4 w-4" /> 重命名
              </Button>
              <Button size="sm" variant="outline" class="text-destructive hover:text-destructive" @click="confirmDeleteSet">
                <Trash2 class="mr-1 h-4 w-4" /> 删除
              </Button>
            </div>
          </CardHeader>

          <CardContent>
            <template v-if="detail">
              <div class="mb-3 flex items-center justify-between">
                <h3 class="text-sm font-medium">测试用例（{{ detail.cases.length }}）</h3>
                <Button size="sm" variant="outline" @click="openAddCase">
                  <Plus class="mr-1 h-4 w-4" /> 添加用例
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
                    </div>
                    <div class="flex shrink-0 gap-1">
                      <Button size="sm" variant="ghost" @click="openEditCase(tc)">
                        <Save class="h-3.5 w-3.5" />
                      </Button>
                      <Button size="sm" variant="ghost" class="text-destructive" @click="confirmDeleteCase(tc)">
                        <Trash2 class="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>
                </div>

                <div v-if="detail.cases.length === 0" class="rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground">
                  暂无用例。添加固定问题与变量值后即可批量运行。
                </div>
              </div>
            </template>
            <p v-else class="text-sm text-muted-foreground">从左侧选择一个用例集，或新建一个。</p>
          </CardContent>
        </Card>

        <!-- Run config -->
        <Card class="border-border/60 bg-card/50">
          <CardHeader class="pb-3">
            <CardTitle class="flex items-center gap-2 text-base"><Play class="h-4 w-4 text-violet-300" /> 批量运行</CardTitle>
            <CardDescription>选择模板（支持 <code class="text-violet-300">{{ varBraces }}</code> 替换）、知识库（可选），对全部用例逐个运行。</CardDescription>
          </CardHeader>
          <CardContent class="space-y-4">
            <div class="space-y-1.5">
              <Label>模板（system 指令，≤8000 字符）</Label>
              <div class="mb-1.5 flex gap-2">
                <select
                  :value="selectedTemplateId"
                  @change="onTemplateSelect(Number(($event.target as HTMLSelectElement).value))"
                  class="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
                >
                  <option :value="0">选择模板（内容将填入下方）</option>
                  <optgroup v-if="publishedTemplates.length" label="已发布">
                    <option v-for="t in publishedTemplates" :key="t.id" :value="t.id">{{ t.name }} (v{{ t.version }})</option>
                  </optgroup>
                  <optgroup v-if="draftTemplates.length" label="草稿">
                    <option v-for="t in draftTemplates" :key="t.id" :value="t.id">{{ t.name }} (v{{ t.version }})</option>
                  </optgroup>
                </select>
                <Button v-if="selectedTemplateId" variant="outline" size="sm" @click="clearTemplate">清除</Button>
              </div>
              <textarea v-model="runTemplateContent" rows="5" maxlength="8000" class="block w-full resize-y rounded-xl border border-input bg-background/60 px-3.5 py-3 font-mono text-xs leading-6 outline-none placeholder:text-muted-foreground focus:border-primary/50 focus:ring-2 focus:ring-primary/20" />
              <p v-if="selectedTemplate" class="text-xs text-violet-300">已关联 {{ selectedTemplate.name }} v{{ selectedTemplate.version }}，本次运行将记录该模板版本用于对比。</p>
            </div>

            <div class="space-y-1.5">
              <Label>知识库（可选）</Label>
              <select
                v-model="runKbId"
                class="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
              >
                <option :value="undefined">纯 LLM（无知识库）</option>
                <option v-for="kb in knowledgeBases" :key="kb.id" :value="kb.id">{{ kb.name }}</option>
              </select>
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
                {{ running ? '运行中…' : `批量运行 ${detail?.cases.length ?? 0} 个用例` }}
              </Button>
              <Button variant="outline" @click="clearRun">
                <RefreshCw class="mr-1 h-4 w-4" /> 清除
              </Button>
            </div>
          </CardContent>
        </Card>

        <!-- Run report -->
        <Card v-if="runResult" class="border-border/60 bg-card/50">
          <CardHeader class="pb-3">
            <CardTitle class="flex flex-wrap items-center gap-2 text-base">
              运行报告
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
                    <span>{{ resultToken(r) }} tokens</span>
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
        <Card class="border-border/60 bg-card/50">
          <CardHeader class="pb-3">
            <CardTitle class="flex items-center gap-2 text-base"><History class="h-4 w-4 text-violet-300" /> 运行历史</CardTitle>
            <CardDescription>保存每次批量运行结果，选择两次运行（不同模板版本）即可对比回答、耗时、Token 与成功率。</CardDescription>
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
                  <span class="flex items-center gap-1"><Zap class="h-3 w-3" /> 差 {{ fmtDiff(c.resultA, c.resultB, 'tokenCount') }} token</span>
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
                    <span>{{ c.resultA ? formatMs(c.resultA.elapsedMs) : '-' }} · {{ compareToken(c.resultA) }} token</span>
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
                    <span>{{ c.resultB ? formatMs(c.resultB.elapsedMs) : '-' }} · {{ compareToken(c.resultB) }} token</span>
                  </div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>

    <!-- ── Set editor dialog ────────────────────────────────────── -->
    <div v-if="showSetEditor" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" @click.self="showSetEditor = false">
      <Card class="w-full max-w-md">
        <CardHeader>
          <CardTitle class="text-base">{{ editingSetId ? '重命名用例集' : '新建用例集' }}</CardTitle>
        </CardHeader>
        <CardContent class="space-y-3">
          <div class="space-y-1.5">
            <Label>名称</Label>
            <Input v-model="setForm.name" maxlength="100" placeholder="例如：客服话术回归" />
          </div>
          <div class="space-y-1.5">
            <Label>描述（可选）</Label>
            <textarea v-model="setForm.description" rows="2" maxlength="500" class="block w-full resize-y rounded-xl border border-input bg-background/60 px-3.5 py-3 text-sm leading-6 outline-none placeholder:text-muted-foreground focus:border-primary/50 focus:ring-2 focus:ring-primary/20" placeholder="描述该用例集覆盖的场景" />
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
    <div v-if="showCaseEditor" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" @click.self="showCaseEditor = false">
      <Card class="w-full max-w-lg">
        <CardHeader>
          <CardTitle class="text-base">{{ editingCaseId ? '编辑用例' : '添加用例' }}</CardTitle>
        </CardHeader>
        <CardContent class="space-y-3">
          <div class="space-y-1.5">
            <Label>固定问题（≤4000 字符）</Label>
            <textarea v-model="caseForm.question" rows="3" maxlength="4000" class="block w-full resize-y rounded-xl border border-input bg-background/60 px-3.5 py-3 text-sm leading-6 outline-none placeholder:text-muted-foreground focus:border-primary/50 focus:ring-2 focus:ring-primary/20" placeholder="例如：如何申请退款？" />
          </div>
          <div class="space-y-1.5">
            <Label>变量值（可选，JSON 对象，用于替换模板中的 <span class="font-mono text-violet-300">{{ varBraces }}</span>）</Label>
            <textarea v-model="caseForm.variables" rows="5" class="block w-full resize-y rounded-xl border border-input bg-background/60 px-3.5 py-3 font-mono text-xs leading-6 outline-none placeholder:text-muted-foreground focus:border-primary/50 focus:ring-2 focus:ring-primary/20" placeholder='{"role":"客服","topic":"退款"}' />
            <p class="text-xs text-muted-foreground" :class="caseVariablesValid ? '' : 'text-red-400'">
              {{ caseVariablesValid ? `模板中的 ${varBraces} 会替换为变量值` : '必须是 JSON 对象，如 {"role":"客服"}（数组/数字无效）' }}
            </p>
          </div>
          <div class="grid gap-3 sm:grid-cols-2">
            <div class="space-y-1.5">
              <Label>期望关键词（可选，逗号分隔）</Label>
              <input v-model="caseForm.expectedKeywords" type="text" class="block w-full rounded-xl border border-input bg-background/60 px-3.5 py-2.5 text-sm outline-none placeholder:text-muted-foreground focus:border-primary/50 focus:ring-2 focus:ring-primary/20" placeholder="例如：退款, 7天" />
              <p class="text-xs text-muted-foreground">AI 回答须包含每个关键词（不区分大小写）才判定通过</p>
            </div>
            <div class="space-y-1.5">
              <Label>必须引用的文档 ID（可选，逗号分隔）</Label>
              <input v-model="caseForm.requiredDocumentIds" type="text" class="block w-full rounded-xl border border-input bg-background/60 px-3.5 py-2.5 text-sm outline-none placeholder:text-muted-foreground focus:border-primary/50 focus:ring-2 focus:ring-primary/20" placeholder="例如：11, 22" />
              <p class="text-xs text-muted-foreground">回答的来源中须引用这些文档才判定通过</p>
            </div>
          </div>
          <div class="flex justify-end gap-2 pt-1">
            <Button variant="outline" @click="showCaseEditor = false">取消</Button>
            <Button :disabled="!canSaveCase" @click="saveCase">
              <Save class="mr-1 h-4 w-4" /> 保存
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  </div>
</template>
