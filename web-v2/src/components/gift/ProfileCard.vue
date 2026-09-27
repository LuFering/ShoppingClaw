<template>
  <article class="pc">
    <!-- 人物视觉主体 + 三项任务摘要 -->
    <header class="pc__head">
      <div class="pc__avatar">
        <span class="pc__initial">{{ head.initial }}</span>
        <span class="pc__ribbon">{{ relationShort }}</span>
      </div>

      <div class="pc__id">
        <div class="pc__namerow">
          <h2 class="pc__name">{{ head.name }}</h2>
          <!--
            ⚠️ 这里原本还有一个「档案完整 2/5」的胶囊，与下方进度条重复。
            同一个数字出现两次既冗余、又占掉了名字右边的空间（窄屏会挤掉名字）。
            完整度统一由进度条表达 —— 它还能逐格点亮，比一个静态数字更有信息量。
          -->
        </div>
        <p class="pc__rel">{{ head.meta }}</p>

        <div class="pc__meta">
          <span class="pc__metaItem"><i>送给</i><b class="pc__fv">{{ task.recipient }}</b></span>
          <span class="pc__metaSep">·</span>
          <span class="pc__metaItem"><i>场合</i><b class="pc__fv">{{ task.occasion }}</b></span>
          <span class="pc__metaSep">·</span>
          <span class="pc__metaItem"><i>预算</i><b class="pc__fv mono">¥{{ task.budget }}</b></span>
        </div>
      </div>
    </header>

    <!--
      开场陈述 —— 学 Letta 的 `human` 记忆块写法：起点不是空白，而是
      一句诚实的「我还不了解 TA」+「我打算怎么去了解」。
      空槽只说明「这里没有东西」；这句话说明「正在建立，而且我知道要建什么」。
      推演一开始就有，随第一条真实信息到达而淡出（它已经完成使命了）。
    -->
    <p v-if="opening" class="pc__opening">
      {{ opening.text }}
      <span class="pc__opening-sub">{{ opening.sub }}</span>
    </p>

    <!--
      ═══════════════════════════════════════════════════════════════
      档案绘制进度 —— 「从 0 开始绘制」的可见载体
      ═══════════════════════════════════════════════════════════════
      用户的原话：「没有那种让我感觉到 agent 正在从 0 绘制个人档案的感觉」。

      查实的原因：五组档案在 **15 毫秒**内全部到达 —— 后端确实是一批批发的
      （历史一批、偏好一批，相隔 400ms），但两次查询都是本地的，加起来
      还不够一次眨眼。**光靠到达时刻做不出「绘制感」**。

      所以这里补一层视觉：五个格子从一开始就画出来（空心的），每读到一个
      就点亮一个。用户看到的是「0/5 → 1/5 → 2/5」这个**计数器在动**，
      而不是「五条一起出现」。

      ⚠️ 它不造假：格子数 = 档案组数（固定 schema），点亮数 = 真实已确认数
      （由后端 build_profile_head 算）。推进慢是因为数据来得慢，不是因为
      我们拖时间。
    -->
    <div class="pc__meter" :class="{ 'is-complete': confirmedCount >= totalGroups }">
      <span class="pc__meter-label">
        档案完整
        <b class="mono">{{ confirmedCount }}/{{ totalGroups }}</b>
      </span>
      <span class="pc__meter-cells">
        <i
          v-for="n in totalGroups"
          :key="n"
          class="pc__cell"
          :class="{ on: n <= confirmedCount }"
        />
      </span>
    </div>

    <!-- 人物侧写：编辑式排版，小标签 + 大正文 -->
    <section class="pc__section">
      <h3 class="pc__sectitle">人物侧写</h3>
      <div class="pc__rows">
        <div
          v-for="g in normalGroups"
          :key="g.key"
          class="gr"
          :class="{ 'gr--fresh': g.fresh }"
          role="button"
          tabindex="0"
          :aria-label="`${g.label}：${g.text}（${stateLabel(g.state)}），可展开来源与操作`"
          @click="$emit('act', g, 'open')"
          @keydown.enter.prevent="$emit('act', g, 'open')"
        >
          <span class="gr__rail">
            <i class="gr__dot" :class="`is-${g.state}`" />
          </span>
          <div class="gr__main">
            <span class="gr__label">{{ g.label }}</span>
            <!--
              空槽（还没读到）与「读到了但没有」是**两件事**，界面上要分得清：
                todo     —— 淡虚线占位 + 「尚未读到」，表示还在等
                pending  —— 显示后端给的具体文案（如「未记录」），表示已经问过了
              混为一谈的话，用户分不清「它还没查」与「查了但没有」。
            -->
            <p v-if="g.state === 'todo'" class="gr__text gr__text--empty">
              尚未读到…
            </p>
            <p v-else class="gr__text">
              {{ g.text }}
              <span v-if="g.note" class="gr__note">{{ g.note }}</span>
              <span v-if="g.arrivedAt" class="gr__at mono">{{ clock(g.arrivedAt) }}</span>
            </p>
          </div>
          <span v-if="g.state !== 'todo'" class="gr__acts">
            <button type="button" @click.stop="$emit('act', g, 'source')">来源</button>
            <button type="button" @click.stop="$emit('act', g, 'edit')">改</button>
            <button type="button" @click.stop="$emit('act', g, 'remove')">删</button>
          </span>
        </div>
      </div>
    </section>

    <!-- 明确禁忌：独立成区，危险色包裹，不与侧写混排 -->
    <section v-if="dangerGroups.length" class="pc__section pc__avoid">
      <h3 class="pc__sectitle pc__sectitle--danger">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4">
          <path d="M8 1.8 14.4 13.5H1.6L8 1.8Z" /><path d="M8 6.4v3.1" /><circle cx="8" cy="11.4" r="0.5" fill="currentColor" stroke="none" />
        </svg>
        明确禁忌
      </h3>
      <div class="pc__rows">
        <div
          v-for="g in dangerGroups"
          :key="g.key"
          class="gr gr--danger"
          :class="{ 'gr--fresh': g.fresh }"
          role="button"
          tabindex="0"
          :aria-label="`${g.label}：${g.text}（${stateLabel(g.state)}），可展开来源与操作`"
          @click="$emit('act', g, 'open')"
          @keydown.enter.prevent="$emit('act', g, 'open')"
        >
          <span class="gr__rail">
            <i class="gr__dot" :class="`is-${g.state}`" />
          </span>
          <div class="gr__main">
            <span class="gr__label">{{ g.label }}</span>
            <!--
              空槽（还没读到）与「读到了但没有」是**两件事**，界面上要分得清：
                todo     —— 淡虚线占位 + 「尚未读到」，表示还在等
                pending  —— 显示后端给的具体文案（如「未记录」），表示已经问过了
              混为一谈的话，用户分不清「它还没查」与「查了但没有」。
            -->
            <p v-if="g.state === 'todo'" class="gr__text gr__text--empty">
              尚未读到…
            </p>
            <p v-else class="gr__text">
              {{ g.text }}
              <span v-if="g.note" class="gr__note">{{ g.note }}</span>
              <span v-if="g.arrivedAt" class="gr__at mono">{{ clock(g.arrivedAt) }}</span>
            </p>
          </div>
          <span v-if="g.state !== 'todo'" class="gr__acts">
            <button type="button" @click.stop="$emit('act', g, 'source')">来源</button>
            <button type="button" @click.stop="$emit('act', g, 'edit')">改</button>
            <button type="button" @click.stop="$emit('act', g, 'remove')">删</button>
          </span>
        </div>
      </div>
    </section>

    <!--
      ── 推演所得 ──
      中栏的第二类内容，与「人物档案」语义分开（前者主语是收礼人，
      后者主语是这次推演）。这些是 search / verify / combine 各阶段
      **真实产生**的信息，逐步回流到这里 —— 这就是「随推演生长」的载体。
    -->
    <section v-if="findings.length" class="pc__section pc__findings">
      <h3 class="pc__sectitle">推演所得</h3>
      <div class="pc__rows">
        <div
          v-for="f in findings"
          :key="f.key"
          class="gr gr--finding"
          :class="{ 'gr--fresh': f.fresh }"
        >
          <span class="gr__rail"><i class="gr__dot is-derived" /></span>
          <div class="gr__main">
            <span class="gr__label">{{ f.label }}</span>
            <p class="gr__text">
              {{ f.text }}
              <span v-if="f.note" class="gr__note">{{ f.note }}</span>
              <span v-if="f.arrivedAt" class="gr__at mono">{{ clock(f.arrivedAt) }}</span>
            </p>
          </div>
        </div>
      </div>
    </section>

    <!-- 当前理解：签名式引文 -->
    <div v-if="understanding.text" class="pc__und">
      <span class="pc__undlabel">当前理解</span>
      <p class="pc__undtext">{{ understanding.text }}</p>
      <span class="pc__undfrom">{{ understanding.from }}</span>
    </div>

    <!-- 三态图例 -->
    <footer class="pc__legend">
      <span class="lg"><i class="gr__dot is-confirmed" />已确认</span>
      <span class="lg"><i class="gr__dot is-inferred" />推测</span>
      <span class="lg"><i class="gr__dot is-pending" />待确认</span>
      <span class="lg lg--hint">点任一信息 → 来源 · 修改 · 删除</span>
    </footer>
  </article>
