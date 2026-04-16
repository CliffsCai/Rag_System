<template>
  <div class="admin-panel">
    <!-- 知识图谱视图 -->
    <KnowledgeGraphPanel
      v-if="graphKbName"
      :kb-name="graphKbName"
      @back="graphKbName = ''"
    />

    <!-- 知识库详情视图 -->
    <div v-else-if="currentCollection">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px">
        <el-button :icon="ArrowLeft" circle size="small" @click="currentCollection = null" />
        <span style="font-size:16px;font-weight:600">{{ currentCollection.display_name || currentCollection.name }}</span>
        <el-tag type="info" size="small">{{ currentCollection.name }}</el-tag>
        <el-tag size="small" v-if="currentCollection.embedding_model">{{ currentCollection.embedding_model }}</el-tag>
      </div>
      <el-tabs type="border-card">
        <el-tab-pane label="📤 上传文档" name="upload">
          <DocUpload :collection="currentCollection.name"
                :image-mode="currentCollection.image_mode"
                @go-categories="$emit('go-categories')" />
        </el-tab-pane>
        <el-tab-pane label="📚 文件列表" name="files">
          <DocList ref="docListRef" :collection="currentCollection.name" @view-chunks="openChunkEditor" />
        </el-tab-pane>
        <el-tab-pane label="🔍 切片检索" name="search">
          <DocSearch :collection="currentCollection.name" :retrieval-config="currentCollection.retrieval_config" />
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
            <el-table-column prop="name" label="知识库名称" min-width="160" />
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
            <el-table-column label="操作" width="260" fixed="right">
              <template #default="{ row }">
                <el-button type="primary" size="small" plain @click="enterCollection(row)">管理</el-button>
                <el-button type="warning" size="small" plain style="margin-left:4px" @click="openRetrievalDialog(row)">配置</el-button>
                <el-button type="warning" size="small" plain style="margin-left:4px" @click="openKnowledgeGraph(row)">知识图谱</el-button>
                <el-popconfirm
                  :title="`确认删除知识库「${row.name}」？`"
                  confirm-button-text="删除" cancel-button-text="取消"
                  confirm-button-type="danger"
                  @confirm="deleteCollection(row.name)"
                >
                  <template #reference>
                    <el-button type="danger" size="small" plain style="margin-left:4px">删除</el-button>
                  </template>
                </el-popconfirm>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <!-- 检索配置 dialog -->
        <el-dialog v-model="retrievalDialogVisible" :title="`检索配置 — ${retrievalTarget?.name}`" width="520px" destroy-on-close>
          <el-form :model="retrievalForm" label-width="160px">

            <el-divider content-position="left">混合检索</el-divider>
            <el-form-item label="融合策略">
              <el-radio-group v-model="retrievalForm.ranker">
                <el-radio value="RRF">RRF（推荐）</el-radio>
                <el-radio value="Weight">Weighted</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item v-if="retrievalForm.ranker === 'Weight'" label="Dense 权重 (α)">
              <el-slider v-model="retrievalForm.hybrid_alpha" :min="0" :max="1" :step="0.05"
                show-input :input-size="'small'" style="width:280px" />
              <div class="tip">Sparse 权重 = 1 - α</div>
            </el-form-item>

            <el-divider content-position="left">检索数量</el-divider>
            <el-form-item label="多文档：文档数">
              <el-input-number v-model="retrievalForm.multi_doc_top_k" :min="1" :max="500" style="width:120px" />
              <div class="tip">{{ retrievalForm.rerank_enabled ? '作为 Rerank 候选池，建议 ≥ 50' : '最多返回多少个不同文档的结果' }}</div>
            </el-form-item>
            <el-form-item label="多文档：每文档 Chunk">
              <el-input-number v-model="retrievalForm.multi_doc_group_size" :min="1" :max="20" style="width:120px" />
              <div class="tip">每个文档最多取几个最相关 chunk</div>
            </el-form-item>
            <el-form-item label="单文档：Chunk 数">
              <el-input-number v-model="retrievalForm.single_doc_top_k" :min="1" :max="500" style="width:120px" />
              <div class="tip">{{ retrievalForm.rerank_enabled ? '作为 Rerank 候选池，建议 ≥ 30' : '检索返回的 chunk 数量' }}</div>
            </el-form-item>
            <el-form-item label="严格 Chunk 数">
              <el-switch v-model="retrievalForm.strict_group_size" active-text="开启" inactive-text="关闭" />
              <div class="tip">强制凑满每文档 chunk 数，通常无需开启</div>
            </el-form-item>

            <el-divider content-position="left">生成</el-divider>
            <el-form-item label="启用 Rerank">
              <el-switch v-model="retrievalForm.rerank_enabled" active-text="开启" inactive-text="关闭" />
              <div class="tip">用 qwen3-rerank 重排候选切片，提升精度，增加约 1-2s 延迟</div>
            </el-form-item>
            <el-form-item v-if="!retrievalForm.rerank_enabled" label="送给 LLM 的切片数">
              <el-input-number v-model="retrievalForm.llm_context_top_k" :min="1" :max="50" style="width:120px" />
              <div class="tip">按检索分数取 top-N 送入 LLM，默认 10</div>
            </el-form-item>
            <template v-if="retrievalForm.rerank_enabled">
              <el-form-item label="单文档 Top-K">
                <el-input-number v-model="retrievalForm.single_doc_rerank_top_k" :min="1" :max="50" style="width:120px" />
                <div class="tip">Rerank 后送入 LLM 的切片数</div>
              </el-form-item>
              <el-form-item label="多文档 Top-K">
                <el-input-number v-model="retrievalForm.multi_doc_rerank_top_k" :min="1" :max="50" style="width:120px" />
                <div class="tip">Rerank 后送入 LLM 的切片数</div>
              </el-form-item>
            </template>
            <el-form-item label="对话记忆轮数">
              <el-input-number v-model="retrievalForm.memory_turns" :min="1" :max="10" style="width:120px" />
              <div class="tip">保留最近 N 轮历史用于查询改写，默认 2</div>
            </el-form-item>

          </el-form>
          <template #footer>
            <el-button @click="retrievalDialogVisible = false">取消</el-button>
            <el-button type="primary" @click="saveRetrievalConfig" :loading="retrievalSaving">保存</el-button>
          </template>
        </el-dialog>
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
            <template v-if="colForm.kb_type === 'standard'">
              <el-form-item label="Embedding 模型">
                <el-select v-model="colForm.embedding_model" @change="onModelChange" style="width:320px">
                  <el-option label="text-embedding-v3（支持自定义维度）" value="text-embedding-v3" />
                  <el-option label="text-embedding-v4（支持 1536 / 2048 维）" value="text-embedding-v4" />
                </el-select>
              </el-form-item>
              <el-form-item label="向量维度">
                <el-select v-model="colForm.dimension" style="width:200px">
                  <el-option v-for="d in availableDims" :key="d" :label="`${d} 维`" :value="d" />
                </el-select>
                <span class="tip" style="margin-left:8px">{{ dimTip }}</span>
              </el-form-item>
            </template>
            <template v-else>
              <el-form-item label="Embedding 模型">
                <el-tag type="success">qwen3-vl-embedding（自动）</el-tag>
                <div class="tip">多模态知识库固定使用 qwen3-vl-embedding，文字和图片在同一语义空间</div>
              </el-form-item>
              <el-form-item label="向量维度">
                <el-select v-model="colForm.retrieval_config.image_vector_dim" style="width:200px">
                  <el-option v-for="d in [256,512,768,1024,1536,2048,2560]" :key="d" :label="`${d} 维`" :value="d" />
                </el-select>
                <div class="tip">文本和图片向量统一使用此维度，推荐 1024</div>
              </el-form-item>
            </template>
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
            <el-form-item label="知识库类型">
              <el-radio-group v-model="colForm.kb_type">
                <el-radio value="standard">标准（文本检索）</el-radio>
                <el-radio value="multimodal">多模态（文本 + 图片联合检索）</el-radio>
              </el-radio-group>
              <div class="tip">多模态使用 qwen3-vl-embedding，文字和图片在同一语义空间，支持以文搜图</div>
            </el-form-item>
            <el-form-item label="启用图文模式">
              <el-switch v-model="colForm.image_mode" active-text="开启" inactive-text="关闭" />
              <div class="tip">开启后上传文件将使用自定义 PDF 解析，提取图片并与切片关联，回答时可展示图片</div>
            </el-form-item>

            <el-divider content-position="left">检索配置</el-divider>
            <el-form-item label="融合策略">
              <el-radio-group v-model="colForm.retrieval_config.ranker">
                <el-radio value="RRF">RRF（推荐）</el-radio>
                <el-radio value="Weight">Weighted</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item v-if="colForm.retrieval_config.ranker === 'Weight'" label="Dense 权重 (α)">
              <el-slider v-model="colForm.retrieval_config.hybrid_alpha" :min="0" :max="1" :step="0.05"
                show-input :input-size="'small'" style="width:280px" />
              <div class="tip">Sparse 权重 = 1 - α</div>
            </el-form-item>
            <el-form-item label="多文档：文档数">
              <el-input-number v-model="colForm.retrieval_config.multi_doc_top_k" :min="1" :max="500" style="width:120px" />
              <div class="tip">{{ colForm.retrieval_config.rerank_enabled ? '作为 Rerank 候选池，建议 ≥ 50' : '最多返回多少个不同文档的结果' }}</div>
            </el-form-item>
            <el-form-item label="多文档：每文档 Chunk">
              <el-input-number v-model="colForm.retrieval_config.multi_doc_group_size" :min="1" :max="20" style="width:120px" />
            </el-form-item>
            <el-form-item label="单文档：Chunk 数">
              <el-input-number v-model="colForm.retrieval_config.single_doc_top_k" :min="1" :max="500" style="width:120px" />
              <div class="tip">{{ colForm.retrieval_config.rerank_enabled ? '作为 Rerank 候选池，建议 ≥ 30' : '检索返回的 chunk 数量' }}</div>
            </el-form-item>
            <el-divider content-position="left">生成</el-divider>
            <el-form-item label="启用 Rerank">
              <el-switch v-model="colForm.retrieval_config.rerank_enabled" active-text="开启" inactive-text="关闭" />
              <div class="tip">用 qwen3-rerank 重排候选切片，提升精度，增加约 1-2s 延迟</div>
            </el-form-item>
            <el-form-item v-if="!colForm.retrieval_config.rerank_enabled" label="送给 LLM 的切片数">
              <el-input-number v-model="colForm.retrieval_config.llm_context_top_k" :min="1" :max="50" style="width:120px" />
              <div class="tip">按检索分数取 top-N 送入 LLM，默认 10</div>
            </el-form-item>
            <template v-if="colForm.retrieval_config.rerank_enabled">
              <el-form-item label="单文档 Top-K">
                <el-input-number v-model="colForm.retrieval_config.single_doc_rerank_top_k" :min="1" :max="50" style="width:120px" />
                <div class="tip">Rerank 后送入 LLM 的切片数</div>
              </el-form-item>
              <el-form-item label="多文档 Top-K">
                <el-input-number v-model="colForm.retrieval_config.multi_doc_rerank_top_k" :min="1" :max="50" style="width:120px" />
                <div class="tip">Rerank 后送入 LLM 的切片数</div>
              </el-form-item>
            </template>

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
import { ref, reactive, watch, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowLeft } from '@element-plus/icons-vue'
import axios from 'axios'
import DocUpload from './doc/DocUpload.vue'
import DocList from './doc/DocList.vue'
import DocSearch from './doc/DocSearch.vue'
import DocJobList from './doc/DocJobList.vue'
import ChunkEditorPanel from './doc/ChunkEditorPanel.vue'
import KnowledgeGraphPanel from './doc/KnowledgeGraphPanel.vue'

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

