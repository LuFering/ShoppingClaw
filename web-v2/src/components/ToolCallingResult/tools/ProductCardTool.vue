<template>
  <div class="product-cards-container">
    <div v-if="cards.length === 0" class="empty-state">
      <span>暂无商品数据</span>
    </div>
    
    <div v-else class="cards-list">
      <a
        v-for="(card, index) in cards" 
        :key="index"
        :href="card.url || '#'"
        target="_blank"
        rel="noopener"
        class="product-card"
      >
        <!-- 商品图片 -->
        <div class="card-image-wrapper">
          <img 
            v-if="card.image_url" 
            :src="card.image_url" 
            :alt="card.title"
            class="card-image"
            loading="lazy"
            @error="$event.target.style.display='none'"
          />
          <div v-if="!card.image_url" class="image-placeholder">
            <ImageIcon :size="32" />
          </div>
        </div>
        
        <!-- 商品信息 -->
        <div class="card-body">
          <div class="card-title" :title="card.title">{{ card.title }}</div>
          
          <div class="card-meta">
            <span class="platform-badge" :class="platformClass(card.platform)">
              {{ platformLabel(card.platform) }}
            </span>
            <span v-if="card.rating" class="rating">
              <StarIcon :size="13" class="star-icon" />
              {{ card.rating }}
            </span>
            <span v-if="card.shop_name" class="shop-name">{{ card.shop_name }}</span>
          </div>
          
          <div class="card-price">
            <span class="price-symbol">¥</span>
            <span class="price-value">{{ formatPrice(card.price) }}</span>
            <span v-if="card.original_price && card.original_price > card.price" class="price-original">
              ¥{{ formatPrice(card.original_price) }}
            </span>
          </div>
        </div>
        
        <!-- 箭头指示可点击 -->
        <div class="card-arrow">
          <ChevronRightIcon :size="18" />
        </div>
      </a>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { ImageIcon, Star, ChevronRight } from 'lucide-vue-next'

const StarIcon = Star
const ChevronRightIcon = ChevronRight

const props = defineProps({
  toolCall: {
    type: Object,
    required: true
  }
})

// 解析工具返回的结构化数据
const cards = computed(() => {
  const content = props.toolCall.tool_call_result?.content
  if (!content) return []
  
  try {
    const data = typeof content === 'string' ? JSON.parse(content) : content
    return data.cards || []
  } catch (e) {
    console.error('[ProductCardTool] 解析失败:', e)
    return []
  }
})

// 平台标签映射
const platformMap = {
  jd: { label: '京东', cls: 'jd' },
  taobao: { label: '淘宝', cls: 'taobao' },
  tmall: { label: '天猫', cls: 'tmall' },
  pdd: { label: '拼多多', cls: 'pdd' },
  suning: { label: '苏宁', cls: 'suning' },
}

const platformLabel = (platform) => {
  return platformMap[platform]?.label || platform || '商城'
}

const platformClass = (platform) => {
  return platformMap[platform]?.cls || 'default'
}

// 格式化价格
const formatPrice = (price) => {
  const num = parseFloat(price)
  if (isNaN(num)) return '0.00'
  // 整数价格不显示小数
  return num % 1 === 0 ? num.toFixed(0) : num.toFixed(2)
}
</script>

<style scoped lang="less">
.product-cards-container {
  padding: 4px 0;
}

.empty-state {
  text-align: center;
  color: var(--text-tertiary, #9ca3af);
  padding: 16px;
  font-size: 13px;
}

.cards-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.product-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  background: var(--bg-primary, #ffffff);
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 10px;
  text-decoration: none;
  color: inherit;
  transition: all 0.2s ease;
  cursor: pointer;
  
  &:hover {
    border-color: var(--main-500, #3b82f6);
    box-shadow: 0 2px 8px rgba(59, 130, 246, 0.1);
    
    .card-arrow {
      opacity: 1;
      transform: translateX(0);
    }
  }
}

// ── 图片 ──
.card-image-wrapper {
  flex-shrink: 0;
  width: 80px;
  height: 80px;
  border-radius: 8px;
  overflow: hidden;
  background: var(--bg-secondary, #f3f4f6);
}

.card-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.image-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-tertiary, #d1d5db);
}

// ── 主体信息 ──
.card-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, #111827);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
}

// ── 元信息行 ──
.card-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.platform-badge {
  font-size: 11px;
  padding: 2px 7px;
  border-radius: 4px;
  font-weight: 500;
  white-space: nowrap;
  
  &.jd {
    background: #fef2f2;
    color: #dc2626;
  }
  &.taobao {
    background: #fff7ed;
    color: #ea580c;
  }
  &.tmall {
    background: #fdf4ff;
    color: #c026d3;
  }
  &.pdd {
    background: #fef2f2;
    color: #dc2626;
  }
  &.suning {
    background: #eff6ff;
    color: #2563eb;
  }
  &.default {
    background: var(--bg-secondary, #f3f4f6);
    color: var(--text-secondary, #6b7280);
  }
}

.rating {
  display: flex;
  align-items: center;
  gap: 3px;
  font-size: 12px;
  color: #f59e0b;
  font-weight: 500;
  
  .star-icon {
    flex-shrink: 0;
  }
}

.shop-name {
  font-size: 11px;
  color: var(--text-tertiary, #9ca3af);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100px;
}

// ── 价格 ──
.card-price {
  display: flex;
  align-items: baseline;
  gap: 1px;
}

.price-symbol {
  font-size: 13px;
  font-weight: 600;
  color: #ef4444;
}

.price-value {
  font-size: 19px;
  font-weight: 700;
  color: #ef4444;
  line-height: 1;
}

.price-original {
  font-size: 11px;
  color: var(--text-tertiary, #9ca3af);
  text-decoration: line-through;
  margin-left: 6px;
}

// ── 箭头 ──
.card-arrow {
  flex-shrink: 0;
  color: var(--text-tertiary, #9ca3af);
  opacity: 0.4;
  transform: translateX(-4px);
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
}
</style>
