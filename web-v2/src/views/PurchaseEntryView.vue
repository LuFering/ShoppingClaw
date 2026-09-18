<template>
  <div class="pe">
    <div class="pe-inner">
      <!-- 身份区：与欢迎页智能体最直接的区分 —— 用户一眼知道自己在跟谁说话 -->
      <header class="pe-hero">
        <span class="pe-sig">采</span>
        <h1 class="pe-name">采办 · 采购规划顾问</h1>
        <p class="pe-desc">装修、换季、搬家的组合采购 —— 我拆清单、排顺序、盯依赖</p>
      </header>

      <!-- 输入形式入口：结构化表单，让用户把需求填实而不是组织语言 -->
      <section class="pe-form">
        <div v-for="f in ENTRY_FORM" :key="f.key" class="pe-field">
          <p class="pe-label">
            {{ f.label }}<em v-if="f.required">*</em>
          </p>
          <div class="pe-chips">
            <button
              v-for="opt in f.options"
              :key="opt"
              class="pe-chip"
              :class="{ on: isPicked(f, opt) }"
              type="button"
              @click="pick(f, opt)"
            >
              {{ f.key === 'when' && opt === '指定日期' ? '▦ ' + opt : opt }}
            </button>
          </div>
        </div>

        <button class="pe-submit" type="button" @click="startFromForm">
          生成采购方案 ›
        </button>
      </section>

      <!-- 预设方案：点一张 = 自动填好场景/预算/周期，直接带参数进工作台 -->
      <section class="pe-presets">
        <div class="pe-preset-head">
          <span class="pe-preset-title">或从预设方案开始</span>
          <span class="pe-preset-hint">点击直接进入工作台</span>
        </div>
        <div class="pe-grid">
          <button
            v-for="p in PRESET_PLANS"
            :key="p.id"
            class="pe-card"
            type="button"
            @click="startFromPreset(p)"
          >
            <span class="pe-card-title">{{ p.title }}</span>
            <span class="pe-card-meta mono">{{ p.budget }} · {{ p.duration }}</span>
            <span class="pe-card-desc">{{ p.desc }}</span>
          </button>
        </div>
      </section>

      <footer class="pe-foot">
        <span>进行中的任务</span>
        <span class="mono pe-foot-n">2 个</span>
        <span class="pe-foot-tag">1 个等你确认</span>
        <button class="pe-foot-link" type="button">查看任务状态 ›</button>
      </footer>
    </div>
  </div>
</template>

<script setup>
/**
 * 采购智能体 · 对话入口页
 *
 * 入口页的职责是「收敛意图」，把模糊需求变成结构化参数，然后交给工作台执行。
 * 所以这里只有三块：身份区、结构化表单、预设方案。
 */
import { reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ENTRY_FORM, PRESET_PLANS } from '@/data/purchaseDemo'

const router = useRouter()

const picked = reactive({
  scene: '装修',
  budget: '¥6万',
  when: '下月开工',
  constraints: ['有老人', '要静音']
})

const isPicked = (field, opt) => {
  const v = picked[field.key]
  return Array.isArray(v) ? v.includes(opt) : v === opt
}

const pick = (field, opt) => {
  if (field.type === 'multi') {
    const list = picked[field.key]
    const i = list.indexOf(opt)
    if (i >= 0) list.splice(i, 1)
    else list.push(opt)
  } else {
    picked[field.key] = opt
  }
}

const goWorkbench = (params) => {
  router.push({
    path: '/planning/run',
    query: {
      scene: params.scene || '',
      budget: String(params.budget || ''),
      duration: params.duration || '',
      source: params.source || 'form'
    }
  })
}

const startFromForm = () => {
  goWorkbench({
    scene: picked.scene,
    budget: picked.budget,
    duration: picked.when,
    source: 'form'
  })
}

const startFromPreset = (preset) => {
  goWorkbench({
    ...preset.params,
    source: 'preset',
    preset: preset.id
  })
}
</script>

<style lang="less" scoped>
.pe {
  width: 100%;
  min-height: 100%;
  display: flex;
  justify-content: center;
  padding: 36px 24px 64px;
  background: var(--bg-base);
}
.pe-inner {
  width: 100%;
  max-width: 680px;
}

/* 身份区 */
.pe-hero {
  text-align: center;
  padding-bottom: 26px;
}
.pe-sig {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  border-radius: 11px;
  background: var(--accent-50);
  color: var(--accent-700);
  font-size: 1rem;
  font-weight: 600;
  margin-bottom: 12px;
}
.pe-name {
  margin: 0;
  font-family: var(--font-display);
  font-size: 1.2rem;
  font-weight: 600;
  color: var(--text-strong);
}
.pe-desc {
  margin: 7px 0 0;
  font-size: 0.82rem;
  line-height: 1.6;
  color: var(--text-muted);
}

/* 表单 */
.pe-form {
  border: 1px solid var(--border-strong);
  border-radius: var(--radius);
  background: var(--bg-surface);
  padding: 18px 20px 20px;
}
.pe-field {
  margin-bottom: 15px;
}
.pe-label {
  margin: 0 0 8px;
  font-size: 0.76rem;
  color: var(--text-muted);
  em {
    font-style: normal;
    color: var(--neg);
    margin-left: 3px;
  }
}
.pe-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.pe-chip {
  font-family: var(--font-body);
  font-size: 0.77rem;
  padding: 5px 13px;
  border-radius: 99px;
  border: 1px solid var(--border-strong);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: background-color 0.15s ease-out, border-color 0.15s ease-out, color 0.15s ease-out;
  &:hover { color: var(--text); }
  &.on {
    background: var(--accent-solid);
    border-color: var(--accent-solid);
    color: var(--on-accent);
  }
}
.pe-submit {
  width: 100%;
  margin-top: 4px;
  padding: 11px;
  font-family: var(--font-body);
  font-size: 0.84rem;
  border: none;
  border-radius: var(--radius-sm);
  background: var(--accent-solid);
  color: var(--on-accent);
  cursor: pointer;
  transition: background-color 0.15s ease-out;
  &:hover { background: var(--accent-600); }
}

/* 预设方案 */
.pe-presets {
  margin-top: 24px;
}
.pe-preset-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 10px;
}
.pe-preset-title {
  font-size: 0.78rem;
  color: var(--text-muted);
}
.pe-preset-hint {
  margin-left: auto;
  font-size: 0.72rem;
  color: var(--text-faint);
}
.pe-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 9px;
}
.pe-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  text-align: left;
  font-family: var(--font-body);
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg-surface);
  cursor: pointer;
  transition: border-color 0.15s ease-out;
  &:hover { border-color: var(--border-strong); }
}
.pe-card-title {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--text-strong);
}
.pe-card-meta {
  font-size: 0.7rem;
  color: var(--text-muted);
}
.pe-card-desc {
  font-size: 0.7rem;
  line-height: 1.5;
  color: var(--text-faint);
}

/* 底部任务入口 */
.pe-foot {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
  font-size: 0.76rem;
  color: var(--text-muted);
}
.pe-foot-n {
  font-size: 0.76rem;
  font-weight: 600;
  color: var(--text-strong);
}
.pe-foot-tag {
  font-size: 0.7rem;
  padding: 2px 8px;
  border-radius: 99px;
  background: var(--accent-50);
  color: var(--accent-700);
}
.pe-foot-link {
  margin-left: auto;
  font-family: var(--font-body);
  font-size: 0.74rem;
  background: transparent;
  border: none;
  color: var(--accent-600);
  cursor: pointer;
  &:hover { color: var(--accent-700); }
}
</style>
