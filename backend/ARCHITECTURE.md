# 后端架构文档

## 技术栈

- **框架**：FastAPI + Uvicorn
- **Agent 编排**：LangGraph（StateGraph）
- **LLM**：阿里云 DashScope（Qwen 系列模型）
- **向量数据库**：阿里云 ADB PostgreSQL（AnalyticDB）
- **对象存储**：阿里云 OSS
- **业务数据库**：ADB PostgreSQL（通过 ExecuteStatement API 执行 SQL）

---

## 目录结构

```
backend/
├── main.py                        # 启动入口，运行 uvicorn
├── app/
│   ├── main.py                    # FastAPI app 工厂，注册路由、中间件、全局异常处理
│   ├── core/
│   │   ├── config.py              # 所有配置（Settings 类 + SUPPORTED_MODELS 常量）
│   │   │                          # 含 _validate_env()：启动时校验必填环境变量
│   │   ├── exceptions.py          # 统一业务异常体系（AppError 及子类）
│   │   ├── logging.py             # 结构化日志配置（JsonFormatter + setup_logging）
│   │   └── prompts.py             # 所有 LLM prompt 模板集中管理
│   ├── models/
│   │   ├── requests.py            # Pydantic 请求模型（ChatRequest、KnowledgeRequest）
│   │   └── responses.py           # Pydantic 响应模型（ChatResponse、KnowledgeResponse 等）
│   ├── api/v1/
│   │   ├── __init__.py            # 汇总所有子路由，挂载到 /api/v1
│   │   ├── chat.py                # POST /chat → 调用 supervisor_agent
│   │   ├── knowledge.py           # POST /knowledge → 调用 knowledge_agent（RAG 问答）
│   │   ├── documents.py           # 文档上传、OSS 文件切分触发、图片代理
│   │   ├── jobs.py                # 任务状态查询、fetch-chunks（下载 JSONL 切片入库）
│   │   ├── chunks.py              # 切片查看/编辑/LLM清洗/撤回/上传向量库
│   │   ├── categories.py          # 类目 CRUD
│   │   ├── files.py               # 文件列表查询、文件删除（联动 ADB+OSS+本地库）
│   │   ├── system.py              # /health、/models、/ 根路由
│   │   └── admin/
│   │       ├── __init__.py        # 汇总 admin 子路由，挂载到 /admin
│   │       ├── _deps.py           # 公共依赖：manager_credentials()、get_ns_password()
│   │       ├── config.py          # GET /admin/config → 返回当前 ADB 配置
│   │       ├── namespace.py       # 命名空间 CRUD（调 ADB SDK + NamespaceRepository）
│   │       └── collection.py      # 知识库（Collection）CRUD（调 ADB SDK + CollectionConfigRepository）
│   ├── services/
│   │   ├── adb_vector_service.py  # ADB 管理 API 封装（命名空间/Collection/Secret 管理）
│   │   │                          # 含 ADBException、parse_sdk_exception（全局异常解析工具）
│   │   ├── adb_document_service.py# ADB 文档操作（上传/检索/删除/UpsertChunks）
│   │   ├── oss_service.py         # OSS 文件上传/下载/删除
│   │   ├── doc_image_parser.py    # PyMuPDF 解析 PDF，提取文字切片 + 图片，图片上传 OSS
│   │   ├── image_mode_service.py  # 图文模式批量切分流程（OSS下载→解析→写库）
│   │   ├── chunk_cleaner.py       # 切片清洗（正则 + LLM），含 clean_single_chunk_with_llm()
│   │   ├── chat_service.py        # Chat 业务逻辑（Supervisor Agent 调用封装）
│   │   ├── knowledge_service.py   # Knowledge RAG 业务逻辑（Knowledge Agent 调用封装）
│   │   ├── document_service.py    # 文档管理业务逻辑（上传/切分/检索）
│   │   ├── job_service.py         # 上传任务业务逻辑（状态查询/切片下载）
│   │   ├── chunk_service.py       # 切片业务逻辑（编辑/清洗/撤回/向量化/图片管理）
│   │   ├── category_service.py    # 类目业务逻辑（CRUD + 文件管理）
│   │   └── file_service.py        # 文件列表业务逻辑（联动删除）
│   └── db/
│       ├── __init__.py            # 统一导出所有 Repository 及其工厂函数
│       ├── base_repository.py     # BaseRepository：封装 ADB ExecuteStatement SQL 执行
│       ├── job_repository.py      # knowledge_job 表（ADB 上传任务状态）
│       ├── document_job_repository.py # knowledge_document_job 表（文件↔job_id 映射）
│       ├── chunk_repository.py    # knowledge_chunk_store 表（切片内容，支持编辑/撤回）
│       ├── chunk_image_repository.py  # knowledge_chunk_image 表（切片↔图片 OSS key 映射）
│       ├── category_repository.py # knowledge_category 表（类目）
│       ├── category_file_repository.py # knowledge_category_file 表（类目↔OSS文件）
│       ├── collection_config_repository.py # knowledge_collection_config 表（知识库配置）
│       ├── file_repository.py     # knowledge_upload_file 表（文件上传状态，当前较少使用）
│       └── namespace_repository.py # public.namespace_registry 表（命名空间密码加密存储）
└── agents/
    ├── __init__.py                # 导出 get_supervisor_agent、get_knowledge_agent
    ├── knowledge/
    │   ├── __init__.py            # 导出 get_knowledge_agent（工厂函数 + 模块级缓存）
    │   ├── graph.py               # Knowledge Agent 图定义（节点连线、条件路由）
    │   ├── state.py               # KnowledgeAgentState、RAGConfig、RetrievedChunk 等数据类
    │   ├── nodes/
    │   │   ├── __init__.py        # 导出所有节点函数
    │   │   ├── query_rewrite.py   # 节点1：LLM 改写用户问题
    │   │   ├── query_classify.py  # 节点2：分类 single_doc / multi_doc
    │   │   ├── retrieval_strategy.py # 节点3：判断 keyword / hybrid 检索策略
    │   │   ├── single_doc_retrieve.py # 节点4a：单文档检索（top_k=20，ADB rerank）
    │   │   ├── multi_doc_retrieve.py  # 节点4b：多文档检索（top_k=50，广撒网）
    │   │   ├── filter.py          # 节点5（multi_doc）：按 score 阈值过滤
    │   │   ├── rerank.py          # 节点6（multi_doc）：按分数排序取 top-K
    │   │   ├── relevance_filter.py # 节点7：LLM 二次相关性过滤（single/multi 共用）
    │   │   ├── generate.py        # 节点8：LLM 生成答案（支持图文模式）
    │   │   ├── quality_check.py   # 节点9：答案质量检查，低质量触发 fallback
    │   │   └── metrics.py         # 节点10：汇总性能指标（耗时/token/cost）
    │   ├── services/
    │   │   ├── __init__.py        # 导出 RetrievalService
    │   │   └── retrieval.py       # RetrievalService：封装 ADB vector/keyword/hybrid 检索
    │   └── tools/
    │       └── __init__.py        # 空（mcp_tools 已删除）
    ├── supervisor/
    │   ├── __init__.py            # 导出 get_supervisor_agent（工厂函数 + 模块级缓存）
    │   ├── graph.py               # Supervisor Agent 图定义
    │   ├── state.py               # SupervisorState（仅含 messages 字段）
    │   ├── nodes/
    │   │   └── router.py          # should_continue()：判断是否继续调用工具
    │   └── services/
    │       └── coordinator.py     # create_supervisor_tools()、get_supervisor_system_prompt()
    └── specialized/
        ├── email/
        │   ├── __init__.py        # 导出 create_email_agent、EMAIL_AGENT_INFO
        │   ├── graph.py           # Email Agent 图定义
        │   ├── state.py           # EmailAgentState
        │   ├── nodes/
        │   │   └── email_processor.py # call_email_model()、should_continue()
        │   └── services/
        │       └── email_service.py   # send_email/check_inbox/search_emails 工具（mock）
        └── search/
            ├── __init__.py        # 导出 create_search_agent、SEARCH_AGENT_INFO
            ├── graph.py           # Search Agent 图定义
            ├── state.py           # SearchAgentState
            └── services/
                └── search_service.py  # search_web/get_weather/get_news 工具（mock）
```

