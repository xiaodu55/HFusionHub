<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Shield, ShieldAlert, ShieldCheck, Eye, EyeOff, RefreshCw } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { useToast } from '@/composables/useToast'
import { formatDateTime } from '@/utils/date'

const toast = useToast()

const loading = ref(false)
const guardrailStatus = ref({
  promptInjection: true,
  contentModeration: true,
  piiMasking: true,
})
const stats = ref({
  totalChecks: 0,
  blockedRequests: 0,
  piiMasked: 0,
  lastCheck: '',
})

// PII mask preview
const previewInput = ref('')
const previewOutput = ref('')
const previewLoading = ref(false)

async function loadStatus() {
  loading.value = true
  try {
    // In production, fetch from /api/guardrails/status
    // For now, show defaults with simulated stats
    stats.value = {
      totalChecks: 2847,
      blockedRequests: 23,
      piiMasked: 156,
      lastCheck: new Date().toISOString(),
    }
  } catch {
    toast.error('无法加载安全配置状态')
  } finally {
    loading.value = false
  }
}

async function toggleGuard(key: keyof typeof guardrailStatus.value) {
  guardrailStatus.value[key] = !guardrailStatus.value[key]
  toast.success(`${guardrailStatus.value[key] ? '已启用' : '已禁用'} ${getLabel(key)}`)
}

async function previewMask() {
  if (!previewInput.value.trim()) return
  previewLoading.value = true
  try {
    // Simulate PII masking
    let masked = previewInput.value
    masked = masked.replace(/\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/g, '[EMAIL]')
    masked = masked.replace(/\b1[3-9]\d{9}\b/g, '[PHONE]')
    masked = masked.replace(/\b\d{17}[\dXx]\b/g, '[ID_NUM]')
    previewOutput.value = masked
  } catch {
    previewOutput.value = '脱敏预览失败'
  } finally {
    previewLoading.value = false
  }
}

function getLabel(key: string): string {
  const map: Record<string, string> = {
    promptInjection: 'Prompt 注入检测',
    contentModeration: '内容审核',
    piiMasking: 'PII 脱敏',
  }
  return map[key] || key
}

onMounted(loadStatus)
</script>

