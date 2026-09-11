// 工具调用渲染注册表（对标 Yuxi components/ToolCallingResult/toolRegistry.js）
// 统一：工具 id 提取、显示名/图标映射、状态判定、结果解析。
// 图标库：本项目使用 lucide-vue-next（Yuxi 用 @lucide/vue，API 一致仅包名不同）。
import {
  BookOpen,
  Bot,
  Brain,
  Calculator,
  CheckSquare,
  Database,
  FileEdit,
  FilePen,
  FileText,
  Folder,
  FolderOutput,
  FolderSearch,
  Globe,
  HelpCircle,
  Image,
  Network,
  RefreshCw,
  SquareTerminal,
  Atom,
  Search,
  Scale,
  Ticket,
  Package,
  Store,
  BarChart3,
  Wrench,
  Sparkles,
  TrendingDown,
  MessageSquareQuote,
  ClipboardList,
  ShieldCheck,
  User,
  ShoppingBag
} from 'lucide-vue-next'

// ── 工具图标映射：Yuxi 通用工具 + 电商业务工具 ──
export const TOOL_ICON_MAP = {
  // Yuxi 通用工具
  ask_user_question: HelpCircle,
  bash: SquareTerminal,
  calculator: Calculator,
  cmd: SquareTerminal,
  edit_file: FilePen,
  execute: SquareTerminal,
  find_kb_document: FolderSearch,
  get_mindmap: Network,
  glob: FolderSearch,
  grep: FolderSearch,
  list_directory: Folder,
  list_kbs: BookOpen,
  ls: Folder,
  mysql_describe_table: Database,
  mysql_list_tables: Database,
  mysql_query: Database,
  ocr_parse_file: FileText,
  open_kb_document: FileText,
  present_artifacts: FolderOutput,
  query_kb: BookOpen,
  read_file: FileText,
  remember_memory: Brain,
  replace: FilePen,
  run_shell_command: SquareTerminal,
  search_file: FolderSearch,
  search_file_content: FolderSearch,
  subagent_await: Bot,
  subagent_cancel: Bot,
  subagent_events: RefreshCw,
  subagent_start: Bot,
  subagent_status: RefreshCw,
  task: Bot,
  web_search: Globe,
  tavily_search: Globe,
  doubao_search: Globe,
  text_to_img_qwen_image: Image,
  write_file: FileEdit,
  write_todos: CheckSquare,

  // 电商业务工具（SC 扩展）
  search_products: Search,
  jd_search: Search,
  search: Search,
  compare_products: Scale,
  compare: Scale,
  get_price: TrendingDown,
  price_history: BarChart3,
  query_coupon: Ticket,
  coupon: Ticket,
  check_stock: Package,
  stock: Package,
  shop_reliability: Store,
  shop: Store,
  analyze_reviews: MessageSquareQuote,
  reviews: MessageSquareQuote,
  risk_audit: ShieldCheck,
  critic: ShieldCheck,
  todo: ClipboardList,
  render_product_card: Sparkles,
  get_product_full_detail: Package,
  get_products_specs_batch: Package,
  get_products_specs_extract: FileText,
  pdd_goods_search: Search,
  query_category_knowledge: BookOpen,
  taobao_getItemInfo: Package,
  taobao_searchMaterial: Search,
  get_user_profile: User,
  get_user_shopping_context: ShoppingBag,
  analyze_shop_reliability: Store
}

