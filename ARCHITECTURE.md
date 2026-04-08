# 后端架构文档

## 技术栈

- **框架**：FastAPI + Uvicorn
- **Agent 编排**：LangGraph（StateGraph + AsyncPostgresSaver checkpoint）
- **LLM**：阿里云 DashScope（Qwen 系列模型）
- **向量数据库**：Milvus Standalone（Docker）
- **业务数据库**：PostgreSQL（Docker）
- **对象存储**：阿里云 OSS
- **Embedding**：DashScope text-embedding-v3 / text-embedding-v4（自调用，批量，支持自定义维度）
- **DB 驱动**：psycopg2（业务层）+ psycopg3（LangGraph checkpoint 专用，两者共存互不干扰）

---

## 快速启动

```bash
# 1. 启动 Docker 服务（Milvus + PostgreSQL，首次约 30-60 秒）
docker-compose up -d

# 2. 配置环境变量
cd backend
cp .env.example .env   # 填写必填项见下方

# 3. 安装依赖
pip install -r requirements.txt

# 4. 启动后端（自动建表 + 初始化 LangGraph checkpoint 表）
python main.py
```

### 必填环境变量

```env
DASHSCOPE_API_KEY=sk-xxxx
OSS_BUCKET=your-bucket
ALIBABA_CLOUD_ACCESS_KEY_ID=xxxx
ALIBABA_CLOUD_ACCESS_KEY_SECRET=xxxx
PG_HOST=localhost
PG_USER=your_pg_user
PG_PASSWORD=your_pg_password
MILVUS_HOST=localhost
```

---

## 目录结构

```
backend/
├── main.py
├── app/
│   ├── main.py                    # FastAPI app 工厂，注册路由、lifespan（含 checkpointer 初始化）
│   ├── core/
│   │   ├── config.py              # Settings：所有配置，启动时校验必填项
│   │   ├── exceptions.py          # 统一业务异常
│   │   ├── logging.py             # 结构化日志
│   │   ├── prompts.py             # LLM prompt 模板
│   │   └── checkpointer.py        # LangGraph AsyncPostgresSaver 单例（psycopg3 连接池）
│   ├── api/v1/
│   │   ├── chat.py                # POST /chat
│   │   ├── knowledge.py           # POST /knowledge（RAG 问答，支持 session_id/force_multi_doc/keyword_filter）
│   │   ├── documents.py           # 文档上传/切分/检索/图片代理
│   │   ├── jobs.py                # 任务状态查询、手动向量化
│   │   ├── chunks.py              # 切片查看/编辑/清洗/撤回/向量化/图片管理/resolve-images
│   │   ├── categories.py          # 类目 CRUD（过滤 __default__ 系统类目）
│   │   ├── files.py               # 知识库文件列表/删除
│   │   ├── conversations.py       # 对话会话 CRUD + 消息历史
│   │   ├── system.py              # /health、/models
│   │   └── admin/
│   │       ├── collection.py      # 知识库 CRUD（含 retrieval_config）
│   │       └── config.py          # 系统配置查询
│   ├── services/
│   │   ├── milvus_service.py      # Milvus：collection管理/upsert/hybrid_search（支持分组搜索）
│   │   ├── embedding_service.py   # DashScope embedding，支持 dimension 参数
│   │   ├── chunk_splitter.py      # 纯文本切分（标准模式），中文友好
│   │   ├── document_service.py    # 文档上传（同名拒绝覆盖，关联 __default__ 类目）
│   │   ├── job_service.py         # run_job_pipeline：chunking→chunked（手动触发向量化）
│   │   ├── chunk_service.py       # 切片编辑/清洗/撤回/向量化/图片管理/resolve_image_placeholders
│   │   ├── file_service.py        # 知识库文件列表/联动删除（含 OSS 图片清理 + __default__ 类目清理）
│   │   ├── category_service.py    # 类目 CRUD（含 get_or_create_default_category）
│   │   ├── knowledge_service.py   # Knowledge RAG 业务逻辑（注入 kb retrieval_config，存对话消息）
│   │   ├── conversation_service.py # 对话会话业务逻辑（含删除时清理 OSS 图片）
│   │   ├── chat_service.py        # Chat 业务逻辑
│   │   ├── oss_service.py         # OSS 文件上传/下载/删除/预签名 URL
│   │   ├── doc_image_parser.py    # PyMuPDF 解析 PDF/DOCX，提取文字切片 + 图片
│   │   └── chunk_cleaner.py       # 切片清洗（正则 + LLM）
│   └── db/
│       ├── pg_client.py           # psycopg2 连接池（业务层专用）
│       ├── init_db.py             # 建表脚本（幂等），启动时调用，含 LangGraph checkpoint 表初始化
│       ├── base_repository.py     # BaseRepository
│       ├── kb_repository.py       # knowledge_base 表（含 retrieval_config JSONB）
│       ├── file_repository.py     # knowledge_file 表
│       ├── job_repository.py      # knowledge_job 表
│       ├── chunk_repository.py    # knowledge_chunk + knowledge_chunk_origin 表
│       ├── chunk_image_repository.py  # knowledge_chunk_image 表（含 get_by_placeholders）
│       ├── category_repository.py
│       ├── category_file_repository.py
│       └── conversation_repository.py # conversation_session + conversation_message 表
└── agents/
    ├── knowledge/                 # Knowledge Agent（RAG 流水线）
    │   ├── graph.py               # StateGraph，编译时注入 AsyncPostgresSaver checkpointer
    │   ├── state.py               # KnowledgeAgentState + RAGConfig（含检索参数字段）
    │   ├── services/retrieval.py  # RetrievalService：hybrid / keyword_filter+hybrid / 分组搜索
    │   └── nodes/                 # query_rewrite/classify/retrieve/filter/rerank/generate...
    ├── supervisor/
    └── specialized/               # email/search（mock）
```

