<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import * as knowledgeBaseApi from '@/api/knowledgeBase'
import type { KnowledgeBase } from '@/api/types'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
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
import { Plus, Search, Edit, Trash2, BookOpen, Power, PowerOff, Loader2 } from 'lucide-vue-next'
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
  <div class="space-y-6">
    <!-- 页面头部 -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-2xl font-bold">知识库管理</h2>
        <p class="text-muted-foreground">管理您的知识库，为 AI 提供知识支持</p>
      </div>
      <Button @click="isCreateDialogOpen = true">
        <Plus class="mr-2 h-4 w-4" />
        创建知识库
      </Button>

      <Dialog v-model:open="isCreateDialogOpen">
        <DialogContent>
          <DialogHeader>
            <DialogTitle>创建知识库</DialogTitle>
            <DialogDescription>创建一个新的知识库来存储和管理知识</DialogDescription>
          </DialogHeader>
          <div class="space-y-4">
            <div class="space-y-2">
              <Label for="name">名称 *</Label>
              <Input
                id="name"
                v-model="createForm.name"
                placeholder="请输入知识库名称"
              />
            </div>
            <div class="space-y-2">
              <Label for="description">描述</Label>
              <Input
                id="description"
                v-model="createForm.description"
                placeholder="请输入知识库描述（可选）"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" @click="isCreateDialogOpen = false">
              取消
            </Button>
            <Button @click="handleCreate">创建</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>

    <!-- 搜索栏 -->
    <div class="flex items-center gap-4">
      <div class="relative flex-1">
        <Search class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          v-model="searchQuery"
          placeholder="搜索知识库..."
          class="pl-10"
        />
      </div>
    </div>

    <!-- 知识库列表 -->
    <LoadingSkeleton v-if="loading" type="card" :count="6" />
    <ErrorState
      v-else-if="loadError"
      message="加载知识库失败"
      @retry="loadKnowledgeBases"
    />
    <EmptyState
      v-else-if="filteredKnowledgeBases.length === 0"
      :icon="BookOpen"
      :title="searchQuery ? '没有找到匹配的知识库' : '暂无知识库'"
      :description="searchQuery ? '尝试更换搜索关键词' : '创建您的第一个知识库，开始上传文档'"
      action="创建知识库"
      :show-action="!searchQuery"
      @action="handleCreateDialogOpen"
    />
    <div v-else class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      <Card
        v-for="kb in filteredKnowledgeBases"
        :key="kb.id"
        class="cursor-pointer transition-shadow hover:shadow-md"
        @click="goToDetail(kb.id)"
      >
        <CardHeader>
          <div class="flex items-start justify-between">
            <div class="space-y-1">
              <CardTitle class="text-lg">{{ kb.name }}</CardTitle>
              <CardDescription>{{ kb.description || '暂无描述' }}</CardDescription>
            </div>
            <Badge :variant="kb.status === 0 ? 'default' : 'secondary'">
              {{ kb.status === 0 ? '启用' : '禁用' }}
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          <p class="text-sm text-muted-foreground">
            创建时间：{{ formatDateTime(kb.createdAt) }}
          </p>
          <p v-if="kb.username" class="text-sm text-muted-foreground">
            创建者：{{ kb.username }}
          </p>
          <p class="text-sm text-muted-foreground">
            文档数量：{{ kb.documentCount || 0 }} 篇
          </p>
        </CardContent>
        <CardFooter class="flex justify-end gap-2">
          <Button
            variant="outline"
            size="sm"
            :disabled="statusUpdatingId === kb.id || (kb.status !== 0 && kb.status !== 1)"
            :title="kb.status === 0 ? '禁用知识库' : '启用知识库'"
            @click.stop="handleToggleStatus(kb)"
          >
            <Loader2 v-if="statusUpdatingId === kb.id" class="mr-2 h-4 w-4 animate-spin" />
            <PowerOff v-else-if="kb.status === 0" class="mr-2 h-4 w-4" />
            <Power v-else class="mr-2 h-4 w-4" />
            {{ kb.status === 0 ? '禁用' : '启用' }}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            @click.stop="handleEdit(kb)"
          >
            <Edit class="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            @click.stop="handleDelete(kb)"
          >
            <Trash2 class="h-4 w-4 text-destructive" />
          </Button>
        </CardFooter>
      </Card>
    </div>

    <!-- 编辑对话框 -->
    <Dialog v-model:open="isEditDialogOpen">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>编辑知识库</DialogTitle>
          <DialogDescription>修改知识库信息</DialogDescription>
        </DialogHeader>
        <div class="space-y-4">
          <div class="space-y-2">
            <Label for="edit-name">名称 *</Label>
            <Input
              id="edit-name"
              v-model="editForm.name"
              placeholder="请输入知识库名称"
            />
          </div>
          <div class="space-y-2">
            <Label for="edit-description">描述</Label>
            <Input
              id="edit-description"
              v-model="editForm.description"
              placeholder="请输入知识库描述（可选）"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="isEditDialogOpen = false">
            取消
          </Button>
          <Button @click="handleUpdate">保存</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- 删除确认对话框 -->
    <Dialog v-model:open="isDeleteDialogOpen">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>确认删除</DialogTitle>
          <DialogDescription>
            确定要删除知识库「{{ currentItem?.name }}」吗？此操作不可撤销。
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" @click="isDeleteDialogOpen = false">
            取消
          </Button>
          <Button variant="destructive" @click="confirmDelete">
            删除
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
