<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowRight,
  Beaker,
  BookOpen,
  BrainCircuit,
  CheckCircle2,
  Clock,
  FlaskConical,
  Lightbulb,
  LoaderCircle,
  MessageCircle,
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

interface TestExample {
  id: string
  name: string
  description: string
  question: string
  useKnowledgeBase: boolean
}

// ── State ──────────────────────────────────────────────────────────

const toast = useToast()
const router = useRouter()

const testExamples: TestExample[] = [
  {
    id: 'greeting',
    name: '普通问候',
    description: '检查语气是否自然',
    question: '你好，请用两句话介绍你能帮我做什么。',
    useKnowledgeBase: false,
  },
  {
    id: 'structured',
    name: '结构化回答',
    description: '检查格式是否清晰',
    question: '请给我一份新员工入职准备清单，按“准备材料、第一天、第一周”分组。',
    useKnowledgeBase: false,
  },
  {
    id: 'knowledge',
    name: '知识库问答',
    description: '检查资料检索和引用',
    question: '请总结当前知识库的主要内容，列出 3 个有明确依据的要点并标注来源。',
    useKnowledgeBase: true,
  },
  {
    id: 'code-review',
    name: '代码检查',
    description: '检查问题和修改建议',
    question: `请检查下面代码是否有明显问题，并按“问题、原因、修改建议”输出：

public int divide(int a, int b) {
    return a / b;
}`,
    useKnowledgeBase: false,
  },
]

const legacyInputPlaceholderPattern = /\{\{\s*(question|query|input|code|requirement|document|content)\s*\}\}/gi

const templates = ref<PromptTemplate[]>([])
const knowledgeBases = ref<KnowledgeBase[]>([])
const selectedTemplateId = ref<number | null>(null)
const selectedKbId = ref<number | undefined>(undefined)
const question = ref(testExamples[0].question)
const testing = ref(false)
const result = ref<PromptTestResponse | null>(null)
const error = ref('')

// ── Computed ───────────────────────────────────────────────────────

const selectedTemplate = computed(() =>
  templates.value.find((t) => t.id === selectedTemplateId.value) || null,
)

const selectedKnowledgeBase = computed(() =>
  knowledgeBases.value.find((kb) => kb.id === selectedKbId.value) || null,
)

const hasLegacyInputPlaceholder = computed(() => {
  if (!selectedTemplate.value) return false
  legacyInputPlaceholderPattern.lastIndex = 0
  return legacyInputPlaceholderPattern.test(selectedTemplate.value.content)
})

const effectiveTemplateContent = computed(() => {
  const content = selectedTemplate.value?.content || ''
  legacyInputPlaceholderPattern.lastIndex = 0
  return content.replace(legacyInputPlaceholderPattern, '').replace(/\n{3,}/g, '\n\n').trim()
})

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

