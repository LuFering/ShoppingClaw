<template>
  <div class="pv">
    <header class="pv-head">
      <div class="pv-title">
        <span class="pv-name">{{ d.name }}</span>
        <span v-if="d.meta" class="pv-meta">{{ d.meta }}</span>
      </div>
      <div class="pv-acts">
        <!--
          下载按钮按**后端声明的 formats** 生成。
          不在这里写死「报告有 PDF」—— 加一种产出物、改一次后端声明即可。
        -->
        <button
          v-for="f in d.formats || []"
          :key="f"
          class="pv-btn is-dl"
          type="button"
          :disabled="busy[`${d.id}:${f}`]"
          @click="$emit('export', { d, fmt: f })"
        >
          <FileDown :size="13" />{{ busy[`${d.id}:${f}`] ? '导出中…' : fmtLabel(f) }}
        </button>
        <button class="pv-btn" type="button" :title="'关闭预览'" @click="$emit('close')">
          <X :size="13" />
        </button>
      </div>
    </header>

    <div class="pv-body">
      <p v-if="d.state === 'running'" class="pv-hint">正在生成…</p>
      <p v-else-if="d.state === 'empty'" class="pv-hint">
        这一份没有内容 —— 本次推演没留下足够数据。不是失败。
      </p>
      <p v-else-if="!d.data" class="pv-hint">还没有内容可预览。</p>

      <!-- 报告：文档形态，全宽才读得下去 -->
      <ReportCard v-else-if="d.data.kind === 'report'" :d="d.data" />

      <!-- 采购清单：照着下单的表 -->
      <template v-else-if="d.data.kind === 'list'">
        <table class="tbl">
          <thead>
            <tr>
              <th>品类</th><th>商品</th>
              <th class="num">单价</th><th class="num">数量</th><th class="num">小计</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(r, i) in d.data.rows" :key="i">
              <td><span class="tag">{{ r.category }}</span></td>
              <td class="tbl-n">
                {{ r.name }}
                <span v-if="r.note" class="tbl-note">{{ r.note }}</span>
                <span v-if="r.item_id" class="tbl-id mono" :title="'item_id：' + r.item_id">
                  {{ r.item_id }}
                </span>
              </td>
              <td class="num mono">{{ r.unit_price != null ? '¥' + fmt(r.unit_price) : '—' }}</td>
              <td class="num mono">{{ r.quantity }}</td>
              <td class="num mono strong">
                {{ r.subtotal != null ? '¥' + fmt(r.subtotal) : '待估' }}
              </td>
            </tr>
          </tbody>
          <tfoot>
            <tr v-if="d.data.total != null">
              <td colspan="4">合计</td>
              <td class="num mono strong">¥{{ fmt(d.data.total) }}</td>
            </tr>
            <tr v-if="d.data.remaining != null">
              <td colspan="4">结余（预算 ¥{{ fmt(d.data.budget) }}）</td>
              <td class="num mono">¥{{ fmt(d.data.remaining) }}</td>
            </tr>
          </tfoot>
        </table>
        <p v-if="d.data.missing?.length" class="pv-warn">
          {{ d.data.missing.join('、') }} 未估出用量，小计与合计未含。
        </p>
        <p v-if="d.data.note" class="pv-note">{{ d.data.note }}</p>
      </template>

      <!-- 候选对比表：按品类分组 -->
      <template v-else-if="d.data.kind === 'compare'">
        <div v-for="g in groups(d)" :key="g.category" class="cmp-grp">
          <p v-if="g.category" class="cmp-cat">{{ g.category }}</p>
          <table class="tbl">
            <thead>
              <tr><th>候选</th><th class="num">价格</th><th>结论</th></tr>
            </thead>
            <tbody>
              <tr
                v-for="(r, i) in g.rows"
                :key="i"
                :class="{ 'is-picked': r.picked, 'is-out': r.tag === '排除' }"
              >
                <td>
                  {{ r.name }}
                  <span v-if="r.reason" class="tbl-note">{{ r.reason }}</span>
                </td>
                <td class="num mono">{{ r.price != null ? '¥' + fmt(r.price) : '—' }}</td>
                <td><span class="tag" :class="tagCls(r.tag)">{{ r.tag }}</span></td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="pv-note">
          共 {{ d.data.counts?.candidates || 0 }} 个候选，排除 {{ d.data.counts?.excluded || 0 }} 个<template
            v-if="d.data.counts?.picked">，入选 {{ d.data.counts.picked }} 件</template>。
        </p>
      </template>

      <!-- 预算分配表 -->
      <template v-else-if="d.data.kind === 'budget'">
        <template v-if="d.data.caliber === 'total'">
          <p class="bud-big mono">¥{{ fmt(d.data.spent) }}
            <span v-if="d.data.budget" class="bud-of">/ 预算 ¥{{ fmt(d.data.budget) }}</span>
          </p>
          <div v-if="d.data.ratio != null" class="bud-bar">
            <i :style="{ width: Math.min(100, Math.round(d.data.ratio * 100)) + '%' }" />
          </div>
          <p class="pv-note">
            占预算 {{ Math.round(d.data.ratio * 100) }}%
            <template v-if="d.data.remaining != null">· 结余 ¥{{ fmt(d.data.remaining) }}</template>
          </p>
        </template>
        <template v-else-if="d.data.caliber === 'unit_only'">
          <p class="bud-big mono">¥{{ fmt(d.data.unit_price) }}<span class="bud-of">选中商品单价</span></p>
          <p class="pv-warn">未含用量估算 —— 这是<em>单价</em>，不是整件事的总花费。</p>
        </template>
        <p v-else class="pv-hint">这次没有选出商品，无法计算花费。</p>

        <table v-if="d.data.items?.length" class="tbl">
          <thead>
            <tr><th>品类</th><th>商品</th><th class="num">单价 × 用量</th><th class="num">小计</th></tr>
          </thead>
          <tbody>
            <tr v-for="(it, i) in d.data.items" :key="i">
              <td><span class="tag">{{ it.category }}</span></td>
              <td>{{ it.name }}</td>
              <td class="num mono">
                <template v-if="it.unit_price != null && it.quantity">
                  ¥{{ fmt(it.unit_price) }} × {{ it.quantity }}
                </template>
                <template v-else>—</template>
              </td>
              <td class="num mono strong">
                {{ it.subtotal != null ? '¥' + fmt(it.subtotal) : '待估' }}
              </td>
            </tr>
          </tbody>
        </table>
        <p v-if="d.data.range" class="pv-note mono">
          候选价格区间 ¥{{ fmt(d.data.range.min) }} – ¥{{ fmt(d.data.range.max) }}
        </p>
      </template>

      <!-- 未知类型：如实说，不假装渲染出来 -->
      <p v-else class="pv-hint">
        这份产出物的类型（{{ d.data.kind }}）还没有对应的预览视图。
        可以下载查看。
      </p>
    </div>
  </div>
