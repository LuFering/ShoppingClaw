<template>
  <div class="gb">
    <!-- 第 0 层：情境开场（不占步骤，进入礼盒前的一次轻决定） -->
    <div v-if="stage === 'brief'" class="gb__brief">
      <div class="gb__briefin">
        <BriefBlock @submit="onBrief" />
      </div>
    </div>

    <template v-else>
      <!-- 顶栏：方向标签由流逐个吐出来，没配构成前显示的是估计价 -->
      <header class="gb__top">
        <div class="gb__dirs">
          <span v-if="!directions.length" class="dir dir--ghost">正在想方向…</span>

          <button
            v-for="d in directions"
            :key="d.id"
            class="dir"
            :class="{ on: active && d.id === active.id }"
            type="button"
            :aria-pressed="active && d.id === active.id"
            @click="pickDirection(d)"
          >
            <span class="dir__t">{{ d.title }}</span>
            <span class="dir__p mono">{{ d.priced ? '¥' + totalOf(d) : '约¥' + d.estTotal }}</span>
          </button>

          <button v-if="directions.length" class="dir dir--more" type="button" @click="refreshDirections">
            换一批
          </button>
        </div>

        <p class="gb__ctx">{{ brief.recipient }} · {{ brief.occasion }} · 预算 ¥{{ brief.budget }}</p>
        <button class="gb__again" type="button" @click="restart">重来</button>
      </header>

      <!-- 层 1：agent 状态条（常驻一行，永不增长） -->
      <AgentStageBar
        :stages="stageState"
        :by="liveBy"
        :text="liveText"
        :running="running"
        :settled="settled"
        :count="thinkCount"
        @expand="openThink"
      />

      <div class="gb__mid">
        <div class="gb__stage">
          <GiftBox
            class="gb__box"
            :palette="boxPalette"
            :wrap="pickedWrap"
            :ribbon="pickedRibbon"
            :label="boxLabel"
          />

          <p class="gb__caption">
            <span class="gb__capt">{{ active ? active.title : '正在成形' }}</span>
            <span v-if="active" class="gb__capn mono">{{ elements.length }}/{{ active.slots }} 件</span>
          </p>

          <ul class="items">
            <li
              v-for="(el, i) in elements"
              :key="el.id"
              class="it"
              :class="{ 'it--focus': focusId === el.id, 'it--done': el.status === 'replaced' }"
            >
              <button
                class="it__btn"
                type="button"
                :aria-pressed="bubbleId === el.id"
                @click="onItemClick(el)"
              >
                <span class="it__glyph">
                  <ItemGlyph :role="el.role" :label="`${el.name} 的示意`" />
                </span>
                <span class="it__tx">
                  <span class="it__name">{{ el.name }}</span>
                  <span class="it__sub">
                    <span class="mono">{{ el.price ? '¥' + el.price : '含' }}</span> · {{ el.role }}
                  </span>
                </span>
                <span v-if="el.status === 'replaced'" class="it__chip">已替换</span>
                <span
                  v-if="riskOf(el)"
                  class="it__risk"
                  :class="{ 'is-ok': riskOf(el).level === 'ok' }"
                  :title="riskOf(el).text"
                />
              </button>

              <!-- 就近挂载（对象级）：这一件的依据，点开就在它自己身上 -->
              <button
                v-if="whyOf(el)"
                class="it__why"
                type="button"
                @click="onWhyClick(el)"
              >
                <i class="it__whydot" />{{ whyId === el.id ? '收起依据' : '为什么是它' }}
              </button>

              <div
                v-if="whyId === el.id && whyOf(el)"
                class="bub bub--why"
                :class="{ 'bub--l': i === 0, 'bub--r': i === elements.length - 1 }"
              >
                <p class="wy__text">{{ whyOf(el).text }}</p>
                <ul v-if="whyOf(el).scores.length" class="wy__sc">
                  <li v-for="s in whyOf(el).scores" :key="s[0]">
                    <span class="wy__k">{{ s[0] }}</span>
                    <span class="wy__v mono">{{ s[1] }}/10</span>
                  </li>
                </ul>
                <p v-if="riskOf(el)" class="wy__risk">
                  <span class="wy__rt">{{ riskOf(el).level === 'ok' ? '放心' : '要提醒你' }}</span>
                  {{ riskOf(el).text }}
                </p>
              </div>

              <div
                v-if="bubbleId === el.id"
                class="bub"
                :class="{ 'bub--l': i === 0, 'bub--r': i === elements.length - 1 }"
              >
                <input
                  v-model="draft"
                  class="bub__in"
                  type="text"
                  :placeholder="`关于「${el.role}」…`"
                  :aria-label="`对「${el.role}」提出修改`"
                  @keydown.enter.prevent="sendAsk(el)"
                />
                <button class="bub__go" type="button" :disabled="!draft.trim()" @click="sendAsk(el)">
                  问
                </button>
              </div>
            </li>

            <!-- 还没长出来的位置：让「正在成形」看得见 -->
            <li v-for="n in pendingSlots" :key="`ph-${n}`" class="it it--ph">
              <span class="it__ph">{{ running ? '配构成中…' : '待配' }}</span>
            </li>
          </ul>
        </div>

        <div class="gb__aside">
          <CuratorPanel
            :notes="notes"
            :hidden="hiddenNotes"
            :evidence="evidence"
            :reply="reply"
            :options="options"
            @pick="onPickOption"
            @cancel="resetAsk"
          />
        </div>
      </div>

      <footer class="gb__bot">
        <div class="gb__track">
          <span v-if="dotCount" class="gb__dots">
            <span v-for="i in dotCount" :key="i" class="dot" :class="{ on: i === dotCount }" />
          </span>
          <button class="gb__loglink" type="button" @click="openThink">{{ trackLabel }}</button>
        </div>

        <span class="gb__sum">合计 <b class="mono">¥{{ total }}</b></span>
        <span v-if="budgetLabel" class="gb__bud">{{ budgetLabel }}</span>

        <button class="gbtn gbtn--warm" type="button" @click="openStudio">就这样定</button>
      </footer>
    </template>

    <!-- 覆盖层：定制 / 清单 / 思考 —— 都不占主页面高度 -->
    <div v-if="overlay" class="ov">
      <div class="ov__scrim" @click="closeOverlay" />

      <section
        class="ov__panel"
        role="dialog"
        aria-modal="true"
        :aria-label="overlay === 'think' ? '思考时间线' : '定制与清单'"
      >
        <header class="ov__hd">
          <template v-if="overlay === 'studio'">
            <button class="ov__tab" :class="{ on: studioTab === 'workshop' }" type="button" @click="studioTab = 'workshop'">定制</button>
            <button class="ov__tab" :class="{ on: studioTab === 'receipt' }" type="button" @click="studioTab = 'receipt'">清单</button>
            <button class="ov__tab" type="button" @click="studioTab = 'think'">思考</button>
          </template>
          <span v-else class="ov__title">思考时间线</span>

          <span class="ov__hint">{{ thinkCount }} 段推理 · Esc 或返回键关闭</span>
          <button class="ov__x" type="button" aria-label="关闭" @click="closeOverlay">✕</button>
        </header>

        <div class="ov__body">
          <template v-if="overlay === 'studio' && studioTab === 'workshop'">
            <WorkshopBlock
              :recipient="brief.recipient"
              :occasion="brief.occasion"
              :concept="active || {}"
              :revisions="revisions"
              @done="onWorkshopDone"
            />
          </template>

          <ReceiptBlock
            v-else-if="overlay === 'studio' && studioTab === 'receipt'"
            :brief="brief"
            :concept="active || {}"
            :elements="elements"
            :custom="custom"
            @save-image="onReceiptAction('save')"
            @order="onReceiptAction('order')"
          />

          <ThinkTimeline v-else :timeline="timeline" />
        </div>
      </section>
    </div>

    <Transition name="gb-toast">
      <p v-if="toast" class="gb__toast">{{ toast }}</p>
    </Transition>
  </div>
