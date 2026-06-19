<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import {
  getAiHealth,
  getAiRuntimeOverview,
  getUserModelConfig,
  type AiHealth,
  type AiRuntimeOverview,
  type UserModelConfig,
} from '@/api/system'
import { clearDemoData, importDemoData, type DemoSectionResult } from '@/api/demo'
import * as knowledgeBaseApi from '@/api/knowledgeBase'
import * as conversationApi from '@/api/conversation'
import { useToast } from '@/composables/useToast'
import { Button } from '@/components/ui/button'
import { Check, CircleAlert, Loader2, MessageSquare, Rocket, X } from 'lucide-vue-next'

const router = useRouter()
const userStore = useUserStore()
const toast = useToast()

const loading = ref(true)
const health = ref<AiHealth | null>(null)
const runtime = ref<AiRuntimeOverview | null>(null)
const modelConfig = ref<UserModelConfig | null>(null)
const kbCount = ref(0)
const convCount = ref(0)
const importing = ref(false)
const clearing = ref(false)
const lastSections = ref<DemoSectionResult[]>([])
// 收起只对当前页面生效，刷新/下次进入自动恢复显示；
// 全部完成后才由 allDone 永久隐藏——避免误点 × 后再也找不回
const dismissed = ref(false)

const modelReady = computed(() => {
  if (modelConfig.value?.configured) return true
  const llm = runtime.value?.llm
  if (!llm) return false
  return ['ready', 'configured', 'reachable', 'development'].includes(llm.state)
})

const items = computed(() => {
  const list = [
    {
      key: 'ai',
      label: 'AI 服务就绪',
      hint: health.value?.ready ? 'Java ↔ Python 链路正常' : (health.value?.summary || 'AI 服务未就绪，见「设置 → AI 服务状态」'),
      done: !!health.value?.ready,
      path: '/settings',
      cta: '查看',
    },
    {
      key: 'model',
      label: '问答模型已配置',
      hint: modelReady.value ? '已有可用模型' : '尚未配置模型（DeepSeek / Ollama，见「模型中心」）',
      done: modelReady.value,
      path: '/builder/models',
      cta: '去配置',
    },
    {
      key: 'kb',
      label: '创建知识库',
      hint: kbCount.value > 0 ? `已创建 ${kbCount.value} 个知识库` : '还没有知识库，可自行创建或一键导入演示数据',
      done: kbCount.value > 0,
      path: '/knowledge-base',
      cta: '去创建',
    },
    {
      key: 'chat',
      label: '发起首次对话',
      hint: convCount.value > 0 ? `已开始 ${convCount.value} 次对话` : '还没有对话，准备好资料后开始提问',
      done: convCount.value > 0,
      path: '/chat',
      cta: '去提问',
    },
  ]
  // 普通用户不能配置模型，不展示模型检查项
  return userStore.isBuilder ? list : list.filter((item) => item.key !== 'model')
})

const doneCount = computed(() => items.value.filter((item) => item.done).length)
const allDone = computed(() => items.value.length > 0 && items.value.every((item) => item.done))
const show = computed(() => !dismissed.value && !allDone.value)

const refresh = async () => {
  loading.value = true
  try {
    const [healthRes, runtimeRes, modelRes, kbRes, convRes] = await Promise.allSettled([
      getAiHealth(),
      getAiRuntimeOverview(),
      getUserModelConfig(),
      knowledgeBaseApi.getMyKnowledgeBaseList({ page: 1, pageSize: 1 }),
      conversationApi.getMyConversations({ page: 1, pageSize: 1 }),
    ])
    if (healthRes.status === 'fulfilled') health.value = healthRes.value.data
    if (runtimeRes.status === 'fulfilled') runtime.value = runtimeRes.value.data
    if (modelRes.status === 'fulfilled') modelConfig.value = modelRes.value.data
    if (kbRes.status === 'fulfilled') kbCount.value = kbRes.value.data.total || 0
    if (convRes.status === 'fulfilled') convCount.value = convRes.value.data.total || 0
  } finally {
    loading.value = false
  }
}

const handleImportDemo = async () => {
  if (!userStore.isAdmin) return
  importing.value = true
  try {
    const res = await importDemoData()
    const data = res.data
    lastSections.value = (data.sections ?? []).filter((s) => s.importedCount > 0 || s.skippedCount > 0)
    if (data.parseFailedCount > 0) {
      toast.warning(`${data.message}（AI 服务就绪后可到文档页重新解析）`)
    } else {
      toast.success(data.message)
    }
    await refresh()
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '导入演示数据失败')
  } finally {
    importing.value = false
  }
}

