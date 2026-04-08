<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
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
  const map: Record<string, string> = { local: '本地', git: 'Git', wheel: 'Wheel' }
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

onMounted(loadPlugins)
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold tracking-tight">插件管理</h1>
        <p class="text-sm text-muted-foreground">安装、启用、禁用工具插件，管理沙箱约束</p>
      </div>
      <Button @click="showInstallDialog = true" class="gap-2">
        <Download class="h-4 w-4" />
        安装插件
      </Button>
    </div>

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
      <p class="text-sm">点击"安装插件"按钮添加新插件</p>
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

    <!-- Install dialog -->
    <div v-if="showInstallDialog" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <Card class="w-full max-w-md">
        <CardHeader>
          <CardTitle>安装插件</CardTitle>
          <CardDescription>输入插件 manifest 信息</CardDescription>
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
    <div v-if="showReasonDialog" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
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
    <div v-if="showCanaryDialog" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
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
    <div v-if="showAuditDialog" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
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