</template>

<script setup>
/**
 * 代购送礼 · 礼盒生长（v2.1 · 流驱动）
 *
 * v2.0 被指出「像纯前端界面，和 agent 搭不到边」——这个批评成立，原因是
 * 上一版为了治「太长」，把 agent 的过程全藏了，而送礼 agent 的推理本身
 * 就是产品价值（依据就是心意）。
 *
 * 这一版的改动只有一句：**界面不再持有方案数据，只渲染 agent 流**。
 * 方向、物件、理由、风险、依据全部来自事件（见 data/giftAgentStream.js）。
 *
 * long reasoning 的处理见设计方案 §10 —— 按用途拆三处，每处都不增长：
 *   层1 状态条（AgentStageBar）  ：只显示当前这一句，新句覆盖旧句
 *   层2 就近挂载                  ：结论旁（右栏）+ 物件上（「为什么是它」）
 *   层3 思考时间线（ThinkTimeline）: 唯一可以长的地方，放在覆盖层里
 *
 * 仍然守住的：一屏固定、旁白 ≤2 条、同类目内替换、改动理由留痕、页面不随推进增长。
 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import BriefBlock from '@/components/gift/blocks/BriefBlock.vue'
import WorkshopBlock from '@/components/gift/blocks/WorkshopBlock.vue'
import ReceiptBlock from '@/components/gift/blocks/ReceiptBlock.vue'
import GiftBox from '@/components/gift/GiftBox.vue'
import ItemGlyph from '@/components/gift/ItemGlyph.vue'
import CuratorPanel from '@/components/gift/CuratorPanel.vue'
import AgentStageBar from '@/components/gift/AgentStageBar.vue'
import ThinkTimeline from '@/components/gift/ThinkTimeline.vue'
import { CONCEPTS, CONCEPT_ALTERNATES, totalOf } from '@/data/giftDemo'
import { useGiftAgent } from '@/composables/useGiftAgent'

const stage = ref('brief')
const brief = ref({ recipient: '', occasion: '', budget: 0 })
const activeId = ref('')

const bubbleId = ref('')
const whyId = ref('')
const focusId = ref('')
const draft = ref('')
const reply = ref('')
const options = ref([])

const custom = ref({})
const overlay = ref('')
const studioTab = ref('workshop')
const toast = ref('')

const {
  stageState,
  liveBy,
  liveText,
  running,
  settled,
  directions,
  evidence,
  timeline,
  thinkCount,
  start,
  ensureComposed,
  abort
} = useGiftAgent({ speed: 1 })

/** 方向由流产生；active 始终跟着流里第一个已吐出的方向，用户切换时 activeId 覆盖它 */
const active = computed(
  () => directions.value.find((d) => d.id === activeId.value) || directions.value[0] || null
)
const elements = computed(() => active.value?.elements || [])
const revisions = computed(() => active.value?.revisions || [])
const total = computed(() => elements.value.reduce((s, e) => s + (Number(e.price) || 0), 0))
const pendingSlots = computed(() => Math.max(0, (active.value?.slots || 0) - elements.value.length))

