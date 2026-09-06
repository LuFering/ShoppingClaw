<template>
  <div class="ws">
    <!-- 界面标题带：全宽，列表与详情都从属于它 -->
    <header class="page-band">
      <h1 class="ws-title">购物档案</h1>
      <div class="stat-strip">
        <span v-if="demoStatus.decisions" class="stat-pill">演示数据 · 等待 /api/decisions</span>
        <span class="stat-pill">需求 <b>{{ countOf('need') }}</b></span>
        <span class="stat-pill">候选 <b>{{ countOf('candidate') }}</b></span>
        <span class="stat-pill">已决策 <b>{{ countOf('decided') }}</b></span>
        <span class="stat-pill">使用中 <b>{{ countOf('using') }}</b></span>
        <span class="stat-pill">已复盘 <b>{{ countOf('reviewed') }}</b></span>
      </div>
    </header>

    <!-- ============ 左：对象列表（按阶段分组） ============ -->
    <aside class="ws-list">
      <div class="list-ctl">
        <input v-model="keyword" class="page-search" type="search" placeholder="搜索想买 / 需求 / 型号…" />
        <div class="ctl-row">
          <a-select v-model:value="stageFilter" size="small" class="ctl-select" :options="stageOptions" />
          <a-button size="small" class="idea-btn lucide-icon-btn" @click="openIdea">
            <Plus :size="13" /><span>记个想法</span>
          </a-button>
        </div>
      </div>

      <div class="list-scroll">
        <template v-for="g in visibleGroups" :key="g.phase">
          <p class="group-label" :class="'gl-' + g.phase">
            {{ g.label }} <span class="num">{{ g.items.length }}</span>
          </p>
          <div
            v-for="r in g.items"
            :key="r.id"
            class="item"
            :class="{ sel: selectedId === r.id }"
            tabindex="0"
            @click="select(r)"
            @keydown.enter="select(r)"
          >
            <div class="item-top">
              <span class="item-title">{{ r.target }}</span>
              <span class="state" :class="PHASES[r.phase].cls"><span class="dot" />{{ PHASES[r.phase].label }}</span>
            </div>
            <div class="item-meta">
              <span class="item-need">{{ snippet(r) }}</span>
              <span class="time mono">{{ r.updatedAt }}</span>
            </div>
          </div>
        </template>

        <div v-if="loadingRecords" class="list-empty">
          <a-spin tip="加载档案…" />
        </div>
        <a-empty
          v-else-if="!visibleGroups.length"
          class="list-empty"
          :image="Empty.PRESENTED_IMAGE_SIMPLE"
          :description="loadError || (records.length ? '没有匹配的记录' : '从一个模糊的想法开始')"
        >
          <a-button v-if="loadError" @click="initRecords">重试</a-button>
          <a-button v-else type="primary" @click="openIdea">记个想法</a-button>
        </a-empty>
      </div>

      <div class="list-foot">
        <a-button type="link" size="small" class="ask-link" @click="goAsk">去提问 ›</a-button>
      </div>
    </aside>

    <!-- ============ 右：详情（按阶段渲染，头部/底栏固定） ============ -->
    <main class="ws-main">
      <div v-if="!selected" class="detail-empty">
        <a-empty :image-style="{ height: '60px' }" description="在左侧选择一条记录，查看它走到了哪一步">
          <a-button @click="openIdea">记个想法</a-button>
        </a-empty>
      </div>

      <div v-else class="detail">
        <div class="detail-head">
          <h2 class="detail-title">{{ selected.target }}</h2>
          <span class="state" :class="PHASES[selected.phase].cls"><span class="dot" />{{ PHASES[selected.phase].label }}</span>
          <span class="head-meta mono">{{ selected.category || '未分类' }} · 更新于 {{ selected.updatedAt }}</span>
        </div>

        <div class="detail-body">
          <!-- ===== 需求段 ===== -->
          <template v-if="selected.phase === 'need'">
            <section class="result">
              <p class="result-label">{{ selected.source === 'ai_draft' ? 'AI 摘要' : '想法' }}</p>
              <p class="draft-summary">{{ selected.aiSummary || selected.rawIdea || selected.note }}</p>
            </section>
            <section class="facts">
              <div class="facts-head">
                <span class="facts-title">结构化需求</span>
                <a-button size="small" @click="fillByAI(selected)">AI 补全需求</a-button>
              </div>
              <div class="fact fact-wide"><p class="fact-label">需求描述</p><p class="fact-value">{{ selected.note }}</p></div>
              <div class="fact"><p class="fact-label">预算</p><p class="fact-value mono">{{ selected.budget || '待补全' }}</p></div>
              <div class="fact"><p class="fact-label">给谁</p><p class="fact-value">{{ selected.forWhom || '待补全' }}</p></div>
              <div class="fact"><p class="fact-label">场景</p><p class="fact-value">{{ selected.scenario || '待补全' }}</p></div>
            </section>
          </template>

          <!-- ===== 候选段 ===== -->
          <template v-else-if="selected.phase === 'candidate'">
            <section class="cands">
              <div class="facts-head">
                <span class="facts-title">候选（{{ selected.candidates.length }}）</span>
              </div>
              <div
                v-for="c in selected.candidates"
                :key="c.id"
                class="cand-row"
                :class="{ chosen: c.chosen }"
              >
                <span class="cand-name">{{ c.name }}</span>
                <span class="cand-price mono">{{ c.price }}</span>
                <span class="cand-note">{{ c.note }}</span>
                <span v-if="c.chosen" class="cand-chosen">主选</span>
                <button v-else class="cand-pick" @click="chooseCandidate(selected, c)">设为主选</button>
                <button class="icon-btn is-danger" title="移除" @click="removeCandidate(selected, c)"><X :size="13" /></button>
              </div>
              <div class="cand-add">
                <a-input v-model:value="candDraft.name" size="small" placeholder="候选型号，如：海尔 501L" />
                <a-input v-model:value="candDraft.price" size="small" placeholder="参考价，如 ¥5699" class="cand-add-price" />
                <a-button size="small" @click="addCandidate(selected)">添加</a-button>
              </div>
              <p v-if="!selected.candidates.length" class="cand-hint">还没有候选，从上方添加，或回对话让 AI 推荐。</p>
            </section>
          </template>

          <!-- ===== 已决策段 ===== -->
          <template v-else-if="selected.phase === 'decided'">
            <section class="result">
              <p class="result-label">AI 推荐</p>
              <div class="result-main">
                <p class="result-name">{{ selected.aiRecommend }}</p>
                <p class="result-price mono">{{ selected.bestPrice }}</p>
              </div>
              <p class="result-reason">{{ selected.recReason }}</p>
            </section>
            <section class="facts">
              <div class="fact fact-wide"><p class="fact-label">需求</p><p class="fact-value">{{ selected.note }}</p></div>
              <div class="fact"><p class="fact-label">预算</p><p class="fact-value mono">{{ selected.budget }}</p></div>
              <div class="fact"><p class="fact-label is-risk">风险</p><p class="fact-value">{{ selected.risk }}</p></div>
            </section>
          </template>

          <!-- ===== 使用中段 ===== -->
          <template v-else-if="selected.phase === 'using'">
            <section class="facts facts-first">
              <div class="fact"><p class="fact-label">实付价</p><p class="fact-value mono">{{ selected.dealPrice || '—' }}</p></div>
              <div class="fact"><p class="fact-label">购买日期</p><p class="fact-value mono">{{ selected.purchasedAt || '—' }}</p></div>
              <div class="fact fact-wide"><p class="fact-label">选择</p><p class="fact-value">{{ selected.aiRecommend }}</p></div>
            </section>
            <section v-if="selected.reminders.length" class="block">
              <h3 class="block-title">温馨提醒</h3>
              <ol class="notes">
                <li v-for="(rm, i) in selected.reminders" :key="i">{{ rm }}</li>
              </ol>
            </section>
          </template>

          <!-- ===== 复盘段 ===== -->
          <template v-else-if="selected.phase === 'reviewed'">
            <section class="result">
              <p class="result-label">复盘小结</p>
              <p class="draft-summary">{{ selected.reviewNote }}</p>
            </section>
            <section class="facts">
              <div class="fact"><p class="fact-label">实付价</p><p class="fact-value mono">{{ selected.dealPrice || '—' }}</p></div>
              <div class="fact"><p class="fact-label">购买日期</p><p class="fact-value mono">{{ selected.purchasedAt || '—' }}</p></div>
            </section>
          </template>

          <!-- ===== 已放弃 ===== -->
          <template v-else>
            <section class="facts facts-first">
              <div class="fact fact-wide"><p class="fact-label">放弃原因</p><p class="fact-value">{{ selected.dropNote || '未填写' }}</p></div>
              <div class="fact fact-wide"><p class="fact-label">需求</p><p class="fact-value">{{ selected.note }}</p></div>
            </section>
          </template>
        </div>

        <footer class="detail-foot">
          <template v-if="selected.phase === 'need'">
            <a-button type="primary" @click="startPicking(selected)">开始挑选</a-button>
          </template>
          <template v-else-if="selected.phase === 'candidate'">
            <a-button type="primary" :disabled="!chosenOf(selected)" @click="confirmChoice(selected)">确定选择</a-button>
          </template>
          <template v-else-if="selected.phase === 'decided'">
            <a-button type="primary" @click="openBuy(selected)">标记已购</a-button>
          </template>
          <template v-else-if="selected.phase === 'using'">
            <a-button type="primary" @click="openReview(selected)">写复盘</a-button>
          </template>
          <a-button
            v-if="selected.threadId && ['decided', 'using', 'reviewed'].includes(selected.phase)"
            @click="continueAsk(selected)"
          >继续问它</a-button>
          <a-button
            v-if="!['dropped', 'reviewed'].includes(selected.phase)"
            danger
            @click="dropRecord(selected)"
          >标记放弃</a-button>
        </footer>
      </div>
    </main>

    <!-- 记个想法 -->
    <a-modal v-model:open="ideaOpen" title="记个想法" :width="480" ok-text="保存" cancel-text="取消" @ok="saveIdea">
      <a-form layout="vertical">
        <a-form-item label="想买什么">
          <a-input v-model:value="ideaForm.target" placeholder="如：洗衣机" />
        </a-form-item>
        <a-form-item label="想法描述（想到什么写什么）">
          <a-textarea v-model:value="ideaForm.rawIdea" :rows="3" placeholder="如：给爸妈换台省心的，静音重要，预算大概四千" />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 标记已购 -->
    <a-modal v-model:open="buyOpen" title="标记已购" :width="420" ok-text="确认已购" cancel-text="取消" @ok="saveBuy">
      <a-form layout="vertical">
        <a-form-item label="实付价">
          <a-input v-model:value="buyForm.dealPrice" class="mono-input" placeholder="如：¥2199" />
        </a-form-item>
        <a-form-item label="购买日期">
          <input v-model="buyForm.purchasedAt" type="date" class="date-input" />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 写复盘 -->
    <a-modal v-model:open="reviewOpen" title="写复盘" :width="520" ok-text="完成复盘" cancel-text="取消" @ok="saveReview">
      <a-form layout="vertical">
        <a-form-item label="复盘小结（值不值、实际体验、下次会怎么做）">
          <a-textarea v-model:value="reviewForm.reviewNote" :rows="4" placeholder="如：用了两个月很满意，静音达标；拖布耗材比预期贵，下次买前先查耗材价" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Modal, message, Empty } from 'ant-design-vue'
