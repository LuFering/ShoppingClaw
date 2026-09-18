<template>
  <div class="gift-concierge">
    <header class="gc-header">
      <div class="gc-brand">
        <span class="gc-mark">礼</span>
        <div>
          <h1>送礼顾问</h1>
          <p>把一份心意挑到合适</p>
        </div>
      </div>
      <div v-if="started" class="gc-header-context">
        <span>{{ brief.recipient }}</span><i />
        <span>{{ brief.occasion }}</span><i />
        <span class="mono">¥{{ format(brief.budget) }}</span>
      </div>
      <button v-if="started" class="gc-reset" type="button" @click="restart">重新描述</button>
    </header>

    <main v-if="!started" class="gc-entry">
      <section class="entry-intro">
        <p class="eyebrow">不是挑最贵的</p>
        <h2>挑一份<br /><em>对她来说有意义的</em></h2>
        <p class="entry-lead">我会先理解这次送礼的关系和场景，再把礼物组合成一份说得通的心意。</p>
        <div class="entry-rule"><span />先定关系，再定东西</div>
      </section>

      <section class="entry-form" aria-label="送礼情境">
        <div class="form-kicker">告诉我这一次</div>
        <label class="form-field">
          <span>送给谁</span>
          <select v-model="draft.recipient">
            <option v-for="item in recipientOptions" :key="item" :value="item">{{ item }}</option>
          </select>
        </label>
        <label class="form-field">
          <span>为了什么</span>
          <select v-model="draft.occasion">
            <option v-for="item in occasionOptions" :key="item" :value="item">{{ item }}</option>
          </select>
        </label>
        <div class="form-field budget-field">
          <div class="field-line"><span>预算大概</span><strong class="mono">¥{{ format(draft.budget) }}</strong></div>
          <input v-model.number="draft.budget" type="range" min="200" max="3000" step="50" aria-label="预算" />
          <div class="range-labels"><span>¥200</span><span>更看重心意</span><span>¥3,000</span></div>
        </div>
        <div class="form-field signal-field">
          <span>你更在意哪一件事</span>
          <div class="signal-list">
            <button
              v-for="signal in signals"
              :key="signal.key"
              class="signal"
              :class="{ on: draft.signals.includes(signal.key) }"
              type="button"
              @click="toggleSignal(signal.key)"
            >
              <i>{{ signal.mark }}</i>{{ signal.label }}
            </button>
          </div>
        </div>
        <button class="entry-submit" type="button" @click="begin">开始挑这份礼物 <span>→</span></button>
        <p class="entry-note">不需要一次说完，之后可以直接在方案上批注。</p>
      </section>
    </main>

    <main v-else class="gc-workspace">
      <aside class="gc-profile">
        <div class="section-label">这次要送给</div>
        <div class="profile-person">
          <div class="person-avatar">{{ brief.recipient.slice(0, 1) }}</div>
          <div><strong>{{ brief.recipient }}</strong><span>{{ brief.occasion }}</span></div>
        </div>
        <div class="profile-line" />
        <div class="section-label">我抓到的重点</div>
        <div class="signal-stack">
          <div v-for="signal in activeSignals" :key="signal.key" class="signal-row">
            <span class="signal-mark">{{ signal.mark }}</span>
            <div><strong>{{ signal.label }}</strong><small>{{ signal.detail }}</small></div>
          </div>
        </div>
        <div class="profile-line" />
        <div class="section-label">这不是商品清单</div>
        <p class="profile-copy">每一件东西都有自己的角色。少一件，整份心意可能就变了。</p>
        <button class="profile-edit" type="button" @click="restart">修改送礼情境 →</button>
      </aside>

      <section class="gc-canvas">
        <div v-if="running" class="running-line"><span class="running-dot" />顾问正在把关系翻译成礼物…</div>
        <div class="canvas-heading">
          <div>
            <p class="eyebrow">当前建议</p>
            <h2>{{ activePlan.title }}</h2>
            <p class="plan-thesis">{{ activePlan.thesis }}</p>
          </div>
          <div class="plan-total"><span>合计</span><strong class="mono">¥{{ format(activeTotal) }}</strong><small>预算内 ¥{{ format(Math.max(0, brief.budget - activeTotal)) }}</small></div>
        </div>

        <div class="plan-line"><span>这份礼物的逻辑</span><strong>{{ activePlan.logic }}</strong></div>

        <div class="object-list">
          <article
            v-for="(object, index) in activePlan.objects"
            :key="object.id"
            class="object-card"
            :class="{ selected: selectedObject === object.id, replaced: object.replaced }"
          >
            <button class="object-main" type="button" @click="selectObject(object.id)">
              <span class="object-index mono">0{{ index + 1 }}</span>
              <span class="object-symbol" :class="object.kind">{{ object.symbol }}</span>
              <span class="object-copy"><strong>{{ object.name }}</strong><small>{{ object.role }} · {{ object.price ? '¥' + format(object.price) : '随礼盒' }}</small></span>
              <span v-if="object.concern" class="concern-dot" :title="object.concern" />
              <span class="object-chevron">{{ selectedObject === object.id ? '−' : '+' }}</span>
            </button>
            <div v-if="selectedObject === object.id" class="object-detail">
              <div class="detail-reason"><span>为什么是它</span><p>{{ object.reason }}</p></div>
              <div v-if="object.concern" class="detail-concern"><span>需要你知道</span><p>{{ object.concern }}</p></div>
              <div class="replace-row">
                <span>不喜欢这一件？</span>
                <button v-for="alternative in object.alternatives" :key="alternative.id" type="button" @click="replaceObject(object, alternative)">{{ alternative.name }} <small class="mono">¥{{ format(alternative.price) }}</small></button>
              </div>
            </div>
          </article>
        </div>

        <div class="plan-footer">
          <span class="footer-mark">◎</span>
          <p>{{ activePlan.closing }}</p>
        </div>
      </section>

      <aside class="gc-advisor">
        <div class="advisor-top"><div class="section-label">顾问判断</div><span class="advisor-state"><i />{{ running ? '推演中' : '已整理' }}</span></div>
        <div class="advisor-process">
          <div v-for="(item, index) in process" :key="item.name" class="process-row" :class="{ current: running && index === 2, done: !running && index < 3 }">
            <span class="process-dot">{{ !running && index < 3 ? '✓' : index + 1 }}</span>
            <div><strong>{{ item.name }}</strong><small>{{ item.detail }}</small></div>
          </div>
        </div>
        <div class="advisor-divider" />
        <div class="section-label">依据</div>
        <div class="evidence-list">
          <div v-for="item in evidence" :key="item.label" class="evidence-row"><span>{{ item.label }}</span><p>{{ item.text }}</p></div>
        </div>
        <div class="advisor-divider" />
        <div class="section-label">如果你不想走这条路</div>
        <button v-for="plan in otherPlans" :key="plan.id" class="other-plan" type="button" @click="choosePlan(plan)">
          <span><strong>{{ plan.title }}</strong><small>{{ plan.short }}</small></span><b class="mono">¥{{ format(plan.total) }}</b>
        </button>
      </aside>
    </main>

    <footer v-if="started" class="gc-footer">
      <div class="footer-budget"><span>当前合计</span><strong class="mono">¥{{ format(activeTotal) }}</strong><small>· 余 ¥{{ format(Math.max(0, brief.budget - activeTotal)) }}</small></div>
      <form class="annotation" @submit.prevent="submitAnnotation"><span>补一句要求</span><input v-model="annotation" placeholder="比如：不要点火，换成更日常的东西" /><button type="submit">应用</button></form>
      <button class="confirm-btn" type="button" @click="openReceipt">确认这份心意 <span>→</span></button>
    </footer>

    <div v-if="receiptOpen" class="receipt-layer" @click.self="receiptOpen = false">
      <section class="receipt-sheet">
        <div class="sheet-head"><div><p class="eyebrow">可以交给你了</p><h2>给{{ brief.recipient }}的{{ brief.occasion }}</h2></div><button type="button" aria-label="关闭" @click="receiptOpen = false">×</button></div>
        <p class="sheet-thesis">{{ activePlan.thesis }}</p>
        <div class="sheet-list"><div v-for="object in activePlan.objects" :key="object.id"><span>{{ object.name }}</span><span class="mono">{{ object.price ? '¥' + format(object.price) : '随礼盒' }}</span></div></div>
        <div class="sheet-total"><span>合计</span><strong class="mono">¥{{ format(activeTotal) }}</strong></div>
        <p class="sheet-note">这份清单会保留到送礼记录里。下次再给{{ brief.recipient }}挑礼物，可以接着这次的偏好继续。</p>
        <div class="sheet-actions"><button type="button" @click="copyReceipt">复制清单</button><button class="sheet-primary" type="button" @click="receiptOpen = false">先收好</button></div>
      </section>
    </div>

    <Transition name="toast"><p v-if="toast" class="gc-toast">{{ toast }}</p></Transition>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'

