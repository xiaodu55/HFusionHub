<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { BellRing, LoaderCircle, Pencil, Plus, RefreshCw, Send, Trash2, Webhook } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import EmptyState from '@/components/EmptyState.vue'
import LoadingSkeleton from '@/components/LoadingSkeleton.vue'
import ErrorState from '@/components/ErrorState.vue'
import { useToast } from '@/composables/useToast'
import { BADGE_TONE_CLASS } from '@/utils/badge'
import * as webhookApi from '@/api/webhook'
import type { WebhookDelivery, WebhookSubscription } from '@/api/webhook'

const toast = useToast()

const subscriptions = ref<WebhookSubscription[]>([])
const loading = ref(false)
const loadError = ref(false)
const actingId = ref<number | null>(null)

// ── 创建/编辑对话框 ──
const dialogOpen = ref(false)
const editingId = ref<number | null>(null)
const saving = ref(false)
const form = ref({ name: '', url: '', secret: '', events: [] as string[] })

// ── 投递历史 ──
const deliveriesOpen = ref(false)
const deliveriesTarget = ref<WebhookSubscription | null>(null)
const deliveries = ref<WebhookDelivery[]>([])
const deliveriesLoading = ref(false)

const formatTime = (value?: string) => (value ? value.replace('T', ' ').slice(0, 16) : '—')

const load = async () => {
  loading.value = true
  loadError.value = false
  try {
    subscriptions.value = (await webhookApi.listSubscriptions()).data
  } catch (error) {
    loadError.value = true
    toast.error(error instanceof Error ? error.message : '加载 Webhook 订阅失败')
  } finally {
    loading.value = false
  }
}

const openCreate = () => {
  editingId.value = null
  form.value = { name: '', url: '', secret: '', events: [] }
  dialogOpen.value = true
}

const openEdit = (sub: WebhookSubscription) => {
  editingId.value = sub.id
  form.value = { name: sub.name, url: sub.url, secret: '', events: [...(sub.events || [])] }
  dialogOpen.value = true
}

const toggleEvent = (value: string) => {
  const list = form.value.events
  const index = list.indexOf(value)
  if (index === -1) list.push(value)
  else list.splice(index, 1)
}

const submitForm = async () => {
  const { name, url, events } = form.value
  if (!name.trim()) { toast.error('订阅名称不能为空'); return }
  if (!/^https?:\/\//.test(url.trim())) { toast.error('回调地址必须以 http:// 或 https:// 开头'); return }
  if (!events.length) { toast.error('至少订阅一个事件类型'); return }

  saving.value = true
  try {
    if (editingId.value) {
      const payload: Record<string, unknown> = { name: name.trim(), url: url.trim(), events }
      if (form.value.secret.trim()) payload.secret = form.value.secret.trim()
      await webhookApi.updateSubscription(editingId.value, payload)
      toast.success('订阅已更新')
    } else {
      await webhookApi.createSubscription({
        name: name.trim(),
        url: url.trim(),
        events,
        secret: form.value.secret.trim() || undefined,
      })
      toast.success('订阅创建成功')
    }
    dialogOpen.value = false
    await load()
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '保存订阅失败')
  } finally {
    saving.value = false
  }
}

const toggleActive = async (sub: WebhookSubscription) => {
  actingId.value = sub.id
  try {
    const next = !(sub.isActive === 1)
    const response = await webhookApi.setActive(sub.id, next)
    Object.assign(sub, response.data)
    toast.success(next ? '已启用' : '已停用')
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '操作失败')
  } finally {
    actingId.value = null
  }
}

const remove = async (sub: WebhookSubscription) => {
  if (!window.confirm(`确定删除订阅「${sub.name}」？删除后不再收到该事件的推送。`)) return
  actingId.value = sub.id
  try {
    await webhookApi.deleteSubscription(sub.id)
    toast.success('订阅已删除')
    await load()
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '删除失败')
  } finally {
    actingId.value = null
  }
}

const test = async (sub: WebhookSubscription) => {
  actingId.value = sub.id
  try {
    const delivery = (await webhookApi.testFire(sub.id)).data
    if (delivery.success === 1) {
      toast.success(`测试投递成功（HTTP ${delivery.responseStatus}，${delivery.durationMs}ms）`)
    } else {
      toast.error(`测试投递失败（HTTP ${delivery.responseStatus ?? '无响应'}），请检查回调地址`)
    }
    await load()
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '测试投递失败')
  } finally {
    actingId.value = null
  }
}