</template>

<script setup>
/**
 * 中栏 · 人物信息档案卡（任务的情感锚点）
 *
 * 视觉上刻意走「人物小传」路线，而不是通用的「信息列表」：
 *   - 头像是带光环 + 关系绶带的焦点，不是占位圆圈
 *   - 侧写用「小标签 + 大正文」的编辑式排版，不再每行配一个通用图标
 *   - 「明确禁忌」单独成区、危险色包裹，与「了解她」明确分开
 *   - 「当前理解」做成签名式引文（展示字体），不是默认左条 callout
 * 功能钩子全部保留（gr / gr__dot / gr__label / gr__text / gr__acts / pc__undtext …），
 * 三态标记、hover 才显操作、随左栏更新的轻微脉冲也都沿用。
 */
import { computed } from 'vue'

const props = defineProps({
  head: { type: Object, required: true },
  task: { type: Object, required: true },
  groups: { type: Array, default: () => [] },
  understanding: { type: Object, default: () => ({ text: '', from: '' }) },
  /** 开场陈述（建 run 时下发一次） */
  opening: { type: Object, default: null },
  /** 推演所得：随 search/verify/combine 逐步到达 */
  findings: { type: Array, default: () => [] }
})

defineEmits(['act'])

const stateLabel = (s) => (s === 'inferred' ? '推测' : s === 'pending' ? '待确认' : '')