const testModeLabel = computed(() =>
  selectedKnowledgeBase.value ? `使用知识库：${selectedKnowledgeBase.value.name}` : '不使用知识库，只检查回答方式',
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

const applyExample = (example: TestExample) => {
  question.value = example.question
  result.value = null
  error.value = ''

  if (!example.useKnowledgeBase) {
    selectedKbId.value = undefined
    return
  }

  if (knowledgeBases.value.length === 0) {
    selectedKbId.value = undefined
    toast.warning('当前没有可用知识库。请先上传并解析文档，或先使用其他示例。')
    return
  }

  if (!selectedKbId.value) {
    selectedKbId.value = knowledgeBases.value[0].id
  }
}

const runTest = async () => {
  if (!canRun.value) return

  testing.value = true
  error.value = ''
  result.value = null

  try {
    const res = await post<ApiResponse<PromptTestResponse>>('/prompt-templates/test', {
      templateContent: effectiveTemplateContent.value || selectedTemplate.value!.content,
      question: question.value.trim(),
      knowledgeBaseId: selectedKbId.value,
    }, {
      // RAG 检索和首次加载本地模型可能超过公共请求的 30 秒限制。
      timeout: 120000,
    })
    result.value = res.data
  } catch (err) {
    const msg = err instanceof Error && /timeout of \d+ms exceeded/i.test(err.message)
      ? 'AI 生成时间较长，可能正在加载模型，请点击“重试”继续。'
      : err instanceof Error ? err.message : '测试请求失败，请稍后重试。'
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
      <div class="relative flex flex-col gap-5 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
        <div class="flex gap-4">
          <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-amber-400/25 bg-amber-400/10 text-amber-200">
            <FlaskConical class="h-5 w-5" />
          </div>
          <div>
            <p class="text-xs font-medium tracking-[0.16em] text-amber-200/90">快速验证</p>
            <h1 class="mt-1 text-2xl font-semibold tracking-tight">回答方案测试</h1>
            <p class="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">先选方案，再点一个示例问题。这里的测试只展示结果，不会影响正式对话。</p>
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
              <CardTitle class="text-base">开始测试</CardTitle>
              <CardDescription class="mt-1">按 1、2、3 填好后，点击查看回答效果。</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent class="space-y-5 p-5">
          <!-- Template selector -->
          <div class="space-y-2">
            <Label for="template-select">1. 选择回答方案</Label>
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
            <p class="text-xs leading-5 text-muted-foreground">草稿用于试效果，已发布方案用于确认正式版本。</p>
          </div>

          <!-- KB selector -->
          <div class="space-y-2">
            <Label for="kb-select">2. 是否使用知识库</Label>
            <select
              id="kb-select"
              v-model="selectedKbId"
              class="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            >
              <option :value="undefined">不使用知识库：只检查回答方式</option>
              <option v-for="kb in knowledgeBases" :key="kb.id" :value="kb.id">
                使用知识库：{{ kb.name }}{{ kb.documentCount ? `（${kb.documentCount} 份文档）` : '' }}
              </option>
            </select>
            <p class="text-xs leading-5 text-muted-foreground">要检查资料检索和来源引用时，选择一个已解析文档的知识库。</p>
            <div class="flex items-center gap-2 rounded-lg border border-primary/15 bg-primary/[0.04] px-3 py-2 text-xs text-muted-foreground">
              <BookOpen class="h-3.5 w-3.5 shrink-0 text-primary" />
              <span>{{ testModeLabel }}</span>
            </div>
          </div>

          <!-- Question input -->
          <div class="space-y-2">
            <div class="flex items-center justify-between">
              <Label for="test-question">3. 输入问题</Label>
              <span class="text-xs text-muted-foreground">{{ question.length }} / 4000</span>
            </div>
            <div class="flex items-center gap-2 text-xs text-muted-foreground">
              <Lightbulb class="h-3.5 w-3.5 text-amber-200" />
              <span>不知道写什么？点击下面的示例即可自动填入。</span>
            </div>
            <div class="grid gap-2 sm:grid-cols-2">
              <button
                v-for="example in testExamples"
                :key="example.id"
                type="button"
                class="rounded-lg border border-border bg-muted/20 px-3 py-2 text-left transition-colors hover:border-primary/35 hover:bg-primary/[0.05]"
                :class="example.useKnowledgeBase && !knowledgeBases.length ? 'opacity-60' : ''"
                :disabled="testing"
                @click="applyExample(example)"
              >
                <span class="block text-xs font-medium text-foreground">{{ example.name }}</span>
                <span class="mt-0.5 block text-[11px] text-muted-foreground">{{ example.description }}</span>
              </button>
            </div>
            <textarea
              id="test-question"
              v-model="question"
              :disabled="testing"
              rows="5"
              maxlength="4000"
              class="block w-full resize-y rounded-xl border border-input bg-background/60 px-3.5 py-3 text-sm leading-6 outline-none placeholder:text-muted-foreground focus:border-primary/50 focus:ring-2 focus:ring-primary/20"
              placeholder="输入你真实想测试的问题，例如：你好，请介绍你能帮我做什么。"
              @keydown.ctrl.enter="runTest"
            />
          </div>

          <!-- Action buttons -->
          <div class="flex gap-2">
            <Button class="gap-2 flex-1" :disabled="!canRun" @click="runTest">
              <LoaderCircle v-if="testing" class="h-4 w-4 animate-spin" />
              <Play v-else class="h-4 w-4" />
              {{ testing ? '正在生成回答…' : '查看回答效果' }}
            </Button>
            <Button v-if="result || error" variant="outline" class="gap-2" @click="reset">
              <RotateCcw class="h-4 w-4" />
              重置
            </Button>
          </div>
          <p class="text-center text-xs text-muted-foreground">也可以按 Ctrl + Enter 快速测试</p>

          <!-- Template preview -->
          <template v-if="selectedTemplate">
            <Separator />
            <details class="group rounded-lg border border-border bg-muted/20">
              <summary class="flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-2.5 text-xs font-medium">
                <span>查看这套方案的回答规则</span>
                <Badge variant="outline" :class="selectedTemplate.status === 'PUBLISHED' ? 'border-emerald-400/25 bg-emerald-400/10 text-emerald-300' : 'border-violet-400/25 bg-violet-400/10 text-violet-200'">
                  {{ selectedTemplate.status === 'PUBLISHED' ? '已发布' : '草稿' }}
                </Badge>
              </summary>
              <div class="space-y-2 border-t border-border p-3">
                <pre class="max-h-40 overflow-y-auto whitespace-pre-wrap rounded-lg border border-border bg-background/40 p-3 font-mono text-xs leading-relaxed text-foreground/85">{{ effectiveTemplateContent }}</pre>
                <p v-if="selectedTemplate.description" class="text-xs text-muted-foreground">用途：{{ selectedTemplate.description }}</p>
                <p v-if="hasLegacyInputPlaceholder" class="text-xs leading-5 text-amber-200/80">已自动忽略旧版输入占位符，测试问题会直接作为用户问题发送，不需要填写 &#123;&#123;code&#125;&#125; 这类内容。</p>
              </div>
            </details>
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
          <h2 class="mt-5 text-lg font-semibold">可以开始了</h2>
          <p class="mt-2 max-w-md text-sm leading-6 text-muted-foreground">左侧已经准备好示例问题。选一个、点击“查看回答效果”，就能看到这套方案实际会怎么回答。</p>
          <div class="mt-6 grid gap-3 text-left">
            <div class="flex items-start gap-2 rounded-lg border border-border bg-muted/30 p-3 text-xs text-muted-foreground">
              <MessageCircle class="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
              <span><strong>普通问候</strong>不选知识库，用来检查语气是否自然。</span>
            </div>
            <div class="flex items-start gap-2 rounded-lg border border-border bg-muted/30 p-3 text-xs text-muted-foreground">
              <BookOpen class="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
              <span><strong>知识库问答</strong>选择知识库，用来检查资料是否被检索并引用。</span>
            </div>
            <div class="flex items-start gap-2 rounded-lg border border-border bg-muted/30 p-3 text-xs text-muted-foreground">
              <CheckCircle2 class="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
              <span><strong>满意后发布</strong>确认回答符合预期，再回到回答方案页面发布。</span>
            </div>
          </div>
        </div>

        <!-- Loading state -->
        <div v-else-if="testing" class="flex min-h-[32rem] flex-col items-center justify-center px-6 text-center">
          <LoaderCircle class="h-8 w-8 animate-spin text-primary" />
          <p class="mt-4 font-medium">正在调用 AI 服务…</p>
          <p class="mt-1 max-w-md text-sm leading-6 text-muted-foreground">正在检索资料并生成回答；首次测试可能需要先加载模型，通常需要 10～60 秒，请不要重复点击。</p>
        </div>

        <!-- Results -->
        <template v-else-if="result">
          <CardHeader class="border-b border-border/70 p-5 sm:p-6">
            <div class="flex items-center gap-2">
              <BrainCircuit class="h-4 w-4 text-primary" />
              <div>
                <CardTitle class="text-base">回答效果</CardTitle>
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
                  生成用时
                </p>
                <p class="mt-2 text-xl font-semibold tabular-nums text-amber-200">{{ elapsedSeconds }}</p>
                <p class="mt-1 text-xs text-muted-foreground">从发送问题到返回结果</p>
              </div>
              <div class="rounded-xl border border-cyan-400/15 bg-cyan-400/[0.04] p-4">
                <p class="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <BrainCircuit class="h-3.5 w-3.5" />
                  使用模型
                </p>
                <p class="mt-2 text-lg font-semibold tabular-nums text-cyan-200">{{ result.model || '—' }}</p>
                <p class="mt-1 text-xs text-muted-foreground">本次测试使用的 AI</p>
              </div>
              <div class="rounded-xl border border-emerald-400/15 bg-emerald-400/[0.04] p-4">
                <p class="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Zap class="h-3.5 w-3.5" />
                  用量参考
                </p>
                <p class="mt-2 text-xl font-semibold tabular-nums text-emerald-200">
                  {{ totalTokens ? formatNumber(totalTokens) : '—' }}
                </p>
                <p v-if="promptTokens !== null && completionTokens !== null" class="mt-1 text-xs text-muted-foreground">
                  输入 {{ formatNumber(promptTokens) }} · 输出 {{ formatNumber(completionTokens) }}
                </p>
                <p v-else class="mt-1 text-xs text-muted-foreground">仅供调试参考</p>
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

            <div class="flex flex-col gap-3 rounded-xl border border-primary/15 bg-primary/[0.04] p-4 sm:flex-row sm:items-center sm:justify-between">
              <div class="flex items-start gap-2.5">
                <CheckCircle2 class="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                <div>
                  <p class="text-sm font-medium">觉得回答符合预期？</p>
                  <p class="mt-1 text-xs leading-5 text-muted-foreground">回到回答方案页面发布后，新建对话才会正式使用它。</p>
                </div>
              </div>
              <Button variant="outline" size="sm" class="gap-1.5 shrink-0" @click="router.push('/builder/prompts')">
                去发布方案
                <ArrowRight class="h-3.5 w-3.5" />
              </Button>
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
