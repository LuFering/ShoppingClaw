<template>
  <div class="wb">
    <!-- 页头：agent 身份 + 当前任务 + 操作 -->
    <header class="wb-head">
      <span class="wb-sig">采</span>
      <div class="wb-id">
        <p class="wb-name">采办 · 采购规划</p>
        <p class="wb-task">{{ taskLabel }}</p>
      </div>
      <div class="wb-actions">
        <button class="wb-btn" type="button" @click="router.push('/planning')">回入口</button>
        <button v-if="demoStatus.planning" class="wb-btn" type="button" @click="loadSnapshot">
          重试
        </button>
        <button
          class="wb-btn"
          type="button"
          :disabled="runStatus !== 'converged' || saving"
          @click="saveToArchive"
        >{{ saved ? '已存入档案' : '存入档案' }}</button>
        <button
          class="wb-btn primary"
          type="button"
          :disabled="!deliverables.length || runStatus !== 'converged' || producing"
          @click="produceAll"
        >{{ producing ? '正在取回…' : '生成交付' }}</button>
      </div>
    </header>

    <!-- 三栏：过程 / 推理 / 产出 -->
    <div class="wb-body">
      <section class="wb-col wb-col--left">
        <AgentExecStream :items="stream" />
      </section>

      <section class="wb-col wb-col--center">
        <!-- 加载/错误：如实说明，不铺演示数据 -->
        <!-- 文案用中性的「加载」：原先写「正在恢复任务」，对刚点完
             「生成方案」的新任务听起来像出了故障在抢救。
             不用 run.created_at 去区分新旧 —— 后端的 format_utc_datetime
             把 naive UTC 当上海时间转，返回的字符串差 8 小时（前端按本地
             解析后恰好显示正确，属两个错误互相抵消），拿它算「多久前建的」
             必然误判。 -->
        <div v-if="loading" class="wb-state">
          <a-spin tip="正在加载任务…" />
        </div>
        <div v-else-if="loadError" class="wb-state">
          <p class="hint-err">{{ loadError }}</p>
          <a-button size="small" @click="loadSnapshot">重试</a-button>
        </div>
        <!-- 空态：图还没长出来（阶段刚起步）或任务已结束但无节点 -->
        <div v-else-if="!graphData.nodes.length" class="wb-state">
          <template v-if="runStatus === 'converged' || runStatus === 'failed'">
            <p class="hint-title">这次规划没有产出决策图</p>
            <p class="hint-sub">任务已结束，但没记录到任何节点 —— 可以回入口页重新开始。</p>
          </template>
          <template v-else>
            <p class="hint-title">正在规划…</p>
            <p class="hint-sub">阶段推进中，决策图会逐步长出来。</p>
          </template>
        </div>
        <template v-else>
          <PurchaseDecisionGraph
            :graph-data="graphData"
            :meta="graphMeta"
            :converged="runStatus === 'converged'"
            @node-click="onNodeClick"
            @clear-selection="selectedNode = null"
          />
          <div v-if="selectedNode" class="wb-detail">
            <span class="wb-detail-type" :style="{ color: NODE_TYPE_COLOR[selectedNode.type] }">
              {{ selectedNode.type }}
            </span>
            <span class="wb-detail-name">{{ selectedNode.name }}</span>
            <span class="wb-detail-state mono">{{ STATE_LABEL[selectedNode.state] || selectedNode.state }}</span>
            <span v-if="selectedNode.meta?.pruneReason" class="wb-detail-why">
              排除原因：{{ selectedNode.meta.pruneReason }}
            </span>
            <span v-else-if="selectedNode.meta?.price" class="wb-detail-why mono">
              ¥{{ selectedNode.meta.price }}
            </span>
            <button class="wb-detail-close" type="button" @click="selectedNode = null">×</button>
          </div>
        </template>
      </section>

      <section class="wb-col wb-col--right">
        <DeliverablesPanel
          :items="deliverables"
          :question="pendingQuestion"
          @answer="onAnswer"
          @download="onDownload"
          @download-pdf="onDownloadPdf"
        />
      </section>
    </div>
  </div>
