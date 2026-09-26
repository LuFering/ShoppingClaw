<template>
  <div class="ap">
    <header class="ap-head">
      <span class="ap-title">交付成果</span>
      <span class="ap-sub mono">{{ readyCount }} / {{ items.length }}</span>
    </header>

    <div class="ap-scroll">
      <!--
        ═══════════════════════════════════════════════════════════════
        2026-09-27 重构：产出物清单 + 独立预览面
        ═══════════════════════════════════════════════════════════════
        用户原话：「右边的交付页也需要重构，饼图等设计很好，但是不要再基于
        之前的交付架构来补内容」。

        之前的架构是「每份产出物在 320px 的窄栏里**内联** render 全文」。
        那个架构撑不住一份真正的报告 —— 报告是**文档**，它的段落、表格、
        图表需要宽度才能读；塞进窄栏的结果就是每一行都折成三四段，
        越做越挤，最后只能靠折叠藏起来，等于没交付。

        现在的分工（借鉴 Yuxi 的产出物/预览分离）：
          · 这一栏是**清单**：每份产出物一个卡片，说明它是什么、能导什么格式
          · 点「预览」在**右侧独立面**里全宽打开 —— 报告才读得下去
          · 下载按钮直接给最终文件（PDF / CSV / MD）

        卡片上只留**一行结论摘要**（"4 个品类 · ¥380.72 · 占 8%"），
        全文留给预览面。这样三四个卡片能一屏扫完，不用展开就能知道结果。
      -->
      <section
        v-for="d in items"
        :key="d.id"
        class="ac"
        :class="[`is-${d.state}`, { 'is-primary': d.primary, 'is-active': activeId === d.id }]"
      >
        <button class="ac-head" type="button" @click="$emit('preview', d)">
          <span class="ac-name">
            {{ d.name }}
            <!-- 主件标记：只标一个，避免「都重要」等于「都不重要」 -->
            <span v-if="d.primary" class="ac-star">主件</span>
          </span>
          <span class="ac-state mono" :class="`is-${d.state}`">{{ stateLabel(d) }}</span>
        </button>

        <p v-if="d.desc" class="ac-desc">{{ d.desc }}</p>

        <!-- 生成中：骨架条，不转圈 -->
        <div v-if="d.state === 'running'" class="sk">
          <span class="sk-bar" style="width: 76%" />
          <span class="sk-bar" style="width: 52%" />
        </div>

        <template v-else-if="d.state === 'ready' && d.data">
          <!-- 一行结论摘要：不展开也能知道这份说了什么 -->
          <p class="ac-brief">{{ brief(d) }}</p>

          <div class="ac-actions">
            <button class="ac-btn" type="button" @click="$emit('preview', d)">
              <Eye :size="12" />预览
            </button>
            <!--
              下载按钮**按后端声明的 formats 生成** —— 不写死哪一份有 PDF。
              点了才发现不支持的体验很差；声明式的话，加一种产出物只要改后端。
            -->
            <button
              v-for="f in d.formats || []"
              :key="f"
              class="ac-btn is-dl"
              type="button"
              :disabled="busy[`${d.id}:${f}`]"
              @click="$emit('export', { d, fmt: f })"
            >
              <FileDown :size="12" />{{ fmtLabel(f) }}
            </button>
          </div>
        </template>

        <p v-else-if="d.state === 'empty'" class="ac-empty">
          这次推演没留下足够数据生成这一份 —— 不是失败，是确实没有内容。
        </p>
        <p v-else-if="d.state === 'waiting'" class="ac-empty dim">等待上游步骤产出</p>
      </section>

      <!--
        agent 停下来等拍板的问题，固定在这里而不是混进左栏执行流。
        放在清单**之后**：它是当前最需要动作的东西，视线自然落到底部。
      -->
      <div v-if="question" class="ap-ask">
        <p class="ap-ask-k">需要你拍板</p>
        <p class="ap-ask-text">{{ question.text }}</p>
        <div class="ap-actions">
          <button
            v-for="opt in question.options"
            :key="opt.key"
            class="ac-btn"
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
 * 右栏 · 交付成果清单。
 *
 * 职责只有两件：**列出这次产出了什么**、**让别人能拿走**（预览 / 下载）。
 * 正文渲染不在这里 —— 它在 ArtifactPreview 里，全宽打开。
 * 见模板顶部那段重构说明。
 */
import { computed } from 'vue'
import { Eye, FileDown } from 'lucide-vue-next'

const props = defineProps({
  items: { type: Array, default: () => [] },
  question: { type: Object, default: null },
  /** 正在导出中的 `${id}:${fmt}` 集合 —— 防连点，由父层管 */
  busy: { type: Object, default: () => ({}) },
  /** 当前在预览面里打开的产出物 id */
  activeId: { type: String, default: '' }
})

defineEmits(['preview', 'export', 'answer'])

const readyCount = computed(() => props.items.filter((d) => d.state === 'ready').length)

const stateLabel = (d) => ({
  ready: '已生成',
  running: Math.round((d.progress || 0) * 100) + '%',
  empty: '无内容',
  waiting: '待生成'
}[d.state] || d.state)

