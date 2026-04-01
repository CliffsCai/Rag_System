<template>
  <div class="chat-wrapper">
    <!-- 知识库模式：会话侧边栏 -->
    <transition name="sidebar-slide">
      <div v-if="chatMode === 'knowledge' && sidebarOpen" class="session-sidebar">
        <div class="sidebar-header">
          <span class="sidebar-title">对话列表</span>
          <button class="sidebar-new-btn" @click="createNewSession" :disabled="!selectedCollection">
            <svg viewBox="0 0 16 16" fill="none"><line x1="8" y1="2" x2="8" y2="14" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><line x1="2" y1="8" x2="14" y2="8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
            新建
          </button>
        </div>
        <div class="session-list">
          <div v-if="sessions.length === 0" class="session-empty">暂无会话</div>
          <div
            v-for="s in sessions" :key="s.id"
            class="session-item" :class="{ active: currentSessionId === s.id }"
            @click="switchSession(s)"
          >
            <div class="session-item-title">{{ s.title }}</div>
            <div class="session-item-meta">{{ s.message_count }} 条 · {{ formatSessionTime(s.updated_at) }}</div>
            <button class="session-delete-btn" @click.stop="deleteSession(s.id)" title="删除会话">
              <svg viewBox="0 0 10 10" fill="none"><line x1="1" y1="1" x2="9" y2="9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><line x1="9" y1="1" x2="1" y2="9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
            </button>
          </div>
        </div>
      </div>
    </transition>

    <div class="chat-main" :class="{ 'sidebar-expanded': chatMode === 'knowledge' && sidebarOpen }">
    <!-- Toolbar -->
    <div class="chat-toolbar">
      <div class="mode-tabs">
        <button v-if="chatMode === 'knowledge'" class="icon-btn sidebar-toggle-btn"
          :class="{ active: sidebarOpen }" @click="sidebarOpen = !sidebarOpen" title="会话列表">
          <svg viewBox="0 0 16 16" fill="none">
            <rect x="1" y="2" width="5" height="12" rx="1" stroke="currentColor" stroke-width="1.3"/>
            <line x1="9" y1="5" x2="15" y2="5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
            <line x1="9" y1="8" x2="15" y2="8" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
            <line x1="9" y1="11" x2="13" y2="11" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
          </svg>
        </button>
        <button v-for="m in modes" :key="m.value"
          class="mode-tab" :class="{ active: chatMode === m.value }"
          @click="chatMode = m.value">
          <el-icon><component :is="m.icon" /></el-icon>
          <span>{{ m.label }}</span>
          <span v-if="chatMode === m.value" class="mode-tab-glow" />
        </button>
      </div>
      <div class="toolbar-right">
        <template v-if="chatMode === 'knowledge'">
          <div class="collection-select-wrap">
            <el-icon class="col-icon"><data-analysis /></el-icon>
            <el-select v-model="selectedCollection" size="small" placeholder="选择知识库"
              style="width:180px" @change="clearMessages">
              <el-option v-for="col in collections" :key="col.name"
                :label="col.display_name || col.name" :value="col.name" />
            </el-select>
          </div>
          <span v-if="collections.length === 0" class="no-kb-hint">暂无知识库</span>
          <div class="kb-options">
            <el-tooltip content="开启后跳过 LLM 分类，直接使用多文档分组搜索" placement="bottom" :show-after="400">
              <button class="opt-pill" :class="{ active: forceMultiDoc }" @click="forceMultiDoc = !forceMultiDoc">
                <span class="opt-pill-dot" />
                <svg class="opt-pill-icon" viewBox="0 0 16 16" fill="none">
                  <rect x="1" y="3" width="6" height="4" rx="1" stroke="currentColor" stroke-width="1.3"/>
                  <rect x="9" y="3" width="6" height="4" rx="1" stroke="currentColor" stroke-width="1.3"/>
                  <rect x="1" y="9" width="6" height="4" rx="1" stroke="currentColor" stroke-width="1.3"/>
                  <rect x="9" y="9" width="6" height="4" rx="1" stroke="currentColor" stroke-width="1.3"/>
                </svg>
                <span>多文档</span>
                <span class="opt-pill-glow" />
              </button>
            </el-tooltip>

            <el-tooltip content="开启后使用关键词精确预过滤，适合错误码、型号等精确匹配场景" placement="bottom" :show-after="400">
              <button class="opt-pill" :class="{ active: keywordFilterEnabled }" @click="toggleKeywordFilter">
                <span class="opt-pill-dot" />
                <svg class="opt-pill-icon" viewBox="0 0 16 16" fill="none">
                  <circle cx="6.5" cy="6.5" r="4" stroke="currentColor" stroke-width="1.3"/>
                  <line x1="9.5" y1="9.5" x2="14" y2="14" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
                  <line x1="4.5" y1="6.5" x2="8.5" y2="6.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
                  <line x1="6.5" y1="4.5" x2="6.5" y2="8.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
                </svg>
                <span>关键词</span>
                <span class="opt-pill-glow" />
              </button>
            </el-tooltip>

            <transition name="kw-slide">
              <div v-if="keywordFilterEnabled" class="kw-input-wrap">
                <svg class="kw-input-icon" viewBox="0 0 16 16" fill="none">
                  <path d="M2 4h12M4 8h8M6 12h4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
                </svg>
                <input
                  v-model="keywordFilter"
                  class="kw-input"
                  placeholder="精确匹配词…"
                  @keydown.escape="toggleKeywordFilter"
                />
                <button v-if="keywordFilter" class="kw-clear" @click="keywordFilter = ''">
                  <svg viewBox="0 0 10 10" fill="none"><line x1="1" y1="1" x2="9" y2="9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><line x1="9" y1="1" x2="1" y2="9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
                </button>
              </div>
            </transition>
          </div>
        </template>
        <div class="mode-badge" :class="chatMode">
          {{ chatMode === 'general' ? 'Multi-Agent' : 'RAG + Rerank' }}
        </div>
        <button class="icon-btn" @click="clearMessages" title="清空对话">
          <el-icon><delete /></el-icon>
        </button>
      </div>
    </div>

    <!-- Messages -->
    <div class="messages" ref="messagesContainer" @click="e => { if (e.target.tagName === 'IMG') openLightbox(e.target.src) }">
      <!-- Welcome screen -->
      <transition name="fade">
        <div v-if="messages.length === 0" class="welcome-screen">
          <div class="welcome-orb">
            <div class="orb-ring" />
            <div class="orb-ring orb-ring-2" />
            <el-icon class="orb-icon"><cpu /></el-icon>
          </div>
          <h2 class="welcome-title">{{ chatMode === 'knowledge' ? 'Knowledge Assistant' : 'AI Assistant' }}</h2>
          <p class="welcome-sub">{{ chatMode === 'knowledge' ? '基于企业知识库，智能检索 + Rerank 重排序' : '多工具智能体，支持邮件、搜索等工具调用' }}</p>
          <div class="suggestion-grid">
            <button v-for="s in suggestions[chatMode]" :key="s" class="suggestion-card" @click="useSuggestion(s)">
              <el-icon><arrow-right /></el-icon>
              <span>{{ s }}</span>
            </button>
          </div>
        </div>
      </transition>

      <!-- Message list -->
      <transition-group name="msg" tag="div">
        <div v-for="(msg, i) in messages" :key="i" :class="['msg-row', msg.role]">
          <div v-if="msg.role === 'assistant'" class="ai-avatar">
            <div class="ai-avatar-ring" />
            <div class="ai-avatar-bg" />
            <el-icon class="ai-avatar-icon"><cpu /></el-icon>
          </div>
          <div v-else class="user-avatar"><span>我</span></div>

          <div class="bubble-wrap">
            <div class="bubble" :class="msg.role">
              <div class="bubble-text" v-if="!msg.isHtml" style="white-space:pre-wrap">{{ msg.content }}</div>
              <div class="bubble-text" v-else v-html="msg.content" />

              <!-- Tools -->
              <div v-if="msg.tools_used?.length" class="meta-row">
                <el-icon style="font-size:10px"><tools /></el-icon>
                <span class="meta-label">Tools:</span>
                <span v-for="t in msg.tools_used" :key="t" class="tool-chip">{{ t }}</span>
              </div>

              <!-- Sources collapsible -->
              <div v-if="msg.sources?.length" class="sources-section">
                <button class="sources-toggle" @click="msg._showSources = !msg._showSources">
                  <el-icon><document /></el-icon>
                  <span>{{ uniqueFileNames(msg.sources).length }} 个来源</span>
                  <span class="sources-count">{{ msg.sources.length }} 切片</span>
                  <el-icon class="toggle-arrow" :class="{ open: msg._showSources }"><arrow-down /></el-icon>
                </button>
                <transition name="expand">
                  <div v-if="msg._showSources" class="sources-list">
                    <div v-for="(name, si) in uniqueFileNames(msg.sources)" :key="si" class="source-card">
                      <div class="source-dot" />
                      <span class="source-name">{{ name }}</span>
                    </div>
                  </div>
                </transition>
              </div>

              <!-- Confidence arc -->
              <div v-if="msg.confidence !== undefined && msg.confidence !== null && msg.role === 'assistant'" class="confidence-row">
                <svg class="conf-arc" viewBox="0 0 60 34" fill="none">
                  <path d="M5 30 A25 25 0 0 1 55 30" stroke="rgba(255,255,255,0.08)" stroke-width="5" stroke-linecap="round"/>
                  <path d="M5 30 A25 25 0 0 1 55 30"
                    :stroke="confColor(msg.confidence)" stroke-width="5" stroke-linecap="round"
                    :stroke-dasharray="`${msg.confidence * 78.5} 78.5`" style="transition:stroke-dasharray 1s ease"/>
                  <text x="30" y="30" text-anchor="middle" font-size="9" :fill="confColor(msg.confidence)" font-weight="700">
                    {{ Math.round(msg.confidence * 100) }}%
                  </text>
                </svg>
                <span class="conf-label">置信度</span>
              </div>
            </div>
            <div class="msg-time">{{ formatTime(msg.timestamp) }}</div>
          </div>
        </div>
      </transition-group>

      <!-- Typing indicator -->
      <transition name="fade">
        <div v-if="loading" class="msg-row assistant">
          <div class="ai-avatar">
            <div class="ai-avatar-ring pulsing" />
            <div class="ai-avatar-bg" />
            <el-icon class="ai-avatar-icon"><cpu /></el-icon>
          </div>
          <div class="bubble-wrap">
            <div class="bubble assistant typing-bubble">
              <div class="wave-bar" /><div class="wave-bar" /><div class="wave-bar" />
            </div>
          </div>
        </div>
      </transition>
    </div>

    <!-- Input area -->
    <div class="input-area" :class="{ focused: inputFocused }">
      <div class="input-wrap">
        <el-input v-model="inputMessage" type="textarea"
          :autosize="{ minRows: 1, maxRows: 5 }"
          placeholder="输入消息... (Enter 发送，Shift+Enter 换行)"
          :disabled="loading"
          @keydown.enter.exact.prevent="sendMessage"
          @focus="inputFocused = true" @blur="inputFocused = false"
          resize="none" />
        <span class="char-count" :class="{ warn: inputMessage.length > 800 }">{{ inputMessage.length }}</span>
      </div>
      <button class="send-btn" :class="{ loading, disabled: !canSend }" :disabled="!canSend" @click="sendMessage">
        <transition name="icon-swap" mode="out-in">
          <span v-if="!loading" key="send" class="send-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <line x1="22" y1="2" x2="11" y2="13"/>
              <polygon points="22 2 15 22 11 13 2 9 22 2"/>
            </svg>
          </span>
          <span v-else key="spin" class="spin-ring" />
        </transition>
      </button>
    </div>
  </div><!-- end chat-main -->
  </div><!-- end chat-wrapper -->

  <!-- Lightbox -->
  <teleport to="body">
    <transition name="lightbox-fade">
      <div v-if="lightbox.show" class="lightbox-overlay" @click="lightbox.show = false">
        <button class="lightbox-close" @click="lightbox.show = false">
          <svg viewBox="0 0 16 16" fill="none"><line x1="2" y1="2" x2="14" y2="14" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><line x1="14" y1="2" x2="2" y2="14" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
        </button>
        <img :src="lightbox.src" class="lightbox-img" @click.stop />
      </div>
    </transition>
  </teleport>
