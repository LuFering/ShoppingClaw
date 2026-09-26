<template>
  <div class="dp">
    <header class="dp-head">
      <span class="dp-title">交付区</span>
      <span class="dp-sub mono">{{ readyCount }} / {{ items.length }} 已生成</span>
    </header>

    <div class="dp-scroll">
      <!--
        每份交付物**就地渲染正文**，而不是只列一个文件名 + 预览按钮。
        之前点「预览」弹出一段「决策图节点」的罗列，三份内容还完全一样 ——
        等于没有交付物。现在内容随事件下发（data），这里直接渲染。
      -->
      <section
        v-for="d in items"
        :key="d.id"
        class="dc"
        :class="[`is-${d.state}`, { 'is-open': openId === d.id }]"
      >
        <button class="dc-head" type="button" @click="toggle(d)">
          <span class="dc-name">{{ d.name }}</span>
          <span class="dc-state mono" :class="`is-${d.state}`">{{ stateLabel(d) }}</span>
          <ChevronDown :size="13" class="dc-chevron" :class="{ open: openId === d.id }" />
        </button>
        <p class="dc-meta">{{ d.meta }}</p>

        <!-- 生成中：骨架条，不转圈 -->
        <div v-if="d.state === 'running'" class="sk">
          <span class="sk-bar" style="width: 72%" />
          <span class="sk-bar" style="width: 48%" />
        </div>

        <!-- 正文只在展开时渲染 —— 收起时留一个紧凑摘要，三份都收起也能扫到重点 -->
        <template v-else-if="d.state === 'ready' && d.data">
          <p v-if="openId !== d.id" class="dc-brief">{{ brief(d) }}</p>
          <div v-show="openId === d.id" class="dc-body">
            <!-- ── 采购方案：买哪件 + 为什么 + 排除原因 ── -->
            <template v-if="d.data.kind === 'plan'">
              <!--
                ⚠️ 2026-09-27：从「一件」改成「一套」。
                原先只渲染 d.data.pick 一件，因为后端 make_decision 只收单件。
                实测「搬家 / 预算 12000」：模型算了整套 5 件 ¥11163，却只能
                交出一张床 —— 卡片上「占 28%」和它自己写的「占 93%」差 3 倍。
                现在后端给的是 picks 列表（按品类），这里逐件渲染。
              -->
              <div v-if="picks(d).length" class="picks">
                <div v-for="(p, i) in picks(d)" :key="i" class="pick">
                  <p class="pick-name">
                    <span v-if="p.category" class="pick-cat">{{ p.category }}</span>
                    {{ p.name }}
                  </p>
                  <p class="pick-line">
                    <span v-if="p.price != null" class="pick-price mono">¥{{ fmtPrice(p.price) }}</span>
                    <!--
                      只在**算式成立**时才写「单价 × 用量 = 小计」。
                      模型可以给一个与单价×用量不符的小计（它可能知道优惠），
                      那时把它写成等式就是在编一个不成立的算术 —— 分开列。
                    -->
                    <span v-if="isProduct(p)" class="pick-qty mono">
                      × {{ p.quantity }} = ¥{{ fmtPrice(p.subtotal) }}
                    </span>
                    <span v-else-if="p.subtotal != null && p.subtotal !== p.price" class="pick-qty mono">
                      小计 ¥{{ fmtPrice(p.subtotal) }}
                    </span>
                    <span class="pick-by" :class="`by-${p.by}`">
                      {{ BY_LABEL[p.by] || '来源未知' }}
                    </span>
                  </p>
                  <p v-if="p.why" class="pick-why">{{ p.why }}</p>
                  <p v-else-if="p.quantity_basis" class="pick-why">{{ p.quantity_basis }}</p>
                </div>
                <p v-if="d.data.total != null" class="picks-total">
                  整套合计 <span class="mono">¥{{ fmtPrice(d.data.total) }}</span>
                </p>
              </div>
              <div v-else class="pick">
                <p class="pick-name">（未选出）</p>
              </div>

              <!-- 整套的取舍逻辑：为什么这么搭配、总账怎么算 -->
              <p v-if="d.data.why" class="pick-why overall">{{ d.data.why }}</p>

              <dl v-if="facts(d).length" class="facts">
                <template v-for="f in facts(d)" :key="f.k">
                  <dt>{{ f.k }}</dt>
                  <dd>{{ f.v }}</dd>
                </template>
              </dl>

              <div v-if="d.data.alternatives?.length" class="blk">
                <p class="blk-title">备选（同品类）</p>
                <ul class="alts">
                  <li v-for="a in d.data.alternatives" :key="a.category + a.name">
                    <span class="alts-n">
                      <span v-if="a.category" class="alts-cat">{{ a.category }}</span>{{ a.name }}
                    </span>
                    <span v-if="a.price != null" class="alts-p mono">¥{{ fmtPrice(a.price) }}</span>
                  </li>
                </ul>
              </div>

              <div v-if="d.data.excluded?.length" class="blk">
                <p class="blk-title">已排除 {{ d.data.excluded.length }} 件</p>
                <ul class="outs">
                  <li v-for="(e, i) in d.data.excluded" :key="i">
                    <span class="outs-n">{{ e.name }}</span>
                    <span class="outs-w">{{ e.reason || '不满足硬约束' }}</span>
                  </li>
                </ul>
              </div>

              <div v-if="d.data.risks?.length" class="blk">
                <p class="blk-title">待确认</p>
                <ul class="risks">
                  <li v-for="(r, i) in d.data.risks" :key="i">{{ r }}</li>
                </ul>
              </div>
            </template>

            <!-- ── 候选对比表：入选与排除同表，按品类分组 ── -->
            <template v-else-if="d.data.kind === 'compare'">
              <div v-for="g in groups(d)" :key="g.category" class="cmp-grp">
                <p v-if="g.category" class="cmp-cat">{{ g.category }}</p>
                <table class="cmp">
                  <thead>
                    <tr><th>候选</th><th class="num">价格</th><th>结论</th></tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="(r, i) in g.rows"
                      :key="i"
                      :class="{ 'is-picked': r.picked, 'is-out': r.tag === '排除' }"
                    >
                      <td class="cmp-n">
                        {{ r.name }}
                        <span v-if="r.reason" class="cmp-why">{{ r.reason }}</span>
                      </td>
                      <td class="num mono">{{ r.price != null ? '¥' + fmtPrice(r.price) : '—' }}</td>
                      <td>
                        <span class="tag" :class="tagClass(r.tag)">{{ r.tag }}</span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <p class="cmp-sum">
                共 {{ d.data.counts?.candidates || 0 }} 个候选，
                排除 {{ d.data.counts?.excluded || 0 }} 个<template
                  v-if="d.data.counts?.picked">，入选 {{ d.data.counts.picked }} 件</template>
              </p>
            </template>

            <!-- ── 预算分配表：花多少 / 占几成 / 剩多少 ── -->
            <template v-else-if="d.data.kind === 'budget'">
              <!--
                ⚠️ 口径决定怎么显示（见后端 build_budget_doc 的说明）：
                  caliber='total'     模型估了用量 → 显示估算总价 + 占比
                  caliber='unit_only' 只有单价 → **如实标「单价」**，不给占比
                早先不分口径，直接拿单价当花费，6 万的预算显示成
                「花费 ¥165.64 · 占 0.3%」—— 算术没错但口径是错的，
                用户看到的「6万只花几百」就是这么来的。
              -->
              <template v-if="d.data.caliber === 'total'">
                <div class="bud">
                  <div class="bud-nums">
                    <span class="bud-spent mono">¥{{ fmtPrice(d.data.spent) }}</span>
                    <span v-if="d.data.budget" class="bud-of">/ 预算 ¥{{ fmtPrice(d.data.budget) }}</span>
                  </div>
                  <div v-if="d.data.ratio != null" class="bud-bar">
                    <i :style="{ width: Math.min(100, Math.round(d.data.ratio * 100)) + '%' }" />
                  </div>
                  <p class="bud-line">
                    <span v-if="d.data.ratio != null">占预算 {{ Math.round(d.data.ratio * 100) }}%</span>
                    <span v-if="d.data.remaining != null">· 结余 ¥{{ fmtPrice(d.data.remaining) }}</span>
                  </p>

                  <!--
                    按品类拆账 —— 用户想知道「钱花在哪一类上了」。
                    买一套时这一行就是「整套」的构成，单件时只有一行。
                  -->
                  <ul v-if="d.data.items?.length > 1" class="bud-items">
                    <li v-for="(it, i) in d.data.items" :key="i">
                      <span class="bud-cat">{{ it.category }}</span>
                      <span class="bud-iname">{{ it.name }}</span>
                      <span class="bud-isum mono">
                        <template v-if="isProduct(it)">
                          ¥{{ fmtPrice(it.unit_price) }} × {{ it.quantity }} =
                        </template>
                        <template v-else-if="it.subtotal == null">小计待估</template>
                        ¥{{ it.subtotal != null ? fmtPrice(it.subtotal) : '—' }}
                      </span>
                    </li>
                  </ul>

                  <p v-if="d.data.quantity" class="bud-basis">
                    用量约 {{ d.data.quantity }} 份<span v-if="d.data.quantity_basis"> · {{ d.data.quantity_basis }}</span>
                  </p>
                  <!-- 有任一件缺小计 → 总额是缺的，如实说，不假装算全了 -->
                  <p v-if="d.data.partial" class="bud-note">
                    有商品未估出用量，<em>合计未含</em>那一部分 —— 不是最终总额。
                  </p>
                </div>
              </template>

              <template v-else-if="d.data.caliber === 'unit_only'">
                <div class="bud">
                  <div class="bud-nums">
                    <span class="bud-spent mono">¥{{ fmtPrice(d.data.unit_price) }}</span>
                    <span class="bud-of">选中商品单价</span>
                  </div>
                  <p class="bud-note">
                    未含用量估算 —— 这是<em>单价</em>，不是整件事的总花费。
                    <span v-if="d.data.quantity_basis">{{ d.data.quantity_basis }}</span>
                  </p>
                  <p v-if="d.data.budget" class="bud-line">
                    预算 ¥{{ fmtPrice(d.data.budget) }}（需知道用量才能算占用）
                  </p>
                </div>
              </template>

              <p v-else class="bud-note">这次没有选出商品，无法计算花费。</p>

              <p v-if="d.data.range" class="bud-range mono">
                候选价格区间 ¥{{ fmtPrice(d.data.range.min) }} – ¥{{ fmtPrice(d.data.range.max) }}
              </p>
            </template>
          </div>

          <div v-show="openId === d.id" class="dc-actions">
            <button class="dp-btn" type="button" @click="$emit('download', d)">下载 Markdown</button>
          </div>
        </template>

        <p v-else-if="d.state === 'empty'" class="dc-empty">
          这次推演没留下足够数据生成这一份 —— 不是失败，是确实没有内容。
        </p>
        <p v-else-if="d.state === 'waiting'" class="dc-empty dim">等待上游步骤产出</p>
      </section>

      <!--
        agent 停下来等拍板的问题，固定在这里而不是混进左栏执行流。
        放在列表**之后**：它是当前最需要动作的东西，视线自然落到底部。
      -->
      <div v-if="question" class="dp-ask">
        <p class="dp-ask-k">需要你拍板</p>
        <p class="dp-ask-text">{{ question.text }}</p>
        <div class="dp-actions">
          <button
            v-for="opt in question.options"
            :key="opt.key"
            class="dp-btn"
            :class="{ primary: opt.primary }"
            type="button"
            @click="$emit('answer', opt.key)"
          >{{ opt.label }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * 右栏 · 交付区。
 *
 * ═══════════════════════════════════════════════════════════════════
 * 2026-09-25 重写：从「文件清单」变成「可读的结论」
 * ═══════════════════════════════════════════════════════════════════
 *
 * 之前每一项只有「名字 + 一句 meta + 预览/下载按钮」，正文要另开弹窗，
 * 而弹窗里是同一段「决策图节点」的罗列 —— 三份交付物内容完全一样。
 * 用户评价「很简陋」，准确。
 *
 * 现在每份就地渲染它**自己的**结构化内容：
 *   d-plan    买哪件 + 理由 + 备选 + 已排除及原因 + 待确认风险
 *   d-compare 逐行横比表，入选与排除同表（否则看不出取舍）
 *   d-budget  花了多少 / 占预算几成 / 结余 / 候选价格区间
 *
 * 内容由后端在收尾时算好、随 deliverable 事件下发（payload.data），
 * 前端只负责渲染，不在浏览器里重算一遍业务。
 *
 * 默认展开第一份：交付物是这一栏的主角，藏起来要多点一次才看得到。
 */
import { ref, computed, watch } from 'vue'
import { ChevronDown } from 'lucide-vue-next'

const props = defineProps({
  items: { type: Array, default: () => [] },
  question: { type: Object, default: null }
})

defineEmits(['download', 'answer'])

const BY_LABEL = {
  llm: '模型判断',
  kb: '知识库命中',
  rule: '规则兜底'
}

const openId = ref('')
// 用户手动点过之后就不再自动切换 —— 否则每次数据更新都会把他正在看的那份顶掉
const userToggled = ref(false)

// 首屏/刷新后自动展开**采购方案**（d-plan）—— 它是结论本身，
// 另外两份是支撑材料。
//
// ⚠️ 不能只「取第一份 ready」：刷新时三份是并发取回的（Promise.all），
// 谁先 resolve 不确定，实测会停在预算分配表上，等于把最该先看的藏起来了。
// 所以在用户动手之前，一直朝 d-plan 收敛。
watch(
  () => props.items,
  (list) => {
    if (userToggled.value) return
    const plan = list.find((d) => d.id === 'd-plan' && d.state === 'ready')
    if (plan) { openId.value = plan.id; return }
    // 方案还没好，先展开任何一份已生成的，别让右栏空着
    const any = list.find((d) => d.state === 'ready')
    if (any && !openId.value) openId.value = any.id
  },
  { immediate: true, deep: true }
)

const toggle = (d) => {
  userToggled.value = true
  openId.value = openId.value === d.id ? '' : d.id
}

const readyCount = computed(() => props.items.filter((d) => d.state === 'ready').length)

const stateLabel = (d) => ({
  ready: '已生成',
  running: Math.round((d.progress || 0) * 100) + '%',
  empty: '无内容',
  waiting: '待生成'
}[d.state] || d.state)

const tagClass = (tag) => ({
  'tag-in': tag === '入选',
  'tag-out': tag === '排除',
  'tag-cand': tag === '候选'
}[tag] || 'tag-cand')

/** 价格可能是小数（元），整数就不显示小数点 */
const fmtPrice = (v) => {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return Number.isInteger(n) ? String(n) : n.toFixed(2)
}

/**
 * 这一项的「单价 × 用量 = 小计」是不是一个**成立的**算式。
 *
 * 模型可以给一个与单价×用量不符的小计（它可能知道我们不知道的，比如套装
 * 优惠）—— 那时把它写成等式就是在编一个不成立的算术。宁可分开列。
 * 实测一次运行里衣柜单价 ¥691.58、小计 ¥686.23，写等式就是错的。
 */
const isProduct = (it) => {
  // picks 里叫 price，预算明细里叫 unit_price —— 两个字段名都认
  const u = Number(it?.unit_price ?? it?.price)
  const q = Number(it?.quantity)
  const s = Number(it?.subtotal)
  if (!Number.isFinite(u) || !Number.isFinite(q) || !Number.isFinite(s)) return false
  if (!(q > 0)) return false
  return Math.abs(u * q - s) < 0.01
}

/** 采购方案顶部的事实行：只放真有值的，不铺空占位 */
const facts = (d) => {
  const x = d.data || {}
  const out = []
  if (x.subject) out.push({ k: '采购对象', v: x.subject })
  if (x.budget) out.push({ k: '预算', v: x.budget })
  if (x.duration) out.push({ k: '周期', v: x.duration })
  if (x.constraints?.length) out.push({ k: '硬约束', v: x.constraints.join('、') })
  return out
}

/**
 * 这次买下的商品列表。
 *
 * ⚠️ 优先读 `picks`（后端 2026-09-27 起给的是整套）。
 * 旧的单件形状（`pick`）仍然兼容 —— 历史事件回放里是那个形状。
 */
const picks = (d) => {
  const x = d.data || {}
  if (x.picks?.length) return x.picks
  return x.pick ? [x.pick] : []
}

/**
 * 对比表的分组。
 *
 * ⚠️ 优先读 `groups`（按品类分组）。旧的拍平 `rows` 兜底 ——
 * 历史事件里没有 groups，不兜底会让旧 run 的表整张空掉。
 */
const groups = (d) => {
  const x = d.data || {}
  if (x.groups?.length) return x.groups
  return x.rows?.length ? [{ category: '', rows: x.rows }] : []
}

/** 收起时的一行摘要 —— 三份都收起也要能扫到各自的结论 */
const brief = (d) => {
  const x = d.data || {}
  if (x.kind === 'plan') {
    const ps = picks(d)
    if (!ps.length) return '未选出'
    if (ps.length === 1) {
      const p = ps[0]
      return `${p.name}${p.price != null ? `　¥${fmtPrice(p.price)}` : ''}`
    }
    // 买一套时，逐个列名字太长 —— 报件数 + 总价才是结论
    const total = x.total != null ? `　¥${fmtPrice(x.total)}` : ''
    return `${ps.length} 件：${ps.map((p) => p.category || p.name.slice(0, 6)).join('、')}${total}`
  }
  if (x.kind === 'compare') {
    const c = x.counts || {}
    const picked = c.picked ? `，入选 ${c.picked} 件` : ''
    return `${c.candidates || 0} 个候选，排除 ${c.excluded || 0} 个${picked}`
  }
  if (x.kind === 'budget') {
    // 口径不同，摘要也不同 —— 单价不能伪装成总花费
    if (x.caliber === 'total') {
      const parts = [`估算 ¥${fmtPrice(x.spent)}`]
      if (x.ratio != null) parts.push(`占 ${Math.round(x.ratio * 100)}%`)
      if (x.remaining != null) parts.push(`结余 ¥${fmtPrice(x.remaining)}`)
      return parts.join(' · ')
    }
    if (x.caliber === 'unit_only') return `单价 ¥${fmtPrice(x.unit_price)}（未含用量）`
    return '未选出商品'
  }
  return ''
}
</script>

<style lang="less" scoped>
.dp {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
}

.dp-head {
  flex: 0 0 auto;
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 0 0 10px;
  border-bottom: 1px solid var(--border);
}
.dp-title {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--text-strong);
}
.dp-sub {
  margin-left: auto;
  font-size: 0.7rem;
  color: var(--text-muted);
}

