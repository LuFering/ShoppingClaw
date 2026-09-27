<template>
  <div class="wb" :data-settled="settled ? '1' : '0'">
    <header class="wb__bar">
      <span class="wb__sig">礼</span>
      <div class="wb__task">
        <p class="wb__who">
          送给 {{ task.recipient || '—' }} · {{ task.occasion || '—' }} · 预算
          <span class="mono">¥{{ task.budget || '—' }}</span>
        </p>
        <p class="wb__sub">推演过程与每处取舍</p>
      </div>

      <span class="wb__state" :class="{ 'is-live': running }">
        <i class="wb__dot" />{{ running ? '推演中' : settled ? '已收敛' : '待开始' }}
      </span>

      <button
        class="wb__again"
        type="button"
        :disabled="!settled || saving || saved"
        @click="saveToArchive"
      >{{ saved ? '已存入档案' : '存入档案' }}</button>
      <button class="wb__again" type="button" @click="router.push('/proxy/new')">重来</button>
    </header>

    <div class="wb__body">
      <!-- 没有 run id：直接访问 /proxy，如实提示回入口，不编一个假任务 -->
      <div v-if="!runId" class="wb__blank">
        <p class="wb__blank-title">还没有开始一次送礼推演</p>
        <p class="wb__blank-sub">先告诉我是送给谁、什么场合，我再来搭这份礼物。</p>
        <button class="wb__blank-btn" type="button" @click="router.push('/proxy/new')">
          去描述这次送礼 →
        </button>
      </div>
      <!--
        ⚠️ 加载中**不再整块换成 spinner**。
        用户要的是「从一个空白档案慢慢变化成完整档案」—— 而 spinner 把
        档案卡整个挡住了，前 5 秒什么都看不到，然后五组一起蹦出来。
        现在直接渲染三栏骨架：中栏是空槽卡、左栏是待办步骤、右栏是等待中的
        交付物。数据一到就地填充，这才看得到「长出来」的过程。
        错误态仍然接管（那时确实没东西可显示）。
      -->
      <div v-else-if="loadError" class="wb__blank">
        <p class="wb__blank-title">{{ loadError }}</p>
        <button class="wb__blank-btn" type="button" @click="reload">重试</button>
      </div>

      <template v-else>
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
              :head="head"
              :task="task"
              :groups="profile"
              :understanding="understanding"
              :opening="opening"
              :findings="findings"
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
      </template>
    </div>

    <Transition name="wb-toast">
      <p v-if="toast" class="wb__toast">{{ toast }}</p>
    </Transition>
  </div>
</template>

<script setup>
/**
 * 代购送礼 · 三栏工作台
 *
 * 结构延续采购智能体的三栏工作台，但三栏的**内容与视觉语言完全不同**：
 *   左栏 礼物探索流（时间性）  中栏 人物档案卡（稳定性）  右栏 交付区（结果性）
 *
 * 中栏刻意比左右都宽（≤470）—— 它是任务的情感锚点，不是配图。
 * 三栏各自滚动，页面本身不滚。
 *
 * 2026-09-24 接真后端：原先数据来自 `data/giftWorkbenchStream.js` 的模拟流
 * 与 `data/giftProfile.js` 的硬编码 TASK。现在：
 *   · task（送谁/场合/预算）来自 run
 *   · 三栏内容来自 `/api/gift/runs/{id}/events` 的事件流
 *   · 首屏用 `GET /runs/{id}` 快照恢复（刷新不重放）
 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { message } from 'ant-design-vue'
import { useRoute, useRouter } from 'vue-router'
import ExploreStream from '@/components/gift/ExploreStream.vue'
import ProfileCard from '@/components/gift/ProfileCard.vue'
import DeliverPanel from '@/components/gift/DeliverPanel.vue'
import { useGiftWorkbench } from '@/composables/useGiftWorkbench'

const route = useRoute()
const router = useRouter()

// run id 来自入口页；直接访问时没有 → 如实提示回入口，不编一个假任务
const runId = computed(() => String(route.query.run || ''))

const {
  task,
  profileHead,
  steps,
  excluded,
  profile,
  understanding,
  opening,
  findings,
  deliverables,
  running,
  settled,
  loadError,
  stageKey,
  doneCount,
  readyCount,
  start,
  abort,
  reload,
  revise
} = useGiftWorkbench({ runId })

/** 抬头兜底：后端还没返回时（推演刚开始）也要能显示，不能空着 */
const head = computed(() => profileHead.value || {
  name: task.value?.recipient || '收礼人',
  initial: (task.value?.recipient || '礼').slice(0, 1),
  meta: task.value?.occasion || '送礼',
  sub: `预算 ¥${task.value?.budget || '—'}`,
  // 「读取中…」而不是编一个「档案完整 4/5」—— 完整度由后端按真实
  // 已确认组数算（build_profile_head），前端不猜。
  completeness: '档案读取中…'
})

