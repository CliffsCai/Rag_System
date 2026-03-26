# LangGraph 多智能体系统

> 文档状态（2026-03）：本仓库以当前代码结构为准。若本文与实现有差异，请优先参考 `PROJECT_STRUCTURE_MASTER.md` 与实际代码路径。

基于 LangGraph 官方推荐的**多智能体架构**，使用千问模型构建的智能对话系统。

## 🎯 核心特性

### 多智能体协作系统
- ✅ **Supervisor Agent**: 主管智能体，负责任务分析和协调
- ✅ **Email Agent**: 邮件专家，处理邮件相关任务
- ✅ **Search Agent**: 搜索专家，处理信息检索任务
- ✅ **易于扩展**: 添加新智能体只需3步

### 技术优势
- ✅ **智能路由**: Supervisor 自动选择合适的专家智能体
- ✅ **专业化分工**: 每个智能体专注特定领域
- ✅ **独立上下文**: 避免上下文混乱
- ✅ **Token 优化**: 只加载需要的智能体

## 🏗️ 系统架构

```
┌─────────────────────────────────────┐
│      Supervisor Agent (主管)        │
│   - 分析用户请求                     │
│   - 选择合适的子智能体               │
│   - 协调多个智能体                   │
│   - 综合结果并回复用户               │
└──────────┬──────────────────────────┘
           │ 调用 (as tools)
           ├──────────┬──────────
           ↓          ↓          
    ┌──────────┐ ┌──────────┐
    │  Email   │ │  Search  │
    │  Agent   │ │  Agent   │
    │          │ │          │
    │ 2 tools  │ │ 3 tools  │
    └──────────┘ └──────────┘
```

## 📁 项目结构

```
├── backend/                    # 后端服务
│   ├── main.py                 # 启动入口
│   ├── app/                    # FastAPI 应用层
│   │   ├── main.py             # 应用装配（/api/v1）
│   │   ├── api/v1/             # chat/knowledge/system/documents/admin
│   │   ├── core/               # 配置
│   │   └── models/             # 请求/响应模型
│   ├── agents/                 # LangGraph 图与智能体
│   │   ├── supervisor/         # 普通对话（多智能体调度）
│   │   ├── knowledge/          # 知识库问答（增强 RAG）
│   │   ├── document_upload/    # 文档上传处理图
│   │   └── specialized/        # email/search 等专业智能体
│   └── requirements.txt
├── frontend/               # Vue.js 前端
│   ├── src/
│   │   ├── components/     # UI 组件
│   │   └── services/       # API 服务
│   └── package.json
└── PROJECT_STRUCTURE_MASTER.md # 统一结构文档
```

## 🚀 快速开始

### 1. 环境准备

**后端要求:**
- Python 3.8+
- pip 包管理器

**前端要求:**
- Node.js 16+
- npm 或 yarn

### 2. 后端设置

```bash
# 进入后端目录
cd backend

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，设置你的 DashScope API Key
```

**环境变量配置 (.env):**
```bash
# DashScope API Key (必需)
DASHSCOPE_API_KEY=sk-your-dashscope-api-key

# 模型配置
LLM_MODEL=qwen-turbo

# SSL 配置 (开发环境)
PYTHONHTTPSVERIFY=0
```

### 3. 前端设置

```bash
# 进入前端目录
cd frontend

# 安装依赖
npm install
```

### 4. 启动服务

**方式1：使用启动脚本（推荐）**
```bash
# Windows
start.bat

# Linux/Mac
./start.sh
```

**方式2：手动启动**

后端：
```bash
cd backend
python main.py
# API: http://localhost:8000
# 文档: http://localhost:8000/docs
```

前端：
```bash
cd frontend
npm run dev
# 界面: http://localhost:5173
```

## 💡 使用示例

### 示例1：单一任务
```
用户: "帮我发邮件给张三"

Supervisor 分析 → 选择 Email Agent
Email Agent 执行 → send_email 工具
返回结果 → "邮件已发送给张三"
```

### 示例2：复合任务
```
用户: "搜索人工智能最新进展，然后发邮件给老板"

Supervisor 分析 → 需要 Search + Email
1. 调用 Search Agent → 搜索信息
2. 调用 Email Agent → 发送邮件
综合结果 → "已完成搜索并发送邮件"
```

### 示例3：智能选择
```
用户: "北京天气怎么样？"

Supervisor 分析 → 选择 Search Agent
Search Agent 执行 → get_weather 工具
返回结果 → "北京：25°C，晴天"
```

