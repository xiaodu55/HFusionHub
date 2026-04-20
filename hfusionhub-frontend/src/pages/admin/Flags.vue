<script setup lang="ts">
import { computed, onMounted, ref, type Component } from 'vue'
import {
  Bot,
  CheckCircle2,
  GitBranch,
  Globe2,
  ListFilter,
  RefreshCw,
  Route,
  ShieldCheck,
  Sparkles,
  Users,
  Wrench,
} from 'lucide-vue-next'
import * as featureApi from '@/api/featureFlag'
import type { FeatureFlagInfo } from '@/api/featureFlag'
import { useToast } from '@/composables/useToast'
import { Button } from '@/components/ui/button'

type CapabilityGroup = 'retrieval' | 'agent' | 'safety'
type CapabilityStatus = 'stable' | 'experimental' | 'frozen'

interface CapabilityDefinition {
  key: string
  name: string
  group: CapabilityGroup
  status: CapabilityStatus
  summary: string
  useCase: string
  impact: string
  icon: Component
  dependsOn?: string
  confirmOnEnable?: string
}

const toast = useToast()
const loading = ref(false)
const savingKey = ref('')
const activeGroup = ref<'all' | CapabilityGroup>('all')
const serverFlags = ref<Record<string, FeatureFlagInfo>>({})

const capabilities: CapabilityDefinition[] = [
  { key: 'rag.hybrid.enabled', name: '混合检索', group: 'retrieval', status: 'stable', icon: Route, summary: '同时使用语义和关键词查找资料。', useCase: '大多数知识库问答', impact: '通常能提高命中率，建议保持开启。' },
  { key: 'rag.graph.enabled', name: '关系检索', group: 'retrieval', status: 'frozen', icon: GitBranch, summary: '根据人物、系统、规则之间的关系补充资料（已冻结：内存图、大数据集下收益不稳定）。', useCase: '制度、组织关系或系统依赖较复杂', impact: '检索更全面，但会略微增加处理时间。' },
  { key: 'rag.reranker.enabled', name: '结果精排', group: 'retrieval', status: 'experimental', icon: ListFilter, summary: '对检索结果再次排序，把更相关的内容放前面（建议仅使用内置 lexical 模式，cross_encoder 模式已冻结）。', useCase: '引用不够准确或资料较多', impact: '答案更精准，会增加少量计算时间。' },
  { key: 'agent.enabled', name: '复杂任务模式', group: 'agent', status: 'experimental', icon: Bot, summary: '为复杂任务增加超时、重试和执行追踪。', useCase: '需要多步骤分析的任务', impact: '成功率更高，但回答时间可能变长。' },
  { key: 'agent.multi_agent.enabled', name: '多角色协作', group: 'agent', status: 'frozen', icon: Users, summary: '让分析和校验角色共同完成复杂问题（已冻结：延迟收益不明确，暂不投入）。', useCase: '高复杂度、需要复核的任务', impact: '消耗更多模型用量，必须先开启复杂任务模式。', dependsOn: 'agent.enabled' },
  { key: 'agent.web_search.enabled', name: '联网搜索', group: 'agent', status: 'experimental', icon: Globe2, summary: '允许 AI 查询互联网上的最新信息（需在服务端配置搜索源）。', useCase: '知识库外的时效性问题', impact: '会使用外部来源，需要注意内容可信度。' },
  { key: 'agent.write_tools.enabled', name: '写入操作', group: 'safety', status: 'experimental', icon: Wrench, summary: '允许 AI 发起新增、修改等操作。', useCase: '希望 AI 协助执行实际操作', impact: '属于高风险能力，执行前仍需要人工确认。', confirmOnEnable: '开启后 AI 可以发起写入操作。确认继续开启吗？' },
  { key: 'approval.required_for_write', name: '操作前确认', group: 'safety', status: 'stable', icon: ShieldCheck, summary: '写入操作执行前必须由当前用户确认。', useCase: '所有启用写入能力的场景', impact: '建议始终开启，避免 AI 未经确认修改数据。' },
]

const groups = [
  { value: 'all' as const, label: '全部' },
  { value: 'retrieval' as const, label: '知识检索' },
  { value: 'agent' as const, label: 'Agent' },
  { value: 'safety' as const, label: '安全操作' },
]

const visibleCapabilities = computed(() => activeGroup.value === 'all'
  ? capabilities
  : capabilities.filter(item => item.group === activeGroup.value))
