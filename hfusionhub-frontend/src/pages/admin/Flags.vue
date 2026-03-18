<script setup lang="ts">
import { computed, ref, type Component } from 'vue'
import {
  Activity,
  Bot,
  Brain,
  CheckCircle2,
  CircleHelp,
  Cpu,
  FileText,
  GitBranch,
  Image,
  Lightbulb,
  Route,
  Settings2,
  ShieldCheck,
  Sparkles,
} from 'lucide-vue-next'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

type FeatureStatus = 'stable' | 'beta' | 'experimental'
type FeatureGroup = 'all' | FeatureStatus

interface FeatureFlag {
  key: string
  name: string
  status: FeatureStatus
  defaultEnabled: boolean
  summary: string
  outcome: string
  dependency: string
  howToEnable: string
  icon: Component
}

const activeGroup = ref<FeatureGroup>('all')
const groups: Array<{ value: FeatureGroup; label: string }> = [
  { value: 'all', label: '全部能力' },
  { value: 'stable', label: '稳定可用' },
  { value: 'beta', label: '测试中' },
  { value: 'experimental', label: '实验功能' },
]

const flags: FeatureFlag[] = [
  {
    key: 'RAG_HYBRID_ENABLED',
    name: '混合检索',
    status: 'stable',
    defaultEnabled: true,
    summary: '同时使用语义搜索和关键词搜索，提升知识库问答的召回率。',
    outcome: '更容易找到既“语义相近”又“关键词匹配”的资料。',
    dependency: '无需额外依赖。',
    howToEnable: 'RAG_HYBRID_ENABLED=true',
    icon: Route,
  },
  {
    key: 'RAG_GRAPH_ENABLED',
    name: '图谱检索',
    status: 'beta',
    defaultEnabled: false,
    summary: '从文档中的实体关系出发补充检索，适合关系复杂的业务知识。',
    outcome: '能关联人物、系统、规则等实体，但会增加索引和维护成本。',
    dependency: '需先完成文档索引，才能构建图谱。',
    howToEnable: 'RAG_GRAPH_ENABLED=true',
    icon: GitBranch,
  },
  {
    key: 'RAG_RERANKER_MODE',
    name: '结果重排',
    status: 'beta',
    defaultEnabled: false,
    summary: '在初步检索后再次排序，让最相关的片段排在前面。',
    outcome: '回答引用更精准，但会增加一次计算和少量等待时间。',
    dependency: 'lexical 无额外依赖；cross_encoder 需要重排模型依赖。',
    howToEnable: 'RAG_RERANKER_MODE=lexical 或 cross_encoder',
    icon: Activity,
  },
  {
    key: 'RAG_MULTIMODAL_ENABLED',
    name: '图片识别（OCR）',
    status: 'experimental',
    defaultEnabled: false,
    summary: '从文档图片中提取文字，让扫描件和图片内容也能被检索。',
    outcome: '能覆盖图片型资料，但处理时间会明显增加。',
    dependency: '需要安装 Tesseract OCR 与多模态依赖。',
    howToEnable: 'RAG_MULTIMODAL_ENABLED=true，并启用 OCR',
    icon: Image,
  },
  {
    key: 'RAG_AGENT_WORKFLOW_ENABLED',
    name: '受限 Agent 工作流',
    status: 'beta',
    defaultEnabled: false,
    summary: '为复杂任务增加超时、重试和执行追踪，提升运行可控性。',
    outcome: '复杂问题更可靠，但单次回答可能更慢。',
    dependency: '无需额外依赖。',
    howToEnable: 'RAG_AGENT_WORKFLOW_ENABLED=true',
    icon: Bot,
  },
  {
    key: 'RAG_MULTI_AGENT_ENABLED',
    name: '多 Agent 协作',
    status: 'experimental',
    defaultEnabled: false,
    summary: '让检索、分析、校验等多个角色协作处理复杂问题。',
    outcome: '适合高复杂度任务，但成本、等待时间和调试难度都会上升。',
    dependency: '需先启用受限 Agent 工作流，并明确选择知识库。',
    howToEnable: 'RAG_MULTI_AGENT_ENABLED=true',
    icon: Brain,
  },
]