---

## 数据库表结构

### PostgreSQL

| 表名 | 用途 | 主键 |
|------|------|------|
| `knowledge_base` | 知识库配置（name/image_mode/embedding_model/vector_dim/metadata_fields/retrieval_config） | UUID |
| `knowledge_category` | 类目（独立体系，含系统内置 `__default__` 类目） | UUID |
| `knowledge_category_file` | 类目文件（OSS 引用） | UUID |
| `knowledge_file` | 知识库文件（kb_id + oss_key，UNIQUE 约束防重复） | UUID |
| `knowledge_job` | 处理任务（状态机） | UUID |
| `knowledge_chunk` | 切片当前内容（可编辑） | UUID |
| `knowledge_chunk_origin` | 切片原始内容（只写一次，用于撤回） | UUID（FK→chunk） |
| `knowledge_chunk_image` | 切片图片（图文模式，placeholder 有索引） | UUID |
| `conversation_session` | 对话会话元数据（user_id/kb_name/title） | UUID |
| `conversation_message` | 对话消息（role/content/sources/image_placeholders） | UUID |
| LangGraph checkpoint 表 | 由 `PostgresSaver.setup()` 自动创建，存 agent 状态快照 | - |

`knowledge_base` 含 `retrieval_config JSONB` 字段，存检索参数：
```json
{
  "ranker": "RRF",
  "rrf_k": 60,
  "hybrid_alpha": 0.5,
  "multi_doc_top_k": 20,
  "multi_doc_group_size": 3,
  "strict_group_size": false,
  "single_doc_top_k": 20
}
```

### 实体关系

```
knowledge_base
    └── knowledge_file (kb_id)  ← UNIQUE(kb_id, oss_key)，同名文件拒绝覆盖
              └── knowledge_job (file_id, kb_id)
                        └── knowledge_chunk (job_id)
                                  ├── knowledge_chunk_origin (chunk_id)
                                  └── knowledge_chunk_image (chunk_id)

knowledge_category  ← 含系统内置 __default__ 类目（对用户不可见）
    └── knowledge_category_file (category_id)
              └── knowledge_file.category_file_id (FK, SET NULL on delete)

conversation_session (user_id, kb_name)
    └── conversation_message (session_id)
```

