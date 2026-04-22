<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  AlertTriangle,
  CheckCircle2,
  CircleAlert,
  Clock,
  Download,
  Eye,
  EyeOff,
  GitBranch,
  LoaderCircle,
  Package,
  Plus,
  RefreshCw,
  ShieldCheck,
  ShieldOff,
  ShieldAlert,
  Trash2,
  Wrench,
  XCircle,
} from 'lucide-vue-next'
import * as pluginsApi from '@/api/plugins'
import type { PluginEntry, PluginAuditLog } from '@/api/plugins'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useToast } from '@/composables/useToast'

const toast = useToast()
const route = useRoute()

const plugins = ref<PluginEntry[]>([])
const loading = ref(false)
const error = ref('')
const statusFilter = ref('all')
const installing = ref(false)
const showInstallDialog = ref(false)
const installForm = ref({
  name: '',
  version: '',
  description: '',
  artifactHash: '',
})
const installFile = ref<File | null>(null)
const selectedPlugin = ref<PluginEntry | null>(null)
const auditLogs = ref<PluginAuditLog[]>([])
const auditLoading = ref(false)
const showAuditDialog = ref(false)
const confirmingAction = ref<string | null>(null)
const actionReason = ref('')
const showReasonDialog = ref(false)
const pendingActionPluginId = ref<string | null>(null)
const showCreateDialog = ref(false)
const creating = ref(false)

interface BuilderParameter {
  name: string
  description: string
  required: boolean
}

interface BuilderTool {
  name: string
  displayName: string
  description: string
  example: string
  endpointUrl: string
  timeoutSeconds: number
  parameters: BuilderParameter[]
}

const emptyBuilderTool = (): BuilderTool => ({
  name: 'custom_',
  displayName: '',
  description: '',
  example: '',
  endpointUrl: '',
  timeoutSeconds: 10,
  parameters: [{ name: 'query', description: '查询内容', required: true }],
})

const createForm = ref({
  name: '',
  displayName: '',
  version: '1.0.0',
  description: '',
  tools: [emptyBuilderTool()],
})

// ── Canary state ───────────────────────────────────────────────────
const showCanaryDialog = ref(false)
const canaryWeight = ref(0.1)
const canaryPluginId = ref<string | null>(null)

// ── Status helpers ───────────────────────────────────────────────────

const statusMeta = (status: string) => {
  const map: Record<string, { label: string; icon: typeof CheckCircle2; class: string }> = {
    active: { label: '运行中', icon: CheckCircle2, class: 'border-emerald-400/25 bg-emerald-400/10 text-emerald-300' },
    disabled: { label: '已禁用', icon: EyeOff, class: 'border-slate-400/25 bg-slate-400/10 text-slate-300' },
    failed: { label: '失败', icon: XCircle, class: 'border-red-400/25 bg-red-400/10 text-red-300' },
    pending: { label: '待激活', icon: Clock, class: 'border-amber-400/25 bg-amber-400/10 text-amber-200' },
    circuit_open: { label: '熔断', icon: ShieldAlert, class: 'border-orange-400/25 bg-orange-400/10 text-orange-300' },
  }
  return map[status] || { label: status, icon: AlertTriangle, class: 'border-border bg-muted text-muted-foreground' }
}

const vulnStatusMeta = (status: string | null) => {
  const map: Record<string, { label: string; class: string }> = {
    clean: { label: '安全', class: 'border-emerald-400/25 bg-emerald-400/10 text-emerald-300' },
    vulnerable: { label: '存在漏洞', class: 'border-red-400/25 bg-red-400/10 text-red-300' },
    pending: { label: '待扫描', class: 'border-amber-400/25 bg-amber-400/10 text-amber-200' },
    error: { label: '扫描失败', class: 'border-slate-400/25 bg-slate-400/10 text-slate-300' },
  }
  return map[status || 'pending'] || { label: status || '未知', class: 'border-border bg-muted text-muted-foreground' }
}

const sourceLabel = (source: string) => {
  const map: Record<string, string> = { local: '本地', git: 'Git', wheel: 'Wheel', builder: '网页创建' }
  return map[source] || source
}

