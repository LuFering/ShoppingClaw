<template>
  <!-- 子智能体卡片默认展开：执行轨迹（工具/RAG/Skill）与交付结果一眼可见 -->
  <BaseToolCall :tool-call="toolCall" :default-expanded="true">
    <template #header>
      <div class="sep-header">
        <span class="subagent">{{ subagentDisplayName }}</span>
        <span v-if="runStatusLabel" class="run-status" :class="runStatusClass">{{ runStatusLabel }}</span>
        <span class="separator" v-if="shortDescription">|</span>
        <span class="description" v-if="shortDescription">{{ shortDescription }}</span>
      </div>
    </template>

    <template #params>
      <div class="task-detail">
        <div v-if="description" class="task-description">{{ description }}</div>

        <!-- 执行详情：子智能体内部到底在做什么。
             运行中即可展开查看（tool_start 的轨迹即计划，tool_complete 后定格为实际执行）。 -->
        <div v-if="hasTrace" class="exec-trace">
          <div v-if="runTools.length" class="exec-block">
            <div class="exec-label">
              <Wrench :size="12" class="exec-icon" />
              <span>调用工具</span>
            </div>
            <ul class="exec-list">
              <li v-for="(t, i) in runTools" :key="`tool-${i}`">
                <span
                  class="exec-dot"
                  :class="execItemClass(t.status)"
                ></span>
                <span class="exec-name">{{ t.name }}</span>
                <span v-if="t.detail" class="exec-detail">{{ t.detail }}</span>
              </li>
            </ul>
          </div>

          <div v-if="runRag.length" class="exec-block">
            <div class="exec-label">
              <Database :size="12" class="exec-icon" />
              <span>检索 RAG</span>
            </div>
            <ul class="exec-list">
              <li v-for="(r, i) in runRag" :key="`rag-${i}`">
                <span class="exec-dot" :class="r.done === false ? 'is-loading' : 'is-done'"></span>
                <span class="exec-name">{{ r.name }}</span>
                <span v-if="r.detail" class="exec-detail">{{ r.detail }}</span>
              </li>
            </ul>
          </div>

          <div v-if="runSkills.length" class="exec-block">
            <div class="exec-label">
              <Sparkles :size="12" class="exec-icon" />
              <span>使用 Skill</span>
            </div>
            <ul class="exec-list exec-list--chips">
              <li v-for="(sk, i) in runSkills" :key="`skill-${i}`">
                <span class="exec-chip">{{ sk.name }}</span>
              </li>
            </ul>
          </div>

          <!-- 渐进显形：还在跑的时候给出下一步的加载态，而不是让卡片静止 -->
          <div v-if="pendingLabel" class="exec-pending">
            <span class="exec-dot is-loading"></span>
            <span>{{ pendingLabel }}</span>
          </div>
        </div>
      </div>
    </template>

    <template #result="{ resultContent }">
      <div class="task-result">
        <MdPreview
          :modelValue="String(resultContent)"
          :theme="theme"
          previewTheme="github"
          class="md-preview-wrapper flat-md-preview"
        />
      </div>
    </template>
  </BaseToolCall>
</template>

<script setup>
import { computed } from 'vue'
import { Wrench, Database, Sparkles } from 'lucide-vue-next'
import BaseToolCall from '../BaseToolCall.vue'
import { MdPreview } from 'md-editor-v3'
import 'md-editor-v3/lib/preview.css'
import { useThemeStore } from '@/stores/theme'
import { parseToolCallArgs, getToolCallDisplayStatus, getToolName } from '../toolRegistry'

const props = defineProps({
  toolCall: {
    type: Object,
    required: true
  }
})

const themeStore = useThemeStore()
const theme = computed(() => (themeStore.isDark ? 'dark' : 'light'))

const parsedArgs = computed(() => parseToolCallArgs(props.toolCall))

// 子智能体展示名：优先运行记录名 > display_label > 参数中的 subagent_type > 工具名映射
const subagentRun = computed(() => props.toolCall.subagent_run || null)
const subagentDisplayName = computed(() => {
  return (
    subagentRun.value?.subagent_name ||
    props.toolCall.display_label ||
    parsedArgs.value.subagent_type ||
    parsedArgs.value.subagent ||
    getToolName('task') ||
    '子智能体'
  )
})

const description = computed(
  () => parsedArgs.value.description || subagentRun.value?.description || ''
)

// ═══ 执行轨迹：子智能体内部「调用了什么工具 / 检索了什么 RAG / 用了哪些 Skill」═══
// tool_start 携带的是计划（status: running），tool_complete 后定格为实际执行。
// 运行中展开即可看到，不必等子智能体跑完。
const runTools = computed(() => subagentRun.value?.tools || [])
const runRag = computed(() => subagentRun.value?.rag || [])
const runSkills = computed(() => subagentRun.value?.skills || [])
const hasTrace = computed(
  () => runTools.value.length > 0 || runRag.value.length > 0 || runSkills.value.length > 0
)

