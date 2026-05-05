<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Bell, Megaphone, Plus, RefreshCw, Trash2 } from 'lucide-vue-next'
import * as notificationApi from '@/api/notification'
import type { SystemNotice } from '@/api/notification'
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
const notices = ref<SystemNotice[]>([])
const saving = ref(false)
const addDialogOpen = ref(false)
const deleteTarget = ref<SystemNotice | null>(null)
const confirmDeleteOpen = ref(false)
const confirmDeleteLoading = ref(false)

const levelOptions = [
  { label: '信息', value: 'info' },
  { label: '警告', value: 'warning' },
  { label: '错误', value: 'error' },
]

const scopeOptions = [
  { label: '全体用户', value: 'all' },
  { label: '仅管理员', value: 'admin' },
  { label: '仅普通用户', value: 'user' },
]

const form = ref({
  title: '',
  content: '',
  level: 'info' as 'info' | 'warning' | 'error',
  scope: 'all' as 'all' | 'admin' | 'user',
  expiresAt: '',
})

const levelClass = (level: string) => ({
  info: 'border-sky-400/30 bg-sky-400/[0.06] text-sky-200',
  warning: 'border-amber-400/30 bg-amber-400/[0.06] text-amber-200',
  error: 'border-rose-400/30 bg-rose-400/[0.06] text-rose-200',
})[level] ?? ''

const levelLabel = (level: string) => ({ info: '提示', warning: '重要', error: '紧急' })[level] ?? level

const scopeLabel = (scope: string) => ({ all: '全体', admin: '管理员', user: '普通用户' })[scope] ?? scope

async function load() {
  loading.value = true
  try {
    const response = await notificationApi.adminListNotices()
    notices.value = response.data
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '加载公告失败')
  } finally {
    loading.value = false
  }
}

async function publish() {
  if (!form.value.title.trim() || !form.value.content.trim()) {
    toast.error('标题和内容不能为空')
    return
  }
  saving.value = true
  try {
    await notificationApi.adminCreateNotice({
      title: form.value.title.trim(),
      content: form.value.content.trim(),
      level: form.value.level,
      scope: form.value.scope,
      expiresAt: form.value.expiresAt ? new Date(form.value.expiresAt).toISOString() : null,
    })
    toast.success('公告已发布')
    form.value = { title: '', content: '', level: 'info', scope: 'all', expiresAt: '' }
    addDialogOpen.value = false
    await load()
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '发布失败')
  } finally {
    saving.value = false
  }
}

function remove(notice: SystemNotice) {
  deleteTarget.value = notice
  confirmDeleteOpen.value = true
}

async function confirmDelete() {
  const notice = deleteTarget.value
  if (!notice) return
  confirmDeleteLoading.value = true
  try {
    await notificationApi.adminDeleteNotice(notice.id)
    toast.success('公告已删除')
    notices.value = notices.value.filter(item => item.id !== notice.id)
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '删除失败')
  } finally {
    confirmDeleteLoading.value = false
    confirmDeleteOpen.value = false
    deleteTarget.value = null
  }
}

function formatTime(value?: string | null) {
  if (!value) return '—'
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

onMounted(load)
</script>

<template>
  <div class="mx-auto max-w-5xl space-y-6 p-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="flex items-center gap-2 text-xl font-semibold">
          <Megaphone class="h-5 w-5 text-emerald-300" />
          公告管理
        </h1>
        <p class="mt-1 text-sm text-muted-foreground">发布系统公告，用户会在通知铃铛中看到并标记已读。</p>
      </div>
      <div class="flex items-center gap-2">
        <Button variant="outline" size="sm" @click="load">
          <RefreshCw class="mr-1.5 h-4 w-4" /> 刷新
        </Button>
        <Dialog v-model:open="addDialogOpen">
          <DialogTrigger as-child>
            <Button size="sm">
              <Plus class="mr-1.5 h-4 w-4" /> 发布公告
            </Button>
          </DialogTrigger>
          <DialogContent class="sm:max-w-lg">
            <DialogHeader>
              <DialogTitle>发布公告</DialogTitle>
              <DialogDescription>公告将出现在所有可见范围内用户的通知铃铛中。</DialogDescription>
            </DialogHeader>
            <div class="space-y-4 py-2">
              <div class="space-y-2">
                <Label>标题</Label>
                <Input v-model="form.title" placeholder="例如：系统将于今晚 23:00 升级维护" maxlength="100" />
              </div>
              <div class="space-y-2">
                <Label>内容</Label>
                <textarea
                  v-model="form.content"
                  rows="5"
                  class="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-emerald-400/40"
                  placeholder="公告正文…"
                />
              </div>
              <div class="grid grid-cols-2 gap-4">
                <div class="space-y-2">
                  <Label>级别</Label>
                  <Select v-model="form.level" :options="levelOptions" />
                </div>
                <div class="space-y-2">
                  <Label>范围</Label>
                  <Select v-model="form.scope" :options="scopeOptions" />
                </div>
              </div>
              <div class="space-y-2">
                <Label>过期时间（可选）</Label>
                <Input v-model="form.expiresAt" type="datetime-local" />
              </div>
            </div>
            <DialogFooter>
              <Button :disabled="saving" @click="publish">
                {{ saving ? '发布中…' : '确认发布' }}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </div>

    <Card>
      <CardHeader>
        <CardTitle class="flex items-center gap-2 text-base">
          <Bell class="h-4 w-4 text-emerald-300" /> 已发布公告
        </CardTitle>
        <CardDescription>共 {{ notices.length }} 条，按发布时间倒序。</CardDescription>
      </CardHeader>
      <CardContent class="space-y-3">
        <LoadingSkeleton v-if="loading" type="card" :count="3" />
        <EmptyState
          v-else-if="!notices.length"
          :icon="Megaphone"
          title="还没有发布过公告"
          description="发布公告后，用户会在通知铃铛中看到并标记已读。点击上方按钮开始。"
          action="发布公告"
          show-action
          @action="addDialogOpen = true"
        />
        <article
          v-for="notice in notices"
          :key="notice.id"
          class="rounded-xl border border-border bg-muted/30 p-4"
        >
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <span class="text-sm font-medium">{{ notice.title }}</span>
                <span class="rounded-full border px-2 py-0.5 text-[11px]" :class="levelClass(notice.level)">
                  {{ levelLabel(notice.level) }}
                </span>
                <span class="rounded-full border px-2 py-0.5 text-[11px] text-muted-foreground">
                  {{ scopeLabel(notice.scope) }}
                </span>
              </div>
              <p class="mt-2 break-words whitespace-pre-wrap text-sm leading-6 text-foreground/85">{{ notice.content }}</p>
              <div class="mt-2 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                <span>发布：{{ formatTime(notice.createdAt) }}</span>
                <span>过期：{{ formatTime(notice.expiresAt) }}</span>
              </div>
            </div>
            <Button variant="outline" size="sm" class="shrink-0" @click="remove(notice)">
              <Trash2 class="h-4 w-4" />
            </Button>
          </div>
        </article>
      </CardContent>
    </Card>

    <ConfirmDialog
      v-model:open="confirmDeleteOpen"
      title="删除确认"
      :description="`确定删除公告「${deleteTarget?.title}」？`"
      confirm-text="删除"
      destructive
      :loading="confirmDeleteLoading"
      @confirm="confirmDelete"
    />
  </div>
</template>
