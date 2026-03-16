<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'

const router = useRouter()
const userStore = useUserStore()

const form = ref({
  username: '',
  password: '',
  confirmPassword: '',
  nickname: '',
  email: '',
  phone: '',
})
const loading = ref(false)
const error = ref('')

const handleRegister = async () => {
  const username = form.value.username.trim()
  const nickname = form.value.nickname.trim()
  const email = form.value.email.trim().toLowerCase()
  const phone = form.value.phone.trim()

  if (!username || !form.value.password) {
    error.value = '请输入用户名和密码'
    return
  }

  if (!/^[\p{L}\p{N}_-]{3,50}$/u.test(username)) {
    error.value = '用户名需为3-50位文字、数字、下划线或短横线'
    return
  }

  if (form.value.password !== form.value.confirmPassword) {
    error.value = '两次输入的密码不一致'
    return
  }

  if (form.value.password.length < 8 || !/[A-Za-z]/.test(form.value.password) || !/\d/.test(form.value.password)) {
    error.value = '密码至少8位，且必须同时包含字母和数字'
    return
  }

  if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    error.value = '请输入正确的邮箱地址'
    return
  }

  if (phone && !/^\+?[1-9]\d{6,14}$/.test(phone)) {
    error.value = '请输入正确的手机号'
    return
  }

  loading.value = true
  error.value = ''

  try {
    await userStore.register({
      username,
      password: form.value.password,
      nickname: nickname || undefined,
      email: email || undefined,
      phone: phone || undefined,
    })
    router.replace({ path: '/login', query: { registered: '1' } })
  } catch (e: any) {
    error.value = e.message || '注册失败'
  } finally {
    loading.value = false
  }
}

const goToLogin = () => {
  router.push('/login')
}
</script>

<template>
  <div class="flex min-h-screen items-center justify-center bg-background p-4">
    <Card class="w-full max-w-md">
      <CardHeader class="space-y-1 text-center">
        <CardTitle class="text-2xl font-bold">HFusionHub</CardTitle>
        <CardDescription>创建新账号</CardDescription>
      </CardHeader>
      <CardContent class="space-y-4">
        <div class="space-y-2">
          <Label for="username">用户名 *</Label>
          <Input
            id="username"
            v-model="form.username"
            autocomplete="username"
            maxlength="50"
            placeholder="3-50位，支持文字、数字、_ 和 -"
            :disabled="loading"
          />
        </div>
        <div class="space-y-2">
          <Label for="nickname">昵称</Label>
          <Input
            id="nickname"
            v-model="form.nickname"
            autocomplete="nickname"
            maxlength="50"
            placeholder="请输入昵称（可选）"
            :disabled="loading"
          />
        </div>
        <div class="space-y-2">
          <Label for="password">密码 *</Label>
          <Input
            id="password"
            v-model="form.password"
            type="password"
            autocomplete="new-password"
            maxlength="72"
            placeholder="至少8位，包含字母和数字"
            :disabled="loading"
          />
        </div>
        <div class="space-y-2">
          <Label for="confirmPassword">确认密码 *</Label>
          <Input
            id="confirmPassword"
            v-model="form.confirmPassword"
            type="password"
            autocomplete="new-password"
            maxlength="72"
            placeholder="请再次输入密码"
            :disabled="loading"
            @keyup.enter="handleRegister"
          />
        </div>
        <div class="space-y-2">
          <Label for="email">邮箱</Label>
          <Input
            id="email"
            v-model="form.email"
            type="email"
            autocomplete="email"
            maxlength="100"
            placeholder="请输入邮箱（可选）"
            :disabled="loading"
          />
        </div>
        <div class="space-y-2">
          <Label for="phone">手机号</Label>
          <Input
            id="phone"
            v-model="form.phone"
            type="tel"
            autocomplete="tel"
            maxlength="15"
            placeholder="请输入手机号（可选）"
            :disabled="loading"
            @keyup.enter="handleRegister"
          />
        </div>
        <div v-if="error" class="text-sm text-destructive">
          {{ error }}
        </div>
      </CardContent>
      <CardFooter class="flex flex-col gap-4">
        <Button class="w-full" :disabled="loading" @click="handleRegister">
          {{ loading ? '注册中...' : '注册' }}
        </Button>
        <div class="text-center text-sm text-muted-foreground">
          已有账号？
          <Button variant="link" class="p-0" @click="goToLogin">
            立即登录
          </Button>
        </div>
      </CardFooter>
    </Card>
  </div>
</template>
