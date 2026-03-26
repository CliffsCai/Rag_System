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
  async knowledgeQuery(query, sessionId = 'default', model = null, collection = null) {
    const payload = { query, session_id: sessionId }
    if (model) payload.model = model
    if (collection) payload.collection = collection
    
    const response = await api.post('/knowledge', payload)
    return response.data
  },

  // Knowledge base QA (alias for better naming)
  async knowledgeQA(query, model = null, sessionId = 'default', collection = null) {
    return this.knowledgeQuery(query, sessionId, model, collection)
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