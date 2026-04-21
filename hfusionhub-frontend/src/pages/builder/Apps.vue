<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Bot, KeyRound, Plus, Rocket, RefreshCw, Trash2, Unplug } from 'lucide-vue-next'
import * as appApi from '@/api/app'
import * as knowledgeBaseApi from '@/api/knowledgeBase'
import type { AppInfo, AppInput, AppApiKeyInfo } from '@/api/app'
import type { KnowledgeBase } from '@/api/types'
import { useToast } from '@/composables/useToast'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import LoadingSkeleton from '@/components/LoadingSkeleton.vue'

const toast = useToast()
const loading = ref(false)
const apps = ref<AppInfo[]>([])
const knowledgeBases = ref<KnowledgeBase[]>([])
const saving = ref(false)

const form = ref<AppInput & { id?: number }>({
  name: '',
  description: '',
  knowledgeBaseId: undefined,
  style: 'detailed',
})
const isEditDialogOpen = ref(false)
const isEditing = computed(() => form.value.id != null)

const styleOptions = [
  { label: '详细（段落级）', value: 'detailed' },
  { label: '简洁（≤200字）', value: 'concise' },
  { label: '报告（章节结构）', value: 'report' },
]

const statusLabel = (status: number) => ({ 0: '草稿', 1: '已发布', 2: '已停用' })[status] ?? '未知'
const styleLabel = (style?: string) =>
  ({ detailed: '详细', concise: '简洁', report: '报告' })[style || ''] || style || '默认'
const statusClass = (status: number) => ({
  0: 'border-zinc-500/40 bg-zinc-500/[0.08] text-zinc-300',
  1: 'border-emerald-400/30 bg-emerald-400/[0.06] text-emerald-300',
  2: 'border-amber-400/30 bg-amber-400/[0.06] text-amber-300',
}[status] ?? '')

async function load() {
  loading.value = true
  try {
    apps.value = (await appApi.listApps()).data
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '加载应用失败')
  } finally {
    loading.value = false
  }
}

async function loadKnowledgeBases() {
  try {
    const res = await knowledgeBaseApi.getMyKnowledgeBaseList({ page: 1, pageSize: 100 })
    knowledgeBases.value = res.data.records
  } catch (error) {
    console.error('加载知识库失败:', error)
  }
}

function openCreate() {
  form.value = { name: '', description: '', knowledgeBaseId: undefined, style: 'detailed' }
  isEditDialogOpen.value = true
}

function openEdit(app: AppInfo) {
  form.value = {
    id: app.id,
    name: app.name,
    description: app.description ?? '',
    knowledgeBaseId: app.knowledgeBaseId ?? undefined,
    style: app.style,
  }
  isEditDialogOpen.value = true
}

async function save() {
  if (!form.value.name.trim()) {
    toast.error('应用名称不能为空')
    return
  }
  saving.value = true
  try {
    const payload: AppInput = {
      name: form.value.name.trim(),
      description: form.value.description?.trim() || undefined,
      knowledgeBaseId: form.value.knowledgeBaseId,
      style: form.value.style,
    }
    if (isEditing.value) {
      await appApi.updateApp(form.value.id!, payload)
      toast.success('应用已更新')
    } else {
      await appApi.createApp(payload)
      toast.success('应用已创建')
    }
    isEditDialogOpen.value = false
    await load()
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '保存失败')
  } finally {
    saving.value = false
  }
}

async function publish(app: AppInfo) {
  try {
    await appApi.publishApp(app.id)
    toast.success('应用已发布')
    await load()
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '发布失败')
  }
}

async function unpublish(app: AppInfo) {
  try {
    await appApi.unpublishApp(app.id)
    toast.success('应用已撤回')
    await load()
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '撤回失败')
  }
}

async function remove(app: AppInfo) {
  if (!window.confirm(`确定删除应用「${app.name}」？其 API Key 将一并失效。`)) return
  try {
    await appApi.deleteApp(app.id)
    toast.success('应用已删除')
    await load()
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '删除失败')
  }
}

// ── API Key 管理 ────────────────────────────────────────────────────────

