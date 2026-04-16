<script setup lang="ts">
import { computed, onMounted, ref, watch, type Component } from 'vue'
import { useRouter } from 'vue-router'
import {
  AlertTriangle,
  BookOpen,
  Calculator,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  Clipboard,
  Clock3,
  ExternalLink,
  Globe2,
  History,
  Info,
  ListTree,
  LoaderCircle,
  MessageSquare,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  StickyNote,
  Wrench,
  XCircle,
} from 'lucide-vue-next'
import * as toolsApi from '@/api/tools'
import type { ToolEntry } from '@/api/tools'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useToast } from '@/composables/useToast'

type AbilityGroup = 'knowledge' | 'utility' | 'external'

interface AbilityPresentation {
  title: string
  description: string
  example: string
  group: AbilityGroup
  icon: Component
}

const router = useRouter()
const toast = useToast()
const registry = ref<toolsApi.ToolRegistryResponse | null>(null)
const calls = ref<toolsApi.ToolCallsResponse | null>(null)
const registryLoading = ref(false)
const callsLoading = ref(false)
const registryError = ref('')
const callsError = ref('')
const searchQuery = ref('')
const activeFilter = ref<'all' | AbilityGroup | 'approval'>('all')
const copiedTool = ref('')
const expandedTool = ref('')
const currentPage = ref(1)
const pageSize = 6

const abilityCatalog: Record<string, AbilityPresentation> = {
  search_knowledge_base: {
    title: '搜索知识库',
    description: '从已选知识库中查找与问题最相关的资料，并把来源带回回答。',
    example: '根据知识库说明什么是 Java 虚拟线程，并标注资料来源。',
    group: 'knowledge',
    icon: Search,
  },
  read_chunk: {
    title: '阅读资料原文',
    description: '当搜索摘要不够完整时，继续阅读命中的原文片段，补足回答依据。',
    example: '详细解释知识库中关于虚拟线程调度原理的原文内容。',
    group: 'knowledge',
    icon: BookOpen,
  },
  list_document_chunks: {
    title: '浏览文档结构',
    description: '查看一份文档包含哪些章节和内容片段，便于定位需要深入阅读的部分。',
    example: '列出《Java 虚拟线程》文档的主要章节和每章内容。',
    group: 'knowledge',
    icon: ListTree,
  },
  write_note: {
    title: '保存知识笔记',
    description: '把对话中的结论整理成笔记并写入知识库，真正保存前会请你确认。',
    example: '把刚才的结论整理成一条知识笔记并保存到知识库。',
    group: 'knowledge',
    icon: StickyNote,
  },
  calculate: {
    title: '数学计算',
    description: '完成明确的数学表达式计算，适合金额、比例和简单公式。',
    example: '计算 128 × 36 ÷ 12，并写出结果。',
    group: 'utility',
    icon: Calculator,
  },
  get_current_time: {
    title: '获取当前时间',
    description: '读取当前日期和时间，用于带时间条件的回答或任务。',
    example: '现在几点？今天是星期几？',
    group: 'utility',
    icon: Clock3,
  },
  web_search: {
    title: '联网查找资料',
    description: '从互联网获取知识库之外的最新信息，结果可能受外部服务和网络影响。',
    example: '联网查找 DeepSeek 最近一次官方模型更新，并附上来源。',
    group: 'external',
    icon: Globe2,
  },
}

const fallbackPresentation = (tool: ToolEntry): AbilityPresentation => ({
  title: tool.display_name || tool.name.replaceAll('_', ' '),
  description: tool.description || '由 AI 根据问题自动选择并使用的辅助能力。',
  example: tool.example || '在智能对话中直接描述你的目标，AI 会在需要时自动使用这项能力。',
  group: tool.category || (tool.risk_level === 'external' ? 'external' : 'utility'),
  icon: Wrench,
})

const presentationFor = (tool: ToolEntry) => abilityCatalog[tool.name] || fallbackPresentation(tool)