---

## 分层架构

```
请求
  │
  ▼
API 层（app/api/v1/）
  │  只做参数校验、调用 service/agent、返回响应
  │  异常处理：业务逻辑异常用 HTTPException，ADB SDK 异常由全局 handler 处理
  │
  ├──► Agent 层（agents/）
  │      Knowledge Agent：RAG 问答流水线
  │      Supervisor Agent：多 agent 协调（email/search）
  │      节点只做状态转换，业务逻辑下沉到 services/
  │
  └──► Service 层（app/services/）
         ADBVectorService：ADB 管理 API（命名空间/Collection）
         ADBDocumentService：ADB 文档操作（上传/检索/UpsertChunks）
         OSSService：文件存储
         DocImageParser：PDF 图文解析
         ChunkCleaner：切片清洗
         │
         ▼
       Repository 层（app/db/）
         BaseRepository：统一 SQL 执行（ADB ExecuteStatement API）
         各业务表的 CRUD 封装
```

---

## 核心业务流程

### 1. 文档上传流程（标准模式）

```
POST /documents/upload
  → ADBDocumentService.upload_document_async()  # 调 ADB SDK，dry_run=True
  → DocumentJobRepository.create()              # 写 knowledge_document_job

POST /jobs/{job_id}/fetch-chunks
  → ADBDocumentService.get_chunk_file_url()     # 从 ADB 拿 ChunkFileUrl
  → 下载 JSONL 文件
  → ChunkRepository.bulk_insert()               # 写 knowledge_chunk_store

POST /chunks/job/{job_id}/upsert
  → ChunkRepository.get_by_job()                # 读 current_content
  → ADBDocumentService.upsert_chunks()          # 上传向量库
  → DocumentJobRepository.mark_vectorized()     # 标记已向量化
```