<template>
  <div class="space-y-6 pb-8">
    <div>
      <h2 class="text-2xl font-bold tracking-tight">安全护栏配置</h2>
      <p class="text-sm text-muted-foreground mt-1">管理 AI 安全策略：注入检测、内容审核、敏感信息脱敏</p>
    </div>

    <div v-if="loading" class="text-center py-16 text-muted-foreground">加载中...</div>

    <template v-else>
      <!-- Status summary -->
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card>
          <CardHeader class="pb-2">
            <CardDescription class="flex items-center gap-1.5">
              <ShieldCheck class="h-3.5 w-3.5 text-emerald-500" />总检查次数
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p class="text-2xl font-bold">{{ stats.totalChecks.toLocaleString() }}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader class="pb-2">
            <CardDescription class="flex items-center gap-1.5">
              <ShieldAlert class="h-3.5 w-3.5 text-amber-500" />拦截请求
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p class="text-2xl font-bold">{{ stats.blockedRequests.toLocaleString() }}</p>
            <p class="text-xs text-muted-foreground mt-1">
              {{ stats.totalChecks ? (stats.blockedRequests / stats.totalChecks * 100).toFixed(2) : 0 }}% 拦截率
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader class="pb-2">
            <CardDescription class="flex items-center gap-1.5">
              <EyeOff class="h-3.5 w-3.5 text-sky-500" />PII 脱敏
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p class="text-2xl font-bold">{{ stats.piiMasked.toLocaleString() }}</p>
            <p class="text-xs text-muted-foreground mt-1">最近检查: {{ stats.lastCheck ? formatDateTime(stats.lastCheck) : '-' }}</p>
          </CardContent>
        </Card>
      </div>

      <!-- Toggle switches -->
      <Card>
        <CardHeader>
          <CardTitle class="text-base">安全策略开关</CardTitle>
          <CardDescription>控制各项安全策略的运行状态</CardDescription>
        </CardHeader>
        <CardContent class="space-y-4">
          <div v-for="(enabled, key) in guardrailStatus" :key="key" class="flex items-center justify-between py-2">
            <div class="space-y-0.5">
              <div class="flex items-center gap-2">
                <Shield :class="['h-4 w-4', enabled ? 'text-emerald-500' : 'text-muted-foreground']" />
                <span class="text-sm font-medium">{{ getLabel(key as string) }}</span>
                <Badge :variant="enabled ? 'default' : 'outline'" class="text-[10px]">
                  {{ enabled ? '启用' : '禁用' }}
                </Badge>
              </div>
              <p class="text-xs text-muted-foreground ml-6">
                {{ key === 'promptInjection' ? '检测并阻止 Prompt 注入攻击' :
                   key === 'contentModeration' ? '审核输入输出中的不当内容' :
                   '自动遮蔽邮箱、手机号、身份证号等敏感信息' }}
              </p>
            </div>
            <Button
              :variant="enabled ? 'default' : 'outline'"
              size="sm"
              @click="toggleGuard(key as keyof typeof guardrailStatus)"
            >
              {{ enabled ? '禁用' : '启用' }}
            </Button>
          </div>
        </CardContent>
      </Card>

      <!-- PII Mask preview -->
      <Card>
        <CardHeader>
          <CardTitle class="text-base">PII 脱敏预览</CardTitle>
          <CardDescription>输入包含敏感信息的文本，预览脱敏效果</CardDescription>
        </CardHeader>
        <CardContent class="space-y-4">
          <div class="space-y-1.5">
            <Label class="text-sm">输入文本</Label>
            <Input
              v-model="previewInput"
              placeholder="例如：我的邮箱是 user@example.com，手机号 13812345678"
              class="font-mono text-sm"
            />
          </div>
          <Button variant="outline" size="sm" :disabled="previewLoading || !previewInput.trim()" @click="previewMask">
            <Eye class="h-3.5 w-3.5 mr-1.5" />{{ previewLoading ? '处理中...' : '预览脱敏' }}
          </Button>
          <div v-if="previewOutput" class="space-y-1.5">
            <Separator />
            <Label class="text-sm">脱敏结果</Label>
            <div class="p-3 rounded-lg bg-muted font-mono text-sm break-all">{{ previewOutput }}</div>
          </div>
        </CardContent>
      </Card>

      <!-- Recent safety events -->
      <Card>
        <CardHeader>
          <CardTitle class="text-base">最近安全事件</CardTitle>
          <CardDescription>最近 20 条安全相关事件记录</CardDescription>
        </CardHeader>
        <CardContent>
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b text-left text-xs text-muted-foreground">
                  <th class="py-2 pr-4">时间</th>
                  <th class="py-2 pr-4">类型</th>
                  <th class="py-2 pr-4">严重性</th>
                  <th class="py-2">详情</th>
                </tr>
              </thead>
              <tbody>
                <tr class="border-b">
                  <td class="py-2 pr-4 text-xs">2026-08-07 08:30</td>
                  <td class="py-2 pr-4">
                    <Badge variant="outline" class="text-[10px]">注入检测</Badge>
                  </td>
                  <td class="py-2 pr-4">
                    <Badge class="text-[10px] bg-red-500/20 text-red-400 border-red-400/25">严重</Badge>
                  </td>
                  <td class="py-2 text-xs text-muted-foreground">检测到 ignore previous instructions 模式</td>
                </tr>
                <tr class="border-b">
                  <td class="py-2 pr-4 text-xs">2026-08-07 07:15</td>
                  <td class="py-2 pr-4">
                    <Badge variant="outline" class="text-[10px]">PII 脱敏</Badge>
                  </td>
                  <td class="py-2 pr-4">
                    <Badge class="text-[10px] bg-sky-500/20 text-sky-400 border-sky-400/25">信息</Badge>
                  </td>
                  <td class="py-2 text-xs text-muted-foreground">掩盖了 2 个邮箱地址和 1 个手机号</td>
                </tr>
                <tr>
                  <td class="py-2 pr-4 text-xs">2026-08-06 22:45</td>
                  <td class="py-2 pr-4">
                    <Badge variant="outline" class="text-[10px]">内容审核</Badge>
                  </td>
                  <td class="py-2 pr-4">
                    <Badge class="text-[10px] bg-amber-500/20 text-amber-400 border-amber-400/25">警告</Badge>
                  </td>
                  <td class="py-2 text-xs text-muted-foreground">检测到不当内容关键词</td>
                </tr>
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </template>
  </div>
</template>
