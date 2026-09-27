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
import { ACTIONS, DELIVERABLES, railMeta, isDangerRail } from '@/data/giftProfile'

/** 三栏的骨架：后端只发「变化」，骨架在前端定，避免首屏空窗 */
const skeletonSteps = () =>
  ACTIONS.map((a) => ({ ...a, status: 'todo', live: '', why: '' }))

/**
 * 档案例子的骨架 = **空**。
 *
 * ⚠️ 旧实现是 PROFILE_GROUPS.map(…) —— 五个预置空槽，界面第一秒就有
 * 五个位置等着填。那既造成「一开始就有半张档案」的观感，也让「从 0 生长」
 * 无从谈起（0 不可能是 5 个空槽）。
 * 现在中栏从真正的 0 条开始，条目全部来自后端事件。
 */
const skeletonProfile = () => []

const skeletonDeliverables = () =>
  DELIVERABLES.map((d) => ({ ...d, state: 'todo', data: null }))

export function useGiftWorkbench({ runId } = {}) {
  const running = ref(false)
  const thinking = ref(false)   // 旧标志位（组件用它显示三点），保留不动
  const settled = ref(false)
  const loading = ref(true)
  const loadError = ref('')
  const stageKey = ref('')
  const freshKey = ref('')

  // 开场陈述 —— 学 Letta 的 `human` 块写法，起点不是空白而是
  // 一句诚实的「我还不了解 TA」。
  //
  // ⚠️ 「推演所得」这块**已并入档案**：搜过的方向 / 排除了什么 / 怎么搭的
  // 现在都由 agent 用 write_profile 写进对应栏（行情锚点 / 这盒的取舍 /
  // 这盒怎么搭），带 `because` 依据。旧的那份是**代码自动派生**的、
  // 没有依据 —— 曾被实测误把「我们搜的品类词」当成「她的喜好」。
  const opening = ref(null)

  /**
   * agent 停下来等拍板的问题 {text, options:[{key,label,primary}]}。
   *
   * ⚠️ 此前前端**完全没有这条链路** —— 后端能停（ask_user 写了 question
   * 就落 awaiting），但没人能答，run 永久卡住。实测撞到过：agent 问了
   * 一个很好的问题（「妈妈日常更贴近久坐型还是劳累型」），然后就死在那。
   */
  const question = ref(null)

  /**
   * 左栏的**事件行**。与采购 `PurchaseWorkbenchView.stream` 同构。
   *
   * ⚠️ 与 `steps`（骨架步骤）是两套东西，刻意分开：
   *   steps   = 「这次推演分几步」的结构，来自前端骨架
   *   stream  = 「模型实际做了什么」的流水，来自后端事件
   * 上一版只有 steps，于是 call/call_result/think_delta 三个事件
   * 到了前端无处可去，只能丢 —— 那正是左栏不像在跑的原因。
   */
  const stream = ref([])
  let streamSeq = 0
  const pushRow = (row) => {
    stream.value.push({ ...row, at: new Date().toISOString(), uid: `r${++streamSeq}` })
    if (stream.value.length > 400) stream.value.splice(0, stream.value.length - 400)
  }

  /** 模型此刻在想什么 —— 只留最新一段，供左栏那一行替换式显示 */
  const liveThought = ref('')
  /** 上一段推理的类型（reasoning / content）。换了类型要重开一段，见 think_delta */
  let thinkingKind = ''

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
    const g = profile.value.find((x) => x.id === key)
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
  const apply = (kind, payload) => {
    const p = payload
    switch (kind) {
      case 'stage':
        stageKey.value = p.key
        break

      // ── 模型决定调某个工具 ──
      // 与采购 `case 'call'` 同一套字段（title/detail/args/sample/
      // tool_call_id），这样两边可以喂给同一个组件。
      case 'call': {
        // 上一条还在流式的思考行收尾（与采购一致：换行了就去掉光标）
        const prev = stream.value[stream.value.length - 1]
        if (prev && prev.streaming) { prev.streaming = false; prev.state = 'done' }
        pushRow({
          kind: 'call',
          title: payload.title || '',
          detail: payload.detail || '',
          tool: payload.tool || '',
          args: payload.args || null,
          sample: payload.sample || null,
          // ⚠️ 配对键：模型会并行调多个同类工具（实测一次并行搜 3 个词），
          // 返回顺序不保证。不靠它配对就只能挂错行。
          toolCallId: payload.tool_call_id || '',
          state: 'done',
          time: nowClock()
        })
        break
      }

      // ── 工具返回：补到刚才那条 call 上，**不新起一行** ──
      case 'call_result': {
        const cid = payload.tool_call_id || ''
        let row = cid
          ? stream.value.find((x) => x.kind === 'call' && x.toolCallId === cid)
          : null
        if (!row) {
          // 没有 id 或找不到：退到「最后一条还没返回的」。
          // 单次调用时这是对的；并行时可能配错，但总比丢掉强。
          row = [...stream.value].reverse().find((x) => x.kind === 'call' && !x.result)
        }
        if (row) row.result = payload.text || ''
        else pushRow({ kind: 'call', title: '工具返回', detail: '',
                       result: payload.text || '', state: 'done', time: nowClock() })
        break
      }

      // ── 逐 token 的推理增量 ──
      // ⚠️ 只在 `liveThought` 里留**最新一段**，不往 stream 堆行：
      // 实测一次 run 114 段、5740 字符。全堆进 268px 的栏里就是流水账，
      // 前几版被否掉的原因正是这个。左栏要的是「它还在动」，不是逐字稿。
      case 'think_delta': {
        const t = String(payload.text || '')
        if (t) {
          // 连续同 kind 的增量拼接；换了 kind（reasoning → content）
          // 就重开一段 —— 否则「它在想」与「它的结论」会粘成一句。
          const k = payload.kind || 'content'
          liveThought.value = (thinkingKind === k ? liveThought.value : '') + t
          thinkingKind = k
        }
        break
      }

      case 'step': {
        // ── 同时落一条 `phase` 行喂给共享组件 ──
        // 采购的 `phase` 与送礼的 `step` 是同一件事的两种叫法（都是
        // 「一批同类调用」），差别只在字段名。在这里归一，共享组件就
        // 只需要认一套 —— 否则它会退化成 if/else 双分支，两套逻辑必然漂。
        const ph = stream.value.find((x) => x.kind === 'phase' && x.phase === payload.key)
        if (payload.status === 'done') {
          if (ph) {
            ph.state = 'done'
            // ⚠️ 同一阶段会被**反复进入**（实测「搜索」进 3 轮），
            // 耗时必须**累加**：只留最后一轮的话，三轮共 126s 的阶段
            // 会显示成 24.4s —— 而「哪一步最费时间」正是用户想知道的。
            if (typeof payload.ms === 'number') ph.msTotal = (ph.msTotal || 0) + payload.ms
            ph.passes = (ph.passes || 0) + 1
            ph.startedAt = null
          }
        } else if (ph) {
          ph.state = 'running'
          if (payload.hint) ph.detail = payload.hint
          if (!ph.startedAt) ph.startedAt = Date.now()
        } else {
          pushRow({
            kind: 'phase',
            phase: payload.key,
            title: payload.label || payload.key,
            detail: payload.hint || '',
            state: 'running',
            startedAt: Date.now(),
            time: nowClock()
          })
        }

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

      // ── 档案条目：增 / 改 / 删 ──
      // 后端推的是**差集**（见 gift_service._push_profile_delta）：
      //   add    新写的一条
      //   update 改写了某条（含状态变化）
      //   drop   删掉了某条 —— 这是本次重构才有的能力，
      //          旧的「固定五组」结构表达不了删除
      // 全部按 `id` 定位，不再按栏名/key。
      case 'profile': {
        const id = String(p.id || '')
        if (!id) break
        const i = profile.value.findIndex((x) => x.id === id)

        if (p.op === 'drop') {
          if (i >= 0) profile.value.splice(i, 1)
          break
        }

        const meta = railMeta(p.rail)
        const item = {
          id,
          rail: p.rail || '其他',
          railKey: meta.key,
          icon: meta.icon,
          danger: isDangerRail(p.rail),
          text: p.text || '',
          because: p.because || '',
          source: p.source || '',
          state: p.state || 'confirmed',
          // 到达时刻：卡片上标出「这一条是什么时候写进来的」，
          // 让「刚长出来的」与「早就在的」可分辨（这是生长感的载体）
          arrivedAt: new Date()
        }
        if (i >= 0) profile.value[i] = { ...profile.value[i], ...item }
        else profile.value.push(item)
        markFresh(id)
        break
      }

      case 'opening':
        // 开场陈述：建 run 时发一次，是「空白档案」的那个起点
        opening.value = { ...p }
        break

      // agent 停下来提问 → 右栏浮出「需要你拍板」
      case 'question':
        question.value = {
          text: payload.text || '',
          options: (payload.options || []).map((o) => ({ ...o }))
        }
        running.value = true          // 它没跑完，只是在等
        break

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
        // 跑完了就别再显示「正在想」—— 否则界面上永远挂着一句没说完的话
        liveThought.value = ''
        break

      default:
        break
    }
  }

  /** 事件到达的墙上时钟，供左栏显示「什么时候到的」 */
  const nowClock = () => new Date().toLocaleTimeString('zh-CN', { hour12: false })

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
        // 后端返回的是**真实条目列表**。补齐展示字段（图标 / 是否危险栏），
        // 这些由前端查表得到，不进库 —— 换图标不该动后端数据。
        profile.value = run.profile.map((g) => {
          const meta = railMeta(g.rail)
          return {
            ...g,
            railKey: meta.key,
            icon: meta.icon,
            danger: isDangerRail(g.rail),
            fresh: false
          }
        })
      }
      if (run.profileHead && Object.keys(run.profileHead).length) {
        profileHead.value = run.profileHead
      }
      if (run.understanding?.text) understanding.value = run.understanding
      // 刷新时恢复待确认问题（后端把它存在 run.question 里）
      if (run.question) question.value = run.question
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
    stream.value = []
    liveThought.value = ''
    thinkingKind = ''
    opening.value = null
    question.value = null
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
    stream,
    liveThought,
    opening,
    question,
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
    /** 回答 agent 的提问 → 后端清掉问题并续跑 */
    answer: async (key) => {
      if (!runId?.value) return null
      try {
        const run = await giftApi.answer(runId.value, key)
        question.value = null       // 问题已收掉，agent 接着跑
        running.value = true
        return run
      } catch { return null }
    },
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
