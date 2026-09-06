<template>
  <div class="tool-output-view">
    <!-- 数组：每项一行，首字段加粗 + 其余字段小字 -->
    <template v-if="kind === 'array'">
      <div v-for="(row, ri) in rows" :key="ri" class="to-row">
        <span v-for="(val, key) in row.head" :key="key" class="to-cell">
          <b>{{ key }}:</b> <span class="to-val" :class="{ mono: isMono(val) }">{{ fmt(val) }}</span>
        </span>
      </div>
    </template>

    <!-- 平面对象：键值对；值为数组的键展开成行列表 -->
    <template v-else-if="kind === 'object'">
      <template v-for="(val, key) in obj" :key="key">
        <template v-if="isArr(val)">
          <div class="to-kv to-kv-arr">
            <span class="to-key">{{ key }}</span>
            <span class="to-arr-count mono">{{ val.length }} 项</span>
          </div>
          <div v-for="(row, ri) in arrRows(val)" :key="key + '-' + ri" class="to-row">
            <span v-for="(v, k) in row.head" :key="k" class="to-cell">
              <b>{{ k }}:</b> <span class="to-val" :class="{ mono: isMono(v) }">{{ fmt(v) }}</span>
            </span>
          </div>
        </template>
        <div v-else class="to-kv">
          <span class="to-key">{{ key }}</span>
          <span class="to-val" :class="{ mono: isMono(val) }">{{ fmt(val) }}</span>
        </div>
      </template>
    </template>

    <!-- 纯文本 -->
    <template v-else-if="kind === 'text'">
      <p class="to-text">{{ text }}</p>
    </template>

    <!-- 兜底：格式化 JSON -->
    <pre v-else class="to-json">{{ raw }}</pre>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  output: { type: null, required: true }
})

// 解析（output 可能是对象，也可能是 JSON 字符串）
const parsed = computed(() => {
  if (typeof props.output === 'string') {
    try { return JSON.parse(props.output) } catch { return props.output }
  }
  return props.output
})

const kind = computed(() => {
  const p = parsed.value
  if (Array.isArray(p)) return 'array'
  if (p && typeof p === 'object') {
    const entries = Object.entries(p)
    // {type:'text', text} 形态当纯文本
    if (entries.length === 2 && entries[0][0] === 'type' && entries[1][0] === 'text' && entries[0][1] === 'text') return 'text'
    return 'object'
  }
  if (typeof p === 'string' && p.length < 2000) return 'text'
  return 'json'
})

const obj = computed(() => (kind.value === 'object' ? parsed.value : {}))
const text = computed(() => (kind.value === 'text' ? (typeof parsed.value === 'string' ? parsed.value : String(parsed.value.text || '')) : ''))

const rows = computed(() => {
  if (kind.value !== 'array') return []
  return arrRows(parsed.value)
})

const isArr = (v) => Array.isArray(v)
const arrRows = (arr) =>
  (arr || []).slice(0, 8).map((item) => {
    if (item && typeof item === 'object') {
      // 挑出 1-3 个"首字段"：跳过元数据字段，取前两个有值的
      const skip = /^(id|_id|type|kind)$/i
      const keys = Object.keys(item).filter((k) => !skip.test(k))
      const headKeys = keys.slice(0, 2)
      return { head: Object.fromEntries(headKeys.map((k) => [k, item[k]])) }
    }
    return { head: { value: item } }
  })

const isMono = (v) => typeof v === 'number' || /^[¥￥]?[\d,，.]+$/.test(String(v))
const fmt = (v) => {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'object') return JSON.stringify(v).slice(0, 80)
  const s = String(v)
  return s.length > 200 ? s.slice(0, 200) + '…' : s
}
const raw = computed(() => {
  try { return JSON.stringify(parsed.value, null, 2).slice(0, 5000) } catch { return String(props.output) }
})
</script>

<style lang="less" scoped>
.tool-output-view {
  font-size: 0.76rem;
  line-height: 1.55;
  color: var(--text);
}

/* 数组行 */
.to-row {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 16px;
  padding: 4px 0;
  border-bottom: 1px solid var(--border);
  &:last-child { border-bottom: none; }
}
.to-cell {
  min-width: 0;
  b { font-weight: 600; color: var(--text-faint); font-size: 0.7rem; margin-right: 2px; }
}

/* 键值 */
.to-kv {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 4px 14px;
  padding: 2px 0;
  .to-key { color: var(--text-faint); font-size: 0.7rem; white-space: nowrap; }
}
.to-kv-arr {
  .to-key { font-weight: 600; }
  .to-arr-count { color: var(--text-faint); }
}
.to-kv-arr + .to-row {
  padding-left: 10px;
  border-left: 2px solid var(--border);
  margin-left: 2px;
  margin-bottom: 2px;
}
.to-val { word-break: break-word; }
.to-val.mono { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }

.to-text { margin: 0; color: var(--text); white-space: pre-wrap; }

.to-json {
  margin: 0;
  font-family: var(--font-mono);
  font-size: 0.7rem;
  line-height: 1.6;
  color: var(--text-muted);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 200px;
  overflow-y: auto;
}
</style>
