<template>
  <section class="gblock" ref="rootEl">
    <div class="g-step">
      <span class="g-step__no">③</span>
      <span class="g-step__t">这一盒里有什么</span>
      <span class="g-step__s">点物件旁的图标，就地跟我说要改什么</span>
    </div>

    <article class="gcard gcard--warm cb">
      <!-- 展开后的主视觉：氛围构成放大，替代「主图」 -->
      <div class="cb__hero">
        <MoodSwatch
          :palette="concept.palette"
          :seed="concept.id + '-hero'"
          variant="hero"
          :width="720"
          :height="150"
          :label="`${concept.title} 的氛围构成`"
        />
        <div class="cb__heroinfo">
          <h2 class="cb__title">{{ concept.title }}</h2>
          <p class="cb__thesis">{{ concept.thesis }}</p>
          <div class="cb__herofoot">
            <span class="cb__total mono">¥{{ currentTotal }}</span>
            <span class="cb__note">{{ concept.budgetNote }}</span>
          </div>
        </div>
      </div>

      <!-- 构成元素 -->
      <ul class="cb__els">
        <li
          v-for="(el, i) in elements"
          :key="el.id"
          class="el"
          :class="{ 'el--done': el.status === 'replaced' }"
          :data-el="el.id"
        >
          <span class="el__thumb">
            <MoodSwatch
              :palette="concept.palette"
              :seed="el.id + (el.status === 'replaced' ? '-new' : '')"
              variant="thumb"
              :width="92"
              :height="92"
              :label="`${el.name} 的示意`"
            />
          </span>

          <div class="el__body">
            <div class="el__head">
              <span class="el__no mono">{{ ['①', '②', '③', '④'][i] || i + 1 }}</span>

              <Transition name="gswap" mode="out-in">
                <span :key="el.name" class="el__name">{{ el.name }}</span>
              </Transition>

              <span v-if="el.status === 'replaced'" class="el__chip">已替换</span>
              <span class="el__price mono">{{ el.price ? '¥' + el.price : '含' }}</span>

              <!-- 气泡入口：只有可替换的物件才有 -->
              <button
                v-if="!el.fixed"
                class="el__bub"
                :class="{ on: openId === el.id }"
                type="button"
                :aria-label="`对「${el.role}」提出修改`"
                @click="toggleBubble(el)"
              >💬</button>
            </div>

            <p class="el__note">{{ el.note }}</p>

            <!-- 改动理由留痕：会一路带到贺卡寄语里 -->
            <p v-if="el.reason" class="gwhy"><i>↳</i>{{ el.reason }}</p>

            <!-- 匿名气泡：只在这一件旁边出现，不占整页输入框 -->
            <div v-if="openId === el.id" class="gbubble">
              <textarea
                v-model="draft"
                class="gbubble__in"
                rows="2"
                :placeholder="`关于「${el.role}」，比如：我不确定她喜不喜欢喝茶，能换成热饮吗？`"
                @keydown.enter.exact.prevent="sendAsk(el)"
              />
              <div class="gbubble__acts">
                <button class="gbtn" type="button" @click="closeBubble">取消</button>
                <button class="gbtn gbtn--ghost" type="button" :disabled="!draft.trim()" @click="sendAsk(el)">
                  发送
                </button>
              </div>
            </div>

            <!-- agent 回应 + 同类目内的替换候选 -->
            <div v-if="el.reply" class="rep">
              <p class="rep__t">{{ el.reply }}</p>
              <div class="rep__opts">
                <button
                  v-for="o in el.options"
                  :key="o.id"
                  class="opt"
                  type="button"
                  @click="applyReplace(el, o)"
                >
                  <span class="opt__n">{{ o.name }}</span>
                  <span class="opt__d">{{ o.note }}</span>
                  <span class="opt__p mono">{{ o.price ? '¥' + o.price : '含' }}</span>
                </button>
              </div>
            </div>
          </div>
        </li>
      </ul>

      <div class="cb__acts">
        <button class="gbtn gbtn--warm" type="button" @click="$emit('next', elements)">
          就这样，去定制包装
        </button>
        <span class="cb__hint">还没定？继续点物件上的气泡改</span>
      </div>
    </article>
  </section>
</template>

<script setup>
/**
 * 阶段 3 · 就地展开 + 局部微调
 *
 * 两件事是这一块存在的理由：
 *   1. 卡片在原地展开成主视觉 —— 不跳页、不弹窗，上面两张卡还在，用户可以随时改主意
 *   2. 对话附着在物件上 —— 没有常驻输入框，只有点中某件时才冒出的气泡
 *
 * 替换只允许同类目内（走 el.replaceOptions），不做自由替换：
 * 自由替换会让「晚安治愈集」这个概念散掉，概念一散整个提案逻辑就失效了。
 *
 * 滚动锚定是必须的：替换后卡片高度会变，下方内容会被顶走。
 * 见 pinElement() —— 它把被改的那一件在视口里的位置钉住，用户不会"被推着走"。
 */
import { ref, computed, nextTick, watch } from 'vue'
import MoodSwatch from '@/components/gift/MoodSwatch.vue'

const props = defineProps({
  concept: { type: Object, required: true }
})

const emit = defineEmits(['next', 'revised'])

const rootEl = ref(null)
const openId = ref('')
const draft = ref('')

/** 本地副本：就地打补丁，不改 props */
const elements = ref(JSON.parse(JSON.stringify(props.concept.elements || [])))

watch(
  () => props.concept?.id,
  () => {
    elements.value = JSON.parse(JSON.stringify(props.concept.elements || []))
    openId.value = ''
    draft.value = ''
  }
)

