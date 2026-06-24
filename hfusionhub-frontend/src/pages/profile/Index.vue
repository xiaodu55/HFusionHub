<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useUserStore } from '@/stores/user'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { KeyRound, IdCard, Mail, Phone, CalendarDays, Clock3, ShieldCheck, ShieldAlert, Fingerprint, Camera, Loader2 } from 'lucide-vue-next'
import { changePassword, uploadAvatar } from '@/api/user'
import type { UserRole } from '@/api/types'
import { useToast } from '@/composables/useToast'

const userStore = useUserStore()
const toast = useToast()

const form = ref({
  nickname: '',
  email: '',
  phone: '',
})
const loading = ref(false)

// ── 身份横幅 ──
const displayName = computed(() => userStore.nickname || userStore.username || '')
const avatarInitial = computed(() => displayName.value.trim().charAt(0).toUpperCase() || '·')

const AVATAR_GRADIENTS = [
  'from-violet-500 to-indigo-600',
  'from-sky-500 to-blue-600',
  'from-emerald-500 to-teal-600',
  'from-amber-500 to-orange-600',
  'from-rose-500 to-pink-600',
]
const avatarGradient = computed(() => {
  const seed = (userStore.username || '').split('').reduce((acc, c) => acc + c.charCodeAt(0), 0)
  return AVATAR_GRADIENTS[seed % AVATAR_GRADIENTS.length]
})

const ROLE_META: Record<UserRole, { label: string; class: string }> = {
  admin: { label: '超级管理员', class: 'border-violet-400/40 bg-violet-400/10 text-violet-600 dark:text-violet-300' },
  builder: { label: '构建者', class: 'border-sky-400/40 bg-sky-400/10 text-sky-600 dark:text-sky-300' },
  user: { label: '普通用户', class: 'border-emerald-400/40 bg-emerald-400/10 text-emerald-600 dark:text-emerald-300' },
  pending: { label: '待审批', class: 'border-amber-400/40 bg-amber-400/10 text-amber-600 dark:text-amber-300' },
}
const roleMeta = computed(() => ROLE_META[userStore.role] ?? ROLE_META.pending)
const isAccountActive = computed(() => userStore.userInfo?.status === 0)

const formatDate = (value?: string) => {
  if (!value) return '—'
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}
const formatDateTime = (value?: string) => {
  if (!value) return '—'
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

// ── 头像上传 ──
// 版本时间戳：上传成功后拼到 URL 防浏览器缓存
const avatarTs = ref(Date.now())
const avatarUploading = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const avatarUrl = computed(() =>
  userStore.userInfo?.avatar ? `${userStore.userInfo.avatar}?t=${avatarTs.value}` : ''
)

const triggerAvatarUpload = () => {
  fileInput.value?.click()
}

const onAvatarFileChange = async (e: Event) => {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  // 允许重复选择同一文件
  input.value = ''
  if (!file) return
  if (!['image/jpeg', 'image/png', 'image/webp', 'image/gif'].includes(file.type)) {
    toast.error('仅支持 JPG / PNG / WEBP / GIF 格式图片')
    return
  }
  if (file.size > 2 * 1024 * 1024) {
    toast.error('头像图片不能超过 2MB')
    return
  }
  avatarUploading.value = true
  try {
    await uploadAvatar(file)
    avatarTs.value = Date.now()
    await userStore.getUserInfo()
    toast.success('头像已更新')
  } catch (err) {
    toast.error(err instanceof Error ? err.message : '头像上传失败')
  } finally {
    avatarUploading.value = false
  }
}

// ── 个人信息编辑 ──
const loadUserInfo = () => {
  if (userStore.userInfo) {
    form.value = {
      nickname: userStore.userInfo.nickname || '',
      email: userStore.userInfo.email || '',
      phone: userStore.userInfo.phone || '',
    }
  }
}

const handleUpdate = async () => {
  const email = form.value.email.trim()
  const phone = form.value.phone.trim()
  if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    toast.error('邮箱格式不正确，请检查后重试')
    return
  }
  if (phone && !/^[0-9+\-\s]{6,20}$/.test(phone)) {
    toast.error('手机号格式不正确，请检查后重试')
    return
  }

  loading.value = true
  try {
    await userStore.updateUserInfo({
      nickname: form.value.nickname.trim(),
      email: email || undefined,
      phone: phone || undefined,
    })
    toast.success('个人信息已更新')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : '更新失败')
  } finally {
    loading.value = false
  }
}

// ── 修改密码 ──
const passwordForm = ref({ oldPassword: '', newPassword: '', confirmPassword: '' })
const passwordLoading = ref(false)