const recipientOptions = ['妈妈', '爸爸', '伴侣', '朋友', '同事', '长辈']
const occasionOptions = ['生日', '纪念日', '节日', '道谢', '探望', '没有特别理由']
const signals = [
  { key: 'useful', mark: '用', label: '真的用得上', detail: '少一点闲置，多一点日常陪伴' },
  { key: 'thoughtful', mark: '心', label: '看得出花了心思', detail: '不是随手买的三样东西' },
  { key: 'experience', mark: '时', label: '留下一个记忆', detail: '让这次见面本身成为礼物' }
]
const draft = reactive({ recipient: '妈妈', occasion: '生日', budget: 800, signals: ['useful', 'thoughtful'] })
const brief = reactive({ recipient: '', occasion: '', budget: 0, signals: [] })
const started = ref(false)
const running = ref(false)
const selectedObject = ref('')
const activePlanId = ref('p-useful')
const annotation = ref('')
const toast = ref('')
const receiptOpen = ref(false)

const plans = [
  {
    id: 'p-useful', title: '让她每天都用得上', short: '日常照顾 · 不容易闲置', total: 674,
    thesis: '不把礼物做得太用力。三件东西围绕睡前半小时，让她每天都能碰到你的心意。',
    logic: '睡前半小时 → 放松 → 留下一句话',
    closing: '这不是把三件好东西放在一起，而是替她安排了一段更舒服的晚上。',
    objects: [
      { id: 'o-candle', kind: 'candle', symbol: '○', role: '睡前氛围', name: '雪松佛手柑香薰蜡烛', price: 358, reason: '她喜欢木质香调，雪松比甜香更克制；放在床头，不点也有轻微气味。', concern: '档案里有“香水过敏”，蜡烛不等于香水，但建议你考虑无火版本。', alternatives: [{ id: 'a-candle', name: '无火香薰藤条', price: 398 }] },
      { id: 'o-tea', kind: 'cup', symbol: '□', role: '每天可用', name: '洋甘菊薰衣草安睡茶', price: 198, reason: '无咖啡因，和“睡前半小时”这个时间窗一致；它不是摆设，是每天都能用的一小步。', alternatives: [{ id: 'a-tea', name: '陶瓷带盖马克杯', price: 198 }] },
      { id: 'o-card', kind: 'card', symbol: '▤', role: '解释这份礼', name: '手写寄语卡 + 定制礼盒', price: 118, reason: '卡片不是装饰，它告诉她为什么是这三件东西，把礼物从清单变成一段话。', alternatives: [] }
    ]
  },
  {
    id: 'p-hand', title: '让她感觉被认真对待', short: '手作温度 · 不像批量下单', total: 614,
    thesis: '如果她什么都不缺，那就不要再堆功能。挑有手作痕迹的东西，让她看得出你花了时间。',
    logic: '手作痕迹 → 拆盒瞬间 → 留下触感',
    closing: '这份礼物的重点不是“有用”，而是让她知道你没有敷衍。',
    objects: [
      { id: 'o-soap', kind: 'soap', symbol: '▰', role: '有手作痕迹', name: '冷制橄榄手工皂', price: 228, reason: '每块纹理都不同，既有手工感，又不会因为太特别而放进柜子。', concern: '属于消耗品，用完了这份礼物就结束；如果你想让它留得久一点，可以换护手霜。', alternatives: [{ id: 'a-soap', name: '乳木果护手霜', price: 248 }] },
      { id: 'o-felt', kind: 'pendant', symbol: '◇', role: '带出门', name: '羊毛毡小挂件', price: 268, reason: '它会跟着她出门，不是只在拆盒当天被看见。', alternatives: [{ id: 'a-felt', name: '手作陶瓷摆件', price: 298 }] },
      { id: 'o-card2', kind: 'card', symbol: '▤', role: '打开瞬间', name: '手写寄语卡 + 干花', price: 118, reason: '拆盒时先看到卡片和干花，第一秒就知道这不是临时买来的。', alternatives: [] }
    ]
  },
  {
    id: 'p-experience', title: '把见面本身变成礼物', short: '共同经历 · 适合什么都不缺', total: 760,
    thesis: '如果她不缺东西，那就送一段你们一起完成的时间。礼物不是物件，而是你提前安排好的一天。',
    logic: '提前安排 → 一起完成 → 留下一件东西',
    closing: '这份礼物不靠包装成立，靠你愿意把时间留出来。',
    objects: [
      { id: 'o-class', kind: 'ticket', symbol: '▱', role: '共同经历', name: '陶艺体验双人课', price: 560, reason: '两小时、成品可带走；体验结束后还能留下一件看得见的东西。', concern: '需要提前一周预约，也要确认她当天有空。', alternatives: [{ id: 'a-class', name: '双人料理课', price: 680 }] },
      { id: 'o-photo', kind: 'card', symbol: '▤', role: '留下记录', name: '拍立得 + 小相册', price: 200, reason: '当天就能把照片贴进去，比手机相册更像一份真的礼物。', alternatives: [{ id: 'a-photo', name: '定制相框', price: 168 }] },
      { id: 'o-card3', kind: 'card', symbol: '▤', role: '先告诉她', name: '手写邀请卡', price: 0, reason: '先把当天要做什么写清楚，让她收到的是期待，不是一张临时通知。', alternatives: [] }
    ]
  }
]

