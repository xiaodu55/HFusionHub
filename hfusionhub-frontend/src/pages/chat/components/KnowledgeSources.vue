<script setup lang="ts">
interface ChatSource {
  document_id?: number | string
  document_name?: string
  title?: string
  score?: number
  outline_path?: string[]
  content?: string
}

const props = defineProps<{
  sources: ChatSource[]
  knowledgeBaseId?: number | null
}>()

// 引用分数展示（缺 score 时显示空，避免 NaN%）
const formatScore = (score?: number) => (score == null ? '' : `${Math.round(score * 100)}%`)

const sourceTitle = (source: ChatSource) =>
  source.document_name || source.title || `文档 #${source.document_id ?? '未知'}`

// 有知识库上下文且来源带 doc id 时渲染为可跳转链接，否则为纯文本外壳
const linkable = (source: ChatSource) =>
  Boolean(props.knowledgeBaseId && source.document_id)

const wrapperProps = (source: ChatSource) => {
  if (!linkable(source)) return {}
  return {
    to: `/knowledge-base/${props.knowledgeBaseId}/chunks/${source.document_id}`,
    title: '查看分块：' + sourceTitle(source),
  }
}

const wrapperClass = (source: ChatSource) =>
  linkable(source)
    ? 'block text-xs bg-secondary-foreground/5 rounded px-2 py-1.5 transition-colors hover:bg-primary/10'
    : 'text-xs bg-secondary-foreground/5 rounded px-2 py-1.5'

const wrapperTag = (source: ChatSource) =>
  (linkable(source) ? 'router-link' : 'div') as unknown as string
</script>

<template>
  <div class="mt-3 pt-3 border-t border-secondary-foreground/20">
    <p class="text-xs font-medium mb-2 flex items-center gap-1">
      <span>📚</span>
      <span>知识来源</span>
      <span class="opacity-60">({{ sources.length }}条)</span>
    </p>
    <div class="space-y-1.5">
      <component
        :is="wrapperTag(source)"
        v-for="(source, index) in sources"
        :key="index"
        v-bind="wrapperProps(source)"
        :class="wrapperClass(source)"
      >
        <div class="flex items-center justify-between gap-2">
          <span class="font-medium truncate flex-1" :title="source.document_name || source.title">
            {{ sourceTitle(source) }}
          </span>
          <span class="shrink-0 text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary">
            {{ formatScore(source.score) }}
          </span>
        </div>
        <p v-if="source.outline_path && source.outline_path.length" class="mt-1 text-[10px] opacity-60 truncate">
          {{ source.outline_path.join(' > ') }}
        </p>
        <p v-if="source.content" class="mt-1 text-[11px] opacity-60 line-clamp-2">
          {{ source.content }}
        </p>
      </component>
    </div>
  </div>
</template>
