<template>
  <div class="page">
    <PageHeader
      title="智能体管理"
      desc="配置购物决策智能体的名称、模型、提示与可用数据源；启用的智能体可被对话页选择"
    >
      <template #stats>
        <span class="stat-pill">共 <b>{{ agents.length }}</b> 个</span>
        <span class="stat-pill">启用 <b>{{ enabledCount }}</b></span>
        <span class="stat-pill"><b>{{ modelCount }}</b> 种模型</span>
      </template>
      <template #actions>
        <a-button type="primary" class="lucide-icon-btn" @click="openCreate">
          <Plus :size="14" /><span>新建智能体</span>
        </a-button>
      </template>
    </PageHeader>

    <div class="page-toolbar">
      <input v-model="keyword" class="page-search" type="search" placeholder="搜索名称或模型…" />
      <a-checkbox v-model:checked="onlyEnabled">只看已启用</a-checkbox>
      <span class="toolbar-note">数据来自 /api/chat/agent（后端注册制）</span>
    </div>

    <div v-if="loading" class="page-empty">
      <a-spin tip="加载智能体…" />
    </div>

    <a-empty v-else-if="!visibleAgents.length" class="page-empty" :description="emptyText">
      <a-button v-if="!loadError" type="primary" @click="openCreate">新建智能体</a-button>
      <a-button v-else @click="loadAgents">重试</a-button>
    </a-empty>

    <div v-else class="card-list">
      <article v-for="a in visibleAgents" :key="a.id" class="card-row" :class="{ 'is-off': !a.enabled }">
        <div class="card-row-main">
          <h3 class="card-row-title">
            {{ a.name }}
            <span v-if="a.builtin" class="tag">内置</span>
          </h3>
          <p class="card-row-desc">{{ a.desc }}</p>
        </div>
        <div class="card-row-meta">
          <span class="tag tag-mono">{{ a.model || '内置' }}</span>
          <span v-if="a.sources?.length" class="tag" :title="srcText(a)">{{ a.sources.length }} 数据源</span>
          <span class="tag tag-mono">{{ a.builtin ? '代码注册' : '本地' }}</span>
        </div>
        <div class="card-row-side">
          <div class="card-row-actions">
            <button class="icon-btn" :disabled="a.builtin" title="编辑（内置智能体不可编辑）" @click="openEdit(a)"><Pencil :size="14" /></button>
            <button class="icon-btn is-danger" :disabled="a.builtin" title="删除（内置智能体不可删除）" @click="removeAgent(a)"><Trash2 :size="14" /></button>
          </div>
          <a-switch :checked="a.enabled" size="small" @change="(v) => (a.enabled = v)" />
        </div>
      </article>
    </div>

    <!-- 新增 / 编辑 -->
    <a-modal
      v-model:open="formOpen"
      :title="editingId ? '编辑智能体' : '新增智能体'"
      :width="560"
      :ok-text="editingId ? '保存更改' : '创建智能体'"
      cancel-text="取消"
      @ok="saveForm"
    >
      <a-form layout="vertical" class="ag-form">
        <a-form-item label="名称">
          <a-input v-model:value="form.name" placeholder="如：购物决策助手" />
        </a-form-item>
        <a-form-item label="描述">
          <a-input v-model:value="form.desc" placeholder="一句话说明它的职责" />
        </a-form-item>
        <a-form-item label="模型">
          <a-input v-model:value="form.model" class="mono" placeholder="如：deepseek-chat" />
        </a-form-item>
        <a-form-item label="欢迎语">
          <a-input v-model:value="form.welcome" placeholder="进入对话时的开场引导" />
        </a-form-item>
        <a-form-item label="系统提示（可选）">
          <a-textarea v-model:value="form.prompt" :rows="3" class="mono" placeholder="约束它的推理与工具使用方式" />
        </a-form-item>
        <a-form-item label="可用数据源">
          <div class="src-list">
            <a-checkbox-group v-model:value="form.sources" :options="dataSources" />
          </div>
        </a-form-item>
        <a-form-item>
          <a-switch v-model:checked="form.enabled" size="small" />
          <span class="switch-label">创建后启用</span>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { Modal, message } from 'ant-design-vue'
