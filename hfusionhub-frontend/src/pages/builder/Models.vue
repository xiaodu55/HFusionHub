<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  Activity,
  BrainCircuit,
  CheckCircle2,
  CircleAlert,
  Cloud,
  Cpu,
  Database,
  Eye,
  EyeOff,
  KeyRound,
  LoaderCircle,
  RefreshCw,
  RotateCcw,
  Save,
  Server,
  ShieldCheck,
  TestTube2,
  TriangleAlert,
} from 'lucide-vue-next'
import * as systemApi from '@/api/system'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useToast } from '@/composables/useToast'

const toast = useToast()
const runtime = ref<systemApi.AiRuntimeOverview | null>(null)
const savedConfig = ref<systemApi.UserModelConfig | null>(null)
const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const resetting = ref(false)
const showApiKey = ref(false)
const error = ref('')
const testResult = ref<systemApi.ProviderTestResult | null>(null)

const form = ref<systemApi.UserModelConfigSave>({
  providerType: 'openai_compatible',
  providerName: 'DeepSeek',
  baseUrl: 'https://api.deepseek.com',
  modelName: 'deepseek-v4-flash',
  apiKey: '',
  enabled: true,
})

const presets = [
  {
    id: 'deepseek',
    label: 'DeepSeek',
    description: '使用 DeepSeek 云端 API',
    providerType: 'openai_compatible' as const,
    providerName: 'DeepSeek',
    baseUrl: 'https://api.deepseek.com',
    modelName: 'deepseek-v4-flash',
  },
  {
    id: 'ollama',
    label: 'Ollama',
    description: '使用本机或内网模型',
    providerType: 'ollama' as const,
    providerName: 'Ollama',
    baseUrl: 'http://localhost:11434',
    modelName: 'qwen2.5:3b',
  },
  {
    id: 'custom',
    label: '其他兼容供应商',
    description: '任何 OpenAI Chat Completions 兼容接口',
    providerType: 'openai_compatible' as const,
    providerName: '自定义供应商',
    baseUrl: '',
    modelName: '',
  },
]

const selectedPreset = computed(() => {
  if (form.value.providerType === 'ollama') return 'ollama'
  if (form.value.providerName === 'DeepSeek' && form.value.baseUrl.includes('api.deepseek.com')) return 'deepseek'
  return 'custom'
})

const needsApiKey = computed(() => form.value.providerType !== 'ollama')
const canSubmit = computed(() =>
  form.value.providerName.trim().length > 0
  && form.value.baseUrl.trim().length > 0
  && form.value.modelName.trim().length > 0
  && (!needsApiKey.value || Boolean(form.value.apiKey?.trim()) || Boolean(savedConfig.value?.apiKeyConfigured)),
)

const usingPersonalModel = computed(() => Boolean(savedConfig.value?.configured && savedConfig.value.enabled))
const effectiveModel = computed(() => usingPersonalModel.value
  ? savedConfig.value?.modelName
  : runtime.value?.llm?.model)
const effectiveProvider = computed(() => usingPersonalModel.value
  ? savedConfig.value?.providerName
  : runtime.value?.llm?.provider_label)

const featureItems = computed(() => {
  const features = runtime.value?.features
  if (!features) return []
  return [
    { name: '混合检索', detail: '向量与关键词结果融合', enabled: features.hybrid_retrieval },
    { name: '图谱检索', detail: '补充实体关系检索', enabled: features.graph_retrieval },
    { name: '结果重排', detail: features.reranker === 'disabled' ? '当前未启用' : `当前模式：${features.reranker}`, enabled: features.reranker !== 'disabled' },
    { name: 'Agent 工作流', detail: '支持工具调用与执行边界', enabled: features.agent_workflow },
  ]
})

const applySavedConfig = (config: systemApi.UserModelConfig) => {
  savedConfig.value = config
  if (!config.configured || config.providerType === 'system') return
  form.value = {
    providerType: config.providerType,
    providerName: config.providerName,
    baseUrl: config.baseUrl || '',
    modelName: config.modelName || '',
    apiKey: '',
    enabled: config.enabled,
  }
}

const loadPage = async () => {
  loading.value = true
  error.value = ''
  try {
    const [runtimeResponse, configResponse] = await Promise.all([
      systemApi.getAiRuntimeOverview(),
      systemApi.getUserModelConfig(),
    ])
    runtime.value = runtimeResponse.data
    applySavedConfig(configResponse.data)
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : '暂时无法读取模型配置'
  } finally {
    loading.value = false
  }
}