const filters = computed(() => [
  { key: 'all' as const, label: '全部能力', count: registry.value?.tools.length ?? 0 },
  {
    key: 'knowledge' as const,
    label: '知识库',
    count: registry.value?.tools.filter((tool) => presentationFor(tool).group === 'knowledge').length ?? 0,
  },
  {
    key: 'utility' as const,
    label: '日常工具',
    count: registry.value?.tools.filter((tool) => presentationFor(tool).group === 'utility').length ?? 0,
  },
  {
    key: 'external' as const,
    label: '联网能力',
    count: registry.value?.tools.filter((tool) => presentationFor(tool).group === 'external').length ?? 0,
  },
  {
    key: 'approval' as const,
    label: '需要确认',
    count: registry.value?.tools.filter((tool) => tool.risk_level === 'read_write' || tool.status === 'beta').length ?? 0,
  },
])

const visibleTools = computed(() => {
  const keyword = searchQuery.value.trim().toLowerCase()
  return (registry.value?.tools ?? []).filter((tool) => {
    const presentation = presentationFor(tool)
    const matchesFilter = activeFilter.value === 'all'
      || (activeFilter.value === 'approval'
        ? tool.risk_level === 'read_write' || tool.status === 'beta'
        : presentation.group === activeFilter.value)
    const matchesSearch = !keyword || [
      presentation.title,
      presentation.description,
      presentation.example,
      tool.name,
    ].some((value) => value.toLowerCase().includes(keyword))
    return matchesFilter && matchesSearch
  })
})

const totalPages = computed(() => Math.max(1, Math.ceil(visibleTools.value.length / pageSize)))
const paginatedTools = computed(() => {
  const start = (currentPage.value - 1) * pageSize
  return visibleTools.value.slice(start, start + pageSize)
})

watch([searchQuery, activeFilter], () => {
  currentPage.value = 1
  expandedTool.value = ''
})

