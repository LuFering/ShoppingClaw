/**
 * 代购送礼 · agent 流（mock）
 *
 * ⚠️ 这是**模拟**的流，不是真的 agent。后端 `proxy_agent` / `gift_ideator` 尚未实现
 * （`src/agents/subagents/subagents.yaml` 里目前只有 researcher / analyst / critic / memory_manager）。
 *
 * 但事件契约是按真实后端设计的，接的时候只需要换掉这个文件的产出源：
 *   后端已有 `server/routers/chat_rounter.py`（text/event-stream + last_event_id 可续传），
 *   把 `createGiftAgent()` 换成 `new EventSource('/api/chat/...')` 即可，界面层不用改。
 *
 * 设计上刻意做了两件与实际 agent 一致的事：
 *   1. **推理是长的**：分句流式输出，每句都有发言方（subagent 名），不做成一次性返回
 *   2. **增量产出**：方向、物件、理由、风险都是分事件逐个吐，界面因此能「看着它长出来」
 *
 * 阶段与真实 subagent 的对应：
 *   read      → memory_manager （懂你的人：偏好、置信度）
 *   draft     → gift_ideator   （缺，需新建：从情境联想出故事方向）
 *   compose   → researcher     （挑东西的）
 *   challenge → analyst + critic（说人话的 + 泼冷水的）
 *   settle    → master_agent   （整合）
 */

import { CONCEPTS, CONCEPT_ALTERNATES } from './giftDemo'

export const STAGES = [
  { key: 'read', label: '读情境', by: 'memory_manager' },
  { key: 'draft', label: '找方向', by: 'gift_ideator' },
  { key: 'compose', label: '配构成', by: 'researcher' },
  { key: 'challenge', label: '推敲', by: 'analyst + critic' },
  { key: 'settle', label: '成形', by: 'master_agent' }
]

/**
 * 每个方向的推演脚本。
 * `why` / `risk` 的键是 demo 数据里的元素 id；缺了就用元素自身的 note 兜底，
 * 所以新增方向不会因为漏写脚本而出现空白。
 */
