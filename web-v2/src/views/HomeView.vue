<template>
  <div class="home-container">
    <div v-if="isLoading" class="loading-container">
      <a-spin size="large" />
      <p class="loading-text">正在连接服务...</p>
    </div>
    <div v-else-if="error" class="error-container">
      <a-result status="error" :title="error.title" :sub-title="error.message">
        <template #extra>
          <a-button type="primary" @click="retryLoad">重试</a-button>
        </template>
      </a-result>
    </div>
    <template v-else>
      <div class="hero-section">
        <div class="glass-header">
          <div class="logo">
            <img :src="infoStore.organization.logo" :alt="infoStore.organization.name" class="logo-img" />
            <span class="logo-text">{{ infoStore.organization.name }}</span>
          </div>
          <div class="header-actions">
            <a-button type="link" v-if="!userStore.isLoggedIn" @click="router.push('/login')">登录</a-button>
            <a-button type="link" v-if="userStore.isLoggedIn" @click="goToChat">智能体</a-button>
          </div>
        </div>
        <div class="hero-layout">
          <div class="hero-content">
            <h1 class="title">ShoppingClaw</h1>
            <p class="subtitle">智能购物助手</p>
            <div class="hero-actions">
              <button class="button-base primary" @click="goToChat">开始对话</button>
            </div>
          </div>
        </div>
      </div>
      <footer class="footer">
        <div class="footer-content">
          <p class="copyright">© 2026 ShoppingClaw. All rights reserved.</p>
        </div>
      </footer>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useInfoStore } from '@/stores/info'
import { useAgentStore } from '@/stores/agent'
import { Result, Button } from 'ant-design-vue'

const AResult = Result
const AButton = Button

const router = useRouter()
const userStore = useUserStore()
const infoStore = useInfoStore()
const agentStore = useAgentStore()

const isLoading = ref(true)
const error = ref(null)

const loadData = async () => {
  isLoading.value = true
  error.value = null
  try {
    const resp = await fetch('/api/system/health')
    if (!resp.ok) throw new Error('服务不可用')
    await infoStore.loadInfoConfig()
  } catch (e) {
    error.value = { title: '服务连接失败', message: '后端服务无法响应' }
  } finally {
    isLoading.value = false
  }
}

const retryLoad = () => { loadData() }

const goToChat = async () => {
  if (!userStore.isLoggedIn) {
    router.push('/login')
    return
  }
  await agentStore.initialize()
  router.push('/agent')
}

onMounted(() => { loadData() })
</script>

<style lang="less" scoped>
.home-container {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: radial-gradient(circle at top right, var(--main-50), transparent 60%), var(--main-5);
}

.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  gap: 1rem;
  .loading-text { color: var(--gray-600); font-size: 0.95rem; }
}

.error-container {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: 2rem;
}

.glass-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  padding: 0.75rem 2.5rem;
  background-color: var(--color-trans-light);
  backdrop-filter: blur(20px);
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
}

.logo {
  display: flex;
  align-items: center;
  font-size: 1.4rem;
  font-weight: bold;
  color: var(--main-800);
  .logo-img { height: 2rem; margin-right: 0.6rem; }
}

.hero-section {
  flex: 1;
  width: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 5rem 2rem 2rem;
}

.hero-layout {
  display: flex;
  justify-content: center;
  align-items: center;
  max-width: 1200px;
  margin: 0 auto;
  padding-top: 4rem;
}

.hero-content {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  text-align: center;
  align-items: center;
}

.title {
  font-size: clamp(2.5rem, 4vw, 4rem);
  font-weight: 800;
  margin: 0;
  background: linear-gradient(135deg, var(--main-900), var(--main-600));
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  line-height: 1.1;
}

.subtitle {
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--gray-700);
}

.hero-actions {
  display: flex;
  gap: 1rem;
  align-items: center;
}

.button-base {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0.5rem 2.75rem;
  border-radius: 999px;
  font-size: 1.05rem;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid transparent;
  min-height: 52px;
  &.primary {
    background: linear-gradient(135deg, var(--main-600), var(--main-500));
    color: var(--gray-0);
    &:hover { background: linear-gradient(135deg, var(--main-700), var(--main-600)); }
  }
}

.footer {
  margin-top: auto;
  background: var(--main-0);
  border-top: 1px solid var(--main-20);
}

.footer-content {
  text-align: center;
  padding: 2rem;
  max-width: 1200px;
  margin: 0 auto;
}

.copyright {
  color: var(--main-700);
  font-size: 0.9rem;
  font-weight: 500;
  margin: 0;
}

@media (max-width: 768px) {
  .glass-header { padding: 0.8rem 1.25rem; }
  .title { font-size: 2.4rem; }
  .subtitle { font-size: 1.2rem; }
}
</style>
