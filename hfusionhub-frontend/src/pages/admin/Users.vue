<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RefreshCw, Search, ShieldCheck, UserCog, Users } from 'lucide-vue-next'
import * as userApi from '@/api/user'
import type { PageResult, UserInfo, UserRole } from '@/api/types'
import { useUserStore } from '@/stores/user'
import { useToast } from '@/composables/useToast'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

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
  { value: 'pending', label: '待分配', summary: '可以登录查看状态，但不能使用任何业务功能。' },
  { value: 'user', label: '普通用户', summary: '使用知识库、文档、智能对话、模型和个人记录。' },
  { value: 'builder', label: 'AI 配置员', summary: '在普通功能基础上配置回答方案、测试用例和查看回答效果。' },
  { value: 'admin', label: '超级管理员', summary: '仅保留给 admin 账号，负责分配身份和管理整个系统。' },
]
const assignableRoles = roles.filter(item => item.value !== 'admin')

const roleMeta = (role?: string) => roles.find(item => item.value === role) || roles[0]
const currentUserId = computed(() => userStore.userInfo?.id)
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
  } catch (error) {
    pendingRoles.value[user.id] = user.role
    toast.error(error instanceof Error ? error.message : '修改身份失败')
  } finally {
    savingId.value = null
  }
}

function resetFilters() {
  keyword.value = ''
  roleFilter.value = ''
  void load(1)
}

function showPending() {
  keyword.value = ''
  roleFilter.value = 'pending'
  void load(1)
}

onMounted(() => load(1))
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-6 pb-6">
    <section class="flex flex-col gap-5 rounded-xl border border-border bg-card/75 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
      <div class="flex gap-4">
        <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-primary/25 bg-primary/10 text-primary">
          <UserCog class="h-5 w-5" />
        </div>
        <div>
          <h1 class="text-2xl font-semibold">用户与权限</h1>
          <p class="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">新注册账号先等待分配。只有 admin 可以在这里开放权限，其他账号不能创建管理员。</p>
        </div>
      </div>
      <Button variant="outline" :disabled="loading" class="gap-2" @click="load()">
        <RefreshCw class="h-4 w-4" :class="loading && 'animate-spin'" />刷新
      </Button>
    </section>

    <section class="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      <article v-for="item in roles" :key="item.value" class="rounded-lg border border-border bg-card/55 p-4">
        <div class="flex items-center gap-2">
          <ShieldCheck class="h-4 w-4 text-primary" />
          <h2 class="font-medium">{{ item.label }}</h2>
        </div>
        <p class="mt-2 text-sm leading-6 text-muted-foreground">{{ item.summary }}</p>
      </article>
    </section>

    <section v-if="pendingTotal > 0" class="flex flex-col gap-3 rounded-lg border border-amber-400/25 bg-amber-400/[0.06] p-4 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <p class="font-medium text-amber-600 dark:text-amber-300">{{ pendingTotal }} 个新账号等待分配</p>
        <p class="mt-1 text-sm text-muted-foreground">选择普通用户或 AI 配置员并保存后，对方刷新页面即可开始使用。</p>
      </div>
      <Button variant="outline" @click="showPending">查看待分配账号</Button>
    </section>

    <section class="overflow-hidden rounded-xl border border-border bg-card/70">
      <div class="flex flex-col gap-3 border-b border-border p-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h2 class="font-semibold">账号列表</h2>
          <p class="mt-1 text-sm text-muted-foreground">共 {{ result.total }} 个账号</p>
        </div>
        <div class="flex flex-col gap-2 sm:flex-row">
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

      <div class="overflow-x-auto">
        <table class="w-full min-w-[820px] text-sm">
          <thead class="border-b border-border bg-muted/25 text-left text-xs text-muted-foreground">
            <tr>
              <th class="px-4 py-3">用户</th>
              <th class="px-4 py-3">当前身份</th>
              <th class="px-4 py-3">最后登录</th>
              <th class="px-4 py-3">注册时间</th>
              <th class="px-4 py-3 text-right">调整身份</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading && !result.records.length">
              <td colspan="5" class="px-4 py-16 text-center text-muted-foreground">正在加载用户...</td>
            </tr>
            <tr v-else-if="!result.records.length">
              <td colspan="5" class="px-4 py-16 text-center text-muted-foreground">
                <Users class="mx-auto mb-3 h-8 w-8 opacity-50" />没有找到符合条件的用户
              </td>
            </tr>
            <tr v-for="user in result.records" :key="user.id" class="border-b border-border/70 last:border-0">
              <td class="px-4 py-4">
                <p class="font-medium">{{ user.nickname || user.username }}</p>
                <p class="mt-1 text-xs text-muted-foreground">{{ user.username }}<span v-if="user.email"> · {{ user.email }}</span></p>
              </td>
              <td class="px-4 py-4"><Badge variant="outline">{{ roleMeta(user.role).label }}</Badge></td>
              <td class="px-4 py-4 text-muted-foreground">{{ formatDate(user.lastLoginTime) }}</td>
              <td class="px-4 py-4 text-muted-foreground">{{ formatDate(user.createdAt) }}</td>
              <td class="px-4 py-4">
                <div class="flex items-center justify-end gap-2">
                  <select
                    v-model="pendingRoles[user.id]"
                    class="h-9 rounded-md border border-input bg-background px-2 text-sm"
                    :disabled="isSuperAdmin(user) || user.id === currentUserId"
                  >
                    <option v-for="item in assignableRoles" :key="item.value" :value="item.value">{{ item.label }}</option>
                  </select>
                  <Button
                    size="sm"
                    :disabled="isSuperAdmin(user) || user.id === currentUserId || pendingRoles[user.id] === user.role || savingId === user.id"
                    @click="saveRole(user)"
                  >
                    {{ savingId === user.id ? '保存中...' : '保存' }}
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
