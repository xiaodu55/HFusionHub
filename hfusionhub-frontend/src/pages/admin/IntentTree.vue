<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  BookOpen,
  Bot,
  ChevronDown,
  GitBranch,
  Layers3,
  Plus,
  RefreshCw,
  Save,
  Search,
  Sparkles,
  Trash2,
} from 'lucide-vue-next'
import * as intentApi from '@/api/intentTree'
import { getMyKnowledgeBaseList } from '@/api/knowledgeBase'
import LoadingSkeleton from '@/components/LoadingSkeleton.vue'
import type {
  KnowledgeBase,
  RagIntentKind,
  RagIntentLevel,
  RagIntentNode,
  RagIntentNodeCreateDTO,
} from '@/api/types'

interface FlatNode extends RagIntentNode {
  depth: number
  pathLabel: string
}

const tree = ref<RagIntentNode[]>([])
const knowledgeBases = ref<KnowledgeBase[]>([])
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const keyword = ref('')
const editingId = ref<number | null>(null)
const advancedOpen = ref(false)

const form = reactive<RagIntentNodeCreateDTO>({
  parentId: null,
  intentCode: '',
  name: '',
  description: '',
  level: 'DOMAIN',
  kind: 'SYSTEM',
  knowledgeBaseId: null,
  mcpToolId: null,
  topK: 5,
  routeConfig: '',
  enabled: 1,
  sortOrder: 0,
})

const levelOptions: Array<{ value: RagIntentLevel; label: string; help: string }> = [
  { value: 'DOMAIN', label: '一级分组', help: '例如：售后服务' },
  { value: 'CATEGORY', label: '二级分类', help: '例如：退款与退货' },
  { value: 'TOPIC', label: '具体问题', help: '例如：退款多久到账' },
]

const kindOptions: Array<{ value: RagIntentKind; label: string; help: string }> = [
  { value: 'KB', label: '从知识库回答', help: '检索指定知识库后再回答' },
  { value: 'SYSTEM', label: '直接回答', help: '问候、闲聊或通用问题' },
  { value: 'MCP', label: '调用工具', help: '交给已接入的工具处理' },
]

const levelLabel = (level: RagIntentLevel) => levelOptions.find(item => item.value === level)?.label || level
const kindLabel = (kind: RagIntentKind) => kindOptions.find(item => item.value === kind)?.label || kind

const flatten = (nodes: RagIntentNode[], depth = 0, prefix = ''): FlatNode[] => {
  return nodes.flatMap((node) => {
    const pathLabel = prefix ? `${prefix} / ${node.name}` : node.name
    return [{ ...node, depth, pathLabel }, ...flatten(node.children || [], depth + 1, pathLabel)]
  })
}

const flatNodes = computed(() => flatten(tree.value))
const visibleNodes = computed(() => {
  const q = keyword.value.trim().toLowerCase()
  if (!q) return flatNodes.value
  return flatNodes.value.filter((node) =>
    [node.name, node.intentCode, node.description || '', node.knowledgeBaseName || '']
      .some((value) => value.toLowerCase().includes(q))
  )
})

const parentOptions = computed(() => {
  if (form.level === 'DOMAIN') return []
  const parentLevel = form.level === 'CATEGORY' ? 'DOMAIN' : 'CATEGORY'
  return flatNodes.value.filter((node) => node.level === parentLevel && node.id !== editingId.value)
})

const selectedNode = computed(() => flatNodes.value.find((node) => node.id === editingId.value))
const selectedKindHelp = computed(() => kindOptions.find(item => item.value === form.kind)?.help)

const resetForm = () => {
  editingId.value = null
  advancedOpen.value = false
  Object.assign(form, {
    parentId: null,
    intentCode: '',
    name: '',
    description: '',
    level: 'DOMAIN',
    kind: 'SYSTEM',
    knowledgeBaseId: null,
    mcpToolId: null,
    topK: 5,
    routeConfig: '',
    enabled: 1,
    sortOrder: 0,
  })
}

