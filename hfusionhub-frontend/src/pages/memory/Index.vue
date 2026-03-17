<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  BookOpenCheck,
  Brain,
  Check,
  CircleHelp,
  Lightbulb,
  LoaderCircle,
  MessageSquareText,
  Plus,
  ShieldCheck,
  Sparkles,
  Trash2,
  UserRound,
} from 'lucide-vue-next'
import * as memoryApi from '@/api/memory'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import LoadingSkeleton from '@/components/LoadingSkeleton.vue'
import { useToast } from '@/composables/useToast'

type MemoryType = 'user_preference' | 'entity_fact' | 'conversation_summary'
type TypeFilter = MemoryType | 'ALL'

const toast = useToast()
const memories = ref<memoryApi.MemoryEntry[]>([])
const draft = ref('')
const selectedType = ref<MemoryType>('user_preference')
const activeFilter = ref<TypeFilter>('ALL')
const loading = ref(false)
const saving = ref(false)
const removingId = ref<number | null>(null)

const memoryTypes: Array<{ value: MemoryType; label: string; shortLabel: string; description: string; placeholder: string; icon: typeof UserRound; importance: number }> = [
  {
    value: 'user_preference',
    label: '回应偏好',
    shortLabel: '偏好',
    description: '告诉 AI 你希望它如何回答',
    placeholder: '例如：默认用简洁的中文回答，并先给结论再解释。',
    icon: UserRound,
    importance: 0.8,
  },
  {
    value: 'entity_fact',
    label: '个人事实',
    shortLabel: '事实',
    description: '保存长期有效的背景信息',
    placeholder: '例如：我主要使用 Java 和 Vue，项目使用 MySQL。',
    icon: BookOpenCheck,
    importance: 0.7,
  },
  {
    value: 'conversation_summary',
    label: '工作上下文',
    shortLabel: '上下文',
    description: '保存之后仍需延续的任务背景',
    placeholder: '例如：当前项目是 HFusionHub，重点关注 Agent 与 RAG 的稳定性。',
    icon: MessageSquareText,
    importance: 0.65,
  },
]

const currentType = computed(() => memoryTypes.find(type => type.value === selectedType.value) || memoryTypes[0])
const filteredMemories = computed(() => activeFilter.value === 'ALL'
  ? memories.value
  : memories.value.filter(memory => memory.type === activeFilter.value))
const memoryCount = (type: MemoryType) => memories.value.filter(memory => memory.type === type).length
const totalMemoryCount = computed(() => memories.value.length)

const typeMeta = (type?: string) => memoryTypes.find(item => item.value === type) || {
  value: 'user_preference' as MemoryType,
  label: '其他记忆',
  shortLabel: '记忆',
  description: '',
  placeholder: '',
  icon: Brain,
  importance: 0.5,
}

const load = async () => {
  loading.value = true
  try {
    memories.value = (await memoryApi.listMemories()).data
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '加载记忆失败')
  } finally {
    loading.value = false
  }
}

const add = async () => {
  const content = draft.value.trim()
  if (!content || saving.value) return
  saving.value = true
  try {
    await memoryApi.createMemory({
      type: selectedType.value,
      content,
      importance: currentType.value.importance,
    })
    draft.value = ''
    toast.success('已保存。AI 会在相关对话中参考这条记忆。')
    await load()
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '保存记忆失败')
  } finally {
    saving.value = false
  }
}

const useTemplate = (type: MemoryType, content: string) => {
  selectedType.value = type
  draft.value = content
  document.getElementById('memory-draft')?.focus()
}

const remove = async (id: number) => {
  if (removingId.value !== null) return
  removingId.value = id
  try {
    await memoryApi.deleteMemory(id)
    memories.value = memories.value.filter(memory => memory.id !== id)
    toast.success('该记忆已删除，后续对话不会再参考它。')
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '删除记忆失败')
  } finally {
    removingId.value = null
  }
}

const formatDate = (value?: string | null) => value ? value.replace('T', ' ').slice(0, 10) : '刚刚保存'
const importanceLabel = (importance?: number) => {
  if ((importance ?? 0.5) >= 0.75) return '高优先级'
  if ((importance ?? 0.5) >= 0.5) return '标准优先级'
  return '低优先级'
}

onMounted(load)
</script>

