import { message } from 'ant-design-vue'
import { useUserStore } from '@/stores/user'

/**
 * 统一聊天错误处理
 * @param {Error} error - 错误对象
 * @param {string} context - 错误上下文（如 'send', 'load', 'create'）
 */
export function handleChatError(error, context = '') {
  console.error(`[ChatError:${context}]`, error)

  // 根据错误类型提供友好的用户提示
  let errorMessage = '操作失败，请稍后重试'
  let needRelogin = false

  if (error.message) {
    if (error.message.includes('网络') || error.message.includes('fetch')) {
      errorMessage = '网络连接失败，请检查网络设置'
    } else if (error.message.includes('401') || error.message.includes('未授权') || error.message.includes('超时')) {
      errorMessage = '登录已过期，请重新登录'
      needRelogin = true
    } else if (error.message.includes('403')) {
      errorMessage = '没有权限执行此操作'
    } else if (error.message.includes('404')) {
      errorMessage = '请求的资源不存在'
    } else if (error.message.includes('500')) {
      errorMessage = '服务器内部错误，请联系管理员'
    } else if (error.message.includes('timeout')) {
      errorMessage = '请求超时，请重试'
    } else {
      errorMessage = error.message
    }
  }

  // 显示错误消息
  message.error(errorMessage)

  // 认证失效：主动登出并跳转到登录页，避免用户被困在"无响应"的聊天页
  if (needRelogin) {
    try {
      const userStore = useUserStore()
      if (userStore.isLoggedIn) userStore.logout()
    } catch (e) {
      // 忽略登出过程中的异常
    }
    setTimeout(() => {
      window.location.href = '/login'
    }, 1500)
  }
}

/**
 * 验证错误处理
 * @param {Error} error - 错误对象
 */
export function handleValidationError(error) {
  console.error('[ValidationError]', error)
  message.error('输入数据验证失败，请检查输入内容')
}