### Milvus（向量数据）

每个知识库对应一个 Milvus collection，schema：

| 字段 | 类型 | 说明 |
|------|------|------|
| `chunk_id` | VARCHAR(36) PK | UUID，与 PG knowledge_chunk.id 对应 |
| `job_id` | VARCHAR | 关联 PG knowledge_job.id |
| `file_name` | VARCHAR | 文件名 |
| `chunk_index` | INT64 | 切片序号 |
| `content` | VARCHAR | 纯文本内容（已剥离图片占位符，enable_analyzer + enable_match，中文分析器） |
| `sparse_bm25` | SPARSE_FLOAT_VECTOR | BM25 Function 自动生成 |
| `dense` | FLOAT_VECTOR(dim) | DashScope embedding，dim 由知识库配置决定 |
| `[metadata_fields]` | VARCHAR | 用户配置的 fulltext 字段（如 title），enable_match=True |
| dynamic fields | - | 其他 metadata |

> **注意**：Milvus `content` 字段存储的是 `fulltext前缀 + 剥离占位符后的纯文本`，不含 `<<IMAGE:xxx>>` 占位符，避免污染向量和 BM25 索引。检索命中后，`hybrid_search` 会批量回填 PG `knowledge_chunk.content`（含占位符的原始内容），供 generate 节点构建 LLM context 时使用。

索引：HNSW（dense）+ SPARSE_WAND（sparse_bm25）

---

## OSS 存储路径规范

| 路径 | 用途 | 生命周期 |
|------|------|------|
| `kb/{kb_name}/{file_name}` | 单文件直传到知识库 | 随知识库文件删除 |
| `category/{category_name}/{file_name}` | 类目文件 | 随类目文件删除 |
| `rag_image/{kb_name}/{file_name}/{chunk_id}/xxx.png` | 旧路径（已废弃） | - |
| `conversation_assets/{placeholder_hex}/image.{ext}` | 切片图片（图文模式，与知识库文件生命周期绑定） | 随知识库文件删除；删除对话不删除此路径图片 |

**重要**：切片图片统一存储在 `conversation_assets/` 路径，生命周期与知识库文件绑定。删除知识库文件时会同步删除对应图片（OSS + PG），历史对话中的图片因此无法显示（符合预期，文件已过时）。删除对话会话时不删除任何图片。

---

## 核心业务流程

### 1. 文档上传流程

**路径一：单文件直传到知识库**
```
POST /documents/upload (kb_name, file)
  → 校验文件名/格式/大小
  → 检查同名文件是否已存在（UNIQUE kb_id+oss_key），存在则 409 拒绝
  → 上传 OSS: kb/{kb_name}/{file_name}
  → 关联到 __default__ 类目（knowledge_category_file）
  → 写 knowledge_file（category_file_id 指向 __default__ 记录）
  → 写 knowledge_job(pending)
  → BackgroundTask: run_job_pipeline()
```

**路径二：类目文件批量切分**
```
POST /documents/start-chunking/{category_id}?kb_name=xxx
  → 遍历 category_file
  → 检查同名文件是否已存在，存在则跳过（返回 skipped 列表）
  → 写 knowledge_file + knowledge_job
  → BackgroundTask: run_job_pipeline()
```

**切分流水线**
```
run_job_pipeline():
  chunking → 下载 OSS → 切分（图文/标准）
    └── 注入 auto_inject 元数据（如 title = 文件名前缀）
  chunked → 写 knowledge_chunk（UUID 主键）+ origin
    ← 停在此状态，等待人工审查后手动触发向量化

POST /chunks/job/{job_id}/upsert（手动触发）
  → 读 PG chunks → 剥离图片占位符（<<IMAGE:xxx>>）得到 clean_content
  → fulltext 字段拼接到 clean_content 前（BM25 + dense 都感知，但不含占位符噪音）
  → embed → upsert Milvus（content 存 fulltext前缀+clean_content）→ mark_vectorized → done
```

### 2. RAG 问答流程

