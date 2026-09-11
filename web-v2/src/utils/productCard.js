// 商品卡片载荷解析（抽成纯函数，便于单测）
//
// 后端 render_product_card 实际下发的是**单卡格式**：
//   { "type": "product_card", "data": { "title": ..., "price": ..., "image_url": ... } }
// 而历史遗留的多卡格式是 { "cards": [ ... ] }。
// 原先 ProductCardTool 只认 data.cards，于是单卡格式恒解析出空数组，
// 卡片区永远渲染成「暂无商品数据」—— 这是「卡片变空」的直接原因。
export function parseProductCards(content) {
  if (content == null || content === '') return []

  let data = content
  if (typeof content === 'string') {
    try {
      data = JSON.parse(content)
    } catch {
      return []
    }
  }
  if (!data || typeof data !== 'object') return []

  // 单卡：{ type: 'product_card', data: {...} }
  if (data.type === 'product_card' && data.data) return [data.data]
  // 多卡：{ cards: [...] }
  if (Array.isArray(data.cards)) return data.cards
  // 兜底：本身就是一个商品对象
  if (data.title) return [data]

  return []
}
