/**
 * 主智能体接口契约（唯一真源 / single source of truth）
 * ═══════════════════════════════════════════════════════════════
 * 主智能体的定位：**编排层**。它自己不搜商品、不下单、不查物流、不读评价，
 * 只做「识别意图 → 检索路由所需的最小信息 → 决定派谁 → 汇总结果」。
 *
 * 设计判据（决定一个能力该不该放在主智能体上）：
 *   「拿掉这个能力，主智能体还能不能正确派活？」
 *     能   → 不该放（下放子智能体）
 *     不能 → 该放（留在主智能体）
 *   凡是让主智能体直接接触业务数据的（搜商品/下单/读评价/查物流），一律下放。
 *
 * 消费方：
 *   真实后端 / BFF —— 按本契约的字段名吐 SSE（**唯一消费方**）。
 *
 * ⚠️ 2026-09-18：**前端 mock（src/mock/agentStreamMock.js）已删除**。
 *    原因：mock 用正则与字符数硬挑剧本，等于在前端复刻了一套「意图判定」
 *    （「你好」因长度 ≤ 6 被判为「意图过泛」而走澄清剧本），既与真实后端行为
 *    不一致，又违背「不做判定、让模型自己理解」的设计红线。
 *    现在 `/agent` 一律走真实后端；`?mock` 参数已失效。
 *    契约本身仍是真源 —— 后端的 orchestration 载荷必须与这里逐字段对齐。
 *
 * 改字段名 = 改后端载荷，前后端必须同步，否则「左侧详情」与「右侧状态面板」会不一致。
 */

export const CONTRACT_VERSION = '1.0.0'

/** 编排护栏：写死在契约里，主智能体任何情况下都不得越过 */
export const MAIN_AGENT_GUARDRAILS = {
  // 主智能体不持有任何业务工具
  forbidden_tools: [
    'search_products', 'render_product_card', 'compare_products', 'get_price',
    'analyze_reviews', 'place_order', 'query_logistics', 'after_sale_service'
  ],
  // 主智能体不碰业务数据：查不到用户实名订单，也不爬每款商品的售后政策
  forbidden_data: ['用户实名订单', '物流轨迹', '各商品售后政策', '支付信息'],
  // 购后助手的业务只围绕「购物档案」展开
  archive_only_note: '购后的业务 = 购物档案（归档/阶段/提醒/复盘），不是履约。'
  // ⚠️ 曾经有 min_confidence_to_dispatch: 0.6（低置信度不派遣），2026-09-18 移除。
  //    用户实测结论：让模型先跑一遍意图/置信度判定，效果不如让它直接理解语境。
  //    判定既会误判，又会把内部决策语气泄露进对话（用户只说「你好」却收到
  //    「置信度太低，派出去只会白跑」）。现在**要不要派完全交给模型自己决定**。
}

/* ══════════════════════════════════════════════════════════════
 * 1. Tools —— 主智能体只有 4 个工具，全都是「编排动作」，没有一个是业务动作
 * ══════════════════════════════════════════════════════════════ */