const changePage = (page: number) => {
  currentPage.value = Math.min(Math.max(page, 1), totalPages.value)
  expandedTool.value = ''
  document.getElementById('ability-list')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

const toggleTool = (toolName: string) => {
  expandedTool.value = expandedTool.value === toolName ? '' : toolName
}

const readyCount = computed(() => registry.value?.tools.filter((tool) => tool.status === 'active').length ?? 0)
const approvalCount = computed(() => registry.value?.tools.filter((tool) => tool.risk_level === 'read_write' || tool.status === 'beta').length ?? 0)
const externalCount = computed(() => registry.value?.tools.filter((tool) => tool.risk_level === 'external').length ?? 0)

const abilityStatus = (tool: ToolEntry) => {
  if (tool.risk_level === 'read_write' || tool.status === 'beta') {
    return { label: '执行前需要确认', class: 'border-amber-400/30 bg-amber-400/10 text-amber-200' }
  }
  if (tool.status === 'experimental') {
    return { label: '试用能力', class: 'border-violet-400/30 bg-violet-400/10 text-violet-200' }
  }
  if (tool.risk_level === 'external') {
    return { label: '需要联网', class: 'border-sky-400/30 bg-sky-400/10 text-sky-200' }
  }
  return { label: '可自动使用', class: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200' }
}

const permissionLabel = (permission: string) => {
  const map: Record<string, string> = {
    'knowledge_base:read': '读取知识库',
    'knowledge_base:write': '写入知识库',
    'system:time': '读取系统时间',
    'external:http': '访问外部网络',
  }
  return map[permission] || permission
}

const loadRegistry = async () => {
  registryLoading.value = true
  registryError.value = ''
  try {
    const response = await toolsApi.getToolRegistry()
    registry.value = response.data
  } catch (error) {
    registryError.value = error instanceof Error ? error.message : '暂时无法读取 AI 能力列表'
  } finally {
    registryLoading.value = false
  }
}

const loadCalls = async () => {
  callsLoading.value = true
  callsError.value = ''
  try {
    const response = await toolsApi.getToolCalls(1, 30)
    calls.value = response.data
  } catch (error) {
    callsError.value = error instanceof Error ? error.message : '暂时无法读取使用记录'
  } finally {
    callsLoading.value = false
  }
}

const copyExample = async (tool: ToolEntry) => {
  const example = presentationFor(tool).example
  try {
    await navigator.clipboard.writeText(example)
    copiedTool.value = tool.name
    toast.success('示例问题已复制，可以到智能对话中直接使用')
    window.setTimeout(() => {
      if (copiedTool.value === tool.name) copiedTool.value = ''
    }, 1800)
  } catch {
    toast.error('复制失败，请手动选择示例文字')
  }
}

const openChat = () => router.push('/chat')
const openToolBuilder = () => router.push({ path: '/builder/plugins', query: { create: 'tool' } })

const formatMs = (milliseconds: number | null) => {
  if (milliseconds == null) return '未记录'
  if (milliseconds < 1000) return `${milliseconds} 毫秒`
  return `${(milliseconds / 1000).toFixed(2)} 秒`
}

const formatTime = (value?: string) => {
  if (!value) return '刚刚'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '刚刚'
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(date)
}

const taskStatusLabel = (status: string) => {
  const map: Record<string, string> = {
    succeeded: '已完成',
    failed: '已失败',
    running: '执行中',
    waiting_approval: '待确认',
    pending: '排队中',
    cancelled: '已取消',
    timed_out: '已超时',
  }
  return map[status] || status
}

onMounted(() => {
  loadRegistry()
  loadCalls()
})
</script>

<template>
  <div class="space-y-6 pb-6">
    <section class="rounded-lg border border-border bg-card/80 p-5 sm:p-6">
      <div class="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
        <div class="flex min-w-0 gap-4">
          <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-primary/25 bg-primary/10 text-primary">
            <Sparkles class="h-5 w-5" />
          </div>
          <div class="min-w-0">
            <p class="text-xs font-medium text-primary">AI 能力</p>
            <h1 class="mt-1 text-2xl font-semibold">AI 能帮你做什么</h1>
            <p class="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
              你不需要手动选择或运行工具，只要在智能对话中正常提问，AI 会按需搜索知识库、阅读原文、计算或联网查找资料。
            </p>
          </div>
        </div>
        <div class="flex shrink-0 flex-wrap items-center gap-2">
          <Button variant="outline" class="gap-2" @click="openToolBuilder">
            <Plus class="h-4 w-4" />
            新建工具
          </Button>
          <Button variant="outline" :disabled="registryLoading" class="gap-2" @click="loadRegistry">
            <LoaderCircle v-if="registryLoading" class="h-4 w-4 animate-spin" />
            <RefreshCw v-else class="h-4 w-4" />
            刷新状态
          </Button>
          <Button class="gap-2" @click="openChat">
            <MessageSquare class="h-4 w-4" />
            去智能对话
          </Button>
        </div>
      </div>

      <div class="mt-6 grid border-t border-border pt-5 sm:grid-cols-3">
        <div class="pb-4 sm:pb-0 sm:pr-5">
          <p class="text-xs text-muted-foreground">可直接使用</p>
          <p class="mt-1 text-xl font-semibold tabular-nums">{{ readyCount }}</p>
          <p class="mt-1 text-xs text-muted-foreground">AI 会根据问题自动调用</p>
        </div>
        <div class="border-t border-border py-4 sm:border-l sm:border-t-0 sm:px-5 sm:py-0">
          <p class="text-xs text-muted-foreground">需要你确认</p>
          <p class="mt-1 text-xl font-semibold tabular-nums">{{ approvalCount }}</p>
          <p class="mt-1 text-xs text-muted-foreground">涉及写入时先展示确认请求</p>
        </div>
        <div class="border-t border-border pt-4 sm:border-l sm:border-t-0 sm:pl-5 sm:pt-0">
          <p class="text-xs text-muted-foreground">联网能力</p>
          <p class="mt-1 text-xl font-semibold tabular-nums">{{ externalCount }}</p>
          <p class="mt-1 text-xs text-muted-foreground">需要外部服务和网络可用</p>
        </div>
      </div>
    </section>

    <section class="rounded-lg border border-border bg-card/55 p-5">
      <div class="flex items-center gap-2">
        <Info class="h-4 w-4 text-primary" />
        <h2 class="text-base font-semibold">怎么使用</h2>
      </div>
      <div class="mt-4 grid gap-3 md:grid-cols-3">
        <div class="flex gap-3 border-b border-border pb-3 md:border-b-0 md:border-r md:pb-0 md:pr-4">
          <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/12 text-xs font-semibold text-primary">1</span>
          <div>
            <p class="text-sm font-medium">打开智能对话</p>
            <p class="mt-1 text-xs leading-5 text-muted-foreground">知识库问题先选择对应知识库，普通问题可以直接提问。</p>
          </div>
        </div>
        <div class="flex gap-3 border-b border-border pb-3 md:border-b-0 md:border-r md:px-4 md:pb-0">
          <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/12 text-xs font-semibold text-primary">2</span>
          <div>
            <p class="text-sm font-medium">描述你要的结果</p>
            <p class="mt-1 text-xs leading-5 text-muted-foreground">例如“总结文档要点并标注来源”，无需输入工具名称。</p>
          </div>
        </div>
        <div class="flex gap-3 md:pl-4">
          <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/12 text-xs font-semibold text-primary">3</span>
          <div>
            <p class="text-sm font-medium">确认敏感操作</p>
            <p class="mt-1 text-xs leading-5 text-muted-foreground">读取和计算自动执行；写入知识库前由你确认。</p>
          </div>
        </div>
      </div>
    </section>

    <div v-if="registryError" class="flex items-start gap-3 rounded-lg border border-rose-400/20 bg-rose-400/[0.06] p-4 text-sm text-rose-100/90">
      <CircleAlert class="mt-0.5 h-4 w-4 shrink-0" />
      <div class="min-w-0">
        <p class="font-medium">AI 能力列表加载失败</p>
        <p class="mt-1 break-words text-rose-100/70">{{ registryError }}</p>
      </div>
    </div>

    <template v-if="registry">
      <section id="ability-list" class="scroll-mt-4">
        <div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h2 class="text-lg font-semibold">可用能力</h2>
            <p class="mt-1 text-sm text-muted-foreground">默认收起，点击一项查看用途和可直接使用的示例。</p>
          </div>
          <div class="relative w-full lg:w-80">
            <Search class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input v-model="searchQuery" class="pl-9" placeholder="搜索能力或使用场景" />
          </div>
        </div>

        <div class="mt-4 flex gap-2 overflow-x-auto pb-1" role="tablist" aria-label="能力分类">
          <button
            v-for="filter in filters"
            :key="filter.key"
            type="button"
            class="shrink-0 rounded-md border px-3 py-2 text-sm transition-colors"
            :class="activeFilter === filter.key
              ? 'border-primary/40 bg-primary/12 text-foreground'
              : 'border-border bg-card/40 text-muted-foreground hover:bg-muted/50 hover:text-foreground'"
            @click="activeFilter = filter.key"
          >
            {{ filter.label }}
            <span class="ml-1 text-xs opacity-70">{{ filter.count }}</span>
          </button>
        </div>

        <div v-if="visibleTools.length" class="mt-4 grid gap-3 lg:grid-cols-2">
          <article
            v-for="tool in paginatedTools"
            :key="tool.name"
            class="min-w-0 rounded-lg border bg-card/70 transition-colors"
            :class="expandedTool === tool.name ? 'border-primary/35' : 'border-border hover:border-primary/25'"
          >
            <button
              type="button"
              class="flex w-full items-center justify-between gap-3 p-4 text-left"
              :aria-expanded="expandedTool === tool.name"
              :aria-controls="`ability-${tool.name}`"
              @click="toggleTool(tool.name)"
            >
              <span class="flex min-w-0 items-center gap-3">
                <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-muted text-foreground">
                  <component :is="presentationFor(tool).icon" class="h-4 w-4" />
                </span>
                <span class="min-w-0">
                  <span class="block truncate text-sm font-semibold">{{ presentationFor(tool).title }}</span>
                  <span class="mt-1 block truncate text-xs text-muted-foreground">{{ presentationFor(tool).description }}</span>
                </span>
              </span>
              <span class="flex shrink-0 items-center gap-2">
                <span class="hidden rounded-full border px-2 py-1 text-[11px] sm:inline-flex" :class="abilityStatus(tool).class">
                  {{ abilityStatus(tool).label }}
                </span>
                <ChevronDown
                  class="h-4 w-4 text-muted-foreground transition-transform"
                  :class="expandedTool === tool.name ? 'rotate-180' : ''"
                />
              </span>
            </button>

            <div
              v-if="expandedTool === tool.name"
              :id="`ability-${tool.name}`"
              class="border-t border-border px-4 pb-4 pt-3"
            >
              <div class="flex items-center justify-between gap-3 sm:hidden">
                <span class="rounded-full border px-2 py-1 text-[11px]" :class="abilityStatus(tool).class">
                  {{ abilityStatus(tool).label }}
                </span>
                <span class="text-xs text-muted-foreground">
                  {{ presentationFor(tool).group === 'knowledge' ? '知识库能力' : presentationFor(tool).group === 'external' ? '外部信息' : '实用工具' }}
                </span>
              </div>

              <p class="mt-1 text-sm leading-6 text-muted-foreground">{{ presentationFor(tool).description }}</p>

              <div class="mt-3 rounded-md border border-border/80 bg-muted/25 p-3">
                <div class="flex items-center justify-between gap-3">
                  <span class="text-xs font-medium text-muted-foreground">示例问法</span>
                  <button
                    type="button"
                    class="inline-flex items-center gap-1 text-xs text-primary hover:text-primary/80"
                    :aria-label="`复制${presentationFor(tool).title}示例`"
                    @click="copyExample(tool)"
                  >
                    <Check v-if="copiedTool === tool.name" class="h-3.5 w-3.5" />
                    <Clipboard v-else class="h-3.5 w-3.5" />
                    {{ copiedTool === tool.name ? '已复制' : '复制示例' }}
                  </button>
                </div>
                <p class="mt-2 break-words text-sm leading-6 text-foreground/90">“{{ presentationFor(tool).example }}”</p>
              </div>

              <details class="group mt-3 border-t border-border/70 pt-3">
                <summary class="flex cursor-pointer list-none items-center justify-between text-xs text-muted-foreground hover:text-foreground">
                  <span>技术详情</span>
                  <ChevronDown class="h-4 w-4 transition-transform group-open:rotate-180" />
                </summary>
                <div class="mt-3 space-y-2 text-xs leading-5 text-muted-foreground">
                  <p><span class="text-foreground/70">内部名称：</span><code class="break-all">{{ tool.name }}</code></p>
                  <p><span class="text-foreground/70">最长等待：</span>{{ tool.timeout_seconds }} 秒</p>
                  <p>
                    <span class="text-foreground/70">所需权限：</span>
                    {{ tool.required_permissions.length ? tool.required_permissions.map(permissionLabel).join('、') : '无额外权限' }}
                  </p>
                  <div v-if="Object.keys(tool.input_schema.properties).length">
                    <p class="text-foreground/70">输入参数：</p>
                    <ul class="mt-1 space-y-1">
                      <li v-for="(property, key) in tool.input_schema.properties" :key="key" class="break-words">
                        <code>{{ key }}</code>：{{ property.description || property.type }}
                        <span v-if="tool.input_schema.required.includes(key as string)" class="text-amber-200">（必填）</span>
                      </li>
                    </ul>
                  </div>
                </div>
              </details>
            </div>
          </article>
        </div>

        <div v-if="visibleTools.length && totalPages > 1" class="mt-4 flex items-center justify-center gap-3">
          <button
            type="button"
            class="flex h-9 w-9 items-center justify-center rounded-md border border-border bg-card/60 text-muted-foreground disabled:cursor-not-allowed disabled:opacity-40"
            title="上一页"
            aria-label="上一页"
            :disabled="currentPage === 1"
            @click="changePage(currentPage - 1)"
          >
            <ChevronLeft class="h-4 w-4" />
          </button>
          <span class="min-w-20 text-center text-sm text-muted-foreground">第 {{ currentPage }} / {{ totalPages }} 页</span>
          <button
            type="button"
            class="flex h-9 w-9 items-center justify-center rounded-md border border-border bg-card/60 text-muted-foreground disabled:cursor-not-allowed disabled:opacity-40"
            title="下一页"
            aria-label="下一页"
            :disabled="currentPage === totalPages"
            @click="changePage(currentPage + 1)"
          >
            <ChevronRight class="h-4 w-4" />
          </button>
        </div>

        <div v-else class="mt-4 flex min-h-44 flex-col items-center justify-center rounded-lg border border-dashed border-border text-center">
          <Search class="h-6 w-6 text-muted-foreground/60" />
          <p class="mt-3 text-sm font-medium">没有找到匹配的能力</p>
          <button type="button" class="mt-2 text-xs text-primary" @click="searchQuery = ''; activeFilter = 'all'">清除筛选</button>
        </div>
      </section>

      <div v-if="registry.notice" class="flex items-start gap-3 rounded-lg border border-amber-400/20 bg-amber-400/[0.06] p-4 text-sm leading-6 text-amber-100/90">
        <AlertTriangle class="mt-1 h-4 w-4 shrink-0" />
        <p>{{ registry.notice }}</p>
      </div>
    </template>

    <div v-else-if="!registryError" class="flex min-h-64 items-center justify-center rounded-lg border border-border bg-card/40">
      <LoaderCircle class="h-6 w-6 animate-spin text-primary" />
    </div>

    <details class="group rounded-lg border border-border bg-card/55">
      <summary class="flex cursor-pointer list-none items-center justify-between gap-4 p-5">
        <div class="flex min-w-0 items-center gap-3">
          <History class="h-4 w-4 shrink-0 text-primary" />
          <div class="min-w-0">
            <h2 class="text-sm font-semibold">最近使用记录</h2>
            <p class="mt-1 truncate text-xs text-muted-foreground">用于确认 AI 是否调用成功，日常使用无需查看。</p>
          </div>
        </div>
        <ChevronDown class="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" />
      </summary>

      <div class="border-t border-border p-5">
        <div class="mb-4 flex justify-end">
          <Button variant="outline" size="sm" :disabled="callsLoading" class="gap-2" @click="loadCalls">
            <LoaderCircle v-if="callsLoading" class="h-4 w-4 animate-spin" />
            <RefreshCw v-else class="h-4 w-4" />
            刷新记录
          </Button>
        </div>

        <div v-if="callsLoading && !calls" class="flex min-h-32 items-center justify-center">
          <LoaderCircle class="h-5 w-5 animate-spin text-primary" />
        </div>
        <div v-else-if="callsError" class="flex items-start gap-3 rounded-md bg-rose-400/[0.06] p-4 text-sm text-rose-100/90">
          <CircleAlert class="mt-0.5 h-4 w-4 shrink-0" />
          <p class="break-words">{{ callsError }}</p>
        </div>
        <div v-else-if="!calls?.calls.length" class="flex min-h-32 flex-col items-center justify-center text-center">
          <History class="h-6 w-6 text-muted-foreground/50" />
          <p class="mt-3 text-sm font-medium">还没有使用记录</p>
          <p class="mt-1 text-xs text-muted-foreground">在 Agent 任务中使用能力后，结果会显示在这里。</p>
        </div>
        <div v-else class="overflow-x-auto">
          <table class="w-full min-w-[680px] text-sm">
            <thead>
              <tr class="border-b border-border text-left text-xs text-muted-foreground">
                <th class="px-3 py-3 font-medium">使用的能力</th>
                <th class="px-3 py-3 font-medium">任务内容</th>
                <th class="px-3 py-3 font-medium">耗时</th>
                <th class="px-3 py-3 font-medium">结果</th>
                <th class="px-3 py-3 font-medium">时间</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="call in calls.calls" :key="call.id" class="border-b border-border/60 last:border-0">
                <td class="px-3 py-3 font-medium">
                  {{ abilityCatalog[call.tool_name]?.title || call.tool_name.replaceAll('_', ' ') }}
                </td>
                <td class="max-w-sm px-3 py-3">
                  <p class="truncate">{{ call.task.query || '未记录任务内容' }}</p>
                  <p class="mt-1 text-xs text-muted-foreground">{{ taskStatusLabel(call.task.status) }} · 任务 #{{ call.task.id }}</p>
                </td>
                <td class="whitespace-nowrap px-3 py-3 text-xs text-muted-foreground">{{ formatMs(call.duration_ms) }}</td>
                <td class="px-3 py-3">
                  <span class="inline-flex items-center gap-1.5 text-xs">
                    <CheckCircle2 v-if="call.success" class="h-4 w-4 text-emerald-300" />
                    <XCircle v-else class="h-4 w-4 text-rose-300" />
                    {{ call.success ? '成功' : '失败' }}
                  </span>
                </td>
                <td class="whitespace-nowrap px-3 py-3 text-xs text-muted-foreground">{{ formatTime(call.created_at) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </details>

    <section class="flex flex-col gap-3 rounded-lg border border-primary/20 bg-primary/[0.045] p-5 sm:flex-row sm:items-center sm:justify-between">
      <div class="flex items-start gap-3">
        <ShieldCheck class="mt-0.5 h-5 w-5 shrink-0 text-primary" />
        <div>
          <h2 class="text-sm font-semibold">操作由你掌控</h2>
          <p class="mt-1 text-xs leading-5 text-muted-foreground">AI 可以自动读取和计算；写入知识库等会改变数据的操作，必须经过你的确认。</p>
        </div>
      </div>
      <Button variant="outline" class="shrink-0 gap-2" @click="openChat">
        立即体验
        <ExternalLink class="h-4 w-4" />
      </Button>
    </section>
  </div>
</template>
