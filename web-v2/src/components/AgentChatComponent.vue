<template>
  <div class="chat-container">
    <ChatSidebarComponent
      :current-chat-id="currentChatId"
      :chats-list="chatsList"
      :chat-previews="chatPreviews"
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
          <!-- 运行状态栏开关 -->
          <div
            v-if="conversations.length > 0 || thinkingState.steps.length > 0"
            type="button"
            class="agent-nav-btn"
            :class="{ active: statePanelOpen }"
            @click="statePanelOpen = !statePanelOpen"
          >
            <Activity class="nav-btn-icon" size="18" />
            <span class="text">运行状态</span>
          </div>
          <slot name="header-right"></slot>
        </div>
      </div>

      <div class="chat-content-container">
        <div class="chat-main" ref="chatMainContainer">
          <div class="chat-box" ref="messagesContainer">
            <!-- 欢迎页品牌区域 (空状态显示) -->
            <div v-if="!conversations.length" class="welcome-brand">
              <img 
                src="@/assets/parrot-logo.png" 
                alt="ShoppingClaw Logo" 
                class="brand-logo" 
              />
              <div class="brand-text">
                <h2 class="brand-name">ShoppingClaw</h2>
                <p class="brand-slogan">有虾购，想购就 go</p>
              </div>
            </div>

            <!-- 固定云朵层 (空状态显示) -->
            <div v-if="!conversations.length" class="fixed-clouds-layer">
              <!-- 上层：左右两栏竖向排列的文本引导云朵 -->
              <div class="text-clouds-wrapper">
                <div class="text-clouds-column left-column">
                  <div 
                    v-for="cloud in currentTextClouds.slice(0, 3)" 
                    :key="cloud.id"
                    class="cloud-pill text-cloud"
                    @click="userInput = cloud.text; messageInputRef?.focusInput()"
                  >
                    <span class="text-content" :class="{ 'fading': cloud.isFading }">{{ cloud.text }}</span>
                    <div class="action-indicator">
                      <ChevronRight class="arrow-icon" :size="16" />
                      <span class="buy-text">一键 go</span>
                    </div>
                  </div>
                </div>
                <div class="text-clouds-column right-column">
                  <div 
                    v-for="cloud in currentTextClouds.slice(3, 6)" 
                    :key="cloud.id + '-r'"
                    class="cloud-pill text-cloud"
                    @click="userInput = cloud.text; messageInputRef?.focusInput()"
                  >
                    <span class="text-content" :class="{ 'fading': cloud.isFading }">{{ cloud.text }}</span>
                    <div class="action-indicator">
                      <ChevronRight class="arrow-icon" :size="16" />
                      <span class="buy-text">一键 go</span>
                    </div>
                  </div>
                </div>
              </div>

              <!-- 下层：状态卡片排（滚动队列：队头淡出、队尾滑入，始终一排 4 张） -->
              <TransitionGroup
                tag="div"
                name="status"
                class="icon-clouds-row status-row"
              >
                <div
                  v-for="st in visibleStatuses"
                  :key="st.id"
                  class="cloud-pill status-card"
                  :style="{ '--stc': statusTypeMeta[st.type].color }"
                >
                  <span class="status-ico">
                    <component :is="statusTypeMeta[st.type].icon" :size="15" />
                  </span>
                  <div class="status-body">
                    <div class="status-head">
                      <span class="status-type">{{ statusTypeMeta[st.type].label }}</span>
                      <span class="status-time num">{{ st.time }}</span>
                    </div>
                    <p class="status-main">{{ st.main }}</p>
                    <p class="status-sub">{{ st.sub }}</p>
                  </div>
                </div>
              </TransitionGroup>
              <p v-if="homeDemo" class="demo-note">监控与决策卡片为演示数据（/api/events/recent 未就绪）</p>
            </div>
            <div class="conv-box" v-for="(view, ci) in conversationViews" :key="view.conv.key ?? ci">
              <template v-for="(item, ii) in view.items" :key="ci + '-' + ii">
                <AgentMessageComponent
                  v-if="item.type === 'message'"
                  :message="item.message"
                  :is-processing="isProcessing && view.conv.status === 'streaming' && ii === view.lastMsgItem"
                  @retry="retryMessage(item.message)"
                />
                <ProcessGroup
                  v-else
                  :steps="item.steps"
                  :plan-steps="item.planSteps"
                  :tool-calls="item.toolCalls"
                  :live="item.live && isProcessing"
                />
              </template>
            </div>
            <!-- 底部占位，防止消息被输入框遮挡 -->
            <div class="chat-bottom-spacer"></div>
          </div>
        </div>
        <!-- 悬浮底部输入框 -->
        <div class="bottom" :class="{ 'start-screen': !conversations.length }">
          <div class="message-input-wrapper">
            <div v-if="isLoadingMessages" class="chat-loading">
              <div class="loading-spinner"></div>
              <span>正在加载消息...</span>
            </div>

            <div v-if="!conversations.length" class="chat-examples-input">
              <h1>{{ currentAgentName }}：想买什么，直接说</h1>
              <p class="chat-examples-sub">描述越随意越好——预算、给谁买、在意什么，它会先检索、再对比、再做风险评审</p>
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
              :placeholder="conversations.length ? '继续追问，比如：和另一款比，哪个更值？' : '例：预算 5000 给爸妈买台洗地机，要静音好打理'"
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
    
    <!-- 右侧运行状态栏（无会话时不渲染空面板；float 时悬浮于聊天区右缘） -->
    <StatePanel
      v-if="conversations.length > 0 || thinkingState.steps.length > 0 || productIndex.length"
      :open="statePanelOpen"
      :mode="statePanelMode"
      :statistics="lastStatistics"
      :plan-steps="thinkingState.planSteps || []"
      :products="productIndex"
      :subagents="subagentCalls"
      @close="statePanelOpen = false"
      @toggle-mode="statePanelMode = statePanelMode === 'dock' ? 'float' : 'dock'"
    />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, watch, nextTick, computed, onUnmounted } from 'vue'
