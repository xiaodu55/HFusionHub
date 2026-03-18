<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, Moon, Palette, Settings2, ShieldCheck, Sun, UserRound } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useTheme } from '@/composables/useTheme'

const router = useRouter()
const { isDarkMode, initializeTheme, setTheme } = useTheme()

onMounted(initializeTheme)
</script>

<template>
  <div class="mx-auto max-w-5xl space-y-6 pb-4">
    <section class="rounded-2xl border border-border bg-card/80 p-5 shadow-[0_18px_45px_rgba(0,0,0,0.18)] sm:p-6">
      <div class="flex items-center gap-4"><div class="flex h-11 w-11 items-center justify-center rounded-xl border border-primary/25 bg-primary/10 text-primary"><Settings2 class="h-5 w-5" /></div><div><p class="text-xs font-medium tracking-[0.16em] text-primary/90">PREFERENCES</p><h1 class="mt-1 text-2xl font-semibold">设置</h1><p class="mt-1 text-sm text-muted-foreground">管理界面偏好和常用账户入口。</p></div></div>
    </section>

    <div class="grid gap-6 lg:grid-cols-2">
      <Card class="border-border bg-card/80"><CardHeader><div class="flex items-center gap-2"><Palette class="h-4 w-4 text-primary" /><CardTitle class="text-base">外观</CardTitle></div><CardDescription>主题会保存在当前浏览器中。</CardDescription></CardHeader><CardContent><div class="grid grid-cols-2 gap-3"><button class="rounded-xl border p-4 text-left transition-colors" :class="!isDarkMode ? 'border-primary/50 bg-primary/[0.08]' : 'border-border bg-muted/25 hover:bg-muted/40'" @click="setTheme(false)"><Sun class="h-5 w-5 text-amber-300" /><p class="mt-3 text-sm font-medium">浅色主题</p><p class="mt-1 text-xs text-muted-foreground">明亮、适合白天使用</p></button><button class="rounded-xl border p-4 text-left transition-colors" :class="isDarkMode ? 'border-primary/50 bg-primary/[0.08]' : 'border-border bg-muted/25 hover:bg-muted/40'" @click="setTheme(true)"><Moon class="h-5 w-5 text-cyan-200" /><p class="mt-3 text-sm font-medium">深色主题</p><p class="mt-1 text-xs text-muted-foreground">低亮度、适合长时间阅读</p></button></div></CardContent></Card>

      <Card class="border-border bg-card/80"><CardHeader><div class="flex items-center gap-2"><UserRound class="h-4 w-4 text-primary" /><CardTitle class="text-base">账户</CardTitle></div><CardDescription>更新昵称、邮箱和手机号。</CardDescription></CardHeader><CardContent><Button variant="outline" class="w-full justify-between" @click="router.push('/profile')"><span>打开个人中心</span><ArrowRight class="h-4 w-4" /></Button></CardContent></Card>

      <Card class="border-border bg-card/80 lg:col-span-2"><CardHeader><div class="flex items-center gap-2"><ShieldCheck class="h-4 w-4 text-primary" /><CardTitle class="text-base">AI 高级能力</CardTitle></div><CardDescription>查看混合检索、OCR、图谱和多 Agent 等可选能力的影响与部署要求。</CardDescription></CardHeader><CardContent><Button variant="outline" class="w-full justify-between" @click="router.push('/admin/flags')"><span>打开高级能力说明</span><ArrowRight class="h-4 w-4" /></Button></CardContent></Card>
    </div>
  </div>
</template>