const permLabel = (perm: string) => {
  try {
    const perms = JSON.parse(perm)
    if (Array.isArray(perms)) {
      const map: Record<string, string> = {
        'knowledge_base:read': '知识库读取',
        'knowledge_base:write': '知识库写入',
        'system:time': '系统时间',
        'external:http': '外部 HTTP',
      }
      return perms.map((p: string) => map[p] || p).join(', ')
    }
  } catch {}
  return perm || '无'
}

// ── Helpers ────────────────────────────────────────────────────────────

const computeFileSha256 = async (file: File): Promise<string> => {
  const buf = await file.arrayBuffer()
  const hashBuf = await crypto.subtle.digest('SHA-256', buf)
  return Array.from(new Uint8Array(hashBuf)).map(b => b.toString(16).padStart(2, '0')).join('')
}

const onInstallFileChange = async (e: Event) => {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  installFile.value = file
  installForm.value.artifactHash = '正在计算...'
  try {
    installForm.value.artifactHash = await computeFileSha256(file)
  } catch {
    installForm.value.artifactHash = ''
    error.value = '计算文件哈希失败'
  }
}

// ── Data fetching ─────────────────────────────────────────────────────

const loadPlugins = async () => {
  loading.value = true
  error.value = ''
  try {
    const res = await pluginsApi.listPlugins(1, 50, statusFilter.value === 'all' ? undefined : statusFilter.value)
    plugins.value = res.data.records || []
  } catch (e) {
    error.value = e instanceof Error ? e.message : '无法加载插件列表'
  } finally {
    loading.value = false
  }
}

const loadAuditLogs = async (pluginId: string) => {
  auditLoading.value = true
  try {
    const res = await pluginsApi.getPluginAuditLogs(pluginId, 20)
    auditLogs.value = res.data || []
  } catch {
    auditLogs.value = []
  } finally {
    auditLoading.value = false
  }
}

// ── Actions ───────────────────────────────────────────────────────────

const handleInstall = async () => {
  if (!installForm.value.name || !installForm.value.version || !installForm.value.artifactHash) return
  installing.value = true
  try {
    const manifest = {
      name: installForm.value.name,
      version: installForm.value.version,
      description: installForm.value.description,
      artifact_hash: installForm.value.artifactHash,
    }
    // 如果有选择 wheel 文件，则走 multipart 上传路径
    if (installFile.value) {
      await pluginsApi.installPluginWithWheel(manifest, installFile.value)
    } else {
      await pluginsApi.installPlugin(manifest)
    }
    showInstallDialog.value = false
    installForm.value = { name: '', version: '', description: '', artifactHash: '' }
    installFile.value = null
    await loadPlugins()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '安装失败'
  } finally {
    installing.value = false
  }
}

const addBuilderTool = () => {
  if (createForm.value.tools.length < 10) createForm.value.tools.push(emptyBuilderTool())
}

const removeBuilderTool = (index: number) => {
  if (createForm.value.tools.length > 1) createForm.value.tools.splice(index, 1)
}

const addBuilderParameter = (tool: BuilderTool) => {
  if (tool.parameters.length < 12) tool.parameters.push({ name: '', description: '', required: false })
}

const removeBuilderParameter = (tool: BuilderTool, index: number) => {
  tool.parameters.splice(index, 1)
}

const applyWeatherExample = () => {
  createForm.value = {
    name: 'weather_helper',
    displayName: '天气查询助手',
    version: '1.0.0',
    description: '让 AI 根据经纬度查询实时天气。',
    tools: [{
      name: 'custom_weather',
      displayName: '查询实时天气',
      description: '根据经纬度获取当前位置的实时天气数据。',
      example: '查询北京当前位置的实时天气。',
      endpointUrl: 'https://api.open-meteo.com/v1/forecast',
      timeoutSeconds: 10,
      parameters: [
        { name: 'latitude', description: '纬度，例如 39.9042', required: true },
        { name: 'longitude', description: '经度，例如 116.4074', required: true },
        { name: 'current', description: '要返回的天气字段，例如 temperature_2m', required: true },
      ],
    }],
  }
}

