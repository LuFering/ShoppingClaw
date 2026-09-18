<template>
  <div class="wb" :data-settled="settled ? '1' : '0'">
    <header class="wb__bar">
      <span class="wb__sig">礼</span>
      <div class="wb__task">
        <p class="wb__who">送给 {{ task.recipient }} · {{ task.occasion }} · 预算 <span class="mono">¥{{ task.budget }}</span></p>
        <p class="wb__sub">替你把一件礼物从头想到能下单</p>
      </div>

      <span class="wb__state" :class="{ 'is-live': running }">
        <i class="wb__dot" />{{ running ? '推演中' : settled ? '已收敛' : '待开始' }}
      </span>

      <button class="wb__again" type="button" @click="restart">重来</button>
    </header>

    <div class="wb__body">
      <div class="col col--l">
        <ExploreStream
          :steps="steps"
          :excluded="excluded"
          :stage-key="stageKey"
          :done-count="doneCount"
        />
      </div>

      <div class="col col--m">
        <div class="col__wrap">
          <ProfileCard
            :head="PROFILE_HEAD"
            :task="task"
            :groups="profile"
            :understanding="understanding"
            @act="onAct"
          />
        </div>
      </div>

      <div class="col col--r">
        <DeliverPanel
          :items="deliverables"
          :ready-count="readyCount"
          @confirm="onConfirm"
          @revise="onRevise"
        />
      </div>
    </div>

    <Transition name="wb-toast">
      <p v-if="toast" class="wb__toast">{{ toast }}</p>
    </Transition>
  </div>
</template>

<script setup>
/**
 * 代购送礼 · v6 三栏工作台
 *
 * 结构延续采购智能体的三栏工作台，但三栏的**内容与视觉语言完全不同**：
 *   左栏 礼物探索流（时间性）  中栏 人物档案卡（稳定性）  右栏 交付区（结果性）
 *
 * 中栏刻意比左右都宽（≤470）—— 它是任务的情感锚点，不是配图。
 * 三栏各自滚动，页面本身不滚。
 */
import { ref, onMounted, onBeforeUnmount } from 'vue'
import ExploreStream from '@/components/gift/ExploreStream.vue'
import ProfileCard from '@/components/gift/ProfileCard.vue'
import DeliverPanel from '@/components/gift/DeliverPanel.vue'
import { PROFILE_HEAD } from '@/data/giftProfile'
import { useGiftWorkbench } from '@/composables/useGiftWorkbench'

const {
  task,
  steps,
  excluded,
  profile,
  understanding,
  deliverables,
  running,
  settled,
  stageKey,
  doneCount,
  readyCount,
  start,
  abort
} = useGiftWorkbench({ speed: 1 })

const toast = ref('')
let toastTimer = 0
const say = (text) => {
  toast.value = text
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toast.value = '' }, 2400)
}

/** 中栏的信息可追溯：来源要能说出来；改动落到真实实现时再走接口 */
const onAct = (g, kind) => {
  if (kind === 'source') {
    say(`来源 · ${g.source}`)
  } else if (kind === 'edit') {
    say(`改「${g.label}」—— 接后端后在这里就地编辑`)
  } else if (kind === 'remove') {
    say(`删「${g.label}」—— 删除会同时影响左栏的依据链`)
  } else {
    say(`${g.label} · ${g.state === 'pending' ? '待确认' : '已记录'} · 来源 ${g.source}`)
  }
}

const onConfirm = () => say('下单链路待接入 —— 订单已可确认，落库与支付等后端')
const onRevise = () => say('改一下 —— 会回到左栏对应步骤重新推演')

const restart = () => {
  abort()
  toast.value = ''
  start()
}

onMounted(start)
onBeforeUnmount(() => {
  abort()
  clearTimeout(toastTimer)
})
</script>

<style lang="less" scoped>
.wb {
  position: relative;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--bg-base);
  overflow: hidden;
}