export const MAIN_AGENT_TOOLS = {
  /**
   * 编排本体。每轮对话只允许调用一次，产出本轮的编排轨迹。
   * 渲染组件：OrchestrateTool.vue（默认展开）
   */
  orchestrate: {
    id: 'orchestrate',
    category: '主智能体',
    icon: 'Network',
    renderer: 'OrchestrateTool',
    purpose: '记录本轮的编排执行事实（用了哪些 Skill、查了哪些资料、派了谁），作为执行状态上报',
    args: {
      decision: 'string // 一句话派遣决策，运行中也先展示，保证「进行中」有内容'
    },
    result: {
      type: 'orchestration',
      orchestration: 'OrchestrationTrace // 见 buildOrchestrationTrace()'
    },
    sse: {
      start: "tool_start  { tool_call_id, tool_name:'orchestrate', arguments:{decision}, orchestration:<trace status='running'>, meta:{icon:'Network',category:'主智能体'}, message_id }",
      done: "tool_complete { tool_call_id, duration_ms, result_content: JSON.stringify({type:'orchestration',orchestration:<trace>}), orchestration:<trace status='completed'>, message_id }"
    },
    note: 'orchestration 字段必须在 upsertToolCall 与 toYuxiToolCall 两处都透传（全局状态 + 消息级状态各存一份）'
  },

  /**
   * 派遣子智能体。这是主智能体唯一真正的「干活」动作。
   * 渲染组件：TaskTool.vue（默认展开，详情里显示子智能体的 tools/RAG/skills 轨迹）
   */
  task: {
    id: 'task',
    category: '子智能体',
    icon: 'Bot',
    renderer: 'TaskTool',
    purpose: '把一个长任务整体交给子智能体，业务工具在子智能体内部执行',
    args: {
      subagent_type: 'string // 购前助手 | 购后助手',
      subagent: 'string  // 展示名',
      description: 'string // 交给子智能体的任务描述（自然语言，子智能体自己拆解）'
    },
    result: {
      result_preview: 'string // 一句话结果，给右侧状态面板',
      result_content: 'string // markdown 详细结果，给左侧详情',
      subagent_run: 'SubagentTrace'
    },
    subagent_run_schema: {
      status: 'running | completed | failed',
      tools: '[{ name, detail }] // 子智能体内部调用的业务工具',
      rag: '[{ name, detail }]   // 子智能体检索的知识库',
      skills: '[{ name, detail }] // 子智能体使用的技能'
    },
    sse: {
      start: "tool_start  { tool_name:'task', arguments:{subagent_type,...}, subagent_run:<trace status='running'>, meta:{icon:'Bot',category:'子智能体'}, message_id }",
      done: "tool_complete { tool_name:'task', duration_ms, result_preview, result_content, subagent_run:<trace status='completed'> }"
    }
  },

  /**
   * 待办：把本轮计划下发成可追踪步骤，随进度推进。
   * 走 plan 事件（不是 tool 事件），但契约上等价于一个工具。
   */
  todo_write: {
    id: 'todo_write',
    category: '主智能体',
    icon: 'ListChecks',
    renderer: 'none // 由右侧 StatePanel 待办分区消费',
    purpose: '把「识别意图 → 派遣 → 汇总」拆成用户看得见的步骤',
    args: {
      steps: '[{ id, description, status: pending|in_progress|completed }]'
    },
    sse: {
      emit: "plan { steps:[...] } // 每次都发全量 steps，前端 applyPlanSteps 覆盖式更新"
    },
    note: '不发 plan 事件，待办区就永远是「暂无计划步骤」——后端必须覆盖'
  },

  /**
   * 反问澄清：置信度不足或关键槽位缺失时，不派遣，先问。
   * 渲染组件：AskUserQuestionTool.vue
   */
  ask_user: {
    id: 'ask_user',
    alias: ['ask_user_question'], // 兼容 Yuxi 同名工具，渲染端两个 id 都注册了
    category: '主智能体',
    icon: 'HelpCircle',
    renderer: 'AskUserQuestionTool',
    purpose: '关键信息缺失时反问，一次最多 3 问、每问带选项，让用户点一下就能继续',
    args: {
      questions: '[{ question_id, question, options:[{label, description}] }]'
    },
    result: {
      user_answer: '{ [question_id]: string }'
    },
    // 触发与否**由模型自己判断**，不再依赖置信度阈值。
    // 典型情形：用户没说给谁买 / 没说预算 / 品类范围过泛，模型觉得问一句比瞎猜强。
    trigger: '模型自行判断信息不足时调用（不设阈值）'
  }
}

/* ══════════════════════════════════════════════════════════════
 * 2. MCP —— 主智能体连的 5 个服务，全部是「编排元数据」，不含业务数据
 * ══════════════════════════════════════════════════════════════ */
