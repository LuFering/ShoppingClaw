/**
 * 三栏工作台的状态机：消费 agent 流，分别喂给左 / 中 / 右三栏。
 *
 * 三栏各自的数据源不共享 —— 这是刻意的：
 *   左栏只关心"走到哪一步、依据是什么"
 *   中栏只关心"此刻这个人被理解成什么样"
 *   右栏只关心"已经交付了什么、还差什么"
 * 所以同一个流事件不会同时改三栏，界面因此不会整体抖动。
 */
import { ref, computed, onBeforeUnmount } from 'vue'
import { ACTIONS, PROFILE_GROUPS, DELIVERABLES, TASK, EXCLUDED } from '@/data/giftProfile'
import { createWorkbenchAgent } from '@/data/giftWorkbenchStream'

export function useGiftWorkbench({ speed = 1 } = {}) {
  const running = ref(false)
  const thinking = ref(false)
  const settled = ref(false)
  const stageKey = ref('')
  /** 中栏：刚被更新的组，用于「刚更新」脉冲 */
  const freshKey = ref('')

  const steps = ref(
    ACTIONS.map((a) => ({ ...a, status: 'todo', live: '', why: '' }))
  )
  const excluded = ref(EXCLUDED.map((e) => ({ ...e, shown: false })))
  const profile = ref(PROFILE_GROUPS.map((g) => ({ ...g, fresh: false })))
  const understanding = ref({ text: '', from: '' })
  const deliverables = ref(
    DELIVERABLES.map((d) => ({ ...d, state: 'todo', data: null }))
  )

  const agent = createWorkbenchAgent({ speed })
  let token = 0
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

  const markFresh = (key) => {
    freshKey.value = key
    profile.value.forEach((g) => { g.fresh = g.key === key })
    clearTimeout(freshTimer)
    freshTimer = setTimeout(() => {
      profile.value.forEach((g) => { g.fresh = false })
      freshKey.value = ''
    }, 2400)
  }

  const apply = (ev) => {
    switch (ev.t) {
      case 'stage':
        stageKey.value = ev.key
        break

      case 'step': {
        const s = steps.value.find((x) => x.key === ev.key)
        if (!s) break
        s.status = ev.status
        if (ev.evidence) s.evidence = ev.evidence
        if (ev.why) s.why = ev.why
        break
      }

      case 'live': {
        const s = steps.value.find((x) => x.key === ev.key)
        if (!s) break
        s.live = ev.more ? s.live + ev.text : ev.text
        break
      }

      case 'excluded': {
        const e = excluded.value.find((x) => x.name === ev.name) || { name: ev.name, why: ev.why }
        e.shown = true
        if (!excluded.value.includes(e)) excluded.value.push(e)
        break
      }

      case 'profile': {
        const g = profile.value.find((x) => x.key === ev.key)
        if (!g) break
        g.state = ev.state
        if (ev.text) g.text = ev.text
        if (ev.note !== undefined) g.note = ev.note
        markFresh(ev.key)
        break
      }

      case 'understanding':
        understanding.value = { text: ev.text, from: ev.from }
        break

      case 'deliverable': {
        const d = deliverables.value.find((x) => x.key === ev.key)
        if (!d) break
        d.state = ev.state
        if (ev.data) d.data = ev.data
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

  const start = async () => {
    token += 1
    const my = token
    running.value = true
    settled.value = false
    thinking.value = true
    stageKey.value = ''
    steps.value = ACTIONS.map((a) => ({ ...a, status: 'todo', live: '', why: '' }))
    excluded.value = EXCLUDED.map((e) => ({ ...e, shown: false }))
    profile.value = PROFILE_GROUPS.map((g) => ({ ...g, fresh: false }))
    understanding.value = { text: '', from: '' }
    deliverables.value = DELIVERABLES.map((d) => ({ ...d, state: 'todo', data: null }))

    for await (const ev of agent.run()) {
      if (my !== token) return
      apply(ev)
    }
    running.value = false
  }

  const abort = () => {
    token += 1
    running.value = false
    thinking.value = false
    clearTimeout(freshTimer)
  }

  onBeforeUnmount(abort)

  return {
    task: TASK,
    steps,
    excluded,
    profile,
    understanding,
    deliverables,
    running,
    settled,
    thinking,
    stageKey,
    freshKey,
    nowIndex,
    doneCount,
    readyCount,
    start,
    abort
  }
}