// 知识图谱视图
const graphKbName = ref('')

const enterCollection = (row) => { currentCollection.value = row }
const onChunksFetched = (job) => { openChunkEditor(job.job_id) }
const openChunkEditor = (jobId, readonly = false) => {
  currentJobId.value = jobId
  chunkEditorReadonly.value = readonly
  chunkEditorVisible.value = true
}
const onVectorized = () => { docListRef.value?.load() }
const openKnowledgeGraph = (row) => {
  graphKbName.value = row.name
}

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
    const { data } = await axios.get(`${API}/admin/collections`)
    if (data.success) collections.value = data.data.collections || []
  } catch (e) {
    ElMessage.error('查询失败: ' + (e.response?.data?.detail || e.message))
  } finally { colListLoading.value = false }
}

const deleteCollection = async (collectionName) => {
  try {
    await axios.delete(`${API}/admin/collections/${collectionName}`)
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
  embedding_model: 'text-embedding-v3', dimension: 1024, metrics: 'cosine',
  hnsw_m: null, hnsw_ef_construction: null,
  pq_enable_bool: false, external_storage_bool: false,
  image_mode: false,
  kb_type: 'standard',
  retrieval_config: {
    ranker: 'RRF',
    hybrid_alpha: 0.5,
    multi_doc_top_k: 20,
    multi_doc_group_size: 3,
    strict_group_size: false,
    single_doc_top_k: 20,
    llm_context_top_k: 10,
    image_vector_dim: 1024,
    memory_turns: 2,
    rerank_enabled: false,
    rerank_model_name: 'qwen3-rerank',
    single_doc_rerank_top_k: 5,
    multi_doc_rerank_top_k: 10,
  },
})
const colForm = ref(defaultColForm())

