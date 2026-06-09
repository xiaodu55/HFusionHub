<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import * as bidApi from '@/api/bid'
import type { BidProjectInfo, BidProjectStatus } from '@/api/bid'
import * as knowledgeBaseApi from '@/api/knowledgeBase'
import type { KnowledgeBase } from '@/api/types'
import { BID_PROJECT_STATUS_LABELS, bidProjectStatusClass } from '@/utils/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Select } from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Plus,
  Search,
  Trash2,
  Loader2,
  ArrowRight,
  FileSearch,
  ChevronLeft,
  ChevronRight,
} from 'lucide-vue-next'
import { formatDateTime } from '@/utils/date'
import { useToast } from '@/composables/useToast'
import EmptyState from '@/components/EmptyState.vue'
import LoadingSkeleton from '@/components/LoadingSkeleton.vue'
import ErrorState from '@/components/ErrorState.vue'

const router = useRouter()
const toast = useToast()

const projects = ref<BidProjectInfo[]>([])
const loading = ref(false)
const loadError = ref(false)
const currentPage = ref(1)
const pageSize = ref(9)
const total = ref(0)
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))
let loadSeq = 0

const keyword = ref('')
const statusFilter = ref('')

const isCreateOpen = ref(false)
const creating = ref(false)
const knowledgeBases = ref<KnowledgeBase[]>([])
const createForm = ref({
  knowledgeBaseId: '',
  title: '',
  tenderNumber: '',
  budget: '',
})

const STATUS_LABELS = BID_PROJECT_STATUS_LABELS

const STATUS_OPTIONS = Object.entries(STATUS_LABELS).map(([value, label]) => ({ value, label }))
const FILTER_OPTIONS = [{ value: '', label: '全部状态' }, ...STATUS_OPTIONS]

const loadProjects = async () => {
  const seq = ++loadSeq
  loading.value = true
  loadError.value = false
  try {
    const res = await bidApi.listBidProjects({
      page: currentPage.value,
      pageSize: pageSize.value,
      keyword: keyword.value || undefined,
      status: (statusFilter.value || undefined) as BidProjectStatus | undefined,
    })
    if (seq !== loadSeq) return
    projects.value = res.data.records
    total.value = res.data.total
    if (projects.value.length === 0 && currentPage.value > 1 && total.value > 0) {
      currentPage.value -= 1
      await loadProjects()
    }
  } catch (error) {
    if (seq !== loadSeq) return
    loadError.value = true
    toast.error(error instanceof Error ? error.message : '加载投标项目失败')
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

const applyFilter = () => {
  currentPage.value = 1
  loadProjects()
}

const openCreate = async () => {
  isCreateOpen.value = true
  createForm.value = { knowledgeBaseId: '', title: '', tenderNumber: '', budget: '' }
  try {
    const res = await knowledgeBaseApi.getMyKnowledgeBaseList({ page: 1, pageSize: 100 })
    knowledgeBases.value = res.data.records
  } catch {
    knowledgeBases.value = []
  }
}

const submitCreate = async () => {
  if (!createForm.value.knowledgeBaseId) {
    toast.error('请选择招标文件知识库')
    return
  }
  if (!createForm.value.title.trim()) {
    toast.error('请输入项目名称')
    return
  }
  creating.value = true
  try {
    const res = await bidApi.createBidProject({
      knowledgeBaseId: Number(createForm.value.knowledgeBaseId),
      title: createForm.value.title.trim(),
      tenderNumber: createForm.value.tenderNumber.trim() || undefined,
      budget: createForm.value.budget ? Number(createForm.value.budget) : undefined,
    })
    toast.success('投标项目已创建')
    isCreateOpen.value = false
    await loadProjects()
    router.push(`/bid/projects/${res.data.id}/interpret`)
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '创建失败')
  } finally {
    creating.value = false
  }
}

const openInterpret = (project: BidProjectInfo) => {
  router.push(`/bid/projects/${project.id}/interpret`)
}

const removeProject = async (project: BidProjectInfo) => {
  if (!window.confirm(`确认删除投标项目「${project.title}」？`)) return
  try {
    await bidApi.deleteBidProject(project.id)
    toast.success('已删除')
    await loadProjects()
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '删除失败')
  }
}

onMounted(loadProjects)
</script>

