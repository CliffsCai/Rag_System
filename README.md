# Knowledge Base RAG System

一个基于 LangGraph + Milvus 的企业级知识库问答系统，支持多轮对话、混合检索、图文解析。

## 技术栈

**后端**
- FastAPI + Uvicorn
- LangGraph（StateGraph + AsyncPostgresSaver）
- 阿里云 DashScope（Qwen 系列 LLM + Embedding）
- Milvus Standalone（向量数据库，混合检索）
- PostgreSQL（业务数据 + LangGraph checkpoint）
- 阿里云 OSS（文件存储）

**前端**
- Vue 3 + Vite

## 快速开始

### 1. 启动基础服务

```bash
docker-compose up -d
```

首次启动需等待 30-60 秒，直到所有服务变为 `healthy`：

```bash
docker-compose ps
```

### 2. 配置环境变量

```bash
cd backend
cp .env.example .env
```

编辑 `.env`，填写必填项：

| 变量 | 说明 |
|------|------|
| `DASHSCOPE_API_KEY` | 阿里云 DashScope API Key |
| `ALIBABA_CLOUD_ACCESS_KEY_ID` | 阿里云 AccessKey ID（OSS 用） |
| `ALIBABA_CLOUD_ACCESS_KEY_SECRET` | 阿里云 AccessKey Secret（OSS 用） |
| `OSS_BUCKET` | OSS Bucket 名称 |

其余配置项有默认值，本地开发无需修改。

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

> LangGraph checkpoint 需要额外安装：
> ```bash
> pip install "psycopg[binary]" langgraph-checkpoint-postgres
> ```

### 4. 启动后端

```bash
python main.py
```

启动时自动建表并初始化 LangGraph checkpoint 表。后端默认运行在 `http://localhost:8000`。

### 5. 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端默认运行在 `http://localhost:5173`。

---

## 项目结构

```
├── docker-compose.yml        # Milvus + PostgreSQL + MinIO + Attu
├── backend/
│   ├── main.py               # 入口
│   ├── requirements.txt
│   ├── .env.example          # 环境变量模板
│   ├── app/
│   │   ├── api/v1/           # REST API 路由
│   │   ├── core/             # 配置、日志、异常、Prompt
│   │   ├── services/         # 业务逻辑
│   │   └── db/               # 数据库 Repository
│   └── agents/
│       ├── knowledge/        # RAG Agent（核心）
│       ├── supervisor/       # Supervisor Agent
│       └── specialized/      # 专用 Agent（email/search）
└── frontend/
    └── src/
        ├── components/       # Vue 组件
        └── services/         # API 调用
```

---

## 核心功能

### 知识库管理
- 创建知识库，支持独立配置 embedding 模型、向量维度、检索参数
- 文档上传（PDF / DOCX / TXT / MD / PPT），同名文件拒绝覆盖
- 切分与向量化解耦：切分后人工审查，手动触发向量化
- 图文模式：自动提取 PDF/DOCX 中的图片，与文本切片关联

### RAG 问答
- 多轮对话，自动指代消解（"它"、"这个" → 明确实体）
- 混合检索：dense（语义）+ BM25（关键词）+ RRF 融合
- 多文档分组搜索：每个文档取 top-N chunk，保证结果多样性
- 关键词精确预过滤模式
- 每个知识库独立检索参数（ranker / top_k / group_size 等）

### 对话记忆
- 基于 LangGraph `AsyncPostgresSaver`，以 `session_id` 为键持久化 agent 状态
- 重启后端历史不丢失
- 无会话模式（`session_id="default"`）也有持久化记忆

---

## 服务端口

| 服务 | 端口 |
|------|------|
| 后端 API | 8000 |
| 前端 | 5173 |
| PostgreSQL | 5432 |
| Milvus | 19530 |
| Attu（Milvus GUI） | 8080 |
| MinIO Console | 9001 |

---

## 常见问题

**Milvus 启动慢？**
首次启动需初始化 etcd 和 MinIO，等 `docker-compose ps` 显示 `healthy` 再启后端。

**embedding 报 Model access denied？**
检查 `DASHSCOPE_API_KEY` 是否开通了对应 embedding 模型的权限。

**切分后 job 状态停在 `chunked`？**
正常，切分和向量化已解耦。在文件列表页选中文件点"上传向量库"手动触发。

**上传同名文件报 409？**
设计如此，防止静默覆盖。先在文件列表删除旧版本，再重新上传。

**历史对话图片显示不出来？**
OSS 预签名 URL 有效期 1 小时，刷新页面重新 resolve 即可。

更多问题参见 [ARCHITECTURE.md](./ARCHITECTURE.md)。

---

## License

MIT