const MODEL_DIMS = {
  'text-embedding-v3': [1024, 768, 512, 256, 128, 64],
  'text-embedding-v4': [1536, 2048],
}

const availableDims = computed(() => MODEL_DIMS[colForm.value.embedding_model] || [1024])
const dimTip = computed(() =>
  colForm.value.embedding_model === 'text-embedding-v4'
    ? '仅支持 1536 / 2048 维'
    : '支持自定义维度：1024 / 768 / 512 / 256 / 128 / 64'
)

const onModelChange = (val) => {
  const dims = MODEL_DIMS[val] || [1024]
  colForm.value.dimension = dims[0]
}

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
      name: colForm.value.collection,
      display_name: colForm.value.collection,
      image_mode: colForm.value.image_mode,
      kb_type: colForm.value.kb_type,
      embedding_model: colForm.value.embedding_model || 'text-embedding-v3',
      vector_dim: colForm.value.dimension || 1024,
      metadata_fields: enabledFields,
      retrieval_config: colForm.value.retrieval_config,
    }
    const { data } = await axios.post(`${API}/admin/collections`, payload)
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

// ── 检索配置 dialog ───────────────────────────────────────────────────────────
const retrievalDialogVisible = ref(false)
const retrievalTarget = ref(null)
const retrievalSaving = ref(false)
const defaultRetrievalForm = () => ({
  ranker: 'RRF', hybrid_alpha: 0.5,
  multi_doc_top_k: 20, multi_doc_group_size: 3, strict_group_size: false,
  single_doc_top_k: 20, llm_context_top_k: 10, memory_turns: 2,
  rerank_enabled: false, rerank_model_name: 'qwen3-rerank',
  single_doc_rerank_top_k: 5, multi_doc_rerank_top_k: 10,
})
const retrievalForm = ref(defaultRetrievalForm())