/**
 * 绘制进度：已确认组数 / 档案组总数。
 *
 * ⚠️ 分母用 props.groups 的长度（五组是固定 schema，从第一秒就在），
 * 不用「已到达的组数」—— 后者会让分母也一起涨，进度条永远满格，
 * 反而看不出「填了多满」。分子只算 confirmed：那是**真读到了**的，
 * 含 inferred/pending 会把「没有依据的推测」也算成已绘制。
 */
const totalGroups = computed(() => props.groups.length || 5)
const confirmedCount = computed(
  () => props.groups.filter((g) => g.state === 'confirmed').length
)

/** 到达时刻（时:分:秒）—— 「这一条是什么时候读到的」 */
const clock = (d) => {
  const t = d instanceof Date ? d : new Date(d)
  if (Number.isNaN(t.getTime())) return ''
  const p = (n) => String(n).padStart(2, '0')
  return `${p(t.getHours())}:${p(t.getMinutes())}:${p(t.getSeconds())}`
}

/* 关系绶带只取第一段，如「母亲 · 52 岁 · 同城」→「母亲」 */
const relationShort = computed(() => (props.head.meta || '').split(/[ ·]/)[0] || '')

/* 非禁忌组进「人物侧写」，禁忌组单独进「明确禁忌」区 */
const normalGroups = computed(() => props.groups.filter((g) => !g.danger))
const dangerGroups = computed(() => props.groups.filter((g) => g.danger))
</script>

<style lang="less" scoped>
.pc {
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--gift-accent-soft) 28%, var(--bg-surface)), var(--bg-surface) 132px);
  border: 1px solid var(--border);
  border-radius: 18px;
  box-shadow: 0 1px 2px rgba(18, 18, 28, 0.04), 0 18px 40px -28px rgba(18, 18, 28, 0.22);
  overflow: hidden;
}

/* 空槽：还没读到的组。淡虚线 + 更浅的字，明确区别于「读到了但没有」 */
.gr__text--empty {
  color: var(--text-faint);
  font-style: normal;
  opacity: 0.75;
}
/* 到达时刻：比正文更弱，是元信息 */
.gr__at {
  margin-left: 6px;
  font-size: 0.62rem;
  color: var(--text-faint);
}

