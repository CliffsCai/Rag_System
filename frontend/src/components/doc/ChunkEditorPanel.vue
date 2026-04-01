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
        <el-button v-if="!props.readonly" size="small" @click="load" :loading="loading">刷新</el-button>
        <template v-if="!props.readonly">
          <el-button size="small" @click="fetchChunks" :loading="fetching">重新获取切片</el-button>
          <el-button size="small" type="warning" @click="cleanAll" :loading="cleaningAll">批量清洗</el-button>
          <el-button size="small" type="danger" plain @click="revertAll">全部还原</el-button>
          <el-button size="small" type="success" @click="upsert" :loading="upserting">确认上传向量库</el-button>
        </template>
      </div>
    </div>

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

          <!-- 图文模式：contenteditable 编辑器 -->
          <template v-if="imageMode">
            <div
              :ref="el => setEditorRef(el, row)"
              class="chunk-editor"
              :contenteditable="!props.readonly"
              :data-placeholder="row.chunk_id"
              @input="onEditorInput(row)"
              @keydown="onEditorKeydown"
              @paste="onEditorPaste"
              @mouseup="onEditorMouseup(row)"
            ></div>

            <!-- 图片预览区 -->
            <div v-if="parsePlaceholders(row.content).length" style="margin-top:8px;display:flex;flex-wrap:wrap;gap:8px;align-items:flex-start">
              <div
                v-for="ph in parsePlaceholders(row.content)" :key="ph"
                class="image-preview-item"
                :class="{ 'image-highlight': row._hoveredPh === ph }"
                @mouseenter="row._hoveredPh = ph; highlightSpan(row, ph, true)"
                @mouseleave="row._hoveredPh = null; highlightSpan(row, ph, false)"
              >
                <el-image
                  v-if="row._imageUrlMap && row._imageUrlMap[ph]"
                  :src="row._imageUrlMap[ph]"
                  style="width:80px;height:60px;object-fit:cover;border-radius:4px;display:block"
                  fit="cover"
                  :preview-src-list="[row._imageUrlMap[ph]]"
                  preview-teleported
                />
                <div v-else style="width:80px;height:60px;background:#f5f7fa;border-radius:4px;display:flex;align-items:center;justify-content:center;font-size:11px;color:#909399">无图片</div>
                <div style="font-size:10px;color:#909399;margin-top:2px;word-break:break-all;max-width:80px">{{ ph }}</div>
              </div>
              <el-button
                v-if="!props.readonly"
                size="small" plain
                :disabled="!row._insertPos"
                :title="!row._insertPos ? '请先在编辑框中点击选择插入位置' : '在光标处插入图片'"
                @click="openAddImage(row)"
              >+ 插入图片</el-button>
            </div>
            <div v-else-if="!props.readonly" style="margin-top:8px">
              <el-button
                size="small" plain
                :disabled="!row._insertPos"
                :title="!row._insertPos ? '请先在编辑框中点击选择插入位置' : '在光标处插入图片'"
                @click="openAddImage(row)"
              >+ 插入图片</el-button>
            </div>
          </template>

          <!-- 标准模式：普通 textarea -->
          <template v-else>
            <el-input
              v-model="row.content"
              type="textarea"
              :autosize="{ minRows: 3, maxRows: 8 }"
              :readonly="props.readonly"
              @input="!props.readonly && (row._edited = true)"
            />
          </template>

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
import { ref, computed, onMounted, nextTick } from 'vue'
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

// chunk_id → editor DOM 元素
const editorRefs = {}
const setEditorRef = (el, row) => {
  if (el) editorRefs[row.chunk_id] = el
}

const paged = computed(() => {
  const s = (currentPage.value - 1) * pageSize.value
  return chunks.value.slice(s, s + pageSize.value)
})
const editedCount = computed(() => chunks.value.filter(c => c._edited).length)

// ── 占位符解析 ────────────────────────────────────────────────────────────────
const PH_RE = /<<IMAGE:[0-9a-f]+>>/g