const visibleFlags = computed(() => activeGroup.value === 'all'
  ? flags
  : flags.filter(flag => flag.status === activeGroup.value))
const countByStatus = (status: FeatureStatus) => flags.filter(flag => flag.status === status).length
const statusMeta = (status: FeatureStatus) => ({
  stable: { label: '稳定可用', class: 'border-emerald-400/25 bg-emerald-400/10 text-emerald-300' },
  beta: { label: '测试中', class: 'border-amber-400/25 bg-amber-400/10 text-amber-200' },
  experimental: { label: '实验功能', class: 'border-violet-400/25 bg-violet-400/10 text-violet-200' },
}[status])
</script>

<template>
  <div class="mx-auto max-w-6xl space-y-6 pb-4">
    <section class="relative overflow-hidden rounded-2xl border border-border bg-card/80 shadow-[0_18px_45px_rgba(0,0,0,0.18)]">
      <div class="pointer-events-none absolute -right-12 -top-16 h-48 w-48 rounded-full bg-primary/10 blur-3xl" />
      <div class="relative flex flex-col gap-5 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
        <div class="flex gap-4">
          <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-primary/25 bg-primary/10 text-primary"><Settings2 class="h-5 w-5" /></div>
          <div>
            <p class="text-xs font-medium tracking-[0.16em] text-primary/90">AI CAPABILITIES</p>
            <h1 class="mt-1 text-2xl font-semibold tracking-tight">高级能力与实验室</h1>
            <p class="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">这里说明 AI 能用哪些增强能力，以及它们会带来什么影响。日常使用保持默认即可；只有维护人员需要在部署配置中启用可选能力。</p>
          </div>
        </div>
        <div class="flex shrink-0 items-center gap-2 rounded-xl border border-border bg-background/40 px-3.5 py-2.5 text-sm text-muted-foreground"><ShieldCheck class="h-4 w-4 text-primary" /><span>配置文件驱动</span></div>
      </div>
    </section>

    <section class="grid gap-3 sm:grid-cols-3">
      <div class="rounded-xl border border-emerald-400/15 bg-emerald-400/[0.04] p-4"><p class="text-sm text-muted-foreground">稳定可用</p><p class="mt-2 text-2xl font-semibold text-emerald-200">{{ countByStatus('stable') }}</p><p class="mt-1 text-xs text-muted-foreground">推荐保持默认设置</p></div>
      <div class="rounded-xl border border-amber-400/15 bg-amber-400/[0.04] p-4"><p class="text-sm text-muted-foreground">测试中能力</p><p class="mt-2 text-2xl font-semibold text-amber-100">{{ countByStatus('beta') }}</p><p class="mt-1 text-xs text-muted-foreground">建议先在测试数据上验证</p></div>
      <div class="rounded-xl border border-violet-400/15 bg-violet-400/[0.04] p-4"><p class="text-sm text-muted-foreground">实验功能</p><p class="mt-2 text-2xl font-semibold text-violet-100">{{ countByStatus('experimental') }}</p><p class="mt-1 text-xs text-muted-foreground">可能增加成本或处理时长</p></div>
    </section>

    <div class="grid items-start gap-6 xl:grid-cols-[minmax(0,1.45fr)_minmax(18rem,0.65fr)]">
      <Card class="overflow-hidden border-border bg-card/80">
        <CardHeader class="border-b border-border/70 p-5">
          <div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between"><div><CardTitle class="text-base">能力目录</CardTitle><CardDescription class="mt-1">展示推荐默认值与启用前应了解的影响</CardDescription></div><div class="flex gap-1 overflow-x-auto rounded-lg bg-muted/45 p-1"><button v-for="group in groups" :key="group.value" class="shrink-0 rounded-md px-2.5 py-1.5 text-xs transition-colors" :class="activeGroup === group.value ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'" @click="activeGroup = group.value">{{ group.label }}</button></div></div>
        </CardHeader>
        <CardContent class="grid gap-3 p-4 sm:grid-cols-2">
          <article v-for="flag in visibleFlags" :key="flag.key" class="rounded-xl border border-border bg-muted/20 p-4 transition-colors hover:border-primary/25 hover:bg-muted/40">
            <div class="flex items-start justify-between gap-3"><div class="flex min-w-0 items-center gap-2.5"><div class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary"><component :is="flag.icon" class="h-4 w-4" /></div><h2 class="text-sm font-semibold">{{ flag.name }}</h2></div><Badge variant="outline" class="shrink-0" :class="statusMeta(flag.status).class">{{ statusMeta(flag.status).label }}</Badge></div>
            <p class="mt-4 text-sm leading-6 text-muted-foreground">{{ flag.summary }}</p>
            <div class="mt-4 rounded-lg border border-border/70 bg-background/35 p-3"><p class="text-xs text-muted-foreground">开启后</p><p class="mt-1 text-xs leading-5 text-foreground/85">{{ flag.outcome }}</p></div>
            <div class="mt-3 flex items-center justify-between gap-3"><span class="text-xs" :class="flag.defaultEnabled ? 'text-emerald-300' : 'text-muted-foreground'">{{ flag.defaultEnabled ? '推荐默认开启' : '默认不启用' }}</span><span class="font-mono text-[10px] text-muted-foreground">{{ flag.key }}</span></div>
            <details class="mt-3 border-t border-border/70 pt-3"><summary class="cursor-pointer text-xs text-primary hover:text-primary/80">查看前置条件与配置方式</summary><div class="mt-3 space-y-2 rounded-lg bg-muted/40 p-3 text-xs leading-5 text-muted-foreground"><p><strong class="font-medium text-foreground">前置条件：</strong>{{ flag.dependency }}</p><p><strong class="font-medium text-foreground">配置项：</strong><code class="ml-1 break-all rounded bg-background/70 px-1.5 py-0.5 text-foreground">{{ flag.howToEnable }}</code></p></div></details>
          </article>
        </CardContent>
      </Card>

      <aside class="space-y-4 xl:sticky xl:top-6">
        <Card class="border-primary/20 bg-primary/[0.055]"><CardHeader class="p-5 pb-3"><div class="flex items-center gap-2"><CircleHelp class="h-4 w-4 text-primary" /><CardTitle class="text-base">这个页面不是开关面板</CardTitle></div></CardHeader><CardContent class="space-y-3 p-5 pt-2 text-sm leading-6 text-muted-foreground"><p>它用于了解能力边界和部署要求；页面不会直接改动运行中的 AI 配置。</p><p>实际启用或关闭需要修改部署环境中的 Python AI 配置，然后重启 AI 服务使配置生效。</p></CardContent></Card>
        <Card class="border-border bg-card/80"><CardHeader class="p-5 pb-3"><div class="flex items-center gap-2"><Lightbulb class="h-4 w-4 text-amber-300" /><CardTitle class="text-base">什么时候需要调整？</CardTitle></div></CardHeader><CardContent class="space-y-3 p-5 pt-2 text-sm leading-6 text-muted-foreground"><div class="flex gap-2.5"><CheckCircle2 class="mt-1 h-4 w-4 shrink-0 text-emerald-300" /><p>一般知识库问答：保持默认混合检索即可。</p></div><div class="flex gap-2.5"><GitBranch class="mt-1 h-4 w-4 shrink-0 text-amber-300" /><p>关系型知识较多：可在测试后考虑图谱检索。</p></div><div class="flex gap-2.5"><FileText class="mt-1 h-4 w-4 shrink-0 text-violet-200" /><p>大量扫描件：验证 OCR 的质量与处理时长后再启用。</p></div><div class="flex gap-2.5"><Cpu class="mt-1 h-4 w-4 shrink-0 text-rose-200" /><p>复杂 Agent：先评估延迟和模型成本，再使用协作模式。</p></div></CardContent></Card>
        <div class="flex gap-3 rounded-xl border border-border bg-muted/20 p-4 text-sm leading-6 text-muted-foreground"><Sparkles class="mt-0.5 h-4 w-4 shrink-0 text-primary" /><p>推荐先通过“RAG 观测”的测试数据验证效果，再将可选能力用于真实业务。</p></div>
      </aside>
    </div>
  </div>
</template>