import AgentInputArea from '@/components/AgentInputArea.vue'
import AgentMessageComponent from '@/components/AgentMessageComponent.vue'
import ChatSidebarComponent from '@/components/ChatSidebarComponent.vue'
import ProcessGroup from '@/components/ProcessGroup.vue'
import StatePanel from '@/components/StatePanel.vue'
import { buildDisplayItems } from '@/utils/messageGrouping'
import { PanelLeftOpen, MessageCirclePlus, LoaderCircle, ChevronRight, Brain, TrendingDown, Tag, Package, Heart, Wrench, ShieldAlert, Star, Activity } from 'lucide-vue-next'
import { handleChatError } from '@/utils/errorHandler'
import { ScrollController } from '@/utils/scrollController'
import { useAgentStore } from '@/stores/agent'
import { useChatUIStore } from '@/stores/chatUI'
import { useUserStore } from '@/stores/user'
import { storeToRefs } from 'pinia'
import { useRoute, useRouter } from 'vue-router'
import { agentApi, threadApi } from '@/apis'
import { homeApi } from '@/apis/home_api'


const props = defineProps({
  agentId: { type: String, default: '' },
  singleMode: { type: Boolean, default: true }
})

const agentStore = useAgentStore()
const chatUIStore = useChatUIStore()
const userStore = useUserStore()
const { agents, selectedAgentId, defaultAgentId } = storeToRefs(agentStore)

const userInput = ref('')

// 欢迎区文本云：默认种子（契约 GET /api/chat/home/suggestions，失败降级并标演示）
const scenePrompts = [
  '帮我选 3000 元降噪耳机',
  '618 该买扫地机器人吗',
  '对比 iPhone 16 和华为 Pura 70',
  '推荐性价比笔记本电脑',
  '学生党平价手机推荐',
  '哪些家电值得囤货'
]
const promptsPool = ref([...scenePrompts])

// 动态文本云朵状态 (固定显示，增加到 6 个以支持两栏)
const currentTextClouds = ref(scenePrompts.slice(0, 6).map((text, index) => ({
  id: `t-${index}`,
  text,
  isFading: false
})))
let textRefreshTimer = null

const homeDemo = ref(false)

// 状态卡片排：类型语义（颜色/标签/图标）—— 替代原"手机数码"类分类入口
const statusTypeMeta = {
  price:   { label: '盯价 · 降价', color: '#d6543f', icon: TrendingDown },
  coupon:  { label: '券 · 到期',   color: '#b45309', icon: Tag },
  stock:   { label: '库存 · 补货', color: '#185fa5', icon: Package },
  decide:  { label: '决策 · 待定', color: '#178a67', icon: Brain },
  fav:     { label: '收藏 · 动态', color: '#178a67', icon: Star },
  prefer:  { label: '偏好 · 确认', color: '#178a67', icon: Heart },
  care:    { label: '售后 · 耗材', color: '#185fa5', icon: Wrench },
  review:  { label: '风评 · 异动', color: '#b45309', icon: ShieldAlert },
}

// 状态卡片数据：来自 /api/events/recent（失败降级演示数据并标记）
const statusMaster = [
  { id: 'st-1', type: 'coupon', main: '你领的 ¥100 券明天过期', sub: '戴森 V12 · 旗舰店', time: '明天' },
  { id: 'st-2', type: 'price',  main: '添可芙万 3.0 降到 ¥2199', sub: '已到你的目标价', time: '2小时前' },
  { id: 'st-3', type: 'stock',  main: '看中的通勤背包有货了', sub: 'Incase Icon · 灰色 M', time: '昨天' },
  { id: 'st-4', type: 'decide', main: '洗地机已比 3 款，等你拍板', sub: '预算 5000 · 给爸妈用', time: '昨天' },
]

