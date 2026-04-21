<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Check, Clock3, RefreshCw, Search, ShieldCheck, UserCog, Users } from 'lucide-vue-next'
import * as userApi from '@/api/user'
import type { PageResult, UserInfo, UserRole } from '@/api/types'
import { useUserStore } from '@/stores/user'
import { useToast } from '@/composables/useToast'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import LoadingSkeleton from '@/components/LoadingSkeleton.vue'

const userStore = useUserStore()
const toast = useToast()
const loading = ref(false)
const savingId = ref<number | null>(null)
const keyword = ref('')
const roleFilter = ref<UserRole | ''>('')
const result = ref<PageResult<UserInfo>>({
  records: [], total: 0, page: 1, pageSize: 20, totalPages: 0, hasPrevious: false, hasNext: false,
})
const pendingTotal = ref(0)
const pendingRoles = ref<Record<number, UserRole>>({})

const roles: Array<{ value: UserRole; label: string; summary: string }> = [
  { value: 'pending', label: '待分配', summary: '只能登录查看等待状态' },
  { value: 'user', label: '普通用户', summary: '知识库、文档和智能对话' },
  { value: 'builder', label: 'AI 配置员', summary: '普通功能及回答方案、测试与效果分析' },
  { value: 'admin', label: '超级管理员', summary: '仅 admin 账号，管理全系统' },
]
const assignableRoles = roles.filter(item => item.value !== 'admin')

const roleMeta = (role?: string) => roles.find(item => item.value === role) || roles[0]
const currentUserId = computed(() => userStore.userInfo?.id)
const viewingPending = computed(() => roleFilter.value === 'pending')
const formatDate = (value?: string) => value ? value.replace('T', ' ').slice(0, 16) : '尚未登录'
const isSuperAdmin = (user: UserInfo) => user.role === 'admin' || user.username === 'admin'

async function load(page = result.value.page || 1) {
  loading.value = true
  try {
    const [response, pendingResponse] = await Promise.all([
      userApi.listUsers({
        page,
        pageSize: result.value.pageSize,
        keyword: keyword.value.trim() || undefined,
        role: roleFilter.value,
      }),
      userApi.listUsers({ page: 1, pageSize: 1, role: 'pending' }),
    ])
    result.value = response.data
    pendingTotal.value = pendingResponse.data.total
    pendingRoles.value = Object.fromEntries(response.data.records.map(user => [user.id, user.role]))
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '加载用户失败')
  } finally {
    loading.value = false
  }
}

async function saveRole(user: UserInfo) {
  const nextRole = pendingRoles.value[user.id]
  if (!nextRole || nextRole === user.role) return
  savingId.value = user.id
  try {
    const response = await userApi.updateUserRole(user.id, nextRole)
    Object.assign(user, response.data)
    toast.success(`${user.nickname || user.username} 已设为${roleMeta(nextRole).label}`)
    await load(result.value.page)
  } catch (error) {
    pendingRoles.value[user.id] = user.role
    toast.error(error instanceof Error ? error.message : '修改身份失败')
  } finally {
    savingId.value = null
  }
}

function showAll() {
  keyword.value = ''
  roleFilter.value = ''
  void load(1)
}

function showPending() {
  keyword.value = ''
  roleFilter.value = 'pending'
  void load(1)
}

function resetFilters() {
  keyword.value = ''
  roleFilter.value = ''
  void load(1)
}

