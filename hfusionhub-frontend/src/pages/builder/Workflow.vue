<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import {
  Plus, Save, Play, Trash2, X, ArrowRight, MessageSquare, Search, Brain,
  Wrench, GitBranch, FileInput, FileOutput, Workflow, ChevronDown,
} from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { useToast } from '@/composables/useToast'
import { useWorkflowStore, type WorkflowNode, type WorkflowEdge } from '@/stores/workflow'
import * as workflowApi from '@/api/workflow'

const toast = useToast()
const store = useWorkflowStore()

const loading = ref(false)
const saving = ref(false)
const savedList = ref<workflowApi.WorkflowDef[]>([])
const showPalette = ref(true)
const showSavedList = ref(false)
const savedListLoading = ref(false)

let nextNodeId = 1
let nextEdgeId = 1

// ── Node palette ──────────────────────────────────────────────────────

const nodeCategories = [
  {
    name: 'LLM',
    icon: Brain,
    nodes: [
      { type: 'llm_chat', label: '对话生成', color: 'bg-violet-500' },
      { type: 'llm_structured', label: '结构化输出', color: 'bg-violet-500' },
      { type: 'llm_intent', label: '意图分类', color: 'bg-violet-500' },
    ],
  },
  {
    name: 'RAG',
    icon: Search,
    nodes: [
      { type: 'rag_retrieve', label: '知识检索', color: 'bg-emerald-500' },
      { type: 'rag_rerank', label: '结果重排', color: 'bg-emerald-500' },
      { type: 'rag_compress', label: '上下文压缩', color: 'bg-emerald-500' },
    ],
  },
  {
    name: 'Tools',
    icon: Wrench,
    nodes: [
      { type: 'tool_search_kb', label: '搜索知识库', color: 'bg-amber-500' },
      { type: 'tool_web_search', label: '网络搜索', color: 'bg-amber-500' },
      { type: 'tool_calculator', label: '计算器', color: 'bg-amber-500' },
    ],
  },
  {
    name: 'Logic',
    icon: GitBranch,
    nodes: [
      { type: 'logic_if', label: '条件判断', color: 'bg-sky-500' },
      { type: 'logic_loop', label: '循环', color: 'bg-sky-500' },
    ],
  },
  {
    name: 'I/O',
    icon: FileInput,
    nodes: [
      { type: 'io_input', label: '输入', color: 'bg-slate-500' },
      { type: 'io_output', label: '输出', color: 'bg-slate-500' },
    ],
  },
]

const nodePalette = computed(() => nodeCategories)

function addNodeToCanvas(catEntry: typeof nodeCategories[0], nodeDef: typeof nodeCategories[0]['nodes'][0]) {
  const id = `node_${nextNodeId++}`
  store.addNode({
    id,
    type: nodeDef.type,
    label: nodeDef.label,
    category: catEntry.name,
    x: 100 + Math.random() * 300,
    y: 100 + Math.random() * 200,
    config: {},
  })
}

// ── Canvas interactions ────────────────────────────────────────────────

const canvasRef = ref<HTMLElement | null>(null)
const draggingNodeId = ref<string | null>(null)
const dragOffset = ref({ x: 0, y: 0 })

function onNodeMouseDown(e: MouseEvent, nodeId: string) {
  if (e.button !== 0) return
  draggingNodeId.value = nodeId
  const node = store.workflow.nodes.find(n => n.id === nodeId)
  if (node) {
    dragOffset.value = { x: e.clientX - node.x, y: e.clientY - node.y }
  }
  store.selectNode(nodeId)
  e.stopPropagation()
}

function onCanvasMouseMove(e: MouseEvent) {
  if (!draggingNodeId.value || !canvasRef.value) return
  const rect = canvasRef.value.getBoundingClientRect()
  const x = e.clientX - rect.left - dragOffset.value.x
  const y = e.clientY - rect.top - dragOffset.value.y
  store.updateNodePosition(draggingNodeId.value, Math.max(0, x), Math.max(0, y))
}

function onCanvasMouseUp() {
  draggingNodeId.value = null
}

function onCanvasClick() {
  store.selectNode(null)
}

// ── Node configuration ────────────────────────────────────────────────

function updateSelectedConfig(key: string, value: any) {
  if (store.selectedNodeId) {
    store.updateNodeConfig(store.selectedNodeId, { [key]: value })
  }
}

// ── Save / Load ────────────────────────────────────────────────────────

async function saveWorkflow() {
  if (!store.workflow.name.trim() || saving.value) return
  saving.value = true
  try {
    const payload = {
      name: store.workflow.name,
      description: store.workflow.description,
      nodes: store.workflow.nodes,
      edges: store.workflow.edges,
    }
    if (store.workflow.id) {
      await workflowApi.updateWorkflow(store.workflow.id, payload)
    } else {
      const res = await workflowApi.createWorkflow(payload)
      store.workflow.id = res.data.id
    }
    store.isDirty = false
    toast.success('工作流已保存')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : '保存失败')
  } finally {
    saving.value = false
  }
}

