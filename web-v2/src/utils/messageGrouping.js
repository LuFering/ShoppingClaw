// 消息流展示项分组
//
// 展示项协议：
//   { type: 'message',     key, message, sourceIndex }
//   { type: 'tool-group',  key, toolCalls, entries, live? }   // live 为 SC 扩展：流式进行中
//   { type: 'process-group', key, items, messageCount, toolCallCount, durationMs }
//
// 本项目适配说明：
//   1. SC 的思考过程不是 ai 消息的 reasoning_content 字段，而是独立的
//      { type:'thinking', thinkingProcess:{ steps, toolCalls, planSteps } } 段，
//      这里统一转换成 tool-group。
//   2. SC 的工具对象字段为 { toolCallId, name, args, output, status, duration }，
//      经 toToolCallContract 转成渲染契约 { id, name, args, status, tool_call_result }。
import MessageProcessor from '@/utils/messageProcessor'
import { enrichTaskToolCalls } from '@/components/ToolCallingResult/toolRegistry'
import { collapseConversationProcess } from '@/utils/conversationProcessGrouping'

/**
 * 把工具异常转成用户能懂的短句。
 *
 * 为什么需要：后端在工具失败时会把异常串作为 output 下发，
 * 直接展示会暴露 Python 堆栈 / SQL 语句（实测界面上出现过
 * `TypeError: find_archive() missing 1 required positional argument`）。
 *
 * 技术细节不丢 —— 仍保留在 tool_call_result.content 里，
 * 展开工具详情可以看到完整信息；模型侧也是通过那条链路拿到细节。
 */
const friendlyError = (raw) => {
  const text = String(raw || '').trim()
  if (!text) return '执行失败'

  // 常见异常归类
  if (/missing \d+ required positional argument|unexpected keyword argument/i.test(text)) {
    return '工具参数不匹配，请稍后重试'
  }
  if (/operator does not exist|asyncpg|sqlalchemy/i.test(text)) {
    return '数据查询失败，请稍后重试'
  }
  if (/timeout|timed out|超时/i.test(text)) {
    return '执行超时，请稍后重试'
  }
  if (/connection|network|unreachable|refused/i.test(text)) {
    return '网络连接异常，请稍后重试'
  }
  if (/not found|不存在|未找到/i.test(text)) {
    return '未找到相关数据'
  }
  if (/permission|forbidden|权限/i.test(text)) {
    return '没有权限执行该操作'
  }

  // 无法归类：若像技术异常（含类名/括号/冒号堆栈特征）则给通用文案，
  // 避免把内部细节抖出来；否则原样返回（可能是业务层的友好提示）。
  const looksTechnical = /^[A-Z][A-Za-z]+Error|Traceback|File "|\bat \w+\./.test(text)
  if (looksTechnical) return '执行失败，请稍后重试'

  // 业务文案（如「查询失败: 未找到用户」）：截断过长内容即可
  return text.length > 60 ? text.slice(0, 60) + '…' : text
}

/** SC 流式工具对象 → 工具调用渲染契约。 */
export const toToolCallContract = (toolCall) => {
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
    // 失败时**不**透出原始 output（可能含 Python 堆栈），转成友好文案
    ...(status === 'error' && rawOutput ? { error_message: friendlyError(rawOutput) } : {}),
    // 后端 tool_error 事件携带的失败原因优先于上面的兜底（同样友好化）
    ...(toolCall.error_message ? { error_message: friendlyError(toolCall.error_message) } : {}),
    ...(toolCall.display_label ? { display_label: toolCall.display_label } : {}),
    // 子智能体执行轨迹（调用工具 / 检索 RAG / 使用 Skill）必须透传到消息级 tool_calls。
    // 左侧对话里的子智能体卡片由 TaskTool 渲染，读的是消息级 toolCall.subagent_run；
    // 这里若丢字段，TaskTool 的「执行详情」就会一直是空的。
    ...(toolCall.subagent_run ? { subagent_run: toolCall.subagent_run } : {}),
    // 主智能体编排轨迹：左侧 orchestrate 卡片读消息级 toolCall.orchestration
    ...(toolCall.orchestration ? { orchestration: toolCall.orchestration } : {}),
    // 下钻标志（expand / collapse）：左侧 TaskTool 卡片据此自动展开/收起
    ...(toolCall.drill ? { drill: toolCall.drill } : {})
  }
}

/** SC 过程段（thinking）→ tool-group。 */
const buildProcessToolGroup = (thinkingProcess, seed, live) => {
  const tp = thinkingProcess || {}
  const steps = tp.steps || []
  const toolCalls = (tp.toolCalls || []).map(toToolCallContract).filter(Boolean)

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
 *
 * AI 消息自带 tool_calls（后端按 message_id 归并下发），
 * 因此仅靠顺序遍历 + 「正文前 flush」即可得到交错结构，无需求助外部补丁。
 *
 * @param {Object} conv - { messages: Message[] }
 * @param {Object} options
 * @param {Function} options.enrichToolCalls - 工具富化（默认走 enrichTaskToolCalls）
 */
export const getConversationDisplayItems = (
  conv,
  {
    enrichToolCalls = defaultEnrichToolCalls,
    collapseIntermediate = false,
    runTiming = null
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
    // seed 决定「正文 / 工具组」的交替边界：
    // 后端把一条 message_id 的消息拆成若干条 {type:'ai'|'thinking'} 片段下发，
    // **同属一个 message_id 的片段必须归并成同一条展示项**，不同 message_id 才切开。
    // 因此 seed 用 message_id 优先；这样「一段前导文本 + 紧随其后的状态块」
    // 天然拼成 [AI(t1), 工具卡, AI(t2), 工具卡, …]，而不是把所有文本并成一大段。
    const seed = message.message_id || message.messageId || message.id || index

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

  return collapseConversationProcess(items, collapseIntermediate, runTiming)
}

/** 兼容旧调用名。 */
export const buildDisplayItems = (messages) => getConversationDisplayItems({ messages })
