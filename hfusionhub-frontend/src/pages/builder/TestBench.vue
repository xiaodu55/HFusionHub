<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  Beaker,
  BookOpen,
  BrainCircuit,
  ChevronDown,
  Clock,
  FileText,
  FlaskConical,
  LoaderCircle,
  Play,
  RotateCcw,
  Zap,
} from 'lucide-vue-next'
import * as promptTemplateApi from '@/api/promptTemplate'
import * as knowledgeBaseApi from '@/api/knowledgeBase'
import { post } from '@/api/request'
import type { PromptTemplate } from '@/api/promptTemplate'
import type { ApiResponse, KnowledgeBase } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { useToast } from '@/composables/useToast'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'

// ── Types ──────────────────────────────────────────────────────────

interface PromptTestResponse {
  content: string
  model: string
  tokenCount: number
  tokenUsage?: {
    prompt_tokens: number
    completion_tokens: number
    total_tokens: number
  }
  sources?: Array<{
    document_id?: number
    title?: string
    document_name?: string
    excerpt?: string
    content: string
    score: number
  }>
  elapsedMs: number
}

// ── State ──────────────────────────────────────────────────────────

const toast = useToast()

const templates = ref<PromptTemplate[]>([])
const knowledgeBases = ref<KnowledgeBase[]>([])
const selectedTemplateId = ref<number | null>(null)
const selectedKbId = ref<number | undefined>(undefined)
const question = ref('')
const testing = ref(false)
const result = ref<PromptTestResponse | null>(null)
const error = ref('')

// ── Computed ───────────────────────────────────────────────────────

const selectedTemplate = computed(() =>
  templates.value.find((t) => t.id === selectedTemplateId.value) || null,
)

const publishedTemplates = computed(() =>
  templates.value.filter((t) => t.status === 'PUBLISHED'),
)

const draftTemplates = computed(() =>
  templates.value.filter((t) => t.status === 'DRAFT'),
)

const totalTokens = computed(() => {
  if (!result.value) return null
  return result.value.tokenUsage?.total_tokens ?? result.value.tokenCount ?? null
})

const promptTokens = computed(() => {
  return result.value?.tokenUsage?.prompt_tokens ?? null
})

const completionTokens = computed(() => {
  return result.value?.tokenUsage?.completion_tokens ?? null
})

