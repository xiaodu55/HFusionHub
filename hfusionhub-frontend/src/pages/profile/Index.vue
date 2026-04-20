<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useUserStore } from '@/stores/user'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { User } from 'lucide-vue-next'

const userStore = useUserStore()

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
            <Label>用户ID</Label>
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
    </div>
  </div>
</template>