export const MAIN_AGENT_MCP = {
  'sc.session-memory': {
    name: '会话记忆服务',
    priority: 'P0',
    why: '主智能体必须知道「这个会话聊到哪了」，否则每轮都当新对话，派不准也接不上',
    endpoints: [
      {
        method: 'get_session_context',
        req: '{ thread_id: string, turns?: number }',
        res: '{ thread_id, turns:[{role, content, ts}], summary: string, open_entities:[{target, phase}] }'
      },
      {
        method: 'append_turn',
        req: '{ thread_id, role, content }',
        res: '{ ok: boolean }'
      },
      {
        method: 'link_record',
        req: '{ thread_id, record_id }',
        res: '{ ok: boolean } // 会话 ↔ 购物档案 双向绑定（对应 ShoppingRecord.threadId）'
      }
    ]
  },

  'sc.subagent-registry': {
    name: '子智能体注册中心',
    priority: 'P0',
    why: '决定「能派谁、谁健康」。没有它，编排就是演的——只能硬编码两个名字',
    endpoints: [
      {
        method: 'list_subagents',
        req: '{}',
        res: ` [{
          slug: string,              // 购前助手 | 购后助手
          name: string,
          capabilities: string[],    // 找候选 / 比价 / 出卡 / 归档 / 提醒 / 复盘
          input_schema: object,      // 主智能体据此组装 description
          output_schema: object,     // 主智能体据此组装汇总
          triggers: string[],        // 触发意图关键词
          not_for: string[],         // 明确不接的活（反路由，防止误派）
          avg_duration_ms: number,
          delivers: string[],        // 产物类型：product_card / comparison_table / decision_record ...
          health: { status: 'online'|'degraded'|'offline', latency_ms: number, queue: number }
        }] `
      },
      { method: 'health', req: '{ slug }', res: '{ status, latency_ms, queue }' }
    ]
  },

  'sc.archive-link': {
    name: '档案关联服务',
    priority: 'P0',
    why: '决定「这件事有没有历史档案」——有档案则派购后助手复用，无档案则派购前助手新建',
    endpoints: [
      {
        method: 'find_record',
        req: '{ target: string, forWhom?: string }',
        res: '{ record_id?: string, phase?: need|candidate|decided|using|reviewed|dropped, thread_id?: string, has_review: boolean }'
      },
      { method: 'list_open', req: '{ limit?: number }', res: '[{ record_id, target, phase, updatedAt }]' }
    ],
    boundary: '只返回路由元数据（id/phase/thread_id），不返回商品与订单内容——守护栏'
  },

  'sc.todo-state': {
    name: '待办 / 状态服务',
    priority: 'P1',
    why: '多轮对话时待办要能续上，不能刷新即丢',
    endpoints: [
      { method: 'upsert_plan', req: '{ thread_id, steps:[{id, description, status}] }', res: '{ ok }' },
      { method: 'patch_step', req: '{ thread_id, step_id, status }', res: '{ ok }' }
    ]
  },

  'sc.orchestration-metrics': {
    name: '编排计量服务',
    priority: 'P2',
    why: '「成本控制」skill 需要有数据：本会话已派几轮、已用多少 token、是否该降级',
    endpoints: [
      { method: 'quota', req: '{ thread_id }', res: '{ rounds_used, rounds_max, subagents_used, subagents_max, tokens_used }' },
      { method: 'record_round', req: '{ thread_id, dispatched:[slug], tokens, elapsed_ms }', res: '{ ok }' }
    ]
  }
}

/* ══════════════════════════════════════════════════════════════
 * 3. RAG —— 主智能体的 5 个知识库，全是「路由与偏好」，不是商品/评价
 * ══════════════════════════════════════════════════════════════ */