import { Plus, Pencil, Trash2 } from 'lucide-vue-next'
import PageHeader from '@/components/PageHeader.vue'
import { agentsApi } from '@/apis/agents_api'

// 可用数据源目录（对应已接入 MCP / 内置工具）
const dataSources = ['京东商城 MCP', '淘宝联盟 MCP', '历史价格 MCP', '优惠券聚合 MCP', '口碑评价 MCP', '内置比价工具']

// 智能体列表：真实注册（GET /api/chat/agent）+ 本地暂存（后端暂无 CRUD 端点）
const agents = ref([])
const loading = ref(false)
const loadError = ref('')

const loadAgents = async () => {
  loading.value = true
  loadError.value = ''
  try {
    agents.value = await agentsApi.listAgents()
  } catch {
    loadError.value = '智能体列表加载失败'
    agents.value = []
  } finally {
    loading.value = false
  }
}

const keyword = ref('')
const onlyEnabled = ref(false)

const enabledCount = computed(() => agents.value.filter((a) => a.enabled).length)
const modelCount = computed(() => new Set(agents.value.map((a) => a.model).filter(Boolean)).size)
const visibleAgents = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return agents.value.filter((a) => {
    if (onlyEnabled.value && !a.enabled) return false
    if (kw && !`${a.name} ${a.model} ${a.desc}`.toLowerCase().includes(kw)) return false
    return true
  })
})
const emptyText = computed(() =>
  loadError.value ? loadError.value
    : agents.value.length ? '没有匹配的智能体，调整搜索或筛选条件试试' : '还没有智能体，创建第一个购物决策智能体'
)
const srcText = (a) => (a.sources?.length ? a.sources.join(' · ') : '')

const removeAgent = (a) => {
  if (a.builtin) { message.info('内置智能体由代码注册，暂不支持删除（后端未实现）'); return }
  Modal.confirm({
    title: `删除智能体「${a.name}」？`,
    content: '删除后对话页将不可再选择它。',
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      await agentsApi.removeAgent(a.id)
      agents.value = agents.value.filter((x) => x.id !== a.id)
      message.success('已删除')
    }
  })
}

const formOpen = ref(false)
const editingId = ref(null)
const form = ref(blank())

function blank() {
  return { name: '', desc: '', model: 'deepseek-chat', welcome: '', prompt: '', sources: ['内置比价工具'], enabled: true }
}

const openCreate = () => {
  editingId.value = null
  form.value = blank()
  formOpen.value = true
}
const openEdit = (a) => {
  if (a.builtin) { message.info('内置智能体由代码注册，可在后端 agent 定义中修改'); return }
  editingId.value = a.id
  form.value = {
    name: a.name, desc: a.desc || '', model: a.model || 'deepseek-chat', welcome: a.welcome || '',
    prompt: a.prompt || '', sources: (a.sources || []).slice(), enabled: a.enabled
  }
  formOpen.value = true
}
const saveForm = async () => {
  const f = form.value
  if (!f.name.trim()) { message.warning('请填写名称'); return }
  const payload = {
    id: editingId.value || `local-${Date.now()}`,
    name: f.name.trim(),
    desc: f.desc.trim() || '—',
    model: f.model.trim() || 'deepseek-chat',
    welcome: f.welcome.trim(),
    prompt: f.prompt.trim(),
    sources: f.sources.slice(),
    enabled: f.enabled
  }
  await agentsApi.upsertAgent(payload)
  await loadAgents()
  formOpen.value = false
  message.success(editingId.value ? '已保存' : '已创建（本地暂存，后端 CRUD 实现后自动升级）')
}

loadAgents()
</script>

<style lang="less" scoped>
.mono {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: 0.8rem;
}
.switch-label {
  margin-left: 8px;
  font-size: 0.84rem;
  color: var(--text-muted);
}
/* 数据源复选框排成两列，避免长名单行溢出 */
.src-list :deep(.ant-checkbox-group) {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 16px;
}
.toolbar-note {
  margin-left: auto;
  font-size: 0.74rem;
  color: var(--text-faint);
}
.page-empty { padding: 40px 0; text-align: center; }
</style>
