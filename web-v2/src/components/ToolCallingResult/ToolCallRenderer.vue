<template>
  <component
    :is="currentRenderer"
    v-if="currentRenderer"
    :tool-call="toolCall"
    :appearance="appearance"
    :default-expanded="defaultExpanded"
    ref="toolRendererRef"
  />
  <BaseToolCall
    v-else-if="!isHidden"
    :tool-call="toolCall"
    :appearance="appearance"
    :default-expanded="defaultExpanded"
  />
</template>

<script setup>
import { computed, ref } from 'vue'
import BaseToolCall from './BaseToolCall.vue'

// Yuxi 通用工具
import WebSearchTool from './tools/WebSearchTool.vue'
import ListKbsTool from './tools/ListKbsTool.vue'
import GetMindmapTool from './tools/GetMindmapTool.vue'
import CalculatorTool from './tools/CalculatorTool.vue'
import TodoListTool from './tools/TodoListTool.vue'
import TaskTool from './tools/TaskTool.vue'
import ImageTool from './tools/ImageTool.vue'
import WriteFileTool from './tools/WriteFileTool.vue'
import ReadFileTool from './tools/ReadFileTool.vue'
import ListDirectoryTool from './tools/ListDirectoryTool.vue'
import SearchFileContentTool from './tools/SearchFileContentTool.vue'
import GlobTool from './tools/GlobTool.vue'
import GrepTool from './tools/GrepTool.vue'
import EditFileTool from './tools/EditFileTool.vue'
import ExecuteTool from './tools/ExecuteTool.vue'
import RememberMemoryTool from './tools/RememberMemoryTool.vue'
import OcrParseFileTool from './tools/OcrParseFileTool.vue'
import MysqlQueryTool from './tools/MysqlQueryTool.vue'
import MysqlDescribeTableTool from './tools/MysqlDescribeTableTool.vue'
import MysqlListTablesTool from './tools/MysqlListTablesTool.vue'
import AskUserQuestionTool from './tools/AskUserQuestionTool.vue'

// SC 电商业务工具
import ProductCardTool from './tools/ProductCardTool.vue'
import ChartTool from './tools/ChartTool.vue'
import ShopTool from './tools/ShopTool.vue'

// SC 交付形态（购物档案视角）：一个工具 = 一种产物 = 一个专属组件
import DecisionArchiveTool from './tools/DecisionArchiveTool.vue'
import ComparisonTableTool from './tools/ComparisonTableTool.vue'
import ReminderListTool from './tools/ReminderListTool.vue'
import ReviewCardTool from './tools/ReviewCardTool.vue'

// 主智能体编排卡已于 2026-09-21 下线渲染（见 toolRegistry 的 HIDDEN_TOOL_CALL_IDS）。
// 组件文件保留在 ./tools/OrchestrateTool.vue，后续接入真实编排数据时可恢复：
// 把 'orchestrate' 从 HIDDEN_TOOL_CALL_IDS 移除，并恢复下面两行。
// import OrchestrateTool from './tools/OrchestrateTool.vue'

import { getToolCallId, isHiddenToolCall } from './toolRegistry'

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

const TOOL_RENDERERS = {
  // 通用
  ask_user_question: AskUserQuestionTool,
  bash: ExecuteTool,
  calculator: CalculatorTool,
  cmd: ExecuteTool,
  edit_file: EditFileTool,
  execute: ExecuteTool,
  get_mindmap: GetMindmapTool,
  glob: GlobTool,
  grep: GrepTool,
  list_directory: ListDirectoryTool,
  list_kbs: ListKbsTool,
  ls: ListDirectoryTool,
  mysql_describe_table: MysqlDescribeTableTool,
  mysql_list_tables: MysqlListTablesTool,
  mysql_query: MysqlQueryTool,
  ocr_parse_file: OcrParseFileTool,
  read_file: ReadFileTool,
  remember_memory: RememberMemoryTool,
  replace: EditFileTool,
  run_shell_command: ExecuteTool,
  search_file_content: SearchFileContentTool,
  task: TaskTool,
  web_search: WebSearchTool,
  tavily_search: WebSearchTool,
  doubao_search: WebSearchTool,
  text_to_img_qwen_image: ImageTool,
  write_file: WriteFileTool,
  write_todos: TodoListTool,

  // 电商业务（SC 扩展）—— 通用购物工具统一走 ShopTool（可读头部 + 结构化结果）
  search_products: ShopTool,
  jd_search: ShopTool,
  search: ShopTool,
  pdd_goods_search: ShopTool,
  taobao_searchMaterial: ShopTool,
  taobao_getItemInfo: ShopTool,
  compare_products: ShopTool,
  compare: ShopTool,
  get_price: ShopTool,
  price_history: ShopTool,
  query_coupon: ShopTool,
  coupon: ShopTool,
  check_stock: ShopTool,
  stock: ShopTool,
  shop_reliability: ShopTool,
  analyze_shop_reliability: ShopTool,
  analyze_reviews: ShopTool,
  reviews: ShopTool,
  risk_audit: ShopTool,
  critic: ShopTool,
  get_product_full_detail: ShopTool,
  get_products_specs_batch: ShopTool,
  get_products_specs_extract: ShopTool,
  query_category_knowledge: ShopTool,
  get_user_profile: ShopTool,
  get_user_shopping_context: ShopTool,

  // 专属呈现（保留独立组件）
  render_product_card: ProductCardTool,
  chart: ChartTool,
  draw_chart: ChartTool,

  // ── 交付形态（购物档案视角）─────────────────────────────
  // 查不到实名订单、也不爬每款售后政策，所以"购后"不做物流/工单，
  // 而是把决策沉淀进购物档案：归档 → 阶段 → 提醒 → 复盘。
  save_to_archive: DecisionArchiveTool,
  update_record_phase: DecisionArchiveTool,
  render_comparison: ComparisonTableTool,
  set_reminder: ReminderListTool,
  write_review: ReviewCardTool,

  // ── 主智能体编排卡已下线（2026-09-21），见上方 import 处的说明 ──

  // ── 主智能体反问澄清（契约里叫 ask_user，渲染复用 Yuxi 的提问组件）──
  ask_user: AskUserQuestionTool,
  ask_user_question: AskUserQuestionTool
}

const currentRenderer = computed(() => TOOL_RENDERERS[toolId.value] || null)
const isHidden = computed(() => isHiddenToolCall(props.toolCall))

const toolRendererRef = ref(null)
const refreshGraph = () => {
  if (toolRendererRef.value && typeof toolRendererRef.value.refreshGraph === 'function') {
    toolRendererRef.value.refreshGraph()
  }
}

defineExpose({ refreshGraph })
</script>

<style lang="less" scoped></style>