onMounted(() => load(1))
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-5 pb-8">
    <section class="rounded-xl border border-border bg-card/80 p-5 sm:p-6">
      <div class="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
        <div class="flex items-start gap-4">
          <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-primary/25 bg-primary/10 text-primary">
            <UserCog class="h-5 w-5" />
          </div>
          <div>
            <p class="text-xs font-medium text-primary">账号管理</p>
            <h1 class="mt-1 text-2xl font-semibold">给新用户分配使用权限</h1>
            <p class="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
              新用户注册后默认没有业务权限。管理员在这里找到账号，选择身份并保存，对方刷新页面后即可使用对应功能。
            </p>
          </div>
        </div>
        <Button variant="outline" :disabled="loading" class="gap-2" @click="load()">
          <RefreshCw class="h-4 w-4" :class="loading && 'animate-spin'" />刷新
        </Button>
      </div>

      <div class="mt-5 flex flex-wrap gap-x-6 gap-y-3 border-t border-border pt-5">
        <div v-for="item in roles" :key="item.value" class="flex items-start gap-2">
          <ShieldCheck class="mt-0.5 h-4 w-4 shrink-0 text-primary" />
          <div>
            <p class="text-sm font-medium">{{ item.label }}</p>
            <p class="text-xs text-muted-foreground">{{ item.summary }}</p>
          </div>
        </div>
      </div>
    </section>

    <section v-if="pendingTotal > 0" class="flex flex-col gap-4 rounded-xl border border-amber-400/25 bg-amber-400/[0.06] p-4 sm:flex-row sm:items-center sm:justify-between">
      <div class="flex items-start gap-3">
        <div class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-amber-400/10 text-amber-300">
          <Clock3 class="h-4 w-4" />
        </div>
        <div>
          <p class="font-medium text-amber-300">有 {{ pendingTotal }} 个新账号等待分配</p>
          <p class="mt-1 text-sm text-muted-foreground">处理方法：选择“普通用户”或“AI 配置员”，再点击保存。</p>
        </div>
      </div>
      <Button variant="outline" class="shrink-0" @click="showPending">立即处理</Button>
    </section>

    <section class="overflow-hidden rounded-xl border border-border bg-card/70">
      <div class="border-b border-border p-4">
        <div class="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
          <div>
            <h2 class="font-semibold">账号列表</h2>
            <p class="mt-1 text-sm text-muted-foreground">当前条件下共 {{ result.total }} 个账号</p>
          </div>

          <div class="flex flex-col gap-2 lg:flex-row lg:items-center">
            <div class="inline-flex w-fit rounded-lg border border-border bg-background p-1">
              <button class="rounded-md px-3 py-1.5 text-sm" :class="!viewingPending ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'" @click="showAll">全部账号</button>
              <button class="flex items-center gap-2 rounded-md px-3 py-1.5 text-sm" :class="viewingPending ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'" @click="showPending">
                待分配<span class="rounded-full bg-background/20 px-1.5 text-xs">{{ pendingTotal }}</span>
              </button>
            </div>

            <form class="flex min-w-0 gap-2 sm:w-80" @submit.prevent="load(1)">
              <div class="relative min-w-0 flex-1">
                <Search class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input v-model="keyword" class="pl-9" placeholder="搜索用户名、昵称或邮箱" />
              </div>
              <Button type="submit">搜索</Button>
            </form>

            <select v-model="roleFilter" class="h-10 rounded-md border border-input bg-background px-3 text-sm" @change="load(1)">
              <option value="">全部身份</option>
              <option v-for="item in roles" :key="item.value" :value="item.value">{{ item.label }}</option>
            </select>
            <Button variant="ghost" @click="resetFilters">重置</Button>
          </div>
        </div>
      </div>

      <div class="overflow-x-auto">
        <table class="w-full min-w-[860px] text-sm">
          <thead class="border-b border-border bg-muted/25 text-left text-xs text-muted-foreground">
            <tr>
              <th class="px-4 py-3">用户</th>
              <th class="px-4 py-3">当前身份</th>
              <th class="px-4 py-3">最后登录</th>
              <th class="px-4 py-3">注册时间</th>
              <th class="px-4 py-3 text-right">分配权限</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading && !result.records.length">
              <td colspan="5" class="px-4 py-10"><LoadingSkeleton type="list" :count="4" /></td>
            </tr>
            <tr v-else-if="!result.records.length">
              <td colspan="5" class="px-4 py-16 text-center">
                <Users class="mx-auto h-8 w-8 text-muted-foreground/45" />
                <p class="mt-3 font-medium">没有符合条件的账号</p>
                <p class="mt-1 text-sm text-muted-foreground">可以清除搜索条件或查看全部账号。</p>
                <Button variant="outline" size="sm" class="mt-4" @click="showAll">查看全部</Button>
              </td>
            </tr>
            <tr v-for="user in result.records" :key="user.id" class="border-b border-border/70 last:border-0 hover:bg-muted/20">
              <td class="px-4 py-4">
                <p class="font-medium">{{ user.nickname || user.username }}</p>
                <p class="mt-1 text-xs text-muted-foreground">{{ user.username }}<span v-if="user.email"> · {{ user.email }}</span></p>
              </td>
              <td class="px-4 py-4">
                <Badge variant="outline" :class="user.role === 'pending' ? 'border-amber-400/35 text-amber-300' : ''">{{ roleMeta(user.role).label }}</Badge>
              </td>
              <td class="px-4 py-4 text-muted-foreground">{{ formatDate(user.lastLoginTime) }}</td>
              <td class="px-4 py-4 text-muted-foreground">{{ formatDate(user.createdAt) }}</td>
              <td class="px-4 py-4">
                <div v-if="isSuperAdmin(user)" class="flex items-center justify-end gap-2 text-xs text-muted-foreground">
                  <ShieldCheck class="h-4 w-4 text-primary" />最高权限不可修改
                </div>
                <div v-else class="flex items-center justify-end gap-2">
                  <select v-model="pendingRoles[user.id]" class="h-9 rounded-md border border-input bg-background px-2 text-sm" :disabled="user.id === currentUserId">
                    <option v-for="item in assignableRoles" :key="item.value" :value="item.value">{{ item.label }}</option>
                  </select>
                  <Button size="sm" class="min-w-16 gap-1.5" :disabled="user.id === currentUserId || pendingRoles[user.id] === user.role || savingId === user.id" @click="saveRole(user)">
                    <Check class="h-3.5 w-3.5" />{{ savingId === user.id ? '保存中' : '保存' }}
                  </Button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="result.totalPages > 1" class="flex items-center justify-between border-t border-border px-4 py-3 text-sm text-muted-foreground">
        <span>第 {{ result.page }} / {{ result.totalPages }} 页</span>
        <div class="flex gap-2">
          <Button size="sm" variant="outline" :disabled="!result.hasPrevious || loading" @click="load(result.page - 1)">上一页</Button>
          <Button size="sm" variant="outline" :disabled="!result.hasNext || loading" @click="load(result.page + 1)">下一页</Button>
        </div>
      </div>
    </section>
  </div>
</template>
