import { message } from 'ant-design-vue'
import { useUserStore } from '@/stores/user'

/**
 * 把上游/后端的原始错误翻译为面向用户的中文提示。
 * 模型服务（如阿里云百炼）会把原始英文报文透传到前端，
 * 直接展示对用户没有意义，这里按特征归类后给出可读文案。
 * @param {string} raw - 原始错误文本
 * @returns {string} 可读提示（无法归类时返回原文）
 */
export function translateErrorMessage(raw) {
  const text = String(raw || '')
  if (!text) return ''

  if (/Arrearage|overdue-payment|account is in good standing/i.test(text)) {
    return '模型服务不可用：上游账户已欠费，请充值后重试'
  }
  if (/InvalidApiKey|invalid_api_key|Authentication|Unauthorized|Token expired/i.test(text)) {
    return '模型服务鉴权失败：请检查 API Key 配置'
  }
  if (/upstream_provider_shared_pool|temporarily rate-limited/i.test(text)) {
    return '该免费模型当前被上游限流（免费额度为公共共享池），请稍后重试或切换其他模型'
  }
  if (/rate.?limit|429/i.test(text)) {
    return '模型服务请求过于频繁，请稍后重试或切换其他模型'
  }
  if (/quota|insufficient.?balance|exceeded/i.test(text)) {
    return '模型服务额度不足，请充值或切换其他模型'
  }
  if (/model_not_found|model.*not.*found|does not exist/i.test(text)) {
    return '所选模型不可用，请在模型选择器中更换后重试'
  }
  if (/timeout|timed out/i.test(text)) {
    return '模型服务响应超时，请稍后重试'
  }
  if (/context.*length|too many tokens|max.*tokens/i.test(text)) {
    return '对话内容过长，请新开对话后重试'
  }
  // 无法归类时剥离技术前缀，保留原始细节便于排查
  return text.replace(/^Error streaming messages:\s*/i, '')
}

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
    } else if (error.message.includes('401') || error.message.includes('未授权')) {
      // 单次请求未授权：仅提示重试，不强制登出（避免正在进行的对话被腰斩跳登录）
      errorMessage = '请求未授权，请稍后重试'
      needRelogin = false
    } else if (error.message.includes('token expired') || error.message.includes('令牌已过期')) {
      // 仅后端明确「令牌过期」才判定登录失效并登出
      errorMessage = '登录已过期，请重新登录'
      needRelogin = true
    } else if (error.message.includes('超时') || error.message.includes('timeout')) {
      // 请求/网络超时：仅提示重试，绝不能当作登录过期，否则长对话会被误判登出
      errorMessage = '请求超时，请稍后重试'
      needRelogin = false
    } else if (error.message.includes('403')) {
      errorMessage = '没有权限执行此操作'
    } else if (error.message.includes('404')) {
      errorMessage = '请求的资源不存在'
    } else if (error.message.includes('500')) {
      errorMessage = '服务器内部错误，请联系管理员'
    } else if (error.message.includes('timeout')) {
      errorMessage = '请求超时，请重试'
    } else {
      // 上游模型服务错误（欠费 / 鉴权 / 限流等）先做归类翻译，
      // 否则会把英文原始报文直接弹给用户
      errorMessage = translateErrorMessage(error.message) || '操作失败，请稍后重试'
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
