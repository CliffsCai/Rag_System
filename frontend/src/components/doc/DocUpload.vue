<template>
  <el-tabs v-model="activeTab" type="border-card">

    <!-- Tab 1: 单文件上传 -->
    <el-tab-pane label="📄 单文件上传" name="single">
      <el-card shadow="never" style="margin-top:12px">
        <el-alert type="info" :closable="false" show-icon style="margin-bottom:20px"
          :title="imageMode
            ? '图文模式：自定义解析 PDF，提取图片并与切片关联，完成后在文件列表查看结果'
            : '直接上传文件并提交切分任务（dry_run=true），不关联类目，完成后在文件列表查看结果'" />

        <el-form label-width="100px" style="margin-bottom:16px">
          <el-form-item label="切分参数">
            <el-row :gutter="16">
              <el-col :span="7">
                <el-input-number v-model="config.chunkSize" :min="100" :max="2048" :step="100" style="width:100%" />
                <div class="tip">块大小（默认{{ imageMode ? 500 : 800 }}）</div>
              </el-col>
              <el-col :span="7">
                <el-input-number v-model="config.chunkOverlap" :min="0" :max="config.chunkSize" :step="10" style="width:100%" />
                <div class="tip">重叠（默认{{ imageMode ? 50 : 100 }}）</div>
              </el-col>
              <template v-if="imageMode">
                <el-col :span="5">
                  <el-input-number v-model="config.imageDpi" :min="72" :max="300" :step="50" style="width:100%" />
                  <div class="tip">图片 DPI</div>
                </el-col>
              </template>
              <template v-else>
                <el-col :span="5">
                  <el-switch v-model="config.zhTitleEnhance" />
                  <div class="tip">中文标题加强</div>
                </el-col>
                <el-col :span="5">
                  <el-switch v-model="config.vlEnhance" />
                  <div class="tip">VL增强识别</div>
                </el-col>
              </template>
            </el-row>
          </el-form-item>
        </el-form>

        <!-- 图文模式：手动上传按钮 -->
        <template v-if="imageMode">
          <el-upload
            ref="imageUploadRef"
            :auto-upload="false"
            :on-change="onImageModeFileChange"
            accept=".pdf"
            :show-file-list="true"
            :limit="1"
          >
            <el-button type="primary" :loading="imageUploading">
              <el-icon><upload-filled /></el-icon> 选择 PDF 文件
            </el-button>
            <template #tip>
              <div style="font-size:12px;color:#909399;margin-top:4px">仅支持 PDF，最大 200MB</div>
            </template>
          </el-upload>
          <el-button
            v-if="imageSelectedFile"
            type="success"
            style="margin-top:12px"
            :loading="imageUploading"
            @click="submitImageUpload"
          >
            ✂️ 开始解析上传
          </el-button>
        </template>

          <!-- 普通模式：拖拽上传 -->
        <el-upload
          v-else
          drag multiple
          :action="uploadUrl"
          :before-upload="beforeUpload"
          :on-success="onSingleSuccess"
          :on-error="onError"
          :data="uploadData"
          :show-file-list="true"
        >
          <el-icon style="font-size:48px"><upload-filled /></el-icon>
          <div style="margin-top:8px;font-size:14px;color:#606266">
            拖拽文件到此处或<em style="color:#409eff;font-style:normal">点击上传</em>
          </div>
          <template #tip>
            <div style="font-size:12px;color:#909399;margin-top:4px">
              支持 PDF、Word、PPT、TXT、MD、Excel，最大 200MB
            </div>
          </template>
        </el-upload>

        <!-- 同步到知识图谱开关 -->
        <div style="margin-top:12px;display:flex;align-items:center;gap:8px">
          <el-switch v-model="syncGraph" active-text="同步到知识图谱" inactive-text="不同步" />
          <el-tooltip content="开启后，向量化完成时自动将切片同步到知识图谱，生成 chunks 关系三元组" placement="top">
            <el-icon style="color:#909399;cursor:pointer"><QuestionFilled /></el-icon>
          </el-tooltip>
        </div>
      </el-card>
    </el-tab-pane>

    <!-- Tab 2: 类目上传 -->
    <el-tab-pane label="🗂️ 类目上传" name="category">
      <el-card shadow="never" style="margin-top:12px">
        <el-alert type="info" :closable="false" show-icon style="margin-bottom:20px"
          title="选择类目后点击「开始切分」，将该类目下所有 OSS 文件批量提交切分任务" />

        <el-form label-width="120px">
          <el-form-item label="选择类目" required>
            <el-select
              v-model="selectedCategoryId"
              placeholder="请选择类目"
              style="width:320px"
              @focus="loadCategories"
              :loading="categoriesLoading"
              clearable
            >
              <el-option
                v-for="cat in categories"
                :key="cat.category_id"
                :label="cat.name"
                :value="cat.category_id"
              >
                <span>{{ cat.name }}</span>
                <span style="float:right;color:#909399;font-size:12px">{{ cat.description || '' }}</span>
              </el-option>
            </el-select>
            <el-button size="small" style="margin-left:8px" @click="$emit('go-categories')">
              管理类目
            </el-button>
          </el-form-item>
          <el-form-item label="目标知识库" required v-if="!collection">
            <el-select
              v-model="selectedCollection"
              placeholder="请选择知识库"
              style="width:320px"
              @focus="loadCollections"
              :loading="collectionsLoading"
              clearable
            >
              <el-option
                v-for="col in collections"
                :key="col.collection_name"
                :label="col.collection_name"
                :value="col.collection_name"
              />
            </el-select>
          </el-form-item>

          <el-divider content-position="left">切分参数</el-divider>

          <el-form-item label="块大小">
            <el-input-number v-model="catConfig.chunkSize" :min="100" :max="2048" :step="100" style="width:160px" />
            <span class="tip" style="margin-left:8px">最大 2048，默认 800</span>
          </el-form-item>
          <el-form-item label="重叠大小">
            <el-input-number v-model="catConfig.chunkOverlap" :min="0" :max="catConfig.chunkSize" :step="10" style="width:160px" />
            <span class="tip" style="margin-left:8px">不超过块大小，默认 100</span>
          </el-form-item>

          <!-- 图文模式专属参数 -->
          <template v-if="imageMode">
            <el-form-item label="图片 DPI">
              <el-input-number v-model="catConfig.imageDpi" :min="72" :max="300" :step="50" style="width:160px" />
              <span class="tip" style="margin-left:8px">截图分辨率，默认 150</span>
            </el-form-item>
            <el-form-item label="同步到图谱">
              <el-switch v-model="syncGraphCat" />
              <span class="tip" style="margin-left:8px">向量化完成后自动同步到知识图谱</span>
            </el-form-item>
          </template>

          <!-- 普通模式专属参数 -->
          <template v-else>
            <el-form-item label="分词器">
              <el-select v-model="catConfig.textSplitterName" style="width:320px">
                <el-option label="ChineseRecursiveTextSplitter（中文推荐）" value="ChineseRecursiveTextSplitter" />
                <el-option label="RecursiveCharacterTextSplitter（英文/代码）" value="RecursiveCharacterTextSplitter" />
                <el-option label="SpacyTextSplitter（英文文档）" value="SpacyTextSplitter" />
                <el-option label="MarkdownHeaderTextSplitter（Markdown）" value="MarkdownHeaderTextSplitter" />
              </el-select>
            </el-form-item>
            <el-form-item label="中文标题加强">
              <el-switch v-model="catConfig.zhTitleEnhance" />
            </el-form-item>
            <el-form-item label="Excel 每片行数">
              <el-input-number v-model="catConfig.excelRowsPerChunk" :min="1" :max="5000" :step="10" style="width:160px" />
              <span class="tip" style="margin-left:8px">Excel 文件每个切片的数据行数，默认 50</span>
            </el-form-item>
            <el-form-item label="VL增强识别">
              <el-switch v-model="catConfig.vlEnhance" />
              <span class="tip" style="margin-left:8px">适用于排版混乱的复杂文档，处理较慢</span>
            </el-form-item>
            <el-form-item label="Metadata">
              <el-tag type="info" size="small">自动注入</el-tag>
              <span class="tip" style="margin-left:8px">根据知识库配置自动提取文件名前缀等字段</span>
            </el-form-item>
            <el-form-item label="同步到图谱">
              <el-switch v-model="syncGraphCat" />
              <span class="tip" style="margin-left:8px">向量化完成后自动同步到知识图谱</span>
            </el-form-item>
          </template>
        </el-form>

        <div style="margin-top:16px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
          <el-button
            type="primary"
            :disabled="!selectedCategoryId || (!collection && !selectedCollection)"
            :loading="chunking"
            @click="startChunking"
          >
            ✂️ 开始切分
          </el-button>

          <span v-if="!selectedCategoryId" style="color:#909399;font-size:13px">
            请先选择类目
          </span>
        </div>

        <el-divider v-if="chunkResult" />
        <el-alert
          v-if="chunkResult"
          :type="chunkResult.errors?.length ? 'warning' : 'success'"
          :closable="false"
          show-icon
          :title="`已提交 ${chunkResult.submitted} 个，跳过 ${chunkResult.skipped?.length || 0} 个${chunkResult.errors?.length ? `，${chunkResult.errors.length} 个失败` : ''}`"
        />
        <div v-if="chunkResult?.skipped?.length" style="margin-top:8px">
          <el-alert type="warning" :closable="false" show-icon
            title="以下文件已存在于知识库，已跳过。如需更新，请先在文件列表删除旧版本后重新切分：" />
          <div style="margin-top:6px;display:flex;flex-direction:column;gap:4px">
            <el-tag
              v-for="s in chunkResult.skipped" :key="s.file_name"
              type="warning" size="small" style="width:fit-content"
            >{{ s.file_name }}</el-tag>
          </div>
        </div>
      </el-card>
    </el-tab-pane>

  </el-tabs>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled, QuestionFilled } from '@element-plus/icons-vue'