const keyDialogApp = ref<AppInfo | null>(null)
const keyName = ref('')
const keys = ref<AppApiKeyInfo[]>([])
const keysLoading = ref(false)
const creatingKey = ref(false)
const lastSecret = ref('')

async function openKeys(app: AppInfo) {
  keyDialogApp.value = app
  lastSecret.value = ''
  keyName.value = ''
  await loadKeys()
}

async function loadKeys() {
  if (!keyDialogApp.value) return
  keysLoading.value = true
  try {
    keys.value = (await appApi.listApiKeys(keyDialogApp.value.id)).data
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '加载 API Key 失败')
  } finally {
    keysLoading.value = false
  }
}

async function createKey() {
  if (!keyDialogApp.value) return
  creatingKey.value = true
  try {
    const result = await appApi.createApiKey(keyDialogApp.value.id, keyName.value.trim() || undefined)
    lastSecret.value = result.data.secret ?? ''
    toast.success('API Key 已创建，请立即复制保存（仅显示一次）')
    await loadKeys()
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '创建失败')
  } finally {
    creatingKey.value = false
  }
}

async function removeKey(keyId: number) {
  if (!keyDialogApp.value) return
  if (!window.confirm('确定删除该 API Key？使用它的调用将立即失败。')) return
  try {
    await appApi.deleteApiKey(keyDialogApp.value.id, keyId)
    toast.success('API Key 已删除')
    await loadKeys()
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '删除失败')
  }
}

function copySecret() {
  if (!lastSecret.value) return
  void navigator.clipboard.writeText(lastSecret.value)
  toast.success('已复制到剪贴板')
}

onMounted(() => {
  load()
  loadKnowledgeBases()
})
</script>