import { Plus, X } from 'lucide-vue-next'
import { decisionsApi } from '@/apis/decisions_api'
import { demoStatus } from '@/apis/demoStatus'

const router = useRouter()
const now = Date.now()
const isoDays = (n) => new Date(now - n * 86400000).toISOString().slice(0, 10)
const rel = (ts) => {
  const d = Math.max(1, Math.round((now - ts) / 86400000))
  return d <= 1 ? '昨天' : d <= 7 ? `${d}天前` : `${Math.round(d / 7)}周前`
}

// ===== 阶段定义 =====
const PHASES = {
  need:      { label: '需求池', cls: 'state-need' },
  candidate: { label: '候选中', cls: 'state-candidate' },
  decided:   { label: '已决策', cls: 'state-decided' },
  using:     { label: '使用中', cls: 'state-using' },
  reviewed:  { label: '已复盘', cls: 'state-reviewed' },
  dropped:   { label: '已放弃', cls: 'state-dropped' }
}
const PHASE_ORDER = ['need', 'candidate', 'decided', 'using', 'reviewed']

const mk = (o) => {
  const ts = o.ts ?? now
  return {
    id: o.id, phase: o.phase, source: o.source || 'manual',
    target: o.target, category: o.category || '',
    note: o.note || o.rawIdea || '', rawIdea: o.rawIdea || '',
    budget: o.budget || '', forWhom: o.forWhom || '', scenario: o.scenario || '',
    aiSummary: o.aiSummary || '',
    candidates: o.candidates || [],
    aiRecommend: o.aiRecommend || '', recReason: o.recReason || '', risk: o.risk || '', bestPrice: o.bestPrice || '',
    dealPrice: o.dealPrice || '', purchasedAt: o.purchasedAt || '',
    reviewNote: o.reviewNote || '', dropNote: o.dropNote || '',
    reminders: o.reminders || [], threadId: o.threadId || null,
    ts, updatedAt: rel(ts)
  }
}

