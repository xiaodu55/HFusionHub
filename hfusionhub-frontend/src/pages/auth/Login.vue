<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const form = ref({
  username: '',
  password: '',
})
const loading = ref(false)
const error = ref('')
const registered = computed(() => route.query.registered === '1')

const handleLogin = async () => {
  if (!form.value.username || !form.value.password) {
    error.value = '请输入用户名和密码'
    return
  }

  loading.value = true
  error.value = ''

  try {
    await userStore.login(form.value.username, form.value.password)
    router.push('/')
  } catch (e: any) {
    error.value = e.message || '登录失败'
  } finally {
    loading.value = false
  }
}

const goToRegister = () => {
  router.push('/register')
}
</script>

<template>
  <div class="flex min-h-screen items-center justify-center bg-background p-4">
    <Card class="w-full max-w-md">
      <CardHeader class="space-y-1 text-center">
        <CardTitle class="text-2xl font-bold">HFusionHub</CardTitle>
        <CardDescription>AI Agent 智能平台</CardDescription>
      </CardHeader>
      <CardContent class="space-y-4">
        <div v-if="registered" class="text-sm text-emerald-600 dark:text-emerald-400">
          注册成功，请使用新账号登录
        </div>
        <div class="space-y-2">
          <Label for="username">用户名</Label>
          <Input
            id="username"
            v-model="form.username"
            placeholder="请输入用户名"
            :disabled="loading"
          />
        </div>
        <div class="space-y-2">
          <Label for="password">密码</Label>
          <Input
            id="password"
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            :disabled="loading"
            @keyup.enter="handleLogin"
          />
        </div>
        <div v-if="error" class="text-sm text-destructive">
          {{ error }}
        </div>
      </CardContent>
      <CardFooter class="flex flex-col gap-4">
        <Button class="w-full" :disabled="loading" @click="handleLogin">
          {{ loading ? '登录中...' : '登录' }}
        </Button>
        <div class="text-center text-sm text-muted-foreground">
          还没有账号？
          <Button variant="link" class="p-0" @click="goToRegister">
            立即注册
          </Button>
        </div>
      </CardFooter>
    </Card>
  </div>
</template>
