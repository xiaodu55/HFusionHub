<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  Activity,
  BrainCircuit,
  CheckCircle2,
  CircleAlert,
  Cloud,
  Cpu,
  Database,
  Gauge,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
} from 'lucide-vue-next'
import * as systemApi from '@/api/system'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

const runtime = ref<systemApi.AiRuntimeOverview | null>(null)
const loading = ref(false)
const error = ref('')

const stateMeta = (state?: string) => {
  const states: Record<string, { label: string; class: string }> = {
    ready: { label: '已就绪', class: 'border-emerald-400/25 bg-emerald-400/10 text-emerald-300' },
    configured: { label: '已配置', class: 'border-cyan-400/25 bg-cyan-400/10 text-cyan-200' },
    reachable: { label: '服务可达', class: 'border-amber-400/25 bg-amber-400/10 text-amber-200' },
    development: { label: '仅开发环境', class: 'border-violet-400/25 bg-violet-400/10 text-violet-200' },
    unavailable: { label: '不可用', class: 'border-rose-400/25 bg-rose-400/10 text-rose-200' },
    not_configured: { label: '未配置', class: 'border-border bg-muted text-muted-foreground' },
  }
  return states[state || 'unavailable'] || states.unavailable
}

const overviewMeta = computed(() => {
  if (!runtime.value || runtime.value.status === 'unavailable') {
    return { label: '无法读取运行状态', class: 'border-rose-400/25 bg-rose-400/10 text-rose-200' }
  }
  if (runtime.value.status === 'ready') {
    return { label: '核心能力已就绪', class: 'border-emerald-400/25 bg-emerald-400/10 text-emerald-300' }
  }
  return { label: '部分能力需要处理', class: 'border-amber-400/25 bg-amber-400/10 text-amber-200' }
})

const featureItems = computed(() => {
  const features = runtime.value?.features
  if (!features) return []
  return [
    { name: '混合检索', detail: '向量与关键词结果融合', enabled: features.hybrid_retrieval },
    { name: '图谱检索', detail: '补充实体关系检索', enabled: features.graph_retrieval },
    { name: '结果重排', detail: features.reranker === 'disabled' ? '当前未启用重排' : `当前模式：${features.reranker}`, enabled: features.reranker !== 'disabled' },
    { name: '受限 Agent', detail: '超时、重试与执行边界', enabled: features.agent_workflow },
    { name: '多 Agent 校验', detail: '增加证据审阅环节', enabled: features.multi_agent },
  ]
})

const formatTime = (value?: string) => {
  if (!value) return '刚刚'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '刚刚'
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(date)
}

const loadRuntime = async () => {
  loading.value = true
  error.value = ''
  try {
    runtime.value = (await systemApi.getAiRuntimeOverview()).data
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : '暂时无法读取 AI 运行状态'
  } finally {
    loading.value = false
  }
}

onMounted(loadRuntime)
</script>

