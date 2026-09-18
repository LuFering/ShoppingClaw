<template>
  <a-modal
    v-model:open="visible"
    title="需要登录"
    :footer="null"
    :closable="true"
    @cancel="handleCancel"
  >
    <div class="login-prompt">
      <p class="prompt-text">{{ message }}</p>
      <div class="action-buttons">
        <a-button @click="handleCancel">取消</a-button>
        <a-button type="primary" @click="goToLogin">去登录</a-button>
      </div>
    </div>
  </a-modal>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const visible = ref(false)
const message = ref('此功能需要登录后才能使用')
let pendingAction = null

const show = (msg, action = null) => {
  message.value = msg || '此功能需要登录后才能使用'
  pendingAction = action
  visible.value = true
}

const handleCancel = () => {
  visible.value = false
  pendingAction = null
}

const goToLogin = () => {
  // 保存当前路径，登录后返回
  const currentPath = window.location.pathname + window.location.search
  if (currentPath !== '/login') {
    sessionStorage.setItem('redirect', currentPath)
  }
  
  visible.value = false
  router.push('/login')
}

defineExpose({ show })
</script>

<style lang="less" scoped>
.login-prompt {
  text-align: center;
  padding: 1rem 0;
  
  .prompt-text {
    font-size: 1rem;
    color: var(--gray-700);
    margin-bottom: 1.5rem;
  }
  
  .action-buttons {
    display: flex;
    gap: 1rem;
    justify-content: center;
  }
}
</style>
