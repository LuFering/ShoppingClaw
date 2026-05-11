import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useInfoStore = defineStore('info', () => {
  const organization = ref({ name: 'ShoppingClaw', logo: '/logo.png', avatar: '/avatar.png' })
  const branding = ref({ name: 'ShoppingClaw', title: 'ShoppingClaw', subtitle: '智能购物助手' })
  const features = ref([])
  const actions = ref([])
  const footer = ref({ copyright: '© 2026 ShoppingClaw. All rights reserved.' })
  const debugMode = ref(false)

  async function loadInfoConfig() {
    try {
      const response = await fetch('/api/system/info')
      if (response.ok) {
        const json = await response.json()
        const data = json?.data
        if (data?.organization) {
          organization.value = data.organization
        }
        if (data?.branding) {
          branding.value = data.branding
        }
        if (data?.features) {
          features.value = data.features
        }
        if (data?.actions) {
          actions.value = data.actions
        }
        if (data?.footer) {
          footer.value = data.footer
        }
      }
    } catch (e) {
      console.warn('Failed to load info config:', e)
    }
  }

  return { organization, branding, features, actions, footer, debugMode, loadInfoConfig }
})
