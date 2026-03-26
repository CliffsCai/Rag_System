<template>
  <div class="chat-wrapper">
    <!-- 模式切换 + 工具栏 -->
    <div class="chat-toolbar">
      <el-radio-group v-model="chatMode" size="small">
        <el-radio-button value="general">
          <el-icon style="margin-right:4px"><cpu /></el-icon>普通对话
        </el-radio-button>
        <el-radio-button value="knowledge">
          <el-icon style="margin-right:4px"><document /></el-icon>知识库
        </el-radio-button>
      </el-radio-group>

      <div class="toolbar-right">
        <!-- 知识库模式下显示知识库选择器 -->
        <template v-if="chatMode === 'knowledge'">
          <el-select
            v-model="selectedCollection"
            size="small"
            placeholder="选择知识库"
            style="width:200px;margin-right:8px"
            clearable
            @change="clearMessages"
          >
            <el-option
              v-for="col in collections"
              :key="col.collection_name"
              :label="col.collection_name"
              :value="col.collection_name"
            />
          </el-select>
          <span v-if="collections.length === 0" style="font-size:12px;color:#f56c6c;margin-right:8px">
            暂无知识库，请先创建
          </span>
        </template>
        <el-tag
          :type="chatMode === 'general' ? 'info' : 'success'"
          size="small"
          style="margin-right:8px"
        >
          {{ chatMode === 'general' ? 'Supervisor 多工具' : '向量检索 + Rerank' }}
        </el-tag>
        <el-button size="small" plain @click="clearMessages">清空对话</el-button>
      </div>
    </div>

    <!-- 消息区 -->
    <div class="messages" ref="messagesContainer">
      <div
        v-for="(msg, i) in messages"
        :key="i"
        :class="['msg-row', msg.role]"
      >
        <!-- 头像 -->
        <div class="avatar">
          <el-avatar v-if="msg.role === 'assistant'" :size="32" style="background:#409eff">AI</el-avatar>
          <el-avatar v-else :size="32" style="background:#67c23a">我</el-avatar>
        </div>

        <div class="bubble-wrap">
          <div class="bubble">
            <div class="bubble-text" style="white-space: pre-wrap" v-if="!msg.isHtml">{{ msg.content }}</div>
            <div class="bubble-text" v-else v-html="msg.content"></div>

            <!-- 工具调用标签 -->
            <div v-if="msg.tools_used && msg.tools_used.length" class="bubble-meta">
              <el-icon style="font-size:11px;margin-right:3px"><tools /></el-icon>
              <el-tag
                v-for="t in msg.tools_used"
                :key="t"
                size="small"
                type="warning"
                style="margin-right:4px;font-size:11px"
              >{{ t }}</el-tag>
            </div>

            <!-- 知识库来源 -->
            <div v-if="msg.sources && msg.sources.length" class="bubble-meta">
              <el-icon style="font-size:11px;margin-right:4px;flex-shrink:0"><document /></el-icon>
              <div style="display:flex;flex-wrap:wrap;gap:4px;flex:1">
                <el-tag
                  v-for="(name, si) in uniqueFileNames(msg.sources)"
                  :key="si"
                  size="small"
                  type="info"
                  style="font-size:11px;height:auto;white-space:normal;line-height:1.4;padding:2px 6px"
                >{{ name }}</el-tag>
                <span style="font-size:11px;color:#c0c4cc;align-self:center">
                  共 {{ msg.sources.length }} 个切片
                </span>
              </div>
            </div>

            <!-- 置信度 -->
            <div v-if="msg.confidence !== undefined" class="bubble-meta">
              <el-progress
                :percentage="Math.round(msg.confidence * 100)"
                :stroke-width="4"
                style="width:120px;display:inline-flex;align-items:center"
              />
              <span style="font-size:11px;color:#909399;margin-left:6px">置信度</span>
            </div>
          </div>
          <div class="msg-time">{{ formatTime(msg.timestamp) }}</div>
        </div>
      </div>

      <!-- 加载中 -->
      <div v-if="loading" class="msg-row assistant">
        <div class="avatar">
          <el-avatar :size="32" style="background:#409eff">AI</el-avatar>
        </div>
        <div class="bubble-wrap">
          <div class="bubble typing-bubble">
            <span class="dot" /><span class="dot" /><span class="dot" />
          </div>
        </div>
      </div>
    </div>

    <!-- 输入区 -->
    <div class="input-area">
      <el-input
        v-model="inputMessage"
        type="textarea"
        :rows="2"
        :autosize="{ minRows: 2, maxRows: 5 }"
        placeholder="输入消息，Enter 发送，Shift+Enter 换行"
        :disabled="loading"
        @keydown.enter.exact.prevent="sendMessage"
        resize="none"
      />
      <el-button
        type="primary"
        :loading="loading"
        :disabled="!inputMessage.trim() || (chatMode === 'knowledge' && !selectedCollection)"
        @click="sendMessage"
        class="send-btn"
      >
        发送
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { apiService } from '../services/api'
import axios from 'axios'
import MarkdownIt from 'markdown-it'