// 滚动队列：始终一排（≤4 张）
const statusQueue = ref(statusMaster.map((s) => ({ ...s })))
const visibleStatuses = computed(() => statusQueue.value)

// 刷新文本云朵 (原地平滑切换内容，从已加载的提示池轮换)
const refreshTextClouds = () => {
  const pool = promptsPool.value.length ? promptsPool.value : scenePrompts
  const shuffled = [...pool].sort(() => 0.5 - Math.random())

  // 第一步：触发淡出动画
  currentTextClouds.value.forEach(cloud => cloud.isFading = true)

  // 第二步：等待淡出完成后更新内容并淡入
  setTimeout(() => {
    currentTextClouds.value.forEach((cloud, index) => {
      cloud.text = shuffled[index % shuffled.length]
      cloud.isFading = false
    })
  }, 300) // 300ms 对应 CSS 中的 transition 时间
}

// 欢迎区数据：GET /api/chat/home/suggestions + /api/events/recent（失败降级演示，homeDemo 标记）
const loadHomeData = async () => {
  try {
    const { prompts, events, demo } = await homeApi.getHomeData()
    homeDemo.value = demo
    if (prompts?.length) {
      promptsPool.value = prompts
      currentTextClouds.value.forEach((cloud, i) => { cloud.text = prompts[i % prompts.length] })
    }
    if (events?.length) {
      statusQueue.value = events.slice(0, 4).map((e, i) => ({
        id: e.id || `st-home-${i}`,
        type: e.type,
        main: e.main,
        sub: e.sub || '',
        time: e.time || ''
      }))
    }
  } catch (e) {
    // homeApi 内部已兜底，此处仅防御
    console.warn('home data load failed:', e)
  }
}

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

// 思考过程状态管理
const thinkingState = reactive({
  isOpen: false,
  steps: [],
  planSteps: [],
  toolCalls: [],
  isInitialRender: true
})

// 每个线程的思考过程快照（切换对话时恢复）
const savedThinkingStates = ref({})

// 运行状态栏（Yuxi 式右侧 340px 状态面板；dock=停靠推挤内容 / float=悬浮覆盖）
const statePanelOpen = ref(window.innerWidth >= 1280)
const statePanelMode = ref('dock')
const lastStatistics = ref(null)

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

// 会话列表摘要：打开过/加载过消息的会话，取最后一条有效内容
const chatPreviews = computed(() => {
  const out = {}
  for (const [tid, msgs] of Object.entries(threadMessages.value)) {
    if (!msgs || !msgs.length) continue
    let last = null
    for (let i = msgs.length - 1; i >= 0; i--) {
      const m = msgs[i]
      if (!m || m.type === 'thinking') continue
      last = m
      break
    }
    const text = last?.content || ''
    const s = text.replace(/\s+/g, ' ').trim()
    if (s) out[tid] = s.length > 48 ? s.slice(0, 48) + '…' : s
  }
  return out
})

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
  messages: [],
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
  return ts.onGoingConv.messages
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

// 每个会话的展示项：消息 + 内联过程组（Yuxi 式）。
// live 过程组只属于正在流式的那轮；已完成轮次的快照插在最后一条用户消息之后。
// 注意：后端 history 里每轮 thinking 已是独立消息（buildDisplayItems 会生成过程组），
// 此时若再 append 内存快照会重复——只有消息流里没有 thinking 消息（本轮刚流式落库）才 append。
const conversationViews = computed(() => {
  const snapshot = savedThinkingStates.value[currentChatId.value] || null
  return conversations.value.map((conv) => {
    const isStream = conv.status === 'streaming'
    const hasThinkingMsgs = (conv.messages || []).some((m) => m && m.type === 'thinking' && m.thinkingProcess)
    const append = isStream
      ? { steps: thinkingState.steps, planSteps: thinkingState.planSteps, toolCalls: thinkingState.toolCalls, live: isProcessing.value }
      : hasThinkingMsgs
        ? null
        : snapshot
    const items = buildDisplayItems(conv.messages, append)
    let lastMsgItem = -1
    items.forEach((it, i) => { if (it.type === 'message') lastMsgItem = i })
    return { conv: { ...conv, key: (isStream ? 'live-' : 'hist-') + currentChatId.value }, items, lastMsgItem }
  })
})

// 状态栏数据：产物（商品卡）与子智能体派发
const productIndex = computed(() => {
  const out = []
  for (const m of currentThreadMessages.value) {
    if (Array.isArray(m.productCards)) out.push(...m.productCards)
  }
  const ts = currentThreadState.value
  for (const m of ts?.onGoingConv?.messages || []) {
    if (Array.isArray(m.productCards)) out.push(...m.productCards)
  }
  return out.slice(0, 8)
})

