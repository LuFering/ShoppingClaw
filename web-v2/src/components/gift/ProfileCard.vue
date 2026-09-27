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
      档案条数 —— 「从 0 开始记」的可见载体
      ═══════════════════════════════════════════════════════════════
      用户的原话：「没有那种让我感觉到 agent 正在从 0 绘制个人档案的感觉」，
      以及「执行流一开始就写完了近半的档案，后续很长时间不再输入」。

      前者是节奏问题，后者是**结构**问题 —— 档案原本是「固定 5 组、
      每组一条」，而 5 组的数据全来自开头那两次查询，所以 7% 处就写完了
      （实测：164 条事件里 profile 全在第 8~12 条），分母也就固定是 5。

      现在档案是开放式条目列表，agent 每执行一步都可能写入，可增可改可删。
      所以这里显示**真实条数**，不再是 N/5：

        ⚠️ 旧的「N/5」在骨架拆掉后就是**假数字** —— agent 写到第 6 条时
        分母还是 5，自建新栏时它也不会变。分母是架构决定的，架构变了就得删。

      条数为 0 时显示「档案 0 条」而不是空白 —— 0 是这次推演的真实起点。
    -->
    <div class="pc__meter">
      <span class="pc__meter-label">
        档案
        <b class="mono">{{ entries.length }}</b> 条
      </span>
      <span class="pc__meter-live" v-if="freshRail">
        正在写入「{{ freshRail }}」…
      </span>
    </div>

    <!-- 人物侧写：按栏分组，每栏可有多条 -->
    <section v-if="normalRails.length" class="pc__section">
      <h3 class="pc__sectitle">人物侧写</h3>
      <div class="pc__rows">
        <template v-for="rail in normalRails" :key="rail.rail">
          <div class="pc__railtitle">
            <span class="pc__railname">{{ rail.rail }}</span>
            <span class="pc__railn mono">{{ rail.items.length }}</span>
          </div>
          <div
            v-for="it in rail.items"
            :key="it.id"
            class="gr"
            :class="{ 'gr--fresh': it.fresh }"
            role="button"
            tabindex="0"
            :aria-label="`${it.text}，来自 ${it.source}，可展开依据与操作`"
            @click="$emit('act', it, 'open')"
            @keydown.enter.prevent="$emit('act', it, 'open')"
          >
            <span class="gr__rail">
              <i class="gr__dot" :class="`is-${it.state || 'confirmed'}`" />
            </span>
            <div class="gr__main">
              <p class="gr__text">
                {{ it.text }}
                <span v-if="it.arrivedAt" class="gr__at mono">{{ clock(it.arrivedAt) }}</span>
              </p>
              <!--
                依据：每一条都带 `because`（后端强制），指回它来自哪次真实
                结果。这是「可核对」的落点 —— 没有依据的条目不该存在，
                所以有就显示、不是可选装饰。
              -->
              <p v-if="it.because" class="gr__because">依据 · {{ it.because }}</p>
            </div>
            <span class="gr__acts">
              <button type="button" @click.stop="$emit('act', it, 'source')">来源</button>
              <button type="button" @click.stop="$emit('act', it, 'revise')">改</button>
            </span>
          </div>
        </template>
      </div>
    </section>

    <!-- 档案还是空的：如实说明它在等什么，不预置空槽 -->
    <p v-else class="pc__empty">
      还没有记下任何信息。每查一步，它会把关于 TA 的要点写进这里。
    </p>

    <!--
      禁忌：独立成区，危险色包裹，不与侧写混排。
      ⚠️ 判据是**栏名里带「禁忌/忌语/不能/过敏」**（见 data/giftProfile 的
      isDangerRail），不是查死表 —— 模型自建「海鲜过敏」这类栏时也该进这里，
      否则最要命的信息会被当普通条目渲染。
    -->
    <section v-if="dangerRails.length" class="pc__section pc__avoid">
      <h3 class="pc__sectitle pc__sectitle--danger">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4">
          <path d="M8 1.8 14.4 13.5H1.6L8 1.8Z" /><path d="M8 6.4v3.1" /><circle cx="8" cy="11.4" r="0.5" fill="currentColor" stroke="none" />
        </svg>
        {{ dangerRails.map((r) => r.rail).join(' · ') }}
      </h3>
      <div class="pc__rows">
        <template v-for="rail in dangerRails" :key="rail.rail">
          <div
            v-for="it in rail.items"
            :key="it.id"
            class="gr gr--danger"
            :class="{ 'gr--fresh': it.fresh }"
            role="button"
            tabindex="0"
            :aria-label="`${it.text}，来自 ${it.source}，可展开依据与操作`"
            @click="$emit('act', it, 'open')"
            @keydown.enter.prevent="$emit('act', it, 'open')"
          >
            <span class="gr__rail"><i class="gr__dot" :class="`is-${it.state || 'confirmed'}`" /></span>
            <div class="gr__main">
              <p class="gr__text">
                {{ it.text }}
                <span v-if="it.arrivedAt" class="gr__at mono">{{ clock(it.arrivedAt) }}</span>
              </p>
              <p v-if="it.because" class="gr__because">依据 · {{ it.because }}</p>
            </div>
            <span class="gr__acts">
              <button type="button" @click.stop="$emit('act', it, 'source')">来源</button>
              <button type="button" @click.stop="$emit('act', it, 'revise')">改</button>
            </span>
          </div>
        </template>
      </div>
    </section>

    <!--
      「推演所得」区已并入上面的栏 —— 这次的检索 / 比价 / 组合结论现在由
      agent 用 write_profile 写进「行情锚点」「这盒的取舍」「这盒怎么搭」，
      带 because 依据。独立一块的意义没了：同一份信息出现两次，
      而且旧的那份**没有依据**（代码自动派生，曾被实测误把「我们搜的品类词」
      当成「她的喜好」）。
    -->

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
// 禁忌栏的判据（按栏名文字，不是查死表）—— 用**函数**判断而不是查表，
// 因为它对「海鲜过敏」这类模型自建的栏名也必须成立。
import { isDangerRail } from '@/data/giftProfile'