```
POST /knowledge (query, session_id, collection, force_multi_doc?, keyword_filter?)
  → knowledge_service（async）:
      1. 从 PG 读取 kb.retrieval_config，注入到 RAGConfig
      2. 构建 LangGraph initial_state（只含当前 query，不传历史消息）
      3. await agent.ainvoke(state, config={"configurable": {"thread_id": session_id}})
         ← LangGraph 通过 thread_id=session_id 从 AsyncPostgresSaver 自动恢复历史
         ← KnowledgeAgentState.messages 使用 add_messages reducer，checkpointer 负责累加
         ← 每次只传当前 query，历史由 checkpointer 自动合并，禁止手动传入历史消息
      4. 问答完成后，仅当 session_id 对应 conversation_session 表中真实记录时，
         才将 user/assistant 消息存入 conversation_message 表
```

**对话记忆的两层存储（职责分离）**
```
LangGraph checkpointer（AsyncPostgresSaver，4张系统表）：
  - 存储完整 agent state 快照（messages 历史、检索中间结果等）
  - 供 query_rewrite 节点做多轮指代消解，供 generate 节点感知历史上下文
  - 按 thread_id=session_id 隔离，重启后端历史不丢失
  - 数据格式为 LangGraph 内部序列化格式，不可直接读取

conversation_message 表（业务层）：
  - 仅存 role/content/sources/image_placeholders，供前端展示历史对话
  - 仅当 session_id 在 conversation_session 表中存在时才写入
  - session_id="default" 时不写入（无会话模式，checkpointer 仍正常工作）
```

**无会话模式 vs 有会话模式**
```
无会话模式（session_id="default"，前端未新建对话）：
  - checkpointer 以 thread_id="default" 存状态，所有无会话请求共享同一历史
  - 不写 conversation_message 表，左侧列表不可见
  - 对话记忆持久化在 PostgreSQL checkpoint 表，重启不丢

有会话模式（session_id=UUID，前端新建对话后）：
  - checkpointer 以 thread_id=UUID 存状态，每个会话独立隔离
  - 写 conversation_message 表，左侧列表可见，支持历史查看/删除
```

**RAG 流水线节点**
```
query_rewrite（多轮指代消解）→ query_classify → determine_retrieval_strategy
  ↓
  [用户覆盖逻辑]
  - force_multi_doc=True → 跳过 LLM 分类，直接 multi_doc
  - keyword_filter 有值 → 跳过规则判断，直接 KEYWORD_ONLY
  ↓
  route_by_query_type:
    single_doc → single_doc_retrieve → generate_answer
    multi_doc  → multi_doc_retrieve（分组搜索 group_by_field=file_name）
               → filter_chunks → rerank_chunks → generate_answer

  [检索后处理]
  hybrid_search 返回 hits 后，批量查 PG knowledge_chunk（WHERE id IN chunk_ids），
  将 current_content（含图片占位符）回填到 hits[].content，
  确保 generate 节点拿到的是含占位符的原始内容，而非 Milvus 中的 clean 版本。
  ↓
  generate_answer（从 state.messages 读历史上下文；图文模式：查 chunk_image，生成预签名 URL 填入 image_map）
  → quality_check → finalize_metrics
```

**query_rewrite 多轮指代消解**
```
有历史（state.messages[:-1] 非空）：
  - 使用 KNOWLEDGE_QUERY_REWRITE_WITH_HISTORY_SYSTEM prompt
  - 取最近 memory_turns 轮历史（默认 2 轮，即 4 条消息），可在 kb.retrieval_config 配置
  - 只做指代消解和主语补全，严格保持专有名词不变（禁止翻译，如 21V 不改写为 21伏特）
  - 如不确定如何消解，原样返回原问题

无历史（第一轮对话）：
  - 使用 KNOWLEDGE_QUERY_REWRITE_SYSTEM prompt（简单规范化，同样保护专有名词）
```

