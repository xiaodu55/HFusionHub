<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  Download,
  FileText,
  LoaderCircle,
  NotebookPen,
  Plus,
  StickyNote,
  Trash2,
  Eye,
} from 'lucide-vue-next'
import * as noteApi from '@/api/note'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import LoadingSkeleton from '@/components/LoadingSkeleton.vue'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import { useToast } from '@/composables/useToast'
import { formatDateTime } from '@/utils/date'
import { friendlyErrorMessage } from '@/utils/errorMessage'

const toast = useToast()
const notes = ref<noteApi.Note[]>([])
const loading = ref(false)
const removingId = ref<number | null>(null)

// ── 查看详情 ──
const viewNote = ref<noteApi.Note | null>(null)
const viewOpen = ref(false)

// ── 手动新建 ──
const createOpen = ref(false)
const createTitle = ref('')
const createContent = ref('')
const creating = ref(false)

const totalCount = computed(() => notes.value.length)
const agentCount = computed(() => notes.value.filter(n => n.source === 'agent_write_note').length)

const loadNotes = async () => {
  loading.value = true
  try {
    const res = await noteApi.listMyNotes(200)
    notes.value = res.data || []
  } catch (e) {
    toast.error(friendlyErrorMessage(e, '加载笔记失败'))
  } finally {
    loading.value = false
  }
}

const openView = (note: noteApi.Note) => {
  viewNote.value = note
  viewOpen.value = true
}

const downloadNote = (note: noteApi.Note) => {
  const title = note.title || `笔记-${note.id}`
  const content = `# ${title}\n\n${note.content || ''}\n\n---\n> 来源：${note.source === 'agent_write_note' ? 'AI 保存' : '手动创建'} · ${formatDateTime(note.createdAt || '')}\n`
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${title}.md`
  a.click()
  URL.revokeObjectURL(url)
}

const removeNote = async (id: number) => {
  if (!window.confirm('确定删除这条笔记吗？')) return
  removingId.value = id
  try {
    await noteApi.deleteNote(id)
    notes.value = notes.value.filter(n => n.id !== id)
    toast.success('已删除')
  } catch (e) {
    toast.error(friendlyErrorMessage(e, '删除失败'))
  } finally {
    removingId.value = null
  }
}

const openCreate = () => {
  createTitle.value = ''
  createContent.value = ''
  createOpen.value = true
}

const submitCreate = async () => {
  if (!createContent.value.trim()) {
    toast.error('笔记内容不能为空')
    return
  }
  creating.value = true
  try {
    await noteApi.createNote({ title: createTitle.value.trim(), content: createContent.value.trim() })
    toast.success('笔记已创建')
    createOpen.value = false
    await loadNotes()
  } catch (e) {
    toast.error(friendlyErrorMessage(e, '创建失败'))
  } finally {
    creating.value = false
  }
}

onMounted(loadNotes)
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="flex items-center gap-2 text-2xl font-semibold">
          <StickyNote class="h-6 w-6 text-primary" /> 我的笔记
        </h1>
        <p class="mt-1 text-sm text-muted-foreground">
          共 {{ totalCount }} 条笔记，其中 {{ agentCount }} 条由 AI 保存
        </p>
      </div>
      <Button variant="outline" class="gap-2" @click="openCreate">
        <Plus class="h-4 w-4" /> 新建笔记
      </Button>
    </div>

    <div v-if="loading" class="space-y-3">
      <LoadingSkeleton type="card" :count="3" class="w-full" />
    </div>

    <div v-else-if="notes.length === 0" class="flex flex-col items-center justify-center py-16 text-center">
      <NotebookPen class="h-12 w-12 text-muted-foreground" />
      <p class="mt-4 text-muted-foreground">还没有笔记</p>
      <p class="mt-1 text-xs text-muted-foreground/70">
        在关联知识库的对话中让 AI「把结论整理成笔记保存到知识库」，确认后即可在这里查看
      </p>
    </div>

    <div v-else class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <Card v-for="note in notes" :key="note.id" class="flex flex-col">
        <CardHeader class="pb-3">
          <div class="flex items-start justify-between gap-2">
            <CardTitle class="line-clamp-1 text-base">{{ note.title || '无标题' }}</CardTitle>
            <Badge :variant="note.source === 'agent_write_note' ? 'default' : 'outline'">
              {{ note.source === 'agent_write_note' ? 'AI 保存' : '手动' }}
            </Badge>
          </div>
          <CardDescription class="text-xs">{{ formatDateTime(note.createdAt || '') }}</CardDescription>
        </CardHeader>
        <CardContent class="flex flex-1 flex-col gap-3">
          <p class="line-clamp-4 flex-1 whitespace-pre-wrap text-sm text-muted-foreground">{{ note.content }}</p>
          <div class="flex items-center gap-2">
            <Button size="sm" variant="outline" class="gap-1" @click="openView(note)">
              <Eye class="h-3.5 w-3.5" /> 查看
            </Button>
            <Button size="sm" variant="outline" class="gap-1" @click="downloadNote(note)">
              <Download class="h-3.5 w-3.5" /> 下载
            </Button>
            <Button
              size="sm"
              variant="ghost"
              class="ml-auto gap-1 text-destructive hover:text-destructive"
              :disabled="removingId === note.id"
              @click="removeNote(note.id)"
            >
              <LoaderCircle v-if="removingId === note.id" class="h-3.5 w-3.5 animate-spin" />
              <Trash2 v-else class="h-3.5 w-3.5" />
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>

    <!-- 查看详情 -->
    <Dialog v-model:open="viewOpen">
      <DialogContent class="max-h-[80vh] overflow-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle class="flex items-center gap-2">
            <FileText class="h-5 w-5 text-primary" /> {{ viewNote?.title || '无标题' }}
          </DialogTitle>
          <DialogDescription v-if="viewNote">
            {{ formatDateTime(viewNote.createdAt || '') }} ·
            {{ viewNote.source === 'agent_write_note' ? 'AI 保存' : '手动创建' }}
          </DialogDescription>
        </DialogHeader>
        <div class="min-h-32 rounded-lg border bg-muted/30 p-4">
          <MarkdownRenderer v-if="viewNote" :content="viewNote.content || ''" />
        </div>
        <DialogFooter>
          <Button variant="outline" @click="downloadNote(viewNote!)">
            <Download class="mr-1 h-4 w-4" /> 下载 Markdown
          </Button>
          <Button @click="viewOpen = false">关闭</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- 新建笔记 -->
    <Dialog v-model:open="createOpen">
      <DialogContent class="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>新建笔记</DialogTitle>
          <DialogDescription>保存一条手动整理的笔记</DialogDescription>
        </DialogHeader>
        <div class="space-y-3">
          <Input v-model="createTitle" placeholder="标题（可选，默认取内容前 30 字）" />
          <Textarea v-model="createContent" rows="8" placeholder="支持 Markdown…" />
        </div>
        <DialogFooter>
          <Button variant="outline" @click="createOpen = false">取消</Button>
          <Button :disabled="creating" @click="submitCreate">
            <LoaderCircle v-if="creating" class="mr-1 h-4 w-4 animate-spin" />
            保存
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
