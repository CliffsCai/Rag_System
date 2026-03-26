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
          <el-form-item label="Rerank因子">
            <el-input-number v-model="form.rerankFactor" :min="0" :max="10" :step="0.5"
              :precision="1" style="width:100%"
              placeholder="不填=不重排" />
            <div style="font-size:11px;color:#909399">留0=不重排，需>1且topK×因子≤1000</div>
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :span="18">
          <el-form-item label="过滤条件">
            <el-input v-model="form.filter" placeholder="SQL WHERE 格式，如: title = 'test'（可选）" clearable />
          </el-form-item>
        </el-col>
        <el-col :span="6">
          <el-form-item label="返回文件URL">
            <el-switch v-model="form.includeFileUrl" />
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
              <pre style="white-space:pre-wrap;background:#f5f7fa;padding:12px;border-radius:4px;font-size:13px;line-height:1.6">{{ row.content }}</pre>
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
            <span style="font-size:13px">{{ row.content?.substring(0, 120) }}{{ row.content?.length > 120 ? '…' : '' }}</span>
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
  collection: { type: String, default: '' }
})

const defaultForm = () => ({
  query: '',
  topK: 10,
  hybridSearch: 'Weight',
  hybridAlpha: 0.5,
  rerankFactor: 0,   // 0 表示不重排
  filter: '',
  includeFileUrl: false,
})

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
    const payload = {
      query: form.value.query,
      top_k: form.value.topK,
      hybrid_search: form.value.hybridSearch || null,
      hybrid_alpha: form.value.hybridAlpha,
      rerank_factor: form.value.rerankFactor > 1 ? form.value.rerankFactor : null,
      filter: form.value.filter || null,
      include_file_url: form.value.includeFileUrl,
      collection: props.collection || null,
    }
    const res = await docApi.searchDocuments(payload)
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
</script>

<style scoped>
.card-header { display:flex; justify-content:space-between; align-items:center; font-weight:600; }
</style>