**检索策略**
```
determine_retrieval_strategy:
  ├── KEYWORD_ONLY（含错误码/代码/精确匹配关键词，或用户指定 keyword_filter）
  │     → TEXT_MATCH 预过滤 + dense + BM25 hybrid_search
  └── HYBRID（常规查询）
        → dense + BM25 hybrid_search（RRF 或 WeightedRanker）

multi_doc_retrieve 使用分组搜索（Milvus group_by_field）：
  - group_by_field="file_name"：每个文档取 top-N chunk，保证结果多样性
  - 参数来自 kb.retrieval_config（multi_doc_top_k / multi_doc_group_size / strict_group_size）

hybrid_search 参数（均来自 kb.retrieval_config）：
  - ranker: RRF（默认）| Weight（hybrid_alpha 控制 dense 权重）
  - rrf_k: RRFRanker k 参数（默认 60）
  - keyword_filter: TEXT_MATCH(content, '关键词') 预过滤候选集
```

### 3. 对话记忆与会话管理

```
会话模型：
  conversation_session（id, user_id, kb_name, title）
    └── conversation_message（role, content, sources, image_placeholders）

LangGraph checkpoint（thread_id = session_id）：
  → 存储完整 agent 状态快照（messages 历史）
  → 同一 session_id 的请求自动续上上次对话上下文
  → 使用 AsyncPostgresSaver，数据存入 PostgreSQL 4张系统表：
      checkpoints / checkpoint_blobs / checkpoint_writes / checkpoint_migrations
  → 这4张表由 LangGraph 自动管理，格式为内部序列化格式，无需手动读写

重要约束：
  → KnowledgeAgentState.messages 使用 add_messages reducer（增量追加语义）
  → 每次 ainvoke 只传当前 query 的 HumanMessage，历史由 checkpointer 自动恢复
  → 禁止手动将历史消息传入 initial_state，否则 add_messages 会导致消息重复累加 → 502
```

图片显示：
  - content 存占位符原文（<<IMAGE:abc123>>），不存 URL
  - 查看历史时：前端提取占位符 → POST /chunks/resolve-images → 后端生成预签名 URL
  - 预签名 URL 有效期 1 小时，按需生成，不持久化

多用户扩展预留：
  - conversation_session.user_id 字段，当前单用户固定 'default'
  - 后续加认证后直接替换 user_id 即可
  - checkpointer 按 thread_id=session_id 天然隔离，多用户无需额外改动
```

### 4. 图片管理

```
切片图片上传（图文模式）：
  POST /chunks/job/{job_id}/chunk/{chunk_index}/images
    → 生成 placeholder_hex（8位 UUID hex）
    → placeholder = <<IMAGE:{placeholder_hex}>>
    → OSS 路径: conversation_assets/{placeholder_hex}/image.{ext}
    → 写 knowledge_chunk_image（chunk_id, placeholder, oss_key）
    → 返回预签名 URL（1小时有效）

图片 URL 解析（批量）：
  POST /chunks/resolve-images
    body: { "placeholders": ["<<IMAGE:abc123>>", ...] }
    → 查 knowledge_chunk_image WHERE placeholder IN (...)
    → 生成预签名 URL 返回
    → 用于：历史对话图片展示 / 切片编辑器图片加载

删除知识库文件：
  → 删除 rag_image/ 路径下的图片（旧路径兼容）
  → 不删除 conversation_assets/ 路径下的图片（保护历史对话）

删除对话会话：
  → 删除 PG conversation_session（CASCADE 删 conversation_message）
  → 不删除任何 OSS 图片（图片生命周期归属知识库文件，不属于对话）
  → image_placeholders 字段仅用于前端 resolve-images 展示，不用于 OSS 清理
```

### 5. 删除联动

```
DELETE /files（file_id）
  → Milvus 删除向量（by job_id）
  → OSS 删除 rag_image/ 图片（旧路径）
  → 若关联 __default__ 类目，清理 knowledge_category_file 记录
  → PG CASCADE 删除 knowledge_file → job → chunk → chunk_origin → chunk_image