const process = [
  { name: '看关系', detail: '读收礼人的已知偏好' },
  { name: '定主题', detail: '把场合翻译成一条心意' },
  { name: '挑构成', detail: '让每件东西承担一个角色' },
  { name: '留余地', detail: '把风险和替换说清楚' }
]
const evidence = [
  { label: '档案事实', text: '上次送的礼，回访标记为“常用”。' },
  { label: '明确信号', text: '她偏好实用，不喜欢太花哨的东西。' },
  { label: '本次推断', text: '生日礼物需要一点仪式感，但不能牺牲日常使用。' }
]

const activePlan = computed(() => plans.find((plan) => plan.id === activePlanId.value) || plans[0])
const activeTotal = computed(() => activePlan.value.objects.reduce((sum, item) => sum + (Number(item.price) || 0), 0))
const otherPlans = computed(() => plans.filter((plan) => plan.id !== activePlanId.value))
const activeSignals = computed(() => brief.signals.map((key) => signals.find((signal) => signal.key === key)).filter(Boolean))

const format = (number) => Number(number || 0).toLocaleString('en-US')
const toggleSignal = (key) => {
  const index = draft.signals.indexOf(key)
  if (index >= 0) draft.signals.splice(index, 1)
  else draft.signals.push(key)
}
const begin = () => {
  brief.recipient = draft.recipient
  brief.occasion = draft.occasion
  brief.budget = draft.budget
  brief.signals = [...draft.signals]
  started.value = true
  running.value = true
  selectedObject.value = ''
  window.setTimeout(() => { running.value = false }, 900)
}
const selectObject = (id) => { selectedObject.value = selectedObject.value === id ? '' : id }
const choosePlan = (plan) => {
  activePlanId.value = plan.id
  selectedObject.value = ''
  say(`已切换为“${plan.title}”`)
}
const replaceObject = (object, alternative) => {
  object.name = alternative.name
  object.price = alternative.price
  object.replaced = true
  object.reason = alternative.reason || `换成${alternative.name}后，整体仍保持“${activePlan.value.logic}”这条逻辑。`
  object.concern = ''
  selectedObject.value = object.id
  say(`已把“${alternative.name}”放进方案`)
}
const submitAnnotation = () => {
  const value = annotation.value.trim()
  if (!value) return
  say(`已记下：“${value}”——你可以继续挑，或直接确认`)
  annotation.value = ''
}
const openReceipt = () => { receiptOpen.value = true }
const copyReceipt = async () => {
  const text = [`给${brief.recipient}的${brief.occasion} · ${activePlan.value.title}`, ...activePlan.value.objects.map((item) => `· ${item.name}${item.price ? `（¥${item.price}）` : ''}`), `合计 ¥${activeTotal.value}`].join('\n')
  try { await navigator.clipboard?.writeText(text) } catch { /* 线上非安全上下文时只给反馈 */ }
  say('清单已复制')
}
const restart = () => {
  started.value = false
  running.value = false
  selectedObject.value = ''
  receiptOpen.value = false
}
let toastTimer = 0
const say = (text) => {
  toast.value = text
  window.clearTimeout(toastTimer)
  toastTimer = window.setTimeout(() => { toast.value = '' }, 2600)
}
</script>

