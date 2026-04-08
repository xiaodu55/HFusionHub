import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface WorkflowNode {
  id: string
  type: string
  label: string
  category: string
  x: number
  y: number
  config: Record<string, any>
}

export interface WorkflowEdge {
  id: string
  sourceId: string
  targetId: string
  sourcePort: string
  targetPort: string
}

export interface WorkflowDef {
  id?: number
  name: string
  description: string
  nodes: WorkflowNode[]
  edges: WorkflowEdge[]
  status?: string
  createdAt?: string
  updatedAt?: string
}

export const useWorkflowStore = defineStore('workflow', () => {
  const workflow = ref<WorkflowDef>({ name: '新建工作流', description: '', nodes: [], edges: [] })
  const selectedNodeId = ref<string | null>(null)
  const isDirty = ref(false)
  const savedWorkflows = ref<WorkflowDef[]>([])

  const selectedNode = computed(() =>
    workflow.value.nodes.find(n => n.id === selectedNodeId.value) || null
  )

  function addNode(node: WorkflowNode) {
    workflow.value.nodes.push(node)
    isDirty.value = true
  }

  function removeNode(nodeId: string) {
    workflow.value.nodes = workflow.value.nodes.filter(n => n.id !== nodeId)
    workflow.value.edges = workflow.value.edges.filter(
      e => e.sourceId !== nodeId && e.targetId !== nodeId
    )
    if (selectedNodeId.value === nodeId) selectedNodeId.value = null
    isDirty.value = true
  }

  function updateNodePosition(nodeId: string, x: number, y: number) {
    const node = workflow.value.nodes.find(n => n.id === nodeId)
    if (node) { node.x = x; node.y = y; isDirty.value = true }
  }

  function updateNodeConfig(nodeId: string, config: Record<string, any>) {
    const node = workflow.value.nodes.find(n => n.id === nodeId)
    if (node) { node.config = { ...node.config, ...config }; isDirty.value = true }
  }

  function addEdge(edge: WorkflowEdge) {
    if (workflow.value.edges.some(e => e.sourceId === edge.sourceId && e.targetId === edge.targetId)) return
    workflow.value.edges.push(edge)
    isDirty.value = true
  }

  function removeEdge(edgeId: string) {
    workflow.value.edges = workflow.value.edges.filter(e => e.id !== edgeId)
    isDirty.value = true
  }

  function selectNode(nodeId: string | null) {
    selectedNodeId.value = nodeId
  }

  function resetWorkflow() {
    workflow.value = { name: '新建工作流', description: '', nodes: [], edges: [] }
    selectedNodeId.value = null
    isDirty.value = false
  }

  function setWorkflow(wf: WorkflowDef) {
    workflow.value = { ...wf }
    selectedNodeId.value = null
    isDirty.value = false
  }

  return {
    workflow, selectedNodeId, isDirty, savedWorkflows, selectedNode,
    addNode, removeNode, updateNodePosition, updateNodeConfig,
    addEdge, removeEdge, selectNode, resetWorkflow, setWorkflow,
  }
})
