// 消息流分组：把一轮会话的消息数组 + （可选的）过程数据，合成消息流展示项。
// 展示项两类：
//   { type: 'message', message }        —— 普通消息（用户/AI/商品卡）
//   { type: 'process', steps, planSteps, toolCalls, live } —— 该轮"思考与工具"过程组
// 约定：后端 history 中 type==='thinking' 且带 thinkingProcess 的消息，就是那一轮过程组的载体。

export function buildDisplayItems(messages, processAppend = null) {
  const items = []
  const msgs = messages || []
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
    else items.push(item)
  }

  return items
}