export const MAIN_AGENT_RAG = {
  subagent_directory: {
    name: '子智能体目录（路由表）',
    priority: 'P0',
    why: '最关键的一个：决定派谁。注册中心给「能不能派」，目录给「该派谁」',
    doc_schema: {
      slug: 'string',
      能做什么: 'string',
      不能做什么: 'string',
      入参: 'string',
      出参: 'string',
      触发意图: 'string[]',
      交付产物: 'string[]',
      平均耗时: 'string'
    },
    query: '{ query: string, top_k?: number }',
    returns: '[{ doc, score, slug }]'
  },

  user_profile: {
    name: '用户长期画像',
    priority: 'P0',
    why: '决定派得准不准：同样是买礼物，给妈妈和给同事是两个任务',
    doc_schema: {
      forWhom: 'string[]   // 妈妈 / 自己 / 同事',
      budget_band: '{ low, high, currency }',
      taboo: 'string[]    // 忌讳：不收鲜花 / 不要闲置',
      preference_tags: 'string[] // 实用 / 重省力 / 可接受耗材成本',
      address_city: 'string'
    },
    query: '{ forWhom?: string, top_k?: number }',
    returns: '[{ doc, score }]'
  },

  history_summary: {
    name: '历史会话摘要',
    priority: 'P1',
    why: '防止重复劳动：去年送过护膝，今年就别再推同类',
    doc_schema: {
      thread_id: 'string', date: 'string', intent: 'string',
      target: 'string', phase: 'string', conclusion: 'string', record_id: 'string'
    },
    query: '{ target?: string, forWhom?: string, months?: number }',
    returns: '[{ doc, score }]'
  },

  orchestration_sop: {
    name: '编排 SOP / 典型案例',
    priority: 'P1',
    why: '把「送礼怎么派、对比怎么派、复盘怎么派」固化成可复用的编排模板',
    doc_schema: {
      intent_pattern: 'string',      // 送礼推荐 | 横向对比 | 使用复盘 | 意图过泛
      route: 'string[]',             // [购前助手, 购后助手]
      parallel: 'boolean',
      plan_template: 'string[]',     // 待办步骤模板
      summary_template: 'string'     // 汇总话术模板
    },
    query: '{ intent: string }',
    returns: '[{ doc, score }]'
  },

  archive_index: {
    name: '购物档案索引',
    priority: 'P1',
    why: '已入手的东西回来问「值不值」时，主智能体要能判断该走复盘而不是重新选',
    doc_schema: {
      record_id: 'string', target: 'string', phase: 'string',
      purchasedAt: 'string', thread_id: 'string'
    },
    query: '{ target: string }',
    returns: '[{ doc, score, phase }]'
  }
}

/* ══════════════════════════════════════════════════════════════
 * 4. Skill —— 主智能体的编排手艺
 *
 * ⚠️ 2026-09-18 移除 `intent_triage`（意图分诊）。
 *    用户实测结论：让模型先跑一遍意图判定再行动，效果不如让它直接理解语境。
 *    判定环节既会误判，又会把内部决策语气泄露进对话 —— 典型症状是用户
 *    只说「你好」，却收到「置信度太低，派出去只会白跑」这种系统日志口吻的自述。
 *    现在「要不要派子智能体」完全由模型自己决定，不设阈值、不做分诊。
 * ══════════════════════════════════════════════════════════════ */
export const MAIN_AGENT_SKILLS = {
  dispatch_orchestration: {
    name: '派遣编排',
    input: '{ query, registry, directory_hits }',
    output: `{
      plan_steps: [{ id, description }],
      parallel: boolean,
      dispatch: [{ slug, task, depends_on: string[], timeout_ms }],
      fallback: string   // 子智能体不健康时的降级方案
    }`,
    rule: '子智能体之间无数据依赖 → 并行；有依赖（先出卡再归档）→ 串行并声明 depends_on'
  },

  result_synthesis: {
    name: '结果汇总与取舍',
    input: '{ query, subagent_results: [{slug, content}] }',
    output: '{ summary_md, picks: [], rejected: [], risks: [], next_action }',
    rule: '只做取舍与收口，不重写子智能体已经给出的细节；必须给出 next_action'
  },

  clarify: {
    name: '反问澄清',
    input: '{ query, missing_info }',
    output: '{ question, options: [{label, description}], why }',
    rule: '一次最多问 3 个；每个问题带选项，别让用户从零开始打字'
  },

  cost_control: {
    name: '轮次 / 成本控制',
    input: '{ metrics, dispatch_plan }',
    output: '{ max_rounds, max_subagents, degrade_if_over: string, skip_dispatch?: boolean }',
    rule: '本轮已派过且结果可用 → 复用，不重派；不值得派就直接回答'
  }
}