// 工具条目的状态点：轨迹未逐条下发状态时，按子智能体整体状态兜底
const execItemClass = (status) => {
  const raw = String(status || subagentRun.value?.status || '').toLowerCase()
  if (['completed', 'done', 'success'].includes(raw)) return 'is-done'
  if (['failed', 'error'].includes(raw)) return 'is-failed'
  return 'is-running'
}

// ── 渐进显形 ──
// 后端在子智能体干活期间，用同一个 tool_call_id 反复发 tool_start，
// 每次比上次多一个「已执行工具」/「已验证 RAG」。这里据此显示下一步加载态。
// 计划中的工具（plannedTools）里还没跑的，也给一个「等待/进行中」的提示。
const pendingPlanned = computed(() =>
  (subagentRun.value?.plannedTools || []).filter((p) => p.done === false)
)
const pendingLabel = computed(() => {
  const st = String(subagentRun.value?.status || '').toLowerCase()
  if (st === 'completed' || st === 'failed' || st === 'error') return ''
  const ragsLeft = runRag.value.filter((r) => r.done === false)
  if (ragsLeft.length) return `正在检索 ${ragsLeft[0].name}…`
  if (pendingPlanned.value.length) return `计划执行 ${pendingPlanned.value[0].name}…`
  return ''
})

// 运行状态（对标 Yuxi）：failed → error
const rawStatus = computed(() => getToolCallDisplayStatus(props.toolCall))
const runStatus = computed(() => (rawStatus.value === 'error' ? 'failed' : rawStatus.value))
const runStatusLabel = computed(() => {
  if (runStatus.value === 'completed') return '已完成'
  if (runStatus.value === 'failed') return '失败'
  if (runStatus.value === 'running') return '运行中'
  return ''
})
const runStatusClass = computed(() => ({
  'is-running': runStatus.value === 'running',
  'is-completed': runStatus.value === 'completed',
  'is-failed': runStatus.value === 'failed'
}))

const shortDescription = computed(() => {
  const desc = description.value
  if (!desc) return ''
  return desc.length > 50 ? desc.slice(0, 50) + '...' : desc
})
</script>

<style lang="less" scoped>
.sep-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  width: 100%;
  overflow: hidden;

  .subagent {
    font-weight: 600;
    color: var(--main-700);
    white-space: nowrap;
    flex-shrink: 0;
  }

  .run-status {
    flex-shrink: 0;
    font-size: 12px;
    padding: 1px 8px;
    border-radius: 999px;
    white-space: nowrap;
    &.is-running { background: var(--main-50); color: var(--main-700); }
    &.is-completed { background: var(--color-success-50, var(--gray-100)); color: var(--color-success-500, var(--gray-600)); }
    &.is-failed { background: var(--color-error-50); color: var(--color-error-500); }
  }
}

.task-description {
  border-radius: 8px;
  font-size: 13px;
  color: var(--gray-800);
}

.task-detail {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* ═══ 执行轨迹：调用工具 / 检索 RAG / 使用 Skill ═══ */
.exec-trace {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid var(--gray-100);
  border-radius: 8px;
  background: var(--gray-0);
}

.exec-block {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.exec-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 600;
  color: var(--gray-500);
}

.exec-icon {
  color: var(--gray-400);
  flex-shrink: 0;
}

.exec-list {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin: 0;
  padding: 0;
  list-style: none;

  li {
    display: flex;
    align-items: baseline;
    gap: 6px;
    min-width: 0;
    font-size: 12px;
    line-height: 1.45;
  }

  &.exec-list--chips {
    flex-direction: row;
    flex-wrap: wrap;
    gap: 4px;
  }
}

.exec-dot {
  flex-shrink: 0;
  width: 6px;
  height: 6px;
  margin-top: 5px;
  border-radius: 50%;
  background: var(--main-600);

  &.is-done {
    background: var(--color-success-500);
  }

  &.is-failed {
    background: var(--color-error-500);
  }

  &.is-running {
    animation: execDotPulse 1.2s ease-in-out infinite;
  }

  /* 渐进显形：这一步还没开始跑，用灰点 + 脉冲表示「在排队 / 正在进行」 */
  &.is-loading {
    background: var(--gray-300);
    animation: execDotPulse 1.2s ease-in-out infinite;
  }
}

/* 渐进显形的加载态行 */
.exec-pending {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--gray-500);
}

.exec-name {
  flex-shrink: 0;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--main-700);
}

.exec-detail {
  min-width: 0;
  font-size: 12px;
  color: var(--gray-600);
  word-break: break-word;
}

.exec-chip {
  display: inline-block;
  padding: 0 8px;
  font-size: 11px;
  line-height: 18px;
  border-radius: 999px;
  color: var(--gray-700);
  background: var(--gray-100);
}

@keyframes execDotPulse {
  0%,
  100% {
    opacity: 0.4;
  }
  50% {
    opacity: 1;
  }
}

.task-result {
  padding: 12px;
  background: var(--gray-0);
  border-radius: 8px;

  :deep(.md-editor-preview-wrapper) {
    padding: 0;
  }

  :deep(.md-editor-preview) {
    font-size: 14px;
    color: var(--gray-800);
    background: transparent;
  }
}
</style>
