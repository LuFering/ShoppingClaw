<template>
  <section class="dp">
    <header class="dp__hd">
      <h2 class="dp__title">交付区</h2>
      <span class="dp__prog mono">{{ readyCount }}/{{ items.length }}</span>
    </header>

    <div
      v-for="d in items"
      :key="d.key"
      class="dc"
      :class="[`is-${d.state}`, { 'dc--needs': d.state === 'needs' }]"
    >
      <div class="dc__hd">
        <span class="dc__label">{{ d.label }}</span>
        <span class="dc__state" :class="`is-${d.state}`">{{ stateText(d.state) }}</span>
      </div>

      <!-- 生成中：骨架，不转圈 -->
      <div v-if="d.state === 'building'" class="sk">
        <span class="sk__bar" style="width:72%" />
        <span class="sk__bar" style="width:52%" />
        <span class="sk__bar" style="width:64%" />
      </div>

      <div v-else-if="d.state === 'todo'" class="dc__idle">等待上游步骤产出</div>

      <template v-else-if="d.data">
        <!-- 礼盒方案 -->
        <template v-if="d.key === 'plan'">
          <p class="dc__lead">{{ d.data.title }}</p>
          <p class="dc__sub">{{ d.data.thesis }}</p>
          <ul class="pl">
            <li v-for="it in d.data.items" :key="it.name">
              <span class="pl__role">{{ it.role }}</span>
              <span class="pl__name">{{ it.name }}</span>
              <span class="pl__p mono">¥{{ it.price }}</span>
              <span class="pl__why">{{ it.why }}</span>
            </li>
          </ul>
        </template>

        <!-- 候选对比 -->
        <template v-else-if="d.key === 'compare'">
          <table class="cmp">
            <thead>
              <tr><th>候选</th><th>价</th><th>契合</th><th /></tr>
            </thead>
            <tbody>
              <tr v-for="r in d.data" :key="r.name" :class="{ 'is-out': r.tag === '排除' }">
                <td class="cmp__n">{{ r.name }}</td>
                <td class="mono">{{ r.price }}</td>
                <td><span class="fit" :style="{ width: (r.fit * 10) + '%' }" /></td>
                <td><span class="tag" :class="r.tag === '入选' ? 'tag--in' : 'tag--out'">{{ r.tag }}</span></td>
              </tr>
            </tbody>
          </table>
        </template>

        <!-- 预算分配 -->
        <template v-else-if="d.key === 'budget'">
          <div v-for="b in d.data" :key="b.label" class="bd">
            <span class="bd__l">{{ b.label }}</span>
            <span class="bd__bar"><i :style="{ width: (b.value / budgetMax * 100) + '%' }" /></span>
            <span class="bd__v mono">¥{{ b.value }}</span>
          </div>
        </template>

        <!-- 寄语文案 -->
        <template v-else-if="d.key === 'message'">
          <div class="msg__tone">
            <span class="tone">{{ d.data.tone }}</span>
            <span class="msg__hint">语气可换</span>
          </div>
          <p class="msg__text">{{ d.data.text }}</p>
        </template>

        <!-- 货源与配送 -->
        <template v-else-if="d.key === 'supply'">
          <div v-for="s in d.data" :key="s.item" class="sp">
            <span class="sp__i">{{ s.item }}</span>
            <span class="sp__f">{{ s.from }}</span>
            <span class="sp__e mono">{{ s.eta }}</span>
            <span class="sp__n">{{ s.note }}</span>
          </div>
        </template>

        <!-- 送礼订单 -->
        <template v-else-if="d.key === 'order'">
          <div class="od__sum">
            <span class="od__t mono">¥{{ d.data.total }}</span>
            <span class="od__b">预算 ¥{{ d.data.budget }} · 余 ¥{{ d.data.budget - d.data.total }}</span>
          </div>
          <span class="od__bar"><i :style="{ width: (d.data.total / d.data.budget * 100) + '%' }" /></span>
          <p class="od__eta">{{ d.data.eta }}</p>
          <ul class="od__steps">
            <li v-for="(s, i) in d.data.steps" :key="s">
              <span class="mono">{{ i + 1 }}</span>{{ s }}
            </li>
          </ul>
          <div class="od__acts">
            <button class="btn btn--primary" type="button" @click="$emit('confirm')">确认并下单</button>
            <button class="btn" type="button" @click="$emit('revise', 'order')">改一下</button>
          </div>
        </template>
      </template>
    </div>
  </section>
