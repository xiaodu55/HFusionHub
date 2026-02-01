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
})
const loading = ref(false)
const error = ref('')

const handleRegister = async () => {
  if (!form.value.username || !form.value.password) {
    error.value = '请输入用户名和密码'
    return
  }

  if (form.value.password !== form.value.confirmPassword) {
    error.value = '两次输入的密码不一致'
    return
  }

  if (form.value.password.length < 6) {
    error.value = '密码长度不能少于6位'
    return
  }

  loading.value = true
  error.value = ''

  try {
    await userStore.register({
      username: form.value.username,
      password: form.value.password,
      nickname: form.value.nickname || undefined,
    })
    router.push('/login')
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
            placeholder="请输入用户名"
            :disabled="loading"
          />
        </div>
        <div class="space-y-2">
          <Label for="nickname">昵称</Label>
          <Input
            id="nickname"
            v-model="form.nickname"
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
            placeholder="请输入密码（至少6位）"
            :disabled="loading"
          />
        </div>
        <div class="space-y-2">
          <Label for="confirmPassword">确认密码 *</Label>
          <Input
            id="confirmPassword"
            v-model="form.confirmPassword"
            type="password"
            placeholder="请再次输入密码"
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
