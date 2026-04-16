<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import * as promptTemplateApi from '@/api/promptTemplate'
import type { PromptTemplate } from '@/api/promptTemplate'
import { useToast } from '@/composables/useToast'
import { formatDateTime } from '@/utils/date'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  AlertTriangle,
  Archive,
  ArrowLeft,
  Clock3,
  FileText,
  Loader2,
  RotateCcw,
  Search,
  Trash2,
} from 'lucide-vue-next'

const router = useRouter()
const toast = useToast()
const templates = ref<PromptTemplate[]>([])
const keyword = ref('')
const loading = ref(false)
const loadError = ref(false)
const actionId = ref<number | null>(null)

const total = computed(() => templates.value.length)
const isSearching = computed(() => Boolean(keyword.value.trim()))

const loadTemplates = async () => {
  loading.value = true
  loadError.value = false
  try {
    const response = await promptTemplateApi.getPromptTemplateRecycleBin(keyword.value.trim() || undefined)
    templates.value = response.data
  } catch (error) {
    loadError.value = true
    toast.error(error instanceof Error ? error.message : '加载回答方案回收站失败')
  } finally {
    loading.value = false
  }
}

const restore = async (template: PromptTemplate) => {
  actionId.value = template.id
  try {
    await promptTemplateApi.restorePromptTemplate(template.id)
    toast.success(template.status === 'PUBLISHED' ? '回答方案已恢复，仍保持已发布状态' : '回答方案已恢复为草稿')
    await loadTemplates()
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '恢复回答方案失败')
  } finally {
    actionId.value = null
  }
}

const purge = async (template: PromptTemplate) => {
  if (!confirm(`确定永久删除「${template.name}」吗？版本历史也会一并删除，无法恢复。`)) return
  actionId.value = template.id
  try {
    await promptTemplateApi.purgePromptTemplate(template.id)
    toast.success('回答方案已永久删除')
    await loadTemplates()
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '永久删除回答方案失败')
  } finally {
    actionId.value = null
  }
}

const getExpiryLabel = (template: PromptTemplate) =>
  template.recycleExpiresAt ? formatDateTime(template.recycleExpiresAt) : '等待系统自动清理'

onMounted(loadTemplates)
</script>

