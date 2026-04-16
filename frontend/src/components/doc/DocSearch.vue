<template>
  <el-card shadow="hover">
    <template #header>
      <div class="card-header">
        <span>🔍 知识库命中测试</span>
        <el-tag type="success" size="small">QueryContent</el-tag>
      </div>
    </template>

    <!-- 参数配置 -->
    <el-form :model="form" label-width="110px" style="margin-bottom:8px">
      <el-row :gutter="16">
        <el-col :span="24">
          <el-form-item label="查询内容" required>
            <el-input v-model="form.query" placeholder="输入检索文本..." clearable
              @keyup.enter="search" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :span="6">
          <el-form-item label="TopK">
            <el-input-number v-model="form.topK" :min="1" :max="200" style="width:100%" />
          </el-form-item>
        </el-col>
        <el-col :span="6">
          <el-form-item label="混合检索">
            <el-select v-model="form.hybridSearch" style="width:100%">
              <el-option label="Weight（加权）" value="Weight" />
              <el-option label="RRF（倒数排序）" value="RRF" />
              <el-option label="Cascaded（级联）" value="Cascaded" />
              <el-option label="不使用" value="" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="6" v-if="form.hybridSearch === 'Weight'">
          <el-form-item label="向量权重α">
            <el-input-number v-model="form.hybridAlpha" :min="0" :max="1" :step="0.1"
              :precision="1" style="width:100%" />
          </el-form-item>
        </el-col>
        <el-col :span="6">
          <el-form-item label="Rerank">
            <el-switch v-model="form.rerank" active-text="开启" inactive-text="关闭" />
          </el-form-item>
        </el-col>
        <el-col :span="6" v-if="form.rerank">
          <el-form-item label="Rerank Top-N">
            <el-input-number v-model="form.rerankTopN" :min="1" :max="200" style="width:100%" />
            <div style="font-size:11px;color:#909399">留空=返回全部重排结果</div>
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="关键词预过滤">
            <el-input v-model="form.keywordFilter"
              placeholder="倒排索引精确匹配，多词空格分隔（可选）" clearable />
            <div style="font-size:11px;color:#909399">填写后先 TEXT_MATCH 过滤，再双路 ANN 检索</div>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="标量过滤">
            <el-input v-model="form.filter" placeholder="SQL WHERE 格式，如: file_name == 'test.pdf'（可选）" clearable />
          </el-form-item>
        </el-col>
      </el-row>

      <el-row>
        <el-col :span="24" style="text-align:right">
          <el-button @click="reset">重置</el-button>
          <el-button type="primary" @click="search" :loading="searching" :disabled="!form.query">
            开始检索
          </el-button>
        </el-col>
      </el-row>
    </el-form>

    <!-- 结果 -->
    <template v-if="results.length > 0">
      <el-divider>
        <el-tag type="success">命中 {{ results.length }} 条</el-tag>
      </el-divider>

      <el-table :data="results" style="width:100%" max-height="560" stripe border>
        <el-table-column type="expand">
          <template #default="{ row }">
            <div style="padding:16px 24px">
              <div style="font-weight:600;margin-bottom:6px">完整内容</div>
              <div
                v-html="renderContent(row.content, row.image_map)"
                style="background:#0d1117;border:1px solid rgba(255,255,255,0.08);padding:12px;border-radius:8px;font-size:13px;line-height:1.6;color:#cbd5e1;white-space:pre-wrap;word-break:break-all"
              />
              <div v-if="row.metadata" style="margin-top:8px;font-size:12px;color:#606266">
                <span style="font-weight:600">元数据：</span>{{ JSON.stringify(row.metadata) }}
              </div>
              <div v-if="row.loader_metadata" style="margin-top:4px;font-size:12px;color:#909399">
                <span style="font-weight:600">加载元数据：</span>{{ row.loader_metadata }}
              </div>
              <div v-if="row.file_url" style="margin-top:4px">
                <a :href="row.file_url" target="_blank" style="font-size:12px">文件链接</a>
              </div>
            </div>
          </template>
        </el-table-column>

        <el-table-column type="index" label="#" width="50" align="center" />
        <el-table-column prop="file_name" label="文件名" width="180" show-overflow-tooltip />
        <el-table-column label="内容预览" min-width="280" show-overflow-tooltip>
          <template #default="{ row }">
            <span style="font-size:13px">{{ stripPlaceholders(row.content)?.substring(0, 120) }}{{ stripPlaceholders(row.content)?.length > 120 ? '…' : '' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="90" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="sourceType(row.retrieval_source)">
              {{ sourceLabel(row.retrieval_source) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="相似度" width="100" align="center">
          <template #default="{ row }">
            <span style="font-size:13px;color:#409eff">{{ row.score != null ? row.score.toFixed(4) : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="Rerank分" width="100" align="center">
          <template #default="{ row }">
            <span v-if="row.rerank_score != null" style="font-size:13px;color:#67c23a;font-weight:600">
              {{ row.rerank_score.toFixed(4) }}
            </span>
            <span v-else style="color:#c0c4cc">-</span>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <el-empty v-else-if="!searching && searched" description="未命中任何结果" />
  </el-card>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { docApi } from '@/services/docApi'

const props = defineProps({
  collection: { type: String, default: '' },
  retrievalConfig: { type: Object, default: () => ({}) },
})

const defaultForm = () => {
  const rc = props.retrievalConfig || {}
  return {
    query: '',
    topK: rc.rerank_enabled
      ? (rc.multi_doc_top_k ?? 20)   // rerank 开启时默认用多文档候选数
      : (rc.llm_context_top_k ?? 10),
    hybridSearch: rc.ranker ?? 'RRF',
    hybridAlpha: rc.hybrid_alpha ?? 0.5,
    rerank: rc.rerank_enabled ?? false,
    rerankTopN: rc.multi_doc_rerank_top_k ?? 10,
    keywordFilter: '',
    filter: '',
  }
}

const form = ref(defaultForm())
const results = ref([])
const searching = ref(false)
const searched = ref(false)

  const search = async () => {
  if (!form.value.query.trim()) return
  searching.value = true
  searched.value = false
  results.value = []
  try {
    const fd = new FormData()
    fd.append('query', form.value.query)
    fd.append('collection', props.collection || '')
    fd.append('top_k', form.value.topK)
    fd.append('hybrid_search', form.value.hybridSearch || 'RRF')
    fd.append('hybrid_alpha', form.value.hybridAlpha)
    if (form.value.rerank) {
      fd.append('rerank', 'true')
      fd.append('rerank_top_n', form.value.rerankTopN)
    }
    if (form.value.keywordFilter) fd.append('keyword_filter', form.value.keywordFilter)
    if (form.value.filter) fd.append('filter_expr', form.value.filter)

    const res = await docApi.searchDocuments(fd)
    results.value = res.data.data.results || []
    searched.value = true
    ElMessage.success(`命中 ${results.value.length} 条结果`)
  } catch (e) {
    ElMessage.error('检索失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    searching.value = false
  }
}

const reset = () => {
  form.value = defaultForm()
  results.value = []
  searched.value = false
}

const sourceLabel = (s) => ({ 1: '向量', 2: '全文', 3: '双路' }[s] || '-')
const sourceType = (s) => ({ 1: 'primary', 2: 'warning', 3: 'success' }[s] || 'info')

const _PH_RE = /<<IMAGE:[0-9a-f]+>>/g

/** 预览列：去掉占位符，避免显示 <<IMAGE:xxx>> */
const stripPlaceholders = (content) => (content || '').replace(_PH_RE, '')

/** 展开行：把占位符替换成 <img>，其余文字做 HTML 转义 */
const escapeHtml = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
const renderContent = (content, imageMap) => {
  if (!content) return ''
  const map = imageMap || {}
  // 按占位符分割，逐段处理
  const parts = content.split(_PH_RE)
  const placeholders = [...content.matchAll(_PH_RE)].map(m => m[0])
  let html = ''
  parts.forEach((part, i) => {
    html += escapeHtml(part)
    if (i < placeholders.length) {
      const ph = placeholders[i]
      const url = map[ph]
      html += url
        ? `<img src="${url}" style="max-width:100%;border-radius:4px;margin:4px 0;display:block" />`
        : `<span style="color:#909399;font-size:12px">[图片]</span>`
    }
  })
  return html
}
</script>

<style scoped>
</style>
