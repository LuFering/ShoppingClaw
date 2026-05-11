<template>
  <div class="agent-view">
    <div class="agent-view-body">
      <div class="content">
        <AgentChatComponent
          ref="chatComponentRef"
          :single-mode="false"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AgentChatComponent from '@/components/AgentChatComponent.vue'
import { useAgentStore } from '@/stores/agent'

const chatComponentRef = ref(null)
const agentStore = useAgentStore()
const route = useRoute()
const router = useRouter()

const syncingRouteAgent = ref(false)

const getRouteAgentId = () => {
  const value = route.params.agent_id
  return typeof value === 'string' ? value : ''
}

const syncSelectedAgentFromRoute = async () => {
  const routeAgentId = getRouteAgentId()
  if (!routeAgentId) return

  syncingRouteAgent.value = true
  try {
    if (!agentStore.isInitialized) {
      await agentStore.initialize()
    }

    const routeAgentExists = (agentStore.agents || []).some((agent) => agent.id === routeAgentId)
    if (!routeAgentExists) {
      if (agentStore.selectedAgentId) {
        await router.replace({ name: 'AgentCompWithId', params: { agent_id: agentStore.selectedAgentId } })
      }
      return
    }

    if (agentStore.selectedAgentId !== routeAgentId) {
      agentStore.selectAgent(routeAgentId)
    }
  } catch (error) {
    console.error('同步智能体失败:', error)
  } finally {
    syncingRouteAgent.value = false
  }
}

watch(
  () => route.params.agent_id,
  () => { syncSelectedAgentFromRoute() },
  { immediate: true }
)

watch(() => agentStore.selectedAgentId, (newAgentId) => {
  if (!newAgentId || syncingRouteAgent.value) return
  const routeAgentId = getRouteAgentId()
  if (routeAgentId === newAgentId) return
  router.replace({ name: 'AgentCompWithId', params: { agent_id: newAgentId } })
})
</script>

<style lang="less" scoped>
.agent-view {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100vh;
  overflow: hidden;
}

.agent-view-body {
  display: flex;
  flex-direction: row;
  width: 100%;
  flex: 1;
  height: 100%;
  overflow: hidden;
  position: relative;

  .content {
    flex: 1;
    display: flex;
    flex-direction: column;
  }
}

.content {
  flex: 1;
  overflow: hidden;
}
</style>