const parsePlaceholders = (content) => {
  if (!content) return []
  return [...content.matchAll(PH_RE)].map(m => m[0])
}

// ── contenteditable 编辑器：DOM ↔ content 互转 ────────────────────────────────

/** 把 content 字符串渲染成 editor DOM（文字节点 + 占位符 span） */
const renderEditor = (el, content, imageUrlMap, hoveredPh) => {
  if (!el) return
  el.innerHTML = ''
  const parts = content.split(/(<<IMAGE:[0-9a-f]+>>)/)
  for (const part of parts) {
    if (/^<<IMAGE:[0-9a-f]+>>$/.test(part)) {
      const span = document.createElement('span')
      span.contentEditable = 'false'
      span.dataset.placeholder = part
      span.className = 'ph-token' + (hoveredPh === part ? ' ph-token--highlight' : '')
      span.textContent = part
      span.addEventListener('mouseenter', () => {
        span.classList.add('ph-token--highlight')
      })
      span.addEventListener('mouseleave', () => {
        span.classList.remove('ph-token--highlight')
      })
      el.appendChild(span)
    } else if (part) {
      el.appendChild(document.createTextNode(part))
    }
  }
}

/** 从 editor DOM 读回 content 字符串 */
const readEditor = (el) => {
  if (!el) return ''
  let result = ''
  for (const node of el.childNodes) {
    if (node.nodeType === Node.TEXT_NODE) {
      result += node.textContent
    } else if (node.nodeType === Node.ELEMENT_NODE) {
      if (node.dataset.placeholder) {
        result += node.dataset.placeholder
      } else if (node.tagName === 'BR') {
        result += '\n'
      } else {
        result += node.textContent
      }
    }
  }
  return result
}

// ── 编辑器事件 ────────────────────────────────────────────────────────────────

const onEditorInput = (row) => {
  const el = editorRefs[row.chunk_id]
  if (!el) return
  row.content = readEditor(el)
  row._edited = true
}

const onEditorKeydown = (e) => {
  // 统一换行为 \n 文本节点，不让浏览器插入 <div> 或 <br>
  if (e.key === 'Enter') {
    e.preventDefault()
    const sel = window.getSelection()
    if (!sel.rangeCount) return
    const range = sel.getRangeAt(0)
    range.deleteContents()
    const textNode = document.createTextNode('\n')
    range.insertNode(textNode)
    range.setStartAfter(textNode)
    range.collapse(true)
    sel.removeAllRanges()
    sel.addRange(range)
    // 触发 input 事件同步 content
    textNode.parentElement?.dispatchEvent(new Event('input', { bubbles: true }))
  }
}

const onEditorPaste = (e) => {
  // 强制纯文本粘贴
  e.preventDefault()
  const text = e.clipboardData.getData('text/plain')
  const sel = window.getSelection()
  if (!sel.rangeCount) return
  const range = sel.getRangeAt(0)
  range.deleteContents()
  const textNode = document.createTextNode(text)
  range.insertNode(textNode)
  range.setStartAfter(textNode)
  range.collapse(true)
  sel.removeAllRanges()
  sel.addRange(range)
  textNode.parentElement?.dispatchEvent(new Event('input', { bubbles: true }))
}

/** 记录光标位置（用于插入图片） */
const onEditorMouseup = (row) => {
  const sel = window.getSelection()
  if (sel && sel.rangeCount) {
    row._insertPos = sel.getRangeAt(0).cloneRange()
  }
}

/** 高亮/取消高亮 editor 里指定占位符的 span */
const highlightSpan = (row, ph, on) => {
  const el = editorRefs[row.chunk_id]
  if (!el) return
  for (const span of el.querySelectorAll('span[data-placeholder]')) {
    if (span.dataset.placeholder === ph) {
      span.classList.toggle('ph-token--highlight', on)
    }
  }
}