const handleClearDemo = async () => {
  if (!userStore.isAdmin) return
  clearing.value = true
  try {
    const res = await clearDemoData()
    lastSections.value = []
    toast.success(res.data.message)
    await refresh()
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '清除演示数据失败')
  } finally {
    clearing.value = false
  }
}

const dismiss = () => {
  dismissed.value = true
}

const reshow = () => {
  dismissed.value = false
}

onMounted(refresh)
</script>

<template>
  <div v-if="!show && !allDone" class="mb-1 flex justify-end">
    <button
      type="button"
      class="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground"
      title="重新显示设置引导"
      @click="reshow"
    >
      <Rocket class="h-3.5 w-3.5" />
      显示设置引导
    </button>
  </div>
  <section v-if="show" class="setup-checklist glass-panel p-4 sm:p-5">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div class="flex items-start gap-3">
        <span class="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-emerald-400/15 text-emerald-700 dark:text-emerald-300">
          <Rocket class="h-4 w-4" />
        </span>
        <div>
          <p class="text-sm font-semibold text-foreground">完成设置，开始使用</p>
          <p class="mt-1 text-xs text-muted-foreground">
            {{ loading ? '正在检查环境…' : `已完成 ${doneCount} / ${items.length} 项` }}
          </p>
        </div>
      </div>
      <button
        type="button"
        class="rounded-md p-1.5 text-muted-foreground transition hover:bg-foreground/10 hover:text-foreground"
        title="收起（本次会话不再显示，刷新后恢复）"
        @click="dismiss"
      >
        <X class="h-4 w-4" />
      </button>
    </div>

    <div class="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
      <button
        v-for="item in items"
        :key="item.key"
        type="button"
        class="flex items-start gap-2.5 rounded-lg border p-3 text-left transition"
        :class="item.done
          ? 'border-emerald-400/20 bg-emerald-400/5 hover:bg-emerald-400/10'
          : 'border-border bg-foreground/[0.03] hover:bg-foreground/[0.07]'"
        @click="router.push(item.path)"
      >
        <span
          class="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full"
          :class="item.done ? 'bg-emerald-400 text-black' : 'bg-foreground/10 text-muted-foreground'"
        >
          <Check v-if="item.done" class="h-3 w-3" />
          <CircleAlert v-else class="h-3 w-3" />
        </span>
        <span class="min-w-0">
          <span class="block truncate text-sm font-medium text-foreground">{{ item.label }}</span>
          <span class="mt-1 block text-xs leading-5 text-muted-foreground">{{ item.hint }}</span>
          <span class="mt-1.5 block text-xs font-medium text-emerald-700 dark:text-emerald-300">{{ item.cta }} →</span>
        </span>
      </button>
    </div>

    <div
      v-if="userStore.isAdmin"
      class="mt-4 rounded-lg border border-emerald-400/15 bg-emerald-400/5 p-3"
    >
      <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div class="flex items-start gap-2.5 text-sm text-foreground/80">
          <MessageSquare class="mt-0.5 h-4 w-4 shrink-0 text-emerald-700 dark:text-emerald-300" />
          <span>
            想快速体验？<span class="text-foreground">一键导入演示数据</span>
            （知识库文档、回答方案、我的笔记、我的记忆、应用发布、公告），导入后即可直接提问。
          </span>
        </div>
        <div class="flex shrink-0 gap-2">
          <Button
            variant="outline"
            class="rounded-lg border-border text-foreground/80 hover:bg-foreground/10 disabled:opacity-60"
            :disabled="importing || clearing"
            title="知识库与回答方案移入回收站，7 天内可恢复"
            @click="handleClearDemo"
          >
            <Loader2 v-if="clearing" class="mr-1.5 h-4 w-4 animate-spin" />
            {{ clearing ? '正在清除…' : '清除演示数据' }}
          </Button>
          <Button
            class="rounded-lg bg-emerald-400 text-black hover:bg-emerald-300 disabled:opacity-60"
            :disabled="importing || clearing"
            @click="handleImportDemo"
          >
            <Loader2 v-if="importing" class="mr-1.5 h-4 w-4 animate-spin" />
            {{ importing ? '正在导入…' : '导入演示数据' }}
          </Button>
        </div>
      </div>

      <!-- 分项结果：让管理员看清每个菜单导入了多少 -->
      <ul v-if="lastSections.length" class="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 border-t border-border pt-3 text-xs text-muted-foreground">
        <li v-for="section in lastSections" :key="section.section">
          {{ section.label }}：
          <span v-if="section.importedCount" class="text-emerald-700 dark:text-emerald-300">新增 {{ section.importedCount }}</span>
          <span v-if="section.importedCount && section.skippedCount"> · </span>
          <span v-if="section.skippedCount">已存在 {{ section.skippedCount }}</span>
        </li>
      </ul>
    </div>
  </section>
</template>
