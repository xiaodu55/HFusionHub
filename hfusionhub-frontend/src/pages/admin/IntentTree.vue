<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { Bot, GitBranch, Layers3, Plus, RefreshCw, Save, Search, Trash2 } from 'lucide-vue-next'
import * as intentApi from '@/api/intentTree'
import { getMyKnowledgeBaseList } from '@/api/knowledgeBase'
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

const levelOptions: Array<{ value: RagIntentLevel; label: string }> = [
  { value: 'DOMAIN', label: '领域' },
  { value: 'CATEGORY', label: '分类' },
  { value: 'TOPIC', label: '意图' },
]

const kindOptions: Array<{ value: RagIntentKind; label: string }> = [
  { value: 'SYSTEM', label: '系统' },
  { value: 'KB', label: '知识库' },
  { value: 'MCP', label: '工具' },
]

const flatten = (nodes: RagIntentNode[], depth = 0, prefix = ''): FlatNode[] => {
  return nodes.flatMap((node) => {
    const pathLabel = prefix ? `${prefix} / ${node.name}` : node.name
    return [
      { ...node, depth, pathLabel },
      ...flatten(node.children || [], depth + 1, pathLabel),
    ]
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

const resetForm = () => {
  editingId.value = null
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

const editNode = (node: RagIntentNode) => {
  editingId.value = node.id
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
    error.value = err instanceof Error ? err.message : '无法加载意图树'
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
  saving.value = true
  error.value = ''
  try {
    const payload = normalizePayload()
    if (editingId.value) {
      await intentApi.updateIntentNode(editingId.value, payload)
    } else {
      await intentApi.createIntentNode(payload)
    }
    resetForm()
    await loadTree()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '保存失败'
  } finally {
    saving.value = false
  }
}

const removeNode = async (node: RagIntentNode) => {
  if (!window.confirm(`删除「${node.name}」及其子节点？`)) return
  error.value = ''
  try {
    await intentApi.deleteIntentNode(node.id)
    if (editingId.value === node.id) resetForm()
    await loadTree()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '删除失败'
  }
}

onMounted(() => {
  void loadTree()
  void loadKnowledgeBases()
})
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-5 pb-6">
    <section class="rounded-xl border border-border bg-card/80 p-5">
      <div class="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div class="flex items-start gap-3">
          <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-primary/25 bg-primary/10 text-primary">
            <GitBranch class="h-5 w-5" />
          </div>
          <div>
            <p class="text-xs font-medium tracking-[0.16em] text-primary">RAG ROUTING</p>
            <h1 class="mt-1 text-2xl font-semibold">意图树</h1>
            <p class="mt-1 max-w-3xl text-sm leading-6 text-muted-foreground">
              用领域、分类、意图三层结构管理知识库路由。后续问答会基于这里的配置选择知识库、topK 和工具路径。
            </p>
          </div>
        </div>
        <button
          class="inline-flex items-center justify-center gap-2 rounded-lg border border-border px-3 py-2 text-sm text-muted-foreground hover:bg-muted"
          @click="loadTree"
        >
          <RefreshCw class="h-4 w-4" />
          刷新
        </button>
      </div>
    </section>

    <p v-if="error" class="rounded-lg border border-rose-400/30 bg-rose-400/10 px-4 py-3 text-sm text-rose-200">{{ error }}</p>

    <div class="grid gap-5 xl:grid-cols-[minmax(0,1.25fr)_minmax(25rem,0.75fr)]">
      <section class="rounded-xl border border-border bg-card/80">
        <div class="flex flex-col gap-3 border-b border-border p-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 class="text-base font-semibold">节点目录</h2>
            <p class="mt-1 text-sm text-muted-foreground">共 {{ flatNodes.length }} 个节点</p>
          </div>
          <label class="relative block md:w-80">
            <Search class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              v-model="keyword"
              class="h-10 w-full rounded-lg border border-border bg-background pl-9 pr-3 text-sm outline-none focus:border-primary"
              placeholder="搜索名称、编码、知识库"
            />
          </label>
        </div>

        <div v-if="loading" class="p-8 text-center text-sm text-muted-foreground">加载中...</div>
        <div v-else-if="visibleNodes.length === 0" class="p-8 text-center text-sm text-muted-foreground">
          暂无意图节点
        </div>
        <div v-else class="divide-y divide-border/70">
          <article
            v-for="node in visibleNodes"
            :key="node.id"
            class="flex flex-col gap-3 p-4 transition-colors hover:bg-muted/30 md:flex-row md:items-center md:justify-between"
            :class="editingId === node.id ? 'bg-primary/5' : ''"
          >
            <button class="min-w-0 text-left" @click="editNode(node)">
              <div class="flex min-w-0 items-center gap-2" :style="{ paddingLeft: `${node.depth * 1.25}rem` }">
                <Layers3 v-if="node.level !== 'TOPIC'" class="h-4 w-4 shrink-0 text-primary" />
                <Bot v-else class="h-4 w-4 shrink-0 text-cyan-300" />
                <h3 class="truncate text-sm font-semibold">{{ node.name }}</h3>
                <span class="rounded border border-border px-1.5 py-0.5 text-[10px] text-muted-foreground">{{ node.level }}</span>
                <span class="rounded border border-primary/20 bg-primary/10 px-1.5 py-0.5 text-[10px] text-primary">{{ node.kind }}</span>
                <span v-if="node.enabled === 0" class="rounded border border-amber-400/20 bg-amber-400/10 px-1.5 py-0.5 text-[10px] text-amber-200">停用</span>
              </div>
              <p class="mt-1 truncate text-xs text-muted-foreground" :style="{ paddingLeft: `${node.depth * 1.25 + 1.5}rem` }">
                {{ node.intentCode }}
                <span v-if="node.knowledgeBaseName"> · {{ node.knowledgeBaseName }}</span>
              </p>
            </button>
            <button
              class="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-muted-foreground hover:bg-rose-400/10 hover:text-rose-200"
              title="删除"
              @click="removeNode(node)"
            >
              <Trash2 class="h-4 w-4" />
            </button>
          </article>
        </div>
      </section>

      <aside class="rounded-xl border border-border bg-card/80">
        <div class="border-b border-border p-4">
          <h2 class="text-base font-semibold">{{ editingId ? '编辑节点' : '新建节点' }}</h2>
          <p class="mt-1 text-sm text-muted-foreground">
            {{ selectedNode?.pathLabel || '配置意图层级和路由目标' }}
          </p>
        </div>

        <form class="space-y-4 p-4" @submit.prevent="saveNode">
          <div class="grid gap-3 sm:grid-cols-2">
            <label class="space-y-1.5 text-sm">
              <span class="text-muted-foreground">层级</span>
              <select v-model="form.level" class="h-10 w-full rounded-lg border border-border bg-background px-3 outline-none focus:border-primary">
                <option v-for="item in levelOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
              </select>
            </label>
            <label class="space-y-1.5 text-sm">
              <span class="text-muted-foreground">类型</span>
              <select v-model="form.kind" class="h-10 w-full rounded-lg border border-border bg-background px-3 outline-none focus:border-primary">
                <option v-for="item in kindOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
              </select>
            </label>
          </div>

          <label v-if="form.level !== 'DOMAIN'" class="block space-y-1.5 text-sm">
            <span class="text-muted-foreground">父节点</span>
            <select v-model.number="form.parentId" class="h-10 w-full rounded-lg border border-border bg-background px-3 outline-none focus:border-primary">
              <option :value="null">请选择父节点</option>
              <option v-for="node in parentOptions" :key="node.id" :value="node.id">{{ node.pathLabel }}</option>
            </select>
          </label>

          <label class="block space-y-1.5 text-sm">
            <span class="text-muted-foreground">编码</span>
            <input v-model.trim="form.intentCode" required class="h-10 w-full rounded-lg border border-border bg-background px-3 outline-none focus:border-primary" placeholder="java.thread.virtual" />
          </label>

          <label class="block space-y-1.5 text-sm">
            <span class="text-muted-foreground">名称</span>
            <input v-model.trim="form.name" required class="h-10 w-full rounded-lg border border-border bg-background px-3 outline-none focus:border-primary" placeholder="Java 虚拟线程" />
          </label>

          <label class="block space-y-1.5 text-sm">
            <span class="text-muted-foreground">描述</span>
            <textarea v-model="form.description" rows="3" class="w-full resize-none rounded-lg border border-border bg-background px-3 py-2 outline-none focus:border-primary" placeholder="这个意图覆盖哪些用户问题" />
          </label>

          <label v-if="form.kind === 'KB'" class="block space-y-1.5 text-sm">
            <span class="text-muted-foreground">知识库</span>
            <select v-model.number="form.knowledgeBaseId" class="h-10 w-full rounded-lg border border-border bg-background px-3 outline-none focus:border-primary">
              <option :value="null">请选择知识库</option>
              <option v-for="kb in knowledgeBases" :key="kb.id" :value="kb.id">{{ kb.name }}</option>
            </select>
          </label>

          <label v-if="form.kind === 'MCP'" class="block space-y-1.5 text-sm">
            <span class="text-muted-foreground">MCP 工具 ID</span>
            <input v-model.number="form.mcpToolId" type="number" min="1" class="h-10 w-full rounded-lg border border-border bg-background px-3 outline-none focus:border-primary" />
          </label>

          <div class="grid gap-3 sm:grid-cols-3">
            <label class="space-y-1.5 text-sm">
              <span class="text-muted-foreground">topK</span>
              <input v-model.number="form.topK" type="number" min="1" max="20" class="h-10 w-full rounded-lg border border-border bg-background px-3 outline-none focus:border-primary" />
            </label>
            <label class="space-y-1.5 text-sm">
              <span class="text-muted-foreground">排序</span>
              <input v-model.number="form.sortOrder" type="number" class="h-10 w-full rounded-lg border border-border bg-background px-3 outline-none focus:border-primary" />
            </label>
            <label class="space-y-1.5 text-sm">
              <span class="text-muted-foreground">状态</span>
              <select v-model.number="form.enabled" class="h-10 w-full rounded-lg border border-border bg-background px-3 outline-none focus:border-primary">
                <option :value="1">启用</option>
                <option :value="0">停用</option>
              </select>
            </label>
          </div>

          <label class="block space-y-1.5 text-sm">
            <span class="text-muted-foreground">高级路由 JSON</span>
            <textarea v-model="form.routeConfig" rows="3" class="w-full resize-none rounded-lg border border-border bg-background px-3 py-2 font-mono text-xs outline-none focus:border-primary" placeholder='{"rerank": true}' />
          </label>

          <div class="flex flex-col gap-2 sm:flex-row">
            <button
              type="submit"
              class="inline-flex flex-1 items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
              :disabled="saving"
            >
              <Save class="h-4 w-4" />
              {{ saving ? '保存中...' : '保存节点' }}
            </button>
            <button
              type="button"
              class="inline-flex items-center justify-center gap-2 rounded-lg border border-border px-4 py-2.5 text-sm text-muted-foreground hover:bg-muted"
              @click="resetForm"
            >
              <Plus class="h-4 w-4" />
              新建
            </button>
          </div>
        </form>
      </aside>
    </div>
  </div>
</template>