const currentTotal = computed(() =>
  elements.value.reduce((s, e) => s + (Number(e.price) || 0), 0)
)

const toggleBubble = (el) => {
  if (openId.value === el.id) return closeBubble()
  openId.value = el.id
  draft.value = ''
  el.reply = ''
  el.options = []
}

const closeBubble = () => {
  openId.value = ''
  draft.value = ''
}

/** 找到最近的可滚动祖先，用于滚动锚定 */
const findScrollParent = (el) => {
  let p = el?.parentElement
  while (p) {
    const s = getComputedStyle(p)
    if (/(auto|scroll)/.test(s.overflowY) && p.scrollHeight > p.clientHeight) return p
    p = p.parentElement
  }
  return null
}

/** 用户发出批注 → agent 给回应 + 同类目候选 */
const sendAsk = (el) => {
  const text = draft.value.trim()
  if (!text) return
  el.annotation = text
  el.reply = `明白。同类目里还有这几个方向，都能保留「${props.concept.title}」的调性：`
  el.options = el.replaceOptions || []
  draft.value = ''
  openId.value = ''
}

/** 就地替换：只改这一件，其余件与上方卡片一律不动 */
const applyReplace = async (el, option) => {
  const fromName = el.name
  const node = rootEl.value?.querySelector(`[data-el="${el.id}"]`)
  const sp = findScrollParent(rootEl.value)
  const st = sp?.scrollTop ?? 0
  const before = node?.getBoundingClientRect().top

  el.name = option.name
  el.note = option.note
  el.price = option.price
  el.status = 'replaced'
  el.reason = option.note
  el.reply = ''
  el.options = []
  el.history = [...(el.history || []), { from: fromName, to: option.name }]

  await nextTick()

  const after = node?.getBoundingClientRect().top
  if (sp && before != null && after != null) {
    // 原生 overflow-anchor 之外再补一次，保证被改的那一件停在原地
    sp.scrollTop = st + (after - before)
  }

  emit('revised', {
    elementId: el.id,
    role: el.role,
    from: fromName,
    to: option.name,
    reason: option.note,
    annotation: el.annotation || ''
  })
}
</script>

<style lang="less" scoped>
.cb { padding: 0; }

/* 主视觉 */
.cb__hero { position: relative; }
.cb__heroinfo {
  padding: 15px 20px 16px;
}
.cb__title {
  font-family: var(--font-display);
  font-size: 1.06rem;
  font-weight: 600;
  color: var(--text-strong);
  margin: 0 0 6px;
}
.cb__thesis {
  font-size: 0.79rem;
  line-height: 1.65;
  color: var(--text-muted);
  margin: 0 0 11px;
}
.cb__herofoot { display: flex; align-items: baseline; gap: 9px; }
.cb__total { font-size: 1rem; font-weight: 600; color: var(--text-strong); }
.cb__note { font-size: 0.72rem; color: var(--text-faint); }

/* 构成元素 */
.cb__els {
  list-style: none;
  margin: 0;
  padding: 0;
  border-top: 1px solid var(--border);
}
.el {
  display: flex;
  gap: 13px;
  padding: 14px 20px;
  border-bottom: 1px solid var(--border);
}
.el--done { background: var(--gift-accent-soft); }
.el__thumb {
  width: 46px;
  height: 46px;
  border-radius: 9px;
  overflow: hidden;
  flex: 0 0 auto;
  border: 1px solid var(--border);
}
.el__body { flex: 1; min-width: 0; }

.el__head {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.el__no { font-size: 0.72rem; color: var(--text-faint); flex: 0 0 auto; }
.el__name {
  font-size: 0.88rem;
  font-weight: 600;
  color: var(--text-strong);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.el__chip {
  font-size: 0.68rem;
  padding: 1px 7px;
  border-radius: 99px;
  background: var(--gift-accent);
  color: var(--bg-surface);
  flex: 0 0 auto;
}
.el__price {
  margin-left: auto;
  font-size: 0.78rem;
  color: var(--text-muted);
  flex: 0 0 auto;
}
.el__bub {
  flex: 0 0 auto;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: 1px solid var(--border-strong);
  background: transparent;
  font-size: 0.72rem;
  line-height: 1;
  cursor: pointer;
  transition: border-color 0.15s ease-out, background-color 0.15s ease-out;
}
.el__bub:hover,
.el__bub.on { border-color: var(--gift-accent); background: var(--gift-accent-soft); }

.el__note {
  font-size: 0.74rem;
  line-height: 1.6;
  color: var(--text-muted);
  margin: 5px 0 0;
}

/* agent 回应与候选 */
.rep { margin-top: 9px; }
.rep__t {
  font-size: 0.75rem;
  line-height: 1.6;
  color: var(--text);
  margin: 0 0 8px;
}
.rep__opts { display: flex; flex-direction: column; gap: 7px; }
.opt {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 2px 10px;
  text-align: left;
  font-family: var(--font-body);
  padding: 10px 12px;
  border: 1px solid var(--border-strong);
  border-radius: 9px;
  background: var(--bg-surface);
  cursor: pointer;
  transition: border-color 0.15s ease-out;
}
.opt:hover { border-color: var(--gift-accent); }
.opt__n { font-size: 0.82rem; font-weight: 500; color: var(--text-strong); }
.opt__d { grid-column: 1; font-size: 0.72rem; line-height: 1.55; color: var(--text-muted); }
.opt__p { grid-column: 2; grid-row: 1; font-size: 0.76rem; color: var(--text-muted); }

/* 底部动作 */
.cb__acts {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px 18px;
}
.cb__hint { font-size: 0.72rem; color: var(--text-faint); }
</style>