const md = new MarkdownIt({
  html: false,
  linkify: true,
  typographer: true,
  breaks: true,
})

const API = 'http://localhost:8000/api/v1'

const props = defineProps({
  model: { type: String, default: 'qwen-turbo' },
})

const chatMode = ref('general')
const selectedCollection = ref('')
const collections = ref([])

const loadCollections = async () => {
  try {
    const { data } = await axios.get(`${API}/admin/collection/list`)
    collections.value = data.data?.collections || []
    // 自动选中第一个
    if (collections.value.length > 0 && !selectedCollection.value) {
      selectedCollection.value = collections.value[0].collection_name
    }
  } catch (e) {
    console.error('加载知识库列表失败', e)
  }
}

onMounted(loadCollections)

const getWelcome = (mode) => mode === 'knowledge'
  ? '你好！我是知识库助手。\n\n✅ 基于企业知识库回答问题\n✅ 提供文档引用和来源\n✅ 智能检索 + Rerank 重排序\n\n请问有什么需要查询的？'
  : '你好！我是智能助手。\n\n✅ 自然对话（带记忆）\n✅ 发送邮件（email_agent）\n✅ 网络搜索（search_agent）\n✅ 自动判断是否调用工具\n\n有什么可以帮您的吗？'

const messages = ref([{ role: 'assistant', content: getWelcome('general'), timestamp: new Date() }])
const inputMessage = ref('')
const loading = ref(false)
const messagesContainer = ref(null)

const scrollToBottom = () => {
  nextTick(() => {
    if (messagesContainer.value)
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  })
}

const sendMessage = async () => {
  const text = inputMessage.value.trim()
  if (!text || loading.value) return

  messages.value.push({ role: 'user', content: text, timestamp: new Date() })
  inputMessage.value = ''
  loading.value = true
  scrollToBottom()

  try {
    if (chatMode.value === 'knowledge') {
      const res = await apiService.knowledgeQA(text, props.model, 'default', selectedCollection.value || null)
      const imageMap = res.image_map || {}
      let raw = res.answer || '抱歉，未收到有效回复。'
      // 先替换图片占位符为 markdown 图片语法
      Object.entries(imageMap).forEach(([placeholder, url]) => {
        raw = raw.split(placeholder).join(`\n![image](${url})\n`)
      })
      // 再渲染 markdown
      const renderedContent = md.render(raw)
      messages.value.push({
        role: 'assistant',
        content: renderedContent,
        isHtml: true,
        confidence: res.confidence,
        sources: res.sources || [],
        timestamp: new Date(),
      })
    } else {
      const apiMsgs = messages.value.map(m => ({ role: m.role, content: m.content }))
      const res = await apiService.chat(apiMsgs, props.model)
      const last = res.messages?.[res.messages.length - 1]
      const toolsUsed = res.usage?.tools_used || []
      const raw = last?.content || '抱歉，未收到有效回复。'
      messages.value.push({
        role: 'assistant',
        content: md.render(raw),
        isHtml: true,
        tools_used: toolsUsed,
        timestamp: new Date(),
      })
      if (toolsUsed.length) ElMessage.success(`调用工具: ${toolsUsed.join(', ')}`)
    }
  } catch (e) {
    console.error(e)
    ElMessage.error('发送失败')
    messages.value.push({ role: 'assistant', content: '抱歉，发生错误，请稍后重试。', timestamp: new Date() })
  } finally {
    loading.value = false
    scrollToBottom()
  }
}

const clearMessages = () => {
  messages.value = [{ role: 'assistant', content: getWelcome(chatMode.value), timestamp: new Date() }]
}

watch(chatMode, (mode) => {
  messages.value = [{ role: 'assistant', content: getWelcome(mode), timestamp: new Date() }]
})

const formatTime = (t) =>
  new Date(t).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })

// 从 sources 列表提取去重后的文件名
const uniqueFileNames = (sources) => {
  const seen = new Set()
  const names = []
  for (const s of sources) {
    const name = s.file_name || s.title || s.id || '未知来源'
    if (!seen.has(name)) {
      seen.add(name)
      names.push(name)
    }
  }
  return names
}

defineExpose({ clearMessages })
</script>

<style scoped>
.chat-wrapper {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 108px);
  background: #fff;
  border-radius: 10px;
  overflow: hidden;
  box-shadow: 0 2px 12px rgba(0,0,0,0.08);
}