const boxPalette = computed(() => active.value?.palette || ['#c9983c', '#dfc183', '#3a2f26'])
const boxLabel = computed(() =>
  active.value ? `${active.value.title} 的礼盒，${elements.value.length} 件` : '正在成形的礼盒'
)

/**
 * 层2 · 结论级依据：最多 2 条（硬约束，见 .impeccable.md）。
 * 优先级是有讲究的：刚改的 > critic 的提醒 > analyst 的理由。
 * critic 排在理由之前，是因为「提醒」比「理由」更需要用户看到。
 */
const notes = computed(() => {
  const a = active.value
  if (!a) return []
  const out = []
  if (a.thesis) out.push({ id: 'thesis', tag: '方向', text: a.thesis })

  const revs = a.revisions
  const warn = (a.risks || []).find((r) => r.level !== 'ok')
  if (revs.length) {
    out.push({ id: `rev-${revs.length}`, tag: '刚改的', text: revs[revs.length - 1].reason })
  } else if (warn) {
    out.push({ id: 'warn', tag: '要提醒你', text: warn.text })
  } else {
    const last = Object.entries(a.why || {}).pop()
    if (last) out.push({ id: `why-${last[0]}`, tag: '为什么是它', text: last[1].text })
  }
  return out.slice(0, 2)
})

