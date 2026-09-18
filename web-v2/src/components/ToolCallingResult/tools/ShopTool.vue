<template>
  <BaseToolCall
    :tool-call="toolCall"
    :appearance="appearance"
    :default-expanded="defaultExpanded"
    :force-show-result="hasDetail"
  >
    <!-- 头部：工具中文名 + 一行可读描述（Yuxi sep-header 风格）。
         运行中显示「在查什么」（来自参数），完成后显示「查到了什么」（来自 result_preview）。 -->
    <template #header>
      <div class="sep-header">
        <span class="note">{{ toolName }}</span>
        <span class="separator" v-if="description">|</span>
        <span class="description">{{ description }}</span>
      </div>
    </template>

    <!-- 结果：结构化可读，而非裸 JSON -->
    <template #result>
      <div class="shop-tool-result">
        <!-- 商品 / 候选列表 -->
        <div v-if="products.length" class="product-rows">
          <div v-for="(p, i) in products.slice(0, 8)" :key="i" class="product-row">
            <span class="pr-name">{{ p.title || p.name }}</span>
            <span class="pr-meta">
              <span v-if="p.shop_name || p.shop" class="pr-shop">{{ p.shop_name || p.shop }}</span>
              <span v-if="p.platform" class="pr-platform">{{ platformLabel(p.platform) }}</span>
            </span>
            <span v-if="p.price != null" class="pr-price">¥{{ fmtPrice(p.price) }}</span>
          </div>
          <div v-if="products.length > 8" class="product-more">+{{ products.length - 8 }} 件</div>
        </div>

        <!-- 一行摘要（后端 result_preview / 非结构化文本）。
             形如「找到 12 件候选：茶具 5 / 茶叶 4 / 书 3」时结构化成分类 chips。 -->
        <div v-else-if="previewText" class="result-preview">
          <template v-if="previewChips">
            <div class="rp-headline">{{ previewChips.headline }}</div>
            <div class="rp-chips">
              <span v-for="(c, i) in previewChips.chips" :key="i" class="rp-chip">{{ c }}</span>
            </div>
          </template>
          <template v-else>{{ previewText }}</template>
        </div>

        <!-- 兜底：结构化 JSON（可滚） -->
        <pre v-else class="result-json">{{ formatResult(output) }}</pre>
      </div>
    </template>
  </BaseToolCall>
</template>

<script setup>
import { computed } from 'vue'
import BaseToolCall from '../BaseToolCall.vue'
import { getToolCallId, getToolName, getToolCallStatus, parseToolCallArgs } from '../toolRegistry'
import { parseProductCards } from '@/utils/productCard'

const props = defineProps({
  toolCall: {
    type: Object,
    required: true
  },
  appearance: {
    type: String,
    default: 'card'
  },
  defaultExpanded: {
    type: Boolean,
    default: false
  }
})

const toolId = computed(() => getToolCallId(props.toolCall))
const toolName = computed(() => getToolName(toolId.value))
const status = computed(() => getToolCallStatus(props.toolCall))

const output = computed(
  () =>
    props.toolCall?.output ??
    props.toolCall?.result ??
    props.toolCall?.tool_call_result?.content ??
    null
)

const parsed = computed(() => {
  const c = output.value
  if (typeof c === 'string') {
    try {
      return JSON.parse(c)
    } catch {
      return null
    }
  }
  return c
})

// 尽可能把结果识别成商品列表（兼容 products / items / goods / cards 多种字段名 + product_card 结构）
const products = computed(() => {
  const c = parsed.value
  if (Array.isArray(c) && c.length) return c
  if (c && Array.isArray(c.products) && c.products.length) return c.products
  if (c && Array.isArray(c.items) && c.items.length) return c.items
  if (c && Array.isArray(c.goods) && c.goods.length) return c.goods
  if (c && Array.isArray(c.cards) && c.cards.length) return c.cards
  const pc = parseProductCards(output.value)
  return pc || []
})