const SCRIPTS = {
  'c-moon': {
    estTotal: 650,
    draftReason:
      '把「睡不好」和「喜欢木质香」并到一起，能想到三条互不重叠的路：往嗅觉走、往手的触感走、往共同经历走。三条总价拉得开，正好让她自己挑倾向。',
    composeReason:
      '按这条方向搜了三组关键词：木质香薰、无咖啡因安睡、手写卡。剔掉 4 件明显不搭的——其中两件是香薰机，和「不用点火也有味道」这条冲突。留三件。',
    whys: {
      'el-candle': {
        text: '档案里有「喜欢木质香调」。雪松佛手柑是木质里最不甜的一支，送长辈或同事都不会显得用力过猛。',
        scores: [['每天都在用', 9], ['不容易闲置', 8], ['预算占比合理', 7]]
      },
      'el-tea': {
        text: '无咖啡因是这条方向的硬条件——「睡前半小时」这个时间窗里，含咖啡因的饮品会把整条逻辑作废。',
        scores: [['每天在碰', 9], ['和蜡烛同一时间窗', 9], ['不挑口味', 7]]
      },
      'el-card': {
        text: '卡片本身不值钱，但它是这盒东西唯一的「解释」。没有它，三件东西只是三件东西。',
        scores: [['承载体贴', 9], ['不可替代', 10], ['成本极低', 10]]
      }
    },
    risks: [
      {
        elementId: 'el-candle',
        level: 'warn',
        text: '档案里有一条「香水过敏」。蜡烛不等于香水，但建议走低烟或无火路线——这条是警示不是红线，可由你拍板。'
      },
      {
        elementId: 'el-card',
        level: 'ok',
        text: '总价低于预算 ¥126，不会让她觉得「太重」。这个区间反而更适合日常礼物。'
      }
    ],
    settleReason:
      '把档案里的两条依据、analyst 的一致性判断、critic 的两处提醒一起收进来。寄语落在「睡得沉一点」这个具体承诺上，不写空话。'
  },

  'c-hand': {
    estTotal: 600,
    draftReason:
      '另一条路是「看得出是人挑的」。重点不在功能，在「被认真对待」——适合她什么都不缺、但会在意你有没有花心思的情况。',
    composeReason:
      '这条方向搜的是「有手工痕迹」而不是「手工」，差别在于前者能看出不完全一致。留了三件，都有纹理或痕迹。',
    whys: {
      'el-soap': {
        text: '冷制皂每块纹理都不同，正好对上「看得出是人挑的」这条。日常能用到，不会被她收进柜子。',
        scores: [['每天在碰', 8], ['有手工痕迹', 9], ['预算占比合理', 8]]
      },
      'el-felt': {
        text: '能挂在包上，等于把这份礼物带出门。这一条比「好看」更重要。',
        scores: [['会被带出门', 8], ['有手工痕迹', 9], ['不挑风格', 7]]
      },
      'el-card2': {
        text: '和干花放在一起，拆盒的时候有气味。这是整盒里唯一一个「打开瞬间」的设计。',
        scores: [['承载体贴', 9], ['不可替代', 10]]
      }
    },
    risks: [
      {
        elementId: 'el-soap',
        level: 'warn',
        text: '手工皂属于消耗品，用完了这盒就没了。如果你希望东西能留久一点，这里要换。'
      }
    ],
    settleReason: '这条方向的落点是「被认真对待」，所以寄语里没写功能，只写了挑这些东西时的动作。'
  },

  'c-exp': {
    estTotal: 760,
    draftReason:
      '第三条不给东西，给一次安排好的共同经历。适合她什么都不缺、但想要你花时间的情况——也是最容易被她记住的一条。',
    composeReason:
      '体验类的关键是「当天能完成、成品能带走」。按这两条筛，陶艺比料理更合适：料理的成果当天吃掉了。',
    whys: {
      'el-class': {
        text: '两小时、成品可带走，等于一次体验会变成一件实物留在她家里。这是选陶艺而不是看展的原因。',
        scores: [['会被记住', 9], ['有实体留存', 9], ['需要你到场', 10]]
      },
      'el-photo': {
        text: '当天拍完就能贴进相册，比手机照片更像礼物——因为它不可转发。',
        scores: [['当天可用', 8], ['不可替代', 8]]
      },
      'el-card3': {
        text: '先给卡再给体验，把「当天要做什么」写清楚。没有它，收到的人会不知道该怎么配合。',
        scores: [['承载体贴', 9], ['成本极低', 10]]
      }
    },
    risks: [
      {
        elementId: 'el-class',
        level: 'warn',
        text: '体验课通常要提前一周预约，且要她当天有空。这一条比预算更容易出问题，建议先确认时间。'
      }
    ],
    settleReason: '这条方向的落点是「你花的时间」，所以寄语的重点放在当天安排，不放在东西上。'
  },

  'c-scent': {
    estTotal: 620,
    draftReason: '往上一条思路的旁边走一格：用气味标记这段时间。适合你们有共同记忆、但说不出具体是什么的场景。',
    composeReason: '同一个气味的延续比三个不同气味更像一套，所以三件都围绕同一支香调选。',
    whys: {},
    risks: [
      { elementId: '', level: 'warn', text: '气味是主观的，且档案里有「香水过敏」这一条。这一方向的风险比前三个都高。' }
    ],
    settleReason: '这条方向的落点是「记住这段时间」，寄语里写的是时间，不是东西。'
  },

  'c-warm': {
    estTotal: 640,
    draftReason: '不提浪漫，只管她冷不冷。冬天送这个最实在，也最不容易出错。',
    composeReason: '保暖类看的是「她会不会真的戴出门」，所以剔掉了所有好看但不好配衣服的。',
    whys: {},
    risks: [
      { elementId: '', level: 'warn', text: '保暖三件容易读成「实用但不用心」。如果你们还在意仪式感，这条要慎选。' }
    ],
    settleReason: '这条方向的落点是「你注意她冷不冷」，寄语里写的是天气和具体的照顾。'
  },

  'c-desk': {
    estTotal: 600,
    draftReason: '让她在公司也有个自己的小角落。适合她最近工作压力大、又说不出口的情况。',
    composeReason: '按「不用天天管」筛的：需要一个不用照顾的绿植、一个能当小夜灯的加湿器、一个久坐真需要的靠垫。',
    whys: {},
    risks: [
      { elementId: '', level: 'warn', text: '工位类礼物是工作场合的，同事会看到。如果她不喜欢被同事注意到，这条要慎选。' }
    ],
    settleReason: '这条方向的落点是「你在意她上班那一整天」，寄语里写的是白天。'
  }
}

export const scriptOf = (id) => SCRIPTS[id] || {}

/**
 * 元素由**流**负责供应，而不是由界面传进来。
 *
 * 这条是流驱动改造的关键：界面侧的方向对象里只有标题/理由/色板这类元信息，
 * 元素（含 replaceOptions）必须从数据源按 id 现取。
 * 之前从传入对象上读 `direction.elements`，切到「还没配过构成」的方向时
 * 拿到的是空数组 —— 表现为状态条跑完了、物件一件都没出。
 */