/** 折叠进时间线的推理段数（不是藏起来，是换个位置放） */
const hiddenNotes = computed(() => Math.max(0, thinkCount.value - notes.value.length))

const budgetLabel = computed(() => {
  const budget = Number(brief.value.budget) || 0
  if (!budget) return ''
  const diff = budget - total.value
  return diff >= 0 ? `低于预算 ¥${diff}` : `超出预算 ¥${-diff}`
})

const trackLabel = computed(() => {
  if (running.value) return `策展人正在推演 · ${thinkCount.value} 段已记`
  if (thinkCount.value) return `思考 ${thinkCount.value} 段 · 点开看全过程`
  return '还没有推理记录'
})

const dotCount = computed(() => Math.min(6, revisions.value.length))
const pickedWrap = computed(() => custom.value.wrap || 'plain')
const pickedRibbon = computed(() => custom.value.ribbon || 'auto')

const whyOf = (el) => active.value?.why?.[el.id] || null
const riskOf = (el) => (active.value?.risks || []).find((r) => r.elementId === el.id) || null

let toastTimer = 0
const say = (text) => {
  toast.value = text
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toast.value = '' }, 2400)
}

const resetAsk = () => {
  bubbleId.value = ''
  whyId.value = ''
  focusId.value = ''
  draft.value = ''
  reply.value = ''
  options.value = []
}

const onBrief = (payload) => {
  brief.value = payload
  stage.value = 'box'
  activeId.value = ''
  resetAsk()
  // 界面不预先持有方案：一切都从流里来
  start(payload, CONCEPTS)
}

const pickDirection = (d) => {
  if (active.value && d.id === active.value.id) return
  activeId.value = d.id
  custom.value = {} // 下游截断：定制与清单属于上一个方向
  resetAsk()
  // 没配过构成的方向，现场再跑一段流（不是预先全算好）
  ensureComposed(d.id)
}

const refreshDirections = () => {
  const n = CONCEPT_ALTERNATES.length
  const floor = Math.floor(Date.now() / 1000) % n
  const next = [0, 1, 2].map((k) => CONCEPT_ALTERNATES[(floor + k) % n])
  activeId.value = ''
  custom.value = {}
  resetAsk()
  start(brief.value, next)
  say('换了一批方向，重新推演')
}

const onItemClick = (el) => {
  if (el.fixed) {
    say('卡片与礼盒是这一盒的锚点，不参与替换')
    return
  }
  whyId.value = ''
  if (bubbleId.value === el.id) {
    resetAsk()
    return
  }
  bubbleId.value = el.id
  focusId.value = el.id
  draft.value = ''
  reply.value = ''
  options.value = []
}

const onWhyClick = (el) => {
  bubbleId.value = ''
  whyId.value = whyId.value === el.id ? '' : el.id
  focusId.value = whyId.value ? el.id : ''
}

/** 用户批注 → 策展人回应。推理还在跑时如实说明会合并处理（这就是「可插话」） */
const sendAsk = (el) => {
  const text = draft.value.trim()
  if (!text) return
  el.annotation = text
  reply.value = running.value
    ? '记下了。这一轮还在推，等它收口我一起调——同类目里有这几个方向：'
    : `明白。同类目里还有这几个，都能保住「${active.value.title}」的调性：`
  options.value = el.replaceOptions || []
  bubbleId.value = ''
  draft.value = ''
}

const onPickOption = (opt) => {
  const dir = active.value
  const el = (dir?.elements || []).find((e) => e.id === focusId.value)
  if (!el) return

  const from = el.name
  el.name = opt.name
  el.note = opt.note
  el.price = opt.price
  el.status = 'replaced'
  el.reason = opt.note
  el.history = [...(el.history || []), { from, to: opt.name }]

  dir.revisions.push({
    elementId: el.id,
    role: el.role,
    from,
    to: opt.name,
    reason: opt.note,
    annotation: el.annotation || ''
  })

  resetAsk()
  say(`已把「${from}」换成「${opt.name}」`)
}