</template>

<script setup>
/**
 * 右栏 · 交付区
 *
 * 用户规格：逐步生成 礼盒方案 / 候选对比 / 预算分配 / 寄语文案 / 货源与配送，
 * 最终收敛为**可确认、可修改、可执行**的送礼订单。
 *
 * 四态：todo（等上游）/ building（骨架，不转圈）/ ready（已生成）/ needs（等你确认）
 * 「needs」是唯一带行动的态 —— 交付区只在真正需要你的时候才打断你。
 */
import { computed } from 'vue'

const props = defineProps({
  items: { type: Array, default: () => [] },
  readyCount: { type: Number, default: 0 }
})

defineEmits(['confirm', 'revise'])

const stateText = (s) =>
  ({ todo: '等待', building: '生成中', ready: '已生成', needs: '待确认' }[s] || s)

const budgetMax = computed(() => {
  const b = props.items.find((d) => d.key === 'budget')?.data || []
  return Math.max(1, ...b.map((x) => x.value))
})
</script>

<style lang="less" scoped>
.dp { padding: 4px 0 24px; }

.dp__hd {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 0 16px 12px;
}
.dp__title {
  font-family: var(--font-display);
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-strong);
  margin: 0;
}
.dp__prog { margin-left: auto; font-size: 0.7rem; color: var(--text-faint); }

.dc {
  /* 与栏头文字的左边距对齐（栏头是 16px），否则卡片会比标题多出 4px 的错位 */
  margin: 0 16px 10px;
  padding: 12px 13px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-surface);
  transition: border-color 0.2s ease-out, opacity 0.2s ease-out;
}
.dc.is-todo { opacity: 0.5; }
.dc--needs { border-color: var(--gift-accent); border-left-width: 2px; }

.dc__hd {
  display: flex;
  align-items: baseline;
  gap: 9px;
}
.dc__label {
  font-size: 0.78rem;
  font-weight: 500;
  color: var(--text-strong);
}
.dc__state { margin-left: auto; font-size: 0.64rem; color: var(--text-faint); }
.dc__state.is-building { color: var(--text-muted); }
.dc__state.is-ready { color: var(--gift-accent); }
.dc__state.is-needs { color: var(--gift-accent); font-weight: 500; }
.dc__idle { font-size: 0.71rem; color: var(--text-faint); margin: 6px 0 0; }

/* 骨架：静态条 + 极轻呼吸，不用转圈 */
.sk { margin-top: 9px; display: flex; flex-direction: column; gap: 6px; }
.sk__bar {
  height: 7px;
  border-radius: 3px;
  background: var(--border);
  animation: sk 1.4s ease-in-out infinite;
}
@keyframes sk {
  0%, 100% { opacity: 0.55; }
  50% { opacity: 1; }
}
@media (prefers-reduced-motion: reduce) {
  .sk__bar { animation: none; }
}

.dc__lead {
  font-size: 0.81rem;
  font-weight: 500;
  color: var(--text-strong);
  margin: 8px 0 0;
}
.dc__sub {
  font-size: 0.72rem;
  line-height: 1.6;
  color: var(--text-muted);
  margin: 4px 0 0;
}

/* 礼盒方案 */
.pl { list-style: none; margin: 8px 0 0; padding: 0; }
.pl li {
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr) auto;
  gap: 2px 8px;
  padding: 6px 0;
  border-top: 1px solid var(--border);
}
.pl__role { font-size: 0.66rem; color: var(--gift-accent); }
.pl__name { font-size: 0.74rem; color: var(--text); }
.pl__p { font-size: 0.72rem; color: var(--text-muted); }
.pl__why {
  grid-column: 2 / -1;
  font-size: 0.68rem;
  line-height: 1.5;
  color: var(--text-faint);
}

