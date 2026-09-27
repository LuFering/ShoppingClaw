/**
 * 三栏工作台的状态机：消费后端事件流，分别喂给左 / 中 / 右三栏。
 *
 * 三栏各自的数据源不共享 —— 这是刻意的：
 *   左栏只关心「走到哪一步、依据是什么」
 *   中栏只关心「此刻这个人被理解成什么样」
 *   右栏只关心「已经交付了什么、还差什么」
 * 所以同一个流事件不会同时改三栏，界面因此不会整体抖动。
 *
 * 2026-09-24 接真后端：原先事件来自 `data/giftWorkbenchStream.js` 的模拟流。
 * 事件类型与后端 `gift_service.emit()` 的 kind **一一对应**，所以
 * `apply()` 的分支完全没改 —— 只换了产出源。
 */
import { ref, computed, onBeforeUnmount } from 'vue'
import { giftApi } from '@/apis/gift_api'
import { demoStatus } from '@/apis/demoStatus'
import { PROFILE_GROUPS, ACTIONS, DELIVERABLES } from '@/data/giftProfile'

/** 三栏的骨架：后端只发「变化」，骨架在前端定，避免首屏空窗 */
const skeletonSteps = () =>
  ACTIONS.map((a) => ({ ...a, status: 'todo', live: '', why: '' }))

const skeletonProfile = () =>
  PROFILE_GROUPS.map((g) => ({ ...g, fresh: false }))

const skeletonDeliverables = () =>
  DELIVERABLES.map((d) => ({ ...d, state: 'todo', data: null }))

