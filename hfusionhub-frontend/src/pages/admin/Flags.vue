<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import LoadingSkeleton from '@/components/LoadingSkeleton.vue'
import ErrorState from '@/components/ErrorState.vue'

interface FeatureFlag {
  key: string
  name: string
  status: 'stable' | 'beta' | 'experimental'
  enabled: boolean
  description: string
  dependencies: string
  howToEnable: string
}

const loading = ref(true)
const loadError = ref(false)
const flags = ref<FeatureFlag[]>([
  {
    key: 'RAG_HYBRID_ENABLED',
    name: 'Hybrid Retrieval (Vector + BM25)',
    status: 'stable',
    enabled: true,
    description: 'Milvus 向量搜索与 BM25 关键词搜索的 RRF 融合检索',
    dependencies: '无',
    howToEnable: '已在 python-ai/.env 中默认开启',
  },
  {
    key: 'RAG_GRAPH_ENABLED',
    name: 'Scoped GraphRAG',
    status: 'beta',
    enabled: false,
    description: '基于知识库范围的实体共现图谱检索通道',
    dependencies: '需先索引文档构建图谱',
    howToEnable: 'python-ai/.env: RAG_GRAPH_ENABLED=true',
  },
  {
    key: 'RAG_RERANKER_MODE',
    name: 'Second-Stage Reranker',
    status: 'beta',
    enabled: false,
    description: '检索结果二次排序（lexical 或 cross_encoder）',
    dependencies: 'cross_encoder 需 pip install -r requirements-reranker.txt',
    howToEnable: 'python-ai/.env: RAG_RERANKER_MODE=lexical 或 cross_encoder',
  },
  {
    key: 'RAG_MULTIMODAL_ENABLED',
    name: 'Multimodal / OCR',
    status: 'experimental',
    enabled: false,
    description: '从文档图片中提取文字证据，融入文本检索管道',
    dependencies: 'Tesseract OCR + pip install -r requirements-multimodal.txt',
    howToEnable: 'python-ai/.env: RAG_MULTIMODAL_ENABLED=true + RAG_MULTIMODAL_OCR_ENABLED=true',
  },
  {
    key: 'RAG_AGENT_WORKFLOW_ENABLED',
    name: 'Single-Agent Workflow',
    status: 'beta',
    enabled: false,
    description: '带超时(45s)、重试(1次)、运行追踪的受限 Agent 工作流',
    dependencies: '无额外依赖',
    howToEnable: 'python-ai/.env: RAG_AGENT_WORKFLOW_ENABLED=true',
  },
  {
    key: 'RAG_MULTI_AGENT_ENABLED',
    name: 'Multi-Agent Collaboration',
    status: 'experimental',
    enabled: false,
    description: '并发专家 Agent（Retrieval/Analysis/Critic/Synthesis）+ 证据校验',
    dependencies: '需先开启 RAG_AGENT_WORKFLOW_ENABLED + 明确选中知识库',
    howToEnable: 'python-ai/.env: RAG_MULTI_AGENT_ENABLED=true',
  },
])

const statusVariant = (status: string) => {
  switch (status) {
    case 'stable': return 'default'
    case 'beta': return 'secondary'
    case 'experimental': return 'outline'
    default: return 'secondary'
  }
}

const statusLabel = (status: string) => {
  switch (status) {
    case 'stable': return 'Stable'
    case 'beta': return 'Beta'
    case 'experimental': return 'Experimental'
    default: return status
  }
}

onMounted(async () => {
  // In future: load real flag status from backend API
  loading.value = false
})
</script>

<template>
  <div class="mx-auto max-w-4xl space-y-6 p-6">
    <div>
      <h1 class="text-2xl font-bold">功能开关管理</h1>
      <p class="mt-1 text-muted-foreground">
        当前状态仅展示配置文档中的默认值。要修改开关，请编辑
        <code class="rounded bg-muted px-1 py-0.5 text-sm">python-ai/.env</code>
        并重启 Python AI 服务。
      </p>
    </div>

    <LoadingSkeleton v-if="loading" type="card" :count="3" />
    <ErrorState
      v-else-if="loadError"
      message="加载功能开关状态失败"
      @retry="loadError = false; loading = true"
    />

    <div v-else class="grid gap-4">
      <Card v-for="flag in flags" :key="flag.key">
        <CardHeader>
          <div class="flex items-center justify-between">
            <div>
              <CardTitle class="text-base">{{ flag.name }}</CardTitle>
              <CardDescription class="mt-1 font-mono text-xs">{{ flag.key }}</CardDescription>
            </div>
            <div class="flex items-center gap-2">
              <Badge :variant="statusVariant(flag.status)">
                {{ statusLabel(flag.status) }}
              </Badge>
              <Badge :variant="flag.enabled ? 'default' : 'secondary'">
                {{ flag.enabled ? '默认开启' : '默认关闭' }}
              </Badge>
            </div>
          </div>
        </CardHeader>
        <CardContent class="space-y-2 text-sm">
          <p>{{ flag.description }}</p>
          <div class="rounded-md bg-muted/50 p-3 text-xs space-y-1">
            <p><strong>依赖：</strong>{{ flag.dependencies }}</p>
            <p><strong>开启方式：</strong><code>{{ flag.howToEnable }}</code></p>
          </div>
        </CardContent>
      </Card>
    </div>
  </div>
</template>
