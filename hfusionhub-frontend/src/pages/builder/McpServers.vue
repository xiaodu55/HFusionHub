<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Cable, Pencil, Plus, RefreshCw, Trash2 } from 'lucide-vue-next'
import * as toolsApi from '@/api/tools'
import type { McpServerInfo } from '@/api/tools'
import { useToast } from '@/composables/useToast'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import LoadingSkeleton from '@/components/LoadingSkeleton.vue'
import EmptyState from '@/components/EmptyState.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'

const toast = useToast()
const loading = ref(false)
const servers = ref<McpServerInfo[]>([])
const adding = ref(false)
const addDialogOpen = ref(false)
const deleteTarget = ref<McpServerInfo | null>(null)
const confirmDeleteOpen = ref(false)
const confirmDeleteLoading = ref(false)

const form = ref({
  id: '',
  name: '',
  url: '',
  transport: 'sse' as 'sse' | 'streamable-http',
  api_key: '',
})
/** 编辑模式：id 固定不可改（add 接口按 id 覆盖更新） */
const editing = ref(false)

const transportOptions = [
  { label: 'SSE', value: 'sse' },
  { label: 'Streamable HTTP', value: 'streamable-http' },
]

/** 一键填入官方 MCP 服务器示例，可修改后再添加 */
function applyExample() {
  form.value = {
    id: 'notion',
    name: 'Notion MCP',
    url: 'https://mcp.notion.com/mcp',
    transport: 'streamable-http',
    api_key: '',
  }
  toast.success('已填入示例配置，可修改后添加')
}

/** 空状态 CTA：打开添加对话框并预填示例 */
function applyExampleAndOpen() {
  applyExample()
  addDialogOpen.value = true
}

const statusClass = (status: string) => ({
  connected: 'border-emerald-400/30 bg-emerald-400/[0.06] text-emerald-300',
  connecting: 'border-amber-400/30 bg-amber-400/[0.06] text-amber-300',
  error: 'border-rose-400/30 bg-rose-400/[0.06] text-rose-300',
  disconnected: 'border-zinc-500/40 bg-zinc-500/[0.08] text-zinc-300',
}[status] ?? '')

/** 把底层原始错误（如 HTTP 401 JSON）翻译成可操作的人话 */
function friendlyError(raw: string): string {
  if (!raw) return ''
  const statusMatch = raw.match(/HTTP\s+(\d{3})/i)
  const status = statusMatch ? statusMatch[1] : ''
  if (status === '401' || /invalid_token|unauthorized|missing.*token/i.test(raw))
    return '鉴权失败（401）：访问令牌缺失或无效。点击「编辑」填入该服务要求的 API Token'
  if (status === '404')
    return '服务地址不存在（404）：请检查 URL 是否正确（注意 SSE 与 Streamable HTTP 的路径差异）'
  if (status === '403')
    return '无访问权限（403）：令牌有效但权限不足，请检查该 Token 的授权范围'
  if (/timeout|timed out/i.test(raw))
    return '连接超时：服务无响应或网络不通，稍后可重试'
  if (status.startsWith('5'))
    return `服务端错误（${status}）：MCP 服务内部异常，稍后重试`
  try {
    const jsonStart = raw.indexOf('{')
    if (jsonStart >= 0) {
      const parsed = JSON.parse(raw.slice(jsonStart))
      return parsed.error_description || parsed.error || parsed.message || raw
    }
  } catch { /* 保留原文 */ }
  return raw
}

const statusLabel = (status: string) => ({
  connected: '已连接',
  connecting: '连接中',
  error: '连接失败',
  disconnected: '未连接',
}[status] ?? status)

async function load() {
  loading.value = true
  try {
    const response = await toolsApi.listMcpServers()
    servers.value = response.data.servers ?? []
    if (response.data.error) {
      toast.error(response.data.error)
    }
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '加载 MCP 服务失败')
  } finally {
    loading.value = false
  }
}

async function add() {
  if (!form.value.id.trim() || !form.value.url.trim()) {
    toast.error('服务 ID 与地址不能为空')
    return
  }
  adding.value = true
  try {
    const response = await toolsApi.addMcpServer({
      id: form.value.id.trim(),
      name: form.value.name.trim() || form.value.id.trim(),
      url: form.value.url.trim(),
      transport: form.value.transport,
      api_key: form.value.api_key.trim() || undefined,
    })
    if (response.data.success) {
      toast.success(editing.value ? '已更新并重新连接' : (response.data.message ?? '已添加'))
      form.value = { id: '', name: '', url: '', transport: 'sse', api_key: '' }
      editing.value = false
      addDialogOpen.value = false
    } else {
      toast.error(response.data.message ?? '添加失败')
    }
    await load()
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '添加失败')
  } finally {
    adding.value = false
  }
}

async function reconnect(server: McpServerInfo) {
  try {
    const response = await toolsApi.reconnectMcpServer(server.id)
    if (response.data.success) {
      toast.success(response.data.message ?? '已重新连接')
    } else {
      toast.error(response.data.message ?? '重连失败')
    }
    await load()
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '重连失败')
  }
}

function openEdit(server: McpServerInfo) {
  editing.value = true
  form.value = {
    id: server.id,
    name: server.name,
    url: server.url,
    transport: (server.transport as 'sse' | 'streamable-http') || 'sse',
    api_key: '',
  }
  addDialogOpen.value = true
}

function remove(server: McpServerInfo) {
  deleteTarget.value = server
  confirmDeleteOpen.value = true
}