const openDeliveries = async (sub: WebhookSubscription) => {
  deliveriesTarget.value = sub
  deliveriesOpen.value = true
  deliveriesLoading.value = true
  try {
    deliveries.value = (await webhookApi.listDeliveries(sub.id, { page: 1, pageSize: 20 })).data.records
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '加载投递历史失败')
  } finally {
    deliveriesLoading.value = false
  }
}

const deliveryBadgeClass = (d: WebhookDelivery) =>
  d.success === 1 ? BADGE_TONE_CLASS.success : BADGE_TONE_CLASS.danger

onMounted(load)
</script>

<template>
  <Card class="border-border bg-card/80 lg:col-span-2">
    <CardHeader>
      <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div class="flex items-center gap-2"><Webhook class="h-4 w-4 text-primary" /><CardTitle class="text-base">Webhook 推送</CardTitle></div>
          <CardDescription>
            把平台事件（Agent 任务完成/失败、等待确认、文档索引、评测完成）推送到你指定的地址。带 HMAC-SHA256 签名，可在接收端校验。
          </CardDescription>
        </div>
        <div class="flex shrink-0 gap-2">
          <Button variant="outline" size="sm" :disabled="loading" class="gap-1.5" @click="load">
            <LoaderCircle v-if="loading" class="h-3.5 w-3.5 animate-spin" />
            <RefreshCw v-else class="h-3.5 w-3.5" />刷新
          </Button>
          <Button size="sm" class="gap-1.5" @click="openCreate"><Plus class="h-3.5 w-3.5" />新建订阅</Button>
        </div>
      </div>
    </CardHeader>
    <CardContent>
      <div v-if="loading && !subscriptions.length" class="py-4"><LoadingSkeleton type="list" :count="2" /></div>

      <ErrorState
        v-else-if="loadError"
        title="加载失败"
        message="无法读取 Webhook 订阅，请确认服务可用后重试。"
        @retry="load"
      />

      <EmptyState
        v-else-if="!subscriptions.length"
        :icon="Webhook"
        title="还没有 Webhook 订阅"
        description="新建一个订阅并填入接收地址，平台事件就会实时推送到你的系统。"
        show-action
        @action="openCreate"
      />

      <div v-else class="space-y-3">
        <article
          v-for="sub in subscriptions"
          :key="sub.id"
          class="rounded-xl border border-border bg-muted/20 p-4"
        >
          <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <p class="text-sm font-medium">{{ sub.name }}</p>
                <Badge variant="outline" :class="sub.isActive === 1 ? BADGE_TONE_CLASS.success : BADGE_TONE_CLASS.neutral">
                  {{ sub.isActive === 1 ? '已启用' : '已停用' }}
                </Badge>
                <Badge v-if="(sub.failureCount || 0) > 0" variant="outline" :class="BADGE_TONE_CLASS.warning">
                  连续失败 {{ sub.failureCount }}
                </Badge>
              </div>
              <p class="mt-1 truncate font-mono text-xs text-muted-foreground" :title="sub.url">{{ sub.url }}</p>
              <div class="mt-2 flex flex-wrap gap-1.5">
                <Badge v-for="event in sub.events" :key="event" variant="outline" class="text-[10px]">
                  {{ webhookApi.webhookEventLabel(event) }}
                </Badge>
              </div>
              <p class="mt-1.5 text-xs text-muted-foreground">最近触发：{{ formatTime(sub.lastTriggeredAt) }}</p>
            </div>
            <div class="flex shrink-0 flex-wrap gap-2">
              <Button size="sm" variant="outline" class="gap-1.5" :disabled="actingId === sub.id" @click="toggleActive(sub)">
                <BellRing class="h-3.5 w-3.5" />{{ sub.isActive === 1 ? '停用' : '启用' }}
              </Button>
              <Button size="sm" variant="outline" class="gap-1.5" :disabled="actingId === sub.id" @click="test(sub)">
                <Send class="h-3.5 w-3.5" />测试
              </Button>
              <Button size="sm" variant="outline" @click="openDeliveries(sub)">投递记录</Button>
              <Button size="sm" variant="ghost" class="gap-1.5" @click="openEdit(sub)"><Pencil class="h-3.5 w-3.5" />编辑</Button>
              <Button size="sm" variant="ghost" class="gap-1.5 hover:text-destructive" :disabled="actingId === sub.id" @click="remove(sub)">
                <Trash2 class="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        </article>
      </div>
    </CardContent>

    <!-- 创建/编辑对话框 -->
    <Dialog v-model:open="dialogOpen">
      <DialogContent class="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{{ editingId ? '编辑订阅' : '新建 Webhook 订阅' }}</DialogTitle>
          <DialogDescription>
            事件触发时平台会向该地址发送带 <code class="rounded bg-muted px-1">X-Webhook-Signature</code> 签名头的 POST 请求。
          </DialogDescription>
        </DialogHeader>
        <div class="space-y-4">
          <div class="space-y-2">
            <Label for="webhook-name">订阅名称</Label>
            <Input id="webhook-name" v-model="form.name" maxlength="50" placeholder="例如：企业微信机器人" @keydown.enter="submitForm" />
          </div>
          <div class="space-y-2">
            <Label for="webhook-url">回调地址</Label>
            <Input id="webhook-url" v-model="form.url" placeholder="https://example.com/hf-webhook" @keydown.enter="submitForm" />
          </div>
          <div class="space-y-2">
            <Label for="webhook-secret">签名密钥（可选）</Label>
            <Input
              id="webhook-secret"
              v-model="form.secret"
              :placeholder="editingId ? '留空则保持原密钥不变' : '用于接收端校验签名'"
            />
            <p class="text-xs text-muted-foreground">签名为 HMAC-SHA256(secret, 原始请求体)，十六进制格式。</p>
          </div>
          <div class="space-y-2">
            <Label>订阅事件</Label>
            <div class="space-y-2">
              <label
                v-for="event in webhookApi.WEBHOOK_EVENTS"
                :key="event.value"
                class="flex cursor-pointer items-start gap-2.5 rounded-lg border p-2.5 transition-colors"
                :class="form.events.includes(event.value) ? 'border-primary/45 bg-primary/[0.06]' : 'border-border hover:bg-muted/30'"
              >
                <input
                  type="checkbox"
                  class="mt-0.5 h-4 w-4 accent-[var(--primary,#7c5cff)]"
                  :checked="form.events.includes(event.value)"
                  @change="toggleEvent(event.value)"
                />
                <span>
                  <span class="block text-sm font-medium">{{ event.label }}</span>
                  <span class="mt-0.5 block text-xs text-muted-foreground">{{ event.description }}</span>
                </span>
              </label>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="dialogOpen = false">取消</Button>
          <Button :disabled="saving" @click="submitForm">{{ saving ? '保存中…' : '保存' }}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- 投递历史对话框 -->
    <Dialog v-model:open="deliveriesOpen">
      <DialogContent class="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>投递记录 — {{ deliveriesTarget?.name }}</DialogTitle>
          <DialogDescription>最近 20 次投递结果。</DialogDescription>
        </DialogHeader>
        <div v-if="deliveriesLoading" class="py-4"><LoadingSkeleton type="list" :count="3" /></div>
        <EmptyState
          v-else-if="!deliveries.length"
          title="暂无投递记录"
          description="订阅创建后尚未触发过任何事件。可点击「测试」手动触发一次。"
        />
        <div v-else class="max-h-80 space-y-2 overflow-auto">
          <div
            v-for="delivery in deliveries"
            :key="delivery.id"
            class="flex items-center justify-between gap-3 rounded-lg border border-border bg-muted/15 px-3 py-2 text-xs"
          >
            <div class="min-w-0">
              <p class="font-medium">{{ webhookApi.webhookEventLabel(delivery.eventType) }}</p>
              <p class="mt-0.5 text-muted-foreground">{{ formatTime(delivery.createdAt) }} · {{ delivery.durationMs ?? '—' }}ms</p>
            </div>
            <Badge variant="outline" :class="deliveryBadgeClass(delivery)">
              {{ delivery.success === 1 ? `HTTP ${delivery.responseStatus}` : `失败 ${delivery.responseStatus ?? ''}` }}
            </Badge>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  </Card>
</template>
