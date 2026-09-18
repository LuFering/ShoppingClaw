<template>
  <BaseToolCall
    :tool-call="toolCall"
    :appearance="appearance"
    :default-expanded="true"
    :force-show-result="hasTrace"
    hide-params
  >
    <template #header>
      <div class="sep-header">
        <span class="note">主智能体编排</span>
        <span class="separator">|</span>
        <span class="description">{{ headline }}</span>
      </div>
    </template>

    <template #result>
      <div class="orch-wrap">
        <!-- 渐进显形：已走完的分区显示为完成，正在推进的分区显示为加载中 -->
        <!--
          ⚠️ 2026-09-18 起刻意**不渲染**「意图分诊 / 置信度」那一档。
          原因（用户实测结论）：让模型直接理解语境，好过先跑一遍判定；
          把判定结论摆给用户看，既没信息量，也把内部决策口吻漏进了对话。
          本卡只呈现「执行事实」：用了哪些 Skill、查了哪些资料、派了谁。
        -->
        <div v-if="skills.length" class="orch-block">
          <div class="orch-label"><Sparkles :size="12" class="orch-icon" /> 使用 Skill</div>
          <ul class="orch-list orch-list--chips">
            <li v-for="(s, i) in skills" :key="`s-${i}`">
              <span class="orch-chip">{{ s.name }}</span>
              <span v-if="s.detail" class="orch-chip-detail">{{ s.detail }}</span>
            </li>
          </ul>
        </div>

        <div v-if="rag.length" class="orch-block">
          <div class="orch-label"><Database :size="12" class="orch-icon" /> 检索 RAG</div>
          <ul class="orch-list">
            <li v-for="(r, i) in rag" :key="`r-${i}`">
              <span class="orch-dot" :class="r.done === false ? 'is-loading' : 'is-done'"></span>
              <span class="orch-name">{{ r.name }}</span>
              <span v-if="r.detail" class="orch-detail">{{ r.detail }}</span>
            </li>
          </ul>
        </div>

        <div v-if="mcp.length" class="orch-block">
          <div class="orch-label"><Server :size="12" class="orch-icon" /> 调用 MCP</div>
          <ul class="orch-list">
            <li v-for="(m, i) in mcp" :key="`m-${i}`">
              <span class="orch-dot" :class="m.done === false ? 'is-loading' : 'is-done'"></span>
              <span class="orch-name">{{ m.name }}</span>
              <span v-if="m.detail" class="orch-detail">{{ m.detail }}</span>
            </li>
          </ul>
        </div>

        <!-- ④ 派遣清单：派谁、干什么、并行还是串行、超时上限 -->
        <div v-if="dispatch.length" class="orch-block">
          <div class="orch-label">
            <Send :size="12" class="orch-icon" />
            派遣 {{ parallel ? '并行' : '串行' }} {{ dispatch.length }} 个子智能体
          </div>
          <ul class="orch-list">
            <li v-for="(d, i) in dispatch" :key="`d-${i}`">
              <span class="orch-dot" :class="d.done === false ? 'is-loading' : 'is-done'"></span>
              <span class="orch-name">{{ d.slug }}</span>
              <span class="orch-detail">
                {{ d.task }}
                <em v-if="d.timeout_ms" class="orch-dim">
                  · 上限 {{ Math.round(d.timeout_ms / 1000) }}s
                </em>
                <em v-if="d.depends_on && d.depends_on.length" class="orch-dim">
                  · 依赖 {{ d.depends_on.join('、') }}
                </em>
              </span>
            </li>
          </ul>
        </div>
        <!--
          ⚠️ 2026-09-18 删掉了「本轮不派遣 —— 先反问澄清」这一块。
          理由：卡上只留「执行事实」。没派遣就是没派遣，画一个空缺位反而是
          把内部判定摆到台面上；反问本身由对话正文承载，不需要卡片复述。
        -->

        <!-- 还没走到下一步时的加载态：让「正在执行」可见，而不是干等 -->
        <div v-if="pendingLabel" class="orch-pending">
          <span class="orch-dot is-loading"></span>
          <span>{{ pendingLabel }}</span>
        </div>

        <div v-if="decision" class="orch-decision">
          <span class="orch-label-inline">派遣决策</span>
          <span class="orch-decision-text">{{ decision }}</span>
        </div>

        <p class="orch-note">
          {{ guardNote }}
        </p>
      </div>
    </template>
  </BaseToolCall>
</template>

<script setup>
import { computed } from 'vue'
import { Sparkles, Database, Server, Send } from 'lucide-vue-next'
import BaseToolCall from '../BaseToolCall.vue'
import { parseToolCallArgs } from '../toolRegistry'

const props = defineProps({
  toolCall: { type: Object, required: true },
  appearance: { type: String, default: 'card' },
  defaultExpanded: { type: Boolean, default: false }
})

// 结果优先（tool_complete 的完整轨迹），运行中回退到参数（tool_start 的计划）
const rawResult = computed(
  () =>
    props.toolCall.tool_call_result?.content ??
    props.toolCall.result ??
    props.toolCall.output ??
    props.toolCall.result_preview ??
    null
)

const orch = computed(() => {
  const raw = rawResult.value
  if (raw) {
    try {
      const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
      const data = parsed?.orchestration || parsed?.data || parsed
      if (data && typeof data === 'object') return data
    } catch {
      /* 非 JSON → 回退参数 */
    }
  }
  return props.toolCall.orchestration || parseToolCallArgs(props.toolCall) || {}
})