<style lang="less" scoped>
.gift-concierge {
  --gc-accent: var(--second-600);
  --gc-accent-soft: var(--second-50);
  --gc-accent-line: var(--second-200);
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--bg-base);
  color: var(--text);
}
.mono { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
.gc-header {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 28px 14px;
  border-bottom: 1px solid var(--border);
}
.gc-brand { display: flex; align-items: center; gap: 10px; }
.gc-mark {
  width: 30px; height: 30px; display: flex; align-items: center; justify-content: center;
  border: 1px solid var(--gc-accent-line); color: var(--gc-accent); border-radius: 8px; font-size: 0.82rem;
}
.gc-brand h1 { margin: 0; font-family: var(--font-display); font-size: 0.94rem; font-weight: 600; color: var(--text-strong); }
.gc-brand p { margin: 2px 0 0; font-size: 0.7rem; color: var(--text-faint); }
.gc-header-context { margin-left: auto; display: flex; align-items: center; gap: 9px; font-size: 0.74rem; color: var(--text-muted); }
.gc-header-context i { width: 3px; height: 3px; border-radius: 50%; background: var(--border-strong); }
.gc-reset, .profile-edit {
  border: 1px solid var(--border); background: transparent; color: var(--text-muted); border-radius: var(--radius-sm); padding: 6px 11px; font-size: 0.72rem; cursor: pointer;
}
.gc-reset:hover, .profile-edit:hover { color: var(--text); border-color: var(--border-strong); }

.eyebrow, .section-label { margin: 0; font-size: 0.68rem; letter-spacing: 0.08em; color: var(--text-faint); }
.gc-entry { flex: 1 1 auto; min-height: 0; display: grid; grid-template-columns: minmax(0, 0.9fr) minmax(390px, 0.72fr); align-items: center; gap: 10%; max-width: 1060px; width: 100%; margin: 0 auto; padding: 34px 44px 54px; overflow-y: auto; }
.entry-intro h2 { margin: 12px 0 18px; font-family: var(--font-display); font-size: clamp(2rem, 4vw, 3.5rem); line-height: 1.14; font-weight: 600; letter-spacing: -0.045em; color: var(--text-strong); }
.entry-intro h2 em { color: var(--gc-accent); font-style: normal; }
.entry-lead { max-width: 350px; margin: 0; font-size: 0.9rem; line-height: 1.8; color: var(--text-muted); }
.entry-rule { display: flex; align-items: center; gap: 10px; margin-top: 44px; font-size: 0.72rem; color: var(--text-faint); }
.entry-rule span { width: 30px; height: 1px; background: var(--gc-accent); }
.entry-form { border-top: 1px solid var(--border-strong); padding-top: 16px; }
.form-kicker { font-size: 0.78rem; font-weight: 600; color: var(--text-strong); margin-bottom: 18px; }
.form-field { display: block; padding: 14px 0; border-bottom: 1px solid var(--border); }
.form-field > span, .field-line > span { display: block; margin-bottom: 8px; font-size: 0.72rem; color: var(--text-muted); }
.form-field select { width: 100%; appearance: none; border: 0; outline: 0; padding: 0; background: transparent; color: var(--text-strong); font: 500 1rem var(--font-body); cursor: pointer; }
.field-line { display: flex; justify-content: space-between; align-items: baseline; }
.field-line > span { margin: 0; }
.field-line strong { color: var(--gc-accent); font-size: 0.92rem; }
.budget-field input[type="range"] { width: 100%; accent-color: var(--gc-accent); cursor: pointer; }
.range-labels { display: flex; justify-content: space-between; font: 0.66rem var(--font-mono); color: var(--text-faint); margin-top: 3px; }
.range-labels span:nth-child(2) { font-family: var(--font-body); }
.signal-list { display: flex; flex-wrap: wrap; gap: 7px; }
.signal { border: 1px solid var(--border); background: transparent; border-radius: var(--radius-sm); padding: 7px 10px; color: var(--text-muted); font-size: 0.72rem; cursor: pointer; }
.signal i { font-style: normal; margin-right: 5px; color: var(--text-faint); }
.signal.on { border-color: var(--gc-accent); color: var(--gc-accent); background: var(--gc-accent-soft); }
.signal.on i { color: var(--gc-accent); }
.entry-submit { width: 100%; margin-top: 24px; padding: 11px 15px; border: 1px solid var(--gc-accent); border-radius: var(--radius-sm); background: var(--gc-accent); color: var(--bg-surface); font-size: 0.82rem; cursor: pointer; }
.entry-submit span { margin-left: 8px; }
.entry-submit:hover { opacity: 0.88; }
.entry-note { margin: 10px 0 0; text-align: center; font-size: 0.68rem; color: var(--text-faint); }

.gc-workspace { flex: 1 1 auto; min-height: 0; display: grid; grid-template-columns: 190px minmax(0, 1fr) 290px; overflow: hidden; }
.gc-profile, .gc-advisor { min-height: 0; overflow-y: auto; padding: 24px 20px; }
.gc-profile { border-right: 1px solid var(--border); }
.gc-advisor { border-left: 1px solid var(--border); background: var(--bg-surface); }
.profile-person { display: flex; align-items: center; gap: 9px; margin-top: 13px; }
.person-avatar { width: 34px; height: 34px; display: flex; align-items: center; justify-content: center; border-radius: 50%; background: var(--gc-accent-soft); color: var(--gc-accent); font-size: 0.84rem; }
.profile-person strong, .profile-person span { display: block; }
.profile-person strong { font-size: 0.9rem; color: var(--text-strong); }
.profile-person span { margin-top: 3px; font-size: 0.7rem; color: var(--text-faint); }
.profile-line, .advisor-divider { height: 1px; background: var(--border); margin: 22px 0; }
.signal-stack { margin-top: 13px; display: flex; flex-direction: column; gap: 13px; }
.signal-row { display: flex; align-items: flex-start; gap: 8px; }
.signal-mark { color: var(--gc-accent); font-size: 0.7rem; min-width: 18px; }
.signal-row strong, .signal-row small { display: block; }
.signal-row strong { font-size: 0.75rem; color: var(--text); font-weight: 500; }
.signal-row small { margin-top: 3px; font-size: 0.66rem; line-height: 1.45; color: var(--text-faint); }
.profile-copy { font-size: 0.72rem; line-height: 1.65; color: var(--text-muted); margin: 11px 0 16px; }
.profile-edit { padding: 0; border: 0; color: var(--gc-accent); }
.profile-edit:hover { border: 0; }

.gc-canvas { min-width: 0; min-height: 0; overflow-y: auto; padding: 28px clamp(28px, 4vw, 64px) 34px; }
.running-line { display: flex; align-items: center; gap: 7px; margin-bottom: 14px; font-size: 0.7rem; color: var(--gc-accent); }
.running-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--gc-accent); animation: pulse 1.1s ease-in-out infinite; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: .3; } }
.canvas-heading { display: flex; justify-content: space-between; align-items: flex-end; gap: 16px; padding-bottom: 18px; border-bottom: 1px solid var(--border-strong); }
.canvas-heading h2 { margin: 9px 0 8px; font-family: var(--font-display); font-size: clamp(1.4rem, 2.2vw, 2rem); line-height: 1.2; font-weight: 600; letter-spacing: -0.035em; color: var(--text-strong); }
.plan-thesis { max-width: 580px; margin: 0; font-size: 0.8rem; line-height: 1.7; color: var(--text-muted); }
.plan-total { flex: 0 0 auto; text-align: right; }
.plan-total span, .plan-total small { display: block; color: var(--text-faint); font-size: 0.68rem; }
.plan-total strong { display: block; margin: 4px 0 3px; font-size: 1.45rem; color: var(--text-strong); }
.plan-total small { color: var(--gc-accent); }
.plan-line { display: flex; align-items: baseline; gap: 13px; padding: 14px 0; border-bottom: 1px solid var(--border); font-size: 0.72rem; }
.plan-line span { color: var(--text-faint); }
.plan-line strong { color: var(--text-muted); font-weight: 400; }
.object-list { margin-top: 8px; }
.object-card { border-bottom: 1px solid var(--border); }
.object-card.selected { border-bottom-color: var(--gc-accent-line); }
.object-main { width: 100%; display: grid; grid-template-columns: 28px 40px minmax(0, 1fr) 10px 16px; align-items: center; gap: 12px; padding: 16px 2px; border: 0; background: transparent; text-align: left; color: inherit; cursor: pointer; }
.object-index { font-size: 0.68rem; color: var(--text-faint); }
.object-symbol { width: 38px; height: 38px; display: flex; align-items: center; justify-content: center; border: 1px solid var(--gc-accent-line); border-radius: 10px; color: var(--gc-accent); font-size: 1rem; }
.object-symbol.cup { border-color: var(--border-strong); color: var(--text-muted); }
.object-symbol.card { border-color: var(--border-strong); color: var(--text-muted); }
.object-copy strong, .object-copy small { display: block; }
.object-copy strong { font-size: 0.84rem; font-weight: 500; color: var(--text-strong); }
.object-copy small { margin-top: 4px; font-size: 0.7rem; color: var(--text-faint); }
.concern-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--warn); }
.object-chevron { color: var(--text-faint); font-size: 1.05rem; }
.object-card.selected .object-chevron { color: var(--gc-accent); }
.object-detail { padding: 0 2px 16px 92px; }
.detail-reason span, .detail-concern span { font-size: 0.66rem; color: var(--text-faint); }
.detail-reason p, .detail-concern p { margin: 4px 0 0; font-size: 0.75rem; line-height: 1.7; color: var(--text-muted); }
.detail-concern { margin-top: 12px; }
.detail-concern span { color: var(--warn); }
.replace-row { display: flex; flex-wrap: wrap; align-items: center; gap: 7px; margin-top: 13px; font-size: 0.68rem; color: var(--text-faint); }
.replace-row button { border: 1px solid var(--border); background: transparent; border-radius: var(--radius-sm); padding: 6px 8px; color: var(--text); font-size: 0.69rem; cursor: pointer; }
.replace-row button:hover { border-color: var(--gc-accent); color: var(--gc-accent); }
.replace-row small { margin-left: 4px; color: var(--text-faint); }
.plan-footer { display: flex; align-items: flex-start; gap: 9px; margin-top: 24px; padding-top: 15px; border-top: 1px solid var(--border); }
.footer-mark { color: var(--gc-accent); font-size: 0.9rem; }
.plan-footer p { margin: 0; font-size: 0.74rem; line-height: 1.6; color: var(--text-muted); }

