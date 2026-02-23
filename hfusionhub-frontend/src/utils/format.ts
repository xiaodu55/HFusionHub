/**
 * 格式化文件大小
 * @param bytes 字节数
 * @returns 格式化后的字符串（如 "1.5 MB"）
 */
export function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

/**
 * 获取文档状态徽章
 * @param status 状态码
 * @returns 徽章文本和样式变体
 */
export function getStatusBadge(status: number): { text: string; variant: 'outline' | 'secondary' | 'default' | 'destructive' } {
  switch (status) {
    case 0:
      return { text: '待解析', variant: 'outline' }
    case 1:
      return { text: '解析中...', variant: 'secondary' }
    case 2:
      return { text: '已完成', variant: 'default' }
    case 3:
      return { text: '解析失败', variant: 'destructive' }
    case 4:
      return { text: '删除中...', variant: 'secondary' }
    case 5:
      return { text: '删除失败', variant: 'destructive' }
    default:
      return { text: '未知', variant: 'outline' }
  }
}

/**
 * 获取知识库状态文本
 * @param status 状态码
 * @returns 状态文本
 */
export function getKnowledgeBaseStatusText(status: number): string {
  return status === 0 ? '启用' : '禁用'
}
