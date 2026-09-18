<template>
  <div class="gw">
    <header class="gw__bar">
      <span class="gw__sig">礼</span>
      <div class="gw__id">
        <p class="gw__name">送礼 · 代购送礼</p>
        <p class="gw__sub">替家人朋友挑一件不容易闲置的礼物</p>
      </div>
      <button v-if="stream.length > 1" class="gw__reset" type="button" @click="reset">重新开始</button>
    </header>

    <div class="gflow">
      <template v-for="b in stream" :key="b.id">
        <BriefBlock
          v-if="b.kind === 'brief'"
          :data-blk="b.id"
          @submit="onBrief"
        />

        <ConceptsBlock
          v-else-if="b.kind === 'concepts'"
          :data-blk="b.id"
          :list="b.list"
          :selected-id="pickedId"
          @pick="onPick"
          @refresh="onRefresh"
        />

        <ConceptBlock
          v-else-if="b.kind === 'concept'"
          :data-blk="b.id"
          :concept="b.concept"
          @revised="onRevised"
          @next="onConceptDone"
        />

        <WorkshopBlock
          v-else-if="b.kind === 'workshop'"
          :data-blk="b.id"
          :recipient="brief.recipient"
          :occasion="brief.occasion"
          :concept="pickedConcept"
          :revisions="revisions"
          @done="onWorkshopDone"
        />

        <ReceiptBlock
          v-else-if="b.kind === 'receipt'"
          :data-blk="b.id"
          :brief="brief"
          :concept="pickedConcept"
          :elements="finalElements"
          :custom="custom"
          @save-image="onSaveImage"
          @order="onOrder"
        />
      </template>
    </div>

    <Transition name="gw-toast">
      <p v-if="toast" class="gw__toast">{{ toast }}</p>
    </Transition>
  </div>
</template>

<script setup>
/**
 * 代购送礼 · 流式卷轴
 *
 * 页面 = 一条有序的块流：
 *   追加 → 新块滚动入场；更新 → 按 id 打补丁，只重渲染那一块。
 * 这是「局部刷新不断层」能成立的前提 —— 所以每块必须有稳定的 id。
 *
 * 一条容易漏但必须有的逻辑：
 *   用户在定制完之后回头改选概念时，下游的「定制工作台」与「礼品清单」已经过期了，
 *   必须整段截断重来。否则清单里会混进上一个概念的包装和寄语。
 *
 * 收礼人档案不由用户维护：阶段 5 的清单落库后自动沉淀，下次开场就能预填。
 */
import { ref, computed, nextTick } from 'vue'
import BriefBlock from '@/components/gift/blocks/BriefBlock.vue'
import ConceptsBlock from '@/components/gift/blocks/ConceptsBlock.vue'
import ConceptBlock from '@/components/gift/blocks/ConceptBlock.vue'
import WorkshopBlock from '@/components/gift/blocks/WorkshopBlock.vue'
import ReceiptBlock from '@/components/gift/blocks/ReceiptBlock.vue'
import { CONCEPTS, CONCEPT_ALTERNATES } from '@/data/giftDemo'

let seq = 0
const nid = (p) => `${p}-${++seq}`

const stream = ref([{ id: 'blk-brief', kind: 'brief' }])
const brief = ref({ recipient: '', occasion: '', budget: 0 })
const pickedId = ref('')
const revisions = ref([])
const finalElements = ref([])
const custom = ref({})
const toast = ref('')
let alternateIndex = 0

const pickedConcept = computed(
  () => stream.value.find((b) => b.kind === 'concept')?.concept || {}
)

const say = (text) => {
  toast.value = text
  setTimeout(() => { toast.value = '' }, 2200)
}

