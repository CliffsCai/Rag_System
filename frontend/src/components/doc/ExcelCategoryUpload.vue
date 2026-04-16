<template>
  <el-card shadow="never" style="margin-top:12px">
    <el-alert type="info" :closable="false" show-icon style="margin-bottom:20px"
      title="选择类目后点击「开始切分」，弹窗中为每个 Excel 文件配置需要录入的列，支持修改列别名" />

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
          />
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

      <el-form-item label="每片行数">
        <el-input-number v-model="rowsPerChunk" :min="1" :max="5000" :step="10" style="width:160px" />
        <span class="tip" style="margin-left:8px">每个切片包含的数据行数，默认 50</span>
      </el-form-item>
    </el-form>

    <div style="margin-top:16px">
      <el-button
        type="primary"
        :disabled="!selectedCategoryId || (!collection && !selectedCollection)"
        :loading="loadingColumns"
        @click="openColumnDialog"
      >
        ✂️ 开始切分
      </el-button>
    </div>

    <el-divider v-if="chunkResult" />
    <el-alert
      v-if="chunkResult"
      :type="chunkResult.errors?.length ? 'warning' : 'success'"
      :closable="false"
      show-icon
      :title="`已提交 ${chunkResult.submitted} 个，跳过 ${chunkResult.skipped?.length || 0} 个${chunkResult.errors?.length ? `，${chunkResult.errors.length} 个失败` : ''}`"
    />
  </el-card>

  <!-- 列配置弹窗 -->
  <el-dialog
    v-model="dialogVisible"
    title="配置 Excel 列"
    width="760px"
    :close-on-click-modal="false"
    destroy-on-close
  >
    <div v-if="excelFiles.length === 0" style="text-align:center;padding:40px;color:#909399">
      该类目中没有 Excel 文件（.xlsx / .xls）
    </div>

    <div v-else>
      <!-- 文件 tabs -->
      <el-tabs v-model="activeFileTab" type="card">
        <el-tab-pane
          v-for="file in excelFiles"
          :key="file.category_file_id"
          :label="file.file_name"
          :name="file.category_file_id"
        >
          <div v-if="file.loading" style="padding:20px;text-align:center">
            <el-icon class="is-loading"><Loading /></el-icon> 读取列名中...
          </div>
          <div v-else-if="file.error" style="padding:20px;color:#f56c6c">
            {{ file.error }}
          </div>
          <div v-else>
            <!-- sheet tabs -->
            <el-tabs v-model="file.activeSheet" type="border-card" style="margin-top:8px">
              <el-tab-pane
                v-for="(cols, sheetName) in file.sheets"
                :key="sheetName"
                :label="sheetName"
                :name="sheetName"
              >
                <div style="margin-bottom:8px;display:flex;gap:8px;align-items:center">
                  <el-button size="small" @click="selectAll(file, sheetName)">全选</el-button>
                  <el-button size="small" @click="deselectAll(file, sheetName)">取消全选</el-button>
                  <span style="font-size:12px;color:#909399">
                    已选 {{ selectedCount(file, sheetName) }} / {{ cols.length }} 列
                  </span>
                </div>

                <el-table :data="file.columnConfigs[sheetName]" style="width:100%" max-height="360">
                  <el-table-column width="50" align="center">
                    <template #default="{ row }">
                      <el-checkbox v-model="row.selected" />
                    </template>
                    <template #header>
                      <el-checkbox
                        :model-value="allSelected(file, sheetName)"
                        :indeterminate="someSelected(file, sheetName)"
                        @change="(v) => toggleAll(file, sheetName, v)"
                      />
                    </template>
                  </el-table-column>
                  <el-table-column label="原始列名" prop="original" min-width="160" show-overflow-tooltip />
                  <el-table-column label="别名（录入时使用）" min-width="200">
                    <template #default="{ row }">
                      <el-input
                        v-model="row.alias"
                        :disabled="!row.selected"
                        size="small"
                        placeholder="留空则使用原始列名"
                        clearable
                      />
                    </template>
                  </el-table-column>
                </el-table>
              </el-tab-pane>
            </el-tabs>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>

    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button
        type="primary"
        :loading="chunking"
        :disabled="excelFiles.length === 0"
        @click="submitChunking"
      >
        开始切分
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { docApi } from '@/services/docApi'

const emit = defineEmits(['uploaded', 'go-categories'])

const props = defineProps({
  collection: { type: String, default: '' },
})

// ── 表单状态 ──────────────────────────────────────────────────────────────────
const selectedCategoryId = ref('')
const selectedCollection = ref('')
const rowsPerChunk = ref(50)
const categories = ref([])
const categoriesLoading = ref(false)
const collections = ref([])
const collectionsLoading = ref(false)
const chunkResult = ref(null)

