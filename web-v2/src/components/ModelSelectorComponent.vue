<template>
  <a-dropdown
    trigger="click"
    :open="dropdownOpen"
    :disabled="props.disabled"
    @open-change="handleOpenChange"
  >
    <div class="model-select" :class="{ 'model-select--disabled': props.disabled }" title="选择对话模型">
      <img v-if="currentProviderIcon" :src="currentProviderIcon" class="model-provider-icon" alt="" />
      <span class="model-text">{{ displayModelText }}</span>
      <ChevronDown :size="13" class="model-chevron" />
    </div>
    <template #overlay>
      <div class="model-dropdown" @click.stop>
        <div class="model-search">
          <a-input
            v-model:value="searchKeyword"
            placeholder="搜索模型"
            allow-clear
            autocomplete="off"
            spellcheck="false"
            @keydown.stop
          />
        </div>
        <a-menu class="scrollable-menu">
          <a-menu-item v-if="loadingModels" key="loading" disabled>加载中...</a-menu-item>
          <a-menu-item v-else-if="!hasFilteredModels" key="empty" disabled>暂无匹配模型</a-menu-item>
          <template v-else>
            <a-menu-item-group v-for="provider in filteredProviders" :key="provider.id">
              <template #title>
                <span class="provider-group-title">
                  <img
                    v-if="getProviderIcon(provider.id)"
                    :src="getProviderIcon(provider.id)"
                    class="model-provider-icon"
                    alt=""
                  />
                  {{ provider.name || provider.id }}
                </span>
              </template>
              <a-menu-item
                v-for="spec in filteredModelSpecs(provider)"
                :key="spec"
                @click="handleSelect(spec)"
              >
                <div class="model-option">
                  <span class="model-option-name" :title="spec">{{ modelNameOnly(spec) }}</span>
                  <Check v-if="spec === props.modelSpec" :size="14" class="model-option-check" />
                </div>
              </a-menu-item>
            </a-menu-item-group>
          </template>
        </a-menu>
        <div class="model-dropdown-footer">选择后立即对下一次提问生效</div>
      </div>
    </template>
  </a-dropdown>
</template>

<script setup>
// 参考自 Yuxi（xerrors/Yuxi）的 ModelSelectorComponent 简化版：
// 保留按提供商分组 + 搜索；模型目录来自 GET /api/chat/models（静态目录），
// 状态检查 / 缓存刷新 / 元数据徽标依赖 Yuxi 专属后端，未引入。
import { computed, ref } from 'vue'
import { ChevronDown, Check } from 'lucide-vue-next'
import { modelApi } from '@/apis/model_api'
import { modelIcons } from '@/utils/modelIcon'

const props = defineProps({
  modelSpec: { type: String, default: '' },
  disabled: { type: Boolean, default: false }
})
const emit = defineEmits(['select-model'])

const providers = ref([])
const loadingModels = ref(false)
const dropdownOpen = ref(false)
const searchKeyword = ref('')
let fetchPromise = null

const fetchModels = async () => {
  if (fetchPromise) return fetchPromise
  loadingModels.value = true
  fetchPromise = modelApi
    .getChatModels()
    .then((res) => {
      providers.value = res?.providers || []
    })
    .catch((error) => {
      console.warn('加载模型目录失败:', error)
    })
    .finally(() => {
      loadingModels.value = false
      fetchPromise = null
    })
  return fetchPromise
}

const handleOpenChange = async (open) => {
  if (props.disabled) {
    dropdownOpen.value = false
    return
  }
  if (!open) {
    dropdownOpen.value = false
    return
  }
  await fetchModels()
  if (!props.disabled) dropdownOpen.value = true
}

const keyword = computed(() => searchKeyword.value.trim().toLowerCase())

const filteredProviders = computed(() => {
  if (!keyword.value) return providers.value
  return providers.value
    .map((provider) => ({
      ...provider,
      models: (provider.models || []).filter(
        (spec) =>
          spec.toLowerCase().includes(keyword.value) ||
          (provider.name || provider.id).toLowerCase().includes(keyword.value)
      )
    }))
    .filter((provider) => provider.models.length)
})

const filteredModelSpecs = (provider) => provider.models || []
const hasFilteredModels = computed(() => filteredProviders.value.some((p) => p.models?.length))

const modelNameOnly = (spec) => (spec || '').split('/').pop() || spec || ''
const currentModelName = computed(() => modelNameOnly(props.modelSpec))
const displayModelText = computed(() => props.modelSpec ? currentModelName.value : '默认模型')

const getProviderIcon = (providerId) => modelIcons[providerId] || modelIcons.default
const currentProviderIcon = computed(() => {
  if (!props.modelSpec) return ''
  const providerId = props.modelSpec.split('/')[0]
  return modelIcons[providerId] || modelIcons.default
})

const handleSelect = (spec) => {
  if (props.disabled) return
  emit('select-model', spec)
  dropdownOpen.value = false
}
</script>

<style lang="less" scoped>
.model-select {
  display: flex;
  align-items: center;
  gap: 5px;
  max-width: 180px;
  height: 30px;
  padding: 0 8px;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1;
  color: var(--gray-600);
  cursor: pointer;
  user-select: none;
  transition: all 0.2s ease;

  &:hover {
    color: var(--gray-900);
    background: var(--gray-100);
  }
}

.model-select--disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.model-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.model-chevron {
  flex-shrink: 0;
  color: var(--gray-500);
}

.model-provider-icon {
  flex-shrink: 0;
  width: 15px;
  height: 15px;
  object-fit: contain;
}

.model-dropdown {
  width: min(280px, calc(100vw - 24px));
  padding: 8px 0;
  overflow: hidden;
  background: var(--gray-0, #fff);
  border-radius: 8px;
  box-shadow: 0 0 18px rgba(0, 0, 0, 0.1);
}

.model-search {
  padding: 8px;
}

:deep(.scrollable-menu) {
  max-height: 260px;
  overflow-y: auto;
  box-shadow: none;
}

.provider-group-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.model-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-width: 0;
}

.model-option-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.model-option-check {
  flex-shrink: 0;
  color: var(--main-600, #1677ff);
}

.model-dropdown-footer {
  padding: 7px 12px;
  border-top: 1px solid var(--gray-100);
  color: var(--gray-500);
  font-size: 11px;
}
</style>