const handleCreate = async () => {
  if (!createForm.value.name || !createForm.value.displayName || !createForm.value.description) {
    toast.warning('请先填写插件名称、标识和用途')
    return
  }
  creating.value = true
  try {
    await pluginsApi.createDeclarativePlugin({
      name: createForm.value.name.trim(),
      display_name: createForm.value.displayName.trim(),
      version: createForm.value.version.trim(),
      description: createForm.value.description.trim(),
      tools: createForm.value.tools.map(tool => {
        const properties: Record<string, { type: 'string'; description: string }> = {}
        const required: string[] = []
        for (const parameter of tool.parameters) {
          const name = parameter.name.trim()
          if (!name) continue
          properties[name] = { type: 'string', description: parameter.description.trim() }
          if (parameter.required) required.push(name)
        }
        return {
          name: tool.name.trim(),
          display_name: tool.displayName.trim(),
          description: tool.description.trim(),
          example: tool.example.trim(),
          endpoint_url: tool.endpointUrl.trim(),
          method: 'GET' as const,
          timeout_seconds: tool.timeoutSeconds,
          input_schema: { type: 'object' as const, properties, required },
        }
      }),
    })
    showCreateDialog.value = false
    createForm.value = { name: '', displayName: '', version: '1.0.0', description: '', tools: [emptyBuilderTool()] }
    toast.success('插件已创建并启用，工具会自动出现在 AI 能力中心')
    await loadPlugins()
  } catch (e) {
    toast.error(e instanceof Error ? e.message : '创建插件失败')
  } finally {
    creating.value = false
  }
}

const pluginToolCount = (plugin: PluginEntry) => {
  if (!plugin.toolSpecsJson) return 0
  try {
    const tools = JSON.parse(plugin.toolSpecsJson)
    return Array.isArray(tools) ? tools.length : 0
  } catch {
    return 0
  }
}

const handleEnable = async (pluginId: string) => {
  try {
    await pluginsApi.enablePlugin(pluginId)
    await loadPlugins()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '启用失败'
  }
}

const handleDisable = (pluginId: string) => {
  pendingActionPluginId.value = pluginId
  actionReason.value = ''
  showReasonDialog.value = true
}

const confirmDisable = async () => {
  if (!pendingActionPluginId.value) return
  try {
    await pluginsApi.disablePlugin(pendingActionPluginId.value, actionReason.value || undefined)
    showReasonDialog.value = false
    pendingActionPluginId.value = null
    await loadPlugins()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '禁用失败'
  }
}

const handleUninstall = (pluginId: string) => {
  pendingActionPluginId.value = pluginId
  actionReason.value = ''
  confirmingAction.value = 'uninstall'
  showReasonDialog.value = true
}

const confirmUninstall = async () => {
  if (!pendingActionPluginId.value) return
  try {
    await pluginsApi.uninstallPlugin(pendingActionPluginId.value, actionReason.value || undefined)
    showReasonDialog.value = false
    pendingActionPluginId.value = null
    confirmingAction.value = null
    await loadPlugins()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '卸载失败'
  }
}

const showAudit = async (plugin: PluginEntry) => {
  selectedPlugin.value = plugin
  showAuditDialog.value = true
  await loadAuditLogs(plugin.pluginId)
}

const closeReasonDialog = () => {
  showReasonDialog.value = false
  pendingActionPluginId.value = null
  confirmingAction.value = null
}

// ── Canary actions ──────────────────────────────────────────────────

const openCanaryDialog = (plugin: PluginEntry) => {
  canaryPluginId.value = plugin.pluginId
  canaryWeight.value = (plugin.canaryWeight as number) || 0.1
  showCanaryDialog.value = true
}

const handleSetCanary = async () => {
  if (!canaryPluginId.value) return
  try {
    await pluginsApi.setCanary(canaryPluginId.value, canaryWeight.value)
    showCanaryDialog.value = false
    await loadPlugins()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '设置金丝雀失败'
  }
}

const handlePromoteCanary = async (pluginId: string) => {
  try {
    await pluginsApi.promoteCanary(pluginId)
    await loadPlugins()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '提升失败'
  }
}

const handleRollback = async (pluginId: string) => {
  try {
    await pluginsApi.rollbackPlugin(pluginId)
    await loadPlugins()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '回滚失败'
  }
}

// ── Computed ──────────────────────────────────────────────────────────

const filteredPlugins = computed(() => {
  if (statusFilter.value === 'all') return plugins.value
  return plugins.value.filter(p => p.status === statusFilter.value)
})