</template>

<script setup>
/**
 * 产出物预览面 —— 全宽渲染正文。
 *
 * ═══════════════════════════════════════════════════════════════════
 * 2026-09-27：为什么要把正文从右栏挪出来
 * ═══════════════════════════════════════════════════════════════════
 * 之前正文是**内联在 320px 的右栏**里渲染的。那个结构撑不住一份真正的
 * 报告：报告的段落、表格、图表需要宽度，挤进窄栏的结果是每行折成三四段，
 * 越做越挤，最后只能靠「默认收起、点开才看」来缓解 —— 而点开之后依然挤。
 *
 * 现在正文搬到这个面里，由工作台主区切换呈现（全宽）。右栏退回它该做的
 * 事：列出产出了什么、让你能拿走。这也是 Yuxi 的做法 —— 产出物清单与
 * 预览面分开，预览面占据主区。
 *
 * ⚠️ 这里只**渲染**，不算任何业务数字 —— 数据来自后端同一套 builder，
 * 与 PDF/CSV 导出共用，三边不会漂。
 */
import { FileDown, X } from 'lucide-vue-next'
import ReportCard from './ReportCard.vue'

defineProps({
  d: { type: Object, required: true },
  busy: { type: Object, default: () => ({}) }
})

defineEmits(['export', 'close'])

const fmt = (v) => {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return Number.isInteger(n) ? n.toLocaleString('en-US') : n.toFixed(2)
}

const fmtLabel = (f) => ({ pdf: 'PDF', csv: 'Excel', md: 'Markdown' }[f] || f.toUpperCase())

/** 对比表分组：优先读 groups，旧结构退回拍平的 rows */
const groups = (d) => {
  const x = d.data || {}
  if (x.groups?.length) return x.groups
  return x.rows?.length ? [{ category: '', rows: x.rows }] : []
}

