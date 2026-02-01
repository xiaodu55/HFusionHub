<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

const props = defineProps<{
  content: string
}>()

// 配置 marked
marked.setOptions({
  gfm: true,
  breaks: true,
})

const renderedContent = computed(() => {
  if (!props.content) return ''

  try {
    // 渲染 Markdown
    const html = marked.parse(props.content) as string
    // 清理 HTML（防止 XSS）
    return DOMPurify.sanitize(html, {
      ADD_TAGS: ['code', 'pre', 'span'],
      ADD_ATTR: ['class'],
    })
  } catch (e) {
    // 如果渲染失败，返回纯文本
    return props.content
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/\n/g, '<br>')
  }
})
</script>

<template>
  <div class="markdown-body prose prose-sm dark:prose-invert max-w-none" v-html="renderedContent" />
</template>

<style scoped>
.markdown-body :deep(pre) {
  background-color: hsl(var(--muted));
  border-radius: 0.5rem;
  padding: 1rem;
  overflow-x: auto;
  margin: 0.5rem 0;
}

.markdown-body :deep(code) {
  background-color: hsl(var(--muted));
  border-radius: 0.25rem;
  padding: 0.125rem 0.25rem;
  font-size: 0.875rem;
}

.markdown-body :deep(pre code) {
  background-color: transparent;
  padding: 0;
}

.markdown-body :deep(p) {
  margin: 0.5rem 0;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 1.5rem;
  margin: 0.5rem 0;
}

.markdown-body :deep(li) {
  margin: 0.25rem 0;
}

.markdown-body :deep(blockquote) {
  border-left: 3px solid hsl(var(--border));
  padding-left: 1rem;
  margin: 0.5rem 0;
  color: hsl(var(--muted-foreground));
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4),
.markdown-body :deep(h5),
.markdown-body :deep(h6) {
  font-weight: 600;
  margin: 1rem 0 0.5rem 0;
}

.markdown-body :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 0.5rem 0;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid hsl(var(--border));
  padding: 0.5rem;
  text-align: left;
}

.markdown-body :deep(th) {
  background-color: hsl(var(--muted));
}

.markdown-body :deep(a) {
  color: hsl(var(--primary));
  text-decoration: underline;
}

.markdown-body :deep(a:hover) {
  opacity: 0.8;
}
</style>