```

---

## 知识库检索配置（retrieval_config）

每个知识库可独立配置检索参数，存储在 `knowledge_base.retrieval_config`：

| 参数 | 说明 | 默认值 |
|------|------|------|
| `ranker` | Rerank 策略：RRF / Weight | RRF |
| `rrf_k` | RRFRanker k 参数 | 60 |
| `hybrid_alpha` | WeightedRanker dense 权重（0~1） | 0.5 |
| `multi_doc_top_k` | 多文档：返回文档组数 | 20 |
| `multi_doc_group_size` | 多文档：每文档取 chunk 数 | 3 |
| `strict_group_size` | 多文档：是否严格凑满 group_size | false |
| `single_doc_top_k` | 单文档：返回 chunk 数 | 20 |
| `llm_context_top_k` | 最终送入 LLM 的切片数上限 | 10 |
| `memory_turns` | 对话记忆轮数（每轮=1问+1答），用于改写和生成 | 2 |

配置在创建知识库时设定，也可通过 `PUT /admin/collections/{kb_name}` 随时更新。

---

## 元数据字段（metadata_fields）

创建知识库时可配置元数据字段，存储在 `knowledge_base.metadata_fields`：

```json
[{"key": "title", "type": "text", "fulltext": true, "index": false, "auto_inject": "filename_prefix"}]
```

- `fulltext: true`：在 Milvus schema 中显式声明该字段并开启 `enable_match=True`（倒排索引）
- `auto_inject: "filename_prefix"`：切分时自动将文件名前缀注入到每个 chunk 的 metadata
- upsert 时 fulltext 字段值拼接到 `content` 前面，BM25 和 dense embedding 均感知

---

## Embedding 配置

- 支持模型：`text-embedding-v3`（64/128/256/512/768/1024 维）、`text-embedding-v4`（1536/2048 维）
- 每个知识库独立配置 `embedding_model` + `vector_dim`，upsert 时按 kb 配置调用，并校验返回维度
- 全局默认值由 `.env` 的 `EMBEDDING_MODEL` / `EMBEDDING_DIMENSION` 控制

---

## API 路由

| 路径 | 说明 |
|------|------|
| `POST /api/v1/chat/` | 普通对话（Supervisor Agent） |
| `POST /api/v1/knowledge/` | RAG 问答（session_id/force_multi_doc/keyword_filter；历史由 checkpointer 自动管理，无需传 messages） |
| `GET/POST /api/v1/admin/collections` | 知识库管理（含 retrieval_config） |
| `PUT /api/v1/admin/collections/{kb_name}` | 更新知识库配置（含 retrieval_config） |
| `POST /api/v1/documents/upload` | 单文件上传到知识库（同名拒绝，关联 __default__ 类目） |
| `POST /api/v1/documents/upload-to-category` | 上传文件到类目（OSS） |
| `POST /api/v1/documents/start-chunking/{category_id}` | 触发类目批量切分（同名跳过，返回 skipped） |
| `POST /api/v1/documents/search` | 切片检索（支持 keyword_filter + hybrid） |
| `GET /api/v1/documents/image-proxy` | OSS 图片代理（降级方案） |
| `GET /api/v1/jobs` | 任务列表（需 kb_name） |
| `POST /api/v1/jobs/{job_id}/upsert` | 手动触发向量化 |
| `GET /api/v1/chunks/job/{job_id}` | 查看切片 |
| `POST /api/v1/chunks/job/{job_id}/upsert` | 切片向量化 |
| `POST /api/v1/chunks/resolve-images` | 批量占位符→预签名 URL（历史对话图片展示） |
| `GET /api/v1/files` | 文件列表（需 kb_name） |
| `DELETE /api/v1/files` | 删除文件（body: file_id） |
| `GET /api/v1/categories` | 类目列表（过滤 __default__） |
| `GET /api/v1/conversations` | 会话列表（需 kb_name） |
| `POST /api/v1/conversations` | 新建会话 |
| `GET /api/v1/conversations/{session_id}/messages` | 获取历史消息 |
| `DELETE /api/v1/conversations/{session_id}` | 删除会话（含 OSS 图片清理） |
| `GET /api/v1/health` | 健康检查 |

---

## 前端功能说明

### 知识库问答（SimpleChat.vue）
- 知识库模式下有可折叠的会话侧边栏，支持新建/切换/删除会话
- 切换会话时加载历史消息，批量调 `resolve-images` 渲染图片
- toolbar 有两个检索控制 pill 按钮：
  - **多文档**：强制使用多文档分组搜索，跳过 LLM 分类
  - **关键词**：启用关键词精确预过滤，需输入关键词

### 知识库管理（AdminPanel.vue）
- 创建知识库时可配置检索参数（ranker/alpha/top_k/group_size 等）
- 知识库列表每行有"配置"按钮，可随时修改检索参数

### 切片编辑器（ChunkEditorPanel.vue）
- 图文模式下，图片加载改为批量调 `resolve-images`（一次请求替代 N 个逐切片请求）
- 图片 URL 原地更新（Object.assign），不触发 Vue 重渲染

---

## 异常处理

```
业务异常（AppError 子类）→ FastAPI exception_handler → 对应 HTTP 状态码
  ConflictError(409)：同名文件已存在、知识库已存在
  NotFoundError(404)：资源不存在
  ForbiddenError(403)：已向量化切片不允许修改