// ===== 数据（经 decisions_api mock 服务层持久化到 localStorage；
//        后端 decisions 表与端点实现后，仅需替换 decisions_api 内部）=====
const records = ref([])
const loadingRecords = ref(true)
const loadError = ref('')

const initRecords = async () => {
  loadingRecords.value = true
  loadError.value = ''
  try {
    records.value = await decisionsApi.load()
  } catch {
    loadError.value = '档案加载失败'
  } finally {
    loadingRecords.value = false
  }
}

// 任何记录变更（阶段流转/字段修改）后自动持久化（防抖）
let saveTimer = null
watch(records, () => {
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    decisionsApi.saveAll(records.value).catch(() => {})
  }, 300)
}, { deep: true })

initRecords()

// ===== 列表 =====
const keyword = ref('')
const stageFilter = ref('all')
const selectedId = ref(null)

const stageOptions = [
  { label: '全部阶段', value: 'all' },
  { label: '需求池', value: 'need' },
  { label: '候选中', value: 'candidate' },
  { label: '已决策', value: 'decided' },
  { label: '使用中', value: 'using' },
  { label: '已复盘', value: 'reviewed' },
  { label: '已放弃', value: 'dropped' }
]

const countOf = (phase) => records.value.filter((r) => r.phase === phase).length
const touch = (r) => { r.ts = Date.now(); r.updatedAt = rel(r.ts) }