/* ── 覆盖层 ── */
let pushed = false
const openOverlay = (kind) => {
  overlay.value = kind
  if (pushed) return
  try {
    history.pushState({ giftOverlay: kind }, '', location.href)
    pushed = true
  } catch {
    pushed = false
  }
}

const closeOverlay = () => {
  const had = pushed
  overlay.value = ''
  pushed = false
  if (had) {
    try { history.back() } catch { /* 历史不可用时忽略 */ }
  }
}

const onPop = () => {
  if (!overlay.value) return
  overlay.value = ''
  pushed = false
}

const openStudio = () => {
  studioTab.value = 'workshop'
  openOverlay('studio')
}

/** 思考时间线直接开在第三个 tab —— 过程可见，但不占主页面高度 */
const openThink = () => {
  studioTab.value = 'think'
  openOverlay('studio')
}

const onWorkshopDone = (payload) => {
  custom.value = payload
  studioTab.value = 'receipt'
}

const onReceiptAction = (kind) => {
  say(
    kind === 'order'
      ? '下单链路待接入 —— 清单已可复制，落库购物档案的部分一并等后端'
      : '存图待接入（需 canvas 渲染），可先用「复制文案」'
  )
}

const onKeydown = (e) => {
  if (e.key !== 'Escape') return
  if (overlay.value) {
    closeOverlay()
    return
  }
  if (bubbleId.value || whyId.value) resetAsk()
}

const restart = () => {
  abort()
  stage.value = 'brief'
  activeId.value = ''
  custom.value = {}
  resetAsk()
  overlay.value = ''
  pushed = false
}

onMounted(() => {
  window.addEventListener('popstate', onPop)
  window.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('popstate', onPop)
  window.removeEventListener('keydown', onKeydown)
  clearTimeout(toastTimer)
})
</script>

<style lang="less" scoped>
.gb {
  position: relative;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--bg-base);
  overflow: hidden;
}

/* ---- 第 0 层：开场 ---- */
.gb__brief {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow-y: auto;
  padding: 28px 24px;
}
.gb__briefin { width: 100%; max-width: 620px; }

/* ---- 顶栏 ---- */
.gb__top {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 26px;
  border-bottom: 1px solid var(--border);
}
.gb__dirs {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  overflow: hidden;
}
.dir {
  display: inline-flex;
  align-items: baseline;
  gap: 7px;
  font-family: var(--font-body);
  font-size: 0.78rem;
  padding: 6px 14px;
  border-radius: 99px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  white-space: nowrap;
  transition: border-color 0.15s ease-out, color 0.15s ease-out, background-color 0.15s ease-out;
}
.dir:hover { border-color: var(--border-strong); color: var(--text); }
.dir.on {
  border-color: var(--gift-accent);
  background: var(--gift-accent-soft);
  color: var(--gift-accent);
}
.dir__t { font-weight: 500; }
.dir__p { font-size: 0.72rem; opacity: 0.8; }
.dir--more { border-style: dashed; color: var(--text-faint); }
.dir--ghost {
  border-style: dashed;
  color: var(--text-faint);
  cursor: default;
  animation: dir-ghost 1.4s ease-in-out infinite;
}
@keyframes dir-ghost {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
@media (prefers-reduced-motion: reduce) {
  .dir--ghost { animation: none; }
}

.gb__ctx {
  margin: 0 0 0 auto;
  font-size: 0.74rem;
  color: var(--text-faint);
  white-space: nowrap;
  flex: 0 0 auto;
}
.gb__again {
  flex: 0 0 auto;
  font-family: var(--font-body);
  font-size: 0.72rem;
  padding: 5px 12px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-faint);
  cursor: pointer;
}
.gb__again:hover { color: var(--text); border-color: var(--border-strong); }

/* ---- 主体 ---- */
.gb__mid {
  flex: 1 1 auto;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 296px;
  overflow: hidden;
}