const applyPreset = (preset: (typeof presets)[number]) => {
  form.value = {
    providerType: preset.providerType,
    providerName: preset.providerName,
    baseUrl: preset.baseUrl,
    modelName: preset.modelName,
    apiKey: '',
    enabled: true,
  }
  testResult.value = null
}

const testConnection = async () => {
  if (!canSubmit.value) return
  testing.value = true
  testResult.value = null
  try {
    const response = await systemApi.testUserModelConfig(form.value)
    testResult.value = response.data
    if (response.data.success) toast.success(`连接成功：${response.data.model || form.value.modelName}`)
    else toast.error(response.data.message || '连接失败')
  } catch (requestError) {
    const message = requestError instanceof Error ? requestError.message : '连接测试失败'
    testResult.value = { success: false, message }
    toast.error(message)
  } finally {
    testing.value = false
  }
}

const saveConfig = async () => {
  if (!canSubmit.value) return
  saving.value = true
  try {
    const response = await systemApi.saveUserModelConfig(form.value)
    applySavedConfig(response.data)
    toast.success('已保存，新对话和回答测试将使用这个模型')
  } catch (requestError) {
    toast.error(requestError instanceof Error ? requestError.message : '保存模型配置失败')
  } finally {
    saving.value = false
  }
}

const resetToSystem = async () => {
  if (!confirm('确定恢复系统默认模型？已保存的个人 API Key 将被删除。')) return
  resetting.value = true
  try {
    await systemApi.resetUserModelConfig()
    savedConfig.value = null
    applyPreset(presets[0])
    toast.success('已恢复系统默认模型')
    await loadPage()
  } catch (requestError) {
    toast.error(requestError instanceof Error ? requestError.message : '恢复系统默认失败')
  } finally {
    resetting.value = false
  }
}

onMounted(loadPage)
</script>

