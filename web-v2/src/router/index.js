import { createRouter, createWebHistory } from 'vue-router'
import AppLayout from '@/layouts/AppLayout.vue'
import BlankLayout from '@/layouts/BlankLayout.vue'
import { useUserStore } from '@/stores/user'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      redirect: '/agent'
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/LoginView.vue'),
      meta: { requiresAuth: false }
    },
    {
      path: '/agent',
      name: 'AgentMain',
      component: AppLayout,
      children: [
        {
          path: '',
          name: 'AgentComp',
          component: () => import('../views/AgentView.vue'),
          meta: { keepAlive: true, requiresAuth: false }
        },
        {
          path: ':agent_id',
          name: 'AgentCompWithId',
          component: () => import('../views/AgentView.vue'),
          meta: { keepAlive: true, requiresAuth: false }
        }
      ]
    },
    {
      path: '/assistant',
      name: 'Assistant',
      component: AppLayout,
      children: [
        {
          path: '',
          name: 'AssistantPage',
          component: () => import('../views/AssistantView.vue'),
          meta: { keepAlive: true, requiresAuth: false }
        }
      ]
    },
    {
      path: '/decisions',
      name: 'DecisionLibrary',
      component: AppLayout,
      children: [
        {
          path: '',
          name: 'DecisionLibraryPage',
          component: () => import('../views/DecisionLibraryView.vue'),
          meta: { keepAlive: true, requiresAuth: false }
        }
      ]
    },
    {
      path: '/tasks',
      name: 'Scheduler',
      component: AppLayout,
      children: [
        {
          path: '',
          name: 'SchedulerPage',
          component: () => import('../views/SchedulerView.vue'),
          meta: { keepAlive: true, requiresAuth: false }
        }
      ]
    },
    {
      path: '/mcps',
      name: 'McpHub',
      component: AppLayout,
      children: [
        {
          path: '',
          name: 'McpHubPage',
          component: () => import('../views/McpHubView.vue'),
          meta: { keepAlive: true, requiresAuth: false }
        }
      ]
    },
    {
      path: '/agents',
      name: 'AgentManage',
      component: AppLayout,
      children: [
        {
          path: '',
          name: 'AgentManagePage',
          component: () => import('../views/AgentManageView.vue'),
          meta: { keepAlive: true, requiresAuth: false }
        }
      ]
    },
    {
      path: '/test-product-card',
      name: 'TestProductCard',
      component: BlankLayout,
      children: [
        {
          path: '',
          name: 'TestProductCardPage',
          component: () => import('../views/TestProductCard.vue'),
          meta: { requiresAuth: false }
        }
      ]
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'NotFound',
      component: () => import('../views/EmptyView.vue'),
      meta: { requiresAuth: false }
    }
  ]
})

router.beforeEach(async (to, from, next) => {
  const requiresAuth = to.matched.some((record) => record.meta.requiresAuth === true)
  const userStore = useUserStore()

  if (userStore.token && !userStore.userId) {
    try {
      await userStore.getCurrentUser()
    } catch (error) {
      // /api/auth/me 明确返回非 200（token 失效）→ 清除登录态，交由登录页重新鉴权。
      // 注意：业务请求（/api/chat/* 等）的 401 不在此处处理，由 base.js/errorHandler 判定，
      // 避免单次业务请求失败把正在进行的对话腰斩跳登录。
      console.error('登录态已失效，需重新登录:', error)
      userStore.logout()
    }
  }

  // 移除强制登录拦截，改为按需触发
  // if (requiresAuth && !userStore.isLoggedIn) {
  //   sessionStorage.setItem('redirect', to.fullPath)
  //   next('/login')
  //   return
  // }

  if (to.path === '/login' && userStore.isLoggedIn) {
    // 登录后跳转到之前尝试访问的页面或默认页面
    const redirectPath = sessionStorage.getItem('redirect') || '/agent'
    sessionStorage.removeItem('redirect')
    next(redirectPath)
    return
  }

  next()
})

export default router
