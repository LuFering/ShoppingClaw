<template>
  <div class="profile-modal-overlay" @click.self="handleClose">
    <div class="profile-modal">
      <div class="modal-header">
        <h3 class="modal-title">个人信息</h3>
        <button class="close-btn" @click="handleClose">
          <XIcon size="20" />
        </button>
      </div>

      <div class="modal-body">
        <div class="info-list">
          <div class="info-item" v-if="userInfo.user_id">
            <span class="info-label">用户ID</span>
            <span class="info-value">{{ userInfo.user_id }}</span>
          </div>

          <div class="info-item" v-if="userInfo.username">
            <span class="info-label">用户名</span>
            <span class="info-value">{{ userInfo.username }}</span>
          </div>

          <div class="info-item" v-if="userInfo.email">
            <span class="info-label">邮箱</span>
            <span class="info-value">{{ userInfo.email }}</span>
          </div>

          <div class="info-item" v-if="userInfo.phone">
            <span class="info-label">手机号</span>
            <span class="info-value">{{ userInfo.phone }}</span>
          </div>

          <div class="info-item" v-if="userInfo.role">
            <span class="info-label">角色</span>
            <span class="info-value">
              <span class="role-badge" :class="userInfo.role">
                {{ getRoleText(userInfo.role) }}
              </span>
            </span>
          </div>

          <div class="info-item" v-if="userInfo.created_at">
            <span class="info-label">注册时间</span>
            <span class="info-value">{{ formatDate(userInfo.created_at) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { X } from 'lucide-vue-next'
import dayjs from 'dayjs'

const props = defineProps({
  userInfo: {
    type: Object,
    required: true
  }
})

const emit = defineEmits(['close'])

const handleClose = () => {
  emit('close')
}

const getRoleText = (role) => {
  const roleMap = {
    'admin': '管理员',
    'user': '普通用户',
    'super_admin': '超级管理员'
  }
  return roleMap[role] || role
}

const formatDate = (dateStr) => {
  return dayjs(dateStr).format('YYYY-MM-DD HH:mm:ss')
}
</script>

<style lang="less" scoped>
.profile-modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
  animation: fadeIn 0.2s ease;
}

.profile-modal {
  background: white;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
  width: 400px;
  max-width: 90vw;
  max-height: 80vh;
  overflow: hidden;
  animation: slideUp 0.3s ease;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--gray-200);
  background: linear-gradient(135deg, var(--main-50), white);
}

.modal-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--gray-900);
}

.close-btn {
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--gray-600);
  transition: all 0.2s ease;

  &:hover {
    background: var(--gray-100);
    color: var(--gray-900);
  }
}

.modal-body {
  padding: 20px;
  max-height: calc(80vh - 60px);
  overflow-y: auto;
}

.info-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.info-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid var(--gray-100);

  &:last-child {
    border-bottom: none;
  }
}

.info-label {
  font-size: 14px;
  color: var(--gray-600);
  font-weight: 500;
  min-width: 80px;
}

.info-value {
  font-size: 14px;
  color: var(--gray-900);
  text-align: right;
  word-break: break-all;
}

.role-badge {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;

  &.admin, &.super_admin {
    background: var(--main-100);
    color: var(--main-700);
  }

  &.user {
    background: var(--gray-100);
    color: var(--gray-700);
  }
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