<template>
  <div class="container mx-auto max-w-6xl px-4 py-6">
    <div class="mb-6 flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-2xl font-bold">投标项目</h1>
        <p class="mt-1 text-sm text-muted-foreground">
          招标文件智能解读 → 需求清单 → 标书撰写与自检 一体化工作台
        </p>
      </div>
      <Button @click="openCreate">
        <Plus class="mr-1 h-4 w-4" /> 新建投标项目
      </Button>
    </div>

    <!-- 筛选 -->
    <div class="mb-4 flex flex-wrap gap-3">
      <div class="relative w-64">
        <Search class="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
        <Input
          v-model="keyword"
          placeholder="搜索项目名称 / 招标编号"
          class="pl-9"
          @keyup.enter="applyFilter"
        />
      </div>
      <div class="w-40">
        <Select v-model="statusFilter" :options="FILTER_OPTIONS" @update:model-value="applyFilter" />
      </div>
      <Button variant="outline" @click="applyFilter">查询</Button>
    </div>

    <LoadingSkeleton v-if="loading" type="card" :count="3" />
    <ErrorState
      v-else-if="loadError"
      title="加载失败"
      description="请检查网络连接后重试"
      @retry="loadProjects"
    />
    <EmptyState
      v-else-if="projects.length === 0"
      :icon="FileSearch"
      title="还没有投标项目"
      description="新建项目并关联招标文件知识库，AI 将自动解读要素与需求"
    />

    <div v-else class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      <Card
        v-for="project in projects"
        :key="project.id"
        class="cursor-pointer transition-shadow hover:shadow-md"
        @click="openInterpret(project)"
      >
        <CardContent class="p-5">
          <div class="mb-2 flex items-start justify-between gap-2">
            <Badge :class="bidProjectStatusClass(project.status)">
              {{ STATUS_LABELS[project.status] }}
            </Badge>
            <button
              class="text-muted-foreground transition-colors hover:text-destructive"
              :aria-label="`删除 ${project.title}`"
              @click.stop="removeProject(project)"
            >
              <Trash2 class="h-4 w-4" />
            </button>
          </div>
          <h3 class="mb-1 line-clamp-2 font-semibold">{{ project.title }}</h3>
          <p v-if="project.tenderNumber" class="mb-2 text-xs text-muted-foreground">
            招标编号：{{ project.tenderNumber }}
          </p>
          <div class="mb-3 flex flex-wrap gap-3 text-xs text-muted-foreground">
            <span v-if="project.budget">预算 ¥{{ Number(project.budget).toLocaleString() }}</span>
            <span v-if="project.requirementCount !== undefined">需求 {{ project.requirementCount }} 项</span>
          </div>
          <div class="flex items-center justify-between text-xs text-muted-foreground">
            <span>创建于 {{ formatDateTime(project.createdAt) }}</span>
            <span class="inline-flex items-center text-primary">
              查看解读 <ArrowRight class="ml-0.5 h-3.5 w-3.5" />
            </span>
          </div>
        </CardContent>
      </Card>
    </div>

    <!-- 分页 -->
    <div v-if="totalPages > 1" class="mt-6 flex items-center justify-center gap-2">
      <Button
        variant="outline"
        size="sm"
        :disabled="currentPage <= 1"
        @click="currentPage--; loadProjects()"
      >
        <ChevronLeft class="h-4 w-4" />
      </Button>
      <span class="text-sm text-muted-foreground">{{ currentPage }} / {{ totalPages }}</span>
      <Button
        variant="outline"
        size="sm"
        :disabled="currentPage >= totalPages"
        @click="currentPage++; loadProjects()"
      >
        <ChevronRight class="h-4 w-4" />
      </Button>
    </div>

    <!-- 新建对话框 -->
    <Dialog v-model:open="isCreateOpen">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>新建投标项目</DialogTitle>
          <DialogDescription>
            选择已上传招标文件并完成向量化的知识库，创建后自动进入解读。
          </DialogDescription>
        </DialogHeader>
        <div class="space-y-4">
          <div class="space-y-2">
            <Label>招标文件知识库 <span class="text-destructive">*</span></Label>
            <Select
              v-model="createForm.knowledgeBaseId"
              :options="knowledgeBases.map(kb => ({ value: String(kb.id), label: kb.name }))"
              placeholder="选择知识库"
            />
          </div>
          <div class="space-y-2">
            <Label>项目名称 <span class="text-destructive">*</span></Label>
            <Input v-model="createForm.title" placeholder="如：滨海园区智能化改造项目" />
          </div>
          <div class="grid grid-cols-2 gap-4">
            <div class="space-y-2">
              <Label>招标编号</Label>
              <Input v-model="createForm.tenderNumber" placeholder="如：BH-2026-0618" />
            </div>
            <div class="space-y-2">
              <Label>预算（元）</Label>
              <Input v-model="createForm.budget" type="number" placeholder="如：12600000" />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="isCreateOpen = false">取消</Button>
          <Button :disabled="creating" @click="submitCreate">
            <Loader2 v-if="creating" class="mr-1 h-4 w-4 animate-spin" />
            创建并解读
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