const useExample = (kind: RagIntentKind) => {
  resetForm()
  if (kind === 'KB') {
    Object.assign(form, {
      name: '产品使用问题',
      description: '例如：怎么创建知识库、文档为什么解析失败',
      kind: 'KB',
      level: 'DOMAIN',
      knowledgeBaseId: knowledgeBases.value[0]?.id ?? null,
    })
  } else if (kind === 'SYSTEM') {
    Object.assign(form, {
      name: '问候与闲聊',
      description: '例如：你好、谢谢、你是谁',
      kind: 'SYSTEM',
      level: 'DOMAIN',
    })
  } else {
    Object.assign(form, {
      name: '查询订单状态',
      description: '例如：帮我查一下订单 123123 到哪里了',
      kind: 'MCP',
      level: 'DOMAIN',
    })
  }
  document.getElementById('routing-form')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

const editNode = (node: RagIntentNode) => {
  editingId.value = node.id
  advancedOpen.value = false
  Object.assign(form, {
    parentId: node.parentId ?? null,
    intentCode: node.intentCode,
    name: node.name,
    description: node.description || '',
    level: node.level,
    kind: node.kind,
    knowledgeBaseId: node.knowledgeBaseId ?? null,
    mcpToolId: node.mcpToolId ?? null,
    topK: node.topK || 5,
    routeConfig: node.routeConfig || '',
    enabled: node.enabled,
    sortOrder: node.sortOrder || 0,
  })
}

const normalizePayload = (): RagIntentNodeCreateDTO => ({
  ...form,
  intentCode: form.intentCode.trim() || `route.${Date.now()}`,
  parentId: form.level === 'DOMAIN' ? null : form.parentId,
  knowledgeBaseId: form.kind === 'KB' ? form.knowledgeBaseId : null,
  mcpToolId: form.kind === 'MCP' ? form.mcpToolId : null,
  routeConfig: form.routeConfig?.trim() || undefined,
})

const loadTree = async () => {
  loading.value = true
  error.value = ''
  try {
    tree.value = (await intentApi.getIntentTree()).data || []
  } catch (err) {
    error.value = err instanceof Error ? err.message : '无法加载问题分流规则'
  } finally {
    loading.value = false
  }
}

const loadKnowledgeBases = async () => {
  try {
    knowledgeBases.value = (await getMyKnowledgeBaseList({ page: 1, pageSize: 100 })).data.records || []
  } catch {
    knowledgeBases.value = []
  }
}

const saveNode = async () => {
  error.value = ''
  if (!form.name.trim()) {
    error.value = '请填写用户问题类型'
    return
  }
  if (form.level !== 'DOMAIN' && !form.parentId) {
    error.value = '二级分类和具体问题需要选择上级规则'
    return
  }
  if (form.kind === 'KB' && !form.knowledgeBaseId) {
    error.value = '请选择用于回答的知识库'
    return
  }
  if (form.kind === 'MCP' && !form.mcpToolId) {
    error.value = '请选择或填写要调用的工具'
    return
  }

  saving.value = true
  try {
    const payload = normalizePayload()
    if (editingId.value) await intentApi.updateIntentNode(editingId.value, payload)
    else await intentApi.createIntentNode(payload)
    resetForm()
    await loadTree()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '保存失败，请稍后重试'
  } finally {
    saving.value = false
  }
}

const removeNode = async (node: RagIntentNode) => {
  if (!window.confirm(`确定删除“${node.name}”及其下级规则吗？`)) return
  error.value = ''
  try {
    await intentApi.deleteIntentNode(node.id)
    if (editingId.value === node.id) resetForm()
    await loadTree()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '删除失败，请稍后重试'
  }
}

onMounted(() => {
  void loadTree()
  void loadKnowledgeBases()
})
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-5 pb-8">
    <section class="rounded-xl border border-border bg-card/80 p-5 sm:p-6">
      <div class="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
        <div class="flex items-start gap-4">
          <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-primary/25 bg-primary/10 text-primary">
            <GitBranch class="h-5 w-5" />
          </div>
          <div>
            <p class="text-xs font-medium text-primary">问题分流</p>
            <h1 class="mt-1 text-2xl font-semibold">让不同问题使用正确的回答方式</h1>
            <p class="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
              例如，用户问“怎么退款”时检索售后知识库；用户说“你好”时直接回答；用户要求查订单时调用订单工具。
            </p>
          </div>
        </div>
        <button class="inline-flex items-center justify-center gap-2 rounded-lg border border-border px-3 py-2 text-sm hover:bg-muted" @click="loadTree">
          <RefreshCw class="h-4 w-4" :class="loading && 'animate-spin'" />刷新
        </button>
      </div>

      <div class="mt-5 grid gap-3 border-t border-border pt-5 sm:grid-cols-3">
        <button class="rounded-lg border border-border bg-background/60 p-3 text-left hover:border-primary/40 hover:bg-primary/[0.04]" @click="useExample('KB')">
          <BookOpen class="h-4 w-4 text-primary" />
          <p class="mt-2 text-sm font-medium">知识库问答示例</p>
          <p class="mt-1 text-xs leading-5 text-muted-foreground">“怎么创建知识库？” → 检索产品知识库</p>
        </button>
        <button class="rounded-lg border border-border bg-background/60 p-3 text-left hover:border-primary/40 hover:bg-primary/[0.04]" @click="useExample('SYSTEM')">
          <Bot class="h-4 w-4 text-cyan-400" />
          <p class="mt-2 text-sm font-medium">直接回答示例</p>
          <p class="mt-1 text-xs leading-5 text-muted-foreground">“你好” → 不检索知识库，直接问候</p>
        </button>
        <button class="rounded-lg border border-border bg-background/60 p-3 text-left hover:border-primary/40 hover:bg-primary/[0.04]" @click="useExample('MCP')">
          <Sparkles class="h-4 w-4 text-amber-400" />
          <p class="mt-2 text-sm font-medium">调用工具示例</p>
          <p class="mt-1 text-xs leading-5 text-muted-foreground">“查订单 123123” → 调用订单查询工具</p>
        </button>
      </div>
    </section>

    <p v-if="error" class="rounded-lg border border-rose-400/30 bg-rose-400/10 px-4 py-3 text-sm text-rose-300">{{ error }}</p>

    <div class="grid gap-5 xl:grid-cols-[minmax(0,1.15fr)_minmax(25rem,0.85fr)]">
      <section class="overflow-hidden rounded-xl border border-border bg-card/70">
        <div class="flex flex-col gap-3 border-b border-border p-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 class="font-semibold">已有分流规则</h2>
            <p class="mt-1 text-sm text-muted-foreground">共 {{ flatNodes.length }} 条，点击一条即可修改</p>
          </div>
          <label class="relative block sm:w-72">
            <Search class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input v-model="keyword" class="h-10 w-full rounded-lg border border-border bg-background pl-9 pr-3 text-sm outline-none focus:border-primary" placeholder="搜索问题或知识库" />
          </label>
        </div>

        <LoadingSkeleton v-if="loading" type="card" :count="3" />
        <div v-else-if="visibleNodes.length === 0" class="flex min-h-72 flex-col items-center justify-center px-6 py-12 text-center">
          <GitBranch class="h-9 w-9 text-muted-foreground/45" />
          <h3 class="mt-4 font-medium">还没有问题分流规则</h3>
          <p class="mt-2 max-w-md text-sm leading-6 text-muted-foreground">先点击上方任意示例，再选择知识库并保存。没有规则时，系统仍会按默认方式回答。</p>
          <button class="mt-5 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground" @click="useExample('KB')">创建第一条规则</button>
        </div>
        <div v-else class="divide-y divide-border/70">
          <article v-for="node in visibleNodes" :key="node.id" class="flex items-center gap-3 p-4 hover:bg-muted/25" :class="editingId === node.id && 'bg-primary/[0.05]'">
            <button class="min-w-0 flex-1 text-left" @click="editNode(node)">
              <div class="flex min-w-0 items-center gap-2" :style="{ paddingLeft: `${node.depth * 1.1}rem` }">
                <Layers3 v-if="node.level !== 'TOPIC'" class="h-4 w-4 shrink-0 text-primary" />
                <Bot v-else class="h-4 w-4 shrink-0 text-cyan-400" />
                <h3 class="truncate text-sm font-semibold">{{ node.name }}</h3>
                <span class="rounded border border-border px-1.5 py-0.5 text-[10px] text-muted-foreground">{{ levelLabel(node.level) }}</span>
                <span v-if="node.enabled === 0" class="rounded border border-amber-400/25 bg-amber-400/10 px-1.5 py-0.5 text-[10px] text-amber-300">已停用</span>
              </div>
              <p class="mt-1 truncate text-xs text-muted-foreground" :style="{ paddingLeft: `${node.depth * 1.1 + 1.5}rem` }">
                {{ kindLabel(node.kind) }}<span v-if="node.knowledgeBaseName"> · {{ node.knowledgeBaseName }}</span><span v-if="node.description"> · {{ node.description }}</span>
              </p>
            </button>
            <button class="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-muted-foreground hover:bg-rose-400/10 hover:text-rose-300" title="删除规则" @click="removeNode(node)">
              <Trash2 class="h-4 w-4" />
            </button>
          </article>
        </div>
      </section>

      <aside id="routing-form" class="self-start overflow-hidden rounded-xl border border-border bg-card/70">
        <div class="border-b border-border p-4">
          <h2 class="font-semibold">{{ editingId ? '修改分流规则' : '新建分流规则' }}</h2>
          <p class="mt-1 text-sm text-muted-foreground">{{ selectedNode?.pathLabel || '填写用户会问什么，以及系统应该怎么回答' }}</p>
        </div>

        <form class="space-y-4 p-4" @submit.prevent="saveNode">
          <label class="block space-y-1.5 text-sm">
            <span class="font-medium">1. 用户会问哪类问题？</span>
            <input v-model.trim="form.name" class="h-10 w-full rounded-lg border border-border bg-background px-3 outline-none focus:border-primary" placeholder="例如：退款问题" />
          </label>

          <label class="block space-y-1.5 text-sm">
            <span class="font-medium">2. 写几个用户可能的问法</span>
            <textarea v-model="form.description" rows="3" class="w-full resize-none rounded-lg border border-border bg-background px-3 py-2 outline-none focus:border-primary" placeholder="例如：怎么退款、退款多久到账、订单能退吗" />
          </label>

          <label class="block space-y-1.5 text-sm">
            <span class="font-medium">3. 系统应该怎么回答？</span>
            <select v-model="form.kind" class="h-10 w-full rounded-lg border border-border bg-background px-3 outline-none focus:border-primary">
              <option v-for="item in kindOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
            </select>
            <span class="text-xs text-muted-foreground">{{ selectedKindHelp }}</span>
          </label>

          <label v-if="form.kind === 'KB'" class="block space-y-1.5 text-sm">
            <span class="font-medium">选择回答使用的知识库</span>
            <select v-model.number="form.knowledgeBaseId" class="h-10 w-full rounded-lg border border-border bg-background px-3 outline-none focus:border-primary">
              <option :value="null">请选择知识库</option>
              <option v-for="kb in knowledgeBases" :key="kb.id" :value="kb.id">{{ kb.name }}</option>
            </select>
            <span v-if="knowledgeBases.length === 0" class="text-xs text-amber-300">暂无知识库，请先在“知识库”页面创建并上传资料。</span>
          </label>

          <label v-if="form.kind === 'MCP'" class="block space-y-1.5 text-sm">
            <span class="font-medium">工具 ID</span>
            <input v-model.number="form.mcpToolId" type="number" min="1" class="h-10 w-full rounded-lg border border-border bg-background px-3 outline-none focus:border-primary" placeholder="例如：1" />
            <span class="text-xs text-muted-foreground">工具需先在“AI 能力”中创建并启用。</span>
          </label>

          <button type="button" class="flex w-full items-center justify-between rounded-lg border border-border px-3 py-2.5 text-sm hover:bg-muted/40" @click="advancedOpen = !advancedOpen">
            <span>高级设置</span>
            <ChevronDown class="h-4 w-4 transition-transform" :class="advancedOpen && 'rotate-180'" />
          </button>

          <div v-if="advancedOpen" class="space-y-4 rounded-lg border border-border bg-background/45 p-3">
            <div class="grid gap-3 sm:grid-cols-2">
              <label class="space-y-1.5 text-sm">
                <span class="text-muted-foreground">规则层级</span>
                <select v-model="form.level" class="h-10 w-full rounded-lg border border-border bg-background px-3 outline-none focus:border-primary">
                  <option v-for="item in levelOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
                </select>
              </label>
              <label class="space-y-1.5 text-sm">
                <span class="text-muted-foreground">状态</span>
                <select v-model.number="form.enabled" class="h-10 w-full rounded-lg border border-border bg-background px-3 outline-none focus:border-primary">
                  <option :value="1">启用</option>
                  <option :value="0">停用</option>
                </select>
              </label>
            </div>

            <p class="text-xs text-muted-foreground">{{ levelOptions.find(item => item.value === form.level)?.help }}</p>

            <label v-if="form.level !== 'DOMAIN'" class="block space-y-1.5 text-sm">
              <span class="text-muted-foreground">上级规则</span>
              <select v-model.number="form.parentId" class="h-10 w-full rounded-lg border border-border bg-background px-3 outline-none focus:border-primary">
                <option :value="null">请选择上级规则</option>
                <option v-for="node in parentOptions" :key="node.id" :value="node.id">{{ node.pathLabel }}</option>
              </select>
            </label>

            <div class="grid gap-3 sm:grid-cols-2">
              <label class="space-y-1.5 text-sm">
                <span class="text-muted-foreground">检索结果数量</span>
                <input v-model.number="form.topK" type="number" min="1" max="20" class="h-10 w-full rounded-lg border border-border bg-background px-3 outline-none focus:border-primary" />
              </label>
              <label class="space-y-1.5 text-sm">
                <span class="text-muted-foreground">排序优先级</span>
                <input v-model.number="form.sortOrder" type="number" class="h-10 w-full rounded-lg border border-border bg-background px-3 outline-none focus:border-primary" />
              </label>
            </div>

            <label class="block space-y-1.5 text-sm">
              <span class="text-muted-foreground">内部编码（留空自动生成）</span>
              <input v-model.trim="form.intentCode" class="h-10 w-full rounded-lg border border-border bg-background px-3 font-mono text-xs outline-none focus:border-primary" placeholder="留空即可" />
            </label>

            <label class="block space-y-1.5 text-sm">
              <span class="text-muted-foreground">高级参数 JSON（一般不用填写）</span>
              <textarea v-model="form.routeConfig" rows="3" class="w-full resize-none rounded-lg border border-border bg-background px-3 py-2 font-mono text-xs outline-none focus:border-primary" placeholder='例如：{"rerank": true}' />
            </label>
          </div>

          <div class="flex flex-col gap-2 sm:flex-row">
            <button type="submit" class="inline-flex flex-1 items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60" :disabled="saving">
              <Save class="h-4 w-4" />{{ saving ? '保存中...' : editingId ? '保存修改' : '创建规则' }}
            </button>
            <button type="button" class="inline-flex items-center justify-center gap-2 rounded-lg border border-border px-4 py-2.5 text-sm hover:bg-muted" @click="resetForm">
              <Plus class="h-4 w-4" />新建
            </button>
          </div>
        </form>
      </aside>
    </div>
  </div>
</template>
