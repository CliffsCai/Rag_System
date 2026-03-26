<template>
  <div class="devtools">
    <el-row :gutter="20">
      <!-- API 健康检查 -->
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header">
              <span>🔌 API 健康检查</span>
              <el-tag :type="status ? 'success' : 'info'" size="small">
                {{ status ? '正常' : '未检测' }}
              </el-tag>
            </div>
          </template>
          <el-button type="primary" @click="check" :loading="checking" style="margin-bottom:16px">
            检测连接
          </el-button>
          <div v-if="result">
            <div v-if="result.architecture" class="info-block">
              <div class="info-label">当前架构</div>
              <div class="info-value">{{ result.architecture }}</div>
              <div class="info-label" style="margin-top:10px">可用 MCP 工具</div>
              <div style="margin-top:6px">
                <el-tag
                  v-for="tool in result.mcp_tools"
                  :key="tool"
                  type="success"
                  size="small"
                  style="margin:3px"
                >{{ tool }}</el-tag>
              </div>
            </div>
            <el-divider />
            <div class="info-label">完整响应</div>
            <pre class="json-pre">{{ JSON.stringify(result, null, 2) }}</pre>
          </div>
        </el-card>
      </el-col>

      <!-- 快速说明 -->
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header><span>📖 接口说明</span></template>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="普通对话">POST /api/v1/chat</el-descriptions-item>
            <el-descriptions-item label="知识库问答">POST /api/v1/knowledge</el-descriptions-item>
            <el-descriptions-item label="文档上传">POST /api/v1/documents/upload</el-descriptions-item>
            <el-descriptions-item label="切片检索">POST /api/v1/documents/search</el-descriptions-item>
            <el-descriptions-item label="任务列表">GET /api/v1/jobs</el-descriptions-item>
            <el-descriptions-item label="切片管理">GET/PUT /api/v1/chunks/job/:id</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { apiService } from '@/services/api'

const checking = ref(false)
const status = ref(false)
const result = ref(null)

const check = async () => {
  checking.value = true
  try {
    result.value = await apiService.healthCheck()
    status.value = true
    ElMessage.success('API 连接正常')
  } catch (e) {
    result.value = { error: e.message }
    status.value = false
    ElMessage.error('API 连接失败')
  } finally {
    checking.value = false
  }
}
</script>

<style scoped>
.devtools { max-width: 1100px; }
.card-header { display:flex; justify-content:space-between; align-items:center; font-weight:600; }
.info-block { padding: 12px; background: #f5f7fa; border-radius: 6px; }
.info-label { font-size: 12px; color: #909399; font-weight: 600; }
.info-value { font-size: 14px; color: #303133; margin-top: 4px; }
.json-pre {
  margin: 8px 0 0;
  padding: 10px;
  background: #1e1e1e;
  color: #d4d4d4;
  border-radius: 6px;
  font-size: 12px;
  overflow-x: auto;
  max-height: 260px;
}
</style>