// ── 工具显示名：后端未下发 display_name 时的前端兜底 ──
export const TOOL_NAME_MAP = {
  // Yuxi 通用工具
  bash: '执行命令',
  cmd: '执行命令',
  execute: '执行命令',
  run_shell_command: '执行命令',
  ls: '列出目录',
  list_directory: '列出目录',
  glob: '匹配文件路径',
  grep: '搜索文件内容',
  read_file: '读取文件',
  remember_memory: '更新记忆',
  write_file: '写入文件',
  edit_file: '编辑文件',
  replace: '编辑文件',
  search_file: '搜索知识库文件',
  search_file_content: '搜索文件内容',
  write_todos: '更新任务清单',
  task: '调用子智能体',
  subagent_start: '启动子智能体',
  subagent_status: '查询子智能体',
  subagent_events: '查看子智能体事件',
  subagent_cancel: '取消子智能体',
  subagent_await: '等待子智能体',
  text_to_img_qwen_image: '生成图片',
  query_kb: '搜索知识库',
  list_kbs: '查看知识库列表',
  find_kb_document: '查找知识库文档',
  open_kb_document: '打开知识库文档',
  get_mindmap: '获取思维导图',
  calculator: '计算器',
  web_search: '网络搜索',
  tavily_search: '网络搜索',
  doubao_search: '网络搜索',
  ocr_parse_file: 'OCR识别文件',
  mysql_list_tables: '列出数据库表',
  mysql_describe_table: '查看表结构',
  mysql_query: '执行SQL查询',
  ask_user_question: '向用户提问',

  // 电商业务工具（SC 扩展）
  search_products: '搜索商品',
  jd_search: '搜索商品',
  search: '搜索',
  compare_products: '对比商品',
  compare: '对比',
  get_price: '查询价格',
  price_history: '历史价格',
  query_coupon: '查询优惠券',
  coupon: '优惠券',
  check_stock: '查询库存',
  stock: '库存',
  shop_reliability: '店铺可靠度',
  analyze_shop_reliability: '店铺可靠度',
  shop: '店铺',
  analyze_reviews: '分析评论',
  reviews: '评论分析',
  risk_audit: '风险评审',
  critic: '风险评审',
  todo: '任务清单',
  render_product_card: '生成商品卡片',
  get_product_full_detail: '获取商品详情',
  get_products_specs_batch: '批量获取规格',
  get_products_specs_extract: '提取商品规格',
  pdd_goods_search: '搜索拼多多商品',
  query_category_knowledge: '查询品类知识',
  taobao_getItemInfo: '获取淘宝商品详情',
  taobao_searchMaterial: '搜索淘宝素材',
  get_user_profile: '读取用户画像',
  get_user_shopping_context: '读取购物上下文'
}

// Keep intentionally hidden tool calls centralized so group summaries and renderers stay consistent.
export const HIDDEN_TOOL_CALL_IDS = ['present_artifacts']

export const getToolCallId = (toolCall) => toolCall?.name || toolCall?.function?.name || ''

export const getToolName = (toolId) => TOOL_NAME_MAP[toolId] || toolId

// 从工具元数据列表（完整工具列表或 buildin options）中按工具 id 查找对应元数据
export const findToolInList = (toolId, toolsList) =>
  (toolsList || []).find((t) => (t.slug ?? t.key ?? t.id) === toolId)

export const isHiddenToolCall = (toolCall) => HIDDEN_TOOL_CALL_IDS.includes(getToolCallId(toolCall))

export const isValidToolCall = (toolCall) => {
  return Boolean(
    toolCall &&
    (toolCall.id || toolCall.name || toolCall.function?.name) &&
    (toolCall.args !== undefined ||
      toolCall.function?.arguments !== undefined ||
      toolCall.tool_call_result !== undefined)
  )
}

export const parseToolCallArgs = (toolCall) => {
  const args = toolCall?.args ?? toolCall?.function?.arguments
  if (!args) return {}
  if (typeof args === 'object') return args
  try {
    return JSON.parse(args)
  } catch {
    return {}
  }
}

export const SUBAGENT_TOOL_IDS = [
  'task',
  'subagent_start',
  'subagent_status',
  'subagent_events',
  'subagent_cancel',
  'subagent_await'
]

export const isSubagentToolCall = (toolCall) => SUBAGENT_TOOL_IDS.includes(getToolCallId(toolCall))

// 结果内容：Yuxi 用 tool_call_result.content，SC 流式侧用 output，两者都兼容
export const parseToolCallResult = (toolCall) => {
  const content = toolCall?.tool_call_result?.content ?? toolCall?.result ?? toolCall?.output
  if (content == null || content === '') return null
  if (typeof content === 'object') return content
  try {
    return JSON.parse(content)
  } catch {
    return null
  }
}

const FINAL_STATUSES = ['completed', 'complete', 'done', 'success', 'called']
const RUNNING_STATUSES = ['in_progress', 'running', 'active', 'processing', 'calling']
// interrupted：流被上游报错 / 用户中止打断时，工具只发了 tool_start 而没有
// tool_complete。归入错误态，避免永久停留在「进行中」；
// 与 Yuxi getToolCallDisplayStatus 把 interrupted 视为 error 的语义一致。
const ERROR_STATUSES = ['failed', 'error', 'cancelled', 'canceled', 'interrupted', 'aborted']

/** SC 侧状态归一化：兼容 Yuxi 的 success/error 与 SC 的 completed/failed。 */
export const normalizeStatus = (status) => {
  const value = String(status || '').toLowerCase()
  if (FINAL_STATUSES.includes(value)) return 'completed'
  if (RUNNING_STATUSES.includes(value)) return 'running'
  if (ERROR_STATUSES.includes(value)) return 'error'
  return 'pending'
}

