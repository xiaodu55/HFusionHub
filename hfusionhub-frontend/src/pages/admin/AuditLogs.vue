<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ClipboardList, RefreshCw, ScrollText } from 'lucide-vue-next'
import * as auditApi from '@/api/audit'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import LoadingSkeleton from '@/components/LoadingSkeleton.vue'
import { useToast } from '@/composables/useToast'
import { formatDateTime } from '@/utils/date'
import { friendlyErrorMessage } from '@/utils/errorMessage'

const toast = useToast()
const tab = ref<'operations' | 'crossTenant'>('operations')
const loading = ref(false)
const operations = ref<auditApi.AuditLogEntry[]>([])
const crossTenant = ref<auditApi.CrossTenantAuditEntry[]>([])
const actionFilter = ref('')

const load = async () => {
  loading.value = true
  try {
    if (tab.value === 'operations') {
      const res = await auditApi.listOperationAudits({
        limit: 100,
        action: actionFilter.value || undefined,
      })
      operations.value = res.data || []
    } else {
      const res = await auditApi.listCrossTenantAudits(100)
      crossTenant.value = res.data || []
    }
  } catch (e) {
    toast.error(friendlyErrorMessage(e, '加载审计日志失败'))
  } finally {
    loading.value = false
  }
}

const switchTab = (t: 'operations' | 'crossTenant') => {
  tab.value = t
  load()
}

onMounted(load)
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="flex items-center gap-2 text-2xl font-semibold">
          <ScrollText class="h-6 w-6 text-primary" /> 审计日志
        </h1>
        <p class="mt-1 text-sm text-muted-foreground">敏感操作与跨租户代操作记录（平台管理员）</p>
      </div>
      <Button variant="outline" class="gap-2" @click="load">
        <RefreshCw class="h-4 w-4" :class="loading && 'animate-spin'" /> 刷新
      </Button>
    </div>

    <div class="flex items-center gap-2">
      <Button
        size="sm"
        :variant="tab === 'operations' ? 'default' : 'outline'"
        @click="switchTab('operations')"
      >
        <ClipboardList class="mr-1 h-4 w-4" /> 操作审计
      </Button>
      <Button
        size="sm"
        :variant="tab === 'crossTenant' ? 'default' : 'outline'"
        @click="switchTab('crossTenant')"
      >
        跨租户代操作
      </Button>
      <Input
        v-if="tab === 'operations'"
        v-model="actionFilter"
        placeholder="按动作过滤（如 app.publish）"
        class="ml-auto max-w-64 h-9"
        @keyup.enter="load"
      />
    </div>

    <Card>
      <CardHeader class="pb-3">
        <CardTitle class="text-base">{{ tab === 'operations' ? '操作审计' : '跨租户代操作审计' }}</CardTitle>
        <CardDescription class="text-xs">
          {{ tab === 'operations' ? '应用/API Key/共享/公告等敏感操作的审计记录' : '平台管理员代其他租户执行操作的记录' }}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div v-if="loading" class="space-y-2"><LoadingSkeleton type="card" :count="3" /></div>
        <div v-else-if="(tab === 'operations' ? operations : crossTenant).length === 0" class="py-10 text-center text-sm text-muted-foreground">
          暂无审计记录
        </div>
        <div v-else class="space-y-2">
          <template v-if="tab === 'operations'">
            <div
              v-for="log in operations"
              :key="log.id"
              class="flex items-center gap-3 rounded-md border bg-muted/20 px-3 py-2 text-sm"
            >
              <Badge variant="outline" class="shrink-0 font-mono">{{ log.action }}</Badge>
              <span class="min-w-0 flex-1 truncate text-muted-foreground">
                {{ log.detail || `${log.targetType}${log.targetId ? '#' + log.targetId : ''}` }}
              </span>
              <span class="shrink-0 text-xs text-muted-foreground">操作人 #{{ log.operatorId }}</span>
              <span class="shrink-0 text-xs text-muted-foreground">{{ formatDateTime(log.createdAt || '') }}</span>
            </div>
          </template>
          <template v-else>
            <div
              v-for="log in crossTenant"
              :key="log.id"
              class="flex items-center gap-3 rounded-md border bg-muted/20 px-3 py-2 text-sm"
            >
              <Badge variant="outline" class="shrink-0 font-mono">{{ log.action }}</Badge>
              <span class="min-w-0 flex-1 truncate text-muted-foreground">
                租户 {{ log.fromTenant }} → 租户 {{ log.toTenant }}
              </span>
              <span class="shrink-0 text-xs text-muted-foreground">操作人 #{{ log.operatorId }}</span>
              <span class="shrink-0 text-xs text-muted-foreground">{{ formatDateTime(log.createdAt || '') }}</span>
            </div>
          </template>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
