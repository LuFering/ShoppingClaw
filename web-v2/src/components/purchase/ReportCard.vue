<template>
  <div class="rp">
    <!--
      报告不是「三张表拼起来」，而是一份有头有尾的文档：
      摘要 → 关键数字 → 预算构成图 → 整体取舍 → 逐品类依据 → 风险。
      阅读顺序就是用户下决定时的思考顺序。
    -->
    <p class="rp-summary">{{ d.summary }}</p>

    <div v-if="headline.length" class="rp-facts">
      <div v-for="f in headline" :key="f.k" class="rp-fact">
        <span class="rp-fact-v mono">{{ f.v }}</span>
        <span class="rp-fact-k">{{ f.k }}</span>
      </div>
    </div>

    <!-- 预算构成：用 echarts 画，可 hover 看金额 -->
    <div v-if="chart.series.length" class="rp-chart">
      <p class="rp-h">预算构成</p>
      <div ref="pieEl" class="rp-pie" />
      <p v-if="chart.remaining" class="rp-chart-note">
        另有余量 ¥{{ fmt(chart.remaining) }} 未动用 —— 未计入上图。
      </p>
      <p v-if="chart.missing?.length" class="rp-chart-warn">
        {{ chart.missing.join('、') }} 未估出用量，未计入上图。
      </p>
    </div>

    <template v-if="d.thesis">
      <p class="rp-h">整体取舍</p>
      <p class="rp-thesis">{{ d.thesis }}</p>
    </template>

    <!-- 逐品类：报告的主体，要能照着它下单 -->
    <template v-if="d.sections?.length">
      <p class="rp-h">逐项方案</p>
      <div v-for="(s, i) in d.sections" :key="i" class="rp-sec">
        <p class="rp-sec-h">
          <span class="rp-sec-n mono">{{ i + 1 }}</span>
          <span class="rp-sec-cat">{{ s.category }}</span>
        </p>
        <p class="rp-sec-name">{{ s.name }}</p>
        <p class="rp-sec-price mono">
          <span v-if="s.price != null">¥{{ fmt(s.price) }}</span>
          <template v-if="s.quantity">
            <span class="rp-x"> × {{ s.quantity }}</span>
            <span v-if="s.subtotal != null" class="rp-eq"> = ¥{{ fmt(s.subtotal) }}</span>
          </template>
        </p>
        <p v-if="s.quantity_basis" class="rp-sec-basis">用量依据：{{ s.quantity_basis }}</p>
        <p v-if="s.why" class="rp-sec-why">{{ s.why }}</p>

        <details v-if="s.alternatives?.length" class="rp-fold">
          <summary>同品类其他候选 {{ s.alternatives.length }} 件</summary>
          <ul>
            <li v-for="(a, k) in s.alternatives" :key="k">
              <span>{{ a.name }}</span>
              <span v-if="a.price != null" class="mono">¥{{ fmt(a.price) }}</span>
            </li>
          </ul>
        </details>

        <details v-if="s.excluded?.length" class="rp-fold">
          <summary>已排除 {{ s.excluded.length }} 件</summary>
          <ul>
            <li v-for="(e, k) in s.excluded" :key="k">
              <span>{{ e.name }}</span>
              <span v-if="e.price != null" class="mono">¥{{ fmt(e.price) }}</span>
              <span class="rp-out-why">{{ e.reason || '不满足硬约束' }}</span>
            </li>
          </ul>
        </details>
      </div>
    </template>

    <template v-if="d.risks?.length">
      <p class="rp-h">风险与待确认</p>
      <ul class="rp-risks">
        <li v-for="(r, i) in d.risks" :key="i">{{ r }}</li>
      </ul>
    </template>

    <p v-if="d.generated_note" class="rp-note">{{ d.generated_note }}</p>
  </div>
</template>

<script setup>
/**
 * 采购规划报告 —— 交付物的主件。
 *
 * ═══════════════════════════════════════════════════════════════════
 * 2026-09-27：为什么单独做一个组件
 * ═══════════════════════════════════════════════════════════════════
 * 用户原话：「这个交付方式还是太简陋了…要么生成一个详细的采购规划报告
 * 而非这种非常敷衍不专业的几张表」。
 *
 * 原先右栏三份交付物各是一张表，读者得自己在脑子里把它们拼起来 ——
 * 「买什么」在一份里、「为什么」在另一份里、「花多少」在第三份里。
 * 报告把这些按**读者的顺序**重新组织成一份文档。
 *
 * 饼图用项目已有的 echarts（package.json 里就有），不引新库。
 * 与 PDF 版共用同一套后端数据（`stages.build_report_doc`），
 * 所以两边不会漂 —— 只是 PDF 那边用 PyMuPDF 自己画。
 */