const subagentCalls = computed(() =>
  (thinkingState.toolCalls || []).filter((t) => /task|subagent/i.test(t.name || t.function || ''))
)

const isLoadingMessages = computed(() => chatUIStore.isLoadingMessages)
const isStreaming = computed(() => currentThreadState.value?.isStreaming || false)
const isProcessing = computed(() => isStreaming.value)

const scrollController = new ScrollController('.chat-main')

onMounted(async () => {
  nextTick(() => {
    const chatMainContainer = document.querySelector('.chat-main')
    if (chatMainContainer) {
      chatMainContainer.addEventListener('scroll', scrollController.handleScroll, { passive: true })
    }
  })
  setTimeout(() => { localUIState.isInitialRender = false }, 300)

  // 欢迎区数据：真实契约优先，失败降级演示（homeApi 内部处理）
  loadHomeData()

  // 启动文本定时刷新 (每 5 秒)
  refreshTextClouds()
  textRefreshTimer = setInterval(refreshTextClouds, 5000)
})

onUnmounted(() => {
  scrollController.cleanup()
  if (textRefreshTimer) clearInterval(textRefreshTimer)
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
  // 切换对话时恢复该对话的思考过程快照
  restoreThinkingState(threadId)
  try {
    const agentId = currentThread.value?.agent_id || currentAgentId.value
    const [historyRes] = await Promise.all([
      agentApi.getAgentHistory(agentId, threadId),
    ])
    const messages = historyRes?.history || []
    threadMessages.value[threadId] = messages
    
    // 从后端历史消息中恢复思考过程（仅在内存快照不存在时）
    if (!savedThinkingStates.value[threadId]) {
      const thinkingMsg = messages.find(m => m.type === 'thinking' && m.thinkingProcess)
      if (thinkingMsg) {
        const tp = thinkingMsg.thinkingProcess
        savedThinkingStates.value[threadId] = {
          steps: tp.steps || [],
          planSteps: tp.planSteps || [],
          toolCalls: tp.toolCalls || [],
        }
        // 重新恢复（现在有数据了）
        restoreThinkingState(threadId)
      }
    }
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
    // 清理已删除线程的思考过程快照
    delete savedThinkingStates.value[threadId]
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

// 添加思考步骤
const addThinkingStep = (step) => {
  if (!step?.content) return
  
  // 检查是否已有活跃的思考步骤（类型为 thinking）
  const lastStep = thinkingState.steps[thinkingState.steps.length - 1]
  if (lastStep && lastStep.type === 'thinking' && lastStep.status === 'active') {
    // 累积内容到最后一个步骤
    lastStep.content = (lastStep.content || '') + step.content
  } else {
    // 创建新步骤
    thinkingState.steps.push({
      ...step,
      status: step.status || 'active',
      timestamp: Date.now()
    })
  }
  
  // 自动打开边栏
  if (!thinkingState.isOpen) {
    thinkingState.isOpen = true
  }
}

// 更新最后一个思考步骤
const updateLastThinkingStep = (updates) => {
  if (thinkingState.steps.length > 0) {
    const lastIndex = thinkingState.steps.length - 1
    thinkingState.steps[lastIndex] = {
      ...thinkingState.steps[lastIndex],
      ...updates
    }
  }
}

// 清空思考步骤
const clearThinkingSteps = () => {
  thinkingState.steps = []
  thinkingState.planSteps = []
  thinkingState.toolCalls = []
}

// 保存当前思考过程到线程快照
const snapshotThinkingState = (threadId) => {
  if (!threadId) return
  savedThinkingStates.value[threadId] = {
    steps: [...thinkingState.steps],
    planSteps: [...thinkingState.planSteps],
    toolCalls: [...thinkingState.toolCalls],
  }
}

// 从线程快照恢复思考过程
const restoreThinkingState = (threadId) => {
  const saved = threadId ? savedThinkingStates.value[threadId] : null
  if (saved) {
    thinkingState.steps.splice(0, thinkingState.steps.length, ...(saved.steps || []))
    thinkingState.planSteps.splice(0, thinkingState.planSteps.length, ...(saved.planSteps || []))
    thinkingState.toolCalls.splice(0, thinkingState.toolCalls.length, ...(saved.toolCalls || []))
  } else {
    clearThinkingSteps()
  }
}

const normalizeProcessStatus = (status) => {
  const value = String(status || 'pending').toLowerCase()
  if (['completed', 'complete', 'done', 'success', 'called'].includes(value)) return 'completed'
  if (['in_progress', 'running', 'active', 'processing', 'calling'].includes(value)) return 'running'
  if (['failed', 'error', 'cancelled', 'canceled'].includes(value)) return 'failed'
  return 'pending'
}

const applyPlanSteps = (steps = []) => {
  const normalized = steps.map((step, index) => {
    const description = step.description || step.content || step.title || `步骤 ${index + 1}`
    return {
      ...step,
      id: String(step.id || `step_${index + 1}`),
      description,
      title: step.title || description,
      status: normalizeProcessStatus(step.status),
      toolCallIds: step.toolCallIds || step.tool_call_ids || []
    }
  })
  thinkingState.planSteps.splice(0, thinkingState.planSteps.length, ...normalized)
}

const upsertToolCall = (toolCall = {}) => {
  const meta = toolCall.tool_meta || {}
  const toolCallId = String(toolCall.tool_call_id || toolCall.id || Date.now())
  const existingIndex = thinkingState.toolCalls.findIndex((item) => item.toolCallId === toolCallId || item.id === toolCallId)
  const item = {
    id: toolCallId,
    name: toolCall.function || toolCall.name || meta.name || 'unknown',
    args: toolCall.args || {},
    output: toolCall.output ?? toolCall.content ?? null,
    status: normalizeProcessStatus(toolCall.status),
    duration: toolCall.duration_ms ?? toolCall.duration ?? null,
    icon: toolCall.icon || meta.icon,
    category: meta.category,
    toolCallId
  }
  if (existingIndex >= 0) {
    thinkingState.toolCalls.splice(existingIndex, 1, {
      ...thinkingState.toolCalls[existingIndex],
      ...item,
      args: Object.keys(item.args || {}).length ? item.args : thinkingState.toolCalls[existingIndex].args,
      output: item.output ?? thinkingState.toolCalls[existingIndex].output
    })
  } else {
    thinkingState.toolCalls.push(item)
  }
}

// ═══ SSE 事件处理函数（新协议）═══
const handleSSEEvent = (eventType, data, context) => {
  const { ts, aiMsgIndex, streamingContent, threadId } = context
  
  switch (eventType) {
    case 'message_chunk':
      // 流式文本块
      if (data.content) {
        let idx = aiMsgIndex
        let content = streamingContent
        content += data.content
        if (idx < 0) {
          idx = ts.onGoingConv.messages.length
          ts.onGoingConv.messages.push({
            type: 'ai',
            content,
            id: Date.now(),
          })
        } else {
          ts.onGoingConv.messages[idx].content = content
        }
        context.aiMsgIndex = idx
        context.streamingContent = content
      }
      break
      
    case 'thinking':
      // 思考过程
      if (data.content) {
        addThinkingStep({
          type: 'thinking',
          content: data.content,
        })
      }
      break
      
    case 'plan':
    case 'plan_update':
      // 计划更新
      if (data.steps) {
        applyPlanSteps(data.steps)
      }
      break
      
    case 'step_start':
      // 步骤开始
      upsertToolCall({
        tool_call_id: data.step_id || `step_${Date.now()}`,
        function: data.step_name || 'unknown',
        name: data.step_name || 'unknown',
        status: 'running',
        args: data.context || {},
      })
      break
      
    case 'step_complete':
      // 步骤完成
      upsertToolCall({
        tool_call_id: data.step_id,
        function: data.step_name,
        name: data.step_name,
        status: 'completed',
        duration_ms: data.duration_ms,
      })
      break
      
    case 'tool_start':
      // 工具调用开始
      upsertToolCall({
        tool_call_id: data.tool_call_id || `tool_${Date.now()}`,
        function: data.tool_name,
        name: data.tool_name,
        status: 'calling',
        args: data.arguments || {},
        icon: data.meta?.icon,
        category: data.meta?.category,
      })
      break
      
    case 'tool_complete':
      // 工具调用完成（完整结果进 output，供展开态结构化展示）
      upsertToolCall({
        tool_call_id: data.tool_call_id,
        function: data.tool_name,
        name: data.tool_name,
        status: 'completed',
        duration_ms: data.duration_ms,
        result_preview: data.result_preview,
        output: data.result_content ?? data.output ?? data.result_preview,
      })
      
      // 检查是否是商品卡片工具，如果是则添加到消息中
      if (data.tool_name === 'render_product_card' && data.result_content) {
        try {
          const result = typeof data.result_content === 'string' 
            ? JSON.parse(data.result_content) 
            : data.result_content
          
          // 兼容两种格式：{type: "product_card", data: {...}} 或 {cards: [...]}
          let cards = []
          if (result.type === 'product_card' && result.data) {
            cards = [result.data]
          } else if (result.cards && result.cards.length > 0) {
            cards = result.cards
          }
          
          if (cards.length > 0) {
            // 关闭当前文本消息，让后续文本另起一条新消息
            // 这样卡片就能自然插入到前后文本之间
            context.aiMsgIndex = -1
            context.streamingContent = ''
            
            // 创建独立的卡片消息，与文本消息交错排列
            context.ts.onGoingConv.messages.push({
              type: 'ai',
              content: '',
              productCards: cards,
              id: Date.now(),
            })
          }
        } catch (e) {
          console.warn('Failed to parse product card data:', e)
        }
      }
      break
      
    case 'agent_state':
      // Agent 状态更新
      ts.agentState = data
      if (Array.isArray(data.todos)) {
        applyPlanSteps(data.todos)
      }
      break
      
    case 'title':
      // 自动标题更新（后端根据首条消息自动生成）
      if (data.thread_id && data.title) {
        const targetThread = threads.value.find((t) => t.id === data.thread_id)
        if (targetThread) {
          targetThread.title = data.title
        }
      }
      break
      
    case 'error':
      // 错误事件
      throw new Error(data.error || 'Unknown error')
      
    case 'done':
      // 完成事件（含统计信息）
      console.log('[SSE] Stream completed:', data.statistics)
      lastStatistics.value = data.statistics || null
      break
      
    default:
      // 兼容旧格式
      if (data.status === 'agent_state') {
        ts.agentState = data.agent_state
        if (Array.isArray(data.agent_state?.todos)) {
          applyPlanSteps(data.agent_state.todos)
        }
      } else if (data.thinking_step) {
        addThinkingStep(data.thinking_step)
      } else if (data.plan) {
        applyPlanSteps(data.plan.steps || [])
      } else if (data.tool_call) {
        upsertToolCall(data.tool_call)
      }
  }
}

const handleSendOrStop = async () => {
  if (isProcessing.value) {
    // 停止生成：真正中止底层 SSE 流
    const ts = currentThreadState.value
    if (ts) ts.isStreaming = false
    const st = chatState.threadStates[currentChatId.value]
    if (st?.abort) st.abort()
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

  // 支持"停止"时真正中断 fetch
  const ac = new AbortController()
  ts.abort = () => ac.abort()
  
  // 清空之前的思考步骤
  clearThinkingSteps()
  
  let streamingContent = ''
  let aiMsgIndex = -1  // 当前正在流式输出的 AI 消息在 messages 数组中的索引

  try {
    const response = await agentApi.sendAgentMessage(currentAgentId.value, {
      query,
      config: {
        thread_id: threadId,
      },
      meta: {}
    }, { signal: ac.signal })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let currentEvent = null  // 当前 SSE 事件类型
    let eventId = ''  // 当前事件 ID

    // 创建可变的 context 对象，用于在 handleSSEEvent 和外部之间共享状态
    const streamContext = {
      ts,
      aiMsgIndex: -1,
      streamingContent: '',
      threadId,
    }

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed) continue
        
        // ═══ 解析标准 SSE 格式 ═══
        if (trimmed.startsWith('event:')) {
          // 事件类型行
          currentEvent = trimmed.slice(6).trim()
        } else if (trimmed.startsWith('id:')) {
          // 事件 ID 行
          eventId = trimmed.slice(3).trim()
        } else if (trimmed.startsWith('data:')) {
          // 数据行
          try {
            const data = JSON.parse(trimmed.slice(5))
            
            // ═══ 处理新协议事件 ═══
            handleSSEEvent(currentEvent, data, streamContext)
            
            // 同步 context 中的状态到局部变量
            aiMsgIndex = streamContext.aiMsgIndex
            streamingContent = streamContext.streamingContent
            
          } catch (e) {
            console.warn('Failed to parse SSE data:', e)
          }
        }
      }
    }

    // 流式结束，保存最终消息到历史
    flushOngoingConv(threadId, ts, streamingContent)
  } catch (error) {
    // 用户主动停止：不当作错误——把已生成的部分标记为"被用户停止"
    if (error && error.name === 'AbortError') {
      const last = ts.onGoingConv.messages[ts.onGoingConv.messages.length - 1]
      if (last && last.type === 'ai') last.isStoppedByUser = true
      // 把已生成的部分落库（含"已停止"提示）
      flushOngoingConv(threadId, ts, streamingContent)
    } else {
      console.error('Stream error:', error)
      handleChatError(error, 'send')
      // 保存已累积的部分内容
      if (streamingContent) {
        threadMessages.value[threadId].push({
          type: 'ai',
          content: streamingContent,
          id: Date.now(),
        })
      }
      threadMessages.value[threadId].push({
        type: 'ai',
        content: '',
        error_type: 'unexpect',
        error_message: error.message,
        id: Date.now(),
      })
    }
  } finally {
    ts.isStreaming = false
    delete ts.abort
    // 保存当前线程的思考过程快照
    snapshotThinkingState(threadId)
    ts.onGoingConv = createOnGoingConvState()
  }
}

// ═══ 临时：注入演示轮次（验证过程组三态；后端接入后删除）═══
// （验证完成，已删除；如需要可回滚 git 查看）

// 把本轮流式产生的消息落回线程历史（正常结束 / 用户停止共用）
const flushOngoingConv = (threadId, ts, streamingContent) => {
  if (!threadMessages.value[threadId]) threadMessages.value[threadId] = []
  if (ts.onGoingConv.messages.length) {
    for (const msg of ts.onGoingConv.messages) {
      threadMessages.value[threadId].push({
        ...msg,
        id: Date.now() + Math.random(),
      })
    }
  } else if (streamingContent) {
    threadMessages.value[threadId].push({
      type: 'ai',
      content: streamingContent,
      id: Date.now(),
    })
  }
}

const handleExampleClick = (text) => {
  userInput.value = text
  handleSendOrStop()
}

// 外部入口（首页等）带来的需求：等智能体就绪且不忙时再自动发送
const route = useRoute()
const router = useRouter()
const pendingAsk = ref('')
const flushPendingAsk = () => {
  if (!pendingAsk.value || !currentAgent.value || isProcessing.value) return
  const text = pendingAsk.value
  pendingAsk.value = ''
  handleExampleClick(text)
}
watch([currentAgent, isProcessing], () => flushPendingAsk())

const ask = (text) => {
  if (!text) return
  pendingAsk.value = text
  flushPendingAsk()
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
  // 消费外带参数：?need=…（带去提问） 或 ?open_thread=…（打开指定记录对话）；用完清掉避免刷新重放
  const need = typeof route.query.need === 'string' ? route.query.need.trim() : ''
  const openThreadId = typeof route.query.open_thread === 'string' ? route.query.open_thread.trim() : ''
  let changed = false
  if (need) {
    ask(need)
    changed = true
  }
  if (openThreadId) {
    const target = (threads.value || []).find((t) => t.id === openThreadId)
    if (target) {
      await selectChat(target.id)
      changed = true
    }
  }
  if (changed) {
    router.replace({ query: {} })
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
  position: relative; // float 状态面板需以本容器定位
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
  &.active { 
    background-color: var(--main-50); 
    color: var(--main-color); 
    font-weight: 500;
  }

  .loading-icon { animation: rotate 1s linear infinite; }
}

.chat-content-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
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

.chat-bottom-spacer {
  height: 180px;
  flex-shrink: 0;
}

.conv-box {
  margin-bottom: 8px;
  display: flex;
  flex-direction: column;
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
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 16px 24px 24px;
  max-width: 800px;
  width: 100%;
  margin: 0 auto;
  background: linear-gradient(to top, var(--gray-0) 80%, transparent);
  pointer-events: none;

  .message-input-wrapper {
    pointer-events: auto;
  }
}

.message-input-wrapper {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.chat-examples-input {
  text-align: center;
  padding: 8px 0 12px;
  h1 { font-size: 1.5rem; font-weight: 600; color: var(--gray-900); margin: 0; }
  .chat-examples-sub {
    margin: 8px auto 0;
    max-width: 560px;
    font-size: 0.85rem;
    color: var(--gray-600);
    line-height: 1.6;
  }
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

/* 欢迎页品牌区域样式 */
.welcome-brand {
  position: absolute;
  top: 18%; /* 进一步向上移动 */
  left: 50%;
  /* 关键：以文字中心为轴对称点。通过 transform 将文字中心对准屏幕中线 */
  /* 假设 gap 为 20px, logo 宽度约为 110px, 则整体需要向左偏移 (logoWidth + gap) / 2 */
  transform: translate(calc(-50% - 65px), -50%);
  display: flex;
  align-items: center;
  gap: 20px;
  pointer-events: none;
  user-select: none;
}

.brand-logo {
  height: 110px; /* 等比例放大 */
  width: auto;
  object-fit: contain;
}

.brand-text {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.brand-name {
  margin: 0;
  font-size: 44px; /* 等比例放大 */
  font-weight: 800;
  color: var(--gray-900);
  line-height: 1.1;
  letter-spacing: -0.5px;
}

.brand-slogan {
  margin: 0;
  margin-top: 4px;
  font-size: 16px; /* 等比例放大 */
  color: var(--gray-500);
  font-weight: 500;
}

/* 固定云朵层 */
.fixed-clouds-layer {
  position: absolute;
  top: 32%; /* 相应向上移动，保持在 Logo 下方 */
  left: 50%;
  transform: translate(-50%, 0);
  width: 90%;
  max-width: 800px;
  display: flex;
  flex-direction: column; /* 上下分栏 */
  align-items: center;
  gap: 30px;
  pointer-events: none;
}

.text-clouds-wrapper {
  display: flex;
  justify-content: center;
  gap: 24px; /* 缩小左右两栏的间距 */
  width: 100%;
}

.text-clouds-column {
  display: flex;
  flex-direction: column;
  gap: 12px;
  pointer-events: auto;
}

.text-cloud {
  font-weight: 500;
  justify-content: space-between; /* 文字在左，动作指示在右 */
  min-width: 280px; /* 稍微缩短以适应两栏布局 */
  padding: 8px 16px;
  position: relative;
  overflow: hidden;
}

.text-content {
  flex: 1;
  text-align: left;
  transition: opacity 0.3s ease, transform 0.3s ease;
}

.text-content.fading {
  opacity: 0;
  transform: translateY(-5px);
}

.action-indicator {
  position: relative;
  width: 40px; /* 预留固定宽度，防止布局抖动 */
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-left: 8px;
}

.arrow-icon {
  color: var(--gray-400);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  position: absolute;
  opacity: 1;
  transform: scale(1);
}

.buy-text {
  font-size: 11px;
  font-weight: 600;
  color: var(--main-color);
  opacity: 0;
  transform: scale(0.8) translateX(-5px);
  transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
  position: absolute;
  white-space: nowrap;
  padding: 2px 8px;
  background: rgba(245, 245, 245, 0.9); /* 灰白色背景框 */
  border-radius: 12px; /* 参考智能体图标的圆角风格 */
  border: 1px solid rgba(220, 220, 220, 0.8);
}

.cloud-pill:hover .arrow-icon {
  opacity: 0;
  transform: scale(0.8) translateX(5px);
}

.cloud-pill:hover .buy-text {
  opacity: 1;
  transform: scale(1) translateX(0);
}

.icon-clouds-row {
  display: flex;
  flex-wrap: nowrap;
  justify-content: center;
  gap: 12px;
  width: 100%;
  max-width: 900px;
  pointer-events: auto;
}

.cloud-pill {
  padding: 8px 16px;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(255, 255, 255, 0.6);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  font-size: 13px;
  color: var(--gray-700);
  cursor: pointer;
  transition: all 0.3s ease;
  display: flex;
  align-items: center;
  gap: 6px;
}

.cloud-pill:hover {
  background: rgba(255, 255, 255, 1);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  color: var(--main-color);
}

.icon-cloud {
  flex-direction: column;
  align-items: center;
  padding: 10px 14px;
  min-width: 80px;
  text-align: center;
}

.icon-cloud .cloud-icon {
  color: var(--primary-color, #4f46e5);
  margin-bottom: 4px;
}

.icon-cloud .cloud-title {
  font-size: 12px;
  font-weight: 600;
  line-height: 1.2;
}

.icon-cloud .cloud-subtitle {
  font-size: 10px;
  color: var(--gray-500);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100px;
}

/* 状态卡片排：滚动队列（队尾滑入 / 队头淡出，保持一排） */
.status-row {
  position: relative;
}

.demo-note {
  margin: 6px 0 0;
  text-align: center;
  font-size: 11px;
  color: var(--text-faint);
}

.status-card {
  flex-direction: row;
  align-items: center;
  gap: 10px;
  flex: 1 1 0;
  min-width: 0;
  max-width: 220px;
  padding: 10px 14px;
  border-radius: 18px;
  text-align: left;
  cursor: default;
}

.status-ico {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 10px;
  flex-shrink: 0;
  background: color-mix(in srgb, var(--stc) 13%, transparent);
  color: var(--stc);
}

.status-body {
  flex: 1;
  min-width: 0;
}

.status-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

.status-type {
  font-size: 11px;
  font-weight: 600;
  color: var(--stc);
}

.status-time {
  font-size: 10px;
  color: var(--gray-500);
  white-space: nowrap;
}

.status-main {
  margin: 2px 0 1px;
  font-size: 12px;
  font-weight: 600;
  color: var(--gray-800);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.status-sub {
  margin: 0;
  font-size: 11px;
  color: var(--gray-500);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 队尾：新卡从右侧滑入 */
.status-enter-active {
  transition: opacity 0.35s ease, transform 0.35s ease;
}
.status-enter-from {
  opacity: 0;
  transform: translateX(28px);
}

/* 队头：旧卡绝对定位原地淡出（不挤压其他卡片宽度） */
.status-leave-active {
  position: absolute;
  top: 0;
  width: calc((100% - 36px) / 4);
  transition: opacity 0.3s ease, transform 0.3s ease;
}
.status-leave-to {
  opacity: 0;
  transform: translateX(-22px) scale(0.96);
}
.status-move {
  transition: transform 0.4s ease;
}


/* 文本云朵平滑过渡动画 (上下滑动 + 渐变) */
.text-slide-move {
  transition: transform 0.5s cubic-bezier(0.4, 0, 0.2, 1);
}

.text-slide-enter-active,
.text-slide-leave-active {
  transition: all 0.6s cubic-bezier(0.34, 1.56, 0.64, 1); /* 增加弹性效果 */
}

.text-slide-enter-from {
  opacity: 0;
  transform: translateY(20px) scale(0.95);
}

.text-slide-leave-to {
  opacity: 0;
  transform: translateY(-20px) scale(0.95);
}
</style>
