<script setup>
import { ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import { Bot, Library, CalendarClock, Plug, Home, Radar, Wrench } from 'lucide-vue-next'
import UserMenuButton from '@/components/UserMenuButton.vue'
import parrotLogo from '@/assets/parrot-logo.png'

const route = useRoute()

// 高频主区：问一句（主页）、看情报（主动助理）、翻台账（购物档案）
const mainList = [
  { name: '主页', path: '/agent', icon: Home },
  { name: '主动助理', path: '/assistant', icon: Radar },
  { name: '购物档案', path: '/decisions', icon: Library }
]

// 系统区：发动机舱，配完不常动，沉到底部并通过二级飞出展开
const configItems = [
  { name: '智能体管理', path: '/agents', icon: Bot },
  { name: '监控任务', path: '/tasks', icon: CalendarClock },
  { name: 'MCP 数据源', path: '/mcps', icon: Plug }
]

// 初始即按当前路由展开：跨顶级路由导航时 AppLayout 会重挂载，watch 来不及生效
const configOpen = ref(configItems.some((i) => route.path.startsWith(i.path)))
// /agents 会误匹配 startsWith('/agent')，主页需精确匹配
const isActive = (p) => (p === '/agent' ? route.path === '/agent' || route.path.startsWith('/agent/') : route.path.startsWith(p))
const inConfig = () => configItems.some((i) => route.path.startsWith(i.path))
const toggleConfig = () => { configOpen.value = !configOpen.value }

// 离开配置区页面时自动收起飞出
watch(() => route.path, () => { if (!inConfig()) configOpen.value = false })
</script>

<template>
  <div class="app-layout">
    <div class="header">
      <div class="logo circle">
        <router-link to="/">
          <img :src="parrotLogo" alt="ShoppingClaw" />
        </router-link>
      </div>

      <!-- 高频主区 + 配置（点击向下展开二级，浅色差异做主次） -->
      <nav class="nav">
        <RouterLink
          v-for="(item, index) in mainList"
          :key="index"
          :to="item.path"
          class="nav-item"
          :class="{ active: isActive(item.path) }"
        >
          <a-tooltip placement="right" :title="item.name">
            <component :is="item.icon" size="22" />
          </a-tooltip>
        </RouterLink>

        <button
          class="nav-item"
          :class="{ active: configOpen || inConfig() }"
          aria-label="配置"
          @click="toggleConfig"
        >
          <a-tooltip placement="right" title="配置">
            <Wrench size="22" />
          </a-tooltip>
        </button>

        <div class="cfg-slide" :class="{ open: configOpen }">
          <div class="cfg-clip">
            <div class="config-sub">
              <RouterLink
                v-for="c in configItems"
                :key="c.path"
                :to="c.path"
                class="nav-item sub"
                :class="{ active: isActive(c.path) }"
              >
                <a-tooltip placement="right" :title="c.name">
                  <component :is="c.icon" size="18" />
                </a-tooltip>
              </RouterLink>
            </div>
          </div>
        </div>
      </nav>

      <div class="nav-divider"></div>
      <div class="fill"></div>

      <!-- 用户菜单（固定在底部） -->
      <div class="user-menu-container">
        <UserMenuButton />
      </div>
    </div>

    <router-view v-slot="{ Component, route }" id="app-router-view">
      <keep-alive v-if="route.meta.keepAlive !== false">
        <component :is="Component" />
      </keep-alive>
      <component :is="Component" v-else />
    </router-view>
  </div>
</template>

<style lang="less" scoped>
@header-width: 50px;

.app-layout {
  position: relative;
  display: flex;
  flex-direction: row;
  width: 100%;
  height: 100vh;
  min-width: var(--min-width);
}

div.header,
#app-router-view {
  height: 100%;
  max-width: 100%;
  user-select: none;
}

#app-router-view {
  flex: 1 1 auto;
  overflow-y: auto;
}

.header {
  display: flex;
  flex-direction: column;
  flex: 0 0 @header-width;
  justify-content: flex-start;
  align-items: center;
  background-color: var(--main-0);
  height: 100%;
  width: @header-width;
  border-right: 1px solid var(--gray-100);
  z-index: 21; // 高于二级飞出，保证 ⚙ 按钮可点

  .nav {
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    position: relative;
    gap: 16px;
  }

  .nav-divider {
    width: 26px;
    height: 1px;
    background: var(--gray-150);
    margin: 10px 0 4px;
  }

  .fill {
    flex-grow: 1;
  }

  .user-menu-container {
    padding: 8px;
    margin-bottom: 8px;
  }

  .logo {
    width: 34px;
    height: 34px;
    margin: 6px 0 20px 0;

    & > a {
      display: flex;
      width: 100%;
      height: 100%;
      align-items: center;
      justify-content: center;
      text-decoration: none;
    }

    img {
      width: 100%;
      height: 100%;
      object-fit: contain;
      border-radius: 4px;
    }
  }

  .nav-item {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    border: none;
    background: transparent;
    color: var(--gray-1000);
    transition: color 0.2s ease-in-out;
    margin: 0;
    text-decoration: none;
    cursor: pointer;
    outline: none;
    -webkit-tap-highlight-color: transparent;

    // 点击后各浏览器会画 focus 描边圈（黑圈），跨浏览器强制清除
    &:focus,
    &:focus-visible,
    &:focus-within,
    &:active {
      outline: none;
      box-shadow: none;
    }

    // 激活只变色，不加方形底框
    &.active {
      color: var(--main-color);
    }

    &:hover {
      color: var(--main-color);
    }
  }
}

/* 配置二级：同栏向下展开，浅色底差异做主次（gray-100 双主题自动切换） */
.cfg-slide {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 0.15s ease-out;
  &.open { grid-template-rows: 1fr; }
}
.cfg-clip { overflow: hidden; }
.config-sub {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 8px 0;
  margin-top: 10px;
  width: 38px;
  background: var(--gray-100);
  border-radius: 10px;
  .nav-item.sub {
    width: 28px;
    height: 28px;
    color: var(--gray-600);
    &.active {
      color: var(--main-color);
    }
  }
}
</style>