/* ---- 抬头 ---- */
.pc__head {
  display: flex;
  gap: 16px;
  padding: 20px 20px 16px;
}
.pc__avatar {
  position: relative;
  flex: 0 0 auto;
  width: 84px;
  height: 84px;
  border-radius: 50%;
  background: radial-gradient(circle at 32% 26%, #fff 8%, var(--gift-accent-soft) 78%);
  display: grid;
  place-items: center;
  box-shadow: 0 0 0 4px var(--bg-surface), 0 0 0 5px var(--gift-accent-line);
}
.pc__initial {
  font-family: var(--font-display);
  font-size: 2rem;
  font-weight: 600;
  line-height: 1;
  color: var(--gift-accent);
}
.pc__ribbon {
  position: absolute;
  left: 50%;
  bottom: -7px;
  transform: translateX(-50%);
  white-space: nowrap;
  font-size: 0.6rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  padding: 2px 9px;
  border-radius: 99px;
  color: #fff;
  background: var(--gift-accent);
  box-shadow: 0 3px 8px -3px var(--gift-accent);
}

.pc__id { flex: 1; min-width: 0; padding-top: 2px; }
.pc__namerow {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.pc__name {
  font-family: var(--font-display);
  font-size: 1.34rem;
  font-weight: 600;
  color: var(--text-strong);
  margin: 0;
  letter-spacing: 0.01em;
}
.pc__complete {
  margin-left: auto;
  font-size: 0.62rem;
  padding: 2px 9px;
  border-radius: 99px;
  border: 1px solid var(--gift-accent-line);
  color: var(--gift-accent);
  white-space: nowrap;
  flex: 0 0 auto;
}
.pc__rel {
  font-size: 0.72rem;
  color: var(--text-faint);
  margin: 3px 0 0;
}
.pc__meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 5px 9px;
  margin-top: 12px;
}
.pc__metaItem {
  display: inline-flex;
  align-items: baseline;
  gap: 5px;
}
.pc__metaItem i {
  font-style: normal;
  font-size: 0.58rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--text-faint);
}
.pc__metaItem .pc__fv {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--text-strong);
}
.pc__metaSep { color: var(--text-faint); opacity: 0.5; }

/* ---- 分区 ---- */
.pc__section { padding: 2px 20px 0; }
.pc__sectspliter { display: none; }
.pc__sectitle {
  font-size: 0.6rem;
  font-weight: 600;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--text-faint);
  margin: 16px 0 4px;
}
.pc__sectitle--danger {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--chart-palette-4);
}
.pc__sectitle--danger svg { width: 13px; height: 13px; }

/* 禁忌区：危险色包裹，与侧写明确分开 */
.pc__avoid {
  margin: 6px 12px 0;
  padding: 10px 16px 8px;
  background: color-mix(in srgb, var(--chart-palette-4) 7%, var(--bg-surface));
  border: 1px solid color-mix(in srgb, var(--chart-palette-4) 24%, transparent);
  border-radius: 14px;
}
.pc__avoid .pc__sectitle--danger { margin-top: 4px; }

/* ---- 编辑式信息行：左轨状态点 + 小标签 + 大正文 ---- */
.pc__rows { display: flex; flex-direction: column; }
.gr {
  display: grid;
  grid-template-columns: 16px 1fr auto;
  align-items: start;
  gap: 11px;
  padding: 12px 14px;
  border-radius: 11px;
  cursor: pointer;
  transition: background-color 0.15s ease-out;
}
.gr:hover { background: var(--bg-base); }
.gr:focus-visible {
  outline: 2px solid var(--gift-accent);
  outline-offset: -2px;
}
.pc__avoid .gr { padding: 10px 12px; }
.pc__avoid .gr:hover { background: color-mix(in srgb, var(--chart-palette-4) 11%, transparent); }

/* 左轨状态点：实心 / 空心圈 / 灰虚线圈 */
.gr__rail { padding-top: 4px; display: flex; }
.gr__dot {
  flex: 0 0 auto;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  display: inline-block;
}
.gr__dot.is-confirmed { background: var(--gift-accent); }
.gr__dot.is-inferred { border: 1.5px solid var(--gift-accent); }
.gr__dot.is-pending { border: 1.5px dashed var(--text-faint); }

.gr__main { min-width: 0; }
.gr__label {
  display: block;
  font-size: 0.6rem;
  font-weight: 600;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--text-faint);
  margin-bottom: 3px;
}
.pc__avoid .gr__label { color: color-mix(in srgb, var(--chart-palette-4) 78%, var(--text)); }
.gr__text {
  font-size: 0.86rem;
  line-height: 1.55;
  color: var(--text-strong);
  margin: 0;
}
.gr__note { color: var(--text-faint); }