const visibleGroups = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  const pool = records.value.filter((r) => {
    if (stageFilter.value === 'all' ? r.phase === 'dropped' : r.phase !== stageFilter.value) return false
    if (kw && !`${r.target} ${r.note} ${r.rawIdea} ${r.aiRecommend}`.toLowerCase().includes(kw)) return false
    return true
  })
  return PHASE_ORDER
    .map((p) => ({ phase: p, label: PHASES[p].label, items: pool.filter((r) => r.phase === p).sort((a, b) => b.ts - a.ts) }))
    .filter((g) => g.items.length)
})

const selected = computed(() => records.value.find((r) => r.id === selectedId.value) || null)
const select = (r) => { selectedId.value = r.id }

const snippet = (r) => ({
  need: r.note || r.rawIdea,
  candidate: r.candidates.length ? `候选 ${r.candidates.length} 个${chosenOf(r) ? ` · 主选 ${chosenOf(r).name}` : ''}` : '待添加候选',
  decided: r.aiRecommend ? `选定 ${r.aiRecommend}` : '—',
  using: r.dealPrice ? `已购 ${r.dealPrice}` : '已下单',
  reviewed: r.reviewNote || '已复盘',
  dropped: r.dropNote || '已放弃'
}[r.phase])

// ===== 阶段流转 =====
const chosenOf = (r) => (r.candidates || []).find((c) => c.chosen) || null
const candDraft = ref({ name: '', price: '' })

const startPicking = (r) => {
  if (!r.candidates) r.candidates = []
  r.phase = 'candidate'
  touch(r)
}