export function useGiftWorkbench({ runId } = {}) {
  const running = ref(false)
  const thinking = ref(false)
  const settled = ref(false)
  const loading = ref(true)
  const loadError = ref('')
  const stageKey = ref('')
  const freshKey = ref('')

  // 「起始陈述」与「推演所得」—— 中栏除人物档案之外的另两块内容。
  // 前者是开场那句「我还不了解 TA」（学 Letta 的 human 块写法），
  // 后者是随推演逐步长出来的真实所得（搜过的方向 / 已排除 / 搭配逻辑）。
  const opening = ref(null)
  const findings = ref([])

  const steps = ref(skeletonSteps())
  const excluded = ref([])
  const profile = ref(skeletonProfile())
  const understanding = ref({ text: '', from: '' })
  const deliverables = ref(skeletonDeliverables())
  const task = ref({ recipient: '', occasion: '', budget: 0 })
  const profileHead = ref(null)

  let abort = null
  let lastSeq = 0
  let retrying = false
  let freshTimer = 0

  const nowIndex = computed(() => {
    const i = steps.value.findIndex((s) => s.status === 'running' || s.status === 'todo')
    return i < 0 ? steps.value.length : i
  })
  const doneCount = computed(() => steps.value.filter((s) => s.status === 'done').length)
  /** 「待确认」也算已产出 —— 只是等你点头，不是没做出来 */
  const readyCount = computed(
    () => deliverables.value.filter((d) => d.state === 'ready' || d.state === 'needs').length
  )

  /**
   * 标记「这一条刚到」，触发一次脉冲动画。
   *
   * ⚠️ 不能 `forEach` 把别人的 fresh 清掉 —— 档案是**成批到达**的
   *（历史那批一次来 4 组）。每来一条就清一次的话，只有最后一条会闪光，
   * 前三条静悄悄地出现 —— 那正是「看不出在绘制」的原因之一。
   *
   * 现在改成**只点亮当前这条**、定时统一熄灭。一批 4 条各闪各的，
   * 视觉上就是「连着亮了几下」。
   */
  const markFresh = (key) => {
    freshKey.value = key
    const g = profile.value.find((x) => x.key === key)
    if (g) g.fresh = true
    clearTimeout(freshTimer)
    freshTimer = setTimeout(() => {
      profile.value.forEach((x) => { x.fresh = false })
      freshKey.value = ''
    }, 2400)
  }

  /**
   * 后端事件 → 三栏。分支名与后端 `gift_service.emit()` 的 kind 对齐。
   */
  const apply = (kind, p) => {
    switch (kind) {
      case 'stage':
        stageKey.value = p.key
        break

      case 'step': {
        const s = steps.value.find((x) => x.key === p.key)
        if (!s) break
        s.status = p.status
        if (p.evidence) s.evidence = p.evidence
        if (p.why) s.why = p.why
        // 实时元素：running 时记下开始时刻，供 ExploreStream 显示**实时**秒数；
        // done 时收下后端给的真实耗时（ms）。startedAt 只在进入 running 时设，
        // 避免重复的 running 事件把计时重置。
        if (p.status === 'running') {
          if (!s.startedAt) s.startedAt = Date.now()
          if (p.hint) s.hint = p.hint
          if (p.label) s.label = s.label || p.label
        } else if (p.status === 'done') {
          s.ms = p.ms ?? (s.startedAt ? Date.now() - s.startedAt : null)
          s.startedAt = null
        }
        break
      }

      case 'live': {
        const s = steps.value.find((x) => x.key === p.key)
        if (!s) break
        s.live = p.more ? s.live + (p.text || '') : (p.text || '')
        break
      }

      case 'excluded': {
        const e = excluded.value.find((x) => x.name === p.name) || { name: p.name, why: p.why }
        e.shown = true
        if (!excluded.value.includes(e)) excluded.value.push(e)
        break
      }

      case 'profile': {
        // ⚠️ 组是**逐步到达**的（后端按两次 RAG 往返分批推，见
        // gift_service._PROFILE_BATCH）。原先这里找不到就 `break` 丢弃 ——
        // 那是「骨架预置了全部五组、只等更新」的写法，现在骨架是空槽，
        // 组必须能被**新增**，否则中栏永远长不出来。
        let g = profile.value.find((x) => x.key === p.key)
        if (!g) {
          const base = PROFILE_GROUPS.find((x) => x.key === p.key) || { key: p.key }
          g = { ...base }
          profile.value.push(g)
        }
        g.state = p.state
        if (p.text) g.text = p.text
        if (p.note !== undefined && p.note !== null) g.note = p.note
        if (p.source) g.source = p.source
        // 到达时刻：卡片上标出「这一条是什么时候读到的」，
        // 让「刚长出来的」与「早就在的」可分辨（这是生长感的载体）
        g.arrivedAt = new Date()
        markFresh(p.key)
        break
      }

      case 'opening':
        // 开场陈述：建 run 时发一次，是「空白档案」的那个起点
        opening.value = { ...p }
        break

      case 'finding': {
        // 推演所得：随 search / verify / combine 逐步到达。
        // 同 key 更新（可能多轮），新 key 追加 —— 与 profile 同样的到达语义。
        const i = findings.value.findIndex((x) => x.key === p.key)
        const item = { ...p, arrivedAt: new Date() }
        if (i >= 0) findings.value[i] = { ...findings.value[i], ...item }
        else findings.value.push(item)
        break
      }

      case 'understanding':
        understanding.value = { text: p.text || '', from: p.from || '' }
        break

      case 'deliverable': {
        const d = deliverables.value.find((x) => x.key === p.key)
        if (!d) break
        d.state = p.state
        if (p.data) d.data = p.data
        break
      }

      case 'done':
        settled.value = true
        running.value = false
        break

      default:
        break
    }
  }

  /** 首屏：一次拿全（刷新即恢复，不重放事件） */
  const loadSnapshot = async () => {
    if (!runId?.value) {
      loading.value = false
      loadError.value = '缺少任务 ID —— 请从入口页开始一次送礼推演。'
      return
    }
    loading.value = true
    loadError.value = ''
    try {
      const run = await giftApi.getRun(runId.value)
      task.value = {
        recipient: run.recipient, occasion: run.occasion, budget: run.budget
      }
      if (run.profile?.length) {
        // 后端返回的是真实五组，直接铺到骨架上（保留前端图标等展示字段）
        profile.value = run.profile.map((g) => {
          const base = PROFILE_GROUPS.find((x) => x.key === g.key) || {}
          return { ...base, ...g, fresh: false }
        })
      }
      if (run.profileHead && Object.keys(run.profileHead).length) {
        profileHead.value = run.profileHead
      }
      if (run.understanding?.text) understanding.value = run.understanding
      settled.value = run.status === 'converged'
      subscribe()
      // 已收敛时把交付物拉全（快照里没有交付物内容，靠事件补）
      if (run.status === 'converged') await loadDeliverables()
    } catch (e) {
      loadError.value = e?.message || '任务加载失败'
      demoStatus.gift = true
    } finally {
      loading.value = false
    }
  }

  /** 收敛后逐个取交付物内容（事件里只有状态，内容在独立端点） */
  const loadDeliverables = async () => {
    for (const d of deliverables.value) {
      try {
        const res = await giftApi.getDeliverable(runId.value, d.key)
        if (res?.data) {
          d.data = res.data
          d.state = 'ready'
        }
      } catch { /* 单个失败不影响其它 */ }
    }
  }

  const subscribe = async () => {
    if (!runId?.value) return
    abort?.abort?.()
    abort = new AbortController()
    let closedByServer = false
    try {
      await giftApi.streamEvents(runId.value, {
        afterSeq: lastSeq,
        signal: abort.signal,
        onEvent: (kind, payload, seq) => {
          if (seq) lastSeq = Math.max(lastSeq, seq)
          apply(kind, payload)
          if (kind === 'done') closedByServer = true
        }
      })
    } catch (e) {
      if (abort?.signal?.aborted) return
      if (retrying) return
      retrying = true
      setTimeout(() => { retrying = false; subscribe() }, 2000)
      return
    }
    // 流自然结束（收敛/失败）：把交付物内容补齐
    if (closedByServer) await loadDeliverables()
  }

  const start = async () => {
    running.value = true
    settled.value = false
    // 重置三栏骨架（「重来」按钮会再走一次）
    steps.value = skeletonSteps()
    opening.value = null
    findings.value = []
    excluded.value = []
    profile.value = skeletonProfile()
    understanding.value = { text: '', from: '' }
    deliverables.value = skeletonDeliverables()
    lastSeq = 0
    await loadSnapshot()
  }

  const abortAll = () => {
    running.value = false
    thinking.value = false
    clearTimeout(freshTimer)
    try { abort?.abort?.() } catch { /* ignore */ }
  }

  onBeforeUnmount(abortAll)

  return {
    task,
    profileHead,
    steps,
    opening,
    findings,
    excluded,
    profile,
    understanding,
    deliverables,
    running,
    settled,
    thinking,
    loading,
    loadError,
    stageKey,
    freshKey,
    nowIndex,
    doneCount,
    readyCount,
    start,
    abort: abortAll,
    reload: loadSnapshot,
    revise: async (key) => {
      if (!runId?.value) return null
      try {
        const run = await giftApi.revise(runId.value, key)
        const g = profile.value.find((x) => x.key === key)
        if (g) g.state = 'pending'
        return run
      } catch { return null }
    }
  }
}