</template>

<script setup>
/**
 * 采购智能体 · 工作台执行页
 *
 * 三栏分工：
 *   左 = 它做了什么（执行流）
 *   中 = 它怎么想的（决策图）
 *   右 = 我能拿到什么（待交付 + 待确认）
 * 三者不重复：图里不出现文件，交付区不出现推理，执行流不出现结论。
 *
 * 数据来源（2026-09-24 接真后端，原先全是 purchaseDemo 的 mock）：
 *   · 首屏 → GET /api/planning/runs/{id}      快照，刷新即恢复（不重放事件）
 *   · 增量 → GET /api/planning/runs/{id}/events  SSE，after_seq 续传
 *   · 拍板 → POST /api/planning/runs/{id}/answer
 * 三处共用同一本事件账（planning_events），前后端不会漂。
 *
 * 图的「渐进长出」由后端驱动：每个阶段跑完发一条 graph 事件（整图），
 * 前端只负责替换 —— 合并逻辑在服务端一处，前端不做第二套。
 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { message } from 'ant-design-vue'
import { useRoute, useRouter } from 'vue-router'
import AgentExecStream from '@/components/purchase/AgentExecStream.vue'
import PurchaseDecisionGraph from '@/components/purchase/PurchaseDecisionGraph.vue'
import DeliverablesPanel from '@/components/purchase/DeliverablesPanel.vue'
import { planningApi } from '@/apis/planning_api'
import { demoStatus } from '@/apis/demoStatus'
import {
  NODE_TYPE_COLOR,
  STATE_LABEL
} from '@/utils/planningGraphStyle'

const route = useRoute()
const router = useRouter()

// ── 任务实例 ──────────────────────────────────────────────
// run id 优先取 query（入口页建好后带过来）；没有则说明是直接访问
// /planning/run —— 如实提示回入口，不编一个假任务出来。
const runId = ref(String(route.query.run || ''))
const runStatus = ref('running')
const loading = ref(true)
const loadError = ref('')

const graphData = ref({ nodes: [], edges: [] })
const graphMeta = ref({})
const stream = ref([])
const deliverables = ref([])
const pendingQuestion = ref(null)

/**
 * 给每一行一个稳定 id。
 *
 * 执行流的渲染会用 `v-for` 的 key 与「是不是最后一行」的判断 ——
 * 之前用数组下标，但「只看核心」开关会把推理行滤掉，下标就漂了
 * （描线会画错位置、Vue 复用错节点）。给每行一个自增 id 就稳定了。
 */
let streamSeq = 0
const pushRow = (row) => {
  stream.value.push({ ...row, uid: `r${++streamSeq}` })
}

const taskLabel = computed(() => {
  const parts = []
  const scene = route.query.scene
  if (scene) parts.push(scene)
  // 预算只挂在 query 上做展示：表单给的是原话（「¥6万」），预设给的是数字。
  // 数字才格式化，字符串原样显示 —— 对「¥6万」做 Number() 会得到 NaN。
  const budget = route.query.budget
  if (budget) {
    const n = Number(budget)
    parts.push(Number.isFinite(n) && n > 0 ? '¥' + n.toLocaleString('en-US') : String(budget))
  }
  return parts.join(' · ') || '采购规划任务'
})

