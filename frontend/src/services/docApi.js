import axios from 'axios'

const BASE = 'http://localhost:8000/api/v1'

export const docApi = {
  // ── 文档 ──────────────────────────────────────────────────────────────────
  uploadDocument: (formData) => axios.post(`${BASE}/documents/upload`, formData),
  uploadDocumentToCategory: (formData) => axios.post(`${BASE}/documents/upload-to-category`, formData),
  batchUploadToCategory: (formData) => axios.post(`${BASE}/documents/batch-upload-to-category`, formData),
  searchDocuments: (formData) => axios.post(`${BASE}/documents/search`, formData),
  startChunking: (categoryId, params = {}) =>
    axios.post(`${BASE}/documents/start-chunking/${categoryId}`, null, { params }),

  // ── Job ───────────────────────────────────────────────────────────────────
  listJobs: (kbName, limit = 200) => axios.get(`${BASE}/jobs`, { params: { kb_name: kbName, limit } }),
  getJob: (jobId) => axios.get(`${BASE}/jobs/${encodeURIComponent(jobId)}`),
  upsertJob: (jobId) => axios.post(`${BASE}/jobs/${encodeURIComponent(jobId)}/upsert`),

  // ── 切片 ──────────────────────────────────────────────────────────────────
  getChunksByJob: (jobId) => axios.get(`${BASE}/chunks/job/${encodeURIComponent(jobId)}`),
  // 单个切片操作：用 job_id + chunk_index 定位
  editChunk: (jobId, chunkIndex, content) =>
    axios.put(`${BASE}/chunks/job/${encodeURIComponent(jobId)}/chunk/${chunkIndex}`, { content }),
  cleanChunk: (jobId, chunkIndex, instruction) => {
    const fd = new FormData()
    if (instruction) fd.append('instruction', instruction)
    return axios.post(`${BASE}/chunks/job/${encodeURIComponent(jobId)}/chunk/${chunkIndex}/clean`, fd)
  },
  revertChunk: (jobId, chunkIndex) =>
    axios.post(`${BASE}/chunks/job/${encodeURIComponent(jobId)}/chunk/${chunkIndex}/revert`),
  // 批量操作：按 job_id
  cleanJobChunks: (jobId, instruction) => axios.post(`${BASE}/chunks/job/${encodeURIComponent(jobId)}/clean`, { instruction }),
  revertJobChunks: (jobId) => axios.post(`${BASE}/chunks/job/${encodeURIComponent(jobId)}/revert`),
  cleanAllChunks: (instruction) => axios.post(`${BASE}/chunks/clean-all`, { instruction }),
  revertAllChunks: () => axios.post(`${BASE}/chunks/revert-all`),
  upsertJobChunks: (jobId) => axios.post(`${BASE}/chunks/job/${encodeURIComponent(jobId)}/upsert`),
  batchUpsertJobs: (jobIds) => axios.post(`${BASE}/chunks/batch-upsert`, { job_ids: jobIds }),

  // ── 切片图片管理 ──────────────────────────────────────────────────────────
  getChunkImages: (jobId, chunkIndex) =>
    axios.get(`${BASE}/chunks/job/${encodeURIComponent(jobId)}/chunk/${chunkIndex}/images`),
  addChunkImage: (jobId, chunkIndex, file, page, insertPosition = 0) => {
    const fd = new FormData()
    fd.append('file', file)
    if (page != null) fd.append('page', page)
    fd.append('insert_position', insertPosition)
    return axios.post(`${BASE}/chunks/job/${encodeURIComponent(jobId)}/chunk/${chunkIndex}/images`, fd)
  },
  deleteChunkImage: (jobId, chunkIndex, imageId) =>
    axios.delete(`${BASE}/chunks/job/${encodeURIComponent(jobId)}/chunk/${chunkIndex}/images/${imageId}`),

  // ── 文件 ──────────────────────────────────────────────────────────────────
  listFiles: (params = {}) => axios.get(`${BASE}/files`, { params }),
  deleteFile: (fileId) => axios.delete(`${BASE}/files`, { data: { file_id: fileId } }),
  batchDeleteFiles: (fileIds, kbName) =>
    axios.post(`${BASE}/files/batch-delete`, { file_ids: fileIds, kb_name: kbName }),

  // ── 类目 ──────────────────────────────────────────────────────────────────
  listCategories: () => axios.get(`${BASE}/categories`),
  createCategory: (data) => axios.post(`${BASE}/categories`, data),
  getCategory: (id) => axios.get(`${BASE}/categories/${id}`),
  updateCategory: (id, data) => axios.put(`${BASE}/categories/${id}`, data),
  deleteCategory: (id) => axios.delete(`${BASE}/categories/${id}`),
  deleteCategoryFile: (categoryId, fileId) => axios.delete(`${BASE}/categories/${categoryId}/files/${fileId}`),
  batchDeleteCategoryFiles: (categoryId, fileIds) =>
    axios.post(`${BASE}/categories/${categoryId}/files/batch-delete`, { file_ids: fileIds }),

  // ── Admin ─────────────────────────────────────────────────────────────────
  listCollections: () => axios.get(`${BASE}/admin/collections`),
  createCollection: (data) => axios.post(`${BASE}/admin/collections`, data),
  updateCollection: (kbName, data) => axios.put(`${BASE}/admin/collections/${kbName}`, data),
  deleteCollection: (kbName) => axios.delete(`${BASE}/admin/collections/${kbName}`),

  // ── 图片占位符解析 ────────────────────────────────────────────────────────
  resolveImages: (placeholders) =>
    axios.post(`${BASE}/chunks/resolve-images`, { placeholders }),

  // ── 对话会话 ──────────────────────────────────────────────────────────────
  listSessions: (kbName, userId = 'default') =>
    axios.get(`${BASE}/conversations`, { params: { kb_name: kbName, user_id: userId } }),
  createSession: (kbName, title = '新会话', userId = 'default') =>
    axios.post(`${BASE}/conversations`, { kb_name: kbName, title, user_id: userId }),
  getSessionMessages: (sessionId, limit = 100) =>
    axios.get(`${BASE}/conversations/${sessionId}/messages`, { params: { limit } }),
  deleteSession: (sessionId) =>
    axios.delete(`${BASE}/conversations/${sessionId}`),
}
