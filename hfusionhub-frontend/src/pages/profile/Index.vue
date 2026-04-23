<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useUserStore } from '@/stores/user'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { User, KeyRound } from 'lucide-vue-next'
import { changePassword } from '@/api/user'
import { useToast } from '@/composables/useToast'

const userStore = useUserStore()
const toast = useToast()

const form = ref({
  nickname: '',
  email: '',
  phone: '',
})
const loading = ref(false)
const successMessage = ref('')
const errorMessage = ref('')

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
  loading.value = true
  successMessage.value = ''
  errorMessage.value = ''

  const email = form.value.email.trim()
  const phone = form.value.phone.trim()
  if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    errorMessage.value = '邮箱格式不正确，请检查后重试'
    loading.value = false
    return
  }
  if (phone && !/^[0-9+\-\s]{6,20}$/.test(phone)) {
    errorMessage.value = '手机号格式不正确，请检查后重试'
    loading.value = false
    return
  }

  try {
    await userStore.updateUserInfo({
      nickname: form.value.nickname.trim(),
      email: email || undefined,
      phone: phone || undefined,
    })
    successMessage.value = '更新成功'
  } catch (e: any) {
    errorMessage.value = e.message || '更新失败'
  } finally {
    loading.value = false
  }
}

// ── 修改密码 ──
const passwordForm = ref({ oldPassword: '', newPassword: '', confirmPassword: '' })
const passwordLoading = ref(false)
const passwordMessage = ref('')

const handleChangePassword = async () => {
  passwordMessage.value = ''
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
    passwordMessage.value = '密码已更新，下次登录请使用新密码'
    toast.success('密码已更新')
  } catch (e: any) {
    toast.error(e.message || '密码修改失败')
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
      <p class="text-muted-foreground">管理您的个人信息</p>
    </div>

    <div class="grid gap-6 md:grid-cols-2">
      <!-- 个人信息 -->
      <Card>
        <CardHeader>
          <CardTitle>个人信息</CardTitle>
          <CardDescription>更新您的个人资料</CardDescription>
        </CardHeader>
        <CardContent class="space-y-4">
          <div class="flex items-center gap-4">
            <div class="flex h-16 w-16 items-center justify-center rounded-full bg-primary text-primary-foreground">
              <User class="h-8 w-8" />
            </div>
            <div>
              <p class="font-medium">{{ userStore.nickname || userStore.username }}</p>
              <p class="text-sm text-muted-foreground">{{ userStore.username }}</p>
            </div>
          </div>
          <div class="space-y-2">
            <Label for="nickname">昵称</Label>
            <Input
              id="nickname"
              v-model="form.nickname"
              placeholder="请输入昵称"
              :disabled="loading"
            />
          </div>
          <div class="space-y-2">
            <Label for="email">邮箱</Label>
            <Input
              id="email"
              v-model="form.email"
              type="email"
              placeholder="请输入邮箱"
              :disabled="loading"
            />
          </div>
          <div class="space-y-2">
            <Label for="phone">手机号</Label>
            <Input
              id="phone"
              v-model="form.phone"
              placeholder="请输入手机号"
              :disabled="loading"
            />
          </div>
          <div v-if="successMessage" class="text-sm text-green-500">
            {{ successMessage }}
          </div>
          <div v-if="errorMessage" class="text-sm text-destructive">
            {{ errorMessage }}
          </div>
          <Button :disabled="loading" @click="handleUpdate">
            {{ loading ? '保存中...' : '保存修改' }}
          </Button>
        </CardContent>
      </Card>

      <!-- 账户信息 -->
      <Card>
        <CardHeader>
          <CardTitle>账户信息</CardTitle>
          <CardDescription>查看您的账户详情</CardDescription>
        </CardHeader>
        <CardContent class="space-y-4">
          <div class="space-y-2">
            <Label>账号编号</Label>
            <p class="text-sm text-muted-foreground">{{ userStore.userInfo?.id }}</p>
          </div>
          <div class="space-y-2">
            <Label>用户名</Label>
            <p class="text-sm text-muted-foreground">{{ userStore.userInfo?.username }}</p>
          </div>
          <div class="space-y-2">
            <Label>注册时间</Label>
            <p class="text-sm text-muted-foreground">
              {{ userStore.userInfo?.createdAt ? new Date(userStore.userInfo.createdAt).toLocaleDateString() : '-' }}
            </p>
          </div>
          <div class="space-y-2">
            <Label>账户状态</Label>
            <p class="text-sm text-muted-foreground">
              {{ userStore.userInfo?.status === 0 ? '正常' : '禁用' }}
            </p>
          </div>
        </CardContent>
      </Card>

      <!-- 修改密码 -->
      <Card class="md:col-span-2">
        <CardHeader>
          <CardTitle class="flex items-center gap-2"><KeyRound class="h-4 w-4 text-primary" />修改密码</CardTitle>
          <CardDescription>定期更换密码有助于保护账户安全</CardDescription>
        </CardHeader>
        <CardContent class="space-y-4">
          <div class="grid gap-4 md:grid-cols-3">
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
          <p v-if="passwordMessage" class="text-sm text-emerald-500">{{ passwordMessage }}</p>
          <Button :disabled="passwordLoading" @click="handleChangePassword">
            {{ passwordLoading ? '提交中...' : '更新密码' }}
          </Button>
        </CardContent>
      </Card>
    </div>
  </div>
</template>
