import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { theme as antdTheme } from 'ant-design-vue'

export const useThemeStore = defineStore('theme', () => {
  const isDark = ref(false)

  const currentTheme = computed(() => ({
    algorithm: isDark.value ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
  }))

  function toggle() {
    isDark.value = !isDark.value
  }

  function setDark(val) {
    isDark.value = val
  }

  return { isDark, currentTheme, toggle, setDark }
})
