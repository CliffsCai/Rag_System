<template>
  <div class="admin-panel">
    <!-- 知识库详情视图 -->
    <div v-if="currentCollection">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px">
        <el-button :icon="ArrowLeft" circle size="small" @click="currentCollection = null" />
        <span style="font-size:16px;font-weight:600">{{ currentCollection.collection_name }}</span>
        <el-tag type="info" size="small">{{ currentCollection.namespace }}</el-tag>
        <el-tag size="small" v-if="currentCollection.embedding_model">{{ currentCollection.embedding_model }}</el-tag>
      </div>
      <el-tabs type="border-card">
        <el-tab-pane label="📤 上传文档" name="upload">
      <DocUpload :collection="currentCollection.collection_name"
            :image-mode="currentCollection.image_mode"
            @go-categories="$emit('go-categories')" />
        </el-tab-pane>
        <el-tab-pane label="📚 文件列表" name="files">
          <DocList ref="docListRef" :collection="currentCollection.collection_name" @view-chunks="openChunkEditor" />
        </el-tab-pane>
        <el-tab-pane label="🔍 切片检索" name="search">
          <DocSearch :collection="currentCollection.collection_name" />
        </el-tab-pane>
      </el-tabs>

      <el-dialog
        v-model="chunkEditorVisible"
        :title="`🧩 切片编辑 — ${currentJobId}`"
        width="92%" top="4vh" destroy-on-close
      >
        <ChunkEditorPanel :job-id="currentJobId" :readonly="chunkEditorReadonly" :image-mode="currentCollection?.image_mode || false" @vectorized="onVectorized" />
      </el-dialog>
    </div>

    <!-- 知识库列表/创建/配置 -->
    <el-tabs v-else v-model="currentTab" class="admin-tabs">

      <!-- 知识库列表 -->
      <el-tab-pane label="📚 知识库列表" name="collections">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header">
              <div>
                <span>知识库列表</span>
                <el-tag type="info" size="small" style="margin-left:8px">{{ defaultNs }}</el-tag>
              </div>
              <el-button type="primary" size="small" @click="loadCollections" :loading="colListLoading">刷新</el-button>
            </div>
          </template>
          <el-table :data="collections" v-loading="colListLoading" empty-text="暂无知识库">
            <el-table-column prop="collection_name" label="知识库名称" min-width="160" />
            <el-table-column prop="embedding_model" label="Embedding 模型" min-width="160" />
            <el-table-column prop="dimension" label="维度" width="80" />
            <el-table-column prop="metrics" label="相似度" width="90" />
            <el-table-column prop="parser" label="分词器" width="80" />
            <el-table-column prop="full_text_retrieval_fields" label="全文检索字段" min-width="120" show-overflow-tooltip />
            <el-table-column label="图文模式" width="90" align="center">
              <template #default="{ row }">
                <el-tag v-if="row.image_mode" type="warning" size="small">图文</el-tag>
                <el-tag v-else type="info" size="small">普通</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="元数据字段" min-width="200" show-overflow-tooltip>
              <template #default="{ row }">
                <span>{{ formatMetaFields(row.metadata_fields) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="120" fixed="right">
              <template #default="{ row }">
                <el-button type="primary" size="small" plain @click="enterCollection(row)">管理</el-button>
                <el-popconfirm
                  :title="`确认删除知识库「${row.collection_name}」？`"
                  confirm-button-text="删除" cancel-button-text="取消"
                  confirm-button-type="danger"
                  @confirm="deleteCollection(row.namespace, row.collection_name)"
                >
                  <template #reference>
                    <el-button type="danger" size="small" plain style="margin-left:4px">删除</el-button>
                  </template>
                </el-popconfirm>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <!-- 创建知识库 -->
      <el-tab-pane label="➕ 创建知识库" name="create">
        <el-card shadow="hover">
          <template #header><span>创建知识库</span></template>
          <el-form :model="colForm" label-width="160px" style="max-width:780px">

            <el-divider content-position="left">基础配置</el-divider>
            <el-form-item label="命名空间">
              <el-tag type="info">{{ defaultNs }}</el-tag>
              <span class="tip" style="margin-left:8px">由 .env ADB_NAMESPACE 决定</span>
            </el-form-item>
            <el-form-item label="知识库名称" required>
              <el-input v-model="colForm.collection" placeholder="例如: my_knowledge" style="width:260px" />
              <div class="tip">小写字母、数字、下划线</div>
            </el-form-item>

            <el-divider content-position="left">元数据字段</el-divider>
            <el-form-item label="可选字段">
              <div class="preset-fields">
                <div v-for="preset in PRESET_FIELDS" :key="preset.key" class="preset-row">
                  <el-checkbox
                    v-model="preset.enabled"
                    style="width:160px;font-weight:500"
                  >{{ preset.label }}（{{ preset.key }}）</el-checkbox>
                  <template v-if="preset.enabled">
                    <el-checkbox v-model="preset.fulltext" :disabled="!isTextType(preset.type)" style="margin-left:16px">全文检索</el-checkbox>
                    <el-checkbox v-model="preset.index" style="margin-left:8px">标量索引</el-checkbox>
                    <el-tag v-if="preset.auto_inject" type="success" size="small" style="margin-left:12px">
                      {{ autoInjectLabel(preset.auto_inject) }}
                    </el-tag>
                  </template>
                  <span v-else class="tip" style="margin-left:16px">{{ preset.description }}</span>
                </div>
              </div>
            </el-form-item>
            <el-form-item label="分词器">
              <el-select v-model="colForm.parser" style="width:200px">
                <el-option label="中文 (zh_cn)" value="zh_cn" />
                <el-option label="英文 (english)" value="english" />
              </el-select>
            </el-form-item>

            <el-divider content-position="left">向量配置</el-divider>
            <el-form-item label="Embedding 模型">
              <el-select v-model="colForm.embedding_model" @change="onModelChange" style="width:320px">
                <el-option-group label="推荐">
                  <el-option label="text-embedding-v3（默认，1024维）" value="text-embedding-v3" />
                  <el-option label="multimodal-embedding-v1（多模态，1024维）" value="multimodal-embedding-v1" />
                </el-option-group>
                <el-option-group label="其他">
                  <el-option label="text-embedding-v2（1536维）" value="text-embedding-v2" />
                  <el-option label="text-embedding-v1（1536维）" value="text-embedding-v1" />
                  <el-option label="m3e-base（768维）" value="m3e-base" />
                  <el-option label="m3e-small（512维）" value="m3e-small" />
                </el-option-group>
              </el-select>
            </el-form-item>
            <el-form-item label="向量维度">
              <el-input-number v-model="colForm.dimension" :min="64" :max="4096" :controls="false" style="width:140px" />
              <span class="tip" style="margin-left:8px">留空自动匹配模型默认维度</span>
            </el-form-item>
            <el-form-item label="相似度算法">
              <el-radio-group v-model="colForm.metrics">
                <el-radio value="cosine">余弦相似度（推荐）</el-radio>
                <el-radio value="l2">欧氏距离</el-radio>
                <el-radio value="ip">内积</el-radio>
              </el-radio-group>
            </el-form-item>

            <el-divider content-position="left">索引配置（高级，可留空）</el-divider>
            <el-form-item label="HNSW 最大邻居数">
              <el-input-number v-model="colForm.hnsw_m" :min="2" :max="1000" :controls="false" style="width:120px" />
              <div class="tip">建议：维度≤384→16，≤768→32，≤1024→64，>1024→128</div>
            </el-form-item>
            <el-form-item label="HNSW 候选集大小">
              <el-input-number v-model="colForm.hnsw_ef_construction" :min="4" :max="1000" :controls="false" style="width:120px" />
              <div class="tip">需 ≥ 2 × HNSW最大邻居数，默认64</div>
            </el-form-item>
            <el-form-item label="PQ 算法加速">
              <el-switch v-model="colForm.pq_enable_bool" active-text="开启" inactive-text="关闭" />
              <div class="tip">数据量 > 50万时建议开启</div>
            </el-form-item>
            <el-form-item label="外部存储（mmap）">
              <el-switch v-model="colForm.external_storage_bool" active-text="开启" inactive-text="关闭" />
              <div class="tip">仅 6.0 版本支持；开启后不支持删除/更新</div>
            </el-form-item>

            <el-divider content-position="left">图文模式</el-divider>
            <el-form-item label="启用图文模式">
              <el-switch v-model="colForm.image_mode" active-text="开启" inactive-text="关闭" />
              <div class="tip">开启后上传文件将使用自定义 PDF 解析，提取图片并与切片关联，回答时可展示图片</div>
            </el-form-item>

            <el-form-item>
              <el-button type="primary" @click="createCollection" :loading="colCreateLoading">创建知识库</el-button>
              <el-button @click="resetColForm">重置</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>

      <!-- 配置信息 -->
      <el-tab-pane label="📊 配置信息" name="config">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header">
              <span>当前 ADB 配置</span>
              <el-button type="primary" size="small" @click="loadConfig" :loading="configLoading">刷新</el-button>
            </div>
          </template>
          <el-descriptions :column="2" border v-if="config">
            <el-descriptions-item label="实例 ID">{{ config.instance_id }}</el-descriptions-item>
            <el-descriptions-item label="区域">{{ config.region_id }}</el-descriptions-item>
            <el-descriptions-item label="命名空间">{{ config.namespace }}</el-descriptions-item>
            <el-descriptions-item label="当前文档集合">{{ config.collection }}</el-descriptions-item>
            <el-descriptions-item label="Embedding 模型" :span="2">{{ config.embedding_model }}</el-descriptions-item>
          </el-descriptions>
          <el-empty v-else description="暂无配置信息" />
        </el-card>
      </el-tab-pane>

    </el-tabs>
  </div>
</template>

<script setup>
import { ref, reactive, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowLeft } from '@element-plus/icons-vue'
import axios from 'axios'
import DocUpload from './doc/DocUpload.vue'
import DocList from './doc/DocList.vue'
import DocSearch from './doc/DocSearch.vue'
import ChunkEditorPanel from './doc/ChunkEditorPanel.vue'

const props = defineProps({
  activeTab: { type: String, default: 'collections' }
})

const API = 'http://localhost:8000/api/v1'
const currentTab = ref(props.activeTab)
watch(() => props.activeTab, (v) => { currentTab.value = v })

const defaultNs = ref('knowledge_ns')

// ── 预定义字段（后续在此扩展）────────────────────────────────────────────────
const PRESET_FIELDS = reactive([
  {
    key: 'title',
    label: '标题',
    type: 'text',
    enabled: false,
    fulltext: true,
    index: false,
    auto_inject: 'filename_prefix',
    description: '自动从文件名提取（去掉扩展名）',
  },
  // 后续扩展示例：
  // { key: 'category', label: '类目', type: 'text', enabled: false, fulltext: false, index: true, auto_inject: 'category_name', description: '自动注入类目名' },
  // { key: 'questions', label: '预设问题', type: 'text', enabled: false, fulltext: true, index: false, auto_inject: 'preset_questions', description: '预设问题列表' },
])

const autoInjectLabel = (v) => {
  const map = { filename_prefix: '自动注入文件名', category_name: '自动注入类目名', preset_questions: '预设问题' }
  return map[v] || v
}
const isTextType = (t) => ['text', 'jsonb'].includes(t)
const formatMetaFields = (fields) => {
  if (!fields || !fields.length) return '-'
  return fields.map(f => f.key).join(', ')
}

// ── 知识库详情 ────────────────────────────────────────────────────────────────
const currentCollection = ref(null)
const chunkEditorVisible = ref(false)
const currentJobId = ref('')
const chunkEditorReadonly = ref(false)
const docListRef = ref(null)

const enterCollection = (row) => { currentCollection.value = row }
const onChunksFetched = (job) => { openChunkEditor(job.job_id) }
const openChunkEditor = (jobId, readonly = false) => {
  currentJobId.value = jobId
  chunkEditorReadonly.value = readonly
  chunkEditorVisible.value = true
}
const onVectorized = () => { docListRef.value?.load() }

// ── 配置信息 ──────────────────────────────────────────────────────────────────
const config = ref(null)
const configLoading = ref(false)
const loadConfig = async () => {
  configLoading.value = true
  try {
    const { data } = await axios.get(`${API}/admin/config`)
    if (data.success) {
      config.value = data.data
      if (data.data?.namespace) defaultNs.value = data.data.namespace
    }
  } catch (e) {
    ElMessage.error('加载配置失败: ' + (e.response?.data?.detail || e.message))
  } finally { configLoading.value = false }
}

// ── 知识库列表 ────────────────────────────────────────────────────────────────
const collections = ref([])
const colListLoading = ref(false)

const loadCollections = async () => {
  colListLoading.value = true
  try {
    const { data } = await axios.get(`${API}/admin/collection/list`, {
      params: { namespace: defaultNs.value }
    })
    if (data.success) collections.value = data.data.collections || []
  } catch (e) {
    ElMessage.error('查询失败: ' + (e.response?.data?.detail || e.message))
  } finally { colListLoading.value = false }
}

const deleteCollection = async (namespace, collectionName) => {
  try {
    await axios.delete(`${API}/admin/collection/delete`, {
      data: { namespace, collection: collectionName }
    })
    ElMessage.success(`知识库「${collectionName}」已删除`)
    await loadCollections()
  } catch (e) {
    ElMessage.error('删除失败: ' + (e.response?.data?.detail || e.message))
  }
}

// ── 创建知识库 ────────────────────────────────────────────────────────────────
const colCreateLoading = ref(false)

const defaultColForm = () => ({
  collection: '', parser: 'zh_cn',
  embedding_model: 'text-embedding-v3', dimension: null, metrics: 'cosine',
  hnsw_m: null, hnsw_ef_construction: null,
  pq_enable_bool: false, external_storage_bool: false,
  image_mode: false,
})
const colForm = ref(defaultColForm())

const modelDimMap = { 'text-embedding-v2': 1536, 'text-embedding-v1': 1536, 'm3e-base': 768, 'm3e-small': 512 }
const onModelChange = (val) => { colForm.value.dimension = modelDimMap[val] ?? null }

const createCollection = async () => {
  if (!colForm.value.collection) return ElMessage.warning('请填写知识库名称')
  colCreateLoading.value = true
  try {
    const enabledFields = PRESET_FIELDS
      .filter(f => f.enabled)
      .map(f => ({
        key: f.key,
        type: f.type,
        fulltext: f.fulltext,
        index: f.index,
        auto_inject: f.auto_inject || null,
      }))

    const payload = {
      namespace: defaultNs.value,
      collection: colForm.value.collection,
      parser: colForm.value.parser,
      embedding_model: colForm.value.embedding_model || null,
      dimension: colForm.value.dimension || null,
      metrics: colForm.value.metrics,
      hnsw_m: colForm.value.hnsw_m || null,
      hnsw_ef_construction: colForm.value.hnsw_ef_construction || null,
      pq_enable: colForm.value.pq_enable_bool ? 1 : 0,
      external_storage: colForm.value.external_storage_bool ? 1 : 0,
      metadata_fields: enabledFields,
      image_mode: colForm.value.image_mode,
    }
    const { data } = await axios.post(`${API}/admin/collection/create`, payload)
    if (data.success) {
      ElMessage.success(`知识库「${colForm.value.collection}」创建成功`)
      resetColForm()
      currentTab.value = 'collections'
      await loadCollections()
    }
  } catch (e) {
    ElMessage.error('创建失败: ' + (e.response?.data?.detail || e.message))
  } finally { colCreateLoading.value = false }
}

const resetColForm = () => {
  colForm.value = defaultColForm()
  PRESET_FIELDS.forEach(f => { f.enabled = false; f.fulltext = f.key === 'title'; f.index = false })
}

onMounted(async () => {
  await loadConfig()
  await loadCollections()
})
</script>

<style scoped>
.admin-panel { padding: 20px; max-width: 1200px; margin: 0 auto; }
.admin-tabs { margin-top: 0; }
.card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 600; }
.preset-fields { display: flex; flex-direction: column; gap: 12px; }
.preset-row { display: flex; align-items: center; padding: 8px 12px; background: #f5f7fa; border-radius: 6px; }
.tip { font-size: 12px; color: #909399; margin-top: 4px; line-height: 1.5; }
:deep(.el-divider__text) { font-weight: 600; color: #409eff; }
</style>