const tagCls = (tag) => ({ 'tag-in': tag === '入选', 'tag-out': tag === '排除' }[tag] || 'tag-cand')
</script>

<style lang="less" scoped>
.pv {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}

.pv-head {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
}
.pv-title {
  display: flex;
  align-items: baseline;
  gap: 10px;
  min-width: 0;
}
.pv-name {
  font-size: 0.88rem;
  font-weight: 600;
  color: var(--text-strong);
}
.pv-meta {
  font-size: 0.72rem;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pv-acts {
  margin-left: auto;
  display: flex;
  gap: 6px;
  flex: 0 0 auto;
}
.pv-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-family: var(--font-body);
  font-size: 0.7rem;
  padding: 3px 10px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-strong);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  &:hover:not(:disabled) { color: var(--text); }
  &:disabled { opacity: 0.55; cursor: default; }
  &.is-dl {
    border-color: var(--accent-200);
    color: var(--accent-700);
    &:hover:not(:disabled) { border-color: var(--accent-500); }
  }
}

/* 正文区：全宽、可滚动。报告的排版按**纸张**的舒适行宽来约束，
   否则一行 1000px 的文字会很难读。 */
.pv-body {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding: 16px 22px 28px;
  max-width: 940px;
}

.pv-hint {
  margin: 0;
  font-size: 0.76rem;
  line-height: 1.6;
  color: var(--text-muted);
}
.pv-note {
  margin: 8px 0 0;
  font-size: 0.7rem;
  line-height: 1.55;
  color: var(--text-faint);
}
.pv-warn {
  margin: 8px 0 0;
  font-size: 0.7rem;
  line-height: 1.55;
  color: var(--warn);
  em { font-style: normal; font-weight: 600; }
}

/* ── 表格（清单 / 对比 / 预算共用） ── */
.tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.73rem;
  margin-top: 4px;
  th {
    text-align: left;
    font-weight: 400;
    color: var(--text-faint);
    padding: 0 6px 5px;
    border-bottom: 1px solid var(--border);
    &.num { text-align: right; }
    &:first-child { padding-left: 0; }
    &:last-child { padding-right: 0; }
  }
  td {
    padding: 7px 6px;
    border-bottom: 1px solid var(--border);
    vertical-align: top;
    color: var(--text);
    &.num { text-align: right; white-space: nowrap; }
    &.strong { font-weight: 600; color: var(--text-strong); }
    &:first-child { padding-left: 0; }
    &:last-child { padding-right: 0; }
  }
  tfoot td {
    border-bottom: none;
    padding-top: 9px;
    color: var(--text-muted);
    &:first-child { text-align: right; }
  }
  tr.is-picked td { background: var(--accent-50); }
  tr.is-out .tbl-note { color: var(--text-faint); }
}
.tbl-n {
  max-width: 0;
  min-width: 220px;
}
.tbl-note {
  display: block;
  margin-top: 2px;
  font-size: 0.68rem;
  line-height: 1.5;
  color: var(--text-faint);
}
/* item_id 很长，默认截断，hover 看全 —— 它的用途是复制去淘宝搜 */
.tbl-id {
  display: block;
  margin-top: 2px;
  font-size: 0.62rem;
  color: var(--text-faint);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 260px;
  cursor: help;
}

.tag {
  display: inline-block;
  font-size: 0.66rem;
  padding: 1px 6px;
  border-radius: 3px;
  background: var(--bg-sunken);
  color: var(--text-muted);
  white-space: nowrap;
  &.tag-in { color: var(--pos); }
  &.tag-out { color: var(--text-faint); }
}

.cmp-grp {
  & + .cmp-grp { margin-top: 18px; }
}
.cmp-cat {
  margin: 0 0 2px;
  font-size: 0.76rem;
  font-weight: 600;
  color: var(--text-strong);
}

/* ── 预算大字 ── */
.bud-big {
  margin: 0;
  font-size: 1.3rem;
  font-weight: 600;
  color: var(--text-strong);
}
.bud-of {
  margin-left: 8px;
  font-size: 0.75rem;
  font-weight: 400;
  color: var(--text-muted);
}
.bud-bar {
  margin-top: 8px;
  height: 6px;
  border-radius: 3px;
  background: var(--bg-sunken);
  overflow: hidden;
  i {
    display: block;
    height: 100%;
    border-radius: 3px;
    background: var(--accent-solid);
  }
}
</style>
