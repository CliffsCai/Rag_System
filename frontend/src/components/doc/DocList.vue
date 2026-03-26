<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
      <el-radio-group v-model="activeTab" size="small">
        <el-radio-button value="pending">
          待向量化
          <el-badge :value="pendingFiles.length" :max="99" type="warning" style="margin-left:4px" />
        </el-radio-button>
        <el-radio-button value="vectorized">
          已向量化
          <el-badge :value="vectorizedFiles.length" :max="99" type="success" style="margin-left:4px" />
        </el-radio-button>
      </el-radio-group>
      <div style="display:flex;gap:8px">
        <template v-if="activeTab === 'pending'">
          <el-button
            v-if="selectedJobIds.length > 0"
            size="small" type="success"
            :loading="upserting"
            @click="batchUpsert(selectedJobIds)"
          >⬆️ 上传选中 ({{ selectedJobIds.length }})</el-button>
          <el-button
            size="small" type="success" plain
            :loading="upserting"
            :disabled="uploadableJobIds.length === 0"
            @click="batchUpsert(uploadableJobIds)"
          >⬆️ 一键全部上传 ({{ uploadableJobIds.length }})</el-button>
        </template>
        <el-button
          v-if="selectedJobIds.length > 0"
          size="small" type="danger"
          :loading="batchDeleting"
          @click="batchDelete"
        >🗑️ 批量删除 ({{ selectedJobIds.length }})</el-button>
        <el-button size="small" type="primary" @click="load" :loading="loading">刷新</el-button>
      </div>
    </div>

    <el-table
      :data="activeTab === 'pending' ? pendingFiles : vectorizedFiles"
      v-loading="loading"
      style="width:100%"
      @selection-change="onSelectionChange"
    >
      <el-table-column type="selection" width="45" />
      <el-table-column prop="file_name" label="文件名" min-width="200" show-overflow-tooltip />
      <el-table-column label="切分状态" width="110" align="center">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="向量化" width="110" align="center">
        <template #default="{ row }">
          <el-tag
            :type="row.vectorized && (row.status || '').toLowerCase() === 'success' ? 'success' : row.vectorized ? 'warning' : 'info'"
            size="small"
          >
            {{ row.vectorized && (row.status || '').toLowerCase() === 'success' ? '已上传' : row.vectorized ? '向量化中' : '未上传' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="stage" label="阶段" width="90" align="center" show-overflow-tooltip />
      <el-table-column label="进度" width="70" align="center">
        <template #default="{ row }">
          <span v-if="row.process != null">{{ row.process }}%</span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="上传时间" width="155" show-overflow-tooltip />
      <el-table-column label="操作" width="160" align="center" fixed="right">
        <template #default="{ row }">
          <template v-if="row.vectorized && (row.status || '').toLowerCase() !== 'success'">
            <!-- 直接入库中：ADB 还在处理，置灰 -->
            <el-button size="small" type="primary" link disabled>向量化中...</el-button>
          </template>
          <template v-else>
            <el-button
              v-if="(row.status || '').toLowerCase() === 'success'"
              size="small"
              type="primary"
              link
              @click="viewChunks(row)"
            >
              查看切片
            </el-button>
            <el-popconfirm
              :title="`确认删除「${row.file_name}」？将同时清除切片和向量数据`"
              confirm-button-text="删除" cancel-button-text="取消"
              confirm-button-type="danger"
              @confirm="deleteFile(row)"
            >
              <template #reference>
                <el-button size="small" type="danger" link>删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-if="!loading && activeFiles.length === 0" description="暂无文件记录" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { docApi } from '@/services/docApi'

const emit = defineEmits(['view-chunks'])

const props = defineProps({
  collection: { type: String, default: '' }
})

const files = ref([])
const loading = ref(false)
const activeTab = ref('pending')
const selectedJobIds = ref([])
const batchDeleting = ref(false)
const upserting = ref(false)

// 可上传：status=Success 且未 vectorized
const uploadableJobIds = computed(() =>
  pendingFiles.value
    .filter(f => (f.status || '').toLowerCase() === 'success' && !f.vectorized)
    .map(f => f.job_id)
)

const pendingFiles = computed(() =>
  files.value.filter(f => !f.vectorized)
)
const vectorizedFiles = computed(() =>
  files.value.filter(f => f.vectorized)
)
const activeFiles = computed(() =>
  activeTab.value === 'pending' ? pendingFiles.value : vectorizedFiles.value
)

const statusType = (s) => {
  const lower = (s || '').toLowerCase()
  if (lower === 'success') return 'success'
  if (['failed', 'error'].includes(lower)) return 'danger'
  if (['running', 'start', 'pending'].includes(lower)) return 'warning'
  return 'info'
}

const statusLabel = (s) => ({
  Success: '已完成', Failed: '失败', Running: '处理中',
  Pending: '等待中', Start: '开始', Cancelled: '已取消', Cancelling: '取消中',
}[s] || s || '-')

const load = async () => {
  loading.value = true
  selectedJobIds.value = []
  try {
    const res = await docApi.listFiles({ collection: props.collection || '' })
    files.value = res.data.data.files || []
  } catch (e) {
    ElMessage.error('加载失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

const viewChunks = (row) => {
  emit('view-chunks', row.job_id, row.vectorized)
}

const onSelectionChange = (rows) => {
  selectedJobIds.value = rows.map(r => r.job_id)
}

const batchDelete = async () => {
  const count = selectedJobIds.value.length
  try {
    await ElMessageBox.confirm(
      `确认删除选中的 ${count} 个文件？将同时清除切片和向量数据。`,
      '批量删除确认',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )
  } catch { return }
  batchDeleting.value = true
  try {
    const res = await docApi.batchDeleteFiles(selectedJobIds.value, props.collection)
    ElMessage.success(res.data.message)
    await load()
  } catch (e) {
    ElMessage.error('批量删除失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    batchDeleting.value = false
  }
}

const batchUpsert = async (jobIds) => {
  if (!jobIds.length) return
  upserting.value = true
  try {
    const res = await docApi.batchUpsertJobs(jobIds)
    const { succeeded, failed } = res.data.data
    if (failed.length === 0) {
      ElMessage.success(`全部 ${succeeded.length} 个文件已上传到向量库`)
    } else {
      ElMessage.warning(`成功 ${succeeded.length} 个，失败 ${failed.length} 个`)
    }
    await load()
  } catch (e) {
    ElMessage.error('批量上传失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    upserting.value = false
  }
}

const deleteFile = async (row) => {
  try {
    await docApi.deleteFile(row.job_id, props.collection)
    ElMessage.success(`「${row.file_name}」已删除`)
    await load()
  } catch (e) {
    ElMessage.error('删除失败: ' + (e.response?.data?.detail || e.message))
  }
}

defineExpose({ load })
onMounted(load)
</script>

<style scoped>
:deep(.el-badge__content) { font-size: 10px; }
</style>
