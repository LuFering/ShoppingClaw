<script setup>
import { RouterLink, RouterView, useRoute } from 'vue-router'
import { Bot } from 'lucide-vue-next'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const route = useRoute()

const mainList = [
  {
    name: '智能体',
    path: '/agent',
    icon: Bot,
    activeIcon: Bot
  }
]
</script>

<template>
  <div class="app-layout">
    <div class="header">
      <div class="logo circle">
        <router-link to="/">
          <Bot size="22" />
        </router-link>
      </div>
      <div class="nav">
        <RouterLink
          v-for="(item, index) in mainList"
          :key="index"
          :to="item.path"
          class="nav-item"
          active-class="active"
        >
          <a-tooltip placement="right">
            <template #title>{{ item.name }}</template>
            <component
              class="icon"
              :is="route.path.startsWith(item.path) ? item.activeIcon : item.icon"
              size="22"
            />
          </a-tooltip>
        </RouterLink>
      </div>
      <div class="fill"></div>
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

  .nav {
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    position: relative;
    gap: 16px;
  }

  .fill {
    flex-grow: 1;
  }

  .logo {
    width: 34px;
    height: 34px;
    margin: 6px 0 20px 0;

    img {
      width: 100%;
      height: 100%;
      border-radius: 4px;
    }

    & > a {
      text-decoration: none;
      font-size: 24px;
      font-weight: bold;
      color: var(--gray-900);
    }
  }

  .nav-item {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    padding: 4px;
    border: 1px solid transparent;
    border-radius: 12px;
    background-color: transparent;
    color: var(--gray-1000);
    font-size: 20px;
    transition: background-color 0.2s ease-in-out, color 0.2s ease-in-out;
    margin: 0;
    text-decoration: none;
    cursor: pointer;
    outline: none;

    &.active {
      background-color: var(--gray-100);
      font-weight: bold;
      color: var(--main-color);
    }

    &:hover {
      color: var(--main-color);
    }
  }
}
</style>