.gb__stage {
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 20px 26px 30px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.gb__box {
  width: 300px;
  height: 196px;
  flex: 0 0 auto;
}

.gb__caption {
  display: flex;
  align-items: baseline;
  gap: 9px;
  margin: 22px 0 28px;
}
.gb__capt {
  font-family: var(--font-display);
  font-size: 1.04rem;
  font-weight: 600;
  color: var(--text-strong);
}
.gb__capn { font-size: 0.74rem; color: var(--text-faint); }

.items {
  list-style: none;
  margin: 0;
  padding: 0;
  width: 100%;
  max-width: 690px;
  display: flex;
  gap: 14px;
  justify-content: center;
  align-items: stretch;
}
.it {
  position: relative;
  flex: 1 1 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--bg-surface);
  transition: border-color 0.15s ease-out, background-color 0.15s ease-out;
}
.it--focus { border-color: var(--gift-accent); }
.it--done { background: var(--gift-accent-soft); }
.it--ph {
  align-items: center;
  justify-content: center;
  border-style: dashed;
  background: transparent;
}
.it__ph {
  font-size: 0.72rem;
  color: var(--text-faint);
  padding: 24px 0;
}

.it__btn {
  flex: 1 1 auto;
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  text-align: left;
  font-family: var(--font-body);
  padding: 13px 13px 9px;
  border: none;
  background: transparent;
  cursor: pointer;
}
.it__glyph {
  width: 42px;
  height: 42px;
  flex: 0 0 auto;
  color: var(--gift-accent);
}
.it__tx {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.it__name {
  font-size: 0.78rem;
  font-weight: 500;
  color: var(--text-strong);
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.it__sub {
  font-size: 0.7rem;
  color: var(--text-faint);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.it__chip {
  position: absolute;
  top: -7px;
  right: 9px;
  font-size: 0.64rem;
  padding: 1px 7px;
  border-radius: 99px;
  background: var(--gift-accent);
  color: var(--bg-surface);
}
/* critic 的标记：挂在出问题的那一件上，而不是汇总在一处 */
.it__risk {
  position: absolute;
  top: 9px;
  right: 9px;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--chart-palette-4);
}
.it__risk.is-ok { background: var(--border-strong); }

.it__why {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  font-family: var(--font-body);
  font-size: 0.7rem;
  color: var(--gift-accent);
  padding: 4px 13px 9px;
  border: none;
  background: transparent;
  cursor: pointer;
  text-align: left;
}
.it__why:hover { text-decoration: underline; }
.it__whydot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--gift-accent);
  flex: 0 0 auto;
}

/* ---- 气泡（批注 / 依据共用同一套定位） ---- */
.bub {
  position: absolute;
  left: 50%;
  top: calc(100% + 10px);
  transform: translateX(-50%);
  width: 306px;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 8px 7px 12px;
  border: 1px solid var(--gift-accent-line);
  border-radius: 11px;
  background: var(--bg-surface);
  z-index: 5;
  animation: bub-in 0.18s ease-out both;
}
.bub--l { left: -8px; transform: none; }
.bub--r { left: auto; right: -8px; transform: none; }
@keyframes bub-in {
  from { opacity: 0; }
  to   { opacity: 1; }
}
@media (prefers-reduced-motion: reduce) {
  .bub { animation: none; }
}
.bub__in {
  flex: 1 1 auto;
  min-width: 0;
  border: none;
  outline: none;
  background: transparent;
  font-family: var(--font-body);
  font-size: 0.78rem;
  color: var(--text);
  padding: 2px 0;
}
.bub__in::placeholder { color: var(--text-faint); }
.bub__go {
  flex: 0 0 auto;
  font-family: var(--font-body);
  font-size: 0.74rem;
  padding: 5px 12px;
  border-radius: 8px;
  border: 1px solid var(--gift-accent);
  background: var(--gift-accent);
  color: var(--bg-surface);
  cursor: pointer;
}
.bub__go:disabled { opacity: 0.45; cursor: not-allowed; }