/* ══════════════════════════════════════════════════════════════
 * 5. OrchestrationTrace —— 在线上传输的编排轨迹结构（orchestrate 工具的载荷）
 *
 * ⚠️ 只描述「执行事实」，不描述「为什么不做什么」。
 *    刻意没有 `intent` / `confidence` 字段（2026-09-18 移除）——
 *    本卡片的职责是如实呈现这一步做了什么，不是「我为什么决定不派」的答辩书。
 * ══════════════════════════════════════════════════════════════ */
export const ORCHESTRATION_TRACE_FIELDS = {
  version: 'number  // 契约版本，渲染端据此兼容',
  status: "running | completed | failed",
  // 渐进显形：编排卡不是一口气长全的，而是随主智能体逐步推进分区出现。
  // step = 已经显形到第几个分区（skills → rag → mcp → dispatch → decision），
  // 前端按 step 逐段 v-if；后端每推进一步就重发一次同 tool_call_id 的 tool_start。
  step: 'number  // 0-based，已显形的分区数；缺省视为全部显形（向后兼容）',
  skills: '[{ id, name, detail }]',
  rag: '[{ id, collection, name, query?, detail }]',
  mcp: '[{ id, server, method, name, detail }]',
  dispatch: '[{ slug, task, depends_on:[], timeout_ms, parallel }]',
  decision: 'string  // 「在做什么」的陈述句，非辩解式表达',
  guardrails: '{ touched_business_data: boolean, note: string }'
}

/**
 * 编排卡的渐进分区顺序。
 * 契约级常量：后端按这个数组的下标推进 step，前端按同一顺序逐段显形。
 * 改动这里 = 改后端的吐法（后端按本契约字段名吐 SSE；mock 已删除）。
 *
 * ⚠️ 首档曾是 'intent'（意图分诊 + 置信度），2026-09-18 移除。
 *    要不要派子智能体**完全由模型自己决定**，不设阈值、不做分诊。
 */
export const ORCHESTRATION_REVEAL_STEPS = ['skills', 'rag', 'mcp', 'dispatch', 'decision']

/**
 * 按契约构造编排轨迹。
 *
 * @param {object} fixture  场景夹具
 * @param {string} status   'running' | 'completed'
 * @param {number} [upTo]   渐进显形：只露出前 upTo 个分区。
 *                          缺省（undefined）= 全部露出，保证「一次性渲染」的老路径不受影响。
 *                          后端在 running 期间逐次递增 upTo，用同一个 tool_call_id 重发
 *                          tool_start，前端 upsertToolCall 原地覆盖 → 卡片逐段长出来。
 */
export function buildOrchestrationTrace (fixture, status = 'running', upTo = undefined) {
  const full = {
    version: 1,
    status,
    skills: fixture.skills || [],
    rag: fixture.rag || [],
    mcp: fixture.mcp || [],
    dispatch: fixture.dispatch || [],
    decision: fixture.decision || '',
    guardrails: {
      touched_business_data: false,
      note: MAIN_AGENT_GUARDRAILS.archive_only_note,
      ...(fixture.guardrails || {})
    }
  }
  if (upTo == null) return { ...full, step: ORCHESTRATION_REVEAL_STEPS.length }
  const n = Math.max(0, Math.min(upTo, ORCHESTRATION_REVEAL_STEPS.length))
  const shown = ORCHESTRATION_REVEAL_STEPS.slice(0, n)
  // 未显形的分区按「空值」下发，而不是省略键 —— 前端 v-if 依赖 length/truthy，
  // 省略键会让契约字段漂移（下游拿不到键就无法区分「还没到」和「本就没有」）。
  const has = (k) => shown.includes(k)
  return {
    ...full,
    step: n,
    skills: has('skills') ? full.skills : [],
    rag: has('rag') ? full.rag : [],
    mcp: has('mcp') ? full.mcp : [],
    dispatch: has('dispatch') ? full.dispatch : [],
    decision: has('decision') ? full.decision : ''
  }
}