const scrollToBlock = async (id) => {
  await nextTick()
  const el = document.querySelector(`[data-blk="${id}"]`)
  el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

const append = async (block) => {
  stream.value.push(block)
  await scrollToBlock(block.id)
}

/** 截断到某个块之后（含该块），下游全部丢弃 */
const truncateAfter = (kind) => {
  const i = stream.value.findIndex((b) => b.kind === kind)
  if (i >= 0) stream.value = stream.value.slice(0, i + 1)
}

/* ── 阶段 1 → 2 ── */
const onBrief = async (payload) => {
  brief.value = payload
  if (!stream.value.some((b) => b.kind === 'concepts')) {
    await append({ id: nid('blk-concepts'), kind: 'concepts', list: CONCEPTS })
  }
}

/* ── 阶段 2 → 3 ── */
const onPick = async (concept) => {
  pickedId.value = concept.id
  revisions.value = []
  finalElements.value = []
  custom.value = {}

  // 改选概念 → 下游的定制与清单已过期，必须截断
  truncateAfter('concepts')

  const prev = stream.value.find((b) => b.kind === 'concept')
  if (prev) {
    // 已有展开卡则就地替换内容（仍是同一块，不重挂载）
    prev.concept = concept
    await scrollToBlock(prev.id)
    return
  }
  await append({ id: nid('blk-concept'), kind: 'concept', concept })
}

/** 换一批灵感：只换提案组本身 */
const onRefresh = () => {
  const b = stream.value.find((x) => x.kind === 'concepts')
  if (!b) return
  const cur = b.list.map((c) => c.id).join(',')
  let next = CONCEPT_ALTERNATES
  for (let i = 0; i < CONCEPT_ALTERNATES.length; i++) {
    alternateIndex += 1
    const start = alternateIndex % CONCEPT_ALTERNATES.length
    next = [
      CONCEPT_ALTERNATES[start],
      CONCEPT_ALTERNATES[(start + 1) % CONCEPT_ALTERNATES.length],
      CONCEPT_ALTERNATES[(start + 2) % CONCEPT_ALTERNATES.length]
    ]
    if (next.map((c) => c.id).join(',') !== cur) break
  }
  b.list = next
  pickedId.value = ''
  truncateAfter('concepts')
  say('换了一批，看看有没有更贴的')
}

const onRevised = (r) => {
  revisions.value = [...revisions.value, r]
}

/* ── 阶段 3 → 4 ── */
const onConceptDone = async (elements) => {
  finalElements.value = JSON.parse(JSON.stringify(elements))
  truncateAfter('concept')
  await append({ id: nid('blk-workshop'), kind: 'workshop' })
}

/* ── 阶段 4 → 5 ── */
const onWorkshopDone = async (payload) => {
  custom.value = payload
  truncateAfter('workshop')
  await append({ id: nid('blk-receipt'), kind: 'receipt' })
}

/* ── 阶段 5 出口 ── */
const onSaveImage = () => {
  // 真实实现用 canvas 把清单渲染成图片；此处先如实标注未实现
  say('存图待接入（需 canvas 渲染），可先用「复制文案」')
}

const onOrder = () => {
  say('下单链路待接入 —— 清单已可复制，落库购物档案的部分一并等后端')
}

const reset = () => {
  seq = 0
  stream.value = [{ id: 'blk-brief', kind: 'brief' }]
  brief.value = { recipient: '', occasion: '', budget: 0 }
  pickedId.value = ''
  revisions.value = []
  finalElements.value = []
  custom.value = {}
  alternateIndex = 0
  window.scrollTo?.({ top: 0, behavior: 'smooth' })
}
</script>

<style lang="less" scoped>
.gw {
  min-height: 100%;
  background: var(--bg-base);
}

/* 顶部身份条：与采购页一致的「署名」逻辑，但更轻，不抢开场 */
.gw__bar {
  max-width: 760px;
  margin: 0 auto;
  padding: 14px 24px 0;
  display: flex;
  align-items: center;
  gap: 10px;
}
.gw__sig {
  width: 26px;
  height: 26px;
  border-radius: 7px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--gift-accent-soft);
  color: var(--gift-accent);
  font-size: 0.78rem;
  font-weight: 600;
  flex: 0 0 auto;
}
.gw__id { min-width: 0; }
.gw__name {
  font-size: 0.84rem;
  font-weight: 600;
  color: var(--text-strong);
  margin: 0;
}
.gw__sub {
  font-size: 0.72rem;
  color: var(--text-faint);
  margin: 1px 0 0;
}
.gw__reset {
  margin-left: auto;
  font-family: var(--font-body);
  font-size: 0.72rem;
  padding: 4px 12px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  flex: 0 0 auto;
}
.gw__reset:hover { color: var(--text); border-color: var(--border-strong); }

.gw__toast {
  position: fixed;
  left: 50%;
  bottom: 32px;
  transform: translateX(-50%);
  z-index: 80;
  margin: 0;
  padding: 9px 18px;
  border-radius: 99px;
  background: var(--bg-surface);
  border: 1px solid var(--border-strong);
  font-size: 0.78rem;
  color: var(--text);
}
.gw-toast-enter-active,
.gw-toast-leave-active { transition: opacity 0.2s ease-out, transform 0.2s ease-out; }
.gw-toast-enter-from,
.gw-toast-leave-to { opacity: 0; transform: translate(-50%, 8px); }
</style>
