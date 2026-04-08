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
- 多轮对话，自动指代消解（"它"、"这个" → 明确实体），严格保护专有名词不做翻译
- 改写使用轻量模型（qwen-turbo），不占用主模型资源
- 混合检索：dense（语义）+ BM25（关键词）+ RRF 融合
- 向量化前自动剥离图片占位符（`<<IMAGE:xxx>>`），避免污染向量和 BM25 索引；检索后从 PG 回填含占位符的原始内容供 LLM 使用
- 多文档分组搜索：每个文档取 top-N chunk，保证结果多样性
- 关键词精确预过滤模式
- 每个知识库独立检索参数（ranker / top_k / group_size / memory_turns 等）
- 图文模式：LLM 输出的图片占位符经后处理校验，自动清除非法占位符

### 对话记忆
- 基于 LangGraph `AsyncPostgresSaver`，以 `session_id` 为键持久化 agent 状态
- 重启后端历史不丢失
- 无会话模式（`session_id="default"`）也有持久化记忆
- 对话记忆轮数（`memory_turns`）可在知识库检索配置中设定，默认 2 轮

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

**图片占位符完整处理链路**
切片阶段（doc_image_parser.py）

PDF/DOCX 解析时，文字和图片按页面位置排序交织处理。遇到图片时：

上传图片到 OSS（路径 rag_image/{kb}/{file}/{chunk_id}/xxx.png）
生成 <<IMAGE:xxxxxxxx>>（8位 hex）占位符，直接插入 buffer 文本流
写 knowledge_chunk_image 表（chunk_id, placeholder, oss_key）
最终 chunk 的 content 形如：

这是一段说明文字<<IMAGE:9593bf16>>下面继续文字内容
向量化阶段（milvus_service.upsert_chunks）

content 字段（含占位符）直接送入 DashScope embedding，同时作为 BM25 的 content 字段写入 Milvus。占位符字符串 <<IMAGE:9593bf16>> 会被完整向量化和 BM25 索引。

生成阶段（generate.py）

检索到 chunk 后，批量查 knowledge_chunk_image 表，生成 image_map（placeholder → 预签名 URL）。LLM 的 system prompt 里包含含占位符的 context，LLM 被要求在回答中引用占位符。_sanitize_image_placeholders 过滤掉 LLM 捏造的非法占位符。

前端渲染（SimpleChat.vue）

实时回答：image_map 随 API 响应返回，前端把 <<IMAGE:xxx>> 替换成 ![image](presigned_url) 再用 markdown-it 渲染。

历史消息：conversation_message.image_placeholders 存占位符列表，加载历史时批量调 POST /chunks/resolve-images 获取预签名 URL，再替换渲染。
---

## License

MIT