未处理异常 → 500
```

---

## 常见问题

**Q: Milvus 启动慢？**
首次启动需 30-60 秒初始化 etcd 和 MinIO，等 `docker-compose ps` 显示 healthy 再启后端。

**Q: embedding 报 Model access denied？**
检查 `DASHSCOPE_API_KEY` 是否开通了对应 embedding 模型的权限。

**Q: 向量维度不匹配？**
知识库创建时的 `vector_dim` 必须与 embedding 模型实际输出维度一致。已有 collection 需删除重建。

**Q: 图文模式支持哪些格式？**
仅 `.pdf` 和 `.docx`。标准模式支持 `.pdf`、`.doc`、`.docx`、`.txt`、`.md`、`.ppt`、`.pptx`。

**Q: 切分后 job 状态停在 chunked？**
正常，切分和向量化已解耦。在文件列表页选中文件点"上传向量库"手动触发。

**Q: 上传同名文件报 409？**
设计如此，防止静默覆盖。请先在文件列表删除旧版本，再重新上传。

**Q: LangGraph checkpoint 表初始化失败？**
需先安装 `pip install "psycopg[binary]" langgraph-checkpoint-postgres`，然后重启后端。

**Q: 历史对话图片显示不出来？**
图片存储在 `conversation_assets/` 路径，与知识库文件解耦，不会因删除文件而丢失。若仍无法显示，检查 OSS 预签名 URL 是否过期（有效期 1 小时，刷新页面重新 resolve 即可）。

**Q: 对话记忆是怎么实现的？**
使用 LangGraph `AsyncPostgresSaver` checkpointer，以 `thread_id=session_id` 为键存储完整 agent state 快照到 PostgreSQL（4张系统表：checkpoints/checkpoint_blobs/checkpoint_writes/checkpoint_migrations）。每次 `ainvoke` 只传当前 query，历史自动恢复。`KnowledgeAgentState.messages` 使用 `add_messages` reducer，禁止手动传入历史消息，否则会导致消息重复累加报 502。

**Q: 不新建对话也有对话记忆吗？**
有。`session_id="default"` 时 checkpointer 以 `thread_id="default"` 存状态，历史持久化在 PostgreSQL，重启不丢。但消息不写入 `conversation_message` 表，左侧列表不可见。新建对话后才会写入业务表并在左侧显示。

**Q: 多轮对话中代词指代（"它"、"这个"）能正确检索吗？**
能。`query_rewrite` 节点有历史时会使用指代消解版 prompt，取最近 `memory_turns` 轮历史（默认 2 轮，可在 `retrieval_config` 配置），将代词替换为明确实体后再做向量检索。改写使用轻量的 `llm_clean_model`（qwen-turbo），严格保护专有名词不做翻译。图文模式下 LLM 输出的图片占位符会经过后处理校验，非法占位符自动清除。

**Q: Attu 端口冲突？**
`docker-compose.yml` 中 attu 映射的是宿主机 `8080:3000`，后端用 `8000`，不冲突。

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