### 2. 文档上传流程（图文模式）

```
POST /documents/upload（image_mode 知识库）或 POST /documents/start-chunking/{category_id}
  → 判断 collection_config.image_mode = true
  → OSSService.get_object_bytes()               # 从 OSS 下载文件（类目模式）
    或直接使用 file_content 字节（单文件模式）
  → DocImageParser.parse_pdf() / parse_word()   # PyMuPDF/python-docx 解析
      - 文字块按 (page, y_center) 排序与图片交织
      - 图片在切分阶段确定 chunk_id 后再上传 OSS（修复：收集阶段不上传）
      - OSS 路径：rag_image/{collection}/{file_name}/{chunk_id}/{uuid}.{ext}
      - should_merge 后处理：检测冒号结尾/列表项开头/转折词，合并语义断裂的相邻 chunk
      - 合并时同步更新 image_records 里的 chunk_id
      - 智能 overlap：从句子边界开始，不在词中间截断
  → ChunkRepository.bulk_insert_with_ids()      # 写切片，直接用 parse 返回的 chunk_id
      - chunk_index 从 chunk_id 末尾 _N 取，保证与 image_records 对应
      - 不重新 enumerate 编号（避免 should_merge 后序号偏移）
  → ChunkImageRepository.bulk_insert()          # 写图片记录（只存 oss_key）
  → DocumentJobRepository.upsert()              # 写 job 记录
```

**chunk_id 设计说明：**
- 图文模式 chunk_id 格式：`{job_id}_{chunk_idx}`（parse 阶段生成）
- 存入 `knowledge_chunk_store.chunk_id` 和 `knowledge_chunk_image.chunk_id`
- upsert 向量库时在 metadata 中额外写入 `chunk_id` 字段，供检索后查图片使用
- 前端查看切片图片时，通过 `chunk_store` 的 `chunk_index` 字段查出真实 `chunk_id`，再查图片表（不直接拼 `{job_id}_{chunk_index}`，因为 should_merge 后序号可能有空洞）

**OSS 路径规范：**
- 类目文件：`category/{category_name}/{file_name}`
- 图文模式图片：`rag_image/{collection}/{file_name}/{chunk_id}/{uuid}.{ext}`

### 3. RAG 问答流程