/* 候选对比 */
.cmp { width: 100%; border-collapse: collapse; margin-top: 8px; }
.cmp th {
  text-align: left;
  font-size: 0.62rem;
  font-weight: 400;
  color: var(--text-faint);
  padding: 0 0 5px;
}
.cmp td { padding: 4px 0; border-top: 1px solid var(--border); font-size: 0.71rem; }
.cmp__n { color: var(--text); max-width: 92px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cmp tr.is-out .cmp__n { color: var(--text-faint); text-decoration: line-through; }
.fit {
  display: block;
  height: 3px;
  border-radius: 2px;
  background: var(--gift-accent);
  min-width: 4px;
}
.cmp tr.is-out .fit { background: var(--border-strong); }
.tag { font-size: 0.62rem; padding: 1px 6px; border-radius: 99px; }
.tag--in { color: var(--gift-accent); border: 1px solid var(--gift-accent-line); }
.tag--out { color: var(--text-faint); border: 1px solid var(--border); }

/* 预算分配 */
.bd {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  padding: 5px 0;
}
.bd__l { font-size: 0.71rem; color: var(--text-muted); }
.bd__bar { display: block; height: 5px; border-radius: 3px; background: var(--border); }
.bd__bar i { display: block; height: 100%; border-radius: 3px; background: var(--gift-accent); }
.bd__v { font-size: 0.71rem; color: var(--text); }

/* 寄语 */
.msg__tone { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
.tone {
  font-size: 0.66rem;
  padding: 1px 8px;
  border-radius: 99px;
  border: 1px solid var(--gift-accent-line);
  color: var(--gift-accent);
}
.msg__hint { font-size: 0.64rem; color: var(--text-faint); }
.msg__text {
  font-size: 0.76rem;
  line-height: 1.75;
  color: var(--text);
  margin: 8px 0 0;
  white-space: pre-line;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--bg-base);
}

/* 货源 */
.sp {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 1px 8px;
  padding: 6px 0;
  border-top: 1px solid var(--border);
}
.sp__i { font-size: 0.72rem; color: var(--text); }
.sp__e { font-size: 0.7rem; color: var(--text-muted); }
.sp__f, .sp__n { grid-column: 1 / -1; font-size: 0.66rem; color: var(--text-faint); }

/* 订单 */
.od__sum { display: flex; align-items: baseline; gap: 9px; margin-top: 8px; }
.od__t { font-size: 1.1rem; font-weight: 600; color: var(--text-strong); }
.od__b { font-size: 0.68rem; color: var(--text-faint); }
.od__bar {
  display: block;
  height: 5px;
  border-radius: 3px;
  background: var(--border);
  margin-top: 7px;
}
.od__bar i { display: block; height: 100%; border-radius: 3px; background: var(--gift-accent); }
.od__eta { font-size: 0.7rem; color: var(--text-muted); margin: 7px 0 0; }
.od__steps {
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 5px 12px;
}
.od__steps li {
  font-size: 0.68rem;
  color: var(--text-muted);
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.od__steps .mono {
  font-size: 0.62rem;
  color: var(--gift-accent);
  border: 1px solid var(--gift-accent-line);
  border-radius: 99px;
  width: 14px;
  height: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.od__acts { display: flex; gap: 8px; margin-top: 12px; }

.btn {
  font-family: var(--font-body);
  font-size: 0.74rem;
  padding: 6px 14px;
  border-radius: 8px;
  border: 1px solid var(--border-strong);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: color 0.15s ease-out, border-color 0.15s ease-out, background-color 0.15s ease-out;
}
.btn:hover { color: var(--text); }
.btn--primary {
  background: var(--gift-accent);
  border-color: var(--gift-accent);
  color: var(--bg-surface);
  font-weight: 500;
}
.btn--primary:hover { color: var(--bg-surface); opacity: 0.9; }
.btn:focus-visible,
.od__acts button:focus-visible {
  outline: 2px solid var(--gift-accent);
  outline-offset: 2px;
}
</style>