/** 以调用、ToolMessage 和结果顶层的错误状态优先决定工具展示状态。 */
export const getToolCallStatus = (toolCall) => {
  const statuses = [
    toolCall?.status,
    toolCall?.tool_call_result?.status,
    parseToolCallResult(toolCall)?.status
  ].map((status) => normalizeStatus(status))

  if (statuses.some((status) => status === 'error')) return 'error'
  if (
    toolCall?.tool_call_result != null ||
    toolCall?.result != null ||
    statuses.includes('completed')
  )
    return 'completed'
  return 'running'
}

/** 子智能体结果与补充运行信息中的状态，供详情和分组共同展示。 */
export const getSubagentRunStatus = (toolCall) => {
  if (getToolCallStatus(toolCall) === 'error') return 'error'
  const result = parseToolCallResult(toolCall)
  return (
    result?.run_status ||
    result?.active_run_status ||
    result?.status ||
    toolCall?.subagent_run?.status ||
    ''
  )
}

/** 统一工具行与分组的展示状态，保留子智能体特有的运行态。 */
export const getToolCallDisplayStatus = (toolCall, activeSubagentToolCallIds) => {
  const status = getToolCallStatus(toolCall)
  if (status === 'error' || !isSubagentToolCall(toolCall)) return status
  const runStatus = getSubagentRunStatus(toolCall)
  if (['error', 'failed', 'cancelled', 'interrupted'].includes(runStatus)) return 'error'
  if (getToolCallId(toolCall) === 'task') {
    if (status === 'completed') return 'completed'
    return activeSubagentToolCallIds?.has(String(toolCall.id)) ? 'running' : 'completed'
  }
  if (['failed', 'cancelled', 'interrupted'].includes(runStatus)) return 'error'
  if (status === 'completed' || runStatus === 'completed' || parseToolCallResult(toolCall)?.status)
    return 'completed'
  return 'running'
}

export const enrichSubagentToolCall = (
  toolCall,
  { subagentRunById, subagentRunByThreadId, subagentOptionBySlug } = {}
) => {
  if (!isSubagentToolCall(toolCall)) return toolCall

  const args = parseToolCallArgs(toolCall)
  const result = parseToolCallResult(toolCall)
  const subagentRun =
    (toolCall.id ? subagentRunById?.get?.(String(toolCall.id)) : null) ||
    (result?.run_id ? subagentRunById?.get?.(String(result.run_id)) : null) ||
    (args.thread_id ? subagentRunByThreadId?.get?.(String(args.thread_id)) : null) ||
    (result?.thread_id ? subagentRunByThreadId?.get?.(String(result.thread_id)) : null)
  const subagentOption = args.subagent_slug
    ? subagentOptionBySlug?.get?.(String(args.subagent_slug))
    : null
  const displayLabel =
    result?.subagent_name ||
    subagentRun?.subagent_name ||
    subagentOption?.name ||
    result?.subagent_slug ||
    subagentRun?.subagent_slug ||
    undefined

  return {
    ...toolCall,
    ...(subagentRun ? { subagent_run: subagentRun } : {}),
    ...(displayLabel ? { display_label: displayLabel } : {})
  }
}

export const normalizeToolCalls = (toolCalls, { includeHidden = false, mapToolCall } = {}) => {
  if (!Array.isArray(toolCalls)) return []

  return toolCalls
    .filter((toolCall) => {
      if (!isValidToolCall(toolCall)) return false
      return includeHidden || !isHiddenToolCall(toolCall)
    })
    .map((toolCall) => (mapToolCall ? mapToolCall(toolCall) : toolCall))
}

export const enrichTaskToolCalls = (toolCalls, options = {}) =>
  normalizeToolCalls(toolCalls, {
    mapToolCall: (toolCall) => enrichSubagentToolCall(toolCall, options)
  })

export const getToolIcon = (toolId) => TOOL_ICON_MAP[toolId] || null

/** 兼容旧调用：工具行标签（display_label > 元数据名 > 兜底映射 > 工具 id）。 */
export const getToolCallLabel = (toolCall, toolsList = []) => {
  const displayLabel = String(toolCall?.display_label || '').trim()
  if (displayLabel) return displayLabel
  const toolId = getToolCallId(toolCall) || toolCall?.id || ''
  const tool = findToolInList(toolId, toolsList)
  return tool ? tool.name : getToolName(toolId)
}