const statusCounts = computed(() => {
  const counts = { all: plugins.value.length, active: 0, disabled: 0, failed: 0, pending: 0 }
  for (const p of plugins.value) {
    if (p.status in counts) counts[p.status as keyof typeof counts]++
  }
  return counts
})

// ── Init ──────────────────────────────────────────────────────────────

// ESC 关闭当前打开的弹窗（a11y）
const closeDialogOnEscape = (event: KeyboardEvent) => {
  if (event.key !== 'Escape') return
  if (showCreateDialog.value) showCreateDialog.value = false
  else if (showInstallDialog.value) showInstallDialog.value = false
  else if (showReasonDialog.value) showReasonDialog.value = false
  else if (showCanaryDialog.value) showCanaryDialog.value = false
  else if (showAuditDialog.value) showAuditDialog.value = false
}

onMounted(async () => {
  await loadPlugins()
  if (route.query.create === 'tool') showCreateDialog.value = true
  document.addEventListener('keydown', closeDialogOnEscape)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', closeDialogOnEscape)
})
</script>

<template>
  <div class="space-y-6">
    <section class="rounded-lg border border-border bg-card/75 p-5 sm:p-6">
      <div class="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
        <div class="flex gap-4">
          <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-primary/25 bg-primary/10 text-primary">
            <Package class="h-5 w-5" />
          </div>
          <div>
            <p class="text-xs font-medium text-primary">AI 扩展</p>
            <h1 class="mt-1 text-2xl font-semibold">插件与工具</h1>
            <p class="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
              把外部 API 变成 AI 可以自动使用的工具。一个插件可以包含多个工具，并统一启用、禁用和审计。
            </p>
          </div>
        </div>
        <div class="flex shrink-0 flex-wrap gap-2">
          <Button variant="outline" class="gap-2" @click="showInstallDialog = true">
            <Download class="h-4 w-4" />
            上传插件包
          </Button>
          <Button class="gap-2" @click="showCreateDialog = true">
            <Plus class="h-4 w-4" />
            新建插件
          </Button>
        </div>
      </div>
      <div class="mt-5 grid gap-3 border-t border-border pt-5 sm:grid-cols-3">
        <div><p class="text-sm font-medium">1. 创建插件</p><p class="mt-1 text-xs text-muted-foreground">填写插件名称和用途。</p></div>
        <div><p class="text-sm font-medium">2. 添加工具</p><p class="mt-1 text-xs text-muted-foreground">配置 HTTPS GET 接口和输入参数。</p></div>
        <div><p class="text-sm font-medium">3. 在对话中使用</p><p class="mt-1 text-xs text-muted-foreground">启用后 AI 会根据问题自动调用。</p></div>
      </div>
    </section>

    <!-- Status filter tabs -->
    <div class="flex gap-2">
      <Button
        v-for="tab in (['all', 'active', 'disabled', 'failed', 'pending'] as const)"
        :key="tab"
        :variant="statusFilter === tab ? 'default' : 'outline'"
        size="sm"
        @click="statusFilter = tab"
        class="gap-1"
      >
        {{ statusCounts[tab] }}
        {{ tab === 'all' ? '全部' : statusMeta(tab).label }}
      </Button>
    </div>

    <!-- Error banner -->
    <div v-if="error" class="flex items-center gap-2 rounded-md border border-red-400/25 bg-red-400/10 p-3 text-sm text-red-200">
      <AlertTriangle class="h-4 w-4 shrink-0" />
      <span>{{ error }}</span>
      <Button variant="ghost" size="sm" @click="error = ''" class="ml-auto">关闭</Button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center py-12">
      <LoaderCircle class="h-6 w-6 animate-spin text-muted-foreground" />
    </div>

    <!-- Empty state -->
    <div v-else-if="filteredPlugins.length === 0" class="flex flex-col items-center justify-center py-12 text-muted-foreground">
      <Package class="h-12 w-12 mb-4 opacity-50" />
      <p class="text-lg font-medium">暂无插件</p>
      <p class="text-sm">点击“新建插件”从示例开始，或上传开发者制作的插件包。</p>
    </div>

    <!-- Plugin list -->
    <div v-else class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      <Card v-for="plugin in filteredPlugins" :key="plugin.pluginId" class="group relative">
        <CardHeader class="pb-3">
          <div class="flex items-start justify-between">
            <div class="flex-1 min-w-0">
              <CardTitle class="text-base truncate">{{ plugin.displayName || plugin.name }}</CardTitle>
              <CardDescription class="mt-1 text-xs">
                {{ plugin.name }}@{{ plugin.version }} &middot; {{ sourceLabel(plugin.source) }}
              </CardDescription>
            </div>
            <Badge :class="statusMeta(plugin.status).class" class="shrink-0 ml-2">
              <component :is="statusMeta(plugin.status).icon" class="h-3 w-3 mr-1" />
              {{ statusMeta(plugin.status).label }}
            </Badge>
          </div>
        </CardHeader>
        <CardContent class="space-y-3">
          <p v-if="plugin.description" class="text-sm text-muted-foreground line-clamp-2">
            {{ plugin.description }}
          </p>
          <div v-if="plugin.permissions" class="text-xs text-muted-foreground">
            <ShieldCheck class="inline h-3 w-3 mr-1" />
            {{ permLabel(plugin.permissions) }}
          </div>
          <div v-if="plugin.author" class="text-xs text-muted-foreground">
            作者: {{ plugin.author }}
          </div>
          <div v-if="plugin.pluginKind === 'declarative'" class="text-xs text-muted-foreground">
            包含 {{ pluginToolCount(plugin) }} 个自建工具
          </div>
          <div v-if="plugin.vulnerabilityStatus" class="text-xs">
            <Badge :class="vulnStatusMeta(plugin.vulnerabilityStatus).class">
              <ShieldCheck class="h-3 w-3 mr-1" />
              {{ vulnStatusMeta(plugin.vulnerabilityStatus).label }}
            </Badge>
          </div>
          <div v-if="plugin.canaryWeight && Number(plugin.canaryWeight) > 0" class="text-xs text-amber-300">
            金丝雀权重: {{ (Number(plugin.canaryWeight) * 100).toFixed(0) }}%
          </div>
          <div v-if="plugin.previousVersion" class="text-xs text-muted-foreground">
            <GitBranch class="inline h-3 w-3 mr-1" />
            上一版本: {{ plugin.previousVersion }}
          </div>
          <div class="flex flex-wrap gap-2 pt-2">
            <Button
              v-if="!plugin.enabled"
              size="sm"
              variant="outline"
              @click="handleEnable(plugin.pluginId)"
              class="gap-1"
            >
              <Eye class="h-3 w-3" />
              启用
            </Button>
            <Button
              v-else
              size="sm"
              variant="outline"
              @click="handleDisable(plugin.pluginId)"
              class="gap-1"
            >
              <EyeOff class="h-3 w-3" />
              禁用
            </Button>
            <Button
              size="sm"
              variant="outline"
              @click="openCanaryDialog(plugin)"
              class="gap-1"
            >
              <Wrench class="h-3 w-3" />
              金丝雀
            </Button>
            <Button
              v-if="plugin.previousVersion"
              size="sm"
              variant="outline"
              @click="handleRollback(plugin.pluginId)"
              class="gap-1"
            >
              <RefreshCw class="h-3 w-3" />
              回滚
            </Button>
            <Button
              size="sm"
              variant="outline"
              @click="showAudit(plugin)"
              class="gap-1"
            >
              <Clock class="h-3 w-3" />
              审计
            </Button>
            <Button
              size="sm"
              variant="outline"
              @click="handleUninstall(plugin.pluginId)"
              class="gap-1 text-red-400 hover:text-red-300"
            >
              <Trash2 class="h-3 w-3" />
              卸载
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>

    <!-- Low-code create dialog -->
    <div v-if="showCreateDialog" role="dialog" aria-modal="true" aria-label="新建插件" class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div class="flex max-h-[92vh] w-full max-w-4xl flex-col overflow-hidden rounded-lg border border-border bg-background shadow-2xl">
        <div class="flex items-start justify-between border-b border-border p-5">
          <div>
            <h2 class="text-lg font-semibold">新建插件</h2>
            <p class="mt-1 text-sm text-muted-foreground">无需写代码，把公开 HTTPS GET 接口配置成 AI 工具。</p>
          </div>
          <Button variant="ghost" size="sm" title="关闭" @click="showCreateDialog = false">
            <XCircle class="h-4 w-4" />
          </Button>
        </div>

        <div class="flex-1 space-y-6 overflow-y-auto p-5">
          <div class="flex items-center justify-between gap-3 rounded-md border border-primary/20 bg-primary/[0.04] p-4">
            <div>
              <p class="text-sm font-medium">第一次创建？</p>
              <p class="mt-1 text-xs text-muted-foreground">载入天气查询示例，修改后即可创建。</p>
            </div>
            <Button variant="outline" size="sm" @click="applyWeatherExample">使用示例</Button>
          </div>

          <section>
            <h3 class="text-sm font-semibold">插件信息</h3>
            <div class="mt-3 grid gap-4 sm:grid-cols-2">
              <label class="text-sm">显示名称 *
                <input v-model="createForm.displayName" placeholder="例如：天气查询助手" class="mt-1 block w-full rounded-md border border-input bg-background px-3 py-2" />
              </label>
              <label class="text-sm">插件标识 *
                <input v-model="createForm.name" placeholder="例如：weather_helper" class="mt-1 block w-full rounded-md border border-input bg-background px-3 py-2 font-mono" />
                <span class="mt-1 block text-xs text-muted-foreground">小写字母、数字、下划线，以字母开头。</span>
              </label>
              <label class="text-sm">版本 *
                <input v-model="createForm.version" placeholder="1.0.0" class="mt-1 block w-full rounded-md border border-input bg-background px-3 py-2" />
              </label>
              <label class="text-sm sm:col-span-2">用途说明 *
                <input v-model="createForm.description" placeholder="说明这个插件为用户解决什么问题" class="mt-1 block w-full rounded-md border border-input bg-background px-3 py-2" />
              </label>
            </div>
          </section>

          <section>
            <div class="flex items-center justify-between gap-3">
              <div>
                <h3 class="text-sm font-semibold">插件工具</h3>
                <p class="mt-1 text-xs text-muted-foreground">每个工具对应一个接口，AI 会根据名称、说明和示例判断何时调用。</p>
              </div>
              <Button variant="outline" size="sm" class="gap-1" :disabled="createForm.tools.length >= 10" @click="addBuilderTool">
                <Plus class="h-3.5 w-3.5" />添加工具
              </Button>
            </div>

            <div class="mt-3 space-y-4">
              <article v-for="(tool, toolIndex) in createForm.tools" :key="toolIndex" class="rounded-lg border border-border p-4">
                <div class="flex items-center justify-between">
                  <h4 class="text-sm font-medium">工具 {{ toolIndex + 1 }}</h4>
                  <Button v-if="createForm.tools.length > 1" variant="ghost" size="sm" title="删除工具" @click="removeBuilderTool(toolIndex)">
                    <Trash2 class="h-4 w-4 text-rose-300" />
                  </Button>
                </div>
                <div class="mt-3 grid gap-4 sm:grid-cols-2">
                  <label class="text-sm">工具名称 *
                    <input v-model="tool.displayName" placeholder="例如：查询实时天气" class="mt-1 block w-full rounded-md border border-input bg-background px-3 py-2" />
                  </label>
                  <label class="text-sm">工具标识 *
                    <input v-model="tool.name" placeholder="custom_weather" class="mt-1 block w-full rounded-md border border-input bg-background px-3 py-2 font-mono" />
                    <span class="mt-1 block text-xs text-muted-foreground">必须以 custom_ 开头。</span>
                  </label>
                  <label class="text-sm sm:col-span-2">接口地址 *
                    <input v-model="tool.endpointUrl" placeholder="https://api.example.com/search" class="mt-1 block w-full rounded-md border border-input bg-background px-3 py-2 font-mono" />
                    <span class="mt-1 block text-xs text-muted-foreground">仅支持公开 HTTPS GET，不允许本机、内网地址或跳转。</span>
                  </label>
                  <label class="text-sm sm:col-span-2">AI 何时使用 *
                    <input v-model="tool.description" placeholder="例如：用户询问天气时，根据经纬度查询实时天气" class="mt-1 block w-full rounded-md border border-input bg-background px-3 py-2" />
                  </label>
                  <label class="text-sm">示例问法
                    <input v-model="tool.example" placeholder="例如：查询北京现在的天气" class="mt-1 block w-full rounded-md border border-input bg-background px-3 py-2" />
                  </label>
                  <label class="text-sm">最长等待（秒）
                    <input v-model.number="tool.timeoutSeconds" type="number" min="2" max="30" class="mt-1 block w-full rounded-md border border-input bg-background px-3 py-2" />
                  </label>
                </div>

                <div class="mt-4 border-t border-border pt-4">
                  <div class="flex items-center justify-between">
                    <p class="text-xs font-medium text-muted-foreground">接口参数</p>
                    <Button variant="ghost" size="sm" class="gap-1" :disabled="tool.parameters.length >= 12" @click="addBuilderParameter(tool)">
                      <Plus class="h-3.5 w-3.5" />添加参数
                    </Button>
                  </div>
                  <div v-if="tool.parameters.length" class="mt-2 space-y-2">
                    <div v-for="(parameter, parameterIndex) in tool.parameters" :key="parameterIndex" class="grid gap-2 sm:grid-cols-[10rem_1fr_auto_auto] sm:items-center">
                      <input v-model="parameter.name" placeholder="参数标识" class="rounded-md border border-input bg-background px-3 py-2 text-sm font-mono" />
                      <input v-model="parameter.description" placeholder="告诉 AI 这个参数怎么填写" class="rounded-md border border-input bg-background px-3 py-2 text-sm" />
                      <label class="flex items-center gap-2 whitespace-nowrap text-xs text-muted-foreground"><input v-model="parameter.required" type="checkbox" />必填</label>
                      <button type="button" title="删除参数" class="p-2 text-muted-foreground hover:text-rose-300" @click="removeBuilderParameter(tool, parameterIndex)"><Trash2 class="h-4 w-4" /></button>
                    </div>
                  </div>
                  <p v-else class="mt-2 text-xs text-muted-foreground">这个接口不需要参数。</p>
                </div>
              </article>
            </div>
          </section>
        </div>

        <div class="flex justify-end gap-2 border-t border-border p-4">
          <Button variant="outline" @click="showCreateDialog = false">取消</Button>
          <Button :disabled="creating" class="gap-2" @click="handleCreate">
            <LoaderCircle v-if="creating" class="h-4 w-4 animate-spin" />
            创建并启用
          </Button>
        </div>
      </div>
    </div>

    <!-- Install dialog -->
    <div v-if="showInstallDialog" role="dialog" aria-modal="true" aria-label="安装插件" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <Card class="w-full max-w-md">
        <CardHeader>
          <CardTitle>上传插件包</CardTitle>
          <CardDescription>供开发者安装经过构建和校验的 Wheel 插件。</CardDescription>
        </CardHeader>
        <CardContent class="space-y-4">
          <div>
            <label class="text-sm font-medium">插件名称 *</label>
            <input
              v-model="installForm.name"
              placeholder="e.g. github_connector"
              class="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label class="text-sm font-medium">版本 (semver) *</label>
            <input
              v-model="installForm.version"
              placeholder="e.g. 1.0.0"
              class="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label class="text-sm font-medium">描述</label>
            <input
              v-model="installForm.description"
              placeholder="插件功能描述"
              class="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label class="text-sm font-medium">插件包 (.whl) *</label>
            <input
              type="file"
              accept=".whl,.zip"
              @change="onInstallFileChange"
              class="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm file:mr-2 file:rounded file:border-0 file:bg-primary file:px-2 file:py-0.5 file:text-xs file:text-primary-foreground"
            />
            <p v-if="installForm.artifactHash" class="mt-1 text-xs text-muted-foreground break-all">
              SHA-256: {{ installForm.artifactHash }}
            </p>
          </div>
          <div class="flex justify-end gap-2 pt-2">
            <Button variant="outline" @click="showInstallDialog = false">取消</Button>
            <Button @click="handleInstall" :disabled="installing || !installForm.name || !installForm.version || !installForm.artifactHash || installForm.artifactHash === '正在计算...'">
              <LoaderCircle v-if="installing" class="h-4 w-4 animate-spin mr-1" />
              安装
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>

    <!-- Reason dialog (disable / uninstall) -->
    <div v-if="showReasonDialog" role="dialog" aria-modal="true" aria-label="审批原因" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <Card class="w-full max-w-md">
        <CardHeader>
          <CardTitle>{{ confirmingAction === 'uninstall' ? '确认卸载' : '确认禁用' }}</CardTitle>
          <CardDescription>
            {{ confirmingAction === 'uninstall' ? '卸载后需重新安装才能使用' : '禁用后该插件将不再可用' }}
          </CardDescription>
        </CardHeader>
        <CardContent class="space-y-4">
          <div>
            <label class="text-sm font-medium">原因（可选）</label>
            <input
              v-model="actionReason"
              placeholder="操作原因"
              class="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            />
          </div>
          <div class="flex justify-end gap-2 pt-2">
            <Button variant="outline" @click="closeReasonDialog">取消</Button>
            <Button
              variant="destructive"
              @click="confirmingAction === 'uninstall' ? confirmUninstall() : confirmDisable()"
            >
              确认{{ confirmingAction === 'uninstall' ? '卸载' : '禁用' }}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>

    <!-- Canary dialog -->
    <div v-if="showCanaryDialog" role="dialog" aria-modal="true" aria-label="灰度发布" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <Card class="w-full max-w-md">
        <CardHeader>
          <CardTitle>设置金丝雀流量</CardTitle>
          <CardDescription>按用户 ID 稳定分流，同一用户始终访问同一版本</CardDescription>
        </CardHeader>
        <CardContent class="space-y-4">
          <div>
            <label class="text-sm font-medium">流量权重 (0-100%)</label>
            <input
              v-model.number="canaryWeight"
              type="range"
              min="0"
              max="1"
              step="0.05"
              class="mt-2 w-full"
            />
            <p class="text-xs text-muted-foreground mt-1">{{ (canaryWeight * 100).toFixed(0) }}% 流量将路由到金丝雀版本</p>
          </div>
          <div class="flex justify-end gap-2 pt-2">
            <Button variant="outline" @click="showCanaryDialog = false">取消</Button>
            <Button @click="handleSetCanary">确认设置</Button>
          </div>
        </CardContent>
      </Card>
    </div>

    <!-- Audit log dialog -->
    <div v-if="showAuditDialog" role="dialog" aria-modal="true" aria-label="审计日志" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <Card class="w-full max-w-2xl max-h-[80vh] overflow-hidden flex flex-col">
        <CardHeader>
          <div class="flex items-center justify-between">
            <div>
              <CardTitle>审计日志</CardTitle>
              <CardDescription>{{ selectedPlugin?.name }}@{{ selectedPlugin?.version }}</CardDescription>
            </div>
            <Button variant="ghost" size="sm" @click="showAuditDialog = false">
              <XCircle class="h-4 w-4" />
            </Button>
          </div>
        </CardHeader>
        <CardContent class="flex-1 overflow-auto">
          <div v-if="auditLoading" class="flex justify-center py-8">
            <LoaderCircle class="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
          <div v-else-if="auditLogs.length === 0" class="text-center py-8 text-muted-foreground text-sm">
            暂无审计记录
          </div>
          <div v-else class="space-y-3">
            <div
              v-for="log in auditLogs"
              :key="log.id"
              class="flex items-start gap-3 rounded-md border p-3 text-sm"
            >
              <Badge
                :class="{
                  'border-emerald-400/25 bg-emerald-400/10 text-emerald-300': log.action === 'install',
                  'border-cyan-400/25 bg-cyan-400/10 text-cyan-200': log.action === 'enable',
                  'border-amber-400/25 bg-amber-400/10 text-amber-200': log.action === 'disable',
                  'border-red-400/25 bg-red-400/10 text-red-300': log.action === 'uninstall',
                }"
                class="shrink-0"
              >
                {{ log.action }}
              </Badge>
              <div class="flex-1 min-w-0">
                <p class="text-muted-foreground">{{ log.reason || '无原因' }}</p>
                <p class="text-xs text-muted-foreground mt-1">
                  操作人 #{{ log.operatorId || '系统' }} &middot;
                  {{ new Date(log.createdAt).toLocaleString() }}
                </p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  </div>
</template>