/* hover 才显操作，避免噪音 */
.gr__acts {
  display: flex;
  gap: 9px;
  align-items: center;
  opacity: 0;
  transform: translateX(3px);
  transition: opacity 0.15s ease-out, transform 0.15s ease-out;
}
.gr:hover .gr__acts,
.gr:focus-within .gr__acts { opacity: 1; transform: none; }
.gr__acts button {
  font-family: var(--font-body);
  font-size: 0.64rem;
  padding: 0;
  border: none;
  background: none;
  color: var(--text-faint);
  cursor: pointer;
}
.gr__acts button:hover { color: var(--gift-accent); }
.pc__avoid .gr__acts button:hover { color: var(--chart-palette-4); }

/* 随左栏更新时的唯一提示：一次轻微脉冲，不做重排 */
.gr--fresh { animation: gr-fresh 1.8s ease-out 2; }
@keyframes gr-fresh {
  0% { box-shadow: inset 0 0 0 0 color-mix(in srgb, var(--gift-accent) 50%, transparent); }
  100% { box-shadow: inset 0 0 0 12px transparent; }
}
@media (prefers-reduced-motion: reduce) {
  .gr--fresh { animation: none; }
}

/* 绘制进度：五格一条，逐格点亮。比抬头那个「档案完整 2/5」更醒目 ——
   它是这一版「从 0 绘制」的主视觉。 */
.pc__meter {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0 20px 4px;
  padding: 7px 10px;
  border-radius: 8px;
  background: var(--bg-sunken);
}
.pc__meter-label {
  flex: 0 0 auto;
  font-size: 0.68rem;
  color: var(--text-muted);
  b { margin-left: 3px; color: var(--text-strong); }
}
.pc__meter-cells {
  flex: 1 1 auto;
  display: flex;
  gap: 4px;
}
.pc__cell {
  flex: 1 1 0;
  height: 5px;
  border-radius: 3px;
  /* 空心 = 还没读到。它从一开始就在，让「总共要填几格」可见 */
  background: transparent;
  border: 1px dashed var(--border-strong);
  box-sizing: border-box;
  transition: background-color 0.35s ease-out, border-color 0.35s ease-out;
  &.on {
    background: var(--gift-accent);
    border: 1px solid var(--gift-accent);
  }
}
/* 全部点亮时整条变绿，给一个「填满了」的收束感 */
.pc__meter.is-complete {
  background: color-mix(in srgb, var(--gift-accent-soft) 55%, transparent);
  .pc__meter-label { color: var(--gift-accent); b { color: var(--gift-accent); } }
}
@media (prefers-reduced-motion: reduce) {
  .pc__cell { transition: none; }
}

/* 开场陈述：起点那句「我还不了解 TA」。比正文弱一档 —— 它是过渡语，
   不是结论；第一条真实信息到达后它就功成身退了。 */
.pc__opening {
  margin: 2px 20px 0;
  padding: 10px 12px;
  border-radius: 10px;
  background: color-mix(in srgb, var(--gift-accent-soft) 42%, transparent);
  font-size: 0.78rem;
  line-height: 1.6;
  color: var(--text);
}
.pc__opening-sub {
  display: block;
  margin-top: 3px;
  font-size: 0.72rem;
  color: var(--text-muted);
}

/* 推演所得：与人物侧写用同一套行样式，但点用「派生」态（空心蓝）区分 */
.gr--finding .gr__text { color: var(--text-muted); }
.gr__dot.is-derived {
  background: transparent;
  border: 1px solid var(--gift-accent);
  box-sizing: border-box;
}

/* ---- 当前理解：签名式引文 ---- */
.pc__und {
  margin: 16px 16px 4px;
  padding: 15px 17px 14px;
  border-radius: 14px;
  background: linear-gradient(135deg, var(--gift-accent-soft), #fff 120%);
  border: 1px solid var(--gift-accent-line);
}
.pc__undlabel {
  font-size: 0.58rem;
  font-weight: 600;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--gift-accent);
}
.pc__undtext {
  font-family: var(--font-display);
  font-size: 0.98rem;
  line-height: 1.72;
  color: var(--text-strong);
  margin: 8px 0 0;
}
.pc__undfrom {
  display: block;
  margin-top: 9px;
  font-size: 0.64rem;
  color: var(--text-faint);
}

/* ---- 图例 ---- */
.pc__legend {
  display: flex;
  align-items: center;
  gap: 13px;
  padding: 4px 20px 16px;
  font-size: 0.66rem;
  color: var(--text-faint);
}
.lg { display: inline-flex; align-items: center; gap: 5px; }
.lg--hint { margin-left: auto; }
</style>
