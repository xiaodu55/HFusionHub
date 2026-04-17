import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { useUserStore } from '@/stores/user'

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
        path: 'agent',
        name: 'AgentTasks',
        component: () => import('@/pages/agent/Index.vue'),
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
      },
      {
        path: 'builder/prompts/recycle-bin',
        name: 'PromptRecycleBin',
        component: () => import('@/pages/builder/PromptRecycleBin.vue'),
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
      },
      {
        path: 'builder/test-bench',
        name: 'PromptTestBench',
        component: () => import('@/pages/builder/TestBench.vue'),
      },
      {
        path: 'builder/test-sets',
        name: 'PromptTestSets',
        component: () => import('@/pages/builder/TestSet.vue'),
      },
      {
        path: 'cost',
        name: 'CostDashboard',
        component: () => import('@/pages/cost/Index.vue'),
      },
      {
        path: 'settings/safety',
        name: 'SafetySettings',
        component: () => import('@/pages/settings/Safety.vue'),
      },
      {
        path: 'memory',
        name: 'Memory',
        component: () => import('@/pages/memory/Index.vue'),
      },
      {
        path: 'rag',
        name: 'RagObservability',
        component: () => import('@/pages/rag/Index.vue'),
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
      },
      {
        path: 'admin/intent-tree',
        name: 'IntentTree',
        component: () => import('@/pages/admin/IntentTree.vue'),
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 路由守卫
router.beforeEach((to, _from, next) => {
  const userStore = useUserStore()
  const requiresAuth = to.meta.requiresAuth !== false

  if (requiresAuth && !userStore.isLoggedIn) {
    next('/login')
  } else if ((to.path === '/login' || to.path === '/register') && userStore.isLoggedIn) {
    next('/')
  } else {
    next()
  }
})

export default router
