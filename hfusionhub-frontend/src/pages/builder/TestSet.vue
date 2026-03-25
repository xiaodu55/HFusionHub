<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  FlaskConical,
  Layers,
  LoaderCircle,
  Play,
  Plus,
  RefreshCw,
  Save,
  Trash2,
  XCircle,
} from 'lucide-vue-next'
import * as promptTemplateApi from '@/api/promptTemplate'
import * as promptTestSetApi from '@/api/promptTestSet'
import * as knowledgeBaseApi from '@/api/knowledgeBase'
import type { PromptTemplate } from '@/api/promptTemplate'
import type {
  PromptTestCase,
  PromptTestCaseResult,
  PromptTestSet,
  PromptTestSetDetail,
  PromptTestSetRunResponse,
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
const caseForm = ref({ question: '', variables: '' })
const editingCaseId = ref<number | null>(null)
const showCaseEditor = ref(false)

// run config
const runTemplateContent = ref('')
const runKbId = ref<number | undefined>(undefined)
const runResult = ref<PromptTestSetRunResponse | null>(null)

// expanded case ids in the run report
const expandedResults = ref<Set<number>>(new Set())

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
  runResult.value = null
  expandedResults.value = new Set()
  try {
    const res = await promptTestSetApi.getPromptTestSet(id)
    detail.value = res.data
    if (detail.value.cases.length > 0) {
      runTemplateContent.value = runTemplateContent.value || '你是一个专业的AI助手，请用中文回答。'
    }
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '加载用例集详情失败')
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
  caseForm.value = { question: '', variables: '' }
  showCaseEditor.value = true
}

const openEditCase = (tc: PromptTestCase) => {
  editingCaseId.value = tc.id
  caseForm.value = {
    question: tc.question,
    variables: tc.variables && Object.keys(tc.variables).length ? JSON.stringify(tc.variables, null, 2) : '',
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
    const payload = {
      question: caseForm.value.question.trim(),
      variables: caseVariables.value || undefined,
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

// ── Batch run ──────────────────────────────────────────────────────

const runAll = async () => {
  if (!canRun.value || !selectedId.value || !detail.value) return
  running.value = true
  runResult.value = null
  expandedResults.value = new Set()
  try {
    const res = await promptTestSetApi.runPromptTestSet(selectedId.value, {
      templateContent: runTemplateContent.value.trim(),
      knowledgeBaseId: runKbId.value,
    })
    runResult.value = res.data
    if (res.data.failureCount > 0) {
      toast.warning(`批量测试完成：${res.data.successCount} 成功，${res.data.failureCount} 失败`)
    } else {
      toast.success(`批量测试完成：${res.data.successCount} 个用例全部成功`)
    }
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '批量测试失败')
  } finally {
    running.value = false
  }
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
              <select
                v-model="runTemplateContent"
                class="mb-1.5 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
              >
                <option value="" disabled>选择模板（内容将填入下方）</option>
                <optgroup v-if="publishedTemplates.length" label="已发布">
                  <option v-for="t in publishedTemplates" :key="t.id" :value="t.content">{{ t.name }} (v{{ t.version }})</option>
                </optgroup>
                <optgroup v-if="draftTemplates.length" label="草稿">
                  <option v-for="t in draftTemplates" :key="t.id" :value="t.content">{{ t.name }} (v{{ t.version }})</option>
                </optgroup>
              </select>
              <textarea v-model="runTemplateContent" rows="5" maxlength="8000" class="block w-full resize-y rounded-xl border border-input bg-background/60 px-3.5 py-3 font-mono text-xs leading-6 outline-none placeholder:text-muted-foreground focus:border-primary/50 focus:ring-2 focus:ring-primary/20" />
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

            <div class="flex items-center gap-2">
              <Button :disabled="!canRun" class="flex-1" @click="runAll">
                <LoaderCircle v-if="running" class="mr-2 h-4 w-4 animate-spin" />
                <Play v-else class="mr-2 h-4 w-4" />
                {{ running ? '运行中…' : `批量运行 ${detail?.cases.length ?? 0} 个用例` }}
              </Button>
              <Button variant="outline" @click="runResult = null">
                <RefreshCw class="mr-1 h-4 w-4" /> 清除
              </Button>
            </div>
          </CardContent>
        </Card>

        <!-- Run report -->
        <Card v-if="runResult" class="border-border/60 bg-card/50">
          <CardHeader class="pb-3">
            <CardTitle class="flex items-center gap-2 text-base">
              运行报告
              <Badge variant="secondary">{{ runResult.successCount }}/{{ runResult.totalCases }} 成功</Badge>
              <span class="ml-auto flex items-center gap-1 text-xs font-normal text-muted-foreground">
                <Clock class="h-3.5 w-3.5" /> 总耗时 {{ totalElapsed }}
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent class="space-y-2">
            <div v-for="r in runResult.results" :key="r.caseId" class="rounded-xl border p-3" :class="r.success ? 'border-border/60 bg-card' : 'border-red-500/30 bg-red-500/5'">
              <button class="flex w-full items-start gap-2 text-left" @click="toggleResult(r.caseId)">
                <CheckCircle2 v-if="r.success" class="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
                <XCircle v-else class="mt-0.5 h-4 w-4 shrink-0 text-red-400" />
                <div class="min-w-0 flex-1">
                  <p class="text-sm font-medium">{{ r.question }}</p>
                  <div class="mt-1 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                    <span class="flex items-center gap-1"><Clock class="h-3 w-3" /> {{ formatMs(r.elapsedMs) }}</span>
                    <span v-if="r.model" class="text-cyan-300">{{ r.model }}</span>
                    <span>{{ resultToken(r) }} tokens</span>
                    <span v-if="r.success">来源 {{ resultSourceCount(r) }}</span>
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
