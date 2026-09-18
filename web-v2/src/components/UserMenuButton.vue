<template>
  <div class="user-menu-button" @mouseenter="showMenu = true" @mouseleave="hideMenuWithDelay">
    <!-- 用户头像/占位 -->
    <div class="avatar-circle" :class="{ 'logged-in': userStore.isLoggedIn }">
      <template v-if="!userStore.isLoggedIn">
        <span class="placeholder">?</span>
      </template>
      <template v-else>
        <img v-if="userAvatar" :src="userAvatar" alt="avatar" class="avatar-img" />
        <span v-else class="avatar-text">{{ userInitial }}</span>
      </template>
    </div>

    <!-- 悬浮菜单 -->
    <transition name="menu-fade">
      <div 
        v-show="showMenu" 
        class="user-menu-popup"
        @mouseenter="cancelHide"
        @mouseleave="hideMenuWithDelay"
      >
        <!-- 未登录菜单 -->
        <template v-if="!userStore.isLoggedIn">
          <div class="menu-item">
            <button class="btn-login" @click="goToLogin">
              <LogIn size="14" />
              <span>登录</span>
            </button>
          </div>
          <div class="menu-item">
            <a 
              :href="githubRepoUrl" 
              target="_blank" 
              rel="noopener noreferrer"
              class="link-about"
            >
              <Github size="14" />
              <span>关于 ShoppingClaw</span>
            </a>
          </div>
        </template>

        <!-- 已登录菜单 -->
        <template v-else>
          <div class="menu-item">
            <button class="btn-profile" @click="showProfileModal">
              <User size="14" />
              <span>个人信息</span>
            </button>
          </div>
          <div class="menu-item">
            <button class="btn-logout" @click="handleLogout">
              <LogOut size="14" />
              <span>退出登录</span>
            </button>
          </div>
        </template>
      </div>
    </transition>

    <!-- 个人信息小窗 -->
    <ProfileModal 
      v-if="showProfile" 
      :user-info="userInfo"
      @close="showProfile = false"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { LogIn, LogOut, User, Github } from 'lucide-vue-next'
import ProfileModal from './ProfileModal.vue'

const router = useRouter()
const userStore = useUserStore()

const showMenu = ref(false)
const showProfile = ref(false)
const hideTimer = ref(null)

const githubRepoUrl = 'https://github.com/your-repo/ShoppingClaw'

const userAvatar = computed(() => userStore.userInfo?.avatar || null)

const userInitial = computed(() => {
  const username = userStore.userInfo?.username || userStore.userInfo?.user_id || 'U'
  return username.charAt(0).toUpperCase()
})

const userInfo = computed(() => ({
  user_id: userStore.userInfo?.user_id,
  username: userStore.userInfo?.username,
  email: userStore.userInfo?.email,
  phone: userStore.userInfo?.phone_number,
  role: userStore.userInfo?.role,
  created_at: userStore.userInfo?.created_at
}))

const goToLogin = () => {
  showMenu.value = false
  router.push('/login')
}

const handleLogout = async () => {
  try {
    await userStore.logout()
    showMenu.value = false
  } catch (error) {
    console.error('退出登录失败:', error)
  }
}

const showProfileModal = () => {
  showProfile.value = true
  showMenu.value = false
}

const hideMenuWithDelay = () => {
  hideTimer.value = setTimeout(() => {
    showMenu.value = false
  }, 200)
}

const cancelHide = () => {
  if (hideTimer.value) {
    clearTimeout(hideTimer.value)
    hideTimer.value = null
  }
}

onMounted(() => {
  if (userStore.isLoggedIn && !userStore.userInfo) {
    userStore.getCurrentUser().catch(console.error)
  }
})
</script>

<style lang="less" scoped>
.user-menu-button {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 12px;
  background: var(--gray-50);
  border: 1px solid var(--gray-200);
  cursor: pointer;
  transition: all 0.2s ease;
  
  &:hover {
    background: var(--gray-100);
    border-color: var(--gray-400);
  }
}

.avatar-circle {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;

  &.logged-in {
    background: transparent;
  }

  .placeholder {
    font-size: 18px;
    font-weight: bold;
    color: var(--gray-700);
  }

  .avatar-img {
    width: 100%;
    height: 100%;
    border-radius: 6px;
    object-fit: cover;
  }

  .avatar-text {
    font-size: 14px;
    font-weight: bold;
    color: var(--gray-800);
  }
}

.user-menu-popup {
  position: absolute;
  left: 50px;
  bottom: 0;
  background: white;
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
  padding: 8px 0;
  min-width: 180px;
  z-index: 1000;
}

.menu-item {
  padding: 4px 8px;

  button, a {
    width: 100%;
    padding: 8px 12px;
    border: none;
    border-radius: 6px;
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    cursor: pointer;
    transition: all 0.2s ease;
    text-decoration: none;
  }
}

.btn-login {
  background: linear-gradient(135deg, var(--main-600), var(--main-500));
  color: white;

  &:hover {
    background: linear-gradient(135deg, var(--main-700), var(--main-600));
  }
}

.btn-logout {
  background: #ff4d4f;
  color: white;

  &:hover {
    background: #ff7875;
  }
}

.btn-profile {
  background: transparent;
  color: var(--gray-700);

  &:hover {
    background: var(--gray-100);
    color: var(--main-600);
  }
}

.link-about {
  color: var(--gray-600);

  &:hover {
    background: var(--gray-100);
    color: var(--main-600);
  }
}

.menu-fade-enter-active,
.menu-fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.menu-fade-enter-from,
.menu-fade-leave-to {
  opacity: 0;
  transform: translateX(-10px);
}
</style>