<template>
  <div class="space-y-6 pb-4">
    <section class="rounded-xl border border-border bg-card/80 shadow-[0_18px_45px_rgba(0,0,0,0.18)]">
      <div class="flex flex-col gap-5 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
        <div class="flex gap-4">
          <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-cyan-400/25 bg-cyan-400/10 text-cyan-200"><Cpu class="h-5 w-5" /></div>
          <div>
            <p class="text-xs font-medium text-cyan-200">模型设置</p>
            <h1 class="mt-1 text-2xl font-semibold">我的模型</h1>
            <p class="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">填写自己的供应商、API Key、Base URL 和模型名称。保存后，你的对话和回答测试会优先使用它。</p>
          </div>
        </div>
        <Button variant="outline" :disabled="loading" class="gap-2" @click="loadPage"><LoaderCircle v-if="loading" class="h-4 w-4 animate-spin" /><RefreshCw v-else class="h-4 w-4" />刷新</Button>
      </div>
    </section>

    <div v-if="error" class="flex items-start gap-3 rounded-lg border border-rose-400/20 bg-rose-400/[0.06] p-4 text-sm text-rose-100"><CircleAlert class="mt-0.5 h-4 w-4 shrink-0" /><div><p class="font-medium">无法读取模型配置</p><p class="mt-1">{{ error }}</p></div></div>

    <template v-else>
      <section class="grid gap-3 lg:grid-cols-3">
        <article class="rounded-lg border border-border bg-card/70 p-4"><div class="flex items-center justify-between gap-3"><span class="text-sm text-muted-foreground">当前对话模型</span><Cloud class="h-4 w-4 text-cyan-200" /></div><p class="mt-3 truncate text-lg font-semibold">{{ effectiveModel || '尚未就绪' }}</p><p class="mt-1 text-xs text-muted-foreground">{{ effectiveProvider || '未配置' }} · {{ usingPersonalModel ? '我的配置' : '系统默认' }}</p></article>
        <article class="rounded-lg border border-border bg-card/70 p-4"><div class="flex items-center justify-between gap-3"><span class="text-sm text-muted-foreground">文档向量模型</span><BrainCircuit class="h-4 w-4 text-violet-200" /></div><p class="mt-3 truncate text-lg font-semibold">{{ runtime?.embedding?.model || '尚未就绪' }}</p><p class="mt-1 text-xs text-muted-foreground">由系统统一管理，保证知识库向量维度一致</p></article>
        <article class="rounded-lg border border-border bg-card/70 p-4"><div class="flex items-center justify-between gap-3"><span class="text-sm text-muted-foreground">向量检索库</span><Database class="h-4 w-4 text-emerald-300" /></div><p class="mt-3 truncate text-lg font-semibold">{{ runtime?.vector_store?.collection || '未检测到集合' }}</p><p class="mt-1 text-xs text-muted-foreground">{{ runtime?.vector_store?.ready ? '已连接，可提供检索' : '当前不可用' }}</p></article>
      </section>

      <div class="grid items-start gap-6 xl:grid-cols-[minmax(0,1.35fr)_minmax(20rem,0.72fr)]">
        <Card class="border-border bg-card/80">
          <CardHeader class="border-b border-border/70 p-5">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div><CardTitle class="text-base">配置我的对话模型</CardTitle><CardDescription class="mt-1">支持 DeepSeek、Ollama，以及任何兼容 OpenAI Chat Completions 的供应商。</CardDescription></div>
              <Badge v-if="savedConfig?.configured" variant="outline" :class="savedConfig.enabled ? 'border-emerald-400/25 bg-emerald-400/10 text-emerald-300' : 'border-border text-muted-foreground'">{{ savedConfig.enabled ? '已启用' : '已停用' }}</Badge>
            </div>
          </CardHeader>
          <CardContent class="space-y-5 p-5">
            <div class="space-y-2">
              <Label>1. 选择供应商</Label>
              <div class="grid gap-2 sm:grid-cols-3">
                <button v-for="preset in presets" :key="preset.id" type="button" class="rounded-lg border px-3 py-3 text-left transition-colors" :class="selectedPreset === preset.id ? 'border-cyan-400/45 bg-cyan-400/[0.08]' : 'border-border bg-muted/10 hover:bg-muted/30'" @click="applyPreset(preset)">
                  <span class="block text-sm font-medium">{{ preset.label }}</span>
                  <span class="mt-1 block text-[11px] leading-4 text-muted-foreground">{{ preset.description }}</span>
                </button>
              </div>
            </div>

            <div class="grid gap-4 sm:grid-cols-2">
              <div class="space-y-1.5"><Label for="provider-name">供应商名称</Label><Input id="provider-name" v-model="form.providerName" placeholder="例如：DeepSeek" /></div>
              <div class="space-y-1.5"><Label for="model-name">模型名称</Label><Input id="model-name" v-model="form.modelName" placeholder="例如：deepseek-v4-flash" /><p class="text-xs text-muted-foreground">填写供应商控制台显示的模型 ID。</p></div>
            </div>

            <div class="space-y-1.5"><Label for="base-url">Base URL</Label><Input id="base-url" v-model="form.baseUrl" placeholder="例如：https://api.example.com/v1" /><p class="text-xs text-muted-foreground">支持填写到域名或 /v1，系统会自动拼接 Chat Completions 地址。</p></div>

            <div v-if="needsApiKey" class="space-y-1.5">
              <Label for="api-key">API Key</Label>
              <div class="relative"><Input id="api-key" v-model="form.apiKey" :type="showApiKey ? 'text' : 'password'" class="pr-11" :placeholder="savedConfig?.apiKeyConfigured ? '已安全保存；不修改可留空' : '粘贴供应商提供的 API Key'" autocomplete="new-password" /><button type="button" class="absolute right-1 top-1 flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted" :title="showApiKey ? '隐藏 API Key' : '显示 API Key'" @click="showApiKey = !showApiKey"><EyeOff v-if="showApiKey" class="h-4 w-4" /><Eye v-else class="h-4 w-4" /></button></div>
              <p class="flex items-center gap-1.5 text-xs text-muted-foreground"><ShieldCheck class="h-3.5 w-3.5 text-emerald-300" />密钥会加密保存，保存后不会再次显示明文。</p>
            </div>
            <div v-else class="rounded-lg border border-emerald-400/20 bg-emerald-400/[0.05] p-3 text-sm text-emerald-100"><Server class="mr-2 inline h-4 w-4" />Ollama 通常不需要 API Key，请确认填写的地址能被 Python AI 服务访问。</div>

            <label class="flex items-start gap-3 rounded-lg border border-border bg-muted/10 p-3"><input v-model="form.enabled" type="checkbox" class="mt-1 h-4 w-4 accent-emerald-500" /><span><span class="block text-sm font-medium">保存后立即启用</span><span class="mt-0.5 block text-xs text-muted-foreground">关闭后保留配置，但聊天继续使用系统默认模型。</span></span></label>

            <div v-if="testResult" class="flex items-start gap-2 rounded-lg border p-3 text-sm" :class="testResult.success ? 'border-emerald-400/25 bg-emerald-400/[0.06] text-emerald-100' : 'border-rose-400/25 bg-rose-400/[0.06] text-rose-100'"><CheckCircle2 v-if="testResult.success" class="mt-0.5 h-4 w-4 shrink-0" /><TriangleAlert v-else class="mt-0.5 h-4 w-4 shrink-0" /><div><p class="font-medium">{{ testResult.success ? '连接成功' : '连接失败' }}</p><p class="mt-1 break-words text-xs opacity-85">{{ testResult.message }}</p></div></div>

            <div class="flex flex-wrap gap-2">
              <Button variant="outline" class="gap-2" :disabled="!canSubmit || testing" @click="testConnection"><LoaderCircle v-if="testing" class="h-4 w-4 animate-spin" /><TestTube2 v-else class="h-4 w-4" />{{ testing ? '正在测试…' : '测试连接' }}</Button>
              <Button class="gap-2" :disabled="!canSubmit || saving" @click="saveConfig"><LoaderCircle v-if="saving" class="h-4 w-4 animate-spin" /><Save v-else class="h-4 w-4" />{{ saving ? '正在保存…' : '保存并应用' }}</Button>
              <Button v-if="savedConfig?.configured" variant="ghost" class="gap-2 text-muted-foreground" :disabled="resetting" @click="resetToSystem"><RotateCcw class="h-4 w-4" />恢复系统默认</Button>
            </div>
          </CardContent>
        </Card>

        <aside class="space-y-4">
          <Card class="border-border bg-card/80">
            <CardHeader class="p-5 pb-3"><div class="flex items-center gap-2"><KeyRound class="h-4 w-4 text-amber-300" /><CardTitle class="text-base">操作示例</CardTitle></div><CardDescription>以 DeepSeek 为例，照着填即可。</CardDescription></CardHeader>
            <CardContent class="space-y-3 p-5 pt-2 text-sm">
              <dl class="grid grid-cols-[5.5rem_minmax(0,1fr)] gap-x-3 gap-y-2 rounded-lg border border-border bg-muted/15 p-3 text-xs">
                <dt class="text-muted-foreground">供应商</dt><dd>DeepSeek</dd>
                <dt class="text-muted-foreground">Base URL</dt><dd class="break-all font-mono">https://api.deepseek.com</dd>
                <dt class="text-muted-foreground">模型</dt><dd class="font-mono">deepseek-v4-flash</dd>
                <dt class="text-muted-foreground">API Key</dt><dd>在供应商控制台创建的密钥</dd>
              </dl>
              <ol class="space-y-2 text-sm leading-6 text-muted-foreground">
                <li><span class="mr-2 text-foreground">1.</span>点击“DeepSeek”自动填入示例。</li>
                <li><span class="mr-2 text-foreground">2.</span>粘贴自己的 API Key，点击“测试连接”。</li>
                <li><span class="mr-2 text-foreground">3.</span>测试成功后点击“保存并应用”。</li>
                <li><span class="mr-2 text-foreground">4.</span>新建对话，回答下方会显示实际模型名。</li>
              </ol>
            </CardContent>
          </Card>

          <div class="rounded-lg border border-cyan-400/20 bg-cyan-400/[0.05] p-4 text-sm leading-6 text-muted-foreground"><ShieldCheck class="mr-2 inline h-4 w-4 text-cyan-200" />个人配置只影响你的对话、回答方案测试和批量检查，不会改变其他用户，也不会修改知识库向量模型。</div>
        </aside>
      </div>

      <Card v-if="runtime" class="border-border bg-card/80"><CardHeader class="border-b border-border/70 p-5"><div class="flex items-center gap-2"><Activity class="h-4 w-4 text-primary" /><div><CardTitle class="text-base">系统检索能力</CardTitle><CardDescription class="mt-1">这些能力由系统统一提供，个人切换对话模型后仍可继续使用。</CardDescription></div></div></CardHeader><CardContent class="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-4"><article v-for="feature in featureItems" :key="feature.name" class="rounded-lg border border-border bg-muted/20 p-3.5"><div class="flex items-start justify-between gap-3"><span class="text-sm font-medium">{{ feature.name }}</span><CheckCircle2 v-if="feature.enabled" class="h-4 w-4 shrink-0 text-emerald-300" /><span v-else class="h-2 w-2 rounded-full bg-muted-foreground/50" /></div><p class="mt-2 text-xs leading-5 text-muted-foreground">{{ feature.detail }}</p></article></CardContent></Card>
    </template>

    <div v-if="loading && !runtime" class="flex min-h-72 items-center justify-center rounded-xl border border-border bg-card/60"><LoaderCircle class="h-6 w-6 animate-spin text-primary" /></div>
  </div>
</template>
