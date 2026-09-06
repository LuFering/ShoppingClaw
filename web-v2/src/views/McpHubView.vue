<template>
  <div class="page">
    <PageHeader
      title="MCP 连接"
      desc="注册数据源 MCP 交由后端加载，agent 据此获得搜索、比价、券、库存等工具"
    >
      <template #stats>
        <span v-if="demoStatus.mcp" class="stat-pill">演示数据 · 等待 /api/mcp/servers</span>
      </template>
      <template #actions>
        <a-button type="primary" class="lucide-icon-btn" @click="openAdd(null)">
          <Plus :size="14" /><span>接入 MCP</span>
        </a-button>
      </template>
    </PageHeader>

    <!-- ============ 一、我的连接 ============ -->
    <section class="page-section">
      <div class="page-section-head">
        <h2 class="page-section-title">我的连接</h2>
        <span class="page-section-meta">已连接 {{ connectedCount }} / {{ connected.length }}</span>
      </div>

      <div class="page-toolbar">
        <input v-model="keyword" class="page-search" type="search" placeholder="搜索名称或地址…" />
        <a-checkbox v-model:checked="onlyConnected">只看已连接</a-checkbox>
      </div>

      <div v-if="loading" class="page-empty">
        <a-spin tip="加载 MCP 连接…" />
      </div>
      <a-empty
        v-else-if="!visibleConnected.length"
        class="page-empty"
        :description="loadError || (connected.length ? '没有匹配的连接，调整搜索或筛选条件试试' : '暂无连接，可从下方「发现 MCP」接入数据源')"
        :image-style="{ height: '48px' }"
      >
        <a-button v-if="loadError" @click="loadAll">重试</a-button>
      </a-empty>

      <div v-else class="card-list">
        <article v-for="c in visibleConnected" :key="c.id" class="card-row" :class="{ 'is-off': !c.enabled }">
          <div class="card-row-main">
            <h3 class="card-row-title">
              {{ c.name }}
              <span class="tag">{{ c.source === 'market' ? '市场' : '自定义' }}</span>
            </h3>
            <p class="card-row-desc">{{ c.desc }}</p>
          </div>
          <div class="card-row-meta">
            <span class="chip" :class="chipClass(c.status)">
              <span class="dot" />{{ statusLabel(c.status) }}
            </span>
            <span class="tag tag-mono">{{ c.type }}</span>
            <span class="tag tag-mono" :title="c.endpoint">{{ c.endpoint }}</span>
            <span class="tag tag-mono">{{ c.tools }} 工具 · {{ c.heartbeat }}</span>
          </div>
          <div class="card-row-side">
            <div class="card-row-actions">
              <button class="icon-btn" :disabled="c.testing" title="测试连接" @click="testConn(c)">
                <RefreshCw :size="14" :class="{ spin: c.testing }" />
              </button>
              <button class="icon-btn" title="编辑" @click="openAdd(c)"><Pencil :size="14" /></button>
              <button class="icon-btn is-danger" title="移除" @click="removeConn(c)"><Trash2 :size="14" /></button>
            </div>
            <a-switch :checked="c.enabled" size="small" @change="(v) => toggleEnabled(c, v)" />
          </div>
        </article>
      </div>
    </section>

    <!-- ============ 二、发现 MCP ============ -->
    <section class="page-section">
      <div class="page-section-head">
        <h2 class="page-section-title">发现 MCP</h2>
        <p class="page-section-desc">电商消费决策常用数据源，点「接入」配置后由后端加载</p>
      </div>

      <div class="tile-grid">
        <article v-for="m in marketMcps" :key="m.id" class="tile">
          <div class="tile-head">
            <h3 class="tile-name">{{ m.name }}</h3>
            <span class="chip" :class="m.installed ? 'chip-ok' : 'chip-idle'">
              <span class="dot" />{{ m.installed ? '已接入' : '未接入' }}
            </span>
          </div>
          <p class="tile-desc">{{ m.cap }}</p>
          <div class="tile-foot">
            <span class="tag tag-mono">{{ m.tools }} 工具</span>
            <a-button v-if="!m.installed" size="small" @click="installFromMarket(m)">接入</a-button>
          </div>
        </article>
      </div>
    </section>

    <!-- 接入 / 编辑 -->
    <a-modal
      v-model:open="formOpen"
      :title="editingId ? '编辑 MCP' : '接入 MCP'"
      :width="540"
      :ok-text="editingId ? '保存更改' : '注册并加载'"
      cancel-text="取消"
      @ok="saveForm"
    >
      <a-form layout="vertical" class="mcp-form">
        <a-form-item label="名称">
          <a-input v-model:value="form.name" placeholder="如：京东商城 MCP" />
        </a-form-item>
        <a-form-item label="传输类型">
          <a-radio-group v-model:value="form.transport">
            <a-radio-button v-for="t in transports" :key="t.value" :value="t.value">{{ t.label }}</a-radio-button>
          </a-radio-group>
        </a-form-item>
        <a-form-item :label="form.transport === 'stdio' ? '启动命令' : '服务地址'">
          <a-input v-model:value="form.endpoint" class="mono" :placeholder="form.transport === 'stdio' ? 'npx @shopclaw/price-history' : 'https://mcp.example.com/sse'" />
        </a-form-item>
        <a-form-item label="说明 / 用途">
          <a-textarea v-model:value="form.desc" :rows="2" placeholder="提供哪些数据、agent 何时调用" />
        </a-form-item>
      </a-form>
      <template #footer>
        <span class="test-result" :class="{ ok: testState === 'ok', fail: testState === 'fail' }">{{ testText }}</span>
        <a-button @click="runTest">测试连接</a-button>
        <a-button type="primary" @click="saveForm">{{ editingId ? '保存更改' : '注册并加载' }}</a-button>
      </template>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { Modal, message } from 'ant-design-vue'