const openRetrievalDialog = (row) => {
  retrievalTarget.value = row
  const rc = row.retrieval_config || {}
  retrievalForm.value = {
    ranker:                rc.ranker               ?? 'RRF',
    hybrid_alpha:          rc.hybrid_alpha          ?? 0.5,
    multi_doc_top_k:       rc.multi_doc_top_k       ?? 20,
    multi_doc_group_size:  rc.multi_doc_group_size  ?? 3,
    strict_group_size:     rc.strict_group_size     ?? false,
    single_doc_top_k:      rc.single_doc_top_k      ?? 20,
    llm_context_top_k:     rc.llm_context_top_k     ?? 10,
    memory_turns:          rc.memory_turns          ?? 2,
    rerank_enabled:        rc.rerank_enabled        ?? false,
    rerank_model_name:     rc.rerank_model_name     ?? 'qwen3-rerank',
    single_doc_rerank_top_k: rc.single_doc_rerank_top_k ?? 5,
    multi_doc_rerank_top_k:  rc.multi_doc_rerank_top_k  ?? 10,
  }
  retrievalDialogVisible.value = true
}

const saveRetrievalConfig = async () => {
  retrievalSaving.value = true
  try {
    const { data } = await axios.put(`${API}/admin/collections/${retrievalTarget.value.name}`, {
      retrieval_config: retrievalForm.value,
    })
    if (data.success) {
      ElMessage.success('检索配置已保存')
      retrievalDialogVisible.value = false
      await loadCollections()
    }
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message))
  } finally { retrievalSaving.value = false }
}

onMounted(async () => {
  await loadConfig()
  await loadCollections()
})
</script>

<style scoped>
.admin-panel { padding: 0; max-width: 1200px; margin: 0 auto; }
.admin-tabs { margin-top: 0; }
.preset-fields { display: flex; flex-direction: column; gap: 10px; }
.preset-row { display: flex; align-items: center; padding: 10px 14px; border-radius: 8px; }
:deep(.el-divider__text) { font-weight: 600; }
</style>