// ── 加载 ──────────────────────────────────────────────────────────────────────

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
      _insertPos: null,   // Range 对象，记录光标位置
      _hoveredPh: null,   // 当前 hover 的占位符
      _imageUrlMap: {},
    }))
    chunks.value = rawChunks
    if (props.imageMode) {
      await loadAllImageUrls()
      await nextTick()
      // 渲染所有编辑器
      for (const row of chunks.value) {
        renderEditor(editorRefs[row.chunk_id], row.content, row._imageUrlMap, null)
      }
    }
  } catch (e) {
    ElMessage.error('加载切片失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

const loadAllImageUrls = async () => {
  // 收集当前页所有切片的占位符，一次批量请求
  const allPhs = []
  for (const row of chunks.value) {
    const phs = parsePlaceholders(row.content)
    allPhs.push(...phs)
  }
  const uniquePhs = [...new Set(allPhs)]
  if (!uniquePhs.length) return

  try {
    const res = await docApi.resolveImages(uniquePhs)
    const urlMap = res.data.data || {}
    // 原地更新每个 row 的 _imageUrlMap，不替换引用
    for (const row of chunks.value) {
      const phs = parsePlaceholders(row.content)
      for (const ph of phs) {
        if (urlMap[ph]) row._imageUrlMap[ph] = urlMap[ph]
      }
    }
  } catch (e) {
    console.warn('批量解析图片 URL 失败:', e)
  }
}

// ── 校验占位符完整性 ──────────────────────────────────────────────────────────

/** 校验 content 里每个占位符都在 _imageUrlMap 里有对应记录 */
const validatePlaceholders = (row) => {
  if (!props.imageMode) return true
  const phs = parsePlaceholders(row.content)
  const missing = phs.filter(ph => !row._imageUrlMap[ph])
  if (missing.length) {
    ElMessage.error(`切片中存在无对应图片的占位符：${missing.join(', ')}，请删除或补充图片后再保存`)
    return false
  }
  return true
}

/** 校验所有切片 */
const validateAllPlaceholders = () => {
  if (!props.imageMode) return true
  for (const row of chunks.value) {
    if (!validatePlaceholders(row)) return false
  }
  return true
}

// ── 图片管理 ──────────────────────────────────────────────────────────────────

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

const onImageFileChange = (file) => { addImageFile.value = file.raw }

const confirmAddImage = async () => {
  if (!addImageFile.value) { ElMessage.warning('请先选择图片'); return }
  addingImage.value = true
  try {
    const row = addImageRow.value
    const res = await docApi.addChunkImage(
      props.jobId, row.chunk_index, addImageFile.value, null, 0
    )
    const { placeholder, oss_url } = res.data.data

    // 在光标位置插入占位符 span
    const el = editorRefs[row.chunk_id]
    if (el && row._insertPos) {
      const range = row._insertPos
      range.deleteContents()
      const span = document.createElement('span')
      span.contentEditable = 'false'
      span.dataset.placeholder = placeholder
      span.className = 'ph-token'
      span.textContent = placeholder
      span.addEventListener('mouseenter', () => span.classList.add('ph-token--highlight'))
      span.addEventListener('mouseleave', () => span.classList.remove('ph-token--highlight'))
      range.insertNode(span)
      // 光标移到 span 后面
      const newRange = document.createRange()
      newRange.setStartAfter(span)
      newRange.collapse(true)
      const sel = window.getSelection()
      sel.removeAllRanges()
      sel.addRange(newRange)
      row._insertPos = newRange.cloneRange()
    }

    row.content = readEditor(el || null) || row.content + placeholder
    row._edited = true
    if (oss_url) row._imageUrlMap = { ...row._imageUrlMap, [placeholder]: oss_url }
    addImageDialogVisible.value = false
    ElMessage.success('图片已插入')
  } catch (e) {
    ElMessage.error('添加失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    addingImage.value = false
  }
}

// ── 切片操作 ──────────────────────────────────────────────────────────────────

const fetchChunks = async () => {
  fetching.value = true
  try {
    const res = await docApi.fetchChunks(props.jobId)
    ElMessage.success(res.data.message || '切片已获取')
    await load()
  } catch (e) {
    ElMessage.error('获取切片失败: ' + (e.response?.data?.detail || e.message))
  } finally { fetching.value = false }
}

const saveOne = async (row) => {
  if (!validatePlaceholders(row)) return
  row._saving = true
  try {
    // 找出被删除的占位符，调后端删除图片记录
    const currentPhs = new Set(parsePlaceholders(row.content))
    const deletedPhs = Object.keys(row._imageUrlMap).filter(ph => !currentPhs.has(ph))
    if (deletedPhs.length) {
      const imgRes = await docApi.getChunkImages(props.jobId, row.chunk_index)
      const images = imgRes.data.data?.images || []
      for (const ph of deletedPhs) {
        const img = images.find(i => i.placeholder === ph)
        if (img) await docApi.deleteChunkImage(props.jobId, row.chunk_index, img.id)
        const map = { ...row._imageUrlMap }
        delete map[ph]
        row._imageUrlMap = map
      }
    }
    await docApi.editChunk(props.jobId, row.chunk_index, row.content)
    row._edited = false
    ElMessage.success('保存成功')
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message))
  } finally { row._saving = false }
}

const cleanOne = async (row) => {
  row._cleaning = true
  try {
    const res = await docApi.cleanChunk(props.jobId, row.chunk_index)
    row.content = res.data.data?.content || row.content
    row._edited = false
    if (props.imageMode) {
      await nextTick()
      renderEditor(editorRefs[row.chunk_id], row.content, row._imageUrlMap, null)
    }
    ElMessage.success('清洗完成')
  } catch (e) {
    ElMessage.error('清洗失败: ' + (e.response?.data?.detail || e.message))
  } finally { row._cleaning = false }
}

const revertOne = async (row) => {
  try {
    await docApi.revertChunk(props.jobId, row.chunk_index)
    row.content = row.original_content
    row._edited = false
    if (props.imageMode) {
      await nextTick()
      renderEditor(editorRefs[row.chunk_id], row.content, row._imageUrlMap, null)
    }
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
  } finally { cleaningAll.value = false }
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
  if (!validateAllPlaceholders()) return
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
  } finally { upserting.value = false }
}