import { Plus, RefreshCw, Pencil, Trash2 } from 'lucide-vue-next'
import PageHeader from '@/components/PageHeader.vue'
import { mcpApi } from '@/apis/mcp_api'
import { demoStatus } from '@/apis/demoStatus'

const transports = [
  { value: 'http', label: 'HTTP' },
  { value: 'sse', label: 'SSE' },
  { value: 'stdio', label: 'stdio' }
]
const statusLabel = (s) => ({ connected: '已连接', failed: '连接失败', idle: '未连接', testing: '测试中' }[s] || s)
const chipClass = (s) => ({ connected: 'chip-ok', failed: 'chip-fail', idle: 'chip-idle', testing: 'chip-info' }[s] || 'chip-idle')

// ---- 我的连接 / 发现市场（数据走 mcp_api mock 服务层，localStorage 持久化；后端 /api/mcp/* 实现后替换）----
const connected = ref([])
const marketMcps = ref([])
const loading = ref(false)
const loadError = ref('')

const loadAll = async () => {
  loading.value = true
  loadError.value = ''
  try {
    const [servers, market] = await Promise.all([mcpApi.listServers(), mcpApi.listMarket()])
    connected.value = servers
    marketMcps.value = market
  } catch {
    loadError.value = 'MCP 数据加载失败'
  } finally {
    loading.value = false
  }
}

const keyword = ref('')
const onlyConnected = ref(false)

const connectedCount = computed(() => connected.value.filter((c) => c.status === 'connected').length)
const visibleConnected = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return connected.value.filter((c) => {
    if (onlyConnected.value && c.status !== 'connected') return false
    if (kw && !`${c.name} ${c.endpoint} ${c.desc}`.toLowerCase().includes(kw)) return false
    return true
  })
})