import { docApi } from '@/services/docApi'

const emit = defineEmits(['open-jobs', 'uploaded', 'go-categories'])

const props = defineProps({
  collection: { type: String, default: '' },
  imageMode: { type: Boolean, default: false },
})

const activeTab = ref('single')
const categories = ref([])
const categoriesLoading = ref(false)
const selectedCategoryId = ref('')
const collections = ref([])
const collectionsLoading = ref(false)
const selectedCollection = ref('')
const chunking = ref(false)
const chunkResult = ref(null)
// 同步到知识图谱
const syncGraph = ref(false)
const syncGraphCat = ref(false)

const config = ref({
  chunkSize: 800,
  chunkOverlap: 100,
  zhTitleEnhance: true,
  vlEnhance: false,
  imageDpi: 150,
})

// 图文模式上传状态
const imageUploadRef = ref(null)
const imageSelectedFile = ref(null)
const imageUploading = ref(false)

const onImageModeFileChange = (file) => {
  imageSelectedFile.value = file.raw
}

const submitImageUpload = async () => {
  if (!imageSelectedFile.value) return
  imageUploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', imageSelectedFile.value)
    fd.append('chunk_size', config.value.chunkSize)
    fd.append('chunk_overlap', config.value.chunkOverlap)
    fd.append('image_dpi', config.value.imageDpi)
    if (props.collection) fd.append('collection', props.collection)
    const res = await docApi.uploadWithImages(fd)
    if (res.data.success) {
      ElMessage.success(res.data.message || '上传成功')
      imageSelectedFile.value = null
      imageUploadRef.value?.clearFiles()
      emit('uploaded', res.data.data)
    }
  } catch (e) {
    ElMessage.error('上传失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    imageUploading.value = false
  }
}

