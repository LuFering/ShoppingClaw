// 消息流展示项分组（对标 Yuxi utils/messageGrouping.js）
//
// 展示项协议：
//   { type: 'message',     key, message, sourceIndex }
//   { type: 'tool-group',  key, toolCalls, entries, live? }   // live 为 SC 扩展：流式进行中
//   { type: 'process-group', key, items, messageCount, toolCallCount, durationMs }
//
// 与 Yuxi 的差异（SC 适配）：
//   1. SC 的思考过程不是 ai 消息的 reasoning_content 字段，而是独立的
//      { type:'thinking', thinkingProcess:{ steps, toolCalls, planSteps } } 段，
//      这里统一转换成 Yuxi 的 tool-group。
//   2. SC 的工具对象字段为 { toolCallId, name, args, output, status, duration }，
//      经 toYuxiToolCall 转成 Yuxi 契约 { id, name, args, status, tool_call_result }。
import MessageProcessor from '@/utils/messageProcessor'
import { enrichTaskToolCalls } from '@/components/ToolCallingResult/toolRegistry'
import { collapseConversationProcess } from '@/utils/conversationProcessGrouping'

/** SC 流式工具对象 → Yuxi 工具调用契约。 */
export const toYuxiToolCall = (toolCall) => {
  if (!toolCall) return null
  const status = toolCall.status === 'failed' ? 'error' : toolCall.status || 'running'
  const rawOutput = toolCall.output ?? toolCall.result
  const hasOutput = rawOutput != null && rawOutput !== ''
  return {
    id: toolCall.toolCallId || toolCall.id || toolCall.name,
    name: toolCall.name || toolCall.function || 'unknown',
    args: toolCall.args || {},
    status,
    duration_ms: toolCall.duration ?? toolCall.duration_ms ?? null,
    ...(hasOutput
      ? {
          tool_call_result: {
            content: typeof rawOutput === 'string' ? rawOutput : JSON.stringify(rawOutput)
          }
        }
      : {}),
    ...(status === 'error' && rawOutput ? { error_message: String(rawOutput) } : {}),
    ...(toolCall.display_label ? { display_label: toolCall.display_label } : {})
  }
}

/** SC 过程段（thinking）→ Yuxi tool-group。 */
const buildProcessToolGroup = (thinkingProcess, seed, live) => {
  const tp = thinkingProcess || {}
  const steps = tp.steps || []
  const toolCalls = (tp.toolCalls || []).map(toYuxiToolCall).filter(Boolean)

  const entries = []
  // 推理文本：合并连续的 thinking 步骤，避免逐条刷屏
  const reasoningText = steps
    .filter((s) => s && s.type === 'thinking' && s.content)
    .map((s) => String(s.content).trim())
    .filter(Boolean)
    .join('\n')
  if (reasoningText) {
    entries.push({ type: 'reasoning', key: `reasoning-${seed}`, content: reasoningText })
  }
  toolCalls.forEach((toolCall, index) => {
    entries.push({ type: 'tool', key: `tool-${seed}-${toolCall.id || index}`, toolCall })
  })

  if (!entries.length) return null
  return {
    type: 'tool-group',
    key: `tool-group-${seed}`,
    toolCalls,
    entries,
    live
  }
}

const defaultEnrichToolCalls = (message) => enrichTaskToolCalls(message?.tool_calls)

const hasVisibleAssistantBody = (message, content) =>
  Boolean(
    content ||
      message.error_type ||
      message.extra_metadata?.error_type ||
      message.isStoppedByUser ||
      message.productCards?.length
  )

/**
 * 将一轮会话切成「正文 / 工具组 / 正文 …」交替的展示序列。
 * @param {Object} conv - { messages: Message[] }
 * @param {Object} options
 * @param {Function} options.enrichToolCalls - 工具富化（默认走 Yuxi 的 enrichTaskToolCalls）
 * @param {Object}  options.processAppend - SC 流式中尚未分段的全局过程池 { steps, toolCalls, planSteps, live }
 */
export const getConversationDisplayItems = (
  conv,
  {
    enrichToolCalls = defaultEnrichToolCalls,
    collapseIntermediate = false,
    runTiming = null,
    processAppend = null
  } = {}
) => {
  if (!Array.isArray(conv?.messages) || conv.messages.length === 0) return []

  const items = []
  let pendingToolGroup = null

  const flushToolGroup = () => {
    if (pendingToolGroup && pendingToolGroup.entries.length > 0) {
      items.push(pendingToolGroup)
    }
    pendingToolGroup = null
  }

  conv.messages.forEach((message, index) => {
    const seed = message.id || index

    // ── SC 过程段：思考 + 工具调用 ──
    if (message.type === 'thinking') {
      flushToolGroup()
      const group = buildProcessToolGroup(message.thinkingProcess, seed, !!message.thinkingProcess?.live)
      if (group) items.push(group)
      return
    }

    // ── 非 AI 消息（用户 / 系统）──
    if (message.type !== 'ai') {
      flushToolGroup()
      items.push({
        type: 'message',
        key: `message-${seed}`,
        message,
        sourceIndex: index
      })
      return
    }

    // ── AI 消息 ──
    const { content, reasoningContent } = MessageProcessor.parseAssistantMessageBody(message)
    const toolCalls = enrichToolCalls(message) || []

    const ensureToolGroup = (segment) => {
      if (!pendingToolGroup) {
        pendingToolGroup = {
          type: 'tool-group',
          key: `tool-group-${seed}-${segment}`,
          toolCalls: [],
          entries: []
        }
      }
      return pendingToolGroup
    }

    if (reasoningContent) {
      ensureToolGroup('reasoning').entries.push({
        type: 'reasoning',
        key: `reasoning-${seed}`,
        content: reasoningContent
      })
    }

    // 正文：先收起进行中的工具组，保证「工具 → 正文」顺序与真实发生次序一致
    if (hasVisibleAssistantBody(message, content)) {
      flushToolGroup()
      items.push({
        type: 'message',
        key: `message-${seed}`,
        message: reasoningContent ? { ...message, reasoning_content: '' } : message,
        sourceIndex: index
      })
    }

    if (toolCalls.length > 0) {
      const group = ensureToolGroup('tools')
      group.toolCalls.push(...toolCalls)
      group.entries.push(
        ...toolCalls.map((toolCall, toolIndex) => ({
          type: 'tool',
          key: `tool-${seed}-${toolCall.id || toolIndex}`,
          toolCall
        }))
      )
    }
  })

  flushToolGroup()

  // ── SC 兼容：尚未分段的流式过程池，作为末尾 live 工具组 ──
  if (processAppend?.live) {
    const group = buildProcessToolGroup(processAppend, `append-${items.length}`, true)
    if (group) items.push(group)
  }

  return collapseConversationProcess(items, collapseIntermediate, runTiming)
}

/** 兼容旧调用名。 */
export const buildDisplayItems = (messages, processAppend = null) =>
  getConversationDisplayItems(
    { messages },
    { processAppend: processAppend || undefined }
  )
