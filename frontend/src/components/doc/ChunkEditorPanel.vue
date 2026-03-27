<template>
  <div>
    <!-- 操作栏 -->
    <el-icon v-show="false"><Loading /></el-icon>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <div>
        <el-tag type="info">共 {{ chunks.length }} 个切片</el-tag>
        <el-tag v-if="editedCount > 0" type="warning" style="margin-left:8px">已编辑 {{ editedCount }} 个</el-tag>
      </div>
      <div style="display:flex;gap:8px">
        <el-button size="small" @click="load" :loading="loading">刷新</el-button>
        <template v-if="!props.readonly">
          <el-button size="small" @click="fetchChunks" :loading="fetching">重新获取切片</el-button>
          <el-button size="small" type="warning" @click="cleanAll" :loading="cleaningAll">批量清洗</el-button>
          <el-button size="small" type="danger" plain @click="revertAll">全部还原</el-button>
          <el-button size="small" type="success" @click="upsert" :loading="upserting">确认上传向量库</el-button>
        </template>
      </div>
    </div>

    <!-- 无切片时提示 -->
    <el-empty v-if="!loading && !fetching && chunks.length === 0" description="暂无切片数据，请确认 Job 已完成后重新获取" />
    <div v-if="fetching && chunks.length === 0" style="text-align:center;padding:40px;color:#909399">
      <el-icon class="is-loading" style="font-size:24px"><Loading /></el-icon>
      <div style="margin-top:8px">正在从 ADB 拉取切片，请稍候...</div>
    </div>

    <el-table v-else :data="paged" v-loading="loading" style="width:100%" max-height="560" stripe border>
      <el-table-column type="index" label="#" width="55" align="center"
        :index="(i) => (currentPage - 1) * pageSize + i + 1" />

      <el-table-column label="切片内容" min-width="420">
        <template #default="{ row }">
          <el-input
            v-model="row.content"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 8 }"
            :readonly="props.readonly"
            @click="onTextareaClick(row, $event)"
            @keyup="onTextareaClick(row, $event)"
            @input="!props.readonly && (row._edited = true)"
          />
          <!-- 图文模式：占位符 tag 列表 + 添加图片 -->
          <div v-if="imageMode" style="margin-top:8px">
            <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
              <template v-for="ph in parsePlaceholders(row.content)" :key="ph">
                <el-tag
                  type="info" size="small" closable
                  style="cursor:pointer;max-width:160px"
                  @close="!props.readonly && removePlaceholder(row, ph)"
                >
                  <el-image
                    v-if="row._imageUrlMap && row._imageUrlMap[ph]"
                    :src="row._imageUrlMap[ph]"
                    style="width:20px;height:16px;object-fit:cover;vertical-align:middle;margin-right:4px;border-radius:2px"
                    fit="cover"
                  />
                  {{ ph }}
                </el-tag>
              </template>
              <el-button
                v-if="!props.readonly"
                size="small" plain
                :disabled="row._cursorPos == null"
                :title="row._cursorPos == null ? '请先点击文本框选择插入位置' : '在光标处插入图片'"
                @click="openAddImage(row)"
              >+ 插入图片</el-button>
            </div>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="元数据" width="160">
        <template #default="{ row }">
          <div style="font-size:12px;color:#606266">
            <div v-if="row.metadata?.page">页码: {{ row.metadata.page }}</div>
            <div v-if="row.metadata?.title" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
              {{ row.metadata.title }}
            </div>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="状态" width="80" align="center">
        <template #default="{ row }">
          <el-tag v-if="row._edited" type="warning" size="small">已编辑</el-tag>
          <el-tag v-else type="info" size="small">原始</el-tag>
        </template>
      </el-table-column>

      <el-table-column v-if="!props.readonly" label="操作" width="180" align="center" fixed="right">
        <template #default="{ row }">
          <el-button size="small" link type="success" @click="saveOne(row)" :disabled="!row._edited" :loading="row._saving">保存</el-button>
          <el-button size="small" link type="primary" @click="cleanOne(row)" :loading="row._cleaning">清洗</el-button>
          <el-button size="small" link type="info" @click="revertOne(row)">还原</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-if="chunks.length > pageSize"
      v-model:current-page="currentPage"
      v-model:page-size="pageSize"
      :page-sizes="[10, 20, 50]"
      :total="chunks.length"
      layout="total, sizes, prev, pager, next"
      style="margin-top:16px;justify-content:center"
    />

    <!-- 添加图片对话框 -->
    <el-dialog v-model="addImageDialogVisible" title="添加图片" width="400px" destroy-on-close>
      <el-upload
        ref="uploadRef"
        :auto-upload="false"
        :limit="1"
        accept="image/*"
        :on-change="onImageFileChange"
        :show-file-list="true"
        drag
      >
        <el-icon style="font-size:32px;color:#909399"><Plus /></el-icon>
        <div style="margin-top:8px;color:#606266">点击或拖拽图片到此处</div>
      </el-upload>
      <template #footer>
        <el-button @click="addImageDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="addingImage" @click="confirmAddImage">确认上传</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Loading, Plus } from '@element-plus/icons-vue'