const enabledCount = computed(() => capabilities.filter(item => serverFlags.value[item.key]?.enabled).length)

const statusLabel = (status: CapabilityStatus) => ({ stable: '稳定', experimental: '实验', frozen: '冻结' }[status])
const statusClass = (status: CapabilityStatus) => ({
  stable: 'border-emerald-400/30 bg-emerald-400/[0.06] text-emerald-300',
  experimental: 'border-amber-400/30 bg-amber-400/[0.06] text-amber-300',
  frozen: 'border-zinc-500/40 bg-zinc-500/[0.08] text-zinc-400',
}[status])
const isEnabled = (key: string) => Boolean(serverFlags.value[key]?.enabled)
const isAvailable = (item: CapabilityDefinition) => Boolean(serverFlags.value[item.key])

async function loadFlags() {
  loading.value = true
  try {
    const response = await featureApi.listFeatureFlags()
    serverFlags.value = Object.fromEntries(response.data.map(flag => [flag.flagKey, flag]))
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '加载高级能力失败')
  } finally {
    loading.value = false
  }
}

async function setCapability(item: CapabilityDefinition, enabled: boolean) {
  const flag = serverFlags.value[item.key]
  if (!flag || savingKey.value) return
  if (enabled && item.dependsOn && !isEnabled(item.dependsOn)) {
    toast.error('请先开启“复杂任务模式”')
    return
  }
  if (enabled && item.confirmOnEnable && !window.confirm(item.confirmOnEnable)) return

  savingKey.value = item.key
  try {
    const response = await featureApi.updateFeatureFlag(flag.id, {
      enabled,
      reason: `在高级能力页面${enabled ? '开启' : '关闭'}${item.name}`,
    })
    serverFlags.value[item.key] = response.data
    toast.success(`${item.name}已${enabled ? '开启' : '关闭'}，最多 30 秒内生效`)
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '开关保存失败')
  } finally {
    savingKey.value = ''
  }
}

const presets = [
  { name: '日常问答', description: '速度优先，适合一般知识库', values: { 'rag.hybrid.enabled': true, 'rag.graph.enabled': false, 'rag.reranker.enabled': false, 'agent.enabled': false, 'agent.multi_agent.enabled': false } },
  { name: '精准检索', description: '适合资料多、关系复杂的知识库', values: { 'rag.hybrid.enabled': true, 'rag.graph.enabled': true, 'rag.reranker.enabled': true, 'agent.enabled': false, 'agent.multi_agent.enabled': false } },
  { name: '复杂任务', description: '适合多步骤分析，耗时和用量更高', values: { 'rag.hybrid.enabled': true, 'rag.graph.enabled': true, 'rag.reranker.enabled': true, 'agent.enabled': true, 'agent.multi_agent.enabled': false } },
]

async function applyPreset(preset: typeof presets[number]) {
  if (!window.confirm(`应用“${preset.name}”推荐组合？`)) return
  savingKey.value = 'preset'
  try {
    for (const [key, enabled] of Object.entries(preset.values)) {
      const flag = serverFlags.value[key]
      if (!flag || flag.enabled === enabled) continue
      const response = await featureApi.updateFeatureFlag(flag.id, {
        enabled,
        reason: `应用${preset.name}推荐组合`,
      })
      serverFlags.value[key] = response.data
    }
    toast.success(`已应用“${preset.name}”，最多 30 秒内生效`)
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '推荐组合应用失败')
  } finally {
    savingKey.value = ''
  }
}

onMounted(loadFlags)
</script>