const elapsedSeconds = computed(() => {
  if (!result.value) return null
  const ms = result.value.elapsedMs
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`
  return `${ms}ms`
})

const canRun = computed(() =>
  selectedTemplate.value !== null && question.value.trim().length > 0 && !testing.value,
)

// ── Data loading ───────────────────────────────────────────────────

const loadTemplates = async () => {
  try {
    const res = await promptTemplateApi.listPromptTemplates()
    templates.value = res.data
    if (res.data.length > 0 && !selectedTemplateId.value) {
      selectedTemplateId.value = res.data[0].id
    }
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '加载模板列表失败')
  }
}

const loadKnowledgeBases = async () => {
  try {
    const res = await knowledgeBaseApi.getMyKnowledgeBaseList({ page: 1, pageSize: 100 })
    knowledgeBases.value = res.data.records.filter((kb) => kb.status === 0)
  } catch (err) {
    console.error('加载知识库失败:', err)
  }
}

// ── Actions ────────────────────────────────────────────────────────

const runTest = async () => {
  if (!canRun.value) return

  testing.value = true
  error.value = ''
  result.value = null

  try {
    const res = await post<ApiResponse<PromptTestResponse>>('/prompt-templates/test', {
      templateContent: selectedTemplate.value!.content,
      question: question.value.trim(),
      knowledgeBaseId: selectedKbId.value,
    })
    result.value = res.data
  } catch (err) {
    const msg = err instanceof Error ? err.message : '测试请求失败'
    error.value = msg
    toast.error(msg)
  } finally {
    testing.value = false
  }
}

const reset = () => {
  result.value = null
  error.value = ''
}

// ── Helpers ────────────────────────────────────────────────────────

const formatNumber = (n: number): string => {
  if (n >= 1000) return n.toLocaleString('zh-CN')
  return String(n)
}

const sourceScorePercent = (score: number): string => `${(score * 100).toFixed(0)}%`

onMounted(() => {
  loadTemplates()
  loadKnowledgeBases()
})
</script>

<template>
  <div class="space-y-6 pb-4">
    <!-- ── Hero banner ──────────────────────────────────────────── -->
    <section class="relative overflow-hidden rounded-2xl border border-border bg-card/80 shadow-[0_18px_45px_rgba(0,0,0,0.18)]">
      <div class="pointer-events-none absolute -right-12 -top-16 h-48 w-48 rounded-full bg-amber-400/10 blur-3xl" />
      <div class="relative flex flex-col gap-5 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
        <div class="flex gap-4">
          <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-amber-400/25 bg-amber-400/10 text-amber-200">
            <FlaskConical class="h-5 w-5" />
          </div>
          <div>
            <p class="text-xs font-medium tracking-[0.16em] text-amber-200/90">PROMPT TEST BENCH</p>
            <h1 class="mt-1 text-2xl font-semibold tracking-tight">回答方案测试</h1>
            <p class="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">选择回答方案，输入一个真实问题，检查 AI 的回答方式是否符合预期。测试不会创建对话记录。</p>
          </div>
        </div>
        <Badge variant="outline" class="border-amber-400/25 bg-amber-400/10 text-amber-200 shrink-0">
          {{ templates.length }} 个方案可测试
        </Badge>
      </div>
    </section>

    <!-- ── Main content: two columns ─────────────────────────────── -->
    <div class="grid items-start gap-6 xl:grid-cols-[minmax(19rem,0.85fr)_minmax(0,1.4fr)]">
      <!-- ── Left: Inputs ──────────────────────────────────────── -->
      <Card class="overflow-hidden border-border bg-card/80">
        <CardHeader class="border-b border-border/70 p-5">
          <div class="flex items-center gap-2">
            <Beaker class="h-4 w-4 text-primary" />
            <div>
              <CardTitle class="text-base">测试配置</CardTitle>
              <CardDescription class="mt-1">选择回答方案，可按需关联知识库。</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent class="space-y-5 p-5">
          <!-- Template selector -->
          <div class="space-y-2">
            <Label for="template-select">回答方案</Label>
            <select
              id="template-select"
              v-model="selectedTemplateId"
              class="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            >
              <option :value="null" disabled>请选择回答方案</option>
              <optgroup v-if="publishedTemplates.length" label="已发布">
                <option v-for="t in publishedTemplates" :key="t.id" :value="t.id">
                  {{ t.name }} (v{{ t.version }})
                </option>
              </optgroup>
              <optgroup v-if="draftTemplates.length" label="草稿">
                <option v-for="t in draftTemplates" :key="t.id" :value="t.id">
                  {{ t.name }} (v{{ t.version }})
                </option>
              </optgroup>
            </select>
            <p class="text-xs leading-5 text-muted-foreground">草稿和已发布方案都能测试。满意后回到“回答方案”页面点击发布。</p>
          </div>

          <!-- KB selector -->
          <div class="space-y-2">
            <Label for="kb-select">关联知识库（可选）</Label>
            <select
              id="kb-select"
              v-model="selectedKbId"
              class="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            >
              <option :value="undefined">不使用知识库（纯 LLM 测试）</option>
              <option v-for="kb in knowledgeBases" :key="kb.id" :value="kb.id">{{ kb.name }}</option>
            </select>
            <p class="text-xs leading-5 text-muted-foreground">选择知识库后，AI 会检索相关资料作为回答依据。</p>
          </div>

          <!-- Question input -->
          <div class="space-y-2">
            <div class="flex items-center justify-between">
              <Label for="test-question">测试问题</Label>
              <span class="text-xs text-muted-foreground">{{ question.length }} / 4000</span>
            </div>
            <textarea
              id="test-question"
              v-model="question"
              :disabled="testing"
              rows="5"
              maxlength="4000"
              class="block w-full resize-y rounded-xl border border-input bg-background/60 px-3.5 py-3 text-sm leading-6 outline-none placeholder:text-muted-foreground focus:border-primary/50 focus:ring-2 focus:ring-primary/20"
              placeholder="输入真实问题，例如：会员到期后还能导出数据吗？"
              @keydown.ctrl.enter="runTest"
            />
          </div>

          <!-- Action buttons -->
          <div class="flex gap-2">
            <Button class="gap-2 flex-1" :disabled="!canRun" @click="runTest">
              <LoaderCircle v-if="testing" class="h-4 w-4 animate-spin" />
              <Play v-else class="h-4 w-4" />
              {{ testing ? '测试中…' : '运行测试' }}
            </Button>
            <Button v-if="result || error" variant="outline" class="gap-2" @click="reset">
              <RotateCcw class="h-4 w-4" />
              重置
            </Button>
          </div>
          <p class="text-center text-xs text-muted-foreground">快捷键：Ctrl + Enter</p>

          <!-- Template preview -->
          <template v-if="selectedTemplate">
            <Separator />
            <div class="space-y-2">
              <div class="flex items-center justify-between">
                <Label class="text-xs">回答规则预览 — {{ selectedTemplate.name }}</Label>
                <Badge variant="outline" :class="selectedTemplate.status === 'PUBLISHED' ? 'border-emerald-400/25 bg-emerald-400/10 text-emerald-300' : 'border-violet-400/25 bg-violet-400/10 text-violet-200'">
                  {{ selectedTemplate.status === 'PUBLISHED' ? '已发布' : '草稿' }}
                </Badge>
              </div>
              <pre class="max-h-40 overflow-y-auto whitespace-pre-wrap rounded-lg border border-border bg-muted/30 p-3 font-mono text-xs leading-relaxed text-foreground/85">{{ selectedTemplate.content }}</pre>
              <p v-if="selectedTemplate.description" class="text-xs text-muted-foreground">{{ selectedTemplate.description }}</p>
            </div>
          </template>
        </CardContent>
      </Card>

      <!-- ── Right: Results ─────────────────────────────────────── -->
      <Card class="min-h-[32rem] overflow-hidden border-border bg-card/80">
        <!-- Error state -->
        <div v-if="error" class="flex min-h-[32rem] flex-col items-center justify-center px-6 text-center">
          <div class="flex h-14 w-14 items-center justify-center rounded-2xl border border-rose-400/25 bg-rose-400/10 text-rose-200">
            <Zap class="h-6 w-6" />
          </div>
          <h2 class="mt-5 text-lg font-semibold">测试请求失败</h2>
          <p class="mt-2 max-w-md text-sm leading-6 text-muted-foreground">{{ error }}</p>
          <Button variant="outline" class="mt-4 gap-2" @click="runTest">
            <RotateCcw class="h-4 w-4" />
            重试
          </Button>
        </div>

        <!-- Empty state -->
        <div v-else-if="!result && !testing" class="flex min-h-[32rem] flex-col items-center justify-center px-6 text-center">
          <div class="flex h-14 w-14 items-center justify-center rounded-2xl border border-amber-400/25 bg-amber-400/10 text-amber-200">
            <BrainCircuit class="h-6 w-6" />
          </div>
          <h2 class="mt-5 text-lg font-semibold">准备就绪</h2>
          <p class="mt-2 max-w-md text-sm leading-6 text-muted-foreground">选择一套回答方案并输入真实问题，点击“运行测试”查看回答效果、引用来源和耗时。</p>
          <div class="mt-6 grid gap-3 text-left">
            <div class="flex items-start gap-2 rounded-lg border border-border bg-muted/30 p-3 text-xs text-muted-foreground">
              <FileText class="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
              <span><strong>回答方案</strong>控制 AI 的语气、结构和回答边界。</span>
            </div>
            <div class="flex items-start gap-2 rounded-lg border border-border bg-muted/30 p-3 text-xs text-muted-foreground">
              <BookOpen class="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
              <span><strong>知识库</strong>可选关联，关联后 AI 会检索资料并附带来源引用。</span>
            </div>
            <div class="flex items-start gap-2 rounded-lg border border-border bg-muted/30 p-3 text-xs text-muted-foreground">
              <Clock class="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
              <span><strong>测试结果</strong>仅在当前页面展示，不会创建对话或保存消息记录。</span>
            </div>
          </div>
        </div>

        <!-- Loading state -->
        <div v-else-if="testing" class="flex min-h-[32rem] flex-col items-center justify-center px-6 text-center">
          <LoaderCircle class="h-8 w-8 animate-spin text-primary" />
          <p class="mt-4 font-medium">正在调用 AI 服务…</p>
          <p class="mt-1 text-sm text-muted-foreground">等待 AI 生成回答，请稍候。</p>
        </div>

        <!-- Results -->
        <template v-else-if="result">
          <CardHeader class="border-b border-border/70 p-5 sm:p-6">
            <div class="flex items-center gap-2">
              <BrainCircuit class="h-4 w-4 text-primary" />
              <div>
                <CardTitle class="text-base">测试结果</CardTitle>
                <CardDescription class="mt-1">{{ selectedTemplate?.name || '模板' }} · {{ question.slice(0, 60) }}{{ question.length > 60 ? '…' : '' }}</CardDescription>
              </div>
            </div>
          </CardHeader>

          <CardContent class="space-y-5 p-5 sm:p-6">
            <!-- Metrics bar -->
            <div class="grid gap-3 sm:grid-cols-3">
              <div class="rounded-xl border border-amber-400/15 bg-amber-400/[0.04] p-4">
                <p class="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Clock class="h-3.5 w-3.5" />
                  耗时
                </p>
                <p class="mt-2 text-xl font-semibold tabular-nums text-amber-200">{{ elapsedSeconds }}</p>
                <p class="mt-1 text-xs text-muted-foreground">服务端往返计时</p>
              </div>
              <div class="rounded-xl border border-cyan-400/15 bg-cyan-400/[0.04] p-4">
                <p class="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <BrainCircuit class="h-3.5 w-3.5" />
                  模型
                </p>
                <p class="mt-2 text-lg font-semibold tabular-nums text-cyan-200">{{ result.model || '—' }}</p>
                <p class="mt-1 text-xs text-muted-foreground">当前使用的 LLM</p>
              </div>
              <div class="rounded-xl border border-emerald-400/15 bg-emerald-400/[0.04] p-4">
                <p class="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Zap class="h-3.5 w-3.5" />
                  Token 消耗
                </p>
                <p class="mt-2 text-xl font-semibold tabular-nums text-emerald-200">
                  {{ totalTokens ? formatNumber(totalTokens) : '—' }}
                </p>
                <p v-if="promptTokens !== null && completionTokens !== null" class="mt-1 text-xs text-muted-foreground">
                  输入 {{ formatNumber(promptTokens) }} · 输出 {{ formatNumber(completionTokens) }}
                </p>
                <p v-else class="mt-1 text-xs text-muted-foreground">Token 用量统计</p>
              </div>
            </div>

            <Separator />

            <!-- AI answer -->
            <div class="space-y-2">
              <h3 class="text-sm font-semibold flex items-center gap-1.5">
                <BrainCircuit class="h-4 w-4 text-primary" />
                AI 回答
              </h3>
              <div class="rounded-xl border border-border bg-muted/20 p-4">
                <MarkdownRenderer v-if="result.content" :content="result.content" class="text-sm" />
                <p v-else class="text-sm text-muted-foreground italic">AI 未返回内容。</p>
              </div>
            </div>

            <!-- Sources -->
            <div v-if="result.sources && result.sources.length > 0" class="space-y-2">
              <Separator />
              <h3 class="text-sm font-semibold flex items-center gap-1.5">
                <BookOpen class="h-4 w-4 text-primary" />
                引用来源
                <span class="font-normal text-muted-foreground">({{ result.sources.length }} 条)</span>
              </h3>
              <div class="space-y-1.5">
                <div v-for="(source, index) in result.sources" :key="index"
                     class="rounded-lg bg-secondary-foreground/5 px-3 py-2">
                  <div class="flex items-center justify-between gap-2">
                    <span class="text-xs font-medium truncate flex-1" :title="source.document_name || source.title">
                      {{ source.document_name || source.title || `文档 #${source.document_id ?? '未知'}` }}
                    </span>
                    <span class="shrink-0 text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary">
                      {{ sourceScorePercent(source.score) }}
                    </span>
                  </div>
                  <p v-if="source.content" class="mt-1 text-[11px] opacity-60 line-clamp-2">
                    {{ source.content }}
                  </p>
                  <p v-else-if="source.excerpt" class="mt-1 text-[11px] opacity-60 line-clamp-2">
                    {{ source.excerpt }}
                  </p>
                </div>
              </div>
            </div>
          </CardContent>
        </template>
      </Card>
    </div>
  </div>
</template>