.advisor-top { display: flex; align-items: center; justify-content: space-between; }
.advisor-state { display: flex; align-items: center; gap: 5px; color: var(--text-faint); font-size: 0.66rem; }
.advisor-state i { width: 5px; height: 5px; border-radius: 50%; background: var(--pos); }
.advisor-process { margin-top: 16px; display: flex; flex-direction: column; gap: 13px; }
.process-row { display: grid; grid-template-columns: 20px minmax(0, 1fr); gap: 8px; opacity: .58; }
.process-row.done, .process-row.current { opacity: 1; }
.process-dot { width: 18px; height: 18px; display: flex; align-items: center; justify-content: center; border: 1px solid var(--border-strong); border-radius: 50%; font: 0.62rem var(--font-mono); color: var(--text-faint); }
.process-row.done .process-dot { border-color: var(--pos); color: var(--pos); }
.process-row.current .process-dot { border-color: var(--gc-accent); color: var(--gc-accent); }
.process-row strong, .process-row small { display: block; }
.process-row strong { font-size: 0.74rem; font-weight: 500; color: var(--text); }
.process-row small { margin-top: 3px; font-size: 0.66rem; line-height: 1.45; color: var(--text-faint); }
.evidence-list { margin-top: 13px; display: flex; flex-direction: column; gap: 13px; }
.evidence-row span { display: block; font-size: 0.64rem; color: var(--gc-accent); }
.evidence-row p { margin: 4px 0 0; font-size: 0.72rem; line-height: 1.6; color: var(--text-muted); }
.other-plan { width: 100%; display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 11px 0; border: 0; border-bottom: 1px solid var(--border); background: transparent; text-align: left; cursor: pointer; }
.other-plan:hover strong { color: var(--gc-accent); }
.other-plan strong, .other-plan small { display: block; }
.other-plan strong { font-size: 0.76rem; font-weight: 500; color: var(--text); }
.other-plan small { margin-top: 3px; font-size: 0.66rem; color: var(--text-faint); }
.other-plan b { font-size: 0.7rem; font-weight: 400; color: var(--text-muted); }

