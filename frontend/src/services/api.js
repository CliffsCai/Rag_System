import axios from 'axios'

// Create axios instance
const api = axios.create({
  baseURL: '/api/v1',  // 更新为新的 API 路径
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// Request interceptor
api.interceptors.request.use(
  (config) => {
    console.log('API Request:', config.method?.toUpperCase(), config.url, config.data)
    return config
  },
  (error) => {
    console.error('Request Error:', error)
    return Promise.reject(error)
  }
)

// Response interceptor
api.interceptors.response.use(
  (response) => {
    console.log('API Response:', response.status, response.data)
    return response
  },
  (error) => {
    console.error('Response Error:', error.response?.status, error.response?.data || error.message)
    return Promise.reject(error)
  }
)

// API service methods
export const apiService = {
  // Health check
  async healthCheck() {
    const response = await api.get('/health')
    return response.data
  },

  // Get available models
  async getModels() {
    const response = await api.get('/models')
    return response.data
  },

  // Chat with agent
  async chat(messages, model = null, temperature = null) {
    const payload = { messages }
    if (model) payload.model = model
    if (temperature !== null) payload.temperature = temperature
    
    const response = await api.post('/chat', payload)  // 对应 /api/v1/chat
    return response.data
  },

  // Knowledge base query
  async knowledgeQuery(query, sessionId = 'default', model = null, collection = null, forceMultiDoc = null, keywordFilter = null, queryImage = null) {
    const payload = { query, session_id: sessionId }
    if (model) payload.model = model
    if (collection) payload.collection = collection
    if (forceMultiDoc != null) payload.force_multi_doc = forceMultiDoc
    if (keywordFilter) payload.keyword_filter = keywordFilter
    if (queryImage) payload.query_image = queryImage

    const response = await api.post('/knowledge', payload)
    return response.data
  },

  /**
   * Knowledge SSE（POST /knowledge/stream）。handlers: { onMeta, onDelta, onDone, onError }，均为可选。
   */
  async knowledgeQueryStream(payload, handlers = {}, signal = undefined) {
    const body = {
      query: payload.query,
      session_id: payload.session_id ?? 'default',
      ...(payload.model && { model: payload.model }),
      ...(payload.collection != null && { collection: payload.collection }),
      ...(payload.force_multi_doc != null && { force_multi_doc: payload.force_multi_doc }),
      ...(payload.keyword_filter && { keyword_filter: payload.keyword_filter }),
      ...(payload.query_image && { query_image: payload.query_image }),
    }
    const res = await fetch('/api/v1/knowledge/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        // 避免中间层对响应做 gzip，导致整段缓冲后才解压、前端收不到增量
        'Accept-Encoding': 'identity',
      },
      body: JSON.stringify(body),
      signal,
    })
    if (!res.ok) {
      const err = new Error(`stream HTTP ${res.status}`)
      handlers.onError?.(err)
      throw err
    }
    const reader = res.body.getReader()
    const decoder = new TextDecoder('utf-8')

    const normalizeLf = (s) => s.replace(/\r\n/g, '\n').replace(/\r/g, '\n')

    const dispatchSseBlock = (blockRaw) => {
      const block = blockRaw.trim()
      if (!block) return
      let ev = null
      let dataStr = null
      for (const line of block.split('\n')) {
        const L = line.trimEnd()
        if (L.startsWith('event:')) ev = L.slice(6).trim()
        else if (L.startsWith('data:')) dataStr = L.slice(5).trim()
      }
      if (dataStr == null) return
      let data
      try {
        data = JSON.parse(dataStr)
      } catch (e) {
        handlers.onError?.(e)
        return
      }
      if (ev === 'meta') handlers.onMeta?.(data)
      else if (ev === 'delta') handlers.onDelta?.(data)
      else if (ev === 'done') handlers.onDone?.(data)
      else if (ev === 'error') handlers.onError?.(new Error(data.message || 'stream error'))
    }

    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (value) buffer += decoder.decode(value, { stream: !done })
      if (done) {
        buffer += decoder.decode()
        buffer = normalizeLf(buffer)
        let sep
        while ((sep = buffer.indexOf('\n\n')) >= 0) {
          const block = buffer.slice(0, sep)
          buffer = buffer.slice(sep + 2)
          dispatchSseBlock(block)
        }
        if (buffer.trim()) dispatchSseBlock(buffer)
        break
      }
      buffer = normalizeLf(buffer)
      let sep
      while ((sep = buffer.indexOf('\n\n')) >= 0) {
        const block = buffer.slice(0, sep)
        buffer = buffer.slice(sep + 2)
        dispatchSseBlock(block)
      }
    }
  },

  // Knowledge base QA (alias for better naming)
  async knowledgeQA(query, model = null, sessionId = 'default', collection = null, forceMultiDoc = null, keywordFilter = null, queryImage = null) {
    return this.knowledgeQuery(query, sessionId, model, collection, forceMultiDoc, keywordFilter, queryImage)
  },

  // Generic API call for testing
  async genericCall(method, endpoint, data = null) {
    const config = { method, url: endpoint }
    if (data) config.data = data
    
    const response = await api(config)
    return response.data
  }
}

export default api