<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

const props = defineProps<{
  content: string
}>()

const rootEl = ref<HTMLElement | null>(null)

// 配置 marked
marked.setOptions({
  gfm: true,
  breaks: true,
})

const renderedContent = computed(() => {
  if (!props.content) return ''

  try {
    // 渲染 Markdown
    let html = marked.parse(props.content) as string
    // 清理 HTML（防止 XSS）
    html = DOMPurify.sanitize(html, {
      ADD_TAGS: ['code', 'pre', 'span'],
      ADD_ATTR: ['class'],
    })
    // 为每个代码块包装复制按钮（在 sanitize 之后注入，避免被过滤）
    html = html.replace(
      /<pre><code([^>]*)>([\s\S]*?)<\/code><\/pre>/g,
      (_, attrs, code) =>
        `<div class="code-block"><div class="code-block-header"><button type="button" class="code-copy-btn" data-copy-code="true">复制</button></div><pre><code${attrs}>${code}</code></pre></div>`,
    )
    return html
  } catch (e) {
    // 如果渲染失败，返回纯文本
    return props.content
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/\n/g, '<br>')
  }
})

const handleContainerClick = (event: MouseEvent) => {
  const button = (event.target as HTMLElement).closest<HTMLElement>('[data-copy-code]')
  if (!button) return
  const block = button.closest<HTMLElement>('.code-block')
  const codeElement = block?.querySelector('pre code')
  if (!codeElement) return
  const text = codeElement.textContent || ''

  const copy = () => {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text)
    }
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
    return Promise.resolve()
  }

  copy().then(() => {
    button.textContent = '已复制'
    setTimeout(() => {
      button.textContent = '复制'
    }, 1500)
  }).catch(() => {
    button.textContent = '复制失败'
    setTimeout(() => {
      button.textContent = '复制'
    }, 1500)
  })
}

onMounted(() => {
  rootEl.value?.addEventListener('click', handleContainerClick)
})

onBeforeUnmount(() => {
  rootEl.value?.removeEventListener('click', handleContainerClick)
})
</script>

<template>
  <div ref="rootEl" class="markdown-body prose prose-sm dark:prose-invert max-w-none" v-html="renderedContent" />
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

.markdown-body :deep(.code-block) {
  position: relative;
  margin: 0.5rem 0;
}

.markdown-body :deep(.code-block-header) {
  display: flex;
  justify-content: flex-end;
  position: absolute;
  top: 0.35rem;
  right: 0.35rem;
  z-index: 1;
}

.markdown-body :deep(.code-copy-btn) {
  border: 1px solid hsl(var(--border));
  background-color: hsl(var(--card));
  color: hsl(var(--muted-foreground));
  border-radius: 0.375rem;
  padding: 0.15rem 0.5rem;
  font-size: 0.7rem;
  line-height: 1.4;
  cursor: pointer;
  opacity: 0.75;
  transition: opacity 150ms ease;
}

.markdown-body :deep(.code-copy-btn:hover) {
  opacity: 1;
  color: hsl(var(--primary));
  border-color: hsl(var(--primary) / 0.4);
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
  display: block;
  overflow-x: auto;
  white-space: nowrap;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid hsl(var(--border));
  padding: 0.5rem;
  text-align: left;
  white-space: normal;
  min-width: 8rem;
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