/* ---- 顶栏：任务抬头 ---- */
.wb__bar {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 11px 20px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-surface);
}
.wb__sig {
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
.wb__task { min-width: 0; }
.wb__who {
  font-size: 0.82rem;
  font-weight: 500;
  color: var(--text-strong);
  margin: 0;
}
.wb__sub {
  font-size: 0.7rem;
  color: var(--text-faint);
  margin: 1px 0 0;
}

.wb__state {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.72rem;
  color: var(--text-muted);
  flex: 0 0 auto;
}
.wb__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--border-strong);
}
.wb__state.is-live { color: var(--gift-accent); }
.wb__state.is-live .wb__dot {
  background: var(--gift-accent);
  animation: wb-pulse 1.2s ease-in-out infinite;
}
@keyframes wb-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.25; }
}
@media (prefers-reduced-motion: reduce) {
  .wb__state.is-live .wb__dot { animation: none; }
}

.wb__again {
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
.wb__again:hover { color: var(--text); border-color: var(--border-strong); }

/* ---- 三栏 ----
   刻意避开采购工作台的「细边栏 + 巨无霸中栏」（268 | 1fr | 288，中栏独占 ~860px）。
   送礼的主角是「人」，但比例是**三栏协调的均衡组合**：左 0.92 / 中 1.18 / 右 1.0，
   中栏只是略宽的主角，而不是吞噬一切的大画布——视觉重心在「人」而不是「占满屏」。
     左 = 探索流，短行列表，0.92fr
     中 = 人物档案卡，情感锚点，1.18fr（最宽但只比右栏多 ~18%）
     右 = 交付区，有价格与成段文案，1.0fr
   卡片贴满中栏（max-width 提升到 560），不再留大片死白。 */
.wb__body {
  flex: 1 1 auto;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(240px, 0.92fr) minmax(420px, 1.18fr) minmax(290px, 1fr);
}
.col {
  min-height: 0;
  min-width: 0;
  overflow-y: auto;
  overflow-x: hidden;
}
.col--l {
  background: var(--bg-surface);
  border-right: 1px solid var(--border);
  padding-top: 12px;
}
.col--m {
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding: 12px clamp(14px, 1.2vw, 22px) 28px;
}
.col__wrap {
  width: 100%;
  /* 560：在 1280–1600 区间，中栏宽度 487–597，卡片贴满、两侧只留 14–20px 框距，不再死白 */
  max-width: 560px;
}
.col--r {
  background: var(--bg-surface);
  border-left: 1px solid var(--border);
  padding-top: 12px;
}

/* ---- 提示 ---- */
.wb__toast {
  position: absolute;
  left: 50%;
  bottom: 26px;
  transform: translateX(-50%);
  z-index: 40;
  margin: 0;
  padding: 9px 18px;
  border-radius: 99px;
  background: var(--bg-surface);
  border: 1px solid var(--border-strong);
  font-size: 0.76rem;
  color: var(--text);
  white-space: nowrap;
}
.wb-toast-enter-active,
.wb-toast-leave-active { transition: opacity 0.2s ease-out; }
.wb-toast-enter-from,
.wb-toast-leave-to { opacity: 0; }

/* ---- 中间档：三栏还开着，等比收一点，保持 0.85 / 1.12 / 0.95 的协调比例 ---- */
@media (max-width: 1320px) {
  .wb__body {
    grid-template-columns: minmax(220px, 0.85fr) minmax(400px, 1.12fr) minmax(270px, 0.95fr);
  }
  .col__wrap { max-width: 500px; }
  .col--m { padding-left: 14px; padding-right: 14px; }
}

/* ---- 窄屏：三栏依次堆叠 ---- */
@media (max-width: 1180px) {
  .wb__body {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: auto auto auto;
    overflow-y: auto;
  }
  .col { overflow: visible; }
  .col--l, .col--r { border: none; border-top: 1px solid var(--border); }
  .col--m { padding: 16px; }
  .col__wrap { max-width: 560px; margin: 0 auto; }
}
</style>
