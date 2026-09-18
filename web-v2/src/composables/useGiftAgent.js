/**
 * 消费 agent 流，把它变成界面状态。
 *
 * 关键点：界面**不再持有硬编码的方案数据** —— 方向、物件、理由、风险
 * 全部来自事件。所以接真后端时，这个文件不用改，只换 `giftAgentStream.js` 的产出源。
 *
 * 长推理的处理方式见设计方案 §10：
 *   · 状态条只显示「当前这一句」——上一句退到旁边变淡，不累积
 *   · 完整原文按阶段收进 timeline，供覆盖层回看
 *   · 增量产出：方向 / 物件 / 理由 / 风险都是分事件到达，界面因此能看着它长出来
 */
import { ref, computed, onBeforeUnmount } from 'vue'
import { STAGES, createGiftAgent } from '@/data/giftAgentStream'

export function useGiftAgent({ speed = 1 } = {}) {
  const stageKey = ref('')
  const liveBy = ref('')
  const liveText = ref('')
  const livePrev = ref('')
  const running = ref(false)
  const settled = ref(false)
  const composingId = ref('')

  const directions = ref([])
  const evidence = ref([])
  const timeline = ref([])

  let token = 0
  let curSid = ''
  let busy = false
  const pending = ref('')
  const agent = createGiftAgent({ speed })

  const stageState = computed(() => {
    const i = STAGES.findIndex((s) => s.key === stageKey.value)
    return STAGES.map((s, k) => ({
      key: s.key,
      label: s.label,
      by: s.by,
      state: settled.value || (i >= 0 && k < i) ? 'done' : k === i ? 'now' : 'todo'
    }))
  })

  const thinkCount = computed(() => timeline.value.filter((e) => e.kind === 'think').length)
  const doneDirections = computed(() => directions.value.filter((d) => d.composed).length)

  const push = (entry) => timeline.value.push({ stage: stageKey.value, ...entry })

  const apply = (ev) => {
    switch (ev.t) {
      case 'stage':
        stageKey.value = ev.stage
        break

      case 'think': {
        liveBy.value = ev.by
        if (ev.sid !== curSid) {
          curSid = ev.sid
          livePrev.value = liveText.value
          liveText.value = ''
        }
        liveText.value = ev.more ? liveText.value + ev.text : ev.text
        // 只把每一句的完整文本收进时间线，片段丢掉 —— 否则时间线会被碎片灌满
        if (!ev.more) push({ kind: 'think', by: ev.by, text: ev.text })
        break
      }

      case 'evidence':
        evidence.value.push(ev)
        push({ kind: 'evidence', from: ev.from, label: ev.kind, text: ev.text })
        break

      case 'direction': {
        const d = directions.value.find((x) => x.id === ev.id)
        if (d) break
        directions.value.push({
          id: ev.id,
          title: ev.title,
          thesis: ev.thesis,
          palette: ev.palette,
          moodLabel: ev.moodLabel,
          budgetNote: ev.budgetNote,
          slots: ev.slots || 0,
          estTotal: ev.estTotal || 0,
          elements: [],
          why: {},
          risks: [],
          revisions: [],
          /** 推敲阶段跑完（含 why / risk）才算 composed；ensureComposed 用它判断要不要补跑 */
          composed: false,
          /** 构成齐了就为 true —— 标签上的价格从「约¥」换成实价，用的正是这个 */
          priced: false
        })
        push({ kind: 'direction', title: ev.title, text: ev.thesis })
        break
      }

      case 'element': {
        const d = directions.value.find((x) => x.id === ev.directionId)
        if (!d) break
        d.elements.push({ ...ev.el, status: ev.el.status || 'original' })
        if (d.slots && d.elements.length >= d.slots) {
          // 价格此刻就确定了，不必等推敲跑完 —— 否则会出现
          // 「标签还写着约¥650、底栏已经合计 ¥674」这种自相矛盾的画面
          d.priced = true
          push({ kind: 'elements', text: `留下 ${d.elements.length} 件：${d.elements.map((e) => e.role).join('、')}` })
        }
        break
      }

      case 'why': {
        const d = directions.value.find((x) => x.id === ev.directionId)
        if (!d) break
        d.why[ev.elementId] = { text: ev.text, scores: ev.scores || [] }
        push({ kind: 'why', text: ev.text })
        break
      }

      case 'risk': {
        const d = directions.value.find((x) => x.id === ev.directionId)
        if (!d) break
        d.risks.push({ elementId: ev.elementId, level: ev.level, text: ev.text })
        push({ kind: 'risk', level: ev.level, text: ev.text })
        break
      }

      case 'settle':
        settled.value = true
        push({ kind: 'settle', text: '三件都定了。剩下的包装和寄语交给手作台。' })
        break

      case 'compose-done': {
        const d = directions.value.find((x) => x.id === ev.directionId)
        if (d) d.composed = true
        composingId.value = ''
        break
      }

      default:
        break
    }
  }

  const consume = async (gen, my) => {
    for await (const ev of gen) {
      if (my !== token) return
      apply(ev)
    }
  }

  /** 串行泵：保证同一时刻只有一条流在写状态，切方向不会并发 */
  const pump = async () => {
    if (busy) return
    while (pending.value) {
      const id = pending.value
      pending.value = ''
      const d = directions.value.find((x) => x.id === id)
      if (!d || d.composed) continue
      const my = token
      busy = true
      running.value = true
      composingId.value = id
      await consume(agent.compose({ direction: d }), my)
      busy = false
      running.value = false
      composingId.value = ''
    }
  }

  /** 开始一次新推演；list 是要摆出来的方向（换一批时传备选池） */
  const start = async (brief, list) => {
    token += 1
    const my = token
    directions.value = []
    evidence.value = []
    timeline.value = []
    stageKey.value = ''
    liveBy.value = ''
    liveText.value = ''
    livePrev.value = ''
    settled.value = false
    curSid = ''
    pending.value = ''

    busy = true
    running.value = true
    await consume(agent.start({ brief, directions: list }), my)
    busy = false
    running.value = false
    pump()
  }

  /** 切换到一个还没配过构成的方向 → 现场再跑一段（不是预先全算好） */
  const ensureComposed = (id) => {
    const d = directions.value.find((x) => x.id === id)
    if (!d || d.composed) return
    pending.value = id
    pump()
  }

  const abort = () => {
    token += 1
    busy = false
    running.value = false
    composingId.value = ''
    pending.value = ''
  }

  onBeforeUnmount(abort)

  return {
    stageState,
    stageKey,
    liveBy,
    liveText,
    livePrev,
    running,
    settled,
    composingId,
    directions,
    evidence,
    timeline,
    thinkCount,
    doneDirections,
    start,
    ensureComposed,
    abort
  }
}
