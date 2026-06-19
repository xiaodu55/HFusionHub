<script setup lang="ts">
import { computed } from 'vue'

interface StepItem {
  title: string
  description?: string
}

interface Props {
  /** Icon component from lucide-vue-next */
  icon?: any
  title?: string
  description?: string
  action?: string
  /** Whether to show a "create" action button */
  showAction?: boolean
  /** 可点击的示例提示（如示例问题），点击触发 example 事件 */
  examples?: string[]
  /** 示例区的标题（默认「试试这样」） */
  examplesLabel?: string
  /** 分步引导（首次使用教程），序号自动生成 */
  steps?: StepItem[]
}

const props = withDefaults(defineProps<Props>(), {
  title: '暂无数据',
  action: '创建',
  showAction: false,
  examplesLabel: '试试这样',
})

const emit = defineEmits<{
  action: []
  example: [text: string]
}>()

const description = computed(() => {
  return props.description || `还没有${props.title}，点击下方按钮${props.action}吧`
})
</script>

<template>
  <div class="flex flex-col items-center justify-center px-4 py-14">
    <div
      v-if="icon"
      class="flex h-20 w-20 items-center justify-center rounded-2xl border border-border/60 bg-gradient-to-b from-muted/70 to-muted/30 shadow-sm"
    >
      <component
        :is="icon"
        class="h-10 w-10 text-muted-foreground"
        :stroke-width="1.5"
      />
    </div>
    <div v-else class="flex h-20 w-20 items-center justify-center rounded-2xl border border-border/60 bg-gradient-to-b from-muted/70 to-muted/30 shadow-sm">
      <svg class="h-10 w-10 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
        <path stroke-linecap="round" stroke-linejoin="round" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
      </svg>
    </div>
    <h3 class="mt-6 text-lg font-semibold text-foreground">{{ title }}</h3>
    <p class="mt-2 max-w-md text-center text-sm leading-6 text-muted-foreground">
      {{ description }}
    </p>

    <!-- 分步引导：首次使用教程 -->
    <ol v-if="steps?.length" class="mt-7 w-full max-w-md space-y-3">
      <li
        v-for="(step, index) in steps"
        :key="step.title"
        class="flex items-start gap-3 rounded-xl border border-border/70 bg-muted/20 p-3.5 transition-colors hover:border-primary/25 hover:bg-muted/40"
      >
        <span class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/12 text-xs font-semibold tabular-nums text-primary">{{ index + 1 }}</span>
        <span class="min-w-0">
          <span class="block text-sm font-medium text-foreground">{{ step.title }}</span>
          <span v-if="step.description" class="mt-0.5 block text-xs leading-5 text-muted-foreground">{{ step.description }}</span>
        </span>
      </li>
    </ol>

    <!-- 示例提示：可点击 -->
    <div v-if="examples?.length" class="mt-7 w-full max-w-md">
      <p class="text-center text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground/70">{{ examplesLabel }}</p>
      <div class="mt-3 flex flex-wrap items-center justify-center gap-2">
        <button
          v-for="example in examples"
          :key="example"
          type="button"
          class="rounded-full border border-border bg-card/70 px-3.5 py-1.5 text-xs leading-5 text-muted-foreground transition-all hover:border-primary/40 hover:bg-primary/8 hover:text-foreground"
          :title="`点击使用示例：${example}`"
          @click="emit('example', example)"
        >
          {{ example }}
        </button>
      </div>
    </div>

    <button
      v-if="showAction"
      class="mt-7 inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm transition-all hover:bg-primary/90 hover:shadow"
      @click="emit('action')"
    >
      <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
        <path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
      </svg>
      {{ action }}
    </button>
  </div>
</template>