.gc-footer { flex: 0 0 auto; display: grid; grid-template-columns: auto minmax(280px, 1fr) auto; align-items: center; gap: 16px; padding: 12px 24px 14px; border-top: 1px solid var(--border); background: var(--bg-base); }
.footer-budget { display: flex; align-items: baseline; gap: 7px; white-space: nowrap; }
.footer-budget span { font-size: 0.7rem; color: var(--text-faint); }
.footer-budget strong { font-size: 1rem; color: var(--text-strong); }
.footer-budget small { font-size: 0.68rem; color: var(--gc-accent); }
.annotation { display: flex; align-items: center; gap: 9px; min-width: 0; }
.annotation > span { flex: 0 0 auto; font-size: 0.68rem; color: var(--text-faint); }
.annotation input { min-width: 0; flex: 1; padding: 8px 11px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--bg-surface); outline: none; color: var(--text); font: 0.76rem var(--font-body); }
.annotation input:focus { border-color: var(--gc-accent); }
.annotation input::placeholder { color: var(--text-faint); }
.annotation button { flex: 0 0 auto; padding: 7px 11px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: transparent; color: var(--text-muted); font-size: 0.7rem; cursor: pointer; }
.annotation button:hover { border-color: var(--gc-accent); color: var(--gc-accent); }
.confirm-btn { padding: 9px 15px; border: 1px solid var(--gc-accent); border-radius: var(--radius-sm); background: var(--gc-accent); color: var(--bg-surface); font-size: 0.76rem; cursor: pointer; white-space: nowrap; }
.confirm-btn span { margin-left: 7px; }
.confirm-btn:hover { opacity: .88; }