const props = defineProps({
  head: { type: Object, required: true },
  task: { type: Object, required: true },
  /** 档案条目（扁平列表，每条 {id, rail, text, because, source}） */
  entries: { type: Array, default: () => [] },
  understanding: { type: Object, default: () => ({ text: '', from: '' }) },
  /** 开场陈述（建 run 时下发一次） */
  opening: { type: Object, default: null }
})

defineEmits(['act'])

const stateLabel = (s) => (s === 'inferred' ? '推测' : s === 'pending' ? '待确认' : '')

/**
 * 按栏分组 —— 保持栏目首次出现的顺序（后端写入的顺序即推演顺序）。
 *
 * ⚠️ 分组在这里做而不是后端做：后端推的是差集（add/update/drop），
 * 分组是纯展示。后端也有一份 `group_by_rail`，那是给**模型**看的
 * （工具回显当前档案），两者用途不同、不必共用。
 */
const rails = computed(() => {
  const order = []
  const map = new Map()
  for (const it of props.entries) {
    const r = it.rail || '其他'
    if (!map.has(r)) { map.set(r, []); order.push(r) }
    map.get(r).push(it)
  }
  return order.map((r) => ({ rail: r, items: map.get(r) }))
})

/** 禁忌类单独成区（判据是栏名文字，见 data/giftProfile 的 isDangerRail） */
const dangerRails = computed(() => rails.value.filter((r) => isDangerRail(r.rail)))
const normalRails = computed(() => rails.value.filter((r) => !isDangerRail(r.rail)))

/** 最近写入的那一栏 —— 头部显示「正在写入「X」…」，让生长可见 */
const freshRail = computed(() => {
  const hit = props.entries.find((x) => x.fresh)
  return hit ? hit.rail : ''
})

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
/* 栏标题：小字 + 条数，比条目本身弱 —— 它是分组不是内容 */
.pc__railtitle {
  display: flex;
  align-items: baseline;
  gap: 7px;
  margin: 10px 0 3px;
  &:first-child { margin-top: 0; }
}
.pc__railname {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-muted);
  letter-spacing: 0.02em;
}
.pc__railn { font-size: 0.64rem; color: var(--text-faint); }

/* 依据：每条都带，指回真实来源。弱于正文但**不隐藏** —— 它是可核对的落点 */
.gr__because {
  margin: 2px 0 0;
  font-size: 0.66rem;
  line-height: 1.5;
  color: var(--text-faint);
}
/* 档案还是空的 */
.pc__empty {
  margin: 6px 0 0;
  font-size: 0.74rem;
  line-height: 1.7;
  color: var(--text-faint);
}

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

/* 档案条数：从 0 开始记。比抬头更醒目 —— 它是这次「持续生长」的主视觉。
   旧的五格进度条已删：分母 5 是固定骨架决定的，骨架拆掉后它就是假数字。 */
.pc__meter {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin: 2px 0 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border);
}
.pc__meter-label {
  font-size: 0.72rem;
  color: var(--text-muted);
  b { color: var(--text-strong); font-size: 0.86rem; }
}
/* 正在写入哪一栏 —— 生长感来自这个会跳的名字 */
.pc__meter-live {
  margin-left: auto;
  font-size: 0.68rem;
  color: var(--gift-accent);
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
