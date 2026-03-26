<template>
  <el-dialog v-model="visible" title="上传任务" width="900px" @open="load">
    <div style="margin-bottom:12px;text-align:right">
      <el-button size="small" @click="load" :loading="loading">刷新</el-button>
    </div>

    <el-table :data="jobs" v-loading="loading" max-height="460" style="width:100%">
      <el-table-column prop="file_name" label="文件名" min-width="200" show-overflow-tooltip />
      <el-table-column prop="job_id" label="Job ID" min-width="220" show-overflow-tooltip />
      <el-table-column prop="splitting_method" label="切分方式" width="90" align="center" />
      <el-table-column label="状态" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)">{{ row.status || 'queued' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="170" show-overflow-tooltip />
      <el-table-column label="操作" width="220" align="center">
        <template #default="{ row }">
          <el-button size="small" link type="primary" @click="refresh(row)">刷新</el-button>
          <el-button
            size="small" link type="success"
            :disabled="!isCompleted(row.status)"
            @click="fetchChunks(row)"
            :loading="row._fetching"
          >
            获取切片
          </el-button>
          <el-button
            size="small" link type="danger"
            :disabled="!canCancel(row)"
            @click="cancel(row)"
          >
            取消
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { docApi } from '@/services/docApi'

const props = defineProps({ modelValue: Boolean })
const emit = defineEmits(['update:modelValue', 'chunks-fetched'])

const visible = ref(props.modelValue)
watch(() => props.modelValue, v => { visible.value = v })
watch(visible, v => emit('update:modelValue', v))

const jobs = ref([])
const loading = ref(false)
let pollTimer = null

// ADB 原生终态：Success
const isCompleted = (s) => (s || '').toLowerCase() === 'success'

watch(visible, (v) => {
  if (v) { load(); startPoll() }
  else stopPoll()
})

const load = async () => {
  loading.value = true
  try {
    const res = await docApi.listJobs()
    const newJobs = (res.data.data.jobs || []).map(j => ({ ...j, _fetching: false }))

    // 自动 fetch-chunks：刚变成 Success 且本地还没有切片的 job
    for (const j of newJobs) {
      const old = jobs.value.find(o => o.job_id === j.job_id)
      if (isCompleted(j.status) && (!old || !isCompleted(old.status))) {
        autoFetchChunks(j)
      }
    }
    jobs.value = newJobs
  } catch (e) {
    ElMessage.error('加载任务失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

const autoFetchChunks = async (job) => {
  try {
    await docApi.fetchChunks(job.job_id)
    emit('chunks-fetched', job)
  } catch {
    // 静默失败，用户可手动点
  }
}

const refresh = async (job) => {
  try {
    const res = await docApi.getJob(job.job_id)
    const updated = res.data.data.job
    const idx = jobs.value.findIndex(j => j.job_id === job.job_id)
    if (idx >= 0) jobs.value[idx] = { ...jobs.value[idx], ...updated }
    ElMessage.success('已刷新')
  } catch (e) {
    ElMessage.error('刷新失败: ' + (e.response?.data?.detail || e.message))
  }
}

const fetchChunks = async (job) => {
  job._fetching = true
  try {
    const res = await docApi.fetchChunks(job.job_id)
    ElMessage.success(res.data.message || '切片已获取并保存')
    emit('chunks-fetched', job)
    visible.value = false
  } catch (e) {
    const detail = e.response?.data?.detail || e.message
    ElMessage.error({ message: '获取切片失败: ' + detail, duration: 6000 })
  } finally {
    job._fetching = false
  }
}

const cancel = async (job) => {
  try {
    await docApi.cancelJob(job.job_id)
    ElMessage.success('已取消')
    await load()
  } catch (e) {
    ElMessage.error('取消失败: ' + (e.response?.data?.detail || e.message))
  }
}

// ADB 返回 'Success'，本地归一化后可能是 'completed'，两种都要兼容
const canCancel = (job) => ['queued', 'running', 'start', 'pending'].includes((job.status || '').toLowerCase())
const statusType = (s) => {
  const lower = (s || '').toLowerCase()
  if (lower === 'success') return 'success'
  if (['failed', 'error'].includes(lower)) return 'danger'
  if (['running', 'start', 'pending'].includes(lower)) return 'warning'
  return 'info'
}

const startPoll = () => {
  if (pollTimer) return
  pollTimer = setInterval(load, 5000)
}
const stopPoll = () => {
  if (!pollTimer) return
  clearInterval(pollTimer)
  pollTimer = null
}
</script>