onMounted(async () => {
  await load()
  if (!props.readonly && !props.imageMode && chunks.value.length === 0) {
    await fetchChunks()
  }
})
</script>

<style scoped>
.chunk-editor {
  min-height: 80px;
  max-height: 200px;
  overflow-y: auto;
  padding: 8px 12px;
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 9px;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  outline: none;
  background: rgba(255,255,255,0.04);
  color: var(--text-primary, #f0f6ff);
  transition: border-color 0.2s, box-shadow 0.2s;
}
.chunk-editor:focus {
  border-color: #5b9eff;
  box-shadow: 0 0 0 3px rgba(79,142,247,0.2);
}
.chunk-editor[contenteditable="false"] {
  background: rgba(255,255,255,0.02);
  cursor: default;
}

/* 占位符 token */
:deep(.ph-token) {
  display: inline-block;
  padding: 1px 6px;
  margin: 0 2px;
  border-radius: 3px;
  background: rgba(79,142,247,0.15);
  border: 1px solid rgba(79,142,247,0.35);
  color: #7eb3ff;
  font-size: 12px;
  cursor: default;
  user-select: none;
  transition: background 0.15s, border-color 0.15s;
}
:deep(.ph-token--highlight) {
  background: rgba(245,166,35,0.15);
  border-color: rgba(245,166,35,0.5);
  color: #fbbf24;
}

/* 图片预览 */
.image-preview-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 4px;
  border-radius: 4px;
  border: 2px solid transparent;
  transition: border-color 0.15s;
  cursor: pointer;
}
.image-preview-item:hover,
.image-highlight {
  border-color: #f5a623;
}
</style>
