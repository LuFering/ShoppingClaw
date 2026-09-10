// 消息流分组：把一轮会话的消息数组 + （可选的）过程数据，合成消息流展示项。
// 展示项两类：
//   { type: 'message', message }        —— 普通消息（用户/AI/商品卡）
//   { type: 'process', steps, planSteps, toolCalls, live } —— 该轮"思考与工具"过程组
// 约定：后端 history 中 type==='thinking' 且带 thinkingProcess 的消息，就是那一轮过程组的载体。
//
// 顺序归一化：后端落库时先存 AI、后存 thinking，历史顺序常为 [human, ai, thinking]。
// 思考过程组应位于"用户提问"与"AI 回答"之间，故把每条 thinking 归位到其对应 AI 之前，
// 保证多轮 / 切换对话重新拉取历史后，思考模块始终在正文框上方。
function normalizeThinkingOrder(messages) {
  const out = []
  let lastAiIndex = -1
  for (const m of messages || []) {
    if (m && m.type === 'thinking' && m.thinkingProcess) {
      // 已在其 AI 之前（正确顺序）则原样保留；否则插入到最近一条 AI 之前
      if (lastAiIndex >= 0) {
        out.splice(lastAiIndex, 0, m)
        lastAiIndex += 1 // 保持指向该 AI，供后续 thinking 继续插到其前
      } else {
        out.push(m)
      }
      continue
    }
    if (m && m.type === 'ai') {
      out.push(m)
      lastAiIndex = out.length - 1
      continue
    }
    out.push(m)
  }
  return out
}

export function buildDisplayItems(messages, processAppend = null) {
  const items = []
  const msgs = normalizeThinkingOrder(messages || [])
  let lastHumanItem = -1

  for (const m of msgs) {
    if (m && m.type === 'thinking' && m.thinkingProcess) {
      const tp = m.thinkingProcess || {}
      items.push({
        type: 'process',
        steps: tp.steps || [],
        planSteps: tp.planSteps || [],
        toolCalls: tp.toolCalls || [],
        live: false
      })
      continue
    }
    if (m && m.type === 'human') lastHumanItem = items.length
    items.push({ type: 'message', message: m })
  }

  // 附加过程数据（进行中的 live 组 / 刚完成轮次的快照）：
  // 插到最后一条用户消息之后（过程发生在提问与回答之间）
  const hasProcess =
    processAppend &&
    ((processAppend.steps || []).length ||
      (processAppend.toolCalls || []).length ||
      (processAppend.planSteps || []).length)
  if (hasProcess) {
    const item = {
      type: 'process',
      steps: processAppend.steps || [],
      planSteps: processAppend.planSteps || [],
      toolCalls: processAppend.toolCalls || [],
      live: !!processAppend.live
    }
    if (lastHumanItem >= 0) items.splice(lastHumanItem + 1, 0, item)
    else items.unshift(item)
  }

  return items
}
