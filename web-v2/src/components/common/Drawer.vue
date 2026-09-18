<template>
  <transition name="dw">
    <div v-if="open" class="dw-mask" @click.self="$emit('close')">
      <aside class="dw" :style="{ width: width + 'px' }">
        <header class="dw-head">
          <span class="dw-title">{{ title }}</span>
          <button class="dw-close" type="button" aria-label="关闭" @click="$emit('close')">
            <span class="x" />
          </button>
        </header>
        <div class="dw-body"><slot /></div>
      </aside>
    </div>
  </transition>
</template>

<script setup>
defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, default: '' },
  width: { type: Number, default: 460 }
})
defineEmits(['close'])
</script>

<style lang="less" scoped>
.dw-mask {
  position: absolute;
  inset: 0;
  z-index: 30;
  display: flex;
  justify-content: flex-end;
  background: rgba(0, 0, 0, 0.18);
}

.dw {
  display: flex;
  flex-direction: column;
  max-width: 92%;
  height: 100%;
  background: var(--bg-surface);
  border-left: 1px solid var(--border);
}

.dw-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);

  .dw-title { font-size: 0.86rem; font-weight: 600; color: var(--text-strong); }

  .dw-close {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    background: transparent;
    border: none;
    cursor: pointer;

    .x {
      position: relative;
      width: 12px;
      height: 12px;

      &::before,
      &::after {
        content: '';
        position: absolute;
        left: 0;
        top: 5px;
        width: 12px;
        height: 1px;
        background: var(--text-muted);
      }
      &::before { transform: rotate(45deg); }
      &::after { transform: rotate(-45deg); }
    }
    &:hover .x::before,
    &:hover .x::after { background: var(--text-strong); }
  }
}

.dw-body {
  flex: 1 1 auto;
  overflow-y: auto;
  padding: 16px 18px;
}

.dw-enter-active,
.dw-leave-active { transition: opacity 0.18s ease-out; }
.dw-enter-active .dw,
.dw-leave-active .dw { transition: transform 0.18s ease-out; }
.dw-enter-from,
.dw-leave-to { opacity: 0; }
.dw-enter-from .dw,
.dw-leave-to .dw { transform: translateX(16px); }
</style>