</template>

<script setup>
import { ref, computed, nextTick, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { apiService } from '../services/api'
import { docApi } from '../services/docApi'
import axios from 'axios'
import MarkdownIt from 'markdown-it'

const md = new MarkdownIt({ html: false, linkify: true, typographer: true, breaks: true })
const API = 'http://localhost:8000/api/v1'
const props = defineProps({ model: { type: String, default: 'qwen-turbo' } })

const chatMode = ref('general')
const selectedCollection = ref('')
const collections = ref([])
const messages = ref([])
const inputMessage = ref('')
const loading = ref(false)
const inputFocused = ref(false)
const messagesContainer = ref(null)

// knowledge 模式选项
const forceMultiDoc = ref(false)
const keywordFilterEnabled = ref(false)
const keywordFilter = ref('')
const toggleKeywordFilter = () => {
  keywordFilterEnabled.value = !keywordFilterEnabled.value
  if (!keywordFilterEnabled.value) keywordFilter.value = ''
}

// 会话管理
const sidebarOpen = ref(true)
const sessions = ref([])
const currentSessionId = ref('')

// Lightbox
const lightbox = ref({ show: false, src: '' })
const openLightbox = (src) => { lightbox.value = { show: true, src } }

// 键盘关闭 lightbox
const onKeydown = (e) => { if (e.key === 'Escape') lightbox.value.show = false }
window.addEventListener('keydown', onKeydown)

const formatSessionTime = (ts) => {
  if (!ts) return ''
  const d = new Date(ts)
  const now = new Date()
  const diff = now - d
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`
  return d.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
}

// 图片 URL 缓存，key=placeholder，value={url, expiresAt}
// 使用 sessionStorage 持久化到标签页生命周期，关闭即清空
const IMAGE_CACHE_TTL = 50 * 60 * 1000 // 50分钟，比 OSS 预签名 1小时短

const getCachedUrl = (ph) => {
  try {
    const raw = sessionStorage.getItem(`img_cache:${ph}`)
    if (!raw) return null
    const { url, expiresAt } = JSON.parse(raw)
    if (Date.now() > expiresAt) { sessionStorage.removeItem(`img_cache:${ph}`); return null }
    return url
  } catch { return null }
}

const setCachedUrl = (ph, url) => {
  try {
    sessionStorage.setItem(`img_cache:${ph}`, JSON.stringify({ url, expiresAt: Date.now() + IMAGE_CACHE_TTL }))
  } catch {} // sessionStorage 满了也不影响功能
}

const loadSessions = async () => {
  if (!selectedCollection.value) return
  try {
    const res = await docApi.listSessions(selectedCollection.value)
    sessions.value = res.data.data?.sessions || []
  } catch (e) {
    console.warn('加载会话列表失败:', e)
  }
}

const createNewSession = async () => {
  if (!selectedCollection.value) return
  try {
    const res = await docApi.createSession(selectedCollection.value)
    const session = res.data.data
    sessions.value.unshift(session)
    await switchSession(session)
  } catch (e) {
    ElMessage.error('创建会话失败')
  }
}

const switchSession = async (session) => {
  if (currentSessionId.value === session.id) return
  currentSessionId.value = session.id
  messages.value = []
  // 加载历史消息
  try {
    const res = await docApi.getSessionMessages(session.id)
    const histMsgs = res.data.data?.messages || []
    if (!histMsgs.length) return

    // 收集所有占位符，批量 resolve（优先读缓存，只请求后端未缓存的）
    const allPhs = []
    for (const m of histMsgs) {
      if (m.image_placeholders?.length) allPhs.push(...m.image_placeholders)
    }
    let urlMap = {}
    if (allPhs.length) {
      const uniquePhs = [...new Set(allPhs)]
      const missedPhs = []
      for (const ph of uniquePhs) {
        const cached = getCachedUrl(ph)
        if (cached) urlMap[ph] = cached
        else missedPhs.push(ph)
      }
      if (missedPhs.length) {
        try {
          const rr = await docApi.resolveImages(missedPhs)
          const fresh = rr.data.data || {}
          for (const [ph, url] of Object.entries(fresh)) {
            urlMap[ph] = url
            setCachedUrl(ph, url)
          }
        } catch {}
      }
    }

    for (const m of histMsgs) {
      let content = m.content
      // 替换占位符为图片 markdown
      if (m.image_placeholders?.length) {
        for (const ph of m.image_placeholders) {
          if (urlMap[ph]) content = content.split(ph).join(`\n![image](${urlMap[ph]})\n`)
        }
      }
      messages.value.push({
        role: m.role,
        isHtml: m.role === 'assistant',
        content: m.role === 'assistant' ? md.render(content) : content,
        confidence: m.confidence,
        sources: m.sources || [],
        _showSources: false,
        timestamp: new Date(m.created_at),
      })
    }
    scrollToBottom()
  } catch (e) {
    console.warn('加载历史消息失败:', e)
  }
}

const deleteSession = async (sessionId) => {
  try {
    await docApi.deleteSession(sessionId)
    sessions.value = sessions.value.filter(s => s.id !== sessionId)
    if (currentSessionId.value === sessionId) {
      currentSessionId.value = ''
      messages.value = []
    }
    ElMessage.success('会话已删除')
  } catch (e) {
    ElMessage.error('删除失败')
  }
}

const modes = [
  { value: 'general',   label: '普通对话', icon: 'Cpu' },
  { value: 'knowledge', label: '知识库',   icon: 'Document' },
]
const suggestions = {
  general:   ['你能做什么？', '帮我搜索最新资讯', '发送一封邮件'],
  knowledge: ['如何接受21V的Guest邀请？', '我换了新手机如何重新配置MFA认证？', '阿里网约车如何操作？'],
}

const canSend = computed(() =>
  inputMessage.value.trim() && !loading.value &&
  !(chatMode.value === 'knowledge' && !selectedCollection.value)
)
const confColor = (c) => c > 0.7 ? '#2dd4a0' : c > 0.4 ? '#f5c842' : '#f06b6b'
const scrollToBottom = () => nextTick(() => {
  if (messagesContainer.value) messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
})
const useSuggestion = (text) => { inputMessage.value = text; sendMessage() }

const sendMessage = async () => {
  const text = inputMessage.value.trim()
  if (!canSend.value || !text) return
  messages.value.push({ role: 'user', content: text, timestamp: new Date() })
  inputMessage.value = ''
  loading.value = true
  scrollToBottom()
  try {
    if (chatMode.value === 'knowledge') {
      const res = await apiService.knowledgeQA(
        text, props.model, currentSessionId.value || 'default', selectedCollection.value || null,
        forceMultiDoc.value || null,
        (keywordFilterEnabled.value && keywordFilter.value) ? keywordFilter.value : null,
      )
      const imageMap = res.image_map || {}
      let raw = res.answer || '抱歉，未收到有效回复。'
      Object.entries(imageMap).forEach(([ph, url]) => { raw = raw.split(ph).join(`\n![image](${url})\n`) })
      messages.value.push({
        role: 'assistant', isHtml: true, content: md.render(raw),
        confidence: res.confidence, sources: res.sources || [], _showSources: false, timestamp: new Date(),
      })
    } else {
      const apiMsgs = messages.value.map(m => ({ role: m.role, content: m.content }))
      const res = await apiService.chat(apiMsgs, props.model)
      const last = res.messages?.[res.messages.length - 1]
      const toolsUsed = res.usage?.tools_used || []
      messages.value.push({
        role: 'assistant', isHtml: true,
        content: md.render(last?.content || '抱歉，未收到有效回复。'),
        tools_used: toolsUsed, timestamp: new Date(),
      })
      if (toolsUsed.length) ElMessage.success(`调用工具: ${toolsUsed.join(', ')}`)
    }
  } catch (e) {
    console.error(e); ElMessage.error('发送失败')
    messages.value.push({ role: 'assistant', content: '抱歉，发生错误，请稍后重试。', timestamp: new Date() })
  } finally { loading.value = false; scrollToBottom() }
}

const clearMessages = () => { messages.value = []; currentSessionId.value = '' }
watch(chatMode, () => { messages.value = []; currentSessionId.value = '' })
watch(selectedCollection, async (val) => {
  messages.value = []
  currentSessionId.value = ''
  if (val) await loadSessions()
})
const formatTime = (t) => new Date(t).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
const uniqueFileNames = (sources) => {
  const seen = new Set()
  return sources.reduce((acc, s) => {
    const name = s.file_name || s.title || s.id || '未知来源'
    if (!seen.has(name)) { seen.add(name); acc.push(name) }
    return acc
  }, [])
}

onMounted(async () => {
  try {
    const { data } = await axios.get(`${API}/admin/collections`)
    collections.value = data.data?.collections || []
    if (collections.value.length > 0) {
      selectedCollection.value = collections.value[0].name
      await loadSessions()
    }
  } catch {}
})
defineExpose({ clearMessages })
</script>

<style scoped>
/* ── Layout ── */
.chat-wrapper {
  display: flex; flex-direction: row;
  height: calc(100vh - 108px);
  background: rgba(255,255,255,0.025);
  border: 1px solid rgba(255,255,255,0.09);
  border-radius: 18px; overflow: hidden;
  box-shadow: 0 8px 40px rgba(0,0,0,0.35), 0 0 0 1px rgba(255,255,255,0.04) inset;
}
.chat-main {
  display: flex; flex-direction: column; flex: 1; min-width: 0;
}

/* ── Session Sidebar ── */
.session-sidebar {
  width: 200px; flex-shrink: 0;
  display: flex; flex-direction: column;
  background: rgba(0,0,0,0.15);
  border-right: 1px solid rgba(255,255,255,0.06);
}
.sidebar-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 12px 8px;
  border-bottom: 1px solid rgba(255,255,255,0.05);
}
.sidebar-title { font-size: 12px; font-weight: 600; color: rgba(255,255,255,0.4); letter-spacing: 0.5px; }
.sidebar-new-btn {
  display: flex; align-items: center; gap: 4px;
  padding: 3px 8px; border-radius: 6px; border: none; cursor: pointer;
  font-size: 11px; font-weight: 600; color: #7eb3ff;
  background: rgba(79,142,247,0.12);
  transition: background 0.2s;
}
.sidebar-new-btn:hover { background: rgba(79,142,247,0.22); }
.sidebar-new-btn:disabled { opacity: 0.3; cursor: not-allowed; }
.sidebar-new-btn svg { width: 10px; height: 10px; }
.session-list { flex: 1; overflow-y: auto; padding: 6px 6px; }
.session-list::-webkit-scrollbar { width: 3px; }
.session-list::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.07); border-radius: 99px; }
.session-empty { font-size: 11px; color: rgba(255,255,255,0.2); text-align: center; padding: 20px 0; }
.session-item {
  position: relative; padding: 8px 10px; border-radius: 8px; cursor: pointer;
  margin-bottom: 2px;
  transition: background 0.15s;
}
.session-item:hover { background: rgba(255,255,255,0.05); }
.session-item.active { background: rgba(79,142,247,0.12); }
.session-item-title {
  font-size: 12px; font-weight: 500; color: rgba(255,255,255,0.7);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  padding-right: 18px;
}
.session-item-meta { font-size: 10px; color: rgba(255,255,255,0.25); margin-top: 2px; }
.session-delete-btn {
  position: absolute; right: 6px; top: 50%; transform: translateY(-50%);
  width: 16px; height: 16px; border-radius: 4px; border: none; cursor: pointer;
  background: transparent; color: rgba(255,255,255,0.2);
  display: flex; align-items: center; justify-content: center; padding: 2px;
  opacity: 0; transition: opacity 0.15s, background 0.15s, color 0.15s;
}
.session-item:hover .session-delete-btn { opacity: 1; }
.session-delete-btn:hover { background: rgba(240,107,107,0.2); color: #f06b6b; }
.session-delete-btn svg { width: 100%; height: 100%; }
.sidebar-toggle-btn { margin-right: 4px; }
.sidebar-toggle-btn.active { color: #7eb3ff; background: rgba(79,142,247,0.12); }

/* sidebar slide transition */
.sidebar-slide-enter-active { transition: width 0.25s cubic-bezier(0.4,0,0.2,1), opacity 0.2s; }
.sidebar-slide-leave-active { transition: width 0.2s cubic-bezier(0.4,0,1,1), opacity 0.15s; }
.sidebar-slide-enter-from { width: 0; opacity: 0; }
.sidebar-slide-leave-to { width: 0; opacity: 0; }

/* ── Toolbar ── */
.chat-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 16px;
  background: rgba(255,255,255,0.02);
  border-bottom: 1px solid rgba(255,255,255,0.06);
  flex-shrink: 0;
}
.mode-tabs { display: flex; gap: 4px; }
.mode-tab {
  position: relative; display: flex; align-items: center; gap: 6px;
  padding: 6px 14px; border-radius: 9px; border: none; cursor: pointer;
  font-size: 13px; font-weight: 500; color: rgba(255,255,255,0.35);
  background: transparent; transition: all 0.2s; overflow: hidden;
}
.mode-tab:hover { color: rgba(255,255,255,0.65); background: rgba(255,255,255,0.05); }
.mode-tab.active { color: #7eb3ff; background: rgba(79,142,247,0.12); }
.mode-tab-glow {
  position: absolute; inset: 0; border-radius: 9px;
  box-shadow: inset 0 0 0 1px rgba(79,142,247,0.35);
  pointer-events: none;
}
.toolbar-right { display: flex; align-items: center; gap: 10px; }
.collection-select-wrap { display: flex; align-items: center; gap: 6px; }
.col-icon { color: rgba(255,255,255,0.3); font-size: 14px; }
.no-kb-hint { font-size: 11px; color: #f06b6b; }
.kb-options { display: flex; align-items: center; gap: 6px; }

/* ── opt-pill toggle ── */
.opt-pill {
  position: relative; display: flex; align-items: center; gap: 5px;
  padding: 4px 10px 4px 8px; border-radius: 99px; border: none; cursor: pointer;
  font-size: 11px; font-weight: 600; letter-spacing: 0.3px;
  color: rgba(255,255,255,0.3);
  background: rgba(255,255,255,0.04);
  box-shadow: inset 0 0 0 1px rgba(255,255,255,0.08);
  transition: color 0.2s, background 0.2s, box-shadow 0.2s, transform 0.15s;
  overflow: hidden;
  white-space: nowrap;
}
.opt-pill:hover {
  color: rgba(255,255,255,0.6);
  background: rgba(255,255,255,0.07);
  transform: translateY(-1px);
}
.opt-pill:active { transform: scale(0.96); }

/* 激活态 — 多文档用蓝紫渐变，关键词用青绿 */
.opt-pill.active {
  color: #fff;
  background: rgba(79,142,247,0.18);
  box-shadow: inset 0 0 0 1px rgba(79,142,247,0.5), 0 0 12px rgba(79,142,247,0.25);
}
.opt-pill.active .opt-pill-dot {
  background: #7eb3ff;
  box-shadow: 0 0 6px #7eb3ff;
}
/* 第二个 pill（关键词）激活用青绿 */
.opt-pill:nth-child(2).active {
  background: rgba(45,212,160,0.15);
  box-shadow: inset 0 0 0 1px rgba(45,212,160,0.45), 0 0 12px rgba(45,212,160,0.2);
}
.opt-pill:nth-child(2).active .opt-pill-dot {
  background: #2dd4a0;
  box-shadow: 0 0 6px #2dd4a0;
}

/* 状态指示点 */
.opt-pill-dot {
  width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0;
  background: rgba(255,255,255,0.2);
  transition: background 0.25s, box-shadow 0.25s;
}

/* 图标 */
.opt-pill-icon {
  width: 12px; height: 12px; flex-shrink: 0;
  color: currentColor; opacity: 0.8;
}

/* 扫光层 */
.opt-pill-glow {
  position: absolute; inset: 0; border-radius: inherit; pointer-events: none;
  background: linear-gradient(105deg, transparent 40%, rgba(255,255,255,0.07) 50%, transparent 60%);
  background-size: 200% 100%; background-position: 200% 0;
  transition: background-position 0s;
}
.opt-pill.active .opt-pill-glow {
  animation: pill-sweep 2.5s ease-in-out infinite;
}
@keyframes pill-sweep {
  0%   { background-position: 200% 0; }
  40%  { background-position: -50% 0; }
  100% { background-position: -50% 0; }
}

/* ── keyword input ── */
.kw-input-wrap {
  display: flex; align-items: center; gap: 6px;
  padding: 3px 8px 3px 10px; border-radius: 99px;
  background: rgba(255,255,255,0.04);
  box-shadow: inset 0 0 0 1px rgba(45,212,160,0.35), 0 0 10px rgba(45,212,160,0.1);
  min-width: 0;
}
.kw-input-icon { width: 11px; height: 11px; color: #2dd4a0; flex-shrink: 0; opacity: 0.7; }
.kw-input {
  border: none; outline: none; background: transparent;
  font-size: 11px; color: rgba(255,255,255,0.75); width: 130px;
  font-family: inherit;
}
.kw-input::placeholder { color: rgba(255,255,255,0.2); }
.kw-clear {
  width: 14px; height: 14px; border-radius: 50%; border: none; cursor: pointer; flex-shrink: 0;
  background: rgba(255,255,255,0.08); color: rgba(255,255,255,0.35);
  display: flex; align-items: center; justify-content: center; padding: 2px;
  transition: background 0.15s, color 0.15s;
}
.kw-clear:hover { background: rgba(240,107,107,0.2); color: #f06b6b; }
.kw-clear svg { width: 100%; height: 100%; }

/* kw-slide transition */
.kw-slide-enter-active { transition: all 0.25s cubic-bezier(0.34,1.56,0.64,1); }
.kw-slide-leave-active { transition: all 0.18s cubic-bezier(0.4,0,1,1); }
.kw-slide-enter-from { opacity: 0; transform: translateX(-8px) scale(0.92); max-width: 0; }
.kw-slide-enter-to   { opacity: 1; transform: translateX(0) scale(1);      max-width: 220px; }
.kw-slide-leave-from { opacity: 1; transform: translateX(0) scale(1);      max-width: 220px; }
.kw-slide-leave-to   { opacity: 0; transform: translateX(-8px) scale(0.92); max-width: 0; }
.mode-badge {
  font-size: 10px; font-weight: 700; padding: 3px 9px; border-radius: 99px;
  text-transform: uppercase; letter-spacing: 0.8px;
}
.mode-badge.general { background: rgba(148,163,184,0.1); color: rgba(255,255,255,0.3); }
.mode-badge.knowledge { background: rgba(45,212,160,0.1); color: #2dd4a0; }
.icon-btn {
  width: 30px; height: 30px; border-radius: 8px; border: none; cursor: pointer;
  background: rgba(255,255,255,0.05); color: rgba(255,255,255,0.3);
  display: flex; align-items: center; justify-content: center; font-size: 14px;
  transition: all 0.2s;
}
.icon-btn:hover { background: rgba(255,255,255,0.09); color: rgba(255,255,255,0.6); }

/* ── Messages ── */
.messages {
  flex: 1; overflow-y: auto; padding: 24px 20px;
  display: flex; flex-direction: column; gap: 0;
}
.messages::-webkit-scrollbar { width: 4px; }
.messages::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.07); border-radius: 99px; }

/* ── Welcome screen ── */
.welcome-screen {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  padding: 40px 20px; text-align: center;
}
.welcome-orb {
  position: relative; width: 80px; height: 80px;
  display: flex; align-items: center; justify-content: center;
  margin-bottom: 24px;
}
.welcome-orb::before {
  content: '';
  position: absolute; inset: -20px; border-radius: 50%;
  background: radial-gradient(circle, rgba(79,142,247,0.25) 0%, rgba(167,139,250,0.15) 40%, transparent 70%);
  filter: blur(20px);
  animation: glow-pulse 3s ease-in-out infinite;
}
@keyframes glow-pulse {
  0%,100% { opacity: 0.6; transform: scale(0.95); }
  50% { opacity: 1; transform: scale(1.05); }
}
.orb-ring {
  position: absolute; inset: 0; border-radius: 50%;
  border: 1.5px solid rgba(79,142,247,0.5);
  animation: orb-spin 4s linear infinite;
  box-shadow: 0 0 8px rgba(79,142,247,0.3);
}
.orb-ring-2 {
  inset: 10px;
  border-color: rgba(167,139,250,0.4);
  animation-duration: 6s; animation-direction: reverse;
  box-shadow: 0 0 6px rgba(167,139,250,0.25);
}
@keyframes orb-spin { to { transform: rotate(360deg); } }
.orb-icon {
  font-size: 28px; color: #7eb3ff; z-index: 1;
  filter: drop-shadow(0 0 14px rgba(79,142,247,0.8));
}
.welcome-title { font-size: 22px; font-weight: 700; color: #f0f4ff; margin: 0 0 8px; letter-spacing: -0.3px; }
.welcome-sub { font-size: 13px; color: rgba(255,255,255,0.3); margin: 0 0 28px; max-width: 360px; }
.suggestion-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; max-width: 560px; width: 100%; }
.suggestion-card {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 14px; border-radius: 10px; cursor: pointer;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.07);
  color: rgba(255,255,255,0.45); font-size: 12px; text-align: left;
  transition: all 0.2s;
}
.suggestion-card:hover {
  background: rgba(79,142,247,0.08); border-color: rgba(79,142,247,0.25);
  color: #7eb3ff; transform: translateY(-1px);
}

/* ── Message rows ── */
.msg-row { display: flex; gap: 12px; margin-bottom: 20px; align-items: flex-start; }
.msg-row.user { flex-direction: row-reverse; }

/* AI avatar */
.ai-avatar {
  position: relative; width: 36px; height: 36px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
}
.ai-avatar::before {
  content: '';
  position: absolute; inset: -4px; border-radius: 50%;
  background: radial-gradient(circle, rgba(79,142,247,0.18) 0%, transparent 70%);
  pointer-events: none;
}
.ai-avatar-ring {
  position: absolute; inset: 0; border-radius: 50%;
  border: 1.5px solid rgba(79,142,247,0.55);
  animation: orb-spin 5s linear infinite;
}
.ai-avatar-ring::after {
  content: '';
  position: absolute; top: -1px; left: 30%; width: 30%; height: 2px;
  background: linear-gradient(90deg, transparent, #7eb3ff, transparent);
  border-radius: 99px;
}
.ai-avatar-ring.pulsing {
  border-color: rgba(79,142,247,0.9);
  animation: ring-pulse 1.2s ease-in-out infinite;
  box-shadow: 0 0 12px rgba(79,142,247,0.5);
}
@keyframes ring-pulse {
  0%,100% { opacity: 0.5; transform: scale(1); box-shadow: 0 0 6px rgba(79,142,247,0.3); }
  50% { opacity: 1; transform: scale(1.12); box-shadow: 0 0 18px rgba(79,142,247,0.7); }
}
.ai-avatar-bg {
  position: absolute; inset: 3px; border-radius: 50%;
  background: linear-gradient(135deg, rgba(79,142,247,0.15), rgba(167,139,250,0.1));
  border: 1px solid rgba(79,142,247,0.2);
}
.ai-avatar-icon { font-size: 15px; color: #7eb3ff; z-index: 1; filter: drop-shadow(0 0 6px rgba(79,142,247,0.7)); }

/* User avatar */
.user-avatar {
  width: 36px; height: 36px; border-radius: 50%; flex-shrink: 0;
  background: linear-gradient(135deg, #3b6fd4 0%, #7c3aed 100%);
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 700; color: #fff;
  box-shadow: 0 2px 14px rgba(59,111,212,0.5), 0 0 0 2px rgba(91,79,207,0.25);
  position: relative;
}
.user-avatar::after {
  content: '';
  position: absolute; inset: -3px; border-radius: 50%;
  border: 1px solid rgba(124,58,237,0.3);
  pointer-events: none;
}

/* Bubble wrap */
.bubble-wrap { max-width: 70%; display: flex; flex-direction: column; }
.msg-row.user .bubble-wrap { align-items: flex-end; }

/* Bubbles */
.bubble {
  border-radius: 16px; padding: 12px 16px;
  word-break: break-word; position: relative;
}
.bubble.assistant {
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 4px 16px 16px 16px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.3);
  padding-left: 18px;
}
/* 渐变竖线用伪元素实现，避免 border-image 破坏 border-radius */
.bubble.assistant::before {
  content: '';
  position: absolute; left: 0; top: 6px; bottom: 6px;
  width: 2.5px; border-radius: 99px;
  background: linear-gradient(180deg, #4f8ef7, #a78bfa);
  box-shadow: 0 0 8px rgba(79,142,247,0.5);
}
.bubble.user {
  background: linear-gradient(135deg, #2d5fc4 0%, #6d28d9 100%);
  border: 1px solid rgba(109,40,217,0.35);
  border-radius: 16px 4px 16px 16px;
  color: #fff;
  box-shadow: 0 4px 24px rgba(59,111,212,0.4), 0 0 0 1px rgba(255,255,255,0.06) inset;
  position: relative; overflow: hidden;
}
/* 用户气泡内光效 */
.bubble.user::after {
  content: '';
  position: absolute; top: 0; left: 0; right: 0; height: 40%;
  background: linear-gradient(180deg, rgba(255,255,255,0.07), transparent);
  pointer-events: none; border-radius: inherit;
}

/* Bubble text / markdown */
.bubble-text { font-size: 14px; line-height: 1.65; color: #e2e8f0; }
.bubble.user .bubble-text { color: #fff; }
.bubble-text :deep(p) { margin: 4px 0; }
.bubble-text :deep(h1),.bubble-text :deep(h2),.bubble-text :deep(h3) { margin: 10px 0 6px; font-weight: 600; }
.bubble-text :deep(h1) { font-size: 17px; } .bubble-text :deep(h2) { font-size: 15px; } .bubble-text :deep(h3) { font-size: 14px; }
.bubble-text :deep(ul),.bubble-text :deep(ol) { padding-left: 18px; margin: 6px 0; }
.bubble-text :deep(li) { margin: 2px 0; }
.bubble-text :deep(code) { background: rgba(79,142,247,0.12); border-radius: 4px; padding: 1px 5px; font-size: 12px; color: #7eb3ff; font-family: 'Fira Code', monospace; }
.bubble-text :deep(pre) { background: #0d1117; border: 1px solid rgba(255,255,255,0.1); border-radius: 10px; padding: 12px 14px; overflow-x: auto; margin: 8px 0; }
.bubble-text :deep(pre code) { background: none; color: #7dd3fc; padding: 0; }
.bubble-text :deep(blockquote) { border-left: 2px solid rgba(79,142,247,0.4); margin: 6px 0; padding: 4px 12px; color: rgba(255,255,255,0.4); }
.bubble-text :deep(table) { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 13px; }
.bubble-text :deep(th),.bubble-text :deep(td) { border: 1px solid rgba(255,255,255,0.08); padding: 6px 10px; }
.bubble-text :deep(th) { background: rgba(255,255,255,0.04); font-weight: 600; }
.bubble-text :deep(a) { color: #7eb3ff; text-decoration: none; }
.bubble-text :deep(a:hover) { text-decoration: underline; }
.bubble-text :deep(img) {
  max-width: 100%;
  max-height: 280px;
  width: auto;
  height: auto;
  object-fit: contain;
  border-radius: 10px;
  margin: 8px 0;
  display: block;
  border: 1px solid rgba(255,255,255,0.08);
  box-shadow: 0 4px 20px rgba(0,0,0,0.5);
  filter: brightness(0.92) contrast(1.04);
  mix-blend-mode: luminosity;
  transition: filter 0.2s, transform 0.2s, box-shadow 0.2s;
  cursor: zoom-in;
}
.bubble-text :deep(img:hover) {
  filter: brightness(1) contrast(1.06);
  mix-blend-mode: normal;
  transform: scale(1.02);
  box-shadow: 0 8px 32px rgba(0,0,0,0.6);
}
.bubble-text :deep(hr) { border: none; border-top: 1px solid rgba(255,255,255,0.08); margin: 10px 0; }
.bubble.user .bubble-text :deep(code) { background: rgba(255,255,255,0.15); color: #fff; }
.bubble.user .bubble-text :deep(a) { color: rgba(255,255,255,0.85); }

/* Meta row (tools) */
.meta-row {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  margin-top: 8px; padding-top: 8px; border-top: 1px solid rgba(255,255,255,0.07);
}
.meta-label { font-size: 10px; color: rgba(255,255,255,0.3); text-transform: uppercase; letter-spacing: 0.5px; }
.tool-chip {
  font-size: 10px; font-weight: 600; padding: 2px 8px; border-radius: 5px;
  background: rgba(245,200,66,0.1); color: #f5c842;
  text-transform: uppercase; letter-spacing: 0.3px;
}

/* Sources */
.sources-section { margin-top: 10px; padding-top: 10px; border-top: 1px solid rgba(255,255,255,0.07); }
.sources-toggle {
  display: flex; align-items: center; gap: 6px;
  background: none; border: none; cursor: pointer; padding: 0;
  color: rgba(255,255,255,0.4); font-size: 12px; transition: color 0.2s;
}
.sources-toggle:hover { color: #7eb3ff; }
.sources-count {
  margin-left: 2px; font-size: 10px; padding: 1px 6px; border-radius: 4px;
  background: rgba(255,255,255,0.06); color: rgba(255,255,255,0.3);
}
.toggle-arrow { font-size: 11px; transition: transform 0.25s; }
.toggle-arrow.open { transform: rotate(180deg); }
.sources-list { margin-top: 8px; display: flex; flex-direction: column; gap: 4px; }
.source-card {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 10px; border-radius: 8px;
  background: rgba(79,142,247,0.06); border: 1px solid rgba(79,142,247,0.12);
}
.source-dot { width: 5px; height: 5px; border-radius: 50%; background: #7eb3ff; flex-shrink: 0; }
.source-name { font-size: 12px; color: rgba(255,255,255,0.5); }

/* Confidence arc */
.confidence-row {
  display: flex; align-items: center; gap: 6px;
  margin-top: 8px; padding-top: 8px; border-top: 1px solid rgba(255,255,255,0.07);
}
.conf-arc { width: 52px; height: 30px; }
.conf-label { font-size: 11px; color: rgba(255,255,255,0.3); }

/* Msg time */
.msg-time { font-size: 10px; color: rgba(255,255,255,0.2); margin-top: 5px; padding: 0 4px; }

/* Typing indicator */
.typing-bubble {
  display: flex; align-items: flex-end; gap: 4px;
  padding: 14px 18px; min-width: 60px;
}
.wave-bar {
  width: 3px; border-radius: 99px; background: #4f8ef7;
  animation: wave 1.2s ease-in-out infinite;
}
.wave-bar:nth-child(1) { height: 8px; animation-delay: 0s; }
.wave-bar:nth-child(2) { height: 14px; animation-delay: 0.15s; }
.wave-bar:nth-child(3) { height: 8px; animation-delay: 0.3s; }
@keyframes wave { 0%,100% { transform: scaleY(0.5); opacity: 0.4; } 50% { transform: scaleY(1); opacity: 1; } }

/* ── Input area ── */
.input-area {
  display: flex; gap: 10px; padding: 14px 16px; align-items: flex-end;
  background: rgba(255,255,255,0.02);
  border-top: 1px solid rgba(255,255,255,0.06);
  flex-shrink: 0;
  transition: border-top-color 0.25s;
}
.input-area.focused { border-top-color: rgba(79,142,247,0.3); }
.input-wrap { flex: 1; position: relative; }
.input-wrap :deep(.el-textarea__inner) {
  border-radius: 12px !important; resize: none !important;
  padding-right: 48px !important;
}
.char-count {
  position: absolute; bottom: 8px; right: 10px;
  font-size: 10px; color: rgba(255,255,255,0.2); pointer-events: none;
}
.char-count.warn { color: #f06b6b; }

/* Send button */
.send-btn {
  width: 44px; height: 44px; border-radius: 50%; border: none; cursor: pointer;
  background: linear-gradient(135deg, #3b6fd4, #7c3aed);
  color: #fff; display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; transition: all 0.25s cubic-bezier(0.4,0,0.2,1);
  box-shadow: 0 2px 16px rgba(59,111,212,0.5), 0 0 0 1px rgba(255,255,255,0.08) inset;
  position: relative; overflow: hidden;
}
.send-btn::before {
  content: '';
  position: absolute; inset: 0; border-radius: 50%;
  background: linear-gradient(180deg, rgba(255,255,255,0.12), transparent);
  pointer-events: none;
}
.send-btn:hover:not(.disabled) {
  box-shadow: 0 6px 28px rgba(59,111,212,0.7), 0 0 0 3px rgba(79,142,247,0.25), 0 0 0 1px rgba(255,255,255,0.1) inset;
  transform: translateY(-2px) scale(1.04);
}
.send-btn:active:not(.disabled) { transform: translateY(0) scale(0.97); }
.send-btn.disabled { opacity: 0.3; cursor: not-allowed; transform: none; box-shadow: none; }
.send-icon { display: flex; align-items: center; justify-content: center; }
.send-icon svg { width: 15px; height: 15px; }
.spin-ring {
  width: 18px; height: 18px; border-radius: 50%;
  border: 2px solid rgba(255,255,255,0.25);
  border-top-color: #fff;
  animation: spin 0.7s linear infinite;
  display: block;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Transitions ── */
.fade-enter-active,.fade-leave-active { transition: opacity 0.3s; }
.fade-enter-from,.fade-leave-to { opacity: 0; }

.msg-enter-active { transition: all 0.35s cubic-bezier(0.4,0,0.2,1); }
.msg-enter-from { opacity: 0; transform: translateY(16px); }
.msg-leave-active { transition: all 0.25s cubic-bezier(0.4,0,1,1); }
.msg-leave-to { opacity: 0; transform: translateY(-8px) scale(0.96); }

.expand-enter-active,.expand-leave-active { transition: all 0.3s cubic-bezier(0.4,0,0.2,1); overflow: hidden; }
.expand-enter-from,.expand-leave-to { opacity: 0; max-height: 0; transform: translateY(-4px); }
.expand-enter-to,.expand-leave-from { opacity: 1; max-height: 600px; transform: translateY(0); }

.icon-swap-enter-active,.icon-swap-leave-active { transition: all 0.18s cubic-bezier(0.4,0,0.2,1); }
.icon-swap-enter-from { opacity: 0; transform: scale(0.7) rotate(-90deg); }
.icon-swap-leave-to { opacity: 0; transform: scale(0.7) rotate(90deg); }

/* Lightbox */
.lightbox-overlay {
  position: fixed; inset: 0; z-index: 9999;
  background: rgba(0,0,0,0.85);
  display: flex; align-items: center; justify-content: center;
  cursor: zoom-out;
  backdrop-filter: blur(6px);
}
.lightbox-img {
  max-width: 90vw; max-height: 90vh;
  object-fit: contain;
  border-radius: 12px;
  box-shadow: 0 24px 80px rgba(0,0,0,0.8);
  cursor: default;
  filter: brightness(1) contrast(1.04);
}
.lightbox-close {
  position: fixed; top: 20px; right: 24px;
  width: 36px; height: 36px;
  background: rgba(255,255,255,0.1);
  border: 1px solid rgba(255,255,255,0.15);
  border-radius: 50%;
  color: #fff; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: background 0.2s;
}
.lightbox-close:hover { background: rgba(255,255,255,0.2); }
.lightbox-close svg { width: 14px; height: 14px; }
.lightbox-fade-enter-active, .lightbox-fade-leave-active { transition: opacity 0.2s ease; }
.lightbox-fade-enter-from, .lightbox-fade-leave-to { opacity: 0; }
</style>
