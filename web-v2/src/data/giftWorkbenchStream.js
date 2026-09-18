/**
 * 代购送礼 · v6 三栏工作台事件流（mock）
 *
 * ⚠️ 是模拟流，不是真 agent：后端 `proxy_agent` 尚未实现
 * （`src/agents/subagents/subagents.yaml` 目前只有 researcher / analyst / critic / memory_manager）。
 * 事件契约按真实后端设计，接入时只换产出源（现有 SSE：`server/routers/chat_rounter.py`，带 last_event_id 可续传）。
 *
 * 事件 → 三栏的落点：
 *   stage / step / live      → 左栏 礼物探索流
 *   profile / understanding  → 中栏 人物档案卡
 *   deliverable              → 右栏 交付区
 */
import { ACTIONS, EXCLUDED, PLAN, COMPARE, BUDGET_ROWS, MESSAGE, SUPPLY, ORDER } from './giftProfile'

const wait = (ms, speed) => new Promise((r) => setTimeout(r, Math.round(ms / speed)))

export function createWorkbenchAgent({ speed = 1 } = {}) {
  /** 把一段文本按片吐出来，用于左栏的实时行动描述 */
  async function* live(key, text) {
    const CH = 12
    for (let i = 0; i < text.length; i += CH) {
      yield { t: 'live', key, text: text.slice(i, i + CH), more: true }
      await wait(46, speed)
    }
    yield { t: 'live', key, text, more: false }
    await wait(150, speed)
  }

  /** 走一步：running → 实时描述 → done + 关键依据 */
  async function* step(key, opts = {}) {
    const def = ACTIONS.find((a) => a.key === key)
    yield { t: 'stage', key }
    yield { t: 'step', key, status: 'running' }

    for (const s of opts.side || []) yield s
    yield* live(key, def.detail)

    yield {
      t: 'step',
      key,
      status: opts.skip ? 'skipped' : 'done',
      evidence: def.evidence,
      why: opts.why || ''
    }
    await wait(opts.hold || 220, speed)
  }

  async function* run() {
    /* ① 理解关系 —— 中栏在这里被写活 */
    yield* step('understand', {
      side: [
        { t: 'profile', key: 'relation', state: 'confirmed' },
        { t: 'understanding', text: '先确认是给谁：妈妈，生日，预算 ¥800。', from: '来自左栏第 1 步「理解关系」' }
      ]
    })

    /* ② 提取需求 —— 推出硬指标，写下最终版「当前理解」 */
    yield* step('extract', {
      side: [
        { t: 'profile', key: 'life', state: 'inferred' },
        { t: 'profile', key: 'likes', state: 'confirmed' },
        { t: 'profile', key: 'taboo', state: 'confirmed' },
        {
          t: 'understanding',
          text: '她在意东西能不能真的用上，而不是贵不贵 —— 所以这一盒要落在「每天都会碰到」上。',
          from: '来自左栏第 2 步「提取需求」'
        }
      ]
    })

    /* ③ 检索商品 —— 右栏第一张卡开始生成 */
    yield* step('search', {
      side: [{ t: 'deliverable', key: 'compare', state: 'building' }]
    })

    /* ④ 比价验货 —— 候选对比出结果 */
    yield* step('verify', {
      side: [
        { t: 'deliverable', key: 'compare', state: 'ready', data: COMPARE },
        { t: 'profile', key: 'giftpref', state: 'pending' }
      ]
    })

    /* ⑤ 排除候选 —— 被排除的保留理由，不删除 */
    yield { t: 'stage', key: 'exclude' }
    yield { t: 'step', key: 'exclude', status: 'running' }
    for (const e of EXCLUDED) {
      yield { t: 'excluded', name: e.name, why: e.why }
      await wait(220, speed)
    }
    yield* live('exclude', ACTIONS.find((a) => a.key === 'exclude').detail)
    yield { t: 'step', key: 'exclude', status: 'done', evidence: ACTIONS.find((a) => a.key === 'exclude').evidence }
    await wait(200, speed)

    /* ⑥ 组合礼盒 —— 方案 + 预算分配 */
    yield* step('combine', {
      side: [
        { t: 'deliverable', key: 'plan', state: 'building' },
        { t: 'deliverable', key: 'plan', state: 'ready', data: PLAN },
        { t: 'deliverable', key: 'budget', state: 'ready', data: BUDGET_ROWS }
      ]
    })

    /* ⑦ 生成寄语 —— 文案 + 货源 + 订单 */
    yield* step('message', {
      side: [
        { t: 'deliverable', key: 'message', state: 'building' },
        { t: 'deliverable', key: 'message', state: 'ready', data: MESSAGE },
        { t: 'deliverable', key: 'supply', state: 'ready', data: SUPPLY },
        { t: 'deliverable', key: 'order', state: 'needs', data: ORDER }
      ]
    })

    yield { t: 'done' }
  }

  return { run }
}