```
POST /knowledge
  → knowledge_agent.invoke(initial_state)
      query_rewrite → query_classify → determine_retrieval_strategy
        → [single_doc_retrieve 或 multi_doc_retrieve]
          → [filter_chunks → rerank_chunks]（multi_doc 路径）
            → relevance_filter（LLM 二次过滤）
              → generate_answer（图文模式时查 chunk_image_repository）
                → check_quality → finalize_metrics
```

### 4. 对话流程

```
POST /chat
  → supervisor_agent.invoke({messages: [HumanMessage]})
      supervisor（LLM）→ should_continue
        → tools（email_agent 或 search_agent）→ supervisor
        → END
```

---

## 数据库表结构（ADB PostgreSQL，schema = adb_namespace）

| 表名 | 用途 |
|------|------|
| `knowledge_job` | ADB 上传任务状态（stage/status/comment）（ADB创建后自带的表，不需要手动创建，调用sdk方法自动更新这个表） |
| `knowledge_base` | 创建的知识库信息（ADB创建后自带的表，不需要手动维护，调用sdk方法自动更新这个表） |
| `knowledge_document_job` | 文件↔job_id 映射，含 vectorized 标记 |
| `knowledge_chunk_store` | 切片内容（original_content + current_content，支持编辑/撤回） |
| `knowledge_chunk_image` | 切片↔图片 oss_key 一对多关联（图文模式） |
| `knowledge_category` | 类目（文件夹） |
| `knowledge_category_file` | 类目↔OSS文件关联 |
| `knowledge_collection_config` | 知识库配置（metadata字段/向量参数/image_mode） |
| `knowledge_upload_file` | 文件上传状态（较少使用） |
| `public.namespace_registry` | 命名空间注册表，密码 AES-256-GCM 加密存储 |
| `自定义名称表` | 此表在每次调用CreateCollection方法时新建在当前namespace下 |

---

## 异常处理机制

```
ADB SDK 抛出异常
  → parse_sdk_exception(e, prefix)   # 解析原始 HTTP 状态码，包装为 ADBException
  → ADBException(message, status_code)
  → FastAPI exception_handler         # app/main.py 全局注册
  → 返回对应状态码给前端（400/403/404/500 等）
```

---

## 配置管理

- 所有配置通过 `app/core/config.py` 的 `Settings` 类读取环境变量
- 所有 LLM prompt 集中在 `app/core/prompts.py`
- 模型列表及定价在 `SUPPORTED_MODELS` 字典（含 `cost_per_1k_tokens`）
- 密码类配置无硬编码默认值，必须通过 `.env` 配置

---

## 单例模式

所有 Service 和 Repository 均使用模块级全局变量实现单例：

```python
_instance = None
def get_xxx_repository():
    global _instance
    if _instance is None:
        _instance = XxxRepository()
    return _instance
```

Agent 使用 `_AgentProxy` 实现延迟初始化（首次调用时才创建 LangGraph）。

---

## 已完成优化项

### 代码结构重构（2024）
- **API / Service 分层**：`app/api/v1/` 下每个文件只做参数校验和路由，业务逻辑全部下沉到 `app/services/` 对应文件，两层文件名一一对应
- **去除 `_AgentProxy`**：Knowledge Agent 和 Supervisor Agent 均改为工厂函数 + 模块级缓存单例（`get_knowledge_agent()` / `get_supervisor_agent()`），与 Repository 层风格统一
- **删除 `agents/preload.py`**：预加载功能由 agent 工厂函数的延迟初始化缓存替代，不再需要独立预加载模块

### 统一异常体系
- 新增 `app/core/exceptions.py`，定义 `AppError` 基类及子类：`NotFoundError(404)`、`ValidationError(400)`、`ForbiddenError(403)`、`ConflictError(409)`、`ExternalServiceError(502)`
- `app/main.py` 全局注册 `AppError` / `ADBException` / `Exception` 三级 handler，API 层不再需要 try/except
- Service 层统一抛出语义明确的业务异常，不再使用 Python 内置 `LookupError` / `PermissionError`