const toast = ref('')
let toastTimer = 0
const say = (text) => {
  toast.value = text
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toast.value = '' }, 2400)
}

/** 中栏的信息可追溯：来源要能说出来；「改一下」真的调后端标记待补充 */
const onAct = async (g, kind) => {
  if (kind === 'source') {
    say(`来源 · ${g.source}`)
  } else if (kind === 'edit') {
    await revise(g.key)
    say(`已把「${g.label}」标记为待补充 —— 补充后我会重新收窄`)
  } else if (kind === 'remove') {
    say(`删「${g.label}」—— 删除会同时影响左栏的依据链`)
  } else {
    say(`${g.label} · ${g.state === 'pending' ? '待确认' : '已记录'} · 来源 ${g.source}`)
  }
}

const onConfirm = () => say('下单链路待接入 —— 订单已可确认，落库与支付等后端')
const onRevise = () => say('改一下 —— 回到入口页调整情境后重推')

// 无 runId 时 composable 的 loadSnapshot 会置 loading=false 并给出提示，
// 所以这里不需要提前 return。
// 存入档案 —— 把这次送礼的结论沉淀成一条可追踪的档案记录。
//
// 送礼与规划的区别在记录形态：送礼的产出一份「礼盒方案 + 寄语」，
// 所以 target 用收礼人 + 场合，candidates 用方案里的几件东西，
// aiSummary 用「当前理解」那句（它本来就是这次推演的核心判断）。
// `runId` 回指本次推演，档案页可据此跳回去看过程。
const saved = ref(false)
const saving = ref(false)

const saveToArchive = async () => {
  if (saving.value || saved.value || !settled.value) return
  saving.value = true
  try {
    const { decisionsApi } = await import('@/apis/decisions_api')
    const plan = deliverables.value.find((d) => d.key === 'plan')?.data || {}
    const items = plan.items || []
    const rec = {
      id: `gf-${Date.now().toString(36)}`,
      phase: 'decided',
      source: 'gift',
      target: `送给${task.value.recipient || '对方'}的${task.value.occasion || '礼物'}`,
      category: '送礼',
      note: plan.thesis || '来自送礼推演',
      rawIdea: '',
      budget: task.value.budget ? `¥${task.value.budget}` : '',
      forWhom: task.value.recipient || '',
      scenario: task.value.occasion || '',
      aiSummary: understanding.value.text || plan.thesis || '',
      candidates: items.map((i) => ({ name: i.name, price: Number(i.price) || 0 })),
      aiRecommend: plan.title || '',
      recReason: items.map((i) => `${i.role}：${i.why}`).join('；'),
      risk: '',
      bestPrice: items.length ? `¥${items.reduce((s, i) => s + (Number(i.price) || 0), 0)}` : '',
      dealPrice: '', purchasedAt: '', reviewNote: '', dropNote: '',
      reminders: [], insights: [],
      threadId: null,
      runId: runId.value || null,
      ts: Date.now(),
      updatedAt: '刚刚'
    }
    const ok = await decisionsApi.createOne(rec)
    if (ok) { saved.value = true; message.success('已存入购物档案') }
    else message.error('存入失败，请重试')
  } finally {
    saving.value = false
  }
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
  /* 2026-09-27：对齐规划工作台（PurchaseWorkbenchView 同一组数字）。
     原先 0.92 / 1.18 / 1fr，中栏约 490px —— 人物档案卡是这一页的主角，
     却被挤在中间；用户要求「左右收窄、中间扩大」。 */
  grid-template-columns: 268px minmax(0, 1fr) 288px;
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
  /* 放开到 760：中栏现在约 860px（268|1fr|288），限 560 会在两侧留出
     大片死白。卡片本身该是这一页的主角。 */
  max-width: 760px;
}
.col--r {
  background: var(--bg-surface);
  border-left: 1px solid var(--border);
  padding-top: 12px;
}

/* ---- 空态 / 加载 / 错误（占满三栏区，居中） ---- */
.wb__blank {
  grid-column: 1 / -1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  text-align: center;
  padding: 40px 24px;
}
.wb__blank-title {
  margin: 0;
  font-family: var(--font-display);
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-strong);
}
.wb__blank-sub {
  margin: 0;
  font-size: 0.82rem;
  line-height: 1.7;
  color: var(--text-muted);
  max-width: 340px;
}
.wb__blank-btn {
  margin-top: 4px;
  font-family: var(--font-body);
  font-size: 0.8rem;
  padding: 8px 16px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--gift-accent);
  background: var(--gift-accent);
  color: var(--on-accent);
  cursor: pointer;
  &:hover { opacity: 0.88; }
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
/* 中间档：三栏还开着，左右收到最小可用宽度，把余量给中栏 */
@media (max-width: 1320px) {
  .wb__body {
    grid-template-columns: 248px minmax(0, 1fr) 268px;
  }
  .col__wrap { max-width: 100%; }
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