const chooseCandidate = (r, c) => {
  r.candidates.forEach((x) => { x.chosen = x === c })
  touch(r)
}
const removeCandidate = (r, c) => {
  r.candidates = r.candidates.filter((x) => x !== c)
  touch(r)
}
const addCandidate = (r) => {
  const name = candDraft.value.name.trim()
  if (!name) { message.warning('请填写候选型号'); return }
  r.candidates.push({ id: `c-${Date.now()}`, name, price: candDraft.value.price.trim() || '待查', note: '', chosen: !chosenOf(r) })
  candDraft.value = { name: '', price: '' }
  touch(r)
}

const confirmChoice = (r) => {
  const c = chosenOf(r)
  if (!c) return
  r.aiRecommend = c.name
  r.bestPrice = c.price
  r.phase = 'decided'
  touch(r)
  message.success(`已确定选择：${c.name}`)
}

const dropRecord = (r) => {
  Modal.confirm({
    title: `放弃「${r.target}」？`,
    content: '记录会移入「已放弃」，可随时通过阶段筛选找回。',
    okText: '放弃',
    okType: 'danger',
    cancelText: '取消',
    onOk() {
      r.dropNote = ''
      r.phase = 'dropped'
      touch(r)
    }
  })
}

// ===== AI 补全（骨架期本地启发式；交互与将来接后端 LLM 一致）=====
const fillByAI = (r) => {
  const text = `${r.rawIdea} ${r.note}`
  const bm = text.match(/预算[^，。；,;]*?(\d+(?:[.,，]\d+)*)(?:\s*(万|元|块))?/) || text.match(/(\d+(?:[.,，]\d+)*)\s*(?:元|块)/)
  const fm = text.match(/给(爸妈|父母|孩子|儿子|女儿|老婆|老公|女友|男友)/)
  const sm = text.match(/(装修|新生儿|开学|送礼|搬家|通勤|办公|自用|出租|宠物|卧室|客厅)/)
  r.budget = bm ? `¥${bm[1]}${bm[2] || ''}` : (r.budget || '待定')
  r.forWhom = fm ? fm[1] : (text.includes('自用') ? '自己' : (r.forWhom || '待定'))
  r.scenario = sm ? sm[1] : (r.scenario || '日常')
  message.success('AI 已补全需求，字段可手动修改')
}

// ===== 记个想法 =====
const ideaOpen = ref(false)
const ideaForm = ref({ target: '', rawIdea: '' })
const openIdea = () => {
  ideaForm.value = { target: '', rawIdea: '' }
  ideaOpen.value = true
}
const saveIdea = () => {
  const f = ideaForm.value
  if (!f.target.trim()) { message.warning('先写下想买什么'); return }
  const r = mk({ id: `nd-${Date.now()}`, phase: 'need', source: 'manual', target: f.target.trim(), rawIdea: f.rawIdea.trim(), note: f.rawIdea.trim(), ts: now })
  records.value.unshift(r)
  selectedId.value = r.id
  ideaOpen.value = false
  message.success('已记入需求池')
}

// ===== 标记已购 =====
const buyOpen = ref(false)
const buyForm = ref({ dealPrice: '', purchasedAt: '' })
let buyTarget = null
const openBuy = (r) => {
  buyTarget = r
  buyForm.value = { dealPrice: r.bestPrice || '', purchasedAt: isoDays(0) }
  buyOpen.value = true
}
const saveBuy = () => {
  if (!buyForm.value.dealPrice.trim()) { message.warning('填一下实付价'); return }
  buyTarget.dealPrice = buyForm.value.dealPrice.trim()
  buyTarget.purchasedAt = buyForm.value.purchasedAt
  buyTarget.phase = 'using'
  touch(buyTarget)
  buyOpen.value = false
  message.success('已标记购买，进入使用中')
}