const handleChangePassword = async () => {
  const { oldPassword, newPassword, confirmPassword } = passwordForm.value
  if (!oldPassword || !newPassword) {
    toast.error('请填写当前密码和新密码')
    return
  }
  if (newPassword.length < 6 || newPassword.length > 64) {
    toast.error('新密码长度需在 6-64 位之间')
    return
  }
  if (newPassword !== confirmPassword) {
    toast.error('两次输入的新密码不一致')
    return
  }
  passwordLoading.value = true
  try {
    await changePassword({ oldPassword, newPassword })
    passwordForm.value = { oldPassword: '', newPassword: '', confirmPassword: '' }
    toast.success('密码已更新，下次登录请使用新密码')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : '密码修改失败')
  } finally {
    passwordLoading.value = false
  }
}

onMounted(() => {
  loadUserInfo()
})
</script>

<template>
  <div class="space-y-6">
    <div>
      <h2 class="text-2xl font-bold">个人中心</h2>
      <p class="text-muted-foreground">管理您的个人信息与账户安全</p>
    </div>

    <!-- 身份横幅 -->
    <Card class="overflow-hidden border-0 bg-gradient-to-r from-primary/10 via-primary/5 to-transparent">
      <CardContent class="flex flex-wrap items-center gap-5 py-6">
        <button
          type="button"
          class="group relative h-20 w-20 shrink-0 overflow-hidden rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          :aria-label="avatarUrl ? '更换头像' : '上传头像'"
          :disabled="avatarUploading"
          @click="triggerAvatarUpload"
        >
          <img
            v-if="avatarUrl"
            :src="avatarUrl"
            alt="头像"
            class="h-full w-full object-cover"
          />
          <span
            v-else
            :class="[
              'flex h-full w-full items-center justify-center bg-gradient-to-br text-3xl font-bold text-white shadow-md',
              avatarGradient
            ]"
          >
            {{ avatarInitial }}
          </span>
          <span
            v-if="!avatarUrl"
            class="pointer-events-none absolute inset-x-0 bottom-0 bg-black/45 py-0.5 text-center text-[10px] font-medium text-white opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100"
          >
            {{ avatarUploading ? '上传中…' : '上传头像' }}
          </span>
          <!-- 常驻相机徽章：不依赖悬停即可发现上传入口 -->
          <span
            class="absolute -right-1 -top-1 flex h-7 w-7 items-center justify-center rounded-full border-2 border-card bg-primary text-primary-foreground shadow-md"
          >
            <Camera v-if="!avatarUploading" class="h-3.5 w-3.5" />
            <Loader2 v-else class="h-3.5 w-3.5 animate-spin" />
          </span>
        </button>
        <input
          ref="fileInput"
          type="file"
          accept="image/jpeg,image/png,image/webp,image/gif"
          class="hidden"
          @change="onAvatarFileChange"
        >
        <div class="min-w-0 flex-1">
          <div class="flex flex-wrap items-center gap-2.5">
            <h3 class="truncate text-xl font-semibold">{{ displayName }}</h3>
            <Badge variant="outline" :class="roleMeta.class">{{ roleMeta.label }}</Badge>
            <Badge variant="outline" :class="isAccountActive
              ? 'border-emerald-400/40 bg-emerald-400/10 text-emerald-600 dark:text-emerald-300'
              : 'border-red-400/40 bg-red-400/10 text-red-600 dark:text-red-300'">
              <component :is="isAccountActive ? ShieldCheck : ShieldAlert" class="mr-1 h-3 w-3" />
              {{ isAccountActive ? '账户正常' : '已禁用' }}
            </Badge>
          </div>
          <p class="mt-1.5 text-sm text-muted-foreground">
            @{{ userStore.username }}
            <span class="ml-2 text-xs">· 点击左侧头像可上传 / 更换头像（支持 JPG / PNG / WEBP / GIF，≤2MB）</span>
          </p>
        </div>
        <div class="grid shrink-0 grid-cols-2 gap-x-8 gap-y-2 text-sm">
          <div class="flex items-center gap-2 text-muted-foreground">
            <CalendarDays class="h-4 w-4" /> 注册于
            <span class="tabular-nums text-foreground">{{ formatDate(userStore.userInfo?.createdAt) }}</span>
          </div>
          <div class="flex items-center gap-2 text-muted-foreground">
            <Clock3 class="h-4 w-4" /> 最近登录
            <span class="tabular-nums text-foreground">{{ formatDateTime(userStore.userInfo?.lastLoginTime) }}</span>
          </div>
        </div>
      </CardContent>
    </Card>

    <div class="grid gap-6 md:grid-cols-2">
      <!-- 个人信息编辑 -->
      <Card>
        <CardHeader>
          <CardTitle>个人信息</CardTitle>
          <CardDescription>更新您的联系方式与昵称</CardDescription>
        </CardHeader>
        <CardContent class="space-y-4">
          <div class="space-y-2">
            <Label for="nickname">昵称</Label>
            <Input id="nickname" v-model="form.nickname" placeholder="请输入昵称" :disabled="loading" />
          </div>
          <div class="space-y-2">
            <Label for="email">
              <Mail class="inline h-3.5 w-3.5" /> 邮箱
            </Label>
            <Input id="email" v-model="form.email" type="email" placeholder="用于接收通知" :disabled="loading" />
          </div>
          <div class="space-y-2">
            <Label for="phone">
              <Phone class="inline h-3.5 w-3.5" /> 手机号
            </Label>
            <Input id="phone" v-model="form.phone" placeholder="请输入手机号" :disabled="loading" />
          </div>
          <Button :disabled="loading" @click="handleUpdate">
            {{ loading ? '保存中...' : '保存修改' }}
          </Button>
        </CardContent>
      </Card>

      <!-- 账户详情（只读键值列表） -->
      <Card>
        <CardHeader>
          <CardTitle>账户详情</CardTitle>
          <CardDescription>由系统维护，不可修改</CardDescription>
        </CardHeader>
        <CardContent>
          <dl class="divide-y divide-border text-sm">
            <div class="flex items-center justify-between py-3 first:pt-0">
              <dt class="flex items-center gap-2 text-muted-foreground">
                <Fingerprint class="h-4 w-4" /> 用户 ID
              </dt>
              <dd class="font-medium tabular-nums">{{ userStore.userInfo?.id ?? '—' }}</dd>
            </div>
            <div class="flex items-center justify-between py-3">
              <dt class="flex items-center gap-2 text-muted-foreground">
                <IdCard class="h-4 w-4" /> 用户名
              </dt>
              <dd class="font-medium">{{ userStore.userInfo?.username || '—' }}</dd>
            </div>
            <div class="flex items-center justify-between py-3">
              <dt class="flex items-center gap-2 text-muted-foreground">
                <ShieldCheck class="h-4 w-4" /> 角色
              </dt>
              <dd>
                <Badge variant="outline" :class="roleMeta.class">{{ roleMeta.label }}</Badge>
              </dd>
            </div>
            <div class="flex items-center justify-between py-3">
              <dt class="flex items-center gap-2 text-muted-foreground">
                <CalendarDays class="h-4 w-4" /> 注册时间
              </dt>
              <dd class="font-medium tabular-nums">{{ formatDate(userStore.userInfo?.createdAt) }}</dd>
            </div>
            <div class="flex items-center justify-between py-3 last:pb-0">
              <dt class="flex items-center gap-2 text-muted-foreground">
                <Clock3 class="h-4 w-4" /> 最近登录
              </dt>
              <dd class="font-medium tabular-nums">{{ formatDateTime(userStore.userInfo?.lastLoginTime) }}</dd>
            </div>
          </dl>
        </CardContent>
      </Card>
    </div>

    <!-- 修改密码 -->
    <Card>
      <CardHeader>
        <CardTitle class="flex items-center gap-2">
          <KeyRound class="h-4 w-4 text-primary" /> 修改密码
        </CardTitle>
        <CardDescription>定期更换密码有助于保护账户安全；更新后当前登录不受影响</CardDescription>
      </CardHeader>
      <CardContent>
        <div class="grid gap-5 md:grid-cols-3">
          <div class="space-y-2">
            <Label for="old-password">当前密码</Label>
            <Input id="old-password" v-model="passwordForm.oldPassword" type="password" placeholder="请输入当前密码" :disabled="passwordLoading" />
          </div>
          <div class="space-y-2">
            <Label for="new-password">新密码</Label>
            <Input id="new-password" v-model="passwordForm.newPassword" type="password" placeholder="6-64 位" :disabled="passwordLoading" />
          </div>
          <div class="space-y-2">
            <Label for="confirm-password">确认新密码</Label>
            <Input id="confirm-password" v-model="passwordForm.confirmPassword" type="password" placeholder="再次输入新密码" :disabled="passwordLoading" @keyup.enter="handleChangePassword" />
          </div>
        </div>
        <div class="mt-5 flex justify-end border-t pt-4">
          <Button :disabled="passwordLoading" @click="handleChangePassword">
            {{ passwordLoading ? '提交中...' : '更新密码' }}
          </Button>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