const catConfig = ref({
  chunkSize: 800,
  chunkOverlap: 100,
  textSplitterName: 'ChineseRecursiveTextSplitter',
  zhTitleEnhance: true,
  vlEnhance: false,
  imageDpi: 150,
  excelRowsPerChunk: 50,
})

const uploadUrl = computed(() => {
  const base = 'http://localhost:8000/api/v1/documents/upload'
  return props.collection ? `${base}?collection=${encodeURIComponent(props.collection)}` : base
})

const uploadData = computed(() => ({
  chunk_size: config.value.chunkSize,
  chunk_overlap: config.value.chunkOverlap,
  zh_title_enhance: config.value.zhTitleEnhance,
  vl_enhance: config.value.vlEnhance,
  sync_graph: syncGraph.value,
}))

const loadCategories = async () => {
  if (categoriesLoading.value || categories.value.length > 0) return
  categoriesLoading.value = true
  try {
    const res = await docApi.listCategories()
    categories.value = res.data.data.categories || []
  } catch (e) {
    console.error(e)
  } finally {
    categoriesLoading.value = false
  }
}

const loadCollections = async () => {
  if (collectionsLoading.value || collections.value.length > 0) return
  collectionsLoading.value = true
  try {
    const res = await docApi.listCollections('knowledge_ns')
    collections.value = res.data.data?.collections || []
  } catch (e) {
    console.error(e)
  } finally {
    collectionsLoading.value = false
  }
}