async function confirmDelete() {
  const server = deleteTarget.value
  if (!server) return
  confirmDeleteLoading.value = true
  try {
    await toolsApi.removeMcpServer(server.id)
    toast.success('已移除')
    await load()
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '移除失败')
  } finally {
    confirmDeleteLoading.value = false
    confirmDeleteOpen.value = false
    deleteTarget.value = null
  }
}

onMounted(load)
</script>

<template>
  <div class="mx-auto max-w-4xl space-y-6 p-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="flex items-center gap-2 text-xl font-semibold">
          <Cable class="h-5 w-5 text-emerald-300" />
          MCP 服务
        </h1>
        <p class="mt-1 text-sm text-muted-foreground">
          注册外部 Model Context Protocol 服务器，其工具可作为 AI 能力使用（external 风险级，执行前需审批）。
        </p>
      </div>
      <div class="flex items-center gap-2">
        <Button variant="outline" size="sm" @click="load"><RefreshCw class="mr-1.5 h-4 w-4" /> 刷新</Button>
        <Dialog v-model:open="addDialogOpen">
          <DialogTrigger as-child>
            <Button size="sm"><Plus class="mr-1.5 h-4 w-4" /> 添加服务</Button>
          </DialogTrigger>
          <DialogContent class="sm:max-w-lg">
            <DialogHeader>
              <DialogTitle>{{ editing ? '编辑 MCP 服务器' : '添加 MCP 服务器' }}</DialogTitle>
              <DialogDescription>服务器需实现 MCP 协议并暴露 /tools/list 与 /tools/call 端点。Notion / GitHub 等官方服务通常需要在其后台生成 API Token 填入下方「API Key」。</DialogDescription>
            </DialogHeader>
            <div class="space-y-4 py-2">
              <div class="grid grid-cols-2 gap-4">
                <div class="space-y-2">
                  <Label>服务 ID *</Label>
                  <Input v-model="form.id" placeholder="例如 notion" :disabled="editing" />
                </div>
                <div class="space-y-2">
                  <Label>显示名称</Label>
                  <Input v-model="form.name" placeholder="例如 Notion" />
                </div>
              </div>
              <div class="space-y-2">
                <Label>服务器地址 *</Label>
                <Input v-model="form.url" placeholder="https://mcp.example.com/sse" />
              </div>
              <div class="grid grid-cols-2 gap-4">
                <div class="space-y-2">
                  <Label>传输协议</Label>
                  <Select v-model="form.transport" :options="transportOptions" />
                </div>
                <div class="space-y-2">
                  <Label>API Key（可选）</Label>
                  <Input v-model="form.api_key" type="password" placeholder="服务器需要鉴权时填写" />
                </div>
              </div>
            </div>
            <DialogFooter>
              <Button v-if="!editing" variant="outline" :disabled="adding" @click="applyExample">填入示例</Button>
              <Button :disabled="adding" @click="add">{{ adding ? '保存中…' : (editing ? '保存并重连' : '添加并连接') }}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </div>

    <Card>
      <CardHeader>
        <CardTitle class="text-base">已注册服务</CardTitle>
        <CardDescription>共 {{ servers.length }} 个。配置保存在 AI 服务端，重启后保留。</CardDescription>
      </CardHeader>
      <CardContent class="space-y-3">
        <LoadingSkeleton v-if="loading" type="card" :count="3" />
        <EmptyState
          v-else-if="!servers.length"
          :icon="Cable"
          title="还没有 MCP 服务"
          description="MCP 让 AI 连接外部工具（如 Notion、GitHub）。可用「填入示例」快速开始，或通过环境变量 MCP_SERVERS_CONFIG 配置。"
          action="填入示例配置"
          show-action
          @action="applyExampleAndOpen"
        />
        <article v-for="server in servers" :key="server.id" class="rounded-xl border border-border bg-muted/20 p-4 transition-colors hover:border-primary/25">
          <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <h3 class="font-medium">{{ server.name }}</h3>
                <span class="rounded-full border px-2 py-0.5 text-[11px]" :class="statusClass(server.status)">
                  {{ statusLabel(server.status) }}
                </span>
                <span class="rounded-full border px-2 py-0.5 text-[11px] text-muted-foreground">{{ server.transport }}</span>
              </div>
              <p class="mt-1 break-all font-mono text-xs text-muted-foreground">{{ server.url }}</p>
              <p class="mt-1 text-xs text-muted-foreground">工具数：{{ server.tool_count }}</p>
              <div v-if="server.error_message" class="mt-2 rounded-lg border border-rose-400/20 bg-rose-400/[0.06] p-2.5">
                <p class="text-xs leading-5 text-rose-700 dark:text-rose-300">{{ friendlyError(server.error_message) }}</p>
              </div>
            </div>
            <div class="flex shrink-0 gap-2">
              <Button size="sm" variant="outline" @click="reconnect(server)"><RefreshCw class="mr-1.5 h-3.5 w-3.5" />重连</Button>
              <Button size="sm" variant="outline" @click="openEdit(server)"><Pencil class="mr-1.5 h-3.5 w-3.5" />编辑</Button>
              <Button size="sm" variant="outline" class="text-rose-300" @click="remove(server)">
                <Trash2 class="h-4 w-4" />
              </Button>
            </div>
          </div>
        </article>
      </CardContent>
    </Card>

    <ConfirmDialog
      v-model:open="confirmDeleteOpen"
      title="移除确认"
      :description="`确定移除 MCP 服务「${deleteTarget?.name}」？`"
      confirm-text="移除"
      destructive
      :loading="confirmDeleteLoading"
      @confirm="confirmDelete"
    />
  </div>
</template>
