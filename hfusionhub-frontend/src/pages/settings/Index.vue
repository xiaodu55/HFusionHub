<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowRight,
  Cloud,
  Cpu,
  Database,
  LoaderCircle,
  Moon,
  Palette,
  RefreshCw,
  Settings2,
  ShieldCheck,
  Sun,
  UserRound,
} from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { useTheme } from '@/composables/useTheme'
import * as systemApi from '@/api/system'

const router = useRouter()
const { isDarkMode, initializeTheme, setTheme } = useTheme()

// ── Provider status ──
const runtime = ref<systemApi.AiRuntimeOverview | null>(null)
const providerLoading = ref(false)
const providerError = ref('')

const stateBadgeClass = (state?: string) => {
  const map: Record<string, string> = {
    ready: 'border-emerald-400/25 bg-emerald-400/10 text-emerald-300',
    configured: 'border-cyan-400/25 bg-cyan-400/10 text-cyan-200',
    reachable: 'border-amber-400/25 bg-amber-400/10 text-amber-200',
    development: 'border-violet-400/25 bg-violet-400/10 text-violet-200',
    unavailable: 'border-rose-400/25 bg-rose-400/10 text-rose-200',
    not_configured: 'border-border bg-muted text-muted-foreground',
  }
  return map[state || 'unavailable'] || map.unavailable
}

const stateLabel = (state?: string) => {
  const map: Record<string, string> = {
    ready: '已就绪',
    configured: '已配置',
    reachable: '服务可达',
    development: '开发模式',
    unavailable: '不可用',
    not_configured: '未配置',
  }
  return map[state || 'unavailable'] || state || '未知'
}

const circuitLabel = (state?: string) => ({
  closed: '正常',
  open: '熔断中',
  half_open: '半开探测',
}[state || ''] || '未知')

const circuitClass = (state?: string) => ({
  closed: 'text-emerald-300',
  open: 'text-rose-300',
  half_open: 'text-amber-300',
}[state || ''] || 'text-muted-foreground')

const loadProviders = async () => {
  providerLoading.value = true
  providerError.value = ''
  try {
    runtime.value = (await systemApi.getAiRuntimeOverview()).data
  } catch (e) {
    providerError.value = e instanceof Error ? e.message : '无法读取 AI 运行状态'
  } finally {
    providerLoading.value = false
  }
}

const formatTime = (value?: string) => {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(date)
}

onMounted(() => {
  initializeTheme()
  loadProviders()
})
</script>