async function loadSavedList() {
  savedListLoading.value = true
  showSavedList.value = true
  try {
    const res = await workflowApi.listWorkflows()
    savedList.value = res.data.records || []
  } catch {
    savedList.value = []
  } finally {
    savedListLoading.value = false
  }
}

function loadWorkflow(wf: workflowApi.WorkflowDef) {
  store.setWorkflow({
    id: wf.id,
    name: wf.name,
    description: wf.description || '',
    nodes: wf.nodes || [],
    edges: wf.edges || [],
  })
  showSavedList.value = false
  nextNodeId = (wf.nodes?.length || 0) + 1
  toast.success(`已加载「${wf.name}」`)
}

// ── Run ────────────────────────────────────────────────────────────────

function testRun() {
  if (!store.workflow.nodes.length) {
    toast.error('工作流没有节点，请先添加节点')
    return
  }
  toast.success('测试运行已发起（模拟），请查看运行记录')
}

onMounted(() => {
  document.addEventListener('mousemove', onCanvasMouseMove)
  document.addEventListener('mouseup', onCanvasMouseUp)
})
</script>

<template>
  <div class="flex h-[calc(100vh-8rem)] gap-0 -mx-6">
    <!-- Left: Node palette -->
    <div v-if="showPalette" class="w-56 shrink-0 border-r bg-card/50 overflow-auto p-3 space-y-3">
      <div class="flex items-center justify-between">
        <h3 class="text-sm font-semibold">节点面板</h3>
        <Button variant="ghost" size="icon" class="h-6 w-6" @click="showPalette = false">
          <X class="h-3.5 w-3.5" />
        </Button>
      </div>
      <div v-for="cat in nodePalette" :key="cat.name" class="space-y-1.5">
        <div class="flex items-center gap-1.5 text-xs text-muted-foreground font-medium">
          <component :is="cat.icon" class="h-3 w-3" />
          {{ cat.name }}
        </div>
        <button
          v-for="nd in cat.nodes" :key="nd.type"
          class="w-full text-left px-2.5 py-1.5 rounded-md text-xs border border-transparent hover:border-primary/30 hover:bg-accent transition-colors flex items-center gap-2"
          @click="addNodeToCanvas(cat, nd)"
        >
          <span :class="[nd.color, 'w-2 h-2 rounded-full shrink-0']" />
          {{ nd.label }}
        </button>
      </div>
    </div>

    <!-- Center: Canvas -->
    <div class="flex-1 flex flex-col min-w-0">
      <!-- Toolbar -->
      <div class="flex items-center gap-2 px-4 py-2 border-b bg-background">
        <Button v-if="!showPalette" variant="ghost" size="icon" class="h-8 w-8" @click="showPalette = true">
          <Plus class="h-4 w-4" />
        </Button>
        <Input v-model="store.workflow.name" class="h-8 max-w-[200px] text-sm font-medium" placeholder="工作流名称" />
        <Separator orientation="vertical" class="h-6" />
        <Button variant="outline" size="sm" :disabled="saving" @click="saveWorkflow">
          <Save class="h-3.5 w-3.5 mr-1.5" />{{ saving ? '保存中...' : '保存' }}
        </Button>
        <Button variant="outline" size="sm" @click="testRun">
          <Play class="h-3.5 w-3.5 mr-1.5" />测试运行
        </Button>
        <Button variant="ghost" size="sm" @click="loadSavedList">
          <ChevronDown class="h-3.5 w-3.5 mr-1.5" />加载
        </Button>
        <div class="flex-1" />
        <Badge v-if="store.isDirty" variant="outline" class="text-xs border-amber-400 text-amber-400">未保存</Badge>
      </div>

      <!-- Canvas -->
      <div
        ref="canvasRef"
        class="flex-1 relative overflow-auto bg-muted/30"
        style="background-image: radial-gradient(circle, hsl(var(--border)) 1px, transparent 1px); background-size: 20px 20px;"
        @click="onCanvasClick"
      >
        <!-- Empty state -->
        <div v-if="store.workflow.nodes.length === 0" class="absolute inset-0 flex items-center justify-center">
          <div class="text-center space-y-3">
            <Workflow class="h-12 w-12 mx-auto text-muted-foreground/50" />
            <p class="text-muted-foreground text-sm">从左侧面板拖入节点开始构建工作流</p>
          </div>
        </div>

        <!-- Nodes -->
        <div
          v-for="node in store.workflow.nodes"
          :key="node.id"
          :class="[
            'absolute px-3 py-2 rounded-lg border-2 shadow-sm cursor-pointer min-w-[120px] select-none',
            store.selectedNodeId === node.id
              ? 'border-primary bg-primary/5 ring-2 ring-primary/20'
              : 'border-border bg-card hover:border-primary/40',
          ]"
          :style="{ left: node.x + 'px', top: node.y + 'px' }"
          @mousedown="(e) => onNodeMouseDown(e, node.id)"
        >
          <div class="flex items-center gap-2">
            <span
              :class="[
                'w-2 h-2 rounded-full shrink-0',
                nodePalette.find(c => c.name === node.category)?.nodes.find(n => n.type === node.type)?.color || 'bg-slate-400',
              ]"
            />
            <span class="text-xs font-medium">{{ node.label }}</span>
            <button
              class="ml-auto text-muted-foreground hover:text-destructive transition-colors"
              @click.stop="store.removeNode(node.id)"
            >
              <X class="h-3 w-3" />
            </button>
          </div>
          <!-- Output port -->
          <div class="absolute -right-1.5 top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-primary border-2 border-background" />
        </div>

        <!-- SVG edges (simple straight lines) -->
        <svg class="absolute inset-0 pointer-events-none" style="width:100%;height:100%">
          <line
            v-for="edge in store.workflow.edges"
            :key="edge.id"
            :x1="(store.workflow.nodes.find(n => n.id === edge.sourceId)?.x || 0) + 120"
            :y1="(store.workflow.nodes.find(n => n.id === edge.sourceId)?.y || 0) + 20"
            :x2="(store.workflow.nodes.find(n => n.id === edge.targetId)?.x || 0)"
            :y2="(store.workflow.nodes.find(n => n.id === edge.targetId)?.y || 0) + 20"
            stroke="hsl(var(--primary))"
            stroke-width="1.5"
            stroke-dasharray="4 2"
            opacity="0.5"
          />
        </svg>
      </div>
    </div>

    <!-- Right: Inspector panel -->
    <div v-if="store.selectedNode" class="w-64 shrink-0 border-l bg-card/50 overflow-auto p-3 space-y-3">
      <div class="flex items-center justify-between">
        <h3 class="text-sm font-semibold">节点配置</h3>
        <Button variant="ghost" size="icon" class="h-6 w-6" @click="store.selectNode(null)">
          <X class="h-3.5 w-3.5" />
        </Button>
      </div>
      <div class="space-y-3">
        <div class="space-y-1.5">
          <Label class="text-xs">模型</Label>
          <select
            class="w-full text-xs rounded-md border bg-background px-2 py-1.5"
            :value="store.selectedNode?.config?.model || ''"
            @change="updateSelectedConfig('model', ($event.target as HTMLSelectElement).value)"
          >
            <option value="">默认</option>
            <option value="deepseek-chat">DeepSeek Chat</option>
            <option value="ollama:qwen2">Ollama Qwen2</option>
          </select>
        </div>
        <div class="space-y-1.5">
          <Label class="text-xs">温度</Label>
          <input
            type="range" min="0" max="2" step="0.1"
            :value="store.selectedNode?.config?.temperature || 0.7"
            class="w-full"
            @input="updateSelectedConfig('temperature', parseFloat(($event.target as HTMLInputElement).value))"
          />
          <span class="text-xs text-muted-foreground">{{ store.selectedNode?.config?.temperature || 0.7 }}</span>
        </div>
        <div class="space-y-1.5">
          <Label class="text-xs">最大 Token</Label>
          <Input
            type="number"
            class="h-7 text-xs"
            :model-value="store.selectedNode?.config?.maxTokens || 2048"
            @update:model-value="updateSelectedConfig('maxTokens', Number($event))"
          />
        </div>
        <Button variant="destructive" size="sm" class="w-full" @click="store.removeNode(store.selectedNode!.id)">
          <Trash2 class="h-3.5 w-3.5 mr-1.5" />删除节点
        </Button>
      </div>
    </div>

    <!-- Saved workflows dialog -->
    <div
      v-if="showSavedList"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      @click.self="showSavedList = false"
    >
      <Card class="w-[400px] max-h-[500px] overflow-auto p-4 space-y-3">
        <div class="flex items-center justify-between">
          <h3 class="font-semibold">已保存的工作流</h3>
          <Button variant="ghost" size="icon" class="h-6 w-6" @click="showSavedList = false">
            <X class="h-4 w-4" />
          </Button>
        </div>
        <div v-if="savedListLoading" class="text-sm text-muted-foreground text-center py-8">加载中...</div>
        <div v-else-if="savedList.length === 0" class="text-sm text-muted-foreground text-center py-8">暂无已保存的工作流</div>
        <button
          v-for="wf in savedList"
          :key="wf.id"
          class="w-full text-left p-3 rounded-lg border hover:border-primary/50 transition-colors space-y-1"
          @click="loadWorkflow(wf)"
        >
          <p class="text-sm font-medium">{{ wf.name }}</p>
          <p class="text-xs text-muted-foreground">{{ wf.description || '无描述' }}</p>
          <div class="flex items-center gap-2 text-xs text-muted-foreground">
            <span>{{ (wf.nodes || []).length }} 个节点</span>
            <span>·</span>
            <Badge variant="outline" class="text-[10px]">{{ wf.status || 'DRAFT' }}</Badge>
          </div>
        </button>
      </Card>
    </div>
  </div>
</template>