## 支持的模型

| 模型 | 描述 | 最大 Token |
|------|------|-----------|
| qwen-turbo | 快速响应，适合简单任务 | 8,000 |
| qwen-plus | 平衡性能和成本 | 32,000 |
| qwen-max | 最强性能，适合复杂任务 | 8,000 |
| qwen-long | 支持长文本 | 2,000,000 |
| qwen-vl-plus | 视觉理解模型 | 8,000 |
| qwen-coder-plus | 代码生成专用 | 8,000 |
| qwen-math-plus | 数学推理专用 | 4,000 |

## API 端点

### 基础端点
- `GET /api/v1/` - 健康检查
- `GET /api/v1/health` - 详细健康状态
- `GET /api/v1/models` - 获取可用模型列表

### 对话端点
- `POST /api/v1/chat/` - 智能对话
- `POST /api/v1/knowledge/` - 知识库问答

### 请求示例

**智能对话:**
```json
{
  "messages": [
    {"role": "user", "content": "你好"}
  ],
  "model": "qwen-turbo"
}
```

**知识问答:**
```json
{
  "query": "什么是人工智能？",
  "session_id": "user_123",
  "model": "qwen-plus"
}
```

## 🔧 开发指南

### 添加新的智能体

**步骤1：创建智能体文件**

```python
# backend/agents/database_agent.py
from langgraph.graph import StateGraph
from langchain_core.tools import tool

@tool
def query_database(sql: str) -> str:
    """执行SQL查询"""
    return "查询结果"

def create_database_agent(model):
    """创建数据库智能体"""
    builder = StateGraph(DatabaseAgentState)
    # 添加节点和边...
    return builder.compile()

DATABASE_AGENT_INFO = {
    "name": "database_agent",
    "display_name": "数据库智能体",
    "description": "专门处理数据库查询和操作",
    "capabilities": ["SQL查询", "数据插入"],
    "keywords": ["数据库", "database", "SQL"]
}
```

**步骤2：注册到 Supervisor**

在 `supervisor_agent.py` 中：
1. 导入新智能体
2. 添加到 `SUB_AGENTS_REGISTRY`
3. 在 `create_supervisor_tools` 中创建工具包装

**步骤3：重启服务**

完成！新智能体自动集成到系统中。

### 修改现有智能体

- **添加工具**: 在对应的 `*_agent.py` 文件中添加 `@tool` 装饰的函数
- **修改逻辑**: 更新 `create_*_agent` 函数中的图结构
- **更新描述**: 修改 `*_AGENT_INFO` 字典

### 前端开发

- **组件**: `frontend/src/components/`
- **API 服务**: `frontend/src/services/api.js`
- **样式**: 修改各组件的 `<style>` 部分

## 故障排除

### 常见问题

**1. API Key 错误**
- 确认 DashScope API Key 格式正确
- 检查 API Key 是否有效且有余额

**2. 连接错误**
- 检查网络连接
- 确认防火墙设置
- 尝试设置 `PYTHONHTTPSVERIFY=0`

**3. 前端无法连接后端**
- 确认后端服务已启动 (http://localhost:8000)
- 检查 CORS 配置
- 查看浏览器控制台错误

**4. 模型调用失败**
- 检查模型名称是否正确
- 确认 API Key 有调用该模型的权限
- 查看后端日志

### 调试技巧

**后端调试:**
```bash
# 查看详细日志
python backend/main.py

# 测试 API 连接
curl http://localhost:8000/api/v1/health
```

**前端调试:**
- 打开浏览器开发者工具
- 查看 Network 标签页的请求
- 查看 Console 标签页的错误

## 📚 文档

- **统一结构说明**: `PROJECT_STRUCTURE_MASTER.md`
- **后端说明**: `backend/README.md`
- **知识 Agent 说明**: `backend/agents/knowledge/README.md`
- **请求流程说明**: `backend/REQUEST_FLOW.md`

## 🎓 技术栈

- **LangGraph**: 多智能体框架
- **LangChain**: 工具和模型集成
- **DashScope**: 千问模型 API
- **FastAPI**: 后端 API 服务器
- **Vue.js + Element Plus**: 前端界面
- **Python 3.8+**: 后端语言
- **Node.js 16+**: 前端构建工具

## 🤝 贡献指南

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

## 📄 许可证

MIT License

## 💬 联系方式

如有问题或建议，请创建 Issue。