// ── 弹窗状态 ──────────────────────────────────────────────────────────────────
const dialogVisible = ref(false)
const loadingColumns = ref(false)
const chunking = ref(false)
const excelFiles = ref([])   // [{category_file_id, file_name, sheets, columnConfigs, activeSheet, loading, error}]
const activeFileTab = ref('')

// ── 加载类目 / 知识库 ─────────────────────────────────────────────────────────
const loadCategories = async () => {
  if (categoriesLoading.value || categories.value.length > 0) return
  categoriesLoading.value = true
  try {
    const res = await docApi.listCategories()
    categories.value = res.data.data.categories || []
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
  } finally {
    collectionsLoading.value = false
  }
}

// ── 打开弹窗：读取类目中的 Excel 文件列表，再逐个获取列名 ─────────────────────
const openColumnDialog = async () => {
  loadingColumns.value = true
  try {
    // 获取类目文件列表
    const res = await docApi.listCategoryFiles(selectedCategoryId.value)
    const allFiles = res.data.data?.files || []
    const excels = allFiles.filter(f =>
      /\.(xlsx|xls)$/i.test(f.file_name)
    )

    if (excels.length === 0) {
      ElMessage.info('该类目中没有 Excel 文件')
      return
    }

    // 初始化文件列表（先展示弹窗，列名异步加载）
    excelFiles.value = excels.map(f => ({
      category_file_id: f.id,
      file_name: f.file_name,
      sheets: {},
      columnConfigs: {},
      activeSheet: '',
      loading: true,
      error: null,
    }))
    activeFileTab.value = excelFiles.value[0]?.category_file_id || ''
    dialogVisible.value = true

    // 并发获取每个文件的列名
    await Promise.all(excelFiles.value.map(async (file) => {
      try {
        const r = await docApi.getExcelColumns(file.category_file_id)
        const sheets = r.data.data.sheets || {}
        file.sheets = sheets
        // 初始化每个 sheet 的列配置（全选，alias = original）
        file.columnConfigs = {}
        for (const [sheetName, cols] of Object.entries(sheets)) {
          file.columnConfigs[sheetName] = cols.map(col => ({
            original: col,
            alias: col,
            selected: true,
          }))
        }
        file.activeSheet = Object.keys(sheets)[0] || ''
      } catch (e) {
        file.error = '读取列名失败: ' + (e.response?.data?.detail || e.message)
      } finally {
        file.loading = false
      }
    }))
  } catch (e) {
    ElMessage.error('获取类目文件失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    loadingColumns.value = false
  }
}

// ── 列选择辅助 ────────────────────────────────────────────────────────────────
const selectedCount = (file, sheetName) =>
  (file.columnConfigs[sheetName] || []).filter(c => c.selected).length

const allSelected = (file, sheetName) => {
  const cols = file.columnConfigs[sheetName] || []
  return cols.length > 0 && cols.every(c => c.selected)
}

const someSelected = (file, sheetName) => {
  const cols = file.columnConfigs[sheetName] || []
  const n = cols.filter(c => c.selected).length
  return n > 0 && n < cols.length
}

const toggleAll = (file, sheetName, val) => {
  (file.columnConfigs[sheetName] || []).forEach(c => { c.selected = val })
}

const selectAll = (file, sheetName) => toggleAll(file, sheetName, true)
const deselectAll = (file, sheetName) => toggleAll(file, sheetName, false)

// ── 提交切分 ──────────────────────────────────────────────────────────────────
const submitChunking = async () => {
  const col = props.collection || selectedCollection.value
  if (!col) return

  // 构建 excel_configs
  const excelConfigs = excelFiles.value
    .filter(f => !f.loading && !f.error)
    .map(file => {
      const columnConfig = {}
      for (const [sheetName, cols] of Object.entries(file.columnConfigs)) {
        const selected = cols
          .filter(c => c.selected)
          .map(c => ({ original: c.original, alias: c.alias || c.original }))
        if (selected.length > 0) {
          columnConfig[sheetName] = selected
        }
      }
      return {
        category_file_id: file.category_file_id,
        column_config: columnConfig,
      }
    })

  chunking.value = true
  try {
    const res = await docApi.startChunkingExcel(selectedCategoryId.value, {
      kb_name: col,
      excel_rows_per_chunk: rowsPerChunk.value,
      excel_configs: JSON.stringify(excelConfigs),
    })
    chunkResult.value = res.data.data
    const { submitted, errors } = res.data.data
    if (submitted === 0) {
      ElMessage.info(res.data.message)
    } else {
      ElMessage.success(`已提交 ${submitted} 个 Excel 文件切分任务`)
      emit('uploaded', res.data.data)
    }
    if (errors?.length) ElMessage.warning(`${errors.length} 个文件提交失败`)
    dialogVisible.value = false
  } catch (e) {
    ElMessage.error('切分失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    chunking.value = false
  }
}
</script>

<style scoped>
.tip { font-size: 12px; color: #909399; }
</style>
