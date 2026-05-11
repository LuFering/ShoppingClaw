<template>
  <div class="chat-container">
    <ChatSidebarComponent
      :current-chat-id="currentChatId"
      :chats-list="chatsList"
      :is-sidebar-open="chatUIStore.isSidebarOpen"
      :is-initial-render="localUIState.isInitialRender"
      :single-mode="props.singleMode"
      :agents="agents"
      :selected-agent-id="currentAgentId"
      :is-creating-new-chat="chatUIStore.creatingNewChat"
      :has-more-chats="hasMoreChats"
      :is-loading-more="isLoadingMoreChats"
      @create-chat="createNewChat"
      @select-chat="selectChat"
      @delete-chat="deleteChat"
      @rename-chat="renameChat"
      @toggle-pin="togglePinChat"
      @toggle-sidebar="toggleSidebar"
      @load-more-chats="loadMoreChats"
      :class="{ 'sidebar-open': chatUIStore.isSidebarOpen, 'no-transition': localUIState.isInitialRender }"
    />
    <div class="chat">
      <div class="chat-header">
        <div class="header__left">
          <div type="button" class="agent-nav-btn"
            v-if="!chatUIStore.isSidebarOpen"
            @click="toggleSidebar">
            <PanelLeftOpen class="nav-btn-icon" size="18" />
          </div>
          <div type="button" class="agent-nav-btn"
            v-if="!chatUIStore.isSidebarOpen"
            :class="{ 'is-disabled': chatUIStore.creatingNewChat }"
            @click="createNewChat">
            <LoaderCircle v-if="chatUIStore.creatingNewChat" class="nav-btn-icon loading-icon" size="18" />
            <MessageCirclePlus v-else class="nav-btn-icon" size="16" />
            <span class="text">新对话</span>
          </div>
        </div>
        <div class="header__right">
          <slot name="header-right"></slot>
        </div>
      </div>

      <div class="chat-content-container">
        <div class="chat-main" ref="chatMainContainer">
          <div class="chat-box" ref="messagesContainer">
            <div class="conv-box" v-for="(conv, index) in conversations" :key="index">
              <AgentMessageComponent
                v-for="(message, msgIndex) in conv.messages"
                :message="message"
                :key="msgIndex"
                :is-processing="isProcessing && conv.status === 'streaming' && msgIndex === conv.messages.length - 1"
                @retry="retryMessage(message)"
              />
            </div>

            <div class="generating-status" v-if="isProcessing && conversations.length > 0">
              <div class="generating-indicator">
                <div class="loading-dots">
                  <div></div><div></div><div></div>
                </div>
                <span class="generating-text">正在生成回复...</span>
              </div>
            </div>
          </div>
          <div class="bottom" :class="{ 'start-screen': !conversations.length }">
            <div class="message-input-wrapper">
              <div v-if="isLoadingMessages" class="chat-loading">
                <div class="loading-spinner"></div>
                <span>正在加载消息...</span>
              </div>

              <div v-if="!conversations.length" class="chat-examples-input">
                <h1>{{ currentAgentName }}，有什么可以帮您？</h1>
              </div>

              <div v-if="showStartAgentSegment" class="agent-segment-wrapper">
                <a-segmented
                  :value="currentAgentId"
                  :options="agentSegmentOptions"
                  @change="handleStartAgentChange"
                />
              </div>

              <AgentInputArea
                ref="messageInputRef"
                v-model="userInput"
                :is-loading="isProcessing"
                :disabled="!currentAgent"
                :send-button-disabled="(!userInput || !currentAgent) && !isProcessing"
                placeholder="输入问题..."
                :supports-file-upload="false"
                :agent-id="currentAgentId"
                :thread-id="currentChatId"
                :ensure-thread="ensureActiveThread"
                :has-state-content="false"
                :is-panel-open="false"
                @send="handleSendOrStop"
              >
                <template #actions-left-extra>
                  <slot name="input-actions-left"></slot>
                </template>
              </AgentInputArea>

              <!-- 示例问题 -->
              <div class="example-questions" v-if="!conversations.length && exampleQuestions.length > 0">
                <div class="example-chips">
                  <div v-for="question in exampleQuestions" :key="question.id"
                    class="example-chip" @click="handleExampleClick(question.text)">
                    {{ question.text }}
                  </div>
                </div>
              </div>

              <div class="bottom-actions" v-if="conversations.length > 0">
                <p class="note">当前智能体：{{ currentThreadAgentName }}；请注意辨别内容的可靠性</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, watch, nextTick, computed, onUnmounted } from 'vue'