// ── 事件 → 界面 ───────────────────────────────────────────
// 后端只发这 8 类（刻意不学 chat 的 15 种）：
//   phase / think / retrieve / call / graph / question / deliverable / done
//
// phase 现在有两种状态（后端从图的 debug 流里取的）：
//   state='running' → 这一步**正在做**，带 hint 说明在等什么
//   state='done'    → 做完了，带 ms 真实耗时
// 早先只有 done 一种，且没有耗时 —— 最慢的两步（检索 ~9s、模型对比 ~8s）
// 期间界面一动不动，看起来像卡死。
const applyEvent = (kind, payload) => {
  switch (kind) {
    case 'phase': {
      const phase = payload.phase
      // ═══════════════════════════════════════════════════════════════
      // 2026-09-26：阶段从「流程步骤」降级成「归类标签」
      // ═══════════════════════════════════════════════════════════════
      // 旧实现按写死的七个阶段推进，所以有 todo→running→done 三态、
      // 还要给每一步算耗时。现在走法由模型定，阶段只是给工具调用**分组**
      // 用的（「这次搜索属于『搜索候选』」），不再是一条可预期的流水线。
      //
      // 所以这里不再维护 todo 态、也不再算耗时 —— 真实耗时由调用行自己带。
      // 同名的阶段标签只落一条，后续调用往它下面挂。
      const exist = stream.value.find((x) => x.kind === 'phase' && x.phase === phase)
      if (exist) {
        exist.state = 'running'
        exist.detail = payload.hint || exist.detail
        exist.time = nowClock()
      } else {
        pushRow({
          kind: 'phase',
          phase,
          title: payload.label || phase,
          detail: payload.hint || '',
          state: 'running',
          time: nowClock()
        })
      }
      break
    }

    // 推理增量：**追加到上一条思考里**，而不是新起一行。
    // 后端按 0.22s 节流推送，一段段长出来 —— 这就是「实时」的来源。
    //
    // kind 两种：
    //   reasoning 模型的自言自语（试错、自我纠正），弱化显示
    //   content   它最终要说的话，正常显示
    // 两者观感不同，混在一起会让用户以为模型在胡言乱语。
    case 'think_delta': {
      const kind = payload.kind || 'content'
      const last = stream.value[stream.value.length - 1]
      if (last && last.streaming && last.thinkKind === kind) {
        last.detail += payload.text || ''
      } else {
        // 换了一种文本（reasoning → content）：收掉上一条，另起一条，
        // 否则「它在想」和「它的结论」会粘成一段。
        const prev = stream.value[stream.value.length - 1]
        if (prev && prev.streaming) {
          prev.streaming = false
          prev.state = 'done'
        }
        pushRow({
          kind: 'think',
          // ⚠️ 不给 title：一行的空间要留给**它说了什么**。
          // 原先 title 是「正在权衡 / 判断依据」，占掉半行，而摘要又是一句
          // 推理的开头 —— 界面上变成「判断依据 · 品类标准知识库没收录…」，
          // 前半截是废话。现在整行就是那句话本身（见 AgentExecStream.briefOf）。
          title: '',
          detail: payload.text || '',
          streaming: true,          // 有光标；收到收尾事件后置 false
          thinkKind: kind,
          by: 'llm',
          state: 'running',
          // ⚠️ 不记 startedAt / 不算耗时。
          // 刷新时事件是**重放**的，几秒的推理会在几十毫秒内全部到达，
          // 本地计时算出「0ms」这种假数字。真实耗时由所属的 phase 行
          // 提供（后端按节点实测），这里再算一遍只会误导。
          time: nowClock()
        })
      }
      break
    }

    case 'think':
    case 'retrieve':
    case 'call':
    case 'produce': {
      // 推理结束时，把上面那条流式行**收尾**（去掉光标），而不是再插一条
      // —— 否则同一段推理会显示两遍。耗时由 phase 行提供，这里不算（见上）。
      const prev = stream.value[stream.value.length - 1]
      if (prev && prev.streaming) {
        prev.streaming = false
        prev.state = 'done'
      }
      pushRow({
        kind,
        title: payload.title || '',
        detail: payload.detail || '',
        // 判断来源：llm 模型判断 / rule 规则兜底。原样透传给 AgentExecStream
        // 显示出来 —— 不显示的话，降级输出和模型输出在界面上无从分辨。
        by: payload.by || '',
        // 真实入参与返回样本（call 事件带）：可展开核对「它真去搜了」。
        args: payload.args || null,
        sample: payload.sample || null,
        ok: payload.ok,
        // 配对键：call_result 靠它找到这条，并行调用时不会串行
        toolCallId: payload.tool_call_id || '',
        state: 'done',
        time: nowClock()
      })
      break
    }
    // 工具**返回**：补到刚才那条调用上，而不是新起一行。
    // ═══════════════════════════════════════════════════════════════
    // 2026-09-26：按 tool_call_id 精确配对，不能靠「最后一条没返回的」
    // ═══════════════════════════════════════════════════════════════
    // 模型会**并行**调多个工具（实测一次并行搜 2~3 个关键词），返回顺序
    // 不保证。按「最后一条还没返回的 call」去挂，会把 A 的结果挂到 B 上 ——
    // 界面上就是「搜的是隔音毡、返回的却是吸音板」，看着像模型在胡说。
    case 'call_result': {
      const cid = payload.tool_call_id || ''
      let row = cid
        ? stream.value.find((x) => x.kind === 'call' && x.toolCallId === cid)
        : null
      if (!row) {
        // 没有 id（旧事件）或找不到：退回到「最后一条还没返回的」。
        // 单次调用时这是对的；并行时可能配错，但总比丢掉强。
        row = [...stream.value].reverse().find((x) => x.kind === 'call' && !x.result)
      }
      if (row) {
        row.result = payload.text || ''
      } else {
        pushRow({
          kind: 'call',
          title: '工具返回',
          detail: '',
          result: payload.text || '',
          state: 'done',
          time: nowClock()
        })
      }
      break
    }

    case 'graph':
      // 整图替换 —— 合并已在服务端做过
      graphData.value = {
        nodes: payload.nodes || [],
        edges: payload.edges || []
      }
      break

    case 'question':
      pendingQuestion.value = {
        text: payload.text,
        options: (payload.options || []).map((o) => ({ ...o }))
      }
      runStatus.value = 'awaiting'
      break
    case 'deliverable':
      upsertDeliverable(payload)
      break
    case 'done':
      // ⚠️ 收尾时把还在流式的那条行**收掉**。否则最后一段推理永远停在
      // streaming 状态 —— 界面上是一条没有内容、光标一直闪的行。
      // 实测一次 run 会留下 4~5 条这样的空「思考」行。
      stream.value.forEach((x) => {
        if (x.streaming) { x.streaming = false; x.state = 'done' }
      })
      runStatus.value = payload.status || 'converged'
      // 收敛/失败后**收掉待拍板的问题** —— 否则用户已经点过「定下来」，
      // 那个问题卡还挂在右栏，看起来像没生效、又像在重复问。
      // 后端在 _patch_run 里已经清空了 run.question，前端也要跟着清。
      pendingQuestion.value = null
      if (payload.status === 'failed') {
        loadError.value = payload.error || '任务执行失败'
      }
      break
    default:
      break
  }
}