.dp-scroll {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* ── 单份交付物 ── */
.dc {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-surface);
  overflow: hidden;
  transition: border-color 0.15s ease-out;
  &.is-open { border-color: var(--border-strong); }
  &.is-empty { opacity: 0.85; }
}
.dc-head {
  display: flex;
  align-items: center;
  gap: 7px;
  width: 100%;
  padding: 8px 10px 0;
  border: none;
  background: transparent;
  font-family: var(--font-body);
  text-align: left;
  cursor: pointer;
}
.dc-name {
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--text-strong);
}
.dc-state {
  margin-left: auto;
  font-size: 0.66rem;
  &.is-ready { color: var(--pos); }
  &.is-running { color: var(--info); }
  &.is-empty { color: var(--warn); }
  &.is-waiting { color: var(--text-faint); }
}
.dc-chevron {
  flex: 0 0 auto;
  color: var(--text-faint);
  transition: transform 0.15s ease-out;
  &.open { transform: rotate(180deg); }
}
.dc-meta {
  margin: 2px 0 0;
  padding: 0 10px;
  font-size: 0.68rem;
  line-height: 1.5;
  color: var(--text-muted);
}
/* 收起时的一行摘要：比 meta 更实，是这份交付物的结论本身 */
.dc-brief {
  margin: 6px 0 0;
  padding: 0 10px 10px;
  font-size: 0.73rem;
  line-height: 1.5;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dc-body {
  padding: 9px 10px 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.dc-actions {
  padding: 9px 10px 10px;
}
.dc-empty {
  margin: 8px 0 0;
  padding: 0 10px 10px;
  font-size: 0.7rem;
  line-height: 1.55;
  color: var(--text-muted);
  &.dim { color: var(--text-faint); }
}

/* 生成中骨架 */
.sk {
  padding: 4px 10px 10px;
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.sk-bar {
  height: 7px;
  border-radius: 3px;
  background: var(--bg-sunken);
  animation: sk-pulse 1.4s ease-in-out infinite;
}
@keyframes sk-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.45; }
}
@media (prefers-reduced-motion: reduce) {
  .sk-bar { animation: none; }
}

/* ── 采购方案 ── */
/* 买一套时每件一个小节，用左边框串起来 —— 单件时视觉与从前一致 */
.picks {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.pick {
  border-left: 2px solid var(--accent-solid);
  padding-left: 9px;
}
/* 品类标签：买一套时先看品类再看商品名 */
.pick-cat {
  display: inline-block;
  margin-right: 5px;
  padding: 0 5px;
  border-radius: 3px;
  background: var(--bg-sunken);
  color: var(--text-muted);
  font-size: 0.64rem;
  font-weight: 400;
  vertical-align: 1px;
}
/* 整套合计：所有小计的和，比单件更重 */
.picks-total {
  margin: 2px 0 0;
  padding-top: 6px;
  border-top: 1px solid var(--border);
  font-size: 0.74rem;
  color: var(--text-strong);
  text-align: right;
}
.pick-name {
  margin: 0;
  font-size: 0.8rem;
  font-weight: 600;
  line-height: 1.45;
  color: var(--text-strong);
}
.pick-line {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 7px;
  margin: 4px 0 0;
}
.pick-price {
  font-size: 0.78rem;
  color: var(--accent-700);
}
/* 单价 × 用量 = 小计 —— 让「怎么算出来的」一眼可核 */
.pick-qty {
  font-size: 0.7rem;
  color: var(--text-muted);
}
/* 来源标记：与左栏执行流同一套语言 */
.pick-by {
  font-size: 0.62rem;
  padding: 1px 5px;
  border-radius: 4px;
  &.by-llm { color: var(--text-faint); }
  &.by-kb { color: var(--text-muted); }
  &.by-rule { color: var(--warn); background: var(--bg-sunken); }
}
.pick-why {
  margin: 0;
  font-size: 0.72rem;
  line-height: 1.6;
  color: var(--text-muted);
  /* 整套的取舍逻辑：与单件理由区分开，它是更高一层的说明 */
  &.overall {
    padding-left: 9px;
    border-left: 2px solid var(--border-strong);
  }
}

.facts {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 2px 10px;
  margin: 0;
  font-size: 0.7rem;
  dt { color: var(--text-faint); }
  dd { margin: 0; color: var(--text); }
}

.blk-title {
  margin: 0 0 4px;
  font-size: 0.68rem;
  color: var(--text-faint);
}

.alts, .outs, .risks {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
  font-size: 0.71rem;
  line-height: 1.5;
}
.alts li {
  display: flex;
  gap: 8px;
}
.alts-n {
  color: var(--text-muted);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.alts-cat {
  display: inline-block;
  margin-right: 4px;
  padding: 0 4px;
  border-radius: 3px;
  background: var(--bg-sunken);
  color: var(--text-faint);
  font-size: 0.62rem;
}
.alts-p { margin-left: auto; color: var(--text-faint); }

.outs li {
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.outs-n {
  color: var(--text-faint);
  text-decoration: line-through;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.outs-w { color: var(--warn); }

.risks li {
  color: var(--text-muted);
  padding-left: 10px;
  position: relative;
  &::before {
    content: '·';
    position: absolute;
    left: 2px;
    color: var(--warn);
  }
}

/* ── 候选对比表 ── */
/* 按品类分组：一组一张表。买一套时 40 行平铺看不出「床这一项比了什么」 */
.cmp-grp {
  display: flex;
  flex-direction: column;
  gap: 4px;
  & + .cmp-grp { margin-top: 10px; }
}
.cmp-cat {
  margin: 0;
  font-size: 0.68rem;
  font-weight: 600;
  color: var(--text-strong);
  padding-bottom: 3px;
  border-bottom: 1px solid var(--border-strong);
}
.cmp {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.7rem;
  th {
    text-align: left;
    font-weight: 400;
    color: var(--text-faint);
    padding: 0 4px 4px;
    border-bottom: 1px solid var(--border);
    &.num { text-align: right; }
  }
  td {
    padding: 5px 4px;
    border-bottom: 1px solid var(--border);
    vertical-align: top;
    color: var(--text);
    &.num { text-align: right; white-space: nowrap; }
  }
  tr.is-picked td { background: var(--accent-50); }
  tr.is-out .cmp-n { color: var(--text-faint); text-decoration: line-through; }
}
.cmp-n {
  max-width: 0;
  width: 60%;
  overflow: hidden;
  text-overflow: ellipsis;
}
.cmp-why {
  display: block;
  margin-top: 2px;
  font-size: 0.66rem;
  line-height: 1.45;
  color: var(--text-faint);
  text-decoration: none;
  white-space: normal;
}
tr.is-picked .cmp-why { color: var(--text-muted); }
.cmp-sum {
  margin: 0;
  font-size: 0.68rem;
  color: var(--text-faint);
}
.tag {
  font-size: 0.64rem;
  padding: 1px 5px;
  border-radius: 4px;
  white-space: nowrap;
  &.tag-in { color: var(--pos); background: var(--bg-sunken); }
  &.tag-out { color: var(--text-faint); background: var(--bg-sunken); }
  &.tag-cand { color: var(--text-muted); }
}

/* ── 预算分配表 ── */
.bud-nums {
  display: flex;
  align-items: baseline;
  gap: 6px;
}
.bud-spent {
  font-size: 0.92rem;
  font-weight: 600;
  color: var(--text-strong);
}
.bud-of {
  font-size: 0.7rem;
  color: var(--text-muted);
}
.bud-bar {
  margin-top: 6px;
  height: 6px;
  border-radius: 3px;
  background: var(--bg-sunken);
  overflow: hidden;
  i {
    display: block;
    height: 100%;
    border-radius: 3px;
    background: var(--accent-solid);
    transition: width 0.3s ease-out;
  }
}
.bud-line {
  margin: 5px 0 0;
  font-size: 0.7rem;
  color: var(--text-muted);
}
/* 按品类拆账 —— 钱花在哪一类上 */
.bud-items {
  list-style: none;
  margin: 7px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 0.69rem;
  li {
    display: flex;
    align-items: baseline;
    gap: 6px;
    padding-top: 4px;
    border-top: 1px solid var(--border);
  }
}
.bud-cat {
  flex: 0 0 auto;
  padding: 0 5px;
  border-radius: 3px;
  background: var(--bg-sunken);
  color: var(--text-muted);
  font-size: 0.63rem;
}
.bud-iname {
  min-width: 0;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bud-isum {
  margin-left: auto;
  flex: 0 0 auto;
  color: var(--text);
  white-space: nowrap;
}
/* 用量依据：比正文更弱，是「我怎么算的」 */
.bud-basis {
  margin: 4px 0 0;
  font-size: 0.68rem;
  line-height: 1.5;
  color: var(--text-faint);
}
/* 口径说明：单价不是总花费时，这句必须看得见 */
.bud-note {
  margin: 5px 0 0;
  font-size: 0.68rem;
  line-height: 1.55;
  color: var(--warn);
  em { font-style: normal; font-weight: 600; }
}
.bud-range {
  margin: 0;
  font-size: 0.68rem;
  color: var(--text-faint);
}

/* ── 待拍板 ── */
.dp-ask {
  border: 1px solid var(--accent-200);
  border-radius: var(--radius-sm);
  background: var(--accent-50);
  padding: 10px 12px;
}
.dp-ask-k {
  margin: 0 0 4px;
  font-size: 0.66rem;
  color: var(--accent-700);
}
.dp-ask-text {
  margin: 0;
  font-size: 0.75rem;
  line-height: 1.55;
  color: var(--text);
}
.dp-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.dp-btn {
  font-family: var(--font-body);
  font-size: 0.7rem;
  padding: 3px 10px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-strong);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: color 0.15s ease-out, border-color 0.15s ease-out;
  &:hover { color: var(--text); }
  &.primary {
    background: var(--accent-solid);
    border-color: var(--accent-solid);
    color: var(--on-accent);
  }
}
</style>
