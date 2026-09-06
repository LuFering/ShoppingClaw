import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { agentApi } from '@/apis'

export const useAgentStore = defineStore('agent', () => {
  const agents = ref([])
  const selectedAgentId = ref(null)
  const defaultAgentId = ref(null)
  const agentDetails = ref({})

  const isLoadingAgents = ref(false)
  const isInitialized = ref(false)
  const isInitializing = ref(false)
  const error = ref(null)

  const selectedAgent = computed(() =>
    selectedAgentId.value ? agents.value.find((a) => a.id === selectedAgentId.value) : null
  )

  const defaultAgent = computed(() =>
    defaultAgentId.value
      ? agents.value.find((a) => a.id === defaultAgentId.value)
      : agents.value[0]
  )

  const agentsList = computed(() => agents.value)

  async function initialize() {
    if (isInitialized.value || isInitializing.value) return
    isInitializing.value = true
    try {
      await fetchAgents()
      await fetchDefaultAgent()
      if (!selectedAgent.value) {
        if (defaultAgent.value) {
          selectedAgentId.value = defaultAgentId.value
        } else if (agents.value.length > 0) {
          selectedAgentId.value = agents.value[0].id
        }
      }
      isInitialized.value = true
    } catch (err) {
      console.error('Failed to initialize agent store:', err)
      error.value = err.message
    } finally {
      isInitializing.value = false
    }
  }

  async function fetchAgents() {
    isLoadingAgents.value = true
    error.value = null
    try {
      const response = await agentApi.getAgents()
      agents.value = response.agents
    } catch (err) {
      console.error('Failed to fetch agents:', err)
      error.value = err.message
      throw err
    } finally {
      isLoadingAgents.value = false
    }
  }

  async function fetchAgentDetail(agentId) {
    if (!agentId || agentDetails.value[agentId]) return agentDetails.value[agentId]
    try {
      const response = await agentApi.getAgentDetail(agentId)
      agentDetails.value[agentId] = response
      return response
    } catch (err) {
      console.error(`Failed to fetch agent detail for ${agentId}:`, err)
      throw err
    }
  }

  async function fetchDefaultAgent() {
    try {
      const response = await agentApi.getDefaultAgent()
      defaultAgentId.value = response.default_agent_id
    } catch (err) {
      console.error('Failed to fetch default agent:', err)
    }
  }

  function selectAgent(agentId) {
    if (agents.value.find((a) => a.id === agentId)) {
      selectedAgentId.value = agentId
    }
  }

  function clearError() {
    error.value = null
  }

  function reset() {
    agents.value = []
    selectedAgentId.value = null
    defaultAgentId.value = null
    agentDetails.value = {}
    isLoadingAgents.value = false
    error.value = null
    isInitialized.value = false
    isInitializing.value = false
  }

  return {
    agents, selectedAgentId, defaultAgentId, agentDetails,
    isLoadingAgents, isInitialized, error,
    selectedAgent, defaultAgent, agentsList,
    initialize, fetchAgents, fetchAgentDetail, fetchDefaultAgent,
    selectAgent, clearError, reset
  }
}, {
  persist: {
    key: 'agent-store',
    storage: localStorage,
    pick: ['selectedAgentId']
  }
})