import AgentInputArea from '@/components/AgentInputArea.vue'
import AgentMessageComponent from '@/components/AgentMessageComponent.vue'
import ChatSidebarComponent from '@/components/ChatSidebarComponent.vue'
import { PanelLeftOpen, MessageCirclePlus, LoaderCircle } from 'lucide-vue-next'
import { handleChatError } from '@/utils/errorHandler'
import { ScrollController } from '@/utils/scrollController'
import { useAgentStore } from '@/stores/agent'
import { useChatUIStore } from '@/stores/chatUI'
import { useUserStore } from '@/stores/user'
import { storeToRefs } from 'pinia'
import { agentApi, threadApi } from '@/apis'


const props = defineProps({
  agentId: { type: String, default: '' },
  singleMode: { type: Boolean, default: true }
})

const agentStore = useAgentStore()
const chatUIStore = useChatUIStore()
const userStore = useUserStore()
const { agents, selectedAgentId, defaultAgentId } = storeToRefs(agentStore)

const userInput = ref('')

// 从智能体元数据获取示例问题
const exampleQuestions = computed(() => {
  const agentId = currentAgentId.value
  let examples = []
  if (agentId && agents.value?.length) {
    const agent = agents.value.find((a) => a.id === agentId)
    examples = agent?.examples || []
  }
  return examples.map((text, index) => ({ id: index + 1, text }))
})

const chatState = reactive({
  currentThreadId: null,
  threadStates: {}
})

const threads = ref([])
const threadMessages = ref({})
const hasMoreChats = ref(true)
const isLoadingMoreChats = ref(false)

const localUIState = reactive({ isInitialRender: true })

const currentAgentId = computed(() => {
  return props.singleMode ? props.agentId || defaultAgentId.value : selectedAgentId.value
})

const currentAgentName = computed(() => {
  return currentAgent.value?.name || '智能体'
})

const currentAgent = computed(() => {
  if (!currentAgentId.value || !agents.value?.length) return null
  return agents.value.find((a) => a.id === currentAgentId.value) || null
})

const chatsList = computed(() => threads.value || [])
const currentChatId = computed(() => chatState.currentThreadId)

const currentThread = computed(() => {
  if (!currentChatId.value) return null
  return threads.value.find((t) => t.id === currentChatId.value) || null
})

const currentThreadAgentName = computed(() => {
  const threadAgentId = currentThread.value?.agent_id
  if (threadAgentId && agents.value?.length) {
    const threadAgent = agents.value.find((a) => a.id === threadAgentId)
    if (threadAgent?.name) return threadAgent.name
  }
  return currentAgentName.value
})

const agentSegmentOptions = computed(() => {
  return (agents.value || []).map((agent) => ({
    label: agent.name || 'Unknown',
    value: agent.id
  }))
})

const showStartAgentSegment = computed(() => {
  return !props.singleMode && !conversations.value.length && agentSegmentOptions.value.length > 1
})

const handleStartAgentChange = async (agentId) => {
  if (!agentId || agentId === currentAgentId.value) return
  if (conversations.value.length > 0) return
  try {
    await agentStore.selectAgent(agentId)
  } catch (error) {
    handleChatError(error, 'load')
  }
}

const currentThreadMessages = computed(() => threadMessages.value[currentChatId.value] || [])

// 在线程状态中管理流式数据
const createOnGoingConvState = () => ({
  msgChunks: {},
  currentRequestKey: null,
  currentAssistantKey: null,
})

const getThreadState = (threadId, autoCreate = true) => {
  if (!threadId) return null
  if (!chatState.threadStates[threadId] && autoCreate) {
    chatState.threadStates[threadId] = {
      isStreaming: false,
      onGoingConv: createOnGoingConvState(),
      agentState: null,
    }
  }
  return chatState.threadStates[threadId] || null
}

const currentThreadState = computed(() => getThreadState(currentChatId.value))

const onGoingConvMessages = computed(() => {
  const ts = currentThreadState.value
  if (!ts?.onGoingConv) return []
  const chunks = ts.onGoingConv.msgChunks
  // 简单合并chunk - 将内容连接起来
  const msgs = Object.values(chunks).map(c => ({
    type: 'ai',
    content: typeof c === 'string' ? c : (c.content || ''),
  }))
  return msgs.filter(m => m.type !== 'tool')
})

const historyConversations = computed(() => {
  const msgs = currentThreadMessages.value || []
  return msgs.length ? [{ messages: msgs, status: 'finished' }] : []
})