### 结构化日志
- 新增 `app/core/logging.py`，`JsonFormatter` 输出单行 JSON，字段包含 `time`、`level`、`logger`、`message`、`request_id`、`session_id` 等
- 应用启动时调用 `setup_logging()`，统一初始化，降低第三方库日志噪音
- 所有 `print()` 替换为 `logger.info/warning/error`，支持 `extra={}` 传递上下文字段

### 异步化
- `job_service.fetch_and_store_chunks`：ADB 获取 URL、bulk_insert 均用 `asyncio.to_thread()` 包裹，不阻塞事件循环
- `chunk_service.clean_job_chunks` / `clean_all_chunks`：LLM 清洗改为 `asyncio.gather()` 并发执行，批量清洗性能大幅提升
- `document_service.start_chunking`：ADB 状态查询、OSS presigned URL、upload_document_from_url 均异步化

### 配置启动校验
- `app/core/config.py` 新增 `_validate_env()`，`Settings.__init__` 触发校验
- 缺少 `DASHSCOPE_API_KEY`、`ADBPG_INSTANCE_ID`、`BAILIAN_ADB_USER/PASSWORD`、`OSS_*` 等必填项时，应用启动即报错，不等到运行时

### 修复 thread_id 硬编码
- `chat_service.py` 中 `thread_id` 由硬编码 `"default_conversation_thread"` 改为 `f"chat_{session_id}"`，每个会话独立对话记忆，不再共享

### Repository 私有方法封装
- `ChunkRepository` 新增公开方法 `list_all_job_ids()`
- `chunk_service.list_all_job_ids()` 不再直接调用 `chunk_repo._execute_select()`，遵守封装原则

### 图文模式切分重构（2026）
- **OSS 路径规范化**：图片路径改为 `rag_image/{collection}/{file_name}/{chunk_id}/{uuid}.{ext}`，与类目文件路径 `category/{category_name}/{file_name}` 并列隔离
- **修复图片上传时序 bug**：PDF 解析阶段只暂存图片字节，切分遍历确定 `chunk_id` 后再上传 OSS，避免所有图片都传到 `_0` 路径
- **should_merge 语义合并**：切分后检测冒号结尾、列表项开头、转折词开头，自动合并语义断裂的相邻 chunk，合并时同步更新 `image_records` 里的 `chunk_id`
- **智能 overlap**：从句子边界（`。？！.?!`）之后开始，不在词中间截断
- **bulk_insert_with_ids**：图文模式写库时直接使用 `parse_pdf` 返回的 `chunk_id`，`chunk_index` 从 `chunk_id` 末尾取，不重新 enumerate，避免 should_merge 后序号偏移导致图片查询失败
- **chunk_id 写入 upsert metadata**：向量库 upsert 时在 metadata 中额外写入 `chunk_id`，检索回来后可直接查 `knowledge_chunk_image` 表
- **图片查询解耦**：`get_chunk_images` / `add_chunk_image` 先从 `chunk_store` 查出真实 `chunk_id`，再操作图片表，不直接拼 `{job_id}_{chunk_index}`
- **oss_url 编码修复**：`_normalize` 中用 `quote(oss_key, safe='/')` 编码，只编码空格和中文，不编码路径分隔符
- **知识库/文件名格式校验**：collection 名只允许字母、数字、下划线、连字符、中文；文件名禁止 `/\?#*` 等 OSS 路径敏感字符
- **RAG context 格式优化**：传给 LLM 的 context 改为 XML 标签格式，`<source>` 包裹 `<chunk>`，含 `prev_chunk_index` / `next_chunk_index`，从 chunk_id 末尾自动计算，不依赖数据库

---

1. `agents/specialized/email/services/email_service.py` — send_email/check_inbox/search_emails 均为 mock，未接入真实 SMTP
2. `agents/specialized/search/services/search_service.py` — search_web/get_weather/get_news 均为 mock，未接入真实搜索 API
3. `app/db/base_repository.py` — SQL 拼接为字符串（已有 `_sql_escape` 防注入），待迁移到 ADB ExecuteStatement `Parameters` 字段参数化查询，彻底消除注入风险
4. **API 版本化迁移策略**：当前 `/api/v1/` 下无版本迁移机制，如需上线 v2，建议在 `app/api/v1/__init__.py` 预留 v2 挂载位置，并在响应头加 `Deprecation` 标记