const SOURCE = [...CONCEPTS, ...CONCEPT_ALTERNATES]
const sourceOf = (id) => SOURCE.find((c) => c.id === id)

/**
 * 造一个 agent。speed > 1 会整体加速（演示用），不影响事件顺序与内容。
 * 返回的 `start` / `compose` 都是 async generator。
 */
export function createGiftAgent({ speed = 1 } = {}) {
  const wait = (ms) => new Promise((r) => setTimeout(r, Math.round(ms / speed)))
  let sid = 0

  /** 一句推理拆成若干片段流式吐出；`more` 为 false 时是这一句的完整文本 */
  async function* say(by, text) {
    const id = `s${++sid}`
    const CH = 14
    for (let i = 0; i < text.length; i += CH) {
      yield { t: 'think', by, sid: id, text: text.slice(i, i + CH), more: true }
      await wait(52)
    }
    yield { t: 'think', by, sid: id, text, more: false }
    await wait(180)
  }

  /** 阶段 ①：读情境 —— memory_manager 从档案里取相关偏好 */
  async function* start({ brief, directions }) {
    yield { t: 'stage', stage: 'read' }
    yield* say(
      'memory_manager',
      `先看这次给谁：${brief.recipient || '她'}，${brief.occasion || '生日'}，预算 ¥${brief.budget || '—'}。档案里和这次真正相关的只有两条，其余全过滤掉。`
    )
    yield {
      t: 'evidence',
      forRef: 'brief',
      from: '档案',
      kind: '明确信号',
      text: `上次送的礼，回访标记为「常用」——她是真的会用东西的人`
    }
    await wait(120)
    yield {
      t: 'evidence',
      forRef: 'brief',
      from: '推断',
      kind: '推断信号',
      text: '她提过喜欢木质香调（置信度：中，不是明说）'
    }
    await wait(200)

    /* 阶段 ②：找方向 —— 逐个吐方向，每个都带一句为什么值得提 */
    yield { t: 'stage', stage: 'draft' }
    yield* say(
      'gift_ideator',
      '把「会真的用」和「木质香」并到一起，再乘上这个预算，能想到几条互不重叠的路。先把它们并排摆出来给你看，不急着替你选。'
    )

    for (const d of directions) {
      const s = scriptOf(d.id)
      yield {
        t: 'direction',
        id: d.id,
        title: d.title,
        thesis: d.thesis,
        palette: d.palette,
        moodLabel: d.moodLabel,
        budgetNote: d.budgetNote,
        slots: (d.elements || []).length,
        estTotal: s.estTotal || Math.round((d.elements || []).reduce((a, e) => a + e.price, 0) / 50) * 50
      }
      await wait(160)
      if (s.draftReason) yield* say('gift_ideator', `「${d.title}」——${s.draftReason}`)
      await wait(260)
    }

    /* 阶段 ③④⑤：先把推荐方向配完，另外两条等你点进去再现配 */
    yield* compose({ direction: directions[0] })
    yield { t: 'settle', directionId: directions[0].id }
    yield { t: 'done' }
  }

  /** 阶段 ③④：针对某一个方向配构成 + 推敲（换方向时按需调用） */
  async function* compose({ direction }) {
    const s = scriptOf(direction.id)
    const src = sourceOf(direction.id) || direction
    const els = (src.elements || []).map((e) => JSON.parse(JSON.stringify(e)))

    yield { t: 'stage', stage: 'compose' }
    yield* say(
      'researcher',
      s.composeReason || `按「${direction.title}」这条调性搜了两轮，剔掉明显不搭的，留下 ${els.length} 件。`
    )

    for (const el of els) {
      yield { t: 'element', directionId: direction.id, el }
      await wait(150)
    }

    yield { t: 'stage', stage: 'challenge' }

    for (const el of els) {
      const w = s.whys?.[el.id]
      yield {
        t: 'why',
        directionId: direction.id,
        elementId: el.id,
        text: w?.text || el.note,
        scores: w?.scores || []
      }
      await wait(110)
    }

    for (const r of s.risks || []) {
      await wait(140)
      yield { t: 'risk', directionId: direction.id, elementId: r.elementId || '', level: r.level, text: r.text }
    }

    if (s.settleReason) yield* say('master_agent', s.settleReason)
    await wait(160)
    yield { t: 'compose-done', directionId: direction.id }
  }

  return { start, compose, say }
}