<template>
  <div class="space-y-6 pb-4">
    <section class="relative overflow-hidden rounded-2xl border border-border bg-card/80 shadow-[0_18px_45px_rgba(0,0,0,0.18)]">
      <div class="pointer-events-none absolute -right-12 -top-16 h-48 w-48 rounded-full bg-primary/10 blur-3xl" />
      <div class="relative flex flex-col gap-5 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
        <div class="flex gap-4">
          <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-primary/25 bg-primary/10 text-primary"><Brain class="h-5 w-5" /></div>
          <div>
            <p class="text-xs font-medium tracking-[0.16em] text-primary/90">PERSONAL MEMORY</p>
            <h2 class="mt-1 text-2xl font-semibold tracking-tight">让对话越来越懂你</h2>
            <p class="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">把希望长期保留的信息存下来。AI 只会在问题相关时引用它们，例如你的回答偏好、技术栈或正在进行的工作背景。</p>
          </div>
        </div>
        <div class="flex shrink-0 items-center gap-2 rounded-xl border border-border bg-background/40 px-3.5 py-2.5 text-sm">
          <Sparkles class="h-4 w-4 text-primary" />
          <span><strong class="font-semibold text-foreground">{{ totalMemoryCount }}</strong><span class="ml-1 text-muted-foreground">条已保存</span></span>
        </div>
      </div>
    </section>

    <div class="grid items-start gap-6 xl:grid-cols-[minmax(0,1.45fr)_minmax(18rem,0.75fr)]">
      <div class="space-y-6">
        <Card class="border-border bg-card/80">
          <CardHeader class="border-b border-border/70 p-5 sm:p-6">
            <div class="flex items-center gap-3">
              <div class="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary"><Plus class="h-4 w-4" /></div>
              <div><CardTitle class="text-base">新增一条记忆</CardTitle><CardDescription class="mt-1">只保存未来多次对话都值得沿用的信息</CardDescription></div>
            </div>
          </CardHeader>
          <CardContent class="p-5 sm:p-6">
            <div class="grid gap-2 sm:grid-cols-3">
              <button
                v-for="type in memoryTypes"
                :key="type.value"
                class="rounded-xl border p-3.5 text-left transition-all"
                :class="selectedType === type.value ? 'border-primary/50 bg-primary/[0.08] shadow-[inset_0_0_0_1px_rgba(52,211,153,0.08)]' : 'border-border bg-muted/20 hover:border-primary/25 hover:bg-muted/45'"
                @click="selectedType = type.value"
              >
                <component :is="type.icon" class="h-4 w-4" :class="selectedType === type.value ? 'text-primary' : 'text-muted-foreground'" />
                <p class="mt-3 text-sm font-medium">{{ type.label }}</p>
                <p class="mt-1 text-xs leading-5 text-muted-foreground">{{ type.description }}</p>
              </button>
            </div>
            <label for="memory-draft" class="mt-5 block text-sm font-medium">{{ currentType.label }}</label>
            <textarea
              id="memory-draft"
              v-model="draft"
              rows="4"
              maxlength="4000"
              class="mt-2 block w-full resize-y rounded-xl border border-input bg-background/60 px-3.5 py-3 text-sm leading-6 outline-none placeholder:text-muted-foreground focus:border-primary/50 focus:ring-2 focus:ring-primary/20"
              :placeholder="currentType.placeholder"
              @keydown.ctrl.enter.prevent="add"
              @keydown.meta.enter.prevent="add"
            />
            <div class="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <p class="text-xs leading-5 text-muted-foreground">仅在相关问题中使用 · 可随时删除 · {{ draft.length }}/4000</p>
              <Button :disabled="!draft.trim() || saving" class="gap-2" @click="add"><LoaderCircle v-if="saving" class="h-4 w-4 animate-spin" /><Check v-else class="h-4 w-4" />保存记忆</Button>
            </div>
          </CardContent>
        </Card>

        <Card class="overflow-hidden border-border bg-card/80">
          <CardHeader class="border-b border-border/70 p-5">
            <div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div><CardTitle class="text-base">已保存的记忆</CardTitle><CardDescription class="mt-1">这些内容会在相关的对话中作为额外上下文提供给 AI</CardDescription></div>
              <div class="flex gap-1 overflow-x-auto rounded-lg bg-muted/45 p-1">
                <button class="shrink-0 rounded-md px-2.5 py-1.5 text-xs transition-colors" :class="activeFilter === 'ALL' ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'" @click="activeFilter = 'ALL'">全部 {{ totalMemoryCount }}</button>
                <button v-for="type in memoryTypes" :key="type.value" class="shrink-0 rounded-md px-2.5 py-1.5 text-xs transition-colors" :class="activeFilter === type.value ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'" @click="activeFilter = type.value">{{ type.shortLabel }} {{ memoryCount(type.value) }}</button>
              </div>
            </div>
          </CardHeader>
          <CardContent class="p-4 sm:p-5">
            <LoadingSkeleton v-if="loading" type="list" :count="3" />
            <div v-else-if="!filteredMemories.length" class="flex min-h-56 flex-col items-center justify-center rounded-xl border border-dashed border-border px-6 text-center">
              <div class="flex h-11 w-11 items-center justify-center rounded-xl bg-muted text-muted-foreground"><Lightbulb class="h-5 w-5" /></div>
              <h3 class="mt-4 font-medium">{{ activeFilter === 'ALL' ? '还没有保存记忆' : '该分类下暂无记忆' }}</h3>
              <p class="mt-1 max-w-sm text-sm leading-6 text-muted-foreground">{{ activeFilter === 'ALL' ? '从上方填写一条你希望 AI 在以后记住的信息。' : '可以切换分类查看，或在上方添加新的记忆。' }}</p>
            </div>
            <div v-else class="grid gap-3 md:grid-cols-2">
              <article v-for="memory in filteredMemories" :key="memory.id" class="group relative rounded-xl border border-border bg-muted/20 p-4 transition-colors hover:border-primary/25 hover:bg-muted/40">
                <div class="flex items-start justify-between gap-3">
                  <div class="flex min-w-0 items-center gap-2"><component :is="typeMeta(memory.type).icon" class="h-4 w-4 shrink-0 text-primary" /><Badge variant="outline" class="border-primary/20 bg-primary/[0.06] text-primary">{{ typeMeta(memory.type).shortLabel }}</Badge></div>
                  <button class="rounded-md p-1.5 text-muted-foreground opacity-0 transition-all hover:bg-rose-400/10 hover:text-rose-300 group-hover:opacity-100 focus:opacity-100" :disabled="removingId === memory.id" :aria-label="`删除记忆：${memory.content}`" @click="remove(memory.id)"><LoaderCircle v-if="removingId === memory.id" class="h-4 w-4 animate-spin" /><Trash2 v-else class="h-4 w-4" /></button>
                </div>
                <p class="mt-3 break-words text-sm leading-6 text-foreground">{{ memory.content }}</p>
                <div class="mt-4 flex items-center justify-between gap-2 border-t border-border/70 pt-3 text-xs text-muted-foreground"><span>{{ importanceLabel(memory.importance) }}</span><span>{{ formatDate(memory.createdAt) }}</span></div>
              </article>
            </div>
          </CardContent>
        </Card>
      </div>

      <aside class="space-y-4 xl:sticky xl:top-6">
        <Card class="border-primary/20 bg-primary/[0.055]">
          <CardHeader class="p-5 pb-3"><div class="flex items-center gap-2"><CircleHelp class="h-4 w-4 text-primary" /><CardTitle class="text-base">它是怎么工作的？</CardTitle></div></CardHeader>
          <CardContent class="space-y-4 p-5 pt-2 text-sm leading-6 text-muted-foreground">
            <div class="flex gap-3"><span class="mt-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary text-[11px] font-semibold text-primary-foreground">1</span><p>你主动保存偏好、事实或工作背景。</p></div>
            <div class="flex gap-3"><span class="mt-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary text-[11px] font-semibold text-primary-foreground">2</span><p>每次对话时，系统只挑选与当前问题相关的最多 5 条记忆。</p></div>
            <div class="flex gap-3"><span class="mt-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary text-[11px] font-semibold text-primary-foreground">3</span><p>AI 用这些上下文调整回答；删除后便不会再使用。</p></div>
          </CardContent>
        </Card>

        <Card class="border-border bg-card/80">
          <CardHeader class="p-5 pb-3"><div class="flex items-center gap-2"><Lightbulb class="h-4 w-4 text-amber-300" /><CardTitle class="text-base">快速开始</CardTitle></div><CardDescription class="mt-1">选择一条模板后可再编辑</CardDescription></CardHeader>
          <CardContent class="space-y-2 p-5 pt-2">
            <button class="w-full rounded-lg border border-border bg-muted/25 p-3 text-left text-sm leading-5 transition-colors hover:border-primary/30 hover:bg-primary/[0.06]" @click="useTemplate('user_preference', '默认使用简洁的中文回答，先给结论，再说明关键原因。')">“默认使用简洁的中文回答”</button>
            <button class="w-full rounded-lg border border-border bg-muted/25 p-3 text-left text-sm leading-5 transition-colors hover:border-primary/30 hover:bg-primary/[0.06]" @click="useTemplate('entity_fact', '我主要使用 Java、Vue 和 MySQL 开发企业应用。')">“我的常用技术栈”</button>
            <button class="w-full rounded-lg border border-border bg-muted/25 p-3 text-left text-sm leading-5 transition-colors hover:border-primary/30 hover:bg-primary/[0.06]" @click="useTemplate('conversation_summary', '当前重点是完善 HFusionHub 的 Agent、RAG 和前端体验。')">“保存当前工作重点”</button>
          </CardContent>
        </Card>

        <div class="flex gap-3 rounded-xl border border-border bg-muted/20 p-4 text-sm leading-6 text-muted-foreground"><ShieldCheck class="mt-0.5 h-4 w-4 shrink-0 text-primary" /><p>记忆归当前账号所有，只用于你的后续对话；不希望保留的信息可以随时删除。</p></div>
      </aside>
    </div>
  </div>
</template>