/* 工具栏 */
.chat-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #e4e7ed;
  background: #fafafa;
  flex-shrink: 0;
}

.toolbar-right {
  display: flex;
  align-items: center;
}

/* 消息区 */
.messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px 16px;
  background: #f5f7fa;
}

.msg-row {
  display: flex;
  gap: 10px;
  margin-bottom: 18px;
}

.msg-row.user {
  flex-direction: row-reverse;
}

.avatar {
  flex-shrink: 0;
  padding-top: 2px;
}

.bubble-wrap {
  max-width: 68%;
  display: flex;
  flex-direction: column;
}

.msg-row.user .bubble-wrap {
  align-items: flex-end;
}

.bubble {
  background: #fff;
  border-radius: 12px;
  padding: 10px 14px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.08);
  word-break: break-word;
}

.msg-row.user .bubble {
  background: #409eff;
  color: #fff;
}

.bubble-text {
  font-size: 14px;
  line-height: 1.6;
}

/* markdown 渲染样式 */
.bubble-text :deep(h1),
.bubble-text :deep(h2),
.bubble-text :deep(h3),
.bubble-text :deep(h4) {
  margin: 10px 0 6px;
  font-weight: 600;
  line-height: 1.4;
}
.bubble-text :deep(h1) { font-size: 18px; }
.bubble-text :deep(h2) { font-size: 16px; }
.bubble-text :deep(h3) { font-size: 15px; }

.bubble-text :deep(p) {
  margin: 4px 0;
}

.bubble-text :deep(ul),
.bubble-text :deep(ol) {
  padding-left: 20px;
  margin: 6px 0;
}

.bubble-text :deep(li) {
  margin: 2px 0;
}

.bubble-text :deep(code) {
  background: #f0f2f5;
  border-radius: 3px;
  padding: 1px 5px;
  font-family: 'Courier New', monospace;
  font-size: 13px;
  color: #e6395a;
}

.bubble-text :deep(pre) {
  background: #1e1e1e;
  border-radius: 6px;
  padding: 12px 14px;
  overflow-x: auto;
  margin: 8px 0;
}

.bubble-text :deep(pre code) {
  background: none;
  color: #d4d4d4;
  padding: 0;
  font-size: 13px;
}

.bubble-text :deep(blockquote) {
  border-left: 3px solid #dcdfe6;
  margin: 6px 0;
  padding: 4px 12px;
  color: #909399;
}

.bubble-text :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 8px 0;
  font-size: 13px;
}

.bubble-text :deep(th),
.bubble-text :deep(td) {
  border: 1px solid #dcdfe6;
  padding: 6px 10px;
  text-align: left;
}

.bubble-text :deep(th) {
  background: #f5f7fa;
  font-weight: 600;
}

.bubble-text :deep(a) {
  color: #409eff;
  text-decoration: none;
}

.bubble-text :deep(a:hover) {
  text-decoration: underline;
}

.bubble-text :deep(img) {
  max-width: 100%;
  border-radius: 6px;
  margin: 8px 0;
  display: block;
}

.bubble-text :deep(hr) {
  border: none;
  border-top: 1px solid #e4e7ed;
  margin: 10px 0;
}

/* 用户消息气泡内 markdown 颜色适配 */
.msg-row.user .bubble-text :deep(code) {
  background: rgba(255,255,255,0.2);
  color: #fff;
}
.msg-row.user .bubble-text :deep(a) {
  color: #fff;
  text-decoration: underline;
}
.msg-row.user .bubble-text :deep(blockquote) {
  border-left-color: rgba(255,255,255,0.5);
  color: rgba(255,255,255,0.8);
}

.bubble-meta {
  display: flex;
  align-items: flex-start;
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px solid rgba(0,0,0,0.06);
}

.msg-time {
  font-size: 11px;
  color: #c0c4cc;
  margin-top: 4px;
  padding: 0 2px;
}

/* 打字动画 */
.typing-bubble {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 12px 16px;
}

.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #c0c4cc;
  animation: bounce 1.2s infinite;
}

.dot:nth-child(2) { animation-delay: 0.2s; }
.dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes bounce {
  0%, 80%, 100% { transform: translateY(0); }
  40% { transform: translateY(-6px); }
}

/* 输入区 */
.input-area {
  display: flex;
  gap: 10px;
  padding: 14px 16px;
  background: #fff;
  border-top: 1px solid #e4e7ed;
  flex-shrink: 0;
  align-items: flex-end;
}

.input-area :deep(.el-textarea__inner) {
  border-radius: 8px;
  resize: none;
}

.send-btn {
  height: 56px;
  padding: 0 20px;
  flex-shrink: 0;
}
</style>