<template>
  <div class="mx-auto max-w-5xl space-y-6 p-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="flex items-center gap-2 text-xl font-semibold">
          <Bot class="h-5 w-5 text-emerald-300" />
          应用发布
        </h1>
        <p class="mt-1 text-sm text-muted-foreground">
          将「知识库 + 回答风格」打包为应用并发布，通过 API Key 供外部调用。
        </p>
      </div>
      <div class="flex items-center gap-2">
        <Button variant="outline" size="sm" @click="load"><RefreshCw class="mr-1.5 h-4 w-4" /> 刷新</Button>
        <Button size="sm" @click="openCreate"><Plus class="mr-1.5 h-4 w-4" /> 创建应用</Button>
      </div>
    </div>

    <Card>
      <CardHeader>
        <CardTitle class="text-base">我的应用</CardTitle>
        <CardDescription>共 {{ apps.length }} 个应用。</CardDescription>
      </CardHeader>
      <CardContent class="space-y-3">
        <LoadingSkeleton v-if="loading" type="card" :count="3" />
        <div v-else-if="!apps.length" class="py-10 text-center text-sm text-muted-foreground">
          还没有应用。创建一个应用并绑定知识库，即可发布为对外 API。
        </div>
        <article v-for="app in apps" :key="app.id" class="rounded-xl border border-border bg-muted/20 p-4">
          <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <h3 class="font-medium">{{ app.name }}</h3>
                <Badge :class="statusClass(app.status)">{{ statusLabel(app.status) }}</Badge>
              </div>
              <p v-if="app.description" class="mt-1 text-sm text-muted-foreground">{{ app.description }}</p>
              <div class="mt-2 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                <span>知识库：{{ app.knowledgeBaseName || '未绑定' }}</span>
                <span>风格：{{ styleLabel(app.style) }}</span>
                <span>API Key：{{ app.apiKeyCount }} 个</span>
              </div>
            </div>
            <div class="flex shrink-0 flex-wrap gap-2">
              <Button v-if="app.status === 0" size="sm" variant="outline" @click="publish(app)">
                <Rocket class="mr-1.5 h-4 w-4" /> 发布
              </Button>
              <Button v-else size="sm" variant="outline" @click="unpublish(app)">
                <Unplug class="mr-1.5 h-4 w-4" /> 撤回
              </Button>
              <Button size="sm" variant="outline" @click="openKeys(app)">
                <KeyRound class="mr-1.5 h-4 w-4" /> API Key
              </Button>
              <Button size="sm" variant="outline" @click="openEdit(app)">编辑</Button>
              <Button size="sm" variant="outline" class="text-rose-300" @click="remove(app)">
                <Trash2 class="h-4 w-4" />
              </Button>
            </div>
          </div>
        </article>
      </CardContent>
    </Card>

    <!-- 创建/编辑应用 -->
    <Dialog v-model:open="isEditDialogOpen">
      <DialogContent class="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{{ isEditing ? '编辑应用' : '创建应用' }}</DialogTitle>
          <DialogDescription>绑定知识库后发布，外部即可通过 API Key 调用。</DialogDescription>
        </DialogHeader>
        <div class="space-y-4 py-2">
          <div class="space-y-2">
            <Label>应用名称 *</Label>
            <Input v-model="form.name" placeholder="例如：客服助手" maxlength="200" />
          </div>
          <div class="space-y-2">
            <Label>应用描述</Label>
            <textarea
              v-model="form.description"
              rows="3"
              class="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-emerald-400/40"
              placeholder="说明这个应用用途…"
            />
          </div>
          <div class="space-y-2">
            <Label>绑定知识库</Label>
            <Select
              :model-value="form.knowledgeBaseId ?? ''"
              :options="knowledgeBases.filter(kb => kb.status === 0).map(kb => ({ label: kb.name, value: String(kb.id) }))"
              placeholder="请选择知识库"
              @update:model-value="(v: string) => (form.knowledgeBaseId = v ? Number(v) : undefined)"
            />
            <p class="text-xs text-muted-foreground">应用只能基于你拥有的知识库发布。</p>
          </div>
          <div class="space-y-2">
            <Label>回答风格</Label>
            <Select v-model="form.style" :options="styleOptions" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="isEditDialogOpen = false">取消</Button>
          <Button :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存' }}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- API Key 管理 -->
    <Dialog :open="keyDialogApp != null" @update:open="(v: boolean) => { if (!v) keyDialogApp = null }">
      <DialogContent class="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>API Key — {{ keyDialogApp?.name }}</DialogTitle>
          <DialogDescription>调用方式：<code class="rounded bg-muted px-1">Authorization: Bearer hf_xxx</code>，POST <code class="rounded bg-muted px-1">/openapi/chat</code>。</DialogDescription>
        </DialogHeader>

        <div v-if="lastSecret" class="rounded-lg border border-emerald-400/25 bg-emerald-400/[0.06] p-3">
          <p class="text-xs text-muted-foreground">新密钥（仅显示一次，请立即保存）：</p>
          <div class="mt-1 flex items-center gap-2">
            <code class="min-w-0 flex-1 break-all rounded bg-background px-2 py-1 font-mono text-xs">{{ lastSecret }}</code>
            <Button size="sm" variant="outline" @click="copySecret">复制</Button>
          </div>
        </div>

        <div class="flex items-end gap-2">
          <div class="flex-1 space-y-2">
            <Label>Key 名称（可选）</Label>
            <Input v-model="keyName" placeholder="例如：生产环境" />
          </div>
          <Button :disabled="creatingKey" @click="createKey">{{ creatingKey ? '创建中…' : '创建 Key' }}</Button>
        </div>

        <div class="space-y-2">
          <p v-if="keysLoading" class="py-4 text-center text-sm text-muted-foreground">正在加载…</p>
          <div v-else-if="!keys.length" class="py-4 text-center text-sm text-muted-foreground">还没有 API Key。</div>
          <article v-for="key in keys" :key="key.id" class="flex items-center justify-between rounded-lg border border-border bg-muted/20 px-3 py-2">
            <div class="min-w-0">
              <p class="text-sm font-medium">{{ key.name }}</p>
              <p class="font-mono text-xs text-muted-foreground">{{ key.keyPrefix }}****（创建于 {{ new Date(key.createdAt).toLocaleDateString('zh-CN') }}）</p>
            </div>
            <Button size="sm" variant="outline" class="text-rose-300" @click="removeKey(key.id)">
              <Trash2 class="h-4 w-4" />
            </Button>
          </article>
        </div>
      </DialogContent>
    </Dialog>
  </div>
</template>
