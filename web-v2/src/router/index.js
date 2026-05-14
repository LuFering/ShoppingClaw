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
      console.error('获取用户信息失败:', error)
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