const toggleEnabled = async (c, val) => {
  c.enabled = val
  if (!c.enabled && c.status === 'connected') c.status = 'idle'
  await mcpApi.upsertServer(c)
}
const testConn = async (c) => {
  if (c.testing) return
  c.testing = true
  c.status = 'testing'
  const ok = await mcpApi.testConnection(c)
  c.testing = false
  c.status = ok ? 'connected' : 'failed'
  if (ok) c.heartbeat = '刚刚'
  await mcpApi.upsertServer(c)
}
const removeConn = (c) => {
  Modal.confirm({
    title: `移除连接「${c.name}」？`,
    content: '移除后依赖它的 agent 将失去对应工具。',
    okText: '移除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      await mcpApi.removeServer(c.id)
      connected.value = connected.value.filter((x) => x.id !== c.id)
      await mcpApi.markMarketInstalled(c.name, false)
      const m = marketMcps.value.find((x) => x.name === c.name)
      if (m) m.installed = false
      message.success('已移除')
    }
  })
}

const formOpen = ref(false)
const editingId = ref(null)
const form = ref(blank())
const testState = ref('')
const testText = ref('')
function blank() {
  return { name: '', transport: 'http', endpoint: '', desc: '' }
}

const openAdd = (target) => {
  if (target && target.id) {
    editingId.value = target.id
    form.value = { name: target.name, transport: target.type, endpoint: target.endpoint, desc: target.desc }
  } else {
    editingId.value = null
    form.value = blank()
  }
  testState.value = ''
  testText.value = ''
  formOpen.value = true
}
const installFromMarket = (m) => {
  form.value = { name: m.name, transport: 'http', endpoint: 'https://mcp.example.com/mcp', desc: m.cap }
  editingId.value = null
  testState.value = ''
  testText.value = ''
  formOpen.value = true
}
const runTest = () => {
  if (!form.value.endpoint.trim()) { testState.value = 'fail'; testText.value = '请先填写地址/命令'; return }
  testState.value = ''
  testText.value = '测试中…'
  setTimeout(() => {
    testState.value = Math.random() > 0.2 ? 'ok' : 'fail'
    testText.value = testState.value === 'ok' ? '连接成功，可加载' : '连接失败，请检查地址'
  }, 800)
}
const saveForm = async () => {
  const f = form.value
  if (!f.name.trim() || !f.endpoint.trim()) { message.warning('请填写名称与地址/命令'); return }
  const payload = {
    id: editingId.value || `mc-${Date.now()}`,
    name: f.name.trim(),
    source: editingId.value ? (connected.value.find((x) => x.id === editingId.value)?.source || 'custom') : 'custom',
    desc: f.desc.trim() || '—',
    type: f.transport,
    endpoint: f.endpoint.trim(),
    status: testState.value === 'ok' ? 'connected' : 'idle',
    tools: editingId.value ? (connected.value.find((x) => x.id === editingId.value)?.tools ?? 0) : 0,
    heartbeat: testState.value === 'ok' ? '刚刚' : '—',
    enabled: true,
    testing: false
  }
  await mcpApi.upsertServer(payload)
  await loadAll()
  const m = marketMcps.value.find((x) => x.name === f.name.trim())
  if (m && !m.installed) {
    m.installed = true
    await mcpApi.markMarketInstalled(m.name, true)
  }
  formOpen.value = false
  message.success(editingId.value ? '已保存' : '已注册')
}

loadAll()
</script>

<style lang="less" scoped>
.mono {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: 0.78rem;
}

@keyframes rot { to { transform: rotate(360deg); } }
.spin { animation: rot 0.8s linear infinite; }

/* 发现瓦片 */
.tile-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.tile-name {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-strong);
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tile-desc {
  margin: 0;
  font-size: 0.8rem;
  color: var(--text-muted);
  line-height: 1.6;
  min-height: 40px;
}
.tile-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

/* 连接测试结果：modal 底栏需容纳「结果 + 两个按钮」，改为 flex 布局 */
.test-result {
  margin-right: auto;
  font-size: 0.8rem;
  color: var(--text-faint);
  &.ok { color: var(--pos); }
  &.fail { color: var(--neg); }
}
:deep(.ant-modal-footer) {
  display: flex;
  align-items: center;
  gap: 10px;
}
</style>