const conversations = computed(() => {
  const historyConvs = historyConversations.value
  if (onGoingConvMessages.value.length > 0) {
    return [...historyConvs, { messages: onGoingConvMessages.value, status: 'streaming' }]
  }
  return historyConvs
})

const isLoadingMessages = computed(() => chatUIStore.isLoadingMessages)
const isStreaming = computed(() => currentThreadState.value?.isStreaming || false)
const isProcessing = computed(() => isStreaming.value)

const scrollController = new ScrollController('.chat-main')

onMounted(() => {
  nextTick(() => {
    const chatMainContainer = document.querySelector('.chat-main')
    if (chatMainContainer) {
      chatMainContainer.addEventListener('scroll', scrollController.handleScroll, { passive: true })
    }
  })
  setTimeout(() => { localUIState.isInitialRender = false }, 300)
})

onUnmounted(() => {
  scrollController.cleanup()
})

// 线程管理
const ensureActiveThread = async () => {
  if (currentChatId.value) return currentChatId.value
  await createNewChat()
  return currentChatId.value
}

const createNewChat = async () => {
  if (chatUIStore.creatingNewChat) return
  chatUIStore.creatingNewChat = true
  try {
    const agentId = currentAgentId.value
    if (!agentId) return
    const newThread = await threadApi.createThread(agentId, '新的对话')
    threads.value.unshift(newThread)
    await selectChat(newThread.id)
  } catch (error) {
    handleChatError(error, 'create')
  } finally {
    chatUIStore.creatingNewChat = false
  }
}

const selectChat = async (threadId) => {
  if (!threadId || threadId === currentChatId.value) return
  chatState.currentThreadId = threadId
  chatUIStore.isLoadingMessages = true
  try {
    const agentId = currentThread.value?.agent_id || currentAgentId.value
    const [historyRes] = await Promise.all([
      agentApi.getAgentHistory(agentId, threadId),
    ])
    threadMessages.value[threadId] = historyRes?.history || []
  } catch (error) {
    console.error('Failed to load messages:', error)
  } finally {
    chatUIStore.isLoadingMessages = false
  }
}

const deleteChat = async (threadId) => {
  try {
    await threadApi.deleteThread(threadId)
    threads.value = threads.value.filter((t) => t.id !== threadId)
    if (currentChatId.value === threadId) {
      chatState.currentThreadId = null
      chatState.threadStates = {}
      const remaining = threads.value
      if (remaining.length > 0) {
        await selectChat(remaining[0].id)
      }
    }
  } catch (error) {
    handleChatError(error, 'delete')
  }
}

const renameChat = async (threadId, title) => {
  try {
    await threadApi.updateThread(threadId, title)
    const thread = threads.value.find((t) => t.id === threadId)
    if (thread) thread.title = title
  } catch (error) {
    handleChatError(error, 'rename')
  }
}

const togglePinChat = async (threadId, isPinned) => {
  try {
    await threadApi.updateThread(threadId, undefined, isPinned)
    const thread = threads.value.find((t) => t.id === threadId)
    if (thread) thread.is_pinned = isPinned
  } catch (error) {
    handleChatError(error, 'pin')
  }
}

const loadMoreChats = async () => {
  if (isLoadingMoreChats.value || !hasMoreChats.value) return
  isLoadingMoreChats.value = true
  try {
    const moreThreads = await threadApi.getThreads(null, 100, threads.value.length)
    if (moreThreads?.length) {
      threads.value.push(...moreThreads)
    } else {
      hasMoreChats.value = false
    }
  } catch (error) {
    console.error('Failed to load more chats:', error)
  } finally {
    isLoadingMoreChats.value = false
  }
}

const toggleSidebar = () => {
  chatUIStore.isSidebarOpen = !chatUIStore.isSidebarOpen
}