const upsertDeliverable = (d) => {
  if (!d?.id) return
  const i = deliverables.value.findIndex((x) => x.id === d.id)
  const item = {
    id: d.id, name: d.name, meta: d.meta, state: d.state, progress: d.progress,
    // ⚠️ `data` 必须带上：后端把交付物**正文**（结构化的方案/对比表/预算）
    // 随事件下发，交付区就地渲染它。原先这里只挑了 id/name/meta/state，
    // 正文被丢掉 —— 面板就只剩文件名，只能靠弹窗再请求一次，
    // 而那次请求返回的又是同一段节点罗列。这是「交付物很简陋」的一半原因。
    data: d.data ?? null,
    // 能不能导出 PDF（只有报告能）。事件里不带，靠收尾后 loadSnapshot 补齐。
    pdf: Boolean(d.pdf),
  }
  if (i >= 0) deliverables.value[i] = { ...deliverables.value[i], ...item }
  else deliverables.value.push(item)
}

const nowClock = () => {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

// ── 载入 ──────────────────────────────────────────────────
let abort = null

const loadSnapshot = async () => {
  if (!runId.value) {
    loading.value = false
    loadError.value = '缺少任务 ID —— 请从入口页开始一次采购规划。'
    return
  }
  loading.value = true
  loadError.value = ''
  try {
    const run = await planningApi.getRun(runId.value)
    runStatus.value = run.status
    graphData.value = run.graph
    graphMeta.value = run.meta || {}
    pendingQuestion.value = run.question
      ? { text: run.question.text, options: run.question.options || [] }
      : null
    // 交付物：快照里没有正文，靠事件补齐。刷新时先按约定的三件套占位，
    // 再**真的把内容取回来** —— 只占位会让面板显示「已生成」却没有正文。
    if (run.status === 'converged') {
      for (const d of DELIVERABLE_FALLBACK) upsertDeliverable({ ...d, state: 'running' })
      await Promise.all(DELIVERABLE_FALLBACK.map(async (d) => {
        try {
          const got = await planningApi.getDeliverable(runId.value, d.id)
          upsertDeliverable({
            ...d,
            state: got?.data ? 'ready' : 'empty',
            data: got?.data || null,
            // 后端说这份能不能导 PDF（只有报告能）——
            // 不带上的话按钮会按 undefined 判false，永远不显示
            pdf: Boolean(got?.pdf),
          })
        } catch {
          // 取不到就如实标成无内容，不假装已生成
          upsertDeliverable({ ...d, state: 'empty', data: null })
        }
      }))
    }
    subscribe()
  } catch (e) {
    loadError.value = e?.message || '任务加载失败'
    demoStatus.planning = true
  } finally {
    loading.value = false
  }
}

const DELIVERABLE_FALLBACK = [
  // 报告排第一 —— 它是主件，另外三份是明细附件（与后端 DELIVERABLE_SPEC 一致）
  { id: 'd-report', name: '采购规划报告', meta: '完整方案：结论、依据、预算与风险' },
  { id: 'd-plan', name: '采购方案.md', meta: '含清单、顺序与依赖' },
  { id: 'd-compare', name: '候选对比表', meta: '按硬约束逐项横比' },
  { id: 'd-budget', name: '预算分配表', meta: '按类别拆分预算' }
]

// 事件流：断线自动重连并带 after_seq 续传（事件落库且 seq 单调，所以能这么做）
let lastSeq = 0
let retrying = false

const subscribe = async () => {
  if (!runId.value) return
  abort?.abort?.()
  abort = new AbortController()
  try {
    await planningApi.streamEvents(runId.value, {
      afterSeq: lastSeq,
      signal: abort.signal,
      onEvent: (kind, payload, seq) => {
        if (seq) lastSeq = Math.max(lastSeq, seq)
        applyEvent(kind, payload)
      }
    })
  } catch (e) {
    // abort 是主动断开，不重连
    if (abort?.signal?.aborted) return
    if (retrying) return
    retrying = true
    setTimeout(() => { retrying = false; subscribe() }, 2000)
    return
  }
  // 流自然结束（收敛/失败）后不再重连
}

// ── 卡片动作 ──────────────────────────────────────────────
const selectedNode = ref(null)
const onNodeClick = (node) => { selectedNode.value = node }

/**
 * 图上被标为「已采纳」的节点。
 *
 * ⚠️ 买**一套**时会有多件（床、沙发、衣柜各一件）—— 2026-09-27 之前
 * 这里一律 `.find()` 只取一件，档案里就只记得下第一件，另外几件凭空消失。
 */
const selectedNodes = computed(() =>
  graphData.value.nodes.filter((n) => n.state === 'selected')
)

const onAnswer = async (key) => {
  if (!runId.value) return
  try {
    const run = await planningApi.answer(runId.value, key)
    runStatus.value = run.status
    pendingQuestion.value = run.question
      ? { text: run.question.text, options: run.question.options || [] }
      : null
    // 续跑会产生新事件，重新订阅（带 after_seq，不重放）
    subscribe()
  } catch (e) {
    loadError.value = e?.message || '提交回答失败'
  }
}

const onDownload = async (d) => {
  if (!runId.value) return
  try {
    const data = await planningApi.getDeliverable(runId.value, d.id)
    if (!data?.content) return
    const blob = new Blob([data.content], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${data.name || 'deliverable'}.md`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    loadError.value = e?.message || '下载失败'
  }
}

/**
 * 导出 PDF。
 *
 * 比 Markdown 多两件事要做对：
 *   1. **忙态**：PDF 要服务端排版，有几秒钟。不加忙态用户会连点，
 *      导出多份。所以先把这一份标成 pdfBusy，再恢复。
 *   2. **文件名**：报告标题里有「·」（「搬家 · 采购规划报告」），
 *      某些系统不允许。换成下划线。
 */
const onDownloadPdf = async (d) => {
  if (!runId.value || d.pdfBusy) return
  upsertDeliverable({ ...d, pdfBusy: true })
  try {
    const safe = String(d.name || '采购规划报告').replace(/[\\/:*?"<>|·]/g, '_')
    await planningApi.downloadPdf(runId.value, d.id, `${safe}.pdf`)
  } catch (e) {
    loadError.value = e?.message || 'PDF 导出失败'
  } finally {
    upsertDeliverable({ ...d, pdfBusy: false })
  }
}

// 存入档案 —— 把这次规划的结论沉淀成一条可追踪的档案记录。
//
// 之前工作台跑完就结束了：结果只能看，落不进档案，也就没有后续
// （推进阶段 / 设提醒 / 复盘）。而档案页反过来也不知道这条记录
// 是从哪次推演来的。这里把两头接上：记录带 `runId` 回指本次 run。
const saved = ref(false)
const saving = ref(false)

const saveToArchive = async () => {
  if (saving.value || saved.value) return
  const picked = selectedNodes.value
  // 没有入选的就退回第一件候选（至少让档案里有个名字，而不是空着）
  const primary = picked[0] || graphData.value.nodes.find((n) => n.type === '候选商品')
  saving.value = true
  try {
    const { decisionsApi } = await import('@/apis/decisions_api')
    const rec = {
      id: `pl-${Date.now().toString(36)}`,
      phase: 'decided',
      source: 'planning',
      target: primary?.name || taskLabel.value || '采购规划',
      category: route.query.scene || '',
      note: `来自采购规划推演（${graphData.value.nodes.length} 个决策节点）`,
      rawIdea: '',
      budget: route.query.budget ? `¥${route.query.budget}` : '',
      forWhom: '',
      scenario: route.query.scene || '',
      aiSummary: briefThesis(),
      candidates: graphData.value.nodes
        .filter((n) => n.type === '候选商品')
        .map((n) => ({ name: n.name, price: Number(n.meta?.price) || 0 })),
      aiRecommend: primary?.name || '',
      recReason: primary?.meta?.why || '推演过程中选定的候选',
      risk: '',
      bestPrice: primary?.meta?.price ? `¥${primary.meta.price}` : '',
      dealPrice: '', purchasedAt: '', reviewNote: '', dropNote: '',
      reminders: [], insights: [],
      threadId: null,
      runId: runId.value || null,   // ← 回指本次推演
      ts: Date.now(),
      updatedAt: '刚刚'
    }
    const ok = await decisionsApi.createOne(rec)
    if (ok) { saved.value = true; message.success('已存入购物档案') }
    else message.error('存入失败，请重试')
  } finally {
    saving.value = false
  }
}

const briefThesis = () => {
  const n = graphData.value.nodes.length
  const sel = selectedNodes.value
  if (!sel.length) return `共 ${n} 个决策节点`
  if (sel.length === 1) return `共 ${n} 个决策节点，选定「${sel[0].name}」`
  // 买一套时会有多件入选 —— 报件数而不是只报第一件的名字
  return `共 ${n} 个决策节点，选定 ${sel.length} 件：${sel.map((x) => x.name.slice(0, 8)).join('、')}`
}

const producing = ref(false)

/**
 * 「生成交付」= 把三份交付物的正文取回来。
 *
 * 后端在收敛时就已算好并随事件下发过；这个按钮是给「事件丢了 / 中途刷新 /
 * 想重新拉一次」准备的，所以它是**真的去取**，而不是把状态标成 ready。
 * 原先这里只做 `state: 'ready'` 的映射 —— 没有正文也照样显示「已生成」，
 * 点开是空的。状态必须跟着内容走。
 */
const produceAll = async () => {
  if (!runId.value || producing.value) return
  producing.value = true
  try {
    await Promise.all(deliverables.value.map(async (d) => {
      try {
        const got = await planningApi.getDeliverable(runId.value, d.id)
        upsertDeliverable({
          ...d,
          state: got?.data ? 'ready' : 'empty',
          data: got?.data || null,
        })
      } catch {
        upsertDeliverable({ ...d, state: 'empty', data: null })
      }
    }))
  } finally {
    producing.value = false
  }
}

onMounted(loadSnapshot)
onBeforeUnmount(() => { try { abort?.abort?.() } catch { /* ignore */ } })
</script>

<style lang="less" scoped>
.wb {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--bg-base);
}

/* 页头 */
.wb-head {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 18px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-surface);
}
.wb-sig {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 7px;
  background: var(--accent-50);
  color: var(--accent-700);
  font-size: 0.78rem;
  font-weight: 600;
}
.wb-id {
  min-width: 0;
}
.wb-name {
  margin: 0;
  font-size: 0.86rem;
  font-weight: 600;
  color: var(--text-strong);
}
.wb-task {
  margin: 1px 0 0;
  font-size: 0.72rem;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.wb-actions {
  margin-left: auto;
  display: flex;
  gap: 6px;
  flex: 0 0 auto;
}
.wb-btn {
  font-family: var(--font-body);
  font-size: 0.74rem;
  padding: 5px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-strong);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: color 0.15s ease-out, border-color 0.15s ease-out, background-color 0.15s ease-out;
  &:hover { color: var(--text); }
  &:disabled { opacity: 0.45; cursor: not-allowed; }
  &.primary {
    background: var(--accent-solid);
    border-color: var(--accent-solid);
    color: var(--on-accent);
    &:hover:not(:disabled) { background: var(--accent-600); }
  }
}

/* 三栏 */
.wb-body {
  flex: 1 1 auto;
  min-height: 0;
  display: grid;
  grid-template-columns: 268px minmax(0, 1fr) 288px;
}
.wb-col {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 14px 16px;
  &--left { border-right: 1px solid var(--border); }
  &--center { padding: 14px; }
  &--right {
    border-left: 1px solid var(--border);
    background: var(--bg-sunken);
    overflow-y: auto;
  }
}

/* 中栏的加载 / 错误 / 空三态 */
.wb-state {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  text-align: center;
}
.hint-title { margin: 0; font-size: 0.92rem; font-weight: 600; color: var(--text-strong); }
.hint-sub { margin: 0; font-size: 0.8rem; color: var(--text-muted); line-height: 1.6; max-width: 320px; }
.hint-err { margin: 0; font-size: 0.82rem; color: var(--neg); }

/* 节点详情条 */
.wb-detail {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 9px;
  flex-wrap: wrap;
  margin-top: 9px;
  padding: 8px 11px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-surface);
  font-size: 0.74rem;
}
.wb-detail-type {
  font-weight: 600;
  flex: 0 0 auto;
}
.wb-detail-name {
  color: var(--text-strong);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.wb-detail-state {
  font-size: 0.7rem;
  color: var(--text-muted);
  padding: 1px 7px;
  border-radius: 99px;
  background: var(--bg-sunken);
  flex: 0 0 auto;
}
.wb-detail-why {
  color: var(--text-muted);
  min-width: 0;
}
.wb-detail-close {
  margin-left: auto;
  flex: 0 0 auto;
  width: 20px;
  height: 20px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--text-faint);
  font-size: 0.9rem;
  line-height: 1;
  cursor: pointer;
  &:hover { color: var(--text); background: var(--bg-sunken); }
}

/* 交付物正文现在**就地**渲染在右栏（DeliverablesPanel），
   不再有弹窗预览 —— 原先的 .wb-preview 是那个弹窗的样式，已随之删除。 */

@media (max-width: 1100px) {
  .wb-body {
    grid-template-columns: minmax(0, 1fr);
    grid-auto-rows: minmax(0, auto);
    overflow-y: auto;
  }
  .wb-col {
    &--left {
      border-right: none;
      border-bottom: 1px solid var(--border);
      max-height: 320px;
    }
    &--center { min-height: 420px; }
    &--right {
      border-left: none;
      border-top: 1px solid var(--border);
    }
  }
}
</style>