/* ---- 依据气泡：比批注气泡宽，因为它要放理由 + 打分 ---- */
.bub--why {
  display: block;
  width: 330px;
  padding: 12px 14px;
}
.wy__text {
  font-size: 0.76rem;
  line-height: 1.68;
  color: var(--text);
  margin: 0;
}
.wy__sc {
  list-style: none;
  margin: 10px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.wy__sc li {
  display: flex;
  align-items: baseline;
  gap: 10px;
  font-size: 0.72rem;
}
.wy__k { color: var(--text-muted); }
.wy__v { margin-left: auto; color: var(--text-strong); }
.wy__risk {
  margin: 10px 0 0;
  padding-top: 9px;
  border-top: 1px solid var(--border);
  font-size: 0.73rem;
  line-height: 1.65;
  color: var(--text-muted);
}
.wy__rt {
  color: var(--gift-accent);
  margin-right: 5px;
}

.gb__aside {
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 20px 26px 20px 22px;
  border-left: 1px solid var(--border);
}
.gb__aside > * { flex: 1 1 auto; min-width: 0; }

/* ---- 底栏 ---- */
.gb__bot {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 13px 26px;
  border-top: 1px solid var(--border);
}
.gb__track {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
}
.gb__dots { display: inline-flex; gap: 5px; flex: 0 0 auto; }
.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--border-strong);
}
.dot.on { background: var(--gift-accent); }
.gb__loglink {
  font-family: var(--font-body);
  font-size: 0.72rem;
  color: var(--text-faint);
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  text-align: left;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.gb__loglink:hover { color: var(--gift-accent); }
.gb__sum {
  margin-left: auto;
  font-size: 0.8rem;
  color: var(--text-muted);
  flex: 0 0 auto;
}
.gb__sum b { font-size: 1rem; color: var(--text-strong); }
.gb__bud { font-size: 0.72rem; color: var(--text-faint); flex: 0 0 auto; }

/* ---- 覆盖层 ---- */
.ov {
  position: absolute;
  inset: 0;
  z-index: 40;
  display: flex;
  flex-direction: column;
}
.ov__scrim {
  position: absolute;
  inset: 0;
  background: var(--bg-base);
  opacity: 0.9;
}
.ov__panel {
  position: relative;
  margin: 26px auto;
  width: min(1040px, calc(100% - 52px));
  max-height: calc(100% - 52px);
  display: flex;
  flex-direction: column;
  background: var(--bg-surface);
  border: 1px solid var(--border-strong);
  border-radius: 14px;
  overflow: hidden;
  animation: ov-in 0.22s ease-out both;
}
@keyframes ov-in {
  from { opacity: 0; transform: translateY(10px); }
  to   { opacity: 1; transform: none; }
}
@media (prefers-reduced-motion: reduce) {
  .ov__panel { animation: none; }
}
.ov__hd {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 11px 16px;
  border-bottom: 1px solid var(--border);
}
.ov__tab {
  font-family: var(--font-body);
  font-size: 0.8rem;
  padding: 6px 15px;
  border-radius: 99px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
}
.ov__tab.on {
  border-color: var(--gift-accent);
  background: var(--gift-accent-soft);
  color: var(--gift-accent);
}
.ov__title { font-size: 0.86rem; font-weight: 600; color: var(--text-strong); }
.ov__hint { margin-left: auto; font-size: 0.71rem; color: var(--text-faint); }
.ov__x {
  width: 26px;
  height: 26px;
  border-radius: 7px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 0.72rem;
  line-height: 1;
}
.ov__x:hover { border-color: var(--border-strong); color: var(--text); }
.ov__body {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding: 20px 22px 24px;
}

/* ---- 提示 ---- */
.gb__toast {
  position: absolute;
  left: 50%;
  bottom: 74px;
  transform: translateX(-50%);
  z-index: 60;
  margin: 0;
  padding: 9px 18px;
  border-radius: 99px;
  background: var(--bg-surface);
  border: 1px solid var(--border-strong);
  font-size: 0.78rem;
  color: var(--text);
  white-space: nowrap;
}
.gb-toast-enter-active,
.gb-toast-leave-active { transition: opacity 0.2s ease-out; }
.gb-toast-enter-from,
.gb-toast-leave-to { opacity: 0; }

/* ---- 窄屏 ---- */
@media (max-width: 980px) {
  .gb__mid {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: minmax(0, 1fr) auto;
    overflow-y: auto;
  }
  .gb__stage { padding: 16px 20px; }
  .gb__aside {
    padding: 16px 20px 20px;
    border-left: none;
    border-top: 1px solid var(--border);
  }
  .gb__ctx { display: none; }
}
</style>