<template>
  <div class="space-y-6 pb-4">
    <section class="relative overflow-hidden rounded-2xl border border-border bg-card/80 shadow-[0_18px_45px_rgba(0,0,0,0.18)]">
      <div class="pointer-events-none absolute -right-12 -top-16 h-48 w-48 rounded-full bg-cyan-400/10 blur-3xl" />
      <div class="relative flex flex-col gap-5 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
        <div class="flex gap-4">
          <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-cyan-400/25 bg-cyan-400/10 text-cyan-200"><Cpu class="h-5 w-5" /></div>
          <div>
            <p class="text-xs font-medium tracking-[0.16em] text-cyan-200/90">MODEL CENTER</p>
            <h1 class="mt-1 text-2xl font-semibold tracking-tight">模型与运行状态</h1>
            <p class="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">查看当前对话模型、文档向量化和检索基础设施是否真的可用，不展示密钥或服务地址。</p>
          </div>
        </div>
        <div class="flex items-center gap-3">
          <Badge variant="outline" :class="overviewMeta.class">{{ overviewMeta.label }}</Badge>
          <Button variant="outline" :disabled="loading" class="gap-2" @click="loadRuntime"><LoaderCircle v-if="loading" class="h-4 w-4 animate-spin" /><RefreshCw v-else class="h-4 w-4" />刷新状态</Button>
        </div>
      </div>
    </section>

    <div v-if="error" class="flex items-start gap-3 rounded-xl border border-rose-400/20 bg-rose-400/[0.06] p-4 text-sm leading-6 text-rose-100/90"><CircleAlert class="mt-0.5 h-4 w-4 shrink-0" /><div><p class="font-medium">无法读取运行状态</p><p class="mt-1">{{ error }}</p></div></div>

    <template v-else-if="runtime">
      <section class="grid gap-3 lg:grid-cols-3">
        <article class="rounded-xl border border-border bg-card/70 p-4"><div class="flex items-center justify-between gap-3"><span class="text-sm text-muted-foreground">当前对话模型</span><Cloud class="h-4 w-4 text-cyan-200" /></div><p class="mt-3 truncate text-lg font-semibold">{{ runtime.llm?.model || '尚未就绪' }}</p><p class="mt-1 text-xs text-muted-foreground">{{ runtime.llm?.provider_label || '未配置模型提供方' }}</p></article>
        <article class="rounded-xl border border-border bg-card/70 p-4"><div class="flex items-center justify-between gap-3"><span class="text-sm text-muted-foreground">文档向量化</span><BrainCircuit class="h-4 w-4 text-violet-200" /></div><p class="mt-3 truncate text-lg font-semibold">{{ runtime.embedding?.model || '尚未就绪' }}</p><p class="mt-1 text-xs text-muted-foreground">{{ runtime.embedding?.dimension ? `${runtime.embedding.dimension} 维向量` : '无法处理新文档' }}</p></article>
        <article class="rounded-xl border border-border bg-card/70 p-4"><div class="flex items-center justify-between gap-3"><span class="text-sm text-muted-foreground">向量检索库</span><Database class="h-4 w-4 text-emerald-300" /></div><p class="mt-3 truncate text-lg font-semibold">{{ runtime.vector_store?.collection || '未检测到集合' }}</p><p class="mt-1 text-xs text-muted-foreground">{{ runtime.vector_store?.ready ? '已连接，可提供检索' : '当前不可用' }}</p></article>
      </section>

      <div v-if="runtime.embedding?.state === 'unavailable'" class="flex items-start gap-3 rounded-xl border border-amber-400/20 bg-amber-400/[0.06] p-4 text-sm leading-6 text-amber-100/90"><TriangleAlert class="mt-0.5 h-4 w-4 shrink-0" /><div><p class="font-medium">新文档暂时无法可靠建立索引</p><p class="mt-1">{{ runtime.embedding.detail }} 请部署一个兼容的本地 Embedding 模型后重新检查；仅有对话模型并不能完成知识库检索。</p></div></div>

      <div class="grid items-start gap-6 xl:grid-cols-[minmax(0,1.35fr)_minmax(20rem,0.72fr)]">
        <div class="space-y-6">
          <Card class="border-border bg-card/80">
            <CardHeader class="border-b border-border/70 p-5"><div class="flex items-center gap-2"><Gauge class="h-4 w-4 text-primary" /><div><CardTitle class="text-base">核心运行组件</CardTitle><CardDescription class="mt-1">状态由 AI 服务实时读取；“已配置”表示凭据已加载，不代表页面会显示或保存密钥。</CardDescription></div></div></CardHeader>
            <CardContent class="grid gap-3 p-4 sm:grid-cols-2">
              <article v-for="item in [runtime.llm, runtime.embedding]" :key="item?.provider_label" class="rounded-xl border border-border bg-muted/20 p-4"><div class="flex items-start justify-between gap-3"><div><p class="text-sm font-semibold">{{ item?.provider_label }}</p><p class="mt-1 font-mono text-xs text-muted-foreground">{{ item?.model || '—' }}</p></div><Badge variant="outline" :class="stateMeta(item?.state).class">{{ stateMeta(item?.state).label }}</Badge></div><p class="mt-4 text-sm leading-6 text-muted-foreground">{{ item?.detail }}</p><p v-if="item?.dimension" class="mt-3 text-xs text-muted-foreground">向量维度：{{ item.dimension }}</p></article>
              <article class="rounded-xl border border-border bg-muted/20 p-4"><div class="flex items-start justify-between gap-3"><div><p class="text-sm font-semibold">向量库</p><p class="mt-1 font-mono text-xs text-muted-foreground">{{ runtime.vector_store?.collection || '—' }}</p></div><Badge variant="outline" :class="runtime.vector_store?.ready ? stateMeta('ready').class : stateMeta('unavailable').class">{{ runtime.vector_store?.ready ? '已就绪' : '不可用' }}</Badge></div><p class="mt-4 text-sm leading-6 text-muted-foreground">{{ runtime.vector_store?.detail || '尚未返回向量库状态。' }}</p></article>
              <article class="rounded-xl border border-border bg-muted/20 p-4"><div class="flex items-start justify-between gap-3"><div><p class="text-sm font-semibold">应用到 AI 的链路</p><p class="mt-1 text-xs text-muted-foreground">Java 服务 → Python AI 服务</p></div><Badge variant="outline" :class="runtime.gateway_reachable ? stateMeta('ready').class : stateMeta('unavailable').class">{{ runtime.gateway_reachable ? '可达' : '不可达' }}</Badge></div><p class="mt-4 text-sm leading-6 text-muted-foreground">{{ runtime.detail || (runtime.gateway_reachable ? '运行状态已通过受保护的内部接口读取。' : '请检查 AI 服务是否已启动。') }}</p></article>
            </CardContent>
          </Card>

          <Card class="border-border bg-card/80"><CardHeader class="border-b border-border/70 p-5"><div class="flex items-center gap-2"><Activity class="h-4 w-4 text-primary" /><div><CardTitle class="text-base">当前启用的能力</CardTitle><CardDescription class="mt-1">这些状态来自部署配置；如需变更，请按发布流程修改服务环境并重启 AI 服务。</CardDescription></div></div></CardHeader><CardContent class="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-3"><article v-for="feature in featureItems" :key="feature.name" class="rounded-xl border border-border bg-muted/20 p-3.5"><div class="flex items-start justify-between gap-3"><span class="text-sm font-medium">{{ feature.name }}</span><CheckCircle2 v-if="feature.enabled" class="h-4 w-4 shrink-0 text-emerald-300" /><span v-else class="h-2 w-2 rounded-full bg-muted-foreground/50" /></div><p class="mt-2 text-xs leading-5 text-muted-foreground">{{ feature.detail }}</p></article></CardContent></Card>
        </div>

        <aside class="space-y-4 xl:sticky xl:top-6">
          <Card class="border-border bg-card/80"><CardHeader class="p-5 pb-3"><div class="flex items-center gap-2"><Sparkles class="h-4 w-4 text-cyan-200" /><CardTitle class="text-base">模型提供方</CardTitle></div><CardDescription>部署中已发现的提供方与模型。</CardDescription></CardHeader><CardContent class="space-y-2 p-5 pt-2"><article v-for="provider in runtime.providers || []" :key="provider.id" class="rounded-xl border border-border bg-muted/20 p-3"><div class="flex items-start justify-between gap-3"><div class="min-w-0"><p class="text-sm font-medium">{{ provider.label }}</p><p class="mt-1 truncate font-mono text-[11px] text-muted-foreground">{{ provider.model || provider.purpose }}</p></div><Badge variant="outline" :class="stateMeta(provider.state).class">{{ stateMeta(provider.state).label }}</Badge></div><p class="mt-2 text-xs text-muted-foreground">{{ provider.configured ? '已写入部署配置' : '使用默认发现策略' }}<template v-if="provider.reachable !== undefined"> · {{ provider.reachable ? '服务可达' : '服务未检测到' }}</template></p></article></CardContent></Card>
          <Card class="border-primary/20 bg-primary/[0.055]"><CardHeader class="p-5 pb-3"><div class="flex items-center gap-2"><ShieldCheck class="h-4 w-4 text-primary" /><CardTitle class="text-base">安全边界</CardTitle></div></CardHeader><CardContent class="space-y-3 p-5 pt-2 text-sm leading-6 text-muted-foreground"><p>此页只读取状态，不允许在浏览器中填写或修改 API Key。</p><p>模型、Embedding 和 Agent 开关由部署配置控制，变更后需要重启对应服务才能生效。</p></CardContent></Card>
          <p class="px-1 text-xs text-muted-foreground">最近检查：{{ formatTime(runtime.generated_at) }}</p>
        </aside>
      </div>
    </template>

    <div v-else class="flex min-h-72 items-center justify-center rounded-2xl border border-border bg-card/60"><LoaderCircle class="h-6 w-6 animate-spin text-primary" /></div>
  </div>
</template>