.receipt-layer { position: absolute; inset: 0; z-index: 20; display: flex; justify-content: flex-end; background: var(--bg-overlay); }
.receipt-sheet { width: min(470px, 100%); height: 100%; overflow-y: auto; padding: 28px 28px 24px; background: var(--bg-surface); border-left: 1px solid var(--border-strong); }
.sheet-head { display: flex; justify-content: space-between; gap: 20px; padding-bottom: 18px; border-bottom: 1px solid var(--border); }
.sheet-head h2 { margin: 9px 0 0; font-family: var(--font-display); font-size: 1.45rem; color: var(--text-strong); }
.sheet-head button { width: 28px; height: 28px; border: 1px solid var(--border); border-radius: 50%; background: transparent; color: var(--text-muted); font-size: 1.2rem; line-height: 1; cursor: pointer; }
.sheet-thesis { margin: 18px 0; font-size: 0.82rem; line-height: 1.8; color: var(--text-muted); }
.sheet-list { border-top: 1px solid var(--border); }
.sheet-list div { display: flex; justify-content: space-between; gap: 12px; padding: 13px 0; border-bottom: 1px solid var(--border); font-size: 0.8rem; color: var(--text); }
.sheet-list span:last-child { color: var(--text-muted); }
.sheet-total { display: flex; justify-content: space-between; align-items: baseline; padding: 18px 0; border-bottom: 1px solid var(--border); color: var(--text-muted); font-size: 0.8rem; }
.sheet-total strong { font-size: 1.25rem; color: var(--text-strong); }
.sheet-note { margin: 18px 0; font-size: 0.72rem; line-height: 1.7; color: var(--text-faint); }
.sheet-actions { display: flex; gap: 8px; }
.sheet-actions button { flex: 1; padding: 9px; border: 1px solid var(--border-strong); border-radius: var(--radius-sm); background: transparent; color: var(--text); font-size: 0.76rem; cursor: pointer; }
.sheet-actions .sheet-primary { border-color: var(--gc-accent); background: var(--gc-accent); color: var(--bg-surface); }
.gc-toast { position: absolute; left: 50%; bottom: 78px; transform: translateX(-50%); z-index: 30; margin: 0; padding: 9px 15px; border: 1px solid var(--border-strong); background: var(--bg-surface); color: var(--text); font-size: 0.72rem; border-radius: 999px; white-space: nowrap; }
.toast-enter-active, .toast-leave-active { transition: opacity .16s ease-out, transform .16s ease-out; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translate(-50%, 5px); }