/* ══════════════════════════════════════════════════════════════
 * 0. 叙述节奏（pacing）—— 每轮对话的硬性时序约定
 * ══════════════════════════════════════════════════════════════
 * 核心规则：**每一次状态块出现之前，主智能体必须先说一段话。**
 * 「状态块」= tool_start（编排 / 派遣 / 业务工具）+ 子智能体下钻 + 产物卡片。
 *
 * 一个标准轮次的完整节奏：
 *
 *   ① thinking × N                     右侧执行流（不占主对话顺序）
 *   ② 正文①：识别意图 + 宣布派遣计划      文本先行，此时还没有任何调用状态
 *   ③ plan（待办下发）                   随②立刻出现
 *   ④ 正文：说明本轮编排的判断依据          ← 状态前导
 *   ⑤ tool_start/complete orchestrate    编排卡（Skill/RAG/MCP/派遣决策）
 *   ⑥ 正文：说明为什么先派购前助手          ← 状态前导
 *   ⑦ tool_start task(购前助手)           子智能体卡出现
 *   ⑧ 正文：展开购前助手                    ← 状态前导
 *   ⑨ subagent_drill expand               子智能体卡展开，内部过程可见
 *   ⑩ 正文：「它第一件事是搜货……」          ← 状态前导
 *   ⑪ tool_start/complete search_products
 *   ⑫ 正文：「收到 12 件候选……」            ← 状态前导
 *   ⑬ tool_start/complete render_product_card（产物卡片）
 *   ⑭ 正文：「购前助手出结果了……」          ← 状态前导
 *   ⑮ subagent_drill collapse             收起该子智能体详情，视线交还主线
 *   ⑯ tool_complete task(购前助手)
 *   …购后助手重复 ⑥~⑯…
 *   ⑰ 正文：说明两路都回来了 + 对账          ← 状态前导
 *   ⑱ 正文②：汇总结论
 *   ⑲ plan 全绿 → done { statistics }
 *
 * 反例（要避免的）：一次性把「我派两个子智能体」说完，然后十几个工具状态连发，
 * 中间再无文字 —— 用户只能看到状态在滚，不知道每一步为什么发生。
 *
 * subagent_drill 事件（下钻）：
 *   { slug: string, action: 'expand' | 'collapse', description?: string, message_id }
 *   - expand：子智能体开始干活前下发，让其卡片展开，用户能看到内部调用过程
 *   - collapse：子智能体干完后下发，收起详情，避免历史越长界面越乱
 *   前端：AgentChatComponent 的 setToolCallDrill() 找到该 slug 的 task 卡片打上
 *   `drill` 标记 → BaseToolCall watch 后改展开态。
 *   ⚠️ drill 必须同时透传进 upsertToolCall 与 toYuxiToolCall（双存储），否则左侧不响应。
 *
 * ── 渐进显形（progressive reveal）：状态块内部也要「边执行边长」 ──
 * 上面的节奏解决的是「状态块之间」的交替；状态块**自己**也不能一口气长全 ——
 * 否则用户看到的是「点了发送，一张塞满内容的卡瞬间出现」，执行感全无。
 *
 * 机制：**复用同一个 tool_call_id，分多次发 tool_start（或 tool_complete），
 * 每次只比上一次多露出一个分区**。前端 upsertToolCall 对同 id 原地覆盖
 * （`orchestration: item.orchestration ?? 旧值`），因此卡片会逐段显形，前端零改动。
 *
 * 适用的状态块与各自的分区序列：
 *   · orchestrate 卡 → ORCHESTRATION_REVEAL_STEPS
 *     ['skills','rag','mcp','dispatch','decision']
 *     即：使用 Skill → 检索 RAG → 调用 MCP → 派遣清单 → 派遣决策
 *     ⚠️ 曾经的第一档是 `intent`（意图分诊 + 置信度），2026-09-18 已移除：
 *        让模型直接理解语境，好过先跑一遍判定。
 *   · task 卡（子智能体）→ subagent_run.tools / .rag / .skills 按执行进度增量填充
 *   · 业务工具卡 → 先 tool_start（无结果，转圈）→ tool_complete（带结果）
 *
 * 为什么必须后端控制：**「执行到哪一步」是后端的运行时事实**，前端无从推断。
 * 前端只负责「按 step 逐段 v-if 显形 + 渲染加载态」。
 *
 * ⚠️ 分区按 ORCHESTRATION_REVEAL_STEPS 的下标推进，未显形的分区必须下发**空值**
 * （null / [] / ''）而不是省略键，避免「还没到」与「本就没有」被混为一谈。
 */

