import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import { theme as antdTheme } from 'ant-design-vue'

export const useThemeStore = defineStore('theme', () => {
  const isDark = ref(false)

  // base.dark.css 以 :root.dark 生效，这里把 store 状态同步到根节点
  watch(
    isDark,
    (val) => {
      document.documentElement.classList.toggle('dark', val)
    },
    { immediate: true }
  )

  // 品牌 emerald（浅色 #178a67 / 深色 #2fae7e），取代 Ant 默认蓝。
  // 收紧圆角到 6px，强化"精密工具"而非"通用聊天壳"的气质。
  const FONT_BODY =
    "'IBM Plex Sans', 'Noto Sans SC', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"

  const currentTheme = computed(() => ({
    algorithm: isDark.value ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
    token: {
      colorPrimary: isDark.value ? '#2fae7e' : '#178a67',
      colorLink: isDark.value ? '#2fae7e' : '#178a67',
      borderRadius: 6,
      fontFamily: FONT_BODY,
      colorBgContainer: isDark.value ? '#1a1e21' : '#ffffff',
    },
  }))

  function toggle() {
    isDark.value = !isDark.value
  }

  function setDark(val) {
    isDark.value = val
  }

  return { isDark, currentTheme, toggle, setDark }
})