const previewText = computed(() => {
  const rp = props.toolCall?.result_preview
  if (rp) return String(rp)
  const c = output.value
  if (typeof c === 'string' && !c.trim().startsWith('{')) return c
  const p = parsed.value
  if (p && (p.result_preview || p.summary || p.preview)) return p.result_preview || p.summary || p.preview
  return ''
})

// 「找到 12 件候选：茶具 5 / 茶叶 4 / 书 3」→ 标题 + 分类 chips
const previewChips = computed(() => {
  const m = previewText.value.match(/找到\s*(\d+)\s*件候选[：:]\s*(.+)/)
  if (m) {
    const chips = m[2]
      .split('/')
      .map((s) => s.trim())
      .filter(Boolean)
    return { headline: `找到 ${m[1]} 件候选`, chips }
  }
  return null
})

// 运行中 / 失败态：从参数推断「在做什么」
const argHint = computed(() => {
  const a = parseToolCallArgs(props.toolCall) || {}
  if (a.keyword || a.q) {
    const kw = a.keyword || a.q
    return [kw, a.budget ? `预算 ¥${a.budget}` : ''].filter(Boolean).join(' · ')
  }
  if (a.items) return `对比：${Array.isArray(a.items) ? a.items.join('、') : a.items}`
  if (a.product || a.product_name) return a.product || a.product_name
  if (a.platform) return `平台：${a.platform}`
  if (a.sku || a.goods_id) return `SKU ${a.sku || a.goods_id}`
  if (a.category) return `品类：${a.category}`
  const entries = Object.entries(a)
    .slice(0, 2)
    .map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`)
  return entries.join(' · ')
})

const description = computed(() => {
  if (status.value === 'completed' && previewText.value) return previewText.value
  if (status.value === 'error') return props.toolCall?.error_message || argHint.value || '执行失败'
  return argHint.value
})

const hasDetail = computed(() => !!(products.value.length || previewText.value || output.value))

const platformMap = {
  jd: '京东',
  taobao: '淘宝',
  tmall: '天猫',
  pdd: '拼多多',
  suning: '苏宁'
}
const platformLabel = (p) => platformMap[p] || p || ''
const fmtPrice = (price) => {
  const n = parseFloat(price)
  if (isNaN(n)) return '0'
  return n % 1 === 0 ? n.toFixed(0) : n.toFixed(2)
}
const formatResult = (data) => {
  if (typeof data === 'object') return JSON.stringify(data, null, 2)
  return String(data)
}
</script>

<style scoped lang="less">
.shop-tool-result {
  padding: 2px 0;

  .product-rows {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .product-row {
    display: flex;
    align-items: baseline;
    gap: 8px;
    font-size: 12px;
    line-height: 1.4;

    .pr-name {
      flex: 1;
      min-width: 0;
      color: var(--gray-800);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .pr-meta {
      display: flex;
      gap: 6px;
      flex-shrink: 0;
      color: var(--gray-500);
      font-size: 11px;
    }

    .pr-price {
      flex-shrink: 0;
      color: #ef4444;
      font-weight: 600;
      font-variant-numeric: tabular-nums;
    }
  }

  .product-more {
    font-size: 11px;
    color: var(--gray-400);
  }

  .result-preview {
    font-size: 12px;
    line-height: 1.5;
    color: var(--gray-700);
    background: var(--gray-25);
    border-radius: 6px;
    padding: 8px 10px;
    white-space: pre-wrap;
    word-break: break-word;
  }

  .result-json {
    margin: 0;
    font-size: 12px;
    line-height: 1.4;
    color: var(--gray-700);
    white-space: pre-wrap;
    word-break: break-word;
    max-height: 300px;
    overflow-y: auto;
    background: var(--gray-25);
    padding: 10px;
    border-radius: 4px;
    font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  }
}
</style>