// ===== 写复盘 =====
const reviewOpen = ref(false)
const reviewForm = ref({ reviewNote: '' })
let reviewTarget = null
const openReview = (r) => {
  reviewTarget = r
  reviewForm.value = { reviewNote: r.reviewNote || '' }
  reviewOpen.value = true
}
const saveReview = () => {
  if (!reviewForm.value.reviewNote.trim()) { message.warning('写一句小结吧'); return }
  reviewTarget.reviewNote = reviewForm.value.reviewNote.trim()
  reviewTarget.phase = 'reviewed'
  touch(reviewTarget)
  reviewOpen.value = false
  message.success('复盘完成')
}

const continueAsk = (r) => router.push(r.threadId ? { path: '/agent', query: { open_thread: r.threadId } } : { path: '/agent' })
const goAsk = () => router.push('/agent')
</script>

<style lang="less" scoped>
/* 工作台骨架：全宽标题带 + 左右分栏，各自内部滚动 */
.ws {
  display: grid;
  grid-template-columns: 460px minmax(0, 1fr);
  /* 行1=界面标题带（全宽 auto），行2=工作区。行高锁定为剩余视口高度：
     AppLayout 的 #app-router-view 以 ID 特异性给本元素附了 overflow-y:auto，
     若行高随内容增长会退化为整页滚动 */
  grid-template-rows: auto minmax(0, 1fr);
  width: 100%;
  height: 100%;
  max-width: 1440px;
  margin: 0 auto;
  color: var(--text);
  overflow: hidden;
}

.page-band {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px 14px;
  padding: 16px 20px 12px;
  border-bottom: 1px solid var(--border);
}
.ws-title {
  font-family: var(--font-display);
  font-size: 1.35rem;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text-strong);
  margin: 0;
}
.page-band .stat-strip { margin-top: 0; }

/* ===== 左列表 ===== */
.ws-list {
  display: flex;
  flex-direction: column;
  min-width: 0;
  border-right: 1px solid var(--border);
}

.list-ctl {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 20px 10px;
  border-bottom: 1px solid var(--border);
}
.page-search { width: 100%; flex: none; }
.ctl-row { display: flex; align-items: center; gap: 8px; }
.ctl-select { min-width: 104px; }
.idea-btn { margin-left: auto; }

.list-scroll { flex: 1; overflow-y: auto; padding: 12px 12px 6px; }
.group-label {
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--text-strong);
  margin: 4px 6px 8px;
  .num { font-family: var(--font-mono); font-size: 0.72rem; color: var(--text-muted); }
}
.gl-need { color: var(--info); }

/* 列表项：紧凑卡片（两行式） */
.item {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 8px 12px;
  margin-bottom: 6px;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  cursor: pointer;
  transition: border-color 0.15s ease-out, box-shadow 0.15s ease-out;
  &:hover {
    border-color: var(--border-strong);
    box-shadow: 0 1px 3px var(--shadow-2);
  }
  &:focus-visible { outline: none; border-color: var(--accent-500); }
  &.sel {
    border-color: var(--accent-500);
    box-shadow: 0 1px 3px var(--shadow-2);
  }
}
.item-top { display: flex; align-items: center; gap: 8px; min-width: 0; }
.item-title {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-strong);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.item-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  .item-need {
    flex: 1;
    min-width: 0;
    font-size: 0.78rem;
    color: var(--text-muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .time { font-size: 0.7rem; color: var(--text-faint); flex-shrink: 0; }
}
.list-empty { padding: 32px 0; }

.list-foot {
  display: flex;
  align-items: center;
  padding: 6px 20px 10px;
  border-top: 1px solid var(--border);
}
.ask-link { padding-left: 0; }

/* ===== 右详情：头部/底栏固定，仅内容区滚动 ===== */
.ws-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}
.detail-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  padding: 40px;
}
.detail {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  width: 100%;
  max-width: 720px;
  margin: 0 auto;
  padding: 0 32px;
}
.detail-head {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 0 12px;
  border-bottom: 1px solid var(--border);
}
.detail-title {
  font-family: var(--font-display);
  font-size: 1.08rem;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text-strong);
  margin: 0;
}
.head-meta {
  margin-left: auto;
  font-size: 0.74rem;
  color: var(--text-faint);
  flex-shrink: 0;
}

