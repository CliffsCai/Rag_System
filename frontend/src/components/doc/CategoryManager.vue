<template>
  <div>
    <!-- 类目列表 -->
    <el-card v-if="!currentCategory" shadow="hover">
      <template #header>
        <div class="card-header">
          <span>🗂️ 类目管理</span>
          <el-button size="small" type="primary" @click="openCreate">新建类目</el-button>
        </div>
      </template>

      <el-table :data="categories" v-loading="loading" style="width:100%">
        <el-table-column label="类目名称" min-width="180">
          <template #default="{ row }">
            <el-button link type="primary" @click="enterCategory(row)">{{ row.name }}</el-button>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="220" show-overflow-tooltip />
        <el-table-column prop="file_count" label="文件数" width="90" align="center" />
        <el-table-column prop="created_at" label="创建时间" width="170" show-overflow-tooltip />
        <el-table-column label="操作" width="120" align="center">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" link type="danger" @click="del(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!loading && categories.length === 0" description="暂无类目，点击右上角新建" />
    </el-card>

    <!-- 类目详情 -->
    <template v-else>
      <el-card shadow="hover" style="margin-bottom:16px">
        <template #header>
          <div class="card-header">
            <div style="display:flex;align-items:center;gap:8px">
              <el-button size="small" @click="currentCategory = null" :icon="ArrowLeft" circle />
              <span>🗂️ {{ currentCategory.name }}</span>
              <el-tag type="info" size="small" v-if="currentCategory.description">
                {{ currentCategory.description }}
              </el-tag>
            </div>
            <el-tag type="success" size="small">{{ files.length }} 个文件</el-tag>
          </div>
        </template>
      </el-card>

      <!-- 文件列表 -->
      <el-card shadow="hover">
        <template #header>
          <div class="card-header">
            <span>📄 文件列表</span>
            <div style="display:flex;gap:8px;align-items:center">
              <el-button
                v-if="selectedFileIds.length > 0"
                size="small"
                type="danger"
                :loading="deleting"
                @click="batchDelete"
              >🗑️ 删除所选 ({{ selectedFileIds.length }})</el-button>
              <el-button size="small" :loading="uploading" @click="triggerUpload">📤 上传文件</el-button>
              <el-button size="small" :loading="uploading" @click="triggerFolderUpload">📁 上传文件夹</el-button>
              <el-button size="small" :loading="syncing" @click="syncAllStatus">🔄 刷新状态</el-button>
            </div>
          </div>
        </template>

        <!-- 隐藏的文件选择器 -->
        <input
          ref="fileInputRef"
          type="file"
          style="display:none"
          multiple
          accept=".pdf,.doc,.docx,.txt,.md,.ppt,.pptx,.xlsx,.xls"
          @change="onFilesSelected"
        />
        <!-- 文件夹选择器 -->
        <input
          ref="folderInputRef"
          type="file"
          style="display:none"
          webkitdirectory
          multiple
          @change="onFilesSelected"
        />

        <el-table :data="files" v-loading="loadingFiles" style="width:100%" @selection-change="onSelectionChange">
          <el-table-column type="selection" width="45" />
          <el-table-column prop="file_name" label="文件名" min-width="220" show-overflow-tooltip />
          <el-table-column label="切片状态" width="120" align="center">
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)" size="small">{{ row.status || '-' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="job_id" label="Job ID" min-width="200" show-overflow-tooltip />
          <el-table-column prop="created_at" label="上传时间" width="170" show-overflow-tooltip />
          <el-table-column label="操作" width="80" align="center">
            <template #default="{ row }">
              <el-button size="small" link type="danger" @click="delFile(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <el-empty v-if="!loadingFiles && files.length === 0" description="该类目暂无文件" />
      </el-card>
    </template>

    <!-- 新建/编辑弹窗 -->
    <el-dialog v-model="formVisible" :title="editTarget ? '编辑类目' : '新建类目'" width="480px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="类目名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="可选描述" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" @click="save" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft } from '@element-plus/icons-vue'
import { docApi } from '@/services/docApi'

const categories = ref([])
const loading = ref(false)
const formVisible = ref(false)
const saving = ref(false)
const editTarget = ref(null)
const form = ref({ name: '', description: '' })

// 详情视图
const currentCategory = ref(null)
const files = ref([])
const loadingFiles = ref(false)
const syncing = ref(false)
const uploading = ref(false)
const deleting = ref(false)
const selectedFileIds = ref([])
const fileInputRef = ref(null)
const folderInputRef = ref(null)
let pollTimer = null

const loadCollections = async () => {}  // 已移至知识库详情页

const load = async () => {
  loading.value = true
  try {
    const res = await docApi.listCategories()
    categories.value = res.data.data.categories || []
  } catch (e) {
    ElMessage.error('加载类目失败')
  } finally {
    loading.value = false
  }
}

const enterCategory = async (row) => {
  currentCategory.value = row
  files.value = []
  selectedFileIds.value = []
  stopPolling()
  await loadFiles()
  syncAllStatus()
}