import { computed, onMounted, onBeforeUnmount, ref, watch, nextTick } from 'vue'
import * as echarts from 'echarts/core'
import { PieChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { themeColor } from '@/utils/themeColors'

echarts.use([PieChart, TooltipComponent, LegendComponent, CanvasRenderer])

const props = defineProps({
  d: { type: Object, required: true }
})

const pieEl = ref(null)
// ⚠️ 叫 pie 而不是 chart —— `chart` 已经是下面那个 computed 的名字，
// 同名 `let` + `const` 会直接编译报错（Redeclaration）。
let pie = null

const fmt = (v) => {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return Number.isInteger(n) ? n.toLocaleString('en-US') : n.toFixed(2)
}

/** 报告开头的关键数字 —— 只放真有值的 */
const headline = computed(() => {
  const h = props.d?.headline || {}
  const out = []
  if (h.categories) out.push({ k: '入选品类', v: String(h.categories) })
  if (h.total != null) out.push({ k: '估算总额', v: '¥' + fmt(h.total) })
  if (h.ratio != null) out.push({ k: '预算占用', v: Math.round(h.ratio * 100) + '%' })
  if (h.remaining != null) out.push({ k: '结余', v: '¥' + fmt(h.remaining) })
  if (h.candidates) out.push({ k: '浏览候选', v: String(h.candidates) })
  return out
})

const chart = computed(() => props.d?.chart || { series: [], missing: [] })

/** 饼图配色与决策图同源，两种视图观感一致 */
const PIE_COLORS = [
  '#9581cc', '#6dc8ec', '#5ad8a6', '#f6bd16',
  '#f27c7c', '#8c8c8c', '#dca63a', '#36a3e0'
]

const render = async () => {
  await nextTick()
  if (!pieEl.value) return
  const series = chart.value.series || []
  if (!series.length) {
    pie?.dispose?.()
    pie = null
    return
  }
  if (!pie) pie = echarts.init(pieEl.value)
  pie.setOption({
    color: PIE_COLORS,
    tooltip: {
      trigger: 'item',
      formatter: (p) => `${p.name}<br/>¥${fmt(p.value)}　${p.percent}%`
    },
    legend: {
      type: 'scroll',
      orient: 'vertical',
      right: 0,
      top: 'center',
      itemWidth: 9,
      itemHeight: 9,
      textStyle: { fontSize: 11, color: themeColor('--text-muted', '#6b727a') }
    },
    series: [{
      type: 'pie',
      radius: ['46%', '72%'],
      center: ['36%', '50%'],
      avoidLabelOverlap: true,
      itemStyle: { borderWidth: 1.5, borderColor: themeColor('--bg-surface', '#fff') },
      label: { show: false },
      labelLine: { show: false },
      data: series.map((s) => ({ name: s.name, value: s.value }))
    }]
  })
  pie.resize()
}

const onResize = () => pie?.resize()

onMounted(() => {
  render()
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  pie?.dispose?.()
  pie = null
})

// 换一份交付物 / 数据到了就重画
watch(() => props.d, render, { deep: true })
</script>

<style lang="less" scoped>
.rp {
  display: flex;
  flex-direction: column;
  gap: 9px;
}

.rp-summary {
  margin: 0;
  font-size: 0.76rem;
  line-height: 1.6;
  color: var(--text);
  padding-left: 9px;
  border-left: 2px solid var(--accent-solid);
}

/* ── 关键数字 ── */
.rp-facts {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 14px;
}
.rp-fact {
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.rp-fact-v {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--text-strong);
}
.rp-fact-k {
  font-size: 0.63rem;
  color: var(--text-faint);
}

/* ── 小节标题 ── */
.rp-h {
  margin: 5px 0 0;
  font-size: 0.68rem;
  font-weight: 600;
  color: var(--text-faint);
  letter-spacing: 0.02em;
}

/* ── 图表 ── */
.rp-pie {
  width: 100%;
  height: 168px;
}
.rp-chart-note,
.rp-chart-warn {
  margin: 0;
  font-size: 0.66rem;
  line-height: 1.5;
  color: var(--text-faint);
}
.rp-chart-warn { color: var(--warn); }

.rp-thesis {
  margin: 0;
  font-size: 0.73rem;
  line-height: 1.65;
  color: var(--text-muted);
}

/* ── 逐项方案 ── */
.rp-sec {
  border-top: 1px solid var(--border);
  padding-top: 7px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  & + .rp-sec { margin-top: 3px; }
}
.rp-sec-h {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
}
.rp-sec-n {
  font-size: 0.64rem;
  color: var(--text-faint);
  background: var(--bg-sunken);
  border-radius: 3px;
  padding: 0 5px;
}
.rp-sec-cat {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-strong);
}
.rp-sec-name {
  margin: 0;
  font-size: 0.74rem;
  line-height: 1.5;
  color: var(--text);
}
.rp-sec-price {
  margin: 0;
  font-size: 0.72rem;
  color: var(--accent-700);
}
.rp-x, .rp-eq { color: var(--text-muted); }
.rp-sec-basis {
  margin: 0;
  font-size: 0.66rem;
  color: var(--text-faint);
}
.rp-sec-why {
  margin: 2px 0 0;
  font-size: 0.71rem;
  line-height: 1.6;
  color: var(--text-muted);
}

/* 折叠的备选与排除：默认收起，需要核对时再点开 */
.rp-fold {
  margin-top: 2px;
  summary {
    font-size: 0.66rem;
    color: var(--text-faint);
    cursor: pointer;
    list-style: none;
    &::marker, &::-webkit-details-marker { display: none; }
    &::before { content: '› '; }
  }
  &[open] summary::before { content: '⌄ '; }
  ul {
    list-style: none;
    margin: 3px 0 0;
    padding: 0 0 0 4px;
    display: flex;
    flex-direction: column;
    gap: 3px;
    font-size: 0.68rem;
    line-height: 1.5;
    li {
      display: flex;
      flex-wrap: wrap;
      gap: 2px 7px;
      color: var(--text-muted);
    }
  }
}
.rp-out-why {
  flex: 1 0 100%;
  color: var(--warn);
  font-size: 0.65rem;
}

.rp-risks {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
  font-size: 0.7rem;
  line-height: 1.55;
  color: var(--text-muted);
  li {
    padding-left: 10px;
    position: relative;
    &::before {
      content: '·';
      position: absolute;
      left: 2px;
      color: var(--warn);
    }
  }
}

.rp-note {
  margin: 4px 0 0;
  padding-top: 6px;
  border-top: 1px solid var(--border);
  font-size: 0.64rem;
  line-height: 1.5;
  color: var(--text-faint);
}
</style>