<template>
  <div class="mx-auto max-w-5xl space-y-6 pb-4">
    <section class="rounded-2xl border border-border bg-card/80 p-5 shadow-[0_18px_45px_rgba(0,0,0,0.18)] sm:p-6">
      <div class="flex items-center gap-4"><div class="flex h-11 w-11 items-center justify-center rounded-xl border border-primary/25 bg-primary/10 text-primary"><Settings2 class="h-5 w-5" /></div><div><p class="text-xs font-medium tracking-[0.16em] text-primary/90">PREFERENCES</p><h1 class="mt-1 text-2xl font-semibold">设置</h1><p class="mt-1 text-sm text-muted-foreground">管理界面偏好、AI 供应商状态和常用账户入口。</p></div></div>
    </section>

    <div class="grid gap-6 lg:grid-cols-2">
      <Card class="border-border bg-card/80"><CardHeader><div class="flex items-center gap-2"><Palette class="h-4 w-4 text-primary" /><CardTitle class="text-base">外观</CardTitle></div><CardDescription>主题会保存在当前浏览器中。</CardDescription></CardHeader><CardContent><div class="grid grid-cols-2 gap-3"><button class="rounded-xl border p-4 text-left transition-colors" :class="!isDarkMode ? 'border-primary/50 bg-primary/[0.08]' : 'border-border bg-muted/25 hover:bg-muted/40'" @click="setTheme(false)"><Sun class="h-5 w-5 text-amber-300" /><p class="mt-3 text-sm font-medium">浅色主题</p><p class="mt-1 text-xs text-muted-foreground">明亮、适合白天使用</p></button><button class="rounded-xl border p-4 text-left transition-colors" :class="isDarkMode ? 'border-primary/50 bg-primary/[0.08]' : 'border-border bg-muted/25 hover:bg-muted/40'" @click="setTheme(true)"><Moon class="h-5 w-5 text-cyan-200" /><p class="mt-3 text-sm font-medium">深色主题</p><p class="mt-1 text-xs text-muted-foreground">低亮度、适合长时间阅读</p></button></div></CardContent></Card>

      <Card class="border-border bg-card/80"><CardHeader><div class="flex items-center gap-2"><UserRound class="h-4 w-4 text-primary" /><CardTitle class="text-base">账户</CardTitle></div><CardDescription>更新昵称、邮箱和手机号。</CardDescription></CardHeader><CardContent><Button variant="outline" class="w-full justify-between" @click="router.push('/profile')"><span>打开个人中心</span><ArrowRight class="h-4 w-4" /></Button></CardContent></Card>

      <Card class="border-border bg-card/80 lg:col-span-2"><CardHeader><div class="flex items-center gap-2"><ShieldCheck class="h-4 w-4 text-primary" /><CardTitle class="text-base">AI 高级能力</CardTitle></div><CardDescription>查看混合检索、OCR、图谱和多 Agent 等可选能力的影响与部署要求。</CardDescription></CardHeader><CardContent><Button variant="outline" class="w-full justify-between" @click="router.push('/admin/flags')"><span>打开高级能力说明</span><ArrowRight class="h-4 w-4" /></Button></CardContent></Card>

      <!-- Provider status card (Phase 1: read-only from runtime API) -->
      <Card class="border-border bg-card/80 lg:col-span-2">
        <CardHeader>
          <div class="flex items-center justify-between gap-3">
            <div>
              <div class="flex items-center gap-2"><Cpu class="h-4 w-4 text-primary" /><CardTitle class="text-base">AI 供应商状态</CardTitle></div>
              <CardDescription>当前部署中已发现和配置的模型提供方。修改供应商配置需通过环境变量并重启服务。</CardDescription>
            </div>
            <Button variant="outline" size="sm" :disabled="providerLoading" class="gap-1.5 shrink-0" @click="loadProviders">
              <LoaderCircle v-if="providerLoading" class="h-3.5 w-3.5 animate-spin" />
              <RefreshCw v-else class="h-3.5 w-3.5" />
              刷新
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <!-- Loading -->
          <div v-if="providerLoading && !runtime" class="flex items-center justify-center py-8 text-sm text-muted-foreground">
            <LoaderCircle class="mr-2 h-4 w-4 animate-spin" />正在读取供应商状态…
          </div>

          <!-- Error -->
          <div v-else-if="providerError" class="rounded-xl border border-rose-400/20 bg-rose-400/[0.06] p-4 text-sm text-rose-100/85">
            {{ providerError }}
            <Button variant="outline" size="sm" class="ml-3" @click="loadProviders">重试</Button>
          </div>

          <!-- Providers grid -->
          <template v-else-if="runtime">
            <div class="grid gap-3 sm:grid-cols-2">
              <article
                v-for="provider in runtime.providers || []"
                :key="provider.id"
                class="rounded-xl border border-border bg-muted/25 p-4"
              >
                <div class="flex items-start justify-between gap-3">
                  <div class="min-w-0">
                    <div class="flex items-center gap-2">
                      <Cloud class="h-4 w-4 shrink-0 text-cyan-200" />
                      <span class="text-sm font-semibold">{{ provider.label }}</span>
                    </div>
                    <p class="mt-1 text-xs text-muted-foreground">{{ provider.purpose }}</p>
                    <p v-if="provider.model" class="mt-0.5 font-mono text-[11px] text-muted-foreground truncate">{{ provider.model }}</p>
                  </div>
                  <Badge variant="outline" :class="stateBadgeClass(provider.state)">{{ stateLabel(provider.state) }}</Badge>
                </div>
                <div class="mt-3 flex items-center gap-3 text-xs text-muted-foreground">
                  <span v-if="provider.configured">✅ 已配置</span>
                  <span v-else>⚪ 未配置</span>
                  <span v-if="provider.reachable !== undefined">
                    {{ provider.reachable ? '✅ 可达' : '❌ 不可达' }}
                  </span>
                  <span v-if="provider.model_available !== undefined">
                    {{ provider.model_available ? '✅ 模型可用' : '❌ 模型未检测到' }}
                  </span>
                </div>
              </article>
            </div>

            <!-- LLM & Embedding summary -->
            <div class="mt-4 grid gap-3 sm:grid-cols-3">
              <div class="rounded-lg border border-border bg-muted/15 p-3">
                <div class="flex items-center gap-1.5 text-xs text-muted-foreground"><Cloud class="h-3 w-3" />对话模型</div>
                <p class="mt-1 text-sm font-medium truncate">{{ runtime.llm?.model || '未检测到' }}</p>
                <Badge variant="outline" class="mt-1.5 text-[10px]" :class="stateBadgeClass(runtime.llm?.state)">{{ stateLabel(runtime.llm?.state) }}</Badge>
              </div>
              <div class="rounded-lg border border-border bg-muted/15 p-3">
                <div class="flex items-center gap-1.5 text-xs text-muted-foreground"><Cpu class="h-3 w-3" />向量化模型</div>
                <p class="mt-1 text-sm font-medium truncate">{{ runtime.embedding?.model || '未检测到' }}</p>
                <Badge variant="outline" class="mt-1.5 text-[10px]" :class="stateBadgeClass(runtime.embedding?.state)">{{ stateLabel(runtime.embedding?.state) }}</Badge>
              </div>
              <div class="rounded-lg border border-border bg-muted/15 p-3">
                <div class="flex items-center gap-1.5 text-xs text-muted-foreground"><Database class="h-3 w-3" />向量库</div>
                <p class="mt-1 text-sm font-medium truncate">{{ runtime.vector_store?.collection || '未检测到' }}</p>
                <Badge variant="outline" class="mt-1.5 text-[10px]" :class="runtime.vector_store?.ready ? stateBadgeClass('ready') : stateBadgeClass('unavailable')">{{ runtime.vector_store?.ready ? '已就绪' : '不可用' }}</Badge>
              </div>
            </div>

            <div v-if="runtime.model_gateway" class="mt-4 rounded-xl border border-border bg-muted/15 p-4">
              <div class="flex items-center justify-between gap-3">
                <div>
                  <p class="text-sm font-medium">模型网关</p>
                  <p class="mt-1 text-xs text-muted-foreground">故障自动切换与熔断恢复状态</p>
                </div>
                <Badge variant="outline" :class="runtime.model_gateway.gateway_enabled ? stateBadgeClass('ready') : stateBadgeClass('unavailable')">
                  {{ runtime.model_gateway.gateway_enabled ? '已启用' : '未启用' }}
                </Badge>
              </div>
              <div v-if="runtime.model_gateway.providers?.length" class="mt-3 grid gap-2 sm:grid-cols-3">
                <div v-for="provider in runtime.model_gateway.providers" :key="provider.provider" class="rounded-lg border border-border bg-background/30 px-3 py-2 text-xs">
                  <div class="flex items-center justify-between gap-2">
                    <span class="font-medium">{{ provider.provider }}</span>
                    <span :class="circuitClass(provider.circuit)">{{ circuitLabel(provider.circuit) }}</span>
                  </div>
                  <div class="mt-1 flex justify-between text-muted-foreground">
                    <span>{{ provider.available ? '可用' : '不可用' }}</span>
                    <span>失败 {{ provider.failure_count }}</span>
                  </div>
                </div>
              </div>
            </div>

            <p v-if="runtime.generated_at" class="mt-3 text-xs text-muted-foreground">最近检查：{{ formatTime(runtime.generated_at) }}</p>
          </template>

          <!-- No data yet -->
          <div v-else class="flex min-h-[8rem] items-center justify-center text-sm text-muted-foreground">
            点击"刷新"读取供应商状态
          </div>
        </CardContent>
      </Card>
    </div>
  </div>
</template>
