<template>
  <aside class="cur">
    <div class="cur__hd">
      <span class="cur__who">策展人</span>
      <span class="cur__rule" />
    </div>

    <div class="cur__body">
      <!-- 应答态：用户刚在某个物件上提过要求 -->
      <template v-if="reply">
        <p class="cur__reply">{{ reply }}</p>

        <div class="cur__opts">
          <button
            v-for="o in options"
            :key="o.id"
            class="cur__opt"
            type="button"
            @click="$emit('pick', o)"
          >
            <span class="cur__on">{{ o.name }}</span>
            <span class="cur__od">{{ o.note }}</span>
            <span class="cur__op mono">{{ o.price ? '¥' + o.price : '含' }}</span>
          </button>
        </div>

        <button class="gbtn cur__cancel" type="button" @click="$emit('cancel')">先不改</button>
      </template>

      <!-- 常态：叙事，不是可增长的列表 -->
      <template v-else>
        <div v-for="n in notes" :key="n.id" class="cur__note">
          <span class="cur__tag">{{ n.tag }}</span>
          <p class="cur__tx">{{ n.text }}</p>
        </div>

        <!-- 依据：来自 memory_manager 的偏好信号，不随改动增长 -->
        <div v-if="evidence.length" class="cur__ev">
          <span class="cur__evh">依据</span>
          <p v-for="e in evidence" :key="e.text" class="cur__evi">
            <span class="cur__evk">{{ e.kind }}</span>{{ e.text }}
          </p>
        </div>

        <p v-if="hidden > 0" class="cur__more">另有 {{ hidden }} 段推理在「思考」里</p>
        <p v-else-if="notes.length <= 1" class="cur__idle">
          点物件旁的圆圈，可以就地跟我说要改什么
        </p>
      </template>
    </div>
  </aside>
</template>

<script setup>
/**
 * 策展人旁白 —— 右侧这一栏是「自然语言叙事」，不是数据面板。
 * 这是与采购页分屏最本质的区别：那边右栏是参数对比，这边右栏是「为什么」。
 *
 * ⚠️ 硬约束（见设计方案 §09）：它绝不能变成第二条流水账。
 * 所以 notes 由父级裁剪到最多 2 条，更早的下沉到底部「改动记录」，
 * 这里只用一个计数提示，不做可增长列表、也不自己做滚动加载。
 *
 * 同一个位置承担「应答」职责：用户在物件上提问后，策展人在这里回答并给出同类目候选。
 * 这样候选不需要新开弹层，页面高度也不会因为多一个面板而变化。
 */
defineProps({
  /** [{ id, tag, text }]，父级已裁到 ≤2 条 */
  notes: { type: Array, default: () => [] },
  /** 被折叠进「思考」时间线的推理段数 */
  hidden: { type: Number, default: 0 },
  /** 来自 agent 的依据事件（memory_manager 的偏好信号），条数固定 */
  evidence: { type: Array, default: () => [] },
  reply: { type: String, default: '' },
  options: { type: Array, default: () => [] }
})

defineEmits(['pick', 'cancel'])
</script>

<style lang="less" scoped>
.cur {
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
}

.cur__hd {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
}
.cur__who {
  font-size: 0.72rem;
  letter-spacing: 0.06em;
  color: var(--text-faint);
  flex: 0 0 auto;
}
.cur__rule {
  flex: 1;
  height: 1px;
  background: var(--border);
}

.cur__body {
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.cur__note {
  border-left: 2px solid var(--gift-accent-line);
  padding: 2px 0 2px 11px;
  animation: cur-in 0.24s ease-out both;
}
@keyframes cur-in {
  from { opacity: 0; transform: translateY(5px); }
  to   { opacity: 1; transform: none; }
}
@media (prefers-reduced-motion: reduce) {
  .cur__note { animation: none; }
}

.cur__tag {
  font-size: 0.68rem;
  color: var(--gift-accent);
}
.cur__tx {
  font-size: 0.79rem;
  line-height: 1.7;
  color: var(--text);
  margin: 3px 0 0;
}

.cur__more,
.cur__idle {
  font-size: 0.72rem;
  line-height: 1.6;
  color: var(--text-faint);
  margin: 2px 0 0;
}

/* 依据块：与叙事区分开 —— 这是 agent 从档案里取到的事实，不是它说的话 */
.cur__ev {
  margin-top: 4px;
  padding-top: 10px;
  border-top: 1px solid var(--border);
}
.cur__evh {
  font-size: 0.68rem;
  letter-spacing: 0.06em;
  color: var(--text-faint);
}
.cur__evi {
  font-size: 0.73rem;
  line-height: 1.6;
  color: var(--text-muted);
  margin: 5px 0 0;
}
.cur__evk {
  display: inline-block;
  font-size: 0.64rem;
  padding: 0 5px;
  margin-right: 6px;
  border-radius: 3px;
  border: 1px solid var(--border-strong);
  color: var(--text-faint);
}

/* 应答态 */
.cur__reply {
  font-size: 0.79rem;
  line-height: 1.7;
  color: var(--text);
  margin: 0;
}
.cur__opts {
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.cur__opt {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 2px 10px;
  text-align: left;
  font-family: var(--font-body);
  padding: 9px 11px;
  border: 1px solid var(--border-strong);
  border-radius: 9px;
  background: var(--bg-surface);
  cursor: pointer;
  transition: border-color 0.15s ease-out;
}
.cur__opt:hover { border-color: var(--gift-accent); }
.cur__on { font-size: 0.8rem; font-weight: 500; color: var(--text-strong); }
.cur__od { grid-column: 1; font-size: 0.71rem; line-height: 1.55; color: var(--text-muted); }
.cur__op { grid-column: 2; grid-row: 1; font-size: 0.74rem; color: var(--text-muted); }

.cur__cancel { align-self: flex-start; }
</style>
