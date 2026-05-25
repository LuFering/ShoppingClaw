<template>
  <div class="test-container">
    <h2>ProductCardTool 组件测试</h2>
    
    <!-- 测试数据1: 单个商品 -->
    <section class="test-section">
      <h3>测试1: 单个商品卡片</h3>
      <ProductCardTool :tool-call="mockToolCall1" />
    </section>

    <!-- 测试数据2: 多个商品 -->
    <section class="test-section">
      <h3>测试2: 多个商品卡片</h3>
      <ProductCardTool :tool-call="mockToolCall2" />
    </section>

    <!-- 测试数据3: 缺少图片的商品 -->
    <section class="test-section">
      <h3>测试3: 无图片商品</h3>
      <ProductCardTool :tool-call="mockToolCall3" />
    </section>

    <!-- 测试数据4: 空数据 -->
    <section class="test-section">
      <h3>测试4: 空数组</h3>
      <ProductCardTool :tool-call="mockToolCallEmpty" />
    </section>
  </div>
</template>

<script setup>
import ProductCardTool from '@/components/ToolCallingResult/tools/ProductCardTool.vue'

// Mock toolCall 结构
const createMockToolCall = (cards) => ({
  tool_call_result: {
    content: JSON.stringify({ cards })
  }
})

// 测试数据1: 完整商品
const mockToolCall1 = createMockToolCall([{
  title: "小米 REDMI Turbo 4 Pro 第四代骁龙8s 7550mAh长续航 12GB+512GB 白色",
  price: 1999.00,
  platform: "京东",
  url: "https://item.jd.com/100204343914.html",
  image_url: "https://img14.360buyimg.com/n1/jfs/t1/231593/29/25806/119770/67a9e5f1F5b8c6e8e/8c3f8e8e8e8e8e8e.jpg",
  rating: 4.8,
  shop_name: "小米京东自营旗舰店",
  sales_count: 10000,
  key_specs: {
    "处理器": "骁龙8s Gen3",
    "内存": "12GB",
    "存储": "512GB",
    "电池": "7550mAh"
  }
}])

// 测试数据2: 多个商品
const mockToolCall2 = createMockToolCall([
  {
    title: "vivo iQOO Z10 Turbo 12GB+256GB 云海白 天玑8400满血版",
    price: 1899.00,
    platform: "京东",
    url: "https://item.jd.com/100201589746.html",
    image_url: "https://img14.360buyimg.com/n1/jfs/t1/228093/31/18539/89956/67a1e5f2F6c7d8e9f/9d4e9f9f9f9f9f9f.jpg",
    rating: 4.9,
    shop_name: "vivo京东自营旗舰店",
    sales_count: 8500,
    key_specs: {
      "处理器": "天玑8400",
      "内存": "12GB",
      "存储": "256GB",
      "电池": "7620mAh"
    }
  },
  {
    title: "荣耀X70 焕新版 8+128 朱砂红十面抗摔 8300mAh青海湖电池",
    price: 1799.00,
    platform: "淘宝",
    url: "https://detail.tmall.com/item.htm?id=example",
    image_url: "https://img.alicdn.com/imgextra/i3/2206743574302/O1CN01abc123_!!2206743574302.jpg",
    rating: 4.7,
    shop_name: "荣耀官方旗舰店",
    sales_count: 12000,
    key_specs: {
      "处理器": "骁龙7 Gen3",
      "内存": "8GB",
      "存储": "128GB",
      "电池": "8300mAh"
    }
  }
])

// 测试数据3: 无图片
const mockToolCall3 = createMockToolCall([{
  title: "一加 Ace 5 竞速版 16GB+256GB 逐浪白",
  price: 2099.00,
  platform: "拼多多",
  url: "https://mobile.yangkeduo.com/goods.html?goods_id=example",
  image_url: null,
  rating: 4.6,
  shop_name: "一加官方旗舰店",
  sales_count: 5000,
  key_specs: {
    "处理器": "天玑9400e",
    "内存": "16GB",
    "存储": "256GB"
  }
}])

// 测试数据4: 空数组
const mockToolCallEmpty = createMockToolCall([])
</script>

<style scoped>
.test-container {
  max-width: 1200px;
  margin: 40px auto;
  padding: 20px;
}

h2 {
  text-align: center;
  color: #333;
  margin-bottom: 40px;
}

.test-section {
  margin-bottom: 60px;
  padding: 20px;
  background: #f5f5f5;
  border-radius: 8px;
}

.test-section h3 {
  margin-bottom: 20px;
  color: #666;
  font-size: 16px;
}
</style>
