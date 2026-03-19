<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import * as knowledgeBaseApi from '@/api/knowledgeBase'
import type { KnowledgeBase } from '@/api/types'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Plus, Search, Edit, Trash2, BookOpen, Power, PowerOff, Loader2, ArrowRight, FileText, FolderOpen } from 'lucide-vue-next'
import { formatDateTime } from '@/utils/date'
import { useToast } from '@/composables/useToast'
import EmptyState from '@/components/EmptyState.vue'
import LoadingSkeleton from '@/components/LoadingSkeleton.vue'
import ErrorState from '@/components/ErrorState.vue'

const router = useRouter()
const toast = useToast()

const knowledgeBases = ref<KnowledgeBase[]>([])
const loading = ref(false)
const loadError = ref(false)
const searchQuery = ref('')
const isCreateDialogOpen = ref(false)
const isEditDialogOpen = ref(false)
const isDeleteDialogOpen = ref(false)
const currentItem = ref<KnowledgeBase | null>(null)
const statusUpdatingId = ref<number | null>(null)

const createForm = ref({
  name: '',
  description: '',
})

const editForm = ref({
  name: '',
  description: '',
})

const loadKnowledgeBases = async () => {
  loading.value = true
  loadError.value = false
  try {
    const res = await knowledgeBaseApi.getMyKnowledgeBaseList({
      page: 1,
      pageSize: 100,
    })
    knowledgeBases.value = res.data.records
  } catch (error) {
    console.error('加载知识库失败:', error)
    loadError.value = true
    toast.error('加载知识库失败，请检查网络连接后重试')
  } finally {
    loading.value = false
  }
}

const handleCreate = async () => {
  if (!createForm.value.name) return

  try {
    await knowledgeBaseApi.createKnowledgeBase(createForm.value)
    isCreateDialogOpen.value = false
    createForm.value = { name: '', description: '' }
    await loadKnowledgeBases()
  } catch (error) {
    console.error('创建知识库失败:', error)
    toast.error('创建知识库失败，请稍后重试')
  }
}

const handleCreateDialogOpen = () => {
  isCreateDialogOpen.value = true
}

const handleEdit = (item: KnowledgeBase) => {
  currentItem.value = item
  editForm.value = { name: item.name, description: item.description }
  isEditDialogOpen.value = true
}

const handleUpdate = async () => {
  if (!currentItem.value || !editForm.value.name) return

  try {
    await knowledgeBaseApi.updateKnowledgeBase(currentItem.value.id, editForm.value)
    isEditDialogOpen.value = false
    await loadKnowledgeBases()
  } catch (error) {
    console.error('更新知识库失败:', error)
  }
}

const handleToggleStatus = async (item: KnowledgeBase) => {
  if (item.status !== 0 && item.status !== 1) return

  statusUpdatingId.value = item.id
  try {
    await knowledgeBaseApi.updateKnowledgeBase(item.id, {
      status: item.status === 0 ? 1 : 0,
    })
    await loadKnowledgeBases()
  } catch (error) {
    console.error('更新知识库状态失败', error)
  } finally {
    statusUpdatingId.value = null
  }
}

const handleDelete = (item: KnowledgeBase) => {
  currentItem.value = item
  isDeleteDialogOpen.value = true
}

const confirmDelete = async () => {
  if (!currentItem.value) return

  try {
    await knowledgeBaseApi.deleteKnowledgeBase(currentItem.value.id)
    isDeleteDialogOpen.value = false
    await loadKnowledgeBases()
  } catch (error) {
    console.error('删除知识库失败:', error)
  }
}

const goToDetail = (id: number) => {
  router.push(`/knowledge-base/${id}`)
}

const filteredKnowledgeBases = computed(() => {
  if (!searchQuery.value) return knowledgeBases.value
  return knowledgeBases.value.filter(
    (kb) =>
      kb.name.toLowerCase().includes(searchQuery.value.toLowerCase()) ||
      kb.description?.toLowerCase().includes(searchQuery.value.toLowerCase())
  )
})

onMounted(() => {
  loadKnowledgeBases()
})
</script>