const loadFiles = async () => {
  if (!currentCategory.value) return
  loadingFiles.value = true
  try {
    const res = await docApi.getCategory(currentCategory.value.category_id)
    files.value = res.data.data.files || []
  } catch (e) {
    ElMessage.error('加载文件失败')
  } finally {
    loadingFiles.value = false
  }
}

const syncAllStatus = async () => {
  await loadFiles()
}

const onSelectionChange = (rows) => {
  selectedFileIds.value = rows.map(r => r.id)
}

const batchDelete = async () => {
  const count = selectedFileIds.value.length
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${count} 个文件吗？此操作将同时删除 OSS 上的原始文件。`, '批量删除确认', {
      confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning'
    })
  } catch { return }
  deleting.value = true
  try {
    const res = await docApi.batchDeleteCategoryFiles(currentCategory.value.category_id, selectedFileIds.value)
    ElMessage.success(res.data.message)
    selectedFileIds.value = []
    await loadFiles()
  } catch (e) {
    ElMessage.error('批量删除失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    deleting.value = false
  }
}

const triggerUpload = () => {
  fileInputRef.value?.click()
}

const triggerFolderUpload = () => {
  folderInputRef.value?.click()
}

const onFilesSelected = async (e) => {
  const fileList = Array.from(e.target.files || [])
  e.target.value = ''
  if (!fileList.length) return

  // 单文件走原有接口，多文件走批量接口
  if (fileList.length === 1) {
    uploading.value = true
    try {
      const fd = new FormData()
      fd.append('file', fileList[0])
      fd.append('category_id', currentCategory.value.category_id)
      await docApi.uploadDocumentToCategory(fd)
      ElMessage.success(`${fileList[0].name} 已上传`)
      await loadFiles()
    } catch (err) {
      ElMessage.error('上传失败: ' + (err.response?.data?.detail || err.message))
    } finally {
      uploading.value = false
    }
    return
  }

  // 多文件批量上传
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('category_id', currentCategory.value.category_id)
    for (const f of fileList) {
      // 文件夹上传时 f.name 可能含路径，只取最后的文件名
      const baseName = f.name.split('/').pop().split('\\').pop()
      const renamed = new File([f], baseName, { type: f.type })
      fd.append('files', renamed)
    }
    const res = await docApi.batchUploadToCategory(fd)
    const { succeeded, failed, total } = res.data.data
    if (failed.length === 0) {
      ElMessage.success(`全部 ${total} 个文件上传成功`)
    } else {
      ElMessage.warning(`成功 ${succeeded.length} 个，失败 ${failed.length} 个：${failed.map(f => f.file_name).join('、')}`)
    }
    await loadFiles()
  } catch (err) {
    ElMessage.error('批量上传失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    uploading.value = false
  }
}

const startChunking = async () => {}  // 已移至知识库详情页

const startPolling = () => {
  stopPolling()
  pollTimer = setInterval(async () => {
    if (!currentCategory.value) { stopPolling(); return }
    try {
      await loadFiles()
      const terminal = ['success', 'failed', 'cancelled']
      const allDone = files.value.every(f => terminal.includes((f.status || '').toLowerCase()))
      if (allDone) stopPolling()
    } catch (_) {}
  }, 5000)
}

const stopPolling = () => {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

const openCreate = () => {
  editTarget.value = null
  form.value = { name: '', description: '' }
  formVisible.value = true
}

const openEdit = (row) => {
  editTarget.value = row
  form.value = { name: row.name, description: row.description || '' }
  formVisible.value = true
}

const save = async () => {
  if (!form.value.name.trim()) {
    ElMessage.warning('请输入类目名称')
    return
  }
  saving.value = true
  try {
    if (editTarget.value) {
      await docApi.updateCategory(editTarget.value.category_id, form.value)
      ElMessage.success('更新成功')
    } else {
      await docApi.createCategory(form.value)
      ElMessage.success('创建成功')
    }
    formVisible.value = false
    await load()
  } catch (e) {
    ElMessage.error('操作失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    saving.value = false
  }
}

const del = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除类目 "${row.name}" 吗？`, '删除确认', {
      confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning'
    })
  } catch { return }
  try {
    await docApi.deleteCategory(row.category_id)
    ElMessage.success('删除成功')
    await load()
  } catch (e) {
    ElMessage.error('删除失败: ' + (e.response?.data?.detail || e.message))
  }
}

const delFile = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除文件 "${row.file_name}" 吗？此操作将同时删除 OSS 上的原始文件。`, '删除确认', {
      confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning'
    })
  } catch { return }
  try {
    await docApi.deleteCategoryFile(currentCategory.value.category_id, row.id)
    ElMessage.success(`文件「${row.file_name}」已删除`)
    await loadFiles()
  } catch (e) {
    ElMessage.error('删除失败: ' + (e.response?.data?.detail || e.message))
  }
}

const statusType = (s) => {
  const lower = (s || '').toLowerCase()
  if (lower === 'success') return 'success'
  if (['failed', 'error'].includes(lower)) return 'danger'
  if (['running', 'start', 'pending'].includes(lower)) return 'warning'
  return 'info'
}

onMounted(load)
onUnmounted(stopPolling)
</script>

<style scoped>
.card-header { display:flex; justify-content:space-between; align-items:center; font-weight:600; color: #e2e8f0; }
</style>