<template>
  <div class="space-y-6 pb-4">
    <section class="relative overflow-hidden rounded-2xl border border-border bg-card/80 shadow-[0_18px_45px_rgba(0,0,0,0.18)]">
      <div class="relative flex flex-col gap-5 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
        <div class="flex items-start gap-4">
          <Button variant="ghost" size="icon" class="mt-0.5 shrink-0" title="返回回答方案" @click="router.push('/builder/prompts')">
            <ArrowLeft class="h-5 w-5" />
          </Button>
          <div class="flex gap-4">
            <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-amber-400/25 bg-amber-400/10 text-amber-300">
              <Archive class="h-5 w-5" />
            </div>
            <div>
              <p class="text-xs font-medium tracking-[0.16em] text-amber-300/90">ANSWER PLAN RECOVERY</p>
              <h1 class="mt-1 text-2xl font-semibold tracking-tight">回答方案回收站</h1>
              <p class="mt-1 text-sm leading-6 text-muted-foreground">删除的回答方案会保留 7 天，可恢复或永久删除。</p>
            </div>
          </div>
        </div>
        <div class="shrink-0 rounded-full border border-amber-400/20 bg-amber-400/[0.06] px-3 py-1.5 text-sm text-amber-200">{{ total }} 个待处理方案</div>
      </div>
    </section>

    <div class="flex items-start gap-3 rounded-xl border border-amber-400/15 bg-amber-400/[0.04] p-4 text-sm leading-6 text-muted-foreground">
      <AlertTriangle class="mt-0.5 h-4 w-4 shrink-0 text-amber-300" />
      <p>恢复后会保留删除前的草稿或已发布状态；永久删除会连同版本历史一起清理，无法撤销。</p>
    </div>

    <Card class="border-border bg-card/80">
      <CardContent class="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:p-5">
        <div class="relative flex-1">
          <Search class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input v-model="keyword" class="pl-10" placeholder="搜索回收站中的回答方案" @keyup.enter="loadTemplates" />
        </div>
        <div class="flex gap-2">
          <Button v-if="isSearching" variant="ghost" @click="keyword = ''; loadTemplates()">清除</Button>
          <Button variant="outline" @click="loadTemplates">搜索</Button>
        </div>
      </CardContent>
    </Card>

    <Card class="overflow-hidden border-border bg-card/80">
      <CardContent class="p-4 sm:p-5">
        <div v-if="loading" class="flex min-h-64 flex-col items-center justify-center text-center text-muted-foreground">
          <Loader2 class="h-7 w-7 animate-spin text-primary" />
          <p class="mt-3 text-sm">正在加载回收站…</p>
        </div>
        <div v-else-if="loadError" class="flex min-h-64 flex-col items-center justify-center text-center">
          <AlertTriangle class="h-10 w-10 text-amber-300" />
          <p class="mt-4 font-medium">回收站暂时无法加载</p>
          <Button class="mt-4" variant="outline" @click="loadTemplates">重新加载</Button>
        </div>
        <div v-else-if="templates.length === 0" class="flex min-h-72 flex-col items-center justify-center text-center">
          <div class="flex h-14 w-14 items-center justify-center rounded-2xl bg-muted text-muted-foreground"><Archive class="h-7 w-7" /></div>
          <p class="mt-4 font-medium">{{ isSearching ? '没有找到匹配的回答方案' : '回收站是空的' }}</p>
          <p class="mt-1 max-w-sm text-sm leading-6 text-muted-foreground">{{ isSearching ? '换一个关键词，或清除搜索条件后再试。' : '删除的回答方案会暂时出现在这里，保留期内可以恢复。' }}</p>
          <Button v-if="isSearching" variant="outline" class="mt-4" @click="keyword = ''; loadTemplates()">清除搜索</Button>
          <Button v-else variant="outline" class="mt-4" @click="router.push('/builder/prompts')">返回回答方案</Button>
        </div>
        <div v-else class="space-y-3">
          <article v-for="template in templates" :key="template.id" class="rounded-xl border border-border bg-muted/20 p-4 transition-colors hover:border-amber-400/25 hover:bg-muted/40">
            <div class="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
              <div class="flex min-w-0 gap-3.5">
                <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-amber-400/10 text-amber-300"><FileText class="h-5 w-5" /></div>
                <div class="min-w-0">
                  <div class="flex flex-wrap items-center gap-2">
                    <h2 class="truncate font-medium">{{ template.name }}</h2>
                    <Badge variant="outline" class="border-amber-400/25 bg-amber-400/10 text-amber-200">回收站</Badge>
                    <Badge variant="outline" :class="template.status === 'PUBLISHED' ? 'border-emerald-400/25 bg-emerald-400/10 text-emerald-300' : 'border-violet-400/25 bg-violet-400/10 text-violet-200'">删除前：{{ template.status === 'PUBLISHED' ? '已发布' : '草稿' }}</Badge>
                  </div>
                  <p class="mt-1 line-clamp-2 text-sm text-muted-foreground">{{ template.description || '未填写适用场景' }}</p>
                  <div class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                    <span>版本 v{{ template.version }}</span>
                    <span>删除于 {{ formatDateTime(template.recycledAt || template.updatedAt) }}</span>
                    <span class="flex items-center gap-1"><Clock3 class="h-3.5 w-3.5" />保留至 {{ getExpiryLabel(template) }}</span>
                  </div>
                </div>
              </div>
              <div class="flex shrink-0 flex-wrap items-center gap-2 xl:justify-end">
                <Button variant="outline" size="sm" :disabled="actionId === template.id" @click="restore(template)"><Loader2 v-if="actionId === template.id" class="mr-1.5 h-3.5 w-3.5 animate-spin" /><RotateCcw v-else class="mr-1.5 h-3.5 w-3.5" />恢复方案</Button>
                <Button variant="ghost" size="sm" class="text-destructive hover:bg-rose-400/10 hover:text-destructive" :disabled="actionId === template.id" @click="purge(template)"><Trash2 class="mr-1.5 h-3.5 w-3.5" />永久删除</Button>
              </div>
            </div>
          </article>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