import { docApi } from '@/services/docApi'

const props = defineProps({
  jobId: { type: String, required: true },
  readonly: { type: Boolean, default: false },
  imageMode: { type: Boolean, default: false },
})
const emit = defineEmits(['vectorized'])

const chunks = ref([])
const loading = ref(false)
const fetching = ref(false)
const cleaningAll = ref(false)
const upserting = ref(false)
const currentPage = ref(1)
const pageSize = ref(20)

const paged = computed(() => {
  const s = (currentPage.value - 1) * pageSize.value
  return chunks.value.slice(s, s + pageSize.value)
})

const editedCount = computed(() => chunks.value.filter(c => c._edited).length)

const load = async () => {
  loading.value = true
  try {
    const res = await docApi.getChunksByJob(props.jobId)
    const rawChunks = (res.data.data?.chunks || []).map(c => ({
      ...c,
      content: c.current_content,
      _edited: false,
      _cleaning: false,
      _saving: false,
      _cursorPos: null,    // 光标位置
      _imageUrlMap: {},    // placeholder → proxy url
    }))
    chunks.value = rawChunks
    if (props.imageMode) {
      await loadAllImageUrls()
    }
  } catch (e) {
    ElMessage.error('加载切片失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

// 从 content 解析占位符列表
const parsePlaceholders = (content) => {
  if (!content) return []
  return [...content.matchAll(/<<IMAGE:[0-9a-f]+>>/g)].map(m => m[0])
}

// 批量加载所有切片的图片 URL（placeholder → proxy url）
const loadAllImageUrls = async () => {
  await Promise.all(chunks.value.map(async (row) => {
    try {
      const res = await docApi.getChunkImages(props.jobId, row.chunk_index)
      const images = res.data.data?.images || []
      const map = {}
      for (const img of images) {
        if (img.placeholder && img.oss_url) {
          map[img.placeholder] = img.oss_url
        }
      }
      row._imageUrlMap = map
    } catch { row._imageUrlMap = {} }
  }))
}

// 记录光标位置
const onTextareaClick = (row, e) => {
  row._cursorPos = e.target.selectionStart ?? null
}

// 图片管理
const addImageDialogVisible = ref(false)
const addImageRow = ref(null)
const addImageFile = ref(null)
const addingImage = ref(false)
const uploadRef = ref(null)

const openAddImage = (row) => {
  addImageRow.value = row
  addImageFile.value = null
  addImageDialogVisible.value = true
}

const onImageFileChange = (file) => {
  addImageFile.value = file.raw
}

const confirmAddImage = async () => {
  if (!addImageFile.value) {
    ElMessage.warning('请先选择图片')
    return
  }
  addingImage.value = true
  try {
    const row = addImageRow.value
    const insertPos = row._cursorPos ?? row.content.length
    const res = await docApi.addChunkImage(
      props.jobId, row.chunk_index, addImageFile.value, null, insertPos
    )
    const { placeholder, oss_url } = res.data.data
    // 前端同步插入占位符到 content
    row.content = row.content.slice(0, insertPos) + placeholder + row.content.slice(insertPos)
    row._cursorPos = null
    // 更新 imageUrlMap
    if (oss_url) {
      row._imageUrlMap = {
        ...row._imageUrlMap,
        [placeholder]: oss_url
      }
    }
    addImageDialogVisible.value = false
    ElMessage.success('图片已插入')
  } catch (e) {
    ElMessage.error('添加失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    addingImage.value = false
  }
}

// 删除占位符对应的图片
const removePlaceholder = async (row, placeholder) => {
  // 找到对应的图片记录 id
  try {
    const res = await docApi.getChunkImages(props.jobId, row.chunk_index)
    const images = res.data.data?.images || []
    const img = images.find(i => i.placeholder === placeholder)
    if (!img) {
      ElMessage.warning('未找到对应图片记录')
      return
    }
    await docApi.deleteChunkImage(props.jobId, row.chunk_index, img.id)
    // 前端同步删除占位符
    row.content = row.content.replace(placeholder, '')
    const map = { ...row._imageUrlMap }
    delete map[placeholder]
    row._imageUrlMap = map
    ElMessage.success('图片已删除')
  } catch (e) {
    ElMessage.error('删除失败: ' + (e.response?.data?.detail || e.message))
  }
}

const fetchChunks = async () => {
  fetching.value = true
  try {
    const res = await docApi.fetchChunks(props.jobId)
    ElMessage.success(res.data.message || '切片已获取')
    await load()
  } catch (e) {
    ElMessage.error('获取切片失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    fetching.value = false
  }
}

const saveOne = async (row) => {
  row._saving = true
  try {
    await docApi.editChunk(props.jobId, row.chunk_index, row.content)
    row._edited = false
    ElMessage.success('保存成功')
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    row._saving = false
  }
}

const cleanOne = async (row) => {
  row._cleaning = true
  try {
    const res = await docApi.cleanChunk(props.jobId, row.chunk_index)
    row.content = res.data.data?.content || row.content
    row._edited = false
    ElMessage.success('清洗完成')
  } catch (e) {
    ElMessage.error('清洗失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    row._cleaning = false
  }
}

const revertOne = async (row) => {
  try {
    await docApi.revertChunk(props.jobId, row.chunk_index)
    row.content = row.original_content
    row._edited = false
    ElMessage.success('已还原')
  } catch (e) {
    ElMessage.error('还原失败: ' + (e.response?.data?.detail || e.message))
  }
}

const cleanAll = async () => {
  try {
    await ElMessageBox.confirm(`批量清洗全部 ${chunks.value.length} 个切片？`, '确认', {
      confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning'
    })
  } catch { return }
  cleaningAll.value = true
  try {
    await docApi.cleanJobChunks(props.jobId)
    ElMessage.success('批量清洗已提交')
    await load()
  } catch (e) {
    ElMessage.error('批量清洗失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    cleaningAll.value = false
  }
}

const revertAll = async () => {
  try {
    await ElMessageBox.confirm('还原该 Job 所有切片到原始内容？', '确认', {
      confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning'
    })
  } catch { return }
  try {
    await docApi.revertJobChunks(props.jobId)
    ElMessage.success('已全部还原')
    await load()
  } catch (e) {
    ElMessage.error('还原失败: ' + (e.response?.data?.detail || e.message))
  }
}

const upsert = async () => {
  try {
    await ElMessageBox.confirm('将切片上传到向量库？', '确认上传', {
      confirmButtonText: '确定', cancelButtonText: '取消', type: 'info'
    })
  } catch { return }
  upserting.value = true
  try {
    const res = await docApi.upsertJobChunks(props.jobId)
    ElMessage.success(res.data.message || '上传成功')
    emit('vectorized')
  } catch (e) {
    ElMessage.error('上传失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    upserting.value = false
  }
}

onMounted(async () => {
  await load()
  // 图文模式切片已本地写入，不需要从 ADB 拉取
  if (!props.imageMode && chunks.value.length === 0) {
    await fetchChunks()
  }
})
</script>
