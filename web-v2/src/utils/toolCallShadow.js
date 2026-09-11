// 工具调用「影子事件」识别与合并（纯函数，便于单测）
//
// 背景：同一次工具调用会被两条通道各下发一遍事件——
//   ① chat_stream_service.emit_tool_call / emit_tool_result
//        · tool_call_id = LangChain 的 call id
//        · 带 message_id（前端靠它把工具挂到对应 AI 消息上）
//        · 带完整 result_content
//   ② runtime.py 的 LifecycleHandler（经 graph.py 的 _sse_sink 转发）
//        · tool_call_id = 现算的 call_<工具名>_<md5 前 12 位>
//        · **不带 message_id**，完成事件也不带结果
//        · 但带真实 args 与 duration_ms
//
// 两条通道 id 不同，若各自建行，界面上同一次调用就会出现两行——其中一行是空的
// （商品卡片场景下那行会渲染成「暂无商品数据」）。这里把 ② 识别为「影子事件」，
// 让它并入 ① 的权威记录，而不是另起一行。
//
// 合并窗口取得很短（影子事件通常在权威事件后几毫秒内到达），
// 避免把「同名工具的两次真实调用」误并成一次。

export const SHADOW_MERGE_WINDOW_MS = 8000

/** LifecycleHandler 现算的 id 形如 call_search_products_ab12cd34ef56。 */
export const isShadowToolCallId = (id) => /^call_.+_[0-9a-f]{12}$/.test(String(id || ''))

/**
 * 规划一次工具调用的写入：是并入已有记录，还是清掉影子行。
 *
 * @param {Object}   p
 * @param {Object}   p.incoming  即将写入的工具调用（已归一化，含 name/messageId/toolCallId）
 * @param {Array}    p.existing  现有的工具调用列表
 * @param {number}   [p.now]     当前时间戳
 * @param {number}   [p.windowMs] 合并窗口
 * @returns {{ mergeInto: Object|null, dropIds: string[] }}
 */
export function planShadowReconcile({
  incoming,
  existing,
  now = Date.now(),
  windowMs = SHADOW_MERGE_WINDOW_MS
} = {}) {
  const plan = { mergeInto: null, dropIds: [] }
  const name = incoming?.name
  if (!name || name === 'unknown' || !Array.isArray(existing)) return plan

  const isRecentSameName = (t) => t && t.name === name && now - (t.createdAt || 0) <= windowMs

  // ── 权威事件到达：清掉同名、近期产生的影子行 ──
  if (incoming.messageId) {
    for (const t of existing) {
      if (isRecentSameName(t) && !t.messageId && isShadowToolCallId(t.toolCallId)) {
        plan.dropIds.push(t.toolCallId)
      }
    }
    return plan
  }

  // ── 影子事件到达：并入同名、近期产生的权威记录 ──
  for (let i = existing.length - 1; i >= 0; i -= 1) {
    const t = existing[i]
    if (isRecentSameName(t) && t.messageId) {
      plan.mergeInto = t
      break
    }
  }
  return plan
}
