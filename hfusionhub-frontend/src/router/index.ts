import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { useUserStore } from '@/stores/user'
import type { UserRole } from '@/api/types'

const BUILDER_ROLES: UserRole[] = ['builder', 'admin']
const ADMIN_ROLES: UserRole[] = ['admin']

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/pages/auth/Login.vue'),
    meta: { requiresAuth: false },
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/pages/auth/Register.vue'),
    meta: { requiresAuth: false },
  },
  {
    path: '/sso/callback',
    name: 'SsoCallback',
    component: () => import('@/pages/auth/SsoCallback.vue'),
    meta: { requiresAuth: false },
  },
  {
    path: '/pending-approval',
    name: 'PendingApproval',
    component: () => import('@/pages/auth/PendingApproval.vue'),
    meta: { requiresAuth: true },
  },
  {
    // 可嵌入聊天挂件（Batch 6）：iframe 场景，鉴权走开放 API Key，无需登录态
    path: '/embed/chat',
    name: 'EmbedChat',
    component: () => import('@/pages/embed/Chat.vue'),
    meta: { requiresAuth: false },
  },
  {
    path: '/',
    component: () => import('@/components/layout/MainLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        name: 'Dashboard',
        component: () => import('@/pages/dashboard/Index.vue'),
      },
      {
        path: 'knowledge-base',
        name: 'KnowledgeBase',
        component: () => import('@/pages/knowledge/Index.vue'),
      },
      {
        path: 'knowledge-base/recycle-bin',
        name: 'KnowledgeBaseRecycleBin',
        component: () => import('@/pages/knowledge/RecycleBin.vue'),
      },
      {
        path: 'knowledge-base/:id',
        name: 'KnowledgeBaseDetail',
        component: () => import('@/pages/knowledge/Detail.vue'),
      },
      {
        path: 'knowledge-base/:id/chunks/:docId',
        name: 'KnowledgeBaseChunks',
        component: () => import('@/pages/knowledge/Chunks.vue'),
      },
      {
        path: 'document',
        name: 'Document',
        component: () => import('@/pages/document/Index.vue'),
      },
      {
        path: 'document/recycle-bin',
        name: 'DocumentRecycleBin',
        component: () => import('@/pages/document/RecycleBin.vue'),
      },
      {
        path: 'chat',
        name: 'Chat',
        component: () => import('@/pages/chat/Index.vue'),
      },
      {
        path: 'chat/:id',
        name: 'ChatDetail',
        component: () => import('@/pages/chat/Detail.vue'),
      },
      {
        path: 'bid/projects',
        name: 'BidProjects',
        component: () => import('@/pages/bid/Projects.vue'),
      },
      {
        path: 'bid/projects/:id/interpret',
        name: 'BidInterpret',
        component: () => import('@/pages/bid/Interpret.vue'),
      },
      {
        path: 'bid/projects/:id/requirements',
        name: 'BidRequirements',
        component: () => import('@/pages/bid/Requirements.vue'),
      },
      {
        path: 'bid/projects/:id/draft',
        name: 'BidDraft',
        component: () => import('@/pages/bid/DraftEditor.vue'),
      },
      {
        path: 'bid/billing',
        name: 'BidBilling',
        component: () => import('@/pages/bid/Billing.vue'),
      },
      {
        path: 'agent',
        name: 'AgentTasks',
        component: () => import('@/pages/agent/Index.vue'),
      },
      {
        path: 'analytics',
        name: 'Analytics',
        component: () => import('@/pages/analytics/Index.vue'),
      },
      {
        path: 'approvals',
        name: 'Approvals',
        component: () => import('@/pages/approval/Index.vue'),
      },
      {
        path: 'builder/prompts',
        name: 'PromptStudio',
        component: () => import('@/pages/builder/Prompts.vue'),
        meta: { roles: BUILDER_ROLES },
      },
      {
        path: 'builder/prompts/recycle-bin',
        name: 'PromptRecycleBin',
        component: () => import('@/pages/builder/PromptRecycleBin.vue'),
        meta: { roles: BUILDER_ROLES },
      },
      {
        path: 'builder/models',
        name: 'ModelCenter',
        component: () => import('@/pages/builder/Models.vue'),
      },
      {
        path: 'builder/tools',
        name: 'ToolCenter',
        component: () => import('@/pages/builder/Tools.vue'),
      },
      {
        path: 'builder/plugins',
        name: 'Plugins',
        component: () => import('@/pages/builder/Plugins.vue'),
        meta: { roles: ADMIN_ROLES },
      },
      {
        path: 'builder/test-bench',
        name: 'PromptTestBench',
        component: () => import('@/pages/builder/TestBench.vue'),
        meta: { roles: BUILDER_ROLES },
      },
      {
        path: 'builder/test-sets',
        name: 'PromptTestSets',
        component: () => import('@/pages/builder/TestSet.vue'),
        meta: { roles: BUILDER_ROLES },
      },
      {
        path: 'builder/apps',
        name: 'Apps',
        component: () => import('@/pages/builder/Apps.vue'),
        meta: { roles: BUILDER_ROLES },
      },
      {
        path: 'builder/mcp',
        name: 'McpServers',
        component: () => import('@/pages/builder/McpServers.vue'),
        meta: { roles: BUILDER_ROLES },
      },
      {
        path: 'cost',
        name: 'CostDashboard',
        component: () => import('@/pages/cost/Index.vue'),
      },
      {
        path: 'memory',
        name: 'Memory',
        component: () => import('@/pages/memory/Index.vue'),
      },
      {
        path: 'notes',
        name: 'Notes',
        component: () => import('@/pages/notes/Index.vue'),
      },
      {
        path: 'rag',
        name: 'RagObservability',
        component: () => import('@/pages/rag/Index.vue'),
        meta: { roles: BUILDER_ROLES },
      },
      {
        path: 'profile',
        name: 'Profile',
        component: () => import('@/pages/profile/Index.vue'),
      },
      {
        path: 'settings',
        name: 'Settings',
        component: () => import('@/pages/settings/Index.vue'),
      },
      {
        path: 'admin/flags',
        name: 'FeatureFlags',
        component: () => import('@/pages/admin/Flags.vue'),
        meta: { roles: ADMIN_ROLES },
      },
      {
        path: 'admin/intent-tree',
        name: 'IntentTree',
        component: () => import('@/pages/admin/IntentTree.vue'),
        meta: { roles: ADMIN_ROLES },
      },
      {
        path: 'admin/users',
        name: 'UserAccess',
        component: () => import('@/pages/admin/Users.vue'),
        meta: { roles: ADMIN_ROLES },
      },
      {
        path: 'admin/notices',
        name: 'AdminNotices',
        component: () => import('@/pages/admin/Notices.vue'),
        meta: { roles: ADMIN_ROLES },
      },
      {
        path: 'admin/audit-logs',
        name: 'AuditLogs',
        component: () => import('@/pages/admin/AuditLogs.vue'),
        meta: { roles: ADMIN_ROLES },
      },
      {
        path: 'admin/plans',
        name: 'Plans',
        component: () => import('@/pages/admin/Plans.vue'),
        meta: { roles: ADMIN_ROLES },
      },
      {
        path: ':pathMatch(.*)*',
        name: 'NotFound',
        component: () => import('@/pages/NotFound.vue'),
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 路由守卫
router.beforeEach(async (to) => {
  const userStore = useUserStore()
  const requiresAuth = to.meta.requiresAuth !== false

  if (requiresAuth && !userStore.isLoggedIn) {
    return '/login'
  }

  if (userStore.isLoggedIn && !userStore.userInfo) {
    try {
      await userStore.getUserInfo()
    } catch {
      userStore.clearToken()
      return '/login'
    }
  }

  if ((to.path === '/login' || to.path === '/register') && userStore.isLoggedIn) {
    return userStore.isPending ? '/pending-approval' : '/'
  }

  if (userStore.isLoggedIn && userStore.isPending && to.path !== '/pending-approval') {
    return '/pending-approval'
  }

  if (userStore.isLoggedIn && !userStore.isPending && to.path === '/pending-approval') {
    return '/'
  }

  const allowedRoles = to.meta.roles as UserRole[] | undefined
  if (allowedRoles?.length && !userStore.hasAnyRole(allowedRoles)) {
    return { path: '/', query: { access: 'denied' } }
  }

  return true
})

export default router