/* 阶段状态：圆点 + 语义色文字（不用胶囊容器） */
.state {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.8rem;
  font-weight: 500;
  white-space: nowrap;
  flex-shrink: 0;
  .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; flex-shrink: 0; }
}
.state-need { color: var(--info); }
.state-candidate { color: var(--warn); }
.state-decided { color: var(--accent-700); }
.state-using { color: var(--pos); }
.state-reviewed { color: var(--text-muted); }
.state-dropped { color: var(--text-faint); }

.detail-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px 0 8px;
}

/* 主块：结论先行，纯排版 */
.result {
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border);
}
.result-label { margin: 0 0 6px; font-size: 0.72rem; color: var(--text-faint); }
.result-main {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px 24px;
  flex-wrap: wrap;
}
.result-name { margin: 0; font-size: 1.1rem; font-weight: 600; color: var(--text-strong); }
.result-price {
  margin: 0;
  font-size: 0.92rem;
  font-weight: 600;
  color: var(--accent-700);
  font-variant-numeric: tabular-nums;
}
.result-reason { margin: 6px 0 0; font-size: 0.82rem; color: var(--text-muted); line-height: 1.6; }
.draft-summary { margin: 0; font-size: 0.88rem; color: var(--text); line-height: 1.65; }

/* 次：事实键值 */
.facts {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px 24px;
  padding: 14px 0 0;
}
.facts-first { padding-top: 2px; }
.facts-head {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.facts-title { font-size: 0.84rem; font-weight: 600; color: var(--text-strong); }
.fact { min-width: 0; }
.fact-wide { grid-column: 1 / -1; }
.fact-label {
  margin: 0 0 3px;
  font-size: 0.72rem;
  color: var(--text-faint);
  &.is-risk { color: var(--warn); }
}
.fact-value { margin: 0; font-size: 0.86rem; color: var(--text); line-height: 1.55; word-break: break-word; }

/* 候选列表 */
.cands { padding-bottom: 4px; }
.cand-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  margin-bottom: 6px;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  &.chosen { border-color: var(--accent-500); }
}
.cand-name { font-size: 0.88rem; font-weight: 600; color: var(--text-strong); flex-shrink: 0; }
.cand-price { font-size: 0.78rem; color: var(--text-muted); flex-shrink: 0; }
.cand-note {
  flex: 1;
  min-width: 0;
  font-size: 0.78rem;
  color: var(--text-faint);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.cand-chosen { font-size: 0.76rem; font-weight: 600; color: var(--accent-700); flex-shrink: 0; }
.cand-pick {
  border: none;
  background: transparent;
  font-size: 0.76rem;
  font-family: var(--font-body);
  color: var(--accent-600);
  cursor: pointer;
  flex-shrink: 0;
  padding: 0;
  &:hover { text-decoration: underline; }
}
.cand-add {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 2px;
  .cand-add-price { width: 140px; flex: none; }
}
.cand-hint { margin: 8px 0 0; font-size: 0.78rem; color: var(--text-faint); }

.block { margin-top: 16px; }
.block-title {
  font-family: var(--font-display);
  font-size: 0.84rem;
  font-weight: 600;
  color: var(--text-strong);
  margin: 0 0 8px;
}

.notes {
  margin: 0;
  padding-left: 18px;
  list-style: decimal;
  li {
    font-size: 0.83rem;
    color: var(--text);
    line-height: 1.7;
    &::marker { color: var(--text-faint); font-family: var(--font-mono); font-size: 0.76rem; }
  }
}

/* 底栏固定：操作不随内容滚动 */
.detail-foot {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 0 16px;
  background: var(--bg-base);
  border-top: 1px solid var(--border);
}

.mono, .num { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }

.date-input {
  width: 100%;
  height: 32px;
  padding: 0 10px;
  font-family: var(--font-body);
  font-size: 0.85rem;
  color: var(--text);
  background: var(--bg-surface);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  outline: none;
  &:focus { border-color: var(--accent-500); }
}
.mono-input { font-family: var(--font-mono); }

@media (max-width: 860px) {
  .ws { grid-template-columns: 1fr; height: auto; overflow: visible; }
  .ws-list { border-right: none; border-bottom: 1px solid var(--border); }
  .list-scroll { max-height: 340px; }
  .detail { padding: 0 20px 24px; }
}
</style>