/* ══════════════════════════════════════════════════════════════
 * 4. Mock 夹具 —— 四个场景的编排轨迹（**mock 已删除，保留供离线校验脚本与后端对齐参考**）
 * ══════════════════════════════════════════════════════════════ */
export const ORCHESTRATION_FIXTURES = {
  // ① 送礼推荐：并行派两个子智能体
  gift: {
    skills: [
      { id: 'dispatch_orchestration', name: '派遣编排', detail: '两个子智能体互不依赖 → 可并行' }
    ],
    rag: [
      { id: 'subagent_directory', collection: 'subagent_directory', name: '子智能体目录', query: '送礼 预算 推荐', detail: '购前助手：找候选/比价/出卡；购后助手：归档/提醒' },
      { id: 'user_profile', collection: 'user_profile', name: '用户长期画像', query: 'forWhom=妈妈', detail: '偏好实用不闲置；预算敏感；忌讳鲜花' },
      { id: 'history_summary', collection: 'history_summary', name: '历史会话摘要', query: '妈妈 礼物', detail: '去年送过护膝；没买过茶具' }
    ],
    mcp: [
      { id: 'session-memory.get_session_context', server: 'sc.session-memory', method: 'get_session_context', name: '会话记忆服务', detail: '读取本会话上下文' },
      { id: 'subagent-registry.list_subagents', server: 'sc.subagent-registry', method: 'list_subagents', name: '子智能体注册中心', detail: '2 个在线：购前助手 / 购后助手' }
    ],
    dispatch: [
      { slug: '购前助手', task: '按偏好找候选、比价、出商品卡', depends_on: [], timeout_ms: 20000, parallel: true },
      { slug: '购后助手', task: '把这次决策存入购物档案并设提醒', depends_on: [], timeout_ms: 15000, parallel: true }
    ],
    decision: '同时委托给：购前助手（找货比价出卡）+ 购后助手（归档并设提醒）'
  },

  // ② 横向对比：购前内部逐款出卡，对外仍是两个子智能体
  compare: {
    skills: [
      { id: 'dispatch_orchestration', name: '派遣编排', detail: '逐款出卡在购前内部串行，对外仍并行' }
    ],
    rag: [
      { id: 'subagent_directory', collection: 'subagent_directory', name: '子智能体目录', query: '对比 横评', detail: '购前助手支持逐款出卡 + 横评；购后助手负责归档' },
      { id: 'user_profile', collection: 'user_profile', name: '用户长期画像', query: 'forWhom=自己', detail: '家里有地毯；养宠；重省力' },
      { id: 'archive_index', collection: 'archive_index', name: '购物档案索引', query: '洗地机', detail: '无进行中档案（phase=need）→ 需新建' }
    ],
    mcp: [
      { id: 'subagent-registry.list_subagents', server: 'sc.subagent-registry', method: 'list_subagents', name: '子智能体注册中心', detail: '2 个在线' },
      { id: 'archive-link.find_record', server: 'sc.archive-link', method: 'find_record', name: '档案关联服务', detail: '未命中 → 走新建归档' }
    ],
    dispatch: [
      { slug: '购前助手', task: '检索两款洗地机、逐款出卡并出横评表', depends_on: [], timeout_ms: 25000, parallel: true },
      { slug: '购后助手', task: '归档对比结论并设耗材提醒', depends_on: ['购前助手'], timeout_ms: 15000, parallel: false }
    ],
    decision: '并行派遣：购前助手（检索并逐款出卡）+ 购后助手（归档并设提醒）'
  },

  // ③ 使用复盘：单派购后助手
  review: {
    skills: [
      { id: 'dispatch_orchestration', name: '派遣编排', detail: '单子智能体即可，无需并行' },
      { id: 'cost_control', name: '成本控制', detail: '本会话第 1 轮，配额 1/3' }
    ],
    rag: [
      { id: 'subagent_directory', collection: 'subagent_directory', name: '子智能体目录', query: '复盘 使用反馈', detail: '购后助手：归档 / 提醒 / 复盘' },
      { id: 'archive_index', collection: 'archive_index', name: '购物档案索引', query: '洗地机', detail: '命中：添可芙万 3.0 · phase=using · 有 threadId' }
    ],
    mcp: [
      { id: 'session-memory.get_session_context', server: 'sc.session-memory', method: 'get_session_context', name: '会话记忆服务', detail: '读取上次选购对话' },
      { id: 'archive-link.find_record', server: 'sc.archive-link', method: 'find_record', name: '档案关联服务', detail: 'rec_01 · phase=using · 可继续问它' }
    ],
    dispatch: [
      { slug: '购后助手', task: '取回档案记录，写复盘并推进阶段到已复盘', depends_on: [], timeout_ms: 15000, parallel: false }
    ],
    decision: '委托给购后助手处理'
  },

  // ④ 信息不足：模型自己判断先问一句比瞎猜强
  //
  // ⚠️ 这个场景**不再由置信度阈值触发**（2026-09-18 移除）。
  //    它是模型自己读到「买个东西」这种过泛的表述后，主动选择调 ask_user。
  //    编排卡此时是「已经决定不派子智能体、改为反问」的如实记录，
  //    而不是「我判定置信度太低所以放弃派遣」的答辩书。
  clarify: {
    skills: [
      { id: 'clarify', name: '反问澄清', detail: '补齐 target / forWhom / budget 三个槽位' },
      { id: 'cost_control', name: '成本控制', detail: '信息不足时不消耗子智能体，本轮 max_subagents=0' }
    ],
    rag: [
      { id: 'user_profile', collection: 'user_profile', name: '用户长期画像', query: '默认画像', detail: '历史买过茶具、护膝；无近期目标' },
      { id: 'history_summary', collection: 'history_summary', name: '历史会话摘要', query: '近 3 轮', detail: '近 3 轮均未完成决策 → 应收敛而非发散' }
    ],
    mcp: [
      { id: 'session-memory.get_session_context', server: 'sc.session-memory', method: 'get_session_context', name: '会话记忆服务', detail: '本会话第 1 轮，无可用上下文' },
      { id: 'orchestration-metrics.quota', server: 'sc.orchestration-metrics', method: 'quota', name: '编排计量服务', detail: 'rounds 0/3 · subagents 0/4' }
    ],
    dispatch: [],
    decision: '先问清楚再动手',
    guardrails: { note: '本轮没有派子智能体，也没有触碰商品数据。' }
  }
}

export default {
  CONTRACT_VERSION,
  MAIN_AGENT_GUARDRAILS,
  MAIN_AGENT_TOOLS,
  MAIN_AGENT_MCP,
  MAIN_AGENT_RAG,
  MAIN_AGENT_SKILLS,
  ORCHESTRATION_TRACE_FIELDS,
  ORCHESTRATION_FIXTURES,
  buildOrchestrationTrace
}
