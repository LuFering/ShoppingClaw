import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useAgentStore } from './agent'

export const useUserStore = defineStore('user', () => {
  const token = ref(localStorage.getItem('user_token') || '')
  const userId = ref(null)
  const username = ref('')
  const userRole = ref('')

  const isLoggedIn = computed(() => !!token.value)
  const isAdmin = computed(() => userRole.value === 'admin' || userRole.value === 'superadmin')
  const isSuperAdmin = computed(() => userRole.value === 'superadmin')

  async function login(credentials) {
    try {
      const formData = new FormData()
      formData.append('username', credentials.loginId)
      formData.append('password', credentials.password)

      const response = await fetch('/api/auth/token', {
        method: 'POST',
        body: formData
      })

      if (!response.ok) {
        const error = await response.json()
        if (response.status === 423) {
          const lockError = new Error(error.detail || '账户被锁定')
          lockError.status = 423
          throw lockError
        }
        throw new Error(error.detail || '登录失败')
      }

      const data = await response.json()
      token.value = data.access_token
      userId.value = data.user_id
      username.value = data.username
      userRole.value = data.role
      localStorage.setItem('user_token', data.access_token)
      return true
    } catch (error) {
      console.error('登录错误:', error)
      throw error
    }
  }

  function logout() {
    token.value = ''
    userId.value = null
    username.value = ''
    userRole.value = ''
    const agentStore = useAgentStore()
    agentStore.reset()
    localStorage.removeItem('user_token')
  }

  async function initialize(admin) {
    try {
      const response = await fetch('/api/auth/initialize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(admin)
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || '初始化管理员失败')
      }

      const data = await response.json()
      token.value = data.access_token
      userId.value = data.user_id
      username.value = data.username
      userRole.value = data.role
      localStorage.setItem('user_token', data.access_token)
      return true
    } catch (error) {
      console.error('初始化管理员错误:', error)
      throw error
    }
  }

  async function checkFirstRun() {
    try {
      const response = await fetch('/api/auth/check-first-run')
      const data = await response.json()
      return data.first_run
    } catch (error) {
      console.error('检查首次运行状态错误:', error)
      return false
    }
  }

  function getAuthHeaders() {
    return { Authorization: `Bearer ${token.value}` }
  }

  async function getCurrentUser() {
    try {
      const response = await fetch('/api/auth/me', {
        headers: { ...getAuthHeaders() }
      })
      if (!response.ok) throw new Error('获取用户信息失败')
      const userData = await response.json()
      userId.value = userData.id
      username.value = userData.username
      userRole.value = userData.role
      return userData
    } catch (error) {
      console.error('获取用户信息错误:', error)
      throw error
    }
  }

  return {
    token, userId, username, userRole,
    isLoggedIn, isAdmin, isSuperAdmin,
    login, logout, initialize, checkFirstRun, getAuthHeaders, getCurrentUser
  }
})