<template>
  <div class="space-y-6 pb-4">
    <section class="relative overflow-hidden rounded-2xl border border-border bg-card/80 shadow-[0_18px_45px_rgba(0,0,0,0.18)]">
      <div class="pointer-events-none absolute -right-12 -top-16 h-48 w-48 rounded-full bg-primary/10 blur-3xl" />
      <div class="relative flex flex-col gap-5 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
        <div class="flex gap-4"><div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-primary/25 bg-primary/10 text-primary"><BookOpen class="h-5 w-5" /></div><div><p class="text-xs font-medium tracking-[0.16em] text-primary/90">KNOWLEDGE SPACES</p><h2 class="mt-1 text-2xl font-semibold tracking-tight">知识库</h2><p class="mt-1 text-sm leading-6 text-muted-foreground">为 AI 组织可靠的业务资料；文档完成解析后即可在对话中被引用。</p></div></div>
        <Button class="shrink-0 gap-2" @click="isCreateDialogOpen = true"><Plus class="h-4 w-4" />创建知识库</Button>
      </div>
    </section>

    <Card class="border-border bg-card/80"><CardContent class="flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:p-5"><div class="relative flex-1"><Search class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" /><Input v-model="searchQuery" placeholder="按名称或描述搜索知识库" class="pl-10" /></div><div class="flex items-center gap-3 text-sm text-muted-foreground"><span class="rounded-full bg-muted px-3 py-1.5">{{ knowledgeBases.length }} 个知识库</span><span class="rounded-full bg-primary/10 px-3 py-1.5 text-primary">{{ knowledgeBases.filter(item => item.status === 0).length }} 个可用</span></div></CardContent></Card>

    <LoadingSkeleton v-if="loading" type="card" :count="6" />
    <ErrorState v-else-if="loadError" message="加载知识库失败" @retry="loadKnowledgeBases" />
    <EmptyState v-else-if="filteredKnowledgeBases.length === 0" :icon="BookOpen" :title="searchQuery ? '没有找到匹配的知识库' : '还没有知识库'" :description="searchQuery ? '尝试更换搜索关键词' : '创建第一个知识库，然后上传文档让 AI 学习。'" action="创建知识库" :show-action="!searchQuery" @action="handleCreateDialogOpen" />
    <div v-else class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      <article v-for="kb in filteredKnowledgeBases" :key="kb.id" class="group relative overflow-hidden rounded-2xl border border-border bg-card/80 p-5 transition-all hover:-translate-y-0.5 hover:border-primary/35 hover:shadow-[0_18px_38px_rgba(0,0,0,0.14)]" @click="goToDetail(kb.id)">
        <div class="flex items-start justify-between gap-3"><div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary"><FolderOpen class="h-5 w-5" /></div><Badge variant="outline" :class="kb.status === 0 ? 'border-emerald-400/25 bg-emerald-400/10 text-emerald-300' : 'border-border bg-muted text-muted-foreground'">{{ kb.status === 0 ? '可用于对话' : '已停用' }}</Badge></div>
        <h3 class="mt-5 truncate text-lg font-semibold">{{ kb.name }}</h3><p class="mt-2 min-h-11 line-clamp-2 text-sm leading-5 text-muted-foreground">{{ kb.description || '暂未填写描述，可进入详情补充知识库用途。' }}</p>
        <div class="mt-5 grid grid-cols-2 gap-3 border-y border-border/70 py-4 text-sm"><div><p class="text-xs text-muted-foreground">已收录文档</p><p class="mt-1 font-semibold">{{ kb.documentCount || 0 }} <span class="text-xs font-normal text-muted-foreground">篇</span></p></div><div><p class="text-xs text-muted-foreground">创建时间</p><p class="mt-1 truncate text-sm">{{ formatDateTime(kb.createdAt) }}</p></div></div>
        <div class="mt-4 flex items-center justify-between gap-2"><span class="truncate text-xs text-muted-foreground">{{ kb.username ? `创建者：${kb.username}` : '我的知识空间' }}</span><Button variant="ghost" size="sm" class="gap-1.5 text-primary" @click.stop="goToDetail(kb.id)">管理<ArrowRight class="h-3.5 w-3.5" /></Button></div>
        <div class="absolute right-5 top-16 flex gap-1 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100"><Button variant="ghost" size="icon" class="h-8 w-8" :disabled="statusUpdatingId === kb.id || (kb.status !== 0 && kb.status !== 1)" :title="kb.status === 0 ? '停用知识库' : '启用知识库'" @click.stop="handleToggleStatus(kb)"><Loader2 v-if="statusUpdatingId === kb.id" class="h-4 w-4 animate-spin" /><PowerOff v-else-if="kb.status === 0" class="h-4 w-4" /><Power v-else class="h-4 w-4" /></Button><Button variant="ghost" size="icon" class="h-8 w-8" title="编辑" @click.stop="handleEdit(kb)"><Edit class="h-4 w-4" /></Button><Button variant="ghost" size="icon" class="h-8 w-8 hover:bg-rose-400/10" title="删除" @click.stop="handleDelete(kb)"><Trash2 class="h-4 w-4 text-destructive" /></Button></div>
      </article>
    </div>

    <Dialog v-model:open="isCreateDialogOpen">
      <DialogContent>
        <DialogHeader><DialogTitle>创建知识库</DialogTitle><DialogDescription>创建一个新的知识空间，用于集中管理 AI 可检索的资料。</DialogDescription></DialogHeader>
        <div class="space-y-4"><div class="space-y-2"><Label for="name">名称 *</Label><Input id="name" v-model="createForm.name" placeholder="例如：产品帮助中心" /></div><div class="space-y-2"><Label for="description">描述</Label><Input id="description" v-model="createForm.description" placeholder="说明这套资料适用于哪些问题（可选）" /></div></div>
        <DialogFooter><Button variant="outline" @click="isCreateDialogOpen = false">取消</Button><Button @click="handleCreate">创建知识库</Button></DialogFooter>
      </DialogContent>
    </Dialog>

    <Dialog v-model:open="isEditDialogOpen">
      <DialogContent>
        <DialogHeader><DialogTitle>编辑知识库</DialogTitle><DialogDescription>修改知识库名称和用途说明。</DialogDescription></DialogHeader>
        <div class="space-y-4"><div class="space-y-2"><Label for="edit-name">名称 *</Label><Input id="edit-name" v-model="editForm.name" placeholder="请输入知识库名称" /></div><div class="space-y-2"><Label for="edit-description">描述</Label><Input id="edit-description" v-model="editForm.description" placeholder="请输入知识库描述（可选）" /></div></div>
        <DialogFooter><Button variant="outline" @click="isEditDialogOpen = false">取消</Button><Button @click="handleUpdate">保存修改</Button></DialogFooter>
      </DialogContent>
    </Dialog>

    <Dialog v-model:open="isDeleteDialogOpen">
      <DialogContent>
        <DialogHeader><DialogTitle>删除知识库？</DialogTitle><DialogDescription>确定删除「{{ currentItem?.name }}」吗？其中的文档和索引将无法继续在对话中使用。</DialogDescription></DialogHeader>
        <DialogFooter><Button variant="outline" @click="isDeleteDialogOpen = false">取消</Button><Button variant="destructive" @click="confirmDelete">确认删除</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