const handleSendOrStop = async () => {
  if (isProcessing.value) {
    // 停止生成
    const ts = currentThreadState.value
    if (ts) ts.isStreaming = false
    return
  }
  if (!userInput.value.trim() || !currentAgent.value) return

  const threadId = await ensureActiveThread()
  if (!threadId) return

  const query = userInput.value
  userInput.value = ''

  // 添加用户消息
  const userMsg = { type: 'human', content: query, id: Date.now() }
  if (!threadMessages.value[threadId]) {
    threadMessages.value[threadId] = []
  }
  threadMessages.value[threadId].push(userMsg)

  // 开始流式处理
  const ts = getThreadState(threadId)
  ts.isStreaming = true
  ts.onGoingConv = createOnGoingConvState()

  try {
    const response = await agentApi.sendAgentMessage(currentAgentId.value, {
      query,
      config: {
        thread_id: threadId,
        model: currentAgentId.value,
      },
      meta: {}
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    let streamingContent = ''
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed) continue
        try {
          const chunk = JSON.parse(trimmed)
          if (chunk.type === 'text' || chunk.type === 'ai') {
            streamingContent += chunk.content || ''
          } else if (chunk.content) {
            streamingContent += chunk.content
          }
          // 更新进行中消息
          const key = 'streaming-msg'
          ts.onGoingConv.msgChunks[key] = {
            type: 'ai',
            content: streamingContent,
          }
        } catch (e) {
          // 忽略解析错误
        }
      }
    }

    // 流式结束，保存消息
    if (streamingContent) {
      threadMessages.value[threadId].push({
        type: 'ai',
        content: streamingContent,
        id: Date.now(),
      })
    }
  } catch (error) {
    console.error('Stream error:', error)
    threadMessages.value[threadId].push({
      type: 'ai',
      content: '',
      error_type: 'unexpect',
      error_message: error.message,
      id: Date.now(),
    })
  } finally {
    ts.isStreaming = false
    ts.onGoingConv = createOnGoingConvState()
  }
}

const handleExampleClick = (text) => {
  userInput.value = text
  handleSendOrStop()
}

const retryMessage = (message) => {
  if (message?.content) {
    userInput.value = message.content
    handleSendOrStop()
  }
}

// 初始化 - 加载线程列表
onMounted(async () => {
  try {
    const threadList = await threadApi.getThreads(null, 100, 0)
    if (threadList?.length) {
      threads.value = threadList
    }
  } catch (e) {
    console.warn('Failed to load threads:', e)
  }
})

defineExpose({
  getExportPayload: () => ({
    messages: threadMessages.value[currentChatId.value] || [],
    onGoingMessages: onGoingConvMessages.value,
  })
})
</script>

<style lang="less" scoped>
.chat-container {
  display: flex;
  flex-direction: row;
  width: 100%;
  height: 100vh;
  overflow: hidden;
}

.chat {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  border-bottom: 1px solid var(--gray-100);
  min-height: 48px;

  .header__left, .header__right {
    display: flex;
    align-items: center;
    gap: 8px;
  }
}

.agent-nav-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  color: var(--gray-700);
  transition: all 0.2s;
  border: none;
  background: transparent;

  &:hover { background-color: var(--gray-100); color: var(--main-color); }
  &.is-disabled { opacity: 0.5; pointer-events: none; }

  .loading-icon { animation: rotate 1s linear infinite; }
}

.chat-content-container {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

.chat-box {
  flex: 1;
  padding: 16px 24px;
  max-width: 800px;
  width: 100%;
  margin: 0 auto;
}

.conv-box {
  margin-bottom: 8px;
}

.generating-status {
  padding: 12px 0;
  .generating-indicator {
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--gray-500);
    font-size: 14px;
  }
  .loading-dots {
    display: flex;
    gap: 4px;
    div {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: var(--gray-400);
      animation: dotPulse 1.4s infinite ease-in-out both;
      &:nth-child(2) { animation-delay: 0.16s; }
      &:nth-child(3) { animation-delay: 0.32s; }
    }
  }
}

.bottom {
  padding: 0 24px 24px;
  max-width: 800px;
  width: 100%;
  margin: 0 auto;
}

.chat-examples-input {
  text-align: center;
  padding: 24px 0 16px;
  h1 { font-size: 1.5rem; font-weight: 600; color: var(--gray-900); }
}

.agent-segment-wrapper {
  display: flex;
  justify-content: center;
  margin-bottom: 12px;
}

.example-questions {
  padding: 12px 0;
  .example-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    justify-content: center;
  }
  .example-chip {
    padding: 6px 14px;
    border-radius: 16px;
    border: 1px solid var(--gray-200);
    font-size: 13px;
    cursor: pointer;
    color: var(--gray-700);
    transition: all 0.2s;
    &:hover { border-color: var(--main-color); color: var(--main-color); background: var(--main-10); }
  }
}

.bottom-actions {
  text-align: center;
  padding-top: 8px;
  .note { font-size: 12px; color: var(--gray-400); }
}

.chat-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: center;
  padding: 12px;
  color: var(--gray-500);
}

.loading-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid var(--gray-200);
  border-top-color: var(--main-color);
  border-radius: 50%;
  animation: rotate 0.8s linear infinite;
}

@keyframes rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@keyframes dotPulse {
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1); }
}
</style>