@media (max-width: 1080px) {
  .gc-workspace { grid-template-columns: 170px minmax(0, 1fr) 250px; }
  .gc-canvas { padding-inline: 28px; }
  .gc-footer { grid-template-columns: 1fr auto; }
  .annotation { grid-column: 1 / -1; grid-row: 1; }
  .footer-budget { grid-column: 1; grid-row: 2; }
  .confirm-btn { grid-column: 2; grid-row: 2; }
}
@media (max-width: 820px) {
  .gc-header { padding-inline: 18px; }
  .gc-entry { grid-template-columns: 1fr; gap: 28px; padding: 28px 24px 46px; max-width: 560px; }
  .entry-intro h2 { font-size: 2.3rem; }
  .entry-rule { margin-top: 24px; }
  .gc-workspace { grid-template-columns: 1fr; overflow-y: auto; }
  .gc-profile, .gc-advisor { border: 0; padding: 18px 22px; }
  .gc-profile { border-bottom: 1px solid var(--border); }
  .gc-advisor { border-top: 1px solid var(--border); }
  .gc-canvas { overflow: visible; padding: 24px 22px 30px; }
  .signal-stack { flex-direction: row; flex-wrap: wrap; }
  .signal-row { flex: 1 1 140px; }
  .profile-line { margin: 16px 0; }
  .gc-footer { position: relative; grid-template-columns: 1fr auto; padding-inline: 18px; }
}
@media (max-width: 560px) {
  .gc-header-context { display: none; }
  .gc-entry { padding-inline: 18px; }
  .canvas-heading { display: block; }
  .plan-total { text-align: left; margin-top: 14px; }
  .plan-total span, .plan-total small { display: inline; margin-right: 8px; }
  .plan-total strong { display: inline; }
  .object-main { grid-template-columns: 23px 36px minmax(0, 1fr) 8px 14px; gap: 8px; }
  .object-detail { padding-left: 68px; }
  .gc-footer { display: flex; flex-wrap: wrap; }
  .annotation { order: 3; flex-basis: 100%; }
  .footer-budget { flex: 1; }
}
</style>