<template>
  <div class="mx-auto max-w-6xl space-y-5 pb-8">
    <header class="flex flex-col gap-4 border-b border-border pb-5 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p class="text-sm font-medium text-primary">AI 能力开关</p>
        <h1 class="mt-1 text-2xl font-semibold">选择 AI 的工作方式</h1>
        <p class="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">直接开启或关闭，不需要修改配置文件。开关会保存到系统中，通常在 30 秒内应用到新请求。</p>
      </div>
      <div class="flex items-center gap-3">
        <span class="text-sm text-muted-foreground">已开启 {{ enabledCount }} / {{ capabilities.length }}</span>
        <Button variant="outline" class="gap-2" :disabled="loading" @click="loadFlags"><RefreshCw class="h-4 w-4" :class="loading && 'animate-spin'" />刷新</Button>
      </div>
    </header>

    <section aria-label="推荐组合" class="grid gap-3 md:grid-cols-3">
      <button v-for="preset in presets" :key="preset.name" class="flex items-start gap-3 rounded-lg border border-border bg-card/45 p-4 text-left transition-colors hover:border-primary/35 hover:bg-primary/[0.04]" :disabled="Boolean(savingKey)" @click="applyPreset(preset)">
        <Sparkles class="mt-0.5 h-4 w-4 shrink-0 text-primary" />
        <span><strong class="block text-sm font-medium">{{ preset.name }}</strong><span class="mt-1 block text-xs leading-5 text-muted-foreground">{{ preset.description }}</span></span>
      </button>
    </section>

    <div class="flex gap-1 overflow-x-auto border-b border-border pb-3">
      <button v-for="group in groups" :key="group.value" class="shrink-0 rounded-md px-3 py-2 text-sm" :class="activeGroup === group.value ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted hover:text-foreground'" @click="activeGroup = group.value">{{ group.label }}</button>
    </div>

    <div class="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-card/40 px-4 py-3 text-xs text-muted-foreground">
      <span class="flex items-center gap-1.5"><span class="rounded-full border border-emerald-400/30 bg-emerald-400/[0.06] px-2 py-0.5 text-emerald-300">稳定</span>已验证、默认推荐</span>
      <span class="flex items-center gap-1.5"><span class="rounded-full border border-amber-400/30 bg-amber-400/[0.06] px-2 py-0.5 text-amber-300">实验</span>可用，效果需实测</span>
      <span class="flex items-center gap-1.5"><span class="rounded-full border border-zinc-500/40 bg-zinc-500/[0.08] px-2 py-0.5 text-zinc-400">冻结</span>已停止投入，仅兼容保留</span>
    </div>

    <section class="divide-y divide-border overflow-hidden rounded-lg border border-border bg-card/40">
      <article v-for="item in visibleCapabilities" :key="item.key" class="grid gap-4 p-4 sm:grid-cols-[minmax(0,1fr)_13rem_auto] sm:items-center sm:p-5">
        <div class="flex min-w-0 gap-3">
          <div class="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-border bg-background text-primary"><component :is="item.icon" class="h-4 w-4" /></div>
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-2"><h2 class="font-medium">{{ item.name }}</h2><span class="rounded-full border px-2 py-0.5 text-[11px]" :class="statusClass(item.status)">{{ statusLabel(item.status) }}</span></div>
            <p class="mt-1 text-sm leading-6 text-muted-foreground">{{ item.summary }}</p>
          </div>
        </div>
        <div class="text-xs leading-5 text-muted-foreground"><p><span class="text-foreground/80">适合：</span>{{ item.useCase }}</p><p class="mt-1"><span class="text-foreground/80">影响：</span>{{ item.impact }}</p></div>
        <div class="flex items-center justify-between gap-3 sm:justify-end">
          <span class="text-xs" :class="isEnabled(item.key) ? 'text-emerald-400' : 'text-muted-foreground'">{{ !isAvailable(item) ? '不可用' : isEnabled(item.key) ? '已开启' : '已关闭' }}</span>
          <button
            type="button"
            role="switch"
            :aria-checked="isEnabled(item.key)"
            :aria-label="`${isEnabled(item.key) ? '关闭' : '开启'}${item.name}`"
            class="relative h-7 w-12 rounded-full border transition-colors disabled:cursor-not-allowed disabled:opacity-45"
            :class="isEnabled(item.key) ? 'border-primary bg-primary' : 'border-border bg-muted'"
            :disabled="!isAvailable(item) || Boolean(savingKey)"
            @click="setCapability(item, !isEnabled(item.key))"
          >
            <span class="absolute top-0.5 h-5 w-5 rounded-full bg-white shadow-sm transition-transform" :class="isEnabled(item.key) ? 'translate-x-5' : 'translate-x-0.5'" />
          </button>
        </div>
      </article>
    </section>

    <div class="flex gap-3 rounded-lg border border-emerald-400/20 bg-emerald-400/[0.05] p-4 text-sm leading-6 text-muted-foreground">
      <CheckCircle2 class="mt-1 h-4 w-4 shrink-0 text-emerald-400" />
      <p>建议从“日常问答”开始。只有在引用不准、关系知识较多或任务确实复杂时，再逐步开启增强能力。</p>
    </div>
  </div>
</template>