const skills = computed(() => (Array.isArray(orch.value.skills) ? orch.value.skills.filter(Boolean) : []))
const rag = computed(() => (Array.isArray(orch.value.rag) ? orch.value.rag.filter(Boolean) : []))
const mcp = computed(() => (Array.isArray(orch.value.mcp) ? orch.value.mcp.filter(Boolean) : []))
const decision = computed(() => orch.value.decision || orch.value.plan || '')
const hasTrace = computed(
  () =>
    skills.value.length ||
    rag.value.length ||
    mcp.value.length ||
    dispatch.value.length ||
    Boolean(decision.value)
)

// ── 意图分诊 / 置信度：已下线（2026-09-18）──
// 曾经的 intent / confidence / confidenceText / confClass / slotList / needClarify
// / SLOT_LABEL 全部删除：后端不再下发 `intent` 字段，卡上也不再展示判定结论。

// ── 派遣清单 ──
const dispatch = computed(() =>
  Array.isArray(orch.value.dispatch) ? orch.value.dispatch.filter(Boolean) : []
)
const parallel = computed(() =>
  dispatch.value.length > 1 && dispatch.value.some((d) => d.parallel)
)
// 派遣清单：只有真的派了才渲染（没派遣时不再画空位，见模板注释）

// ── 护栏 ──
const guardNote = computed(() => {
  const g = orch.value.guardrails
  if (g && typeof g === 'object' && g.note) return g.note
  return '主智能体只做编排，不直接检索商品 / 下单 / 查物流——这些都在子智能体里执行。'
})

const headline = computed(() => {
  if (decision.value) return decision.value
  const parts = []
  if (skills.value.length) parts.push(`${skills.value.length} 个 Skill`)
  if (rag.value.length) parts.push(`${rag.value.length} 个 RAG`)
  if (mcp.value.length) parts.push(`${mcp.value.length} 个 MCP`)
  return parts.length ? parts.join(' · ') : '编排中'
})

// ── 渐进显形 ──
// 后端在 running 期间按 ORCHESTRATION_REVEAL_STEPS 的顺序，
// 用同一个 tool_call_id 反复发 tool_start，每次多露出一个分区（trace.step 递增）。
// 这里据此显示「下一步正在推进」的加载态，让执行过程可见。
const REVEAL_ORDER = ['skills', 'rag', 'mcp', 'dispatch', 'decision']
const STEP_LABEL = {
  skills: '正在匹配 Skill…',
  rag: '正在检索 RAG…',
  mcp: '正在调用 MCP…',
  dispatch: '正在决定派遣…',
  decision: '正在收口决策…'
}
const step = computed(() => {
  const v = orch.value.step
  return typeof v === 'number' ? v : null
})
// 只有 running 且未显形完时才显示加载态；completed 一律不显示
const pendingLabel = computed(() => {
  if (props.toolCall.status && props.toolCall.status !== 'running') return ''
  if (step.value == null) return ''
  const next = REVEAL_ORDER[step.value]
  return next ? STEP_LABEL[next] || '' : ''
})
</script>

<style lang="less" scoped>
.sep-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  width: 100%;
  overflow: hidden;

  .note { font-weight: 500; color: var(--gray-600); flex-shrink: 0; }
  .separator { color: var(--gray-300); flex-shrink: 0; }
  .description {
    color: var(--gray-600);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-width: 0;
  }
}

.orch-wrap {
  display: flex;
  flex-direction: column;
  gap: 9px;
  padding: 10px 12px;
  background: var(--gray-0);
  border-radius: 8px;
}

.orch-block { display: flex; flex-direction: column; gap: 4px; }

.orch-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 600;
  color: var(--gray-500);
}

.orch-label-inline {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 600;
  color: var(--gray-500);
}

.orch-icon { color: var(--gray-400); flex-shrink: 0; }

.orch-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 3px;

  li {
    display: flex;
    align-items: baseline;
    gap: 6px;
    font-size: 12px;
    min-width: 0;
  }

  &.orch-list--chips {
    flex-direction: row;
    flex-wrap: wrap;
    gap: 4px;
  }
}

.orch-dot {
  flex-shrink: 0;
  width: 6px;
  height: 6px;
  margin-top: 5px;
  border-radius: 50%;
  background: var(--main-600);

  &.is-done { background: var(--color-success-500); }
}

.orch-name {
  flex-shrink: 0;
  font-weight: 600;
  color: var(--main-700);
}

.orch-detail {
  min-width: 0;
  font-size: 12px;
  color: var(--gray-600);
  word-break: break-word;
}

.orch-chip {
  display: inline-block;
  padding: 0 8px;
  font-size: 11px;
  line-height: 18px;
  border-radius: 999px;
  color: var(--gray-700);
  background: var(--gray-100);
}

.orch-chip--strong {
  color: var(--main-700);
  background: var(--main-50, var(--gray-100));
  font-weight: 600;
}

.orch-chip-detail {
  font-size: 11px;
  color: var(--gray-500);
}

/* ⚠️ 2026-09-18 起不再需要 .orch-intent-line / .orch-conf / .orch-clarify：
   意图分诊与置信度已下线，这三个类没有任何模板引用了。 */

.orch-dim {
  font-style: normal;
  color: var(--gray-400);
}

.orch-decision {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding-top: 6px;
  border-top: 1px solid var(--gray-100);

  .orch-decision-text {
    min-width: 0;
    font-size: 12px;
    color: var(--gray-800);
    word-break: break-word;
  }
}

.orch-note {
  margin: 0;
  font-size: 11px;
  line-height: 1.5;
  color: var(--gray-400);
}

/* ── 渐进显形的加载态 ── */
.orch-pending {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--gray-500);
}

.orch-dot.is-loading {
  background: var(--gray-300);
  animation: orch-pulse 1.1s ease-in-out infinite;
}

@keyframes orch-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}

@media (prefers-reduced-motion: reduce) {
  .orch-dot.is-loading { animation: none; }
}
</style>