/** 格式 → 按钮文案。用户认「PDF」「Excel」比认「csv」快 */
const fmtLabel = (f) => ({ pdf: 'PDF', csv: 'Excel', md: 'Markdown' }[f] || f.toUpperCase())

const fmtPrice = (v) => {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return Number.isInteger(n) ? n.toLocaleString('en-US') : n.toFixed(2)
}

/**
 * 一行结论摘要 —— 不展开也要能知道这份产出物说了什么。
 *
 * 每份产出物的**结论**不同，所以按 kind 分别取：
 *   报告/清单 → 几个品类、多少钱、占预算几成（结论本身就是这些数字）
 *   对比表   → 比了多少件、排除多少
 *   预算表   → 花多少、剩多少
 */
const brief = (d) => {
  const x = d.data || {}
  if (x.kind === 'report' || x.kind === 'list') {
    const h = x.headline || {}
    const parts = []
    const n = h.categories ?? (x.rows?.length || 0)
    if (n) parts.push(`${n} 个品类`)
    const total = h.total ?? x.total
    if (total != null) parts.push(`¥${fmtPrice(total)}`)
    const budget = h.budget ?? x.budget
    if (total != null && budget) parts.push(`占 ${Math.round((total / budget) * 100)}%`)
    const rem = h.remaining ?? x.remaining
    if (rem != null) parts.push(`结余 ¥${fmtPrice(rem)}`)
    if (x.kind === 'list' && x.missing?.length) parts.push(`${x.missing.length} 类待估`)
    return parts.join(' · ')
  }
  if (x.kind === 'compare') {
    const c = x.counts || {}
    return `${c.candidates || 0} 个候选，排除 ${c.excluded || 0} 个，入选 ${c.picked || 0} 件`
  }
  if (x.kind === 'budget') {
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
.ap {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
}

.ap-head {
  flex: 0 0 auto;
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 0 0 10px;
  border-bottom: 1px solid var(--border);
}
.ap-title {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--text-strong);
}
.ap-sub {
  margin-left: auto;
  font-size: 0.7rem;
  color: var(--text-muted);
}

.ap-scroll {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* ── 产出物卡片 ── */
.ac {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-surface);
  padding: 8px 10px 10px;
  transition: border-color 0.15s ease-out;
  &.is-primary { border-color: var(--accent-200); }
  &.is-active { border-color: var(--accent-solid); background: var(--accent-50); }
  &.is-empty { opacity: 0.85; }
}
.ac-head {
  display: flex;
  align-items: center;
  gap: 7px;
  width: 100%;
  padding: 0;
  border: none;
  background: transparent;
  font-family: var(--font-body);
  text-align: left;
  cursor: pointer;
}
.ac-name {
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--text-strong);
}
.ac-star {
  display: inline-block;
  margin-left: 5px;
  padding: 0 5px;
  border-radius: 3px;
  background: var(--accent-50);
  color: var(--accent-700);
  font-size: 0.6rem;
  font-weight: 400;
  vertical-align: 1px;
}
.ac-state {
  margin-left: auto;
  font-size: 0.66rem;
  &.is-ready { color: var(--pos); }
  &.is-running { color: var(--info); }
  &.is-empty { color: var(--warn); }
  &.is-waiting { color: var(--text-faint); }
}
.ac-desc {
  margin: 3px 0 0;
  font-size: 0.68rem;
  line-height: 1.5;
  color: var(--text-faint);
}
/* 一行结论摘要：卡片的主角，比 desc 实 */
.ac-brief {
  margin: 6px 0 0;
  font-size: 0.73rem;
  line-height: 1.5;
  color: var(--text);
}

.ac-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 7px;
}
.ac-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-family: var(--font-body);
  font-size: 0.68rem;
  padding: 2px 9px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-strong);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: color 0.15s ease-out, border-color 0.15s ease-out;
  &:hover:not(:disabled) { color: var(--text); border-color: var(--text-faint); }
  &:disabled { opacity: 0.55; cursor: default; }
  /* 下载按钮稍弱于「预览」—— 预览是主路径，下载是拿走 */
  &.is-dl {
    border-color: var(--border);
    color: var(--text-faint);
    &:hover:not(:disabled) { color: var(--accent-700); border-color: var(--accent-200); }
  }
  &.primary {
    background: var(--accent-solid);
    border-color: var(--accent-solid);
    color: var(--on-accent);
  }
}

/* 生成中骨架 */
.sk {
  margin-top: 7px;
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

.ac-empty {
  margin: 6px 0 0;
  font-size: 0.7rem;
  line-height: 1.55;
  color: var(--text-muted);
  &.dim { color: var(--text-faint); }
}

/* ── 待拍板 ── */
.ap-ask {
  border: 1px solid var(--accent-200);
  border-radius: var(--radius-sm);
  background: var(--accent-50);
  padding: 10px 12px;
}
.ap-ask-k {
  margin: 0 0 4px;
  font-size: 0.66rem;
  color: var(--accent-700);
}
.ap-ask-text {
  margin: 0;
  font-size: 0.75rem;
  line-height: 1.55;
  color: var(--text);
}
.ap-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
</style>
