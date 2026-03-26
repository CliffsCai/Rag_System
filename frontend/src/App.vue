<template>
  <div id="app">
    <el-container class="app-layout">
      <!-- 侧边栏 -->
      <el-aside :width="collapsed ? '64px' : '220px'" class="sidebar">
        <div class="sidebar-logo">
          <el-icon class="logo-icon"><cpu /></el-icon>
          <span v-show="!collapsed" class="logo-text">LangGraph Agent</span>
        </div>

        <el-menu
          :default-active="activeMenu"
          class="sidebar-menu"
          :collapse="collapsed"
          :collapse-transition="false"
          @select="handleMenuSelect"
        >
          <el-menu-item index="chat">
            <el-icon><chat-dot-round /></el-icon>
            <template #title>智能对话</template>
          </el-menu-item>

          <el-sub-menu index="knowledge">
            <template #title>
              <el-icon><document /></el-icon>
              <span>文档管理</span>
            </template>
            <el-menu-item index="kb-categories">类目管理</el-menu-item>
          </el-sub-menu>

          <el-sub-menu index="admin">
            <template #title>
              <el-icon><setting /></el-icon>
              <span>系统管理</span>
            </template>
            <el-menu-item index="admin-collections">知识库列表</el-menu-item>
            <el-menu-item index="admin-create">创建知识库</el-menu-item>
            <el-menu-item index="admin-config">配置信息</el-menu-item>
          </el-sub-menu>

          <el-menu-item index="devtools">
            <el-icon><monitor /></el-icon>
            <template #title>开发工具</template>
          </el-menu-item>
        </el-menu>

        <div class="sidebar-footer">
          <el-button
            :icon="collapsed ? Expand : Fold"
            circle
            size="small"
            @click="collapsed = !collapsed"
            class="collapse-btn"
          />
        </div>
      </el-aside>

      <!-- 右侧主区域 -->
      <el-container class="main-container">
        <!-- 顶部栏 -->
        <el-header class="topbar">
          <div class="topbar-left">
            <span class="page-title">{{ pageTitle }}</span>
          </div>
          <div class="topbar-right">
            <el-select
              v-model="selectedModel"
              size="small"
              style="width: 180px"
              placeholder="选择模型"
            >
              <el-option
                v-for="m in availableModels"
                :key="m.name"
                :label="m.name"
                :value="m.name"
              />
            </el-select>
            <el-tag :type="apiStatus ? 'success' : 'danger'" size="small" style="margin-left:12px">
              {{ apiStatus ? '● 已连接' : '● 断开' }}
            </el-tag>
          </div>
        </el-header>

        <!-- 内容区 -->
        <el-main class="content-area">
          <!-- 智能对话 -->
          <div v-show="activeMenu === 'chat'">
            <SimpleChat :model="selectedModel" ref="chatInterface" />
          </div>

          <!-- 文档管理：类目管理 -->
          <div v-show="activeMenu === 'kb-categories'">
            <CategoryManager />
          </div>

          <!-- 系统管理 -->
          <div v-show="activeMenu.startsWith('admin')">
            <AdminPanel :active-tab="adminTab" />
          </div>

          <!-- 开发工具 -->
          <div v-show="activeMenu === 'devtools'">
            <DevTools />
          </div>
        </el-main>
      </el-container>
    </el-container>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { Expand, Fold } from '@element-plus/icons-vue'
import { apiService } from './services/api'

import SimpleChat from './components/SimpleChat.vue'
import CategoryManager from './components/doc/CategoryManager.vue'
import AdminPanel from './components/AdminPanel.vue'
import DevTools from './components/DevTools.vue'

const collapsed = ref(false)
const activeMenu = ref('chat')
const selectedModel = ref('qwen-turbo')
const availableModels = ref([])
const apiStatus = ref(false)
const chatInterface = ref(null)

// 菜单 → AdminPanel tab 映射
const adminTabMap = {
  'admin-collections': 'collections',
  'admin-create': 'create',
  'admin-config': 'config',
}
const adminTab = computed(() => adminTabMap[activeMenu.value] || 'namespace')

const pageTitleMap = {
  chat: '智能对话',
  'kb-categories': '类目管理',
  'admin-collections': '知识库列表',
  'admin-create': '创建知识库',
  'admin-config': '配置信息',
  devtools: '开发工具',
}
const pageTitle = computed(() => pageTitleMap[activeMenu.value] || '')

const handleMenuSelect = (key) => {
  activeMenu.value = key
}

const loadModels = async () => {
  try {
    const res = await apiService.getModels()
    availableModels.value = res.models
    selectedModel.value = res.default_model
    apiStatus.value = true
  } catch {
    availableModels.value = [
      { name: 'qwen-turbo', description: '快速' },
      { name: 'qwen-plus', description: '平衡' },
      { name: 'qwen-max', description: '最强' },
    ]
  }
}

onMounted(loadModels)
</script>

<style scoped>
.app-layout {
  height: 100vh;
  overflow: hidden;
}

/* ── 侧边栏 ── */
.sidebar {
  background: #1a1f2e;
  display: flex;
  flex-direction: column;
  transition: width 0.25s;
  overflow: hidden;
}

.sidebar-logo {
  height: 60px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 18px;
  border-bottom: 1px solid rgba(255,255,255,0.08);
  flex-shrink: 0;
}

.logo-icon {
  font-size: 22px;
  color: #409eff;
  flex-shrink: 0;
}

.logo-text {
  font-size: 15px;
  font-weight: 600;
  color: #fff;
  white-space: nowrap;
  overflow: hidden;
}

.sidebar-menu {
  flex: 1;
  border-right: none;
  background: transparent;
  overflow-y: auto;
  overflow-x: hidden;
}

:deep(.sidebar-menu .el-menu-item),
:deep(.sidebar-menu .el-sub-menu__title) {
  color: rgba(255,255,255,0.7);
  height: 46px;
  line-height: 46px;
}

:deep(.sidebar-menu .el-menu-item:hover),
:deep(.sidebar-menu .el-sub-menu__title:hover) {
  background: rgba(255,255,255,0.08) !important;
  color: #fff;
}

:deep(.sidebar-menu .el-menu-item.is-active) {
  background: rgba(64,158,255,0.2) !important;
  color: #409eff !important;
  border-right: 3px solid #409eff;
}

:deep(.sidebar-menu .el-sub-menu .el-menu) {
  background: rgba(0,0,0,0.2);
}

:deep(.sidebar-menu .el-sub-menu .el-menu .el-menu-item) {
  padding-left: 48px !important;
  height: 40px;
  line-height: 40px;
  font-size: 13px;
}

.sidebar-footer {
  padding: 12px;
  display: flex;
  justify-content: center;
  border-top: 1px solid rgba(255,255,255,0.08);
  flex-shrink: 0;
}

.collapse-btn {
  background: rgba(255,255,255,0.1);
  border: none;
  color: rgba(255,255,255,0.6);
}

.collapse-btn:hover {
  background: rgba(255,255,255,0.2);
  color: #fff;
}

/* ── 顶部栏 ── */
.topbar {
  height: 60px !important;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  flex-shrink: 0;
}

.topbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.page-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.topbar-right {
  display: flex;
  align-items: center;
}

/* ── 内容区 ── */
.main-container {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: #f0f2f5;
}

.content-area {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}
</style>