const beforeUpload = (file) => {
  const allowed = ['.pdf', '.doc', '.docx', '.txt', '.md', '.ppt', '.pptx', '.xlsx', '.xls']
  const ext = '.' + file.name.split('.').pop().toLowerCase()
  if (!allowed.includes(ext)) {
    ElMessage.error(`不支持的格式: ${ext}`)
    return false
  }
  if (file.size > 200 * 1024 * 1024) {
    ElMessage.error('文件超过 200MB')
    return false
  }
  return true
}

const onSingleSuccess = (response, file) => {
  if (response.success) {
    ElMessage.success(`${file.name} 上传成功，请在文件列表查看进度`)
    emit('uploaded', response.data)
  } else {
    ElMessage.error(`${file.name} 上传失败: ` + (response.message || '未知错误'))
  }
}

const onError = (error, file) => {
  let msg = '上传失败'
  try { msg = JSON.parse(error.message)?.detail || msg } catch {}
  ElMessage.error(`${file.name}: ${msg}`)
}

const startChunking = async () => {
  if (!selectedCategoryId.value) return
  const col = props.collection || selectedCollection.value
  if (!col) return
  chunking.value = true
  chunkResult.value = null
  try {
    const res = await docApi.startChunking(selectedCategoryId.value, {
      kb_name: col,
      chunk_size: catConfig.value.chunkSize,
      chunk_overlap: catConfig.value.chunkOverlap,
      text_splitter_name: catConfig.value.textSplitterName,
      zh_title_enhance: catConfig.value.zhTitleEnhance,
      vl_enhance: catConfig.value.vlEnhance,
      image_dpi: catConfig.value.imageDpi,
      sync_graph: syncGraphCat.value,
      excel_rows_per_chunk: catConfig.value.excelRowsPerChunk,
    })
    chunkResult.value = res.data.data
    const { submitted, errors } = res.data.data
    if (submitted === 0) {
      ElMessage.info(res.data.message)
    } else {
      ElMessage.success(`已提交 ${submitted} 个文件切分任务`)
      emit('uploaded', res.data.data)
    }
    if (errors?.length) {
      ElMessage.warning(`${errors.length} 个文件提交失败`)
    }
  } catch (err) {
    ElMessage.error('切分失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    chunking.value = false
  }
}


</script>

<style scoped>
:deep(.el-upload-dragger) { padding: 30px; }
</style>
