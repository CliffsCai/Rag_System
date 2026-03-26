# 设计文档：Knowledge Agent System

> 文档状态（规格目标态）：本文是设计规格文档，包含目标架构与验收属性；当前实现可能已演进。实施与联调请优先参考 `PROJECT_STRUCTURE_MASTER.md` 与 `backend/agents/knowledge/graph.py`。

## 概述

Knowledge Agent System 是一个基于 LangGraph 的企业级知识库智能问答系统。系统采用完整的 7 节点 RAG（检索增强生成）工作流，通过状态机模式管理复杂的查询处理流程，集成 MCP 工具扩展功能，支持高质量的知识库问答服务。

### 核心特性

- **完整的 RAG 流水线**：7 个专门化节点，每个节点负责特定任务
- **状态驱动架构**：使用 TypedDict 定义的 State 在节点间传递数据
- **MCP 工具集成**：支持邮件发送、网络搜索、数据库查询等扩展功能
- **质量保证机制**：内置质量检查和回退策略
- **性能监控**：完整的性能指标统计和成本估算
- **可扩展设计**：易于添加新节点和新工具

### 技术栈

- **后端框架**：Python 3.8+, LangGraph, FastAPI
- **LLM 服务**：阿里云百炼（DashScope）
- **前端框架**：Vue 3, Axios
- **数据库**：阿里云百炼 ADB（向量数据库，待集成）

## 架构设计

### 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                        用户请求                              │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Server                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  GET /api/v1/│  │POST /api/v1/chat/││POST /api/v1/knowledge/│
│  │  健康检查     │  │  对话接口     │  │  知识库问答    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  Knowledge Agent (LangGraph)                 │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Node 1: Query Analysis                              │  │
│  │  - 分析查询意图（factual/procedural/comparative）     │  │
│  │  - 判断查询复杂度（simple/medium/complex）            │  │
│  │  - 提取关键词和实体                                   │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                         │                                    │
│  ┌──────────────────────▼───────────────────────────────┐  │
│  │  Node 2: Retrieve (当前 MOCK)                        │  │
│  │  - 向量搜索（待集成 Bailian ADB）                     │  │
│  │  - 关键词搜索                                         │  │
│  │  - 混合搜索策略                                       │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                         │                                    │
│  ┌──────────────────────▼───────────────────────────────┐  │
│  │  Node 3: Filter                                      │  │
│  │  - 按相关性分数过滤                                   │  │
│  │  - 移除低质量文档片段                                 │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                         │                                    │
│  ┌──────────────────────▼───────────────────────────────┐  │
│  │  Node 4: Rerank                                      │  │
│  │  - 重新排序文档片段                                   │  │
│  │  - 选择 top-K 最相关文档                              │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                         │                                    │
│  ┌──────────────────────▼───────────────────────────────┐  │
│  │  Node 5: Generate                                    │  │
│  │  - 基于上下文生成答案                                 │  │
│  │  - 调用 MCP 工具（如需要）                            │  │
│  │  - 提取来源和引用                                     │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                         │                                    │
│  ┌──────────────────────▼───────────────────────────────┐  │
│  │  Node 6: Quality Check                               │  │
│  │  - 检查答案质量                                       │  │
│  │  - 应用回退策略（如需要）                             │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                         │                                    │
│  ┌──────────────────────▼───────────────────────────────┐  │
│  │  Node 7: Metrics Finalization                        │  │
│  │  - 统计性能指标                                       │  │
│  │  - 估算成本                                           │  │
│  └──────────────────────┬───────────────────────────────┘  │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                      返回结果给用户                           │
│  - 答案文本                                                  │
│  - 置信度分数                                                │
│  - 来源引用                                                  │
│  - 性能指标                                                  │
└─────────────────────────────────────────────────────────────┘
```


### State 流转机制

系统使用 `KnowledgeAgentState` TypedDict 在节点间传递数据。State 包含 40+ 字段，涵盖查询信息、检索结果、生成答案、性能指标等所有数据。

**State 流转规则**：

1. **不可变性**：每个节点返回 State 的部分更新，LangGraph 自动合并
2. **Reducer 字段**：`all_errors`、`all_warnings`、`processing_log` 使用 `operator.add` 累加
3. **阶段性数据**：每个节点只更新自己负责的字段
4. **完整历史**：`processing_log` 记录每个节点的执行信息

**State 生命周期**：

```
初始化 (create_initial_state)
  ↓
Query Analysis (更新 query_intent, query_complexity, query_keywords)
  ↓
Retrieve (更新 retrieved_chunks, merged_chunks, metrics.total_chunks_retrieved)
  ↓
Filter (更新 filtered_chunks, metrics.chunks_after_filter)
  ↓
Rerank (更新 reranked_chunks, metrics.chunks_after_rerank)
  ↓
Generate (更新 answer, confidence, sources, tools_used)
  ↓
Quality Check (更新 answer_quality, quality_passed, used_fallback)
  ↓
Metrics (更新 metrics.total_duration_ms, metrics.estimated_cost)
  ↓
返回最终 State
```

### MCP 工具集成方式

MCP 工具在 Generate 节点中绑定到 LLM。LLM 根据用户查询和上下文自主决定是否调用工具。

**工具注册流程**：

1. 使用 `@tool` 装饰器定义工具函数
2. 在 `create_mcp_tools()` 中收集所有工具
3. 在 Generate 节点中使用 `llm.bind_tools(mcp_tools)` 绑定
4. LLM 返回 `tool_calls` 时，执行工具并将结果返回给 LLM
5. LLM 基于工具结果生成最终答案

**当前支持的工具**：

- `send_email(to, subject, body)`: 发送邮件
- `web_search(query, num_results)`: 搜索网络
- `query_database(sql)`: 查询数据库

## 核心组件

### 1. Knowledge Agent

**职责**：协调整个 RAG 流水线的执行

**实现**：
```python
def create_knowledge_agent():
    builder = StateGraph(KnowledgeAgentState)
    
    # 添加节点
    builder.add_node("query_analysis", query_analysis_node)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("filter", filter_node)
    builder.add_node("rerank", rerank_node)
    builder.add_node("generate", generate_node)
    builder.add_node("quality_check", quality_check_node)
    builder.add_node("metrics", metrics_finalization_node)
    
    # 添加边（线性工作流）
    builder.add_edge(START, "query_analysis")
    builder.add_edge("query_analysis", "retrieve")
    builder.add_edge("retrieve", "filter")
    builder.add_edge("filter", "rerank")
    builder.add_edge("rerank", "generate")
    
    # 条件边：是否需要质量检查
    builder.add_conditional_edges(
        "generate",
        should_use_fallback,
        {
            "quality_check": "quality_check",
            "metrics": "metrics"
        }
    )
    builder.add_edge("quality_check", "metrics")
    builder.add_edge("metrics", END)
    
    return builder.compile()
```

**配置参数**：
- `model`: LLM 模型名称（如 "qwen-plus"）
- `session_id`: 会话标识符

### 2. Query Analysis Node

**职责**：分析用户查询，提取意图、复杂度和关键词

**输入**：
- `state["query"]`: 用户查询字符串

**处理逻辑**：
1. 检测查询中的关键词，判断意图类型
   - 包含"如何/怎么/怎样" → procedural
   - 包含"是什么/什么是" → factual
   - 包含"比较/区别/差异" → comparative
   - 其他 → general
2. 根据查询长度判断复杂度
   - < 20 字符 → simple
   - 20-50 字符 → medium
   - > 50 字符 → complex
3. 简单分词提取关键词（长度 > 2 的词）

**输出**：
- `query_intent`: 查询意图
- `query_complexity`: 查询复杂度
- `query_keywords`: 关键词列表
- `processing_log`: 处理日志

**错误处理**：
- 捕获所有异常，返回错误信息到 `all_errors`

### 3. Retrieve Node

**职责**：从知识库检索相关文档片段

**当前实现**：Mock 数据（返回 3 个固定的文档片段）

**未来实现**：
1. 调用 Bailian ADB 向量搜索 API
2. 根据 `config.retrieval_strategy` 选择搜索方式
   - `vector_only`: 仅向量搜索
   - `keyword_only`: 仅关键词搜索
   - `hybrid`: 混合搜索（向量 + 关键词）
3. 合并和去重检索结果

**输入**：
- `state["query"]`: 用户查询
- `state["config"]`: RAG 配置

**输出**：
- `retrieved_chunks`: 检索到的文档片段列表
- `merged_chunks`: 合并后的文档片段
- `metrics.total_chunks_retrieved`: 检索数量

**数据结构**：
```python
{
    "id": "doc_1",
    "content": "文档内容...",
    "title": "文档标题",
    "score": 0.95,
    "metadata": {
        "source": "knowledge_base",
        "doc_type": "documentation",
        "created_at": "2024-01-01"
    }
}
```

### 4. Filter Node

**职责**：过滤低相关性的文档片段

**输入**：
- `state["merged_chunks"]`: 检索到的文档片段
- `state["config"].vector_score_threshold`: 分数阈值

**处理逻辑**：
1. 遍历所有文档片段
2. 保留 `score >= threshold` 的片段
3. 更新统计信息

**输出**：
- `filtered_chunks`: 过滤后的文档片段
- `metrics.chunks_after_filter`: 过滤后数量

### 5. Rerank Node

**职责**：重新排序文档片段，选择最相关的 top-K

**输入**：
- `state["filtered_chunks"]`: 过滤后的文档片段
- `state["config"].rerank_top_k`: 选择数量

**处理逻辑**：
1. 按 `score` 降序排序
2. 选择前 K 个片段

**输出**：
- `reranked_chunks`: 重排序后的 top-K 片段
- `metrics.chunks_after_rerank`: 重排序后数量

### 6. Generate Node

**职责**：基于检索的上下文生成答案，支持 MCP 工具调用

**输入**：
- `state["query"]`: 用户查询
- `state["reranked_chunks"]`: 重排序后的文档片段
- `state["config"]`: RAG 配置
- `config["configurable"]["model"]`: LLM 模型名称

**处理逻辑**：
1. 创建 LLM 实例（ChatOpenAI）
2. 创建并绑定 MCP 工具
3. 构建上下文（从 reranked_chunks）
4. 构建系统提示词和用户提示词
5. 调用 LLM
6. 如果 LLM 返回 tool_calls：
   - 执行工具
   - 将工具结果返回给 LLM
   - LLM 生成最终答案
7. 提取来源信息
8. 计算置信度（基于文档分数）

**输出**：
- `answer`: 生成的答案
- `confidence`: 置信度分数（0-1）
- `sources`: 来源信息列表
- `context`: 使用的上下文文本
- `tools_used`: 使用的工具列表
- `metrics.llm_calls`: LLM 调用次数

**系统提示词模板**：
```
你是企业知识库智能助手（方案 3 架构）。

你的能力：
1. 基于知识库上下文回答问题
2. 使用 MCP 工具扩展功能：
   - send_email: 发送邮件
   - web_search: 搜索网络信息
   - query_database: 查询业务数据库

知识库上下文：
{context}

回答指南：
- 优先使用知识库上下文回答
- 如果上下文不足，可以使用 MCP 工具
- 引用来源时使用 [文档 X] 格式
- 保持回答准确、简洁
```

### 7. Quality Check Node

**职责**：检查答案质量，应用回退策略

**输入**：
- `state["answer"]`: 生成的答案
- `state["confidence"]`: 置信度
- `state["config"]`: RAG 配置

**处理逻辑**：
1. 检查答案长度（< 10 字符为问题）
2. 检查置信度（< 阈值为问题）
3. 根据问题数量判断质量等级：
   - 0 个问题 → HIGH
   - 1 个问题 → MEDIUM
   - 2+ 个问题 → LOW
4. 如果质量为 LOW 且启用回退，使用回退消息

**输出**：
- `answer`: 可能被回退消息替换的答案
- `answer_quality`: 质量等级（HIGH/MEDIUM/LOW）
- `quality_passed`: 是否通过质量检查
- `quality_issues`: 质量问题列表
- `used_fallback`: 是否使用回退
- `fallback_reason`: 回退原因

### 8. Metrics Finalization Node

**职责**：统计性能指标，估算成本

**输入**：
- `state["metrics"]`: 性能指标对象
- `state["config"].model`: 使用的模型

**处理逻辑**：
1. 计算总耗时（end_time - start_time）
2. 根据模型估算成本：
   - qwen-plus: $0.002 / 1K tokens
   - qwen-turbo: $0.001 / 1K tokens
3. 更新指标对象

**输出**：
- `metrics.end_time`: 结束时间
- `metrics.total_duration_ms`: 总耗时（毫秒）
- `metrics.estimated_cost`: 估算成本（美元）


## State 字段说明

### 输入字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `query` | str | 用户查询 |
| `original_query` | str | 原始查询（保留） |
| `user_context` | UserContext | 用户上下文（user_id, session_id 等） |
| `config` | RAGConfig | RAG 配置参数 |

### 查询分析字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `query_intent` | Optional[str] | 查询意图（factual/procedural/comparative/general） |
| `query_complexity` | Optional[str] | 查询复杂度（simple/medium/complex） |
| `query_keywords` | List[str] | 提取的关键词 |
| `query_entities` | List[Dict] | 提取的实体 |

### 检索字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `vector_chunks` | List[RetrievedChunk] | 向量搜索结果 |
| `keyword_chunks` | List[RetrievedChunk] | 关键词搜索结果 |
| `merged_chunks` | List[RetrievedChunk] | 合并后的结果 |
| `retrieval_strategy_used` | Optional[RetrievalStrategy] | 使用的检索策略 |
| `total_candidates` | int | 候选文档总数 |

### 过滤字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `filtered_chunks` | List[RetrievedChunk] | 过滤后的文档片段 |
| `filter_decisions` | List[Dict] | 过滤决策记录 |
| `filter_strategy_used` | Optional[FilterStrategy] | 使用的过滤策略 |
| `chunks_removed` | int | 移除的片段数量 |

### 重排序字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `reranked_chunks` | List[RetrievedChunk] | 重排序后的片段 |
| `rerank_scores` | List[float] | 重排序分数 |

### 上下文字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `context` | str | 传递给 LLM 的上下文文本 |
| `context_length` | int | 上下文长度 |
| `sources` | List[Dict] | 来源信息 |
| `images` | List[Dict] | 图片信息 |
| `tables` | List[Dict] | 表格信息 |

### 生成字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `answer` | str | 生成的答案 |
| `confidence` | float | 置信度分数（0-1） |
| `answer_quality` | Optional[AnswerQuality] | 答案质量等级 |
| `citations` | List[Dict] | 引用信息 |
| `follow_up_questions` | List[str] | 后续问题建议 |
| `tools_used` | List[str] | 使用的工具列表 |

### 质量控制字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `quality_passed` | bool | 是否通过质量检查 |
| `quality_issues` | List[str] | 质量问题列表 |
| `used_fallback` | bool | 是否使用回退 |
| `fallback_reason` | Optional[str] | 回退原因 |

### 性能指标字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `metrics` | PerformanceMetrics | 性能指标对象 |

### 错误处理字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `error` | Optional[str] | 错误信息 |
| `error_stage` | Optional[str] | 出错阶段 |
| `error_details` | Optional[Dict] | 错误详情 |
| `all_errors` | List[str] | 所有错误（累加） |
| `all_warnings` | List[str] | 所有警告（累加） |
| `processing_log` | List[Dict] | 处理日志（累加） |

## 工具注册机制

### 工具定义

使用 LangChain 的 `@tool` 装饰器定义工具：

```python
from langchain_core.tools import tool

@tool("send_email")
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email to a recipient"""
    # 实现邮件发送逻辑
    return f"✅ Email sent successfully to {to}"
```

### 工具注册

在 `create_mcp_tools()` 函数中收集所有工具：

```python
def create_mcp_tools() -> List:
    tools = []
    
    @tool("send_email")
    def send_email(to: str, subject: str, body: str) -> str:
        """Send an email to a recipient"""
        return f"✅ Email sent successfully to {to}"
    
    tools.append(send_email)
    
    # 添加更多工具...
    
    return tools
```

### 工具绑定

在 Generate 节点中绑定工具到 LLM：

```python
mcp_tools = create_mcp_tools()
llm_with_tools = llm.bind_tools(mcp_tools)
```

### 工具调用流程

```
1. LLM 接收用户查询和上下文
   ↓
2. LLM 决定是否需要调用工具
   ↓
3. 如果需要，LLM 返回 tool_calls
   ↓
4. Generate 节点执行工具
   ↓
5. 将工具结果作为 ToolMessage 返回给 LLM
   ↓
6. LLM 基于工具结果生成最终答案
```

### 添加新工具

1. 在 `create_mcp_tools()` 中定义新工具函数
2. 使用 `@tool` 装饰器并提供描述
3. 将工具添加到 tools 列表
4. 无需修改其他代码，LLM 会自动识别新工具

## API 设计

### 端点列表

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 健康检查，返回系统信息 |
| `/models` | GET | 获取支持的模型列表 |
| `/api/v1/chat/` | POST | 对话接口 |
| `/api/v1/knowledge/` | POST | 知识库问答接口 |
| `/health` | GET | 健康检查（详细） |

### GET / - 健康检查

**响应示例**：
```json
{
  "status": "ok",
  "message": "Agent API is running",
  "version": "1.0.0",
  "architecture": "Solution 3: Complete Knowledge Agent with Full Workflow",
  "workflow": "query_analysis → retrieve → filter → rerank → generate → quality_check → metrics",
  "models": ["qwen-turbo", "qwen-plus", "qwen-max"],
  "default_model": "qwen-turbo",
  "mcp_tools": ["send_email", "web_search", "query_database"],
  "note": "Using MOCK retrieval - ready for real KB integration"
}
```

### POST /api/v1/chat/ - 对话接口

**请求格式**：
```json
{
  "messages": [
    {"role": "user", "content": "你好！"}
  ],
  "model": "qwen-plus",
  "temperature": 0.0
}
```

**响应格式**：
```json
{
  "messages": [
    {"role": "user", "content": "你好！"},
    {"role": "assistant", "content": "你好！我是企业知识库助手..."}
  ],
  "model": "qwen-plus",
  "usage": {
    "tools_used": []
  }
}
```

### POST /api/v1/knowledge/ - 知识库问答接口

**请求格式**：
```json
{
  "query": "什么是 LangGraph？",
  "session_id": "user_123",
  "model": "qwen-plus"
}
```

**响应格式**：
```json
{
  "answer": "LangGraph 是一个用于构建有状态的多 Agent 应用的框架...",
  "confidence": 0.95,
  "sources": [
    {
      "id": "doc_1",
      "title": "LangGraph 介绍文档",
      "content": "这是关于...",
      "score": 0.95,
      "metadata": {...}
    }
  ],
  "model": "qwen-plus",
  "error": null
}
```

## 数据流

### 完整请求处理流程

```
1. 用户发送请求
   ↓
2. FastAPI 接收请求（/api/v1/chat/ 或 /api/v1/knowledge/）
   ↓
3. 验证请求参数（model, messages/query）
   ↓
4. 创建初始 State
   - query: 用户查询
   - user_context: 用户信息
   - config: RAG 配置
   - metrics: 初始化性能指标
   ↓
5. 调用 knowledge_agent.invoke(initial_state, config)
   ↓
6. Node 1: Query Analysis
   - 分析查询意图和复杂度
   - 提取关键词
   - 更新 State
   ↓
7. Node 2: Retrieve
   - 检索相关文档（当前 MOCK）
   - 更新 retrieved_chunks
   ↓
8. Node 3: Filter
   - 过滤低相关性文档
   - 更新 filtered_chunks
   ↓
9. Node 4: Rerank
   - 重排序文档
   - 选择 top-K
   - 更新 reranked_chunks
   ↓
10. Node 5: Generate
    - 构建上下文
    - 调用 LLM（绑定 MCP 工具）
    - 如果 LLM 调用工具：
      * 执行工具
      * 将结果返回给 LLM
      * LLM 生成最终答案
    - 提取来源和置信度
    - 更新 answer, confidence, sources, tools_used
    ↓
11. Node 6: Quality Check（条件执行）
    - 检查答案质量
    - 如果质量低且启用回退，使用回退消息
    - 更新 answer_quality, used_fallback
    ↓
12. Node 7: Metrics
    - 计算总耗时
    - 估算成本
    - 更新 metrics
    ↓
13. 返回最终 State
    ↓
14. FastAPI 提取结果字段
    - answer
    - confidence
    - sources
    - tools_used
    ↓
15. 构建响应 JSON
    ↓
16. 返回给用户
```

### State 更新示例

**初始 State**：
```python
{
  "query": "什么是 LangGraph？",
  "user_context": UserContext(user_id="api_user", session_id="api_session"),
  "config": RAGConfig(model="qwen-plus", ...),
  "metrics": PerformanceMetrics(start_time=datetime.now()),
  "all_errors": [],
  "processing_log": []
}
```

**Query Analysis 后**：
```python
{
  ...  # 保留之前的字段
  "query_intent": "factual",
  "query_complexity": "simple",
  "query_keywords": ["LangGraph"],
  "processing_log": [
    {
      "stage": "query_analysis",
      "timestamp": "2024-01-01T10:00:00",
      "intent": "factual",
      "complexity": "simple"
    }
  ]
}
```

**Retrieve 后**：
```python
{
  ...  # 保留之前的字段
  "retrieved_chunks": [
    {"id": "doc_1", "content": "...", "score": 0.95, ...},
    {"id": "doc_2", "content": "...", "score": 0.88, ...},
    {"id": "doc_3", "content": "...", "score": 0.82, ...}
  ],
  "merged_chunks": [...],  # 同上
  "metrics": PerformanceMetrics(
    start_time=...,
    total_chunks_retrieved=3
  ),
  "processing_log": [
    ...,  # 之前的日志
    {
      "stage": "retrieve",
      "timestamp": "2024-01-01T10:00:01",
      "chunks_retrieved": 3,
      "note": "MOCK DATA"
    }
  ]
}
```

**最终 State**：
```python
{
  "query": "什么是 LangGraph？",
  "query_intent": "factual",
  "query_complexity": "simple",
  "query_keywords": ["LangGraph"],
  "retrieved_chunks": [...],
  "filtered_chunks": [...],
  "reranked_chunks": [...],
  "answer": "LangGraph 是一个用于构建有状态的多 Agent 应用的框架...",
  "confidence": 0.95,
  "sources": [...],
  "tools_used": [],
  "answer_quality": "HIGH",
  "quality_passed": True,
  "metrics": PerformanceMetrics(
    start_time=...,
    end_time=...,
    total_duration_ms=1234.56,
    total_chunks_retrieved=3,
    chunks_after_filter=3,
    chunks_after_rerank=3,
    llm_calls=1,
    estimated_cost=0.0024
  ),
  "processing_log": [...]  # 所有节点的日志
}
```

## 扩展点

### 1. 添加新节点

在现有工作流中添加新节点：

```python
# 1. 定义新节点函数
def new_node(state: KnowledgeAgentState) -> Dict[str, Any]:
    # 处理逻辑
    return {
        "new_field": "value",
        "processing_log": [{
            "stage": "new_node",
            "timestamp": datetime.now().isoformat()
        }]
    }

# 2. 在 create_knowledge_agent 中注册
builder.add_node("new_node", new_node)

# 3. 添加边
builder.add_edge("existing_node", "new_node")
builder.add_edge("new_node", "next_node")
```

### 2. 添加新工具

在 `create_mcp_tools()` 中添加新工具：

```python
@tool("new_tool")
def new_tool(param1: str, param2: int) -> str:
    """Tool description for LLM"""
    # 实现工具逻辑
    return "Tool result"

tools.append(new_tool)
```

### 3. 添加新功能

**添加新的检索策略**：
1. 在 `RetrievalStrategy` 枚举中添加新策略
2. 在 Retrieve 节点中实现新策略逻辑
3. 在配置中启用新策略

**添加新的过滤策略**：
1. 在 `FilterStrategy` 枚举中添加新策略
2. 在 Filter 节点中实现新策略逻辑
3. 在配置中启用新策略

**添加新的质量检查规则**：
1. 在 Quality Check 节点中添加新的检查逻辑
2. 更新 `quality_issues` 列表

### 4. 集成真实知识库

替换 Retrieve 节点的实现：

```python
def retrieve_node(state: KnowledgeAgentState) -> Dict[str, Any]:
    query = state["query"]
    config = state["config"]
    
    # 调用 Bailian ADB API
    from bailian_sdk import VectorSearch
    
    vector_search = VectorSearch(
        api_key=settings.bailian_api_key,
        index_name=settings.bailian_index_name
    )
    
    results = vector_search.search(
        query=query,
        top_k=config.vector_top_k,
        score_threshold=config.vector_score_threshold
    )
    
    # 转换为 RetrievedChunk 格式
    chunks = [
        {
            "id": r["id"],
            "content": r["content"],
            "title": r["metadata"]["title"],
            "score": r["score"],
            "metadata": r["metadata"]
        }
        for r in results
    ]
    
    return {
        "retrieved_chunks": chunks,
        "merged_chunks": chunks,
        "metrics": state["metrics"]._replace(
            total_chunks_retrieved=len(chunks)
        )
    }
```


## 正确性属性

*属性（Property）是系统在所有有效执行中应该保持的特征或行为。属性是需求和实现之间的桥梁，提供了可机器验证的正确性保证。*

### 属性 1：工作流节点顺序执行

*对于任意*用户查询，Knowledge Agent 执行后，processing_log 中的节点执行顺序应该严格为：query_analysis → retrieve → filter → rerank → generate → quality_check（可选）→ metrics

**验证需求**：需求 1.1

### 属性 2：State 字段传递完整性

*对于任意*节点和任意查询，当节点执行完成后，State 应该包含该节点负责更新的所有字段，且之前节点设置的字段值应该被保留

**验证需求**：需求 1.2, 10.2

### 属性 3：最终结果完整性

*对于任意*查询，工作流执行完成后，最终 State 应该包含 answer（非空字符串）、confidence（0-1 之间的浮点数）、sources（列表）、metrics（包含 total_duration_ms 和 estimated_cost）

**验证需求**：需求 1.3

### 属性 4：错误记录累加

*对于任意*模拟的节点错误，all_errors 字段应该包含该错误信息，且不覆盖之前的错误

**验证需求**：需求 1.4, 13.2

### 属性 5：处理日志完整性

*对于任意*查询，processing_log 应该包含所有执行节点的日志条目，每个条目包含 stage、timestamp 字段

**验证需求**：需求 1.5

### 属性 6：查询意图识别正确性

*对于任意*包含特定关键词的查询：
- 包含"如何/怎么/怎样" → query_intent 应为 "procedural"
- 包含"是什么/什么是" → query_intent 应为 "factual"
- 包含"比较/区别/差异" → query_intent 应为 "comparative"

**验证需求**：需求 2.1, 2.2, 2.3

### 属性 7：查询复杂度判断正确性

*对于任意*查询：
- 长度 < 20 字符 → query_complexity 应为 "simple"
- 长度 20-50 字符 → query_complexity 应为 "medium"
- 长度 > 50 字符 → query_complexity 应为 "complex"

**验证需求**：需求 2.4, 2.5, 2.6

### 属性 8：关键词提取非空性

*对于任意*非空查询，query_keywords 应该是一个列表（可以为空列表，但必须是列表类型）

**验证需求**：需求 2.7

### 属性 9：检索结果非空性

*对于任意*查询，retrieved_chunks 应该至少包含 1 个文档片段

**验证需求**：需求 3.2

### 属性 10：检索结果数据结构完整性

*对于任意*检索结果中的任意文档片段，应该包含 id、content、title、score、metadata 字段

**验证需求**：需求 3.3

### 属性 11：检索 State 更新正确性

*对于任意*查询，Retrieve 节点执行后，State 应该包含 retrieved_chunks（列表）和 metrics.total_chunks_retrieved（整数，等于 retrieved_chunks 的长度）

**验证需求**：需求 3.4

### 属性 12：Mock 数据标注

*对于任意*查询，processing_log 中应该包含至少一个条目的 note 字段包含 "MOCK DATA" 字符串

**验证需求**：需求 3.5

### 属性 13：过滤阈值正确性

*对于任意*阈值和任意文档集合，过滤后的 filtered_chunks 中所有片段的 score 应该 >= 配置的阈值

**验证需求**：需求 4.1

### 属性 14：过滤 State 更新正确性

*对于任意*查询，Filter 节点执行后，metrics.chunks_after_filter 应该等于 filtered_chunks 的长度

**验证需求**：需求 4.2

### 属性 15：过滤日志记录完整性

*对于任意*查询，Filter 节点的处理日志应该包含 chunks_before 和 chunks_after 字段

**验证需求**：需求 4.3

### 属性 16：重排序降序正确性

*对于任意*文档集合，reranked_chunks 应该按 score 降序排列（即对于任意相邻的两个片段 i 和 i+1，chunks[i].score >= chunks[i+1].score）

**验证需求**：需求 5.1

### 属性 17：Top-K 选择正确性

*对于任意*配置的 rerank_top_k 值 K 和任意文档集合，reranked_chunks 的长度应该 <= K

**验证需求**：需求 5.2

### 属性 18：重排序 State 更新正确性

*对于任意*查询，Rerank 节点执行后，metrics.chunks_after_rerank 应该等于 reranked_chunks 的长度

**验证需求**：需求 5.3

### 属性 19：LLM 模型使用正确性

*对于任意*配置的模型名称，Generate 节点的处理日志中记录的 model 字段应该与配置一致

**验证需求**：需求 6.1

### 属性 20：工具使用记录正确性

*对于任意*触发工具调用的查询，tools_used 字段应该非空且包含被调用的工具名称

**验证需求**：需求 6.4

### 属性 21：置信度范围正确性

*对于任意*查询，confidence 字段应该在 0 到 1 之间（包含 0 和 1）

**验证需求**：需求 6.5

### 属性 22：来源信息非空性

*对于任意*查询，sources 字段应该是一个列表（可以为空列表，但必须是列表类型）

**验证需求**：需求 6.6

### 属性 23：LLM 调用计数正确性

*对于任意*查询，metrics.llm_calls 应该 >= 1（至少调用一次 LLM）

**验证需求**：需求 6.7

### 属性 24：MCP 工具接口正确性

*对于任意*MCP 工具（send_email, web_search, query_database）和任意有效参数，工具应该返回字符串类型的结果（成功消息或错误消息）

**验证需求**：需求 7.1, 7.2, 7.3, 7.4, 7.5

### 属性 25：质量问题检测正确性

*对于任意*答案：
- 如果长度 < 10 字符，quality_issues 应该包含 "Answer too short"
- 如果 confidence < 配置的阈值，quality_issues 应该包含 "Confidence" 相关问题

**验证需求**：需求 8.1, 8.2

### 属性 26：质量等级判断正确性

*对于任意*答案和质量问题列表：
- 如果 quality_issues 为空，answer_quality 应为 "HIGH"
- 如果 quality_issues 长度为 1，answer_quality 应为 "MEDIUM"
- 如果 quality_issues 长度 >= 2，answer_quality 应为 "LOW"

**验证需求**：需求 8.3, 8.4, 8.5

### 属性 27：回退机制正确性

*对于任意*质量为 "LOW" 的答案，如果 config.enable_fallback 为 True，则 answer 应该等于 config.fallback_message，且 used_fallback 应为 True，fallback_reason 应非空

**验证需求**：需求 8.6, 8.7

### 属性 28：性能指标初始化正确性

*对于任意*查询，初始 State 的 metrics.start_time 应该非空

**验证需求**：需求 9.1

### 属性 29：总耗时计算正确性

*对于任意*查询，最终 State 的 metrics.total_duration_ms 应该 > 0

**验证需求**：需求 9.2

### 属性 30：成本估算非负性

*对于任意*查询，metrics.estimated_cost 应该 >= 0

**验证需求**：需求 9.3

### 属性 31：指标字段完整性

*对于任意*查询，最终 State 的 metrics 应该包含 end_time（非空）、total_duration_ms（> 0）、estimated_cost（>= 0）

**验证需求**：需求 9.4

### 属性 32：初始 State 完整性

*对于任意*输入参数（query, user_id, session_id），create_initial_state 应该返回包含所有必需字段的 State（query, user_context, config, metrics, all_errors, processing_log 等）

**验证需求**：需求 10.1

### 属性 33：Reducer 字段累加正确性

*对于任意*多次更新 all_errors 或 processing_log 字段，新值应该追加到列表末尾，而不是覆盖之前的值

**验证需求**：需求 10.3

### 属性 34：最终 State 完整性

*对于任意*查询，最终 State 应该包含所有关键字段：query, answer, confidence, sources, metrics, processing_log

**验证需求**：需求 10.4

### 属性 35：API 响应格式正确性

*对于任意*有效的 /api/v1/chat/ 或 /api/v1/knowledge/ 请求，API 应该返回 HTTP 200 状态码和符合定义格式的 JSON 响应

**验证需求**：需求 11.3, 11.4, 11.5

### 属性 36：API 错误处理正确性

*对于任意*无效请求（如不支持的模型），API 应该返回 4xx 或 5xx 状态码和包含错误信息的响应

**验证需求**：需求 11.6, 11.7

### 属性 37：配置参数正确存储

*对于任意*配置参数（model, temperature, retrieval_strategy 等），RAGConfig 对象应该正确存储这些参数，且可以通过属性访问

**验证需求**：需求 12.1, 12.2, 12.3, 12.4, 12.5, 12.6

### 属性 38：节点错误捕获正确性

*对于任意*模拟的节点异常，节点应该捕获异常并返回包含错误信息的 State 更新（而不是让异常传播）

**验证需求**：需求 13.1

### 属性 39：部分执行结果保留

*对于任意*在中间节点出错的查询，之前成功执行的节点的结果应该保留在最终 State 中

**验证需求**：需求 13.5

## 错误处理

### 错误处理策略

1. **节点级错误处理**：
   - 每个节点使用 try-except 捕获所有异常
   - 将错误信息添加到 `all_errors` 字段
   - 打印错误日志到控制台
   - 返回部分更新的 State（保留已有数据）

2. **API 级错误处理**：
   - 参数验证错误 → HTTP 400
   - 后端处理错误 → HTTP 500
   - 返回包含错误详情的 JSON

3. **LLM 调用错误处理**：
   - 配置重试机制（最多 3 次）
   - 超时设置（默认 60 秒）
   - 失败后记录错误并返回回退消息

4. **工具调用错误处理**：
   - 工具执行失败时返回错误消息字符串
   - 不抛出异常，让 LLM 处理错误信息
   - 记录工具调用失败到日志

### 错误恢复机制

1. **质量回退**：
   - 当答案质量低于阈值时，使用预定义的回退消息
   - 保留原始答案和质量信息用于调试

2. **部分结果返回**：
   - 即使某个节点失败，也返回已执行节点的结果
   - 在响应中标注哪个阶段出错

3. **降级策略**：
   - 检索失败 → 使用 LLM 通用知识回答
   - 重排序失败 → 使用过滤后的结果
   - 质量检查失败 → 跳过质量检查，直接返回答案

## 测试策略

### 双重测试方法

系统采用**单元测试**和**属性测试**相结合的方法，确保全面的测试覆盖：

- **单元测试**：验证特定示例、边缘情况和错误条件
- **属性测试**：验证通用属性在所有输入下都成立

两种测试方法是互补的，单元测试捕获具体的 bug，属性测试验证通用的正确性。

### 单元测试

**测试范围**：
- 特定示例：测试已知的输入输出对
- 边缘情况：空查询、超长查询、特殊字符
- 错误条件：无效参数、API 错误、超时
- 集成点：API 端点、节点间交互

**测试框架**：pytest

**示例测试**：
```python
def test_query_analysis_factual_intent():
    """测试事实性查询的意图识别"""
    state = create_initial_state(
        query="什么是 LangGraph？",
        user_id="test_user",
        session_id="test_session"
    )
    result = query_analysis_node(state)
    assert result["query_intent"] == "factual"

def test_empty_query_handling():
    """测试空查询的处理"""
    state = create_initial_state(
        query="",
        user_id="test_user",
        session_id="test_session"
    )
    result = knowledge_agent.invoke(state)
    assert "error" in result or result["answer"] != ""

def test_api_invalid_model():
    """测试 API 对无效模型的处理"""
    response = client.post("/api/v1/chat/", json={
        "messages": [{"role": "user", "content": "Hello"}],
        "model": "invalid-model"
    })
    assert response.status_code == 400
    assert "not supported" in response.json()["detail"]
```

### 属性测试

**测试框架**：Hypothesis（Python 的属性测试库）

**配置**：
- 每个属性测试至少运行 100 次迭代
- 使用随机生成的输入数据
- 每个测试标注对应的设计文档属性

**标注格式**：
```python
# Feature: knowledge-agent-system, Property 1: 工作流节点顺序执行
```

**示例属性测试**：
```python
from hypothesis import given, strategies as st

# Feature: knowledge-agent-system, Property 1: 工作流节点顺序执行
@given(query=st.text(min_size=1, max_size=200))
def test_workflow_node_order(query):
    """属性 1：验证工作流节点按正确顺序执行"""
    state = create_initial_state(
        query=query,
        user_id="test_user",
        session_id="test_session"
    )
    result = knowledge_agent.invoke(state)
    
    # 提取节点执行顺序
    stages = [log["stage"] for log in result["processing_log"]]
    
    # 验证顺序
    expected_order = [
        "query_analysis",
        "retrieve",
        "filter",
        "rerank",
        "generate",
        "metrics"
    ]
    
    # quality_check 是可选的，可能在 generate 和 metrics 之间
    assert stages[0] == "query_analysis"
    assert stages[1] == "retrieve"
    assert stages[2] == "filter"
    assert stages[3] == "rerank"
    assert stages[4] == "generate"
    assert stages[-1] == "metrics"

# Feature: knowledge-agent-system, Property 7: 查询复杂度判断正确性
@given(query=st.text(min_size=1, max_size=100))
def test_query_complexity_classification(query):
    """属性 7：验证查询复杂度判断正确"""
    state = create_initial_state(
        query=query,
        user_id="test_user",
        session_id="test_session"
    )
    result = query_analysis_node(state)
    
    query_length = len(query)
    complexity = result["query_complexity"]
    
    if query_length < 20:
        assert complexity == "simple"
    elif query_length <= 50:
        assert complexity == "medium"
    else:
        assert complexity == "complex"

# Feature: knowledge-agent-system, Property 13: 过滤阈值正确性
@given(
    threshold=st.floats(min_value=0.0, max_value=1.0),
    num_chunks=st.integers(min_value=1, max_value=10)
)
def test_filter_threshold_correctness(threshold, num_chunks):
    """属性 13：验证过滤阈值正确应用"""
    # 生成随机文档片段
    chunks = [
        {
            "id": f"doc_{i}",
            "content": f"Content {i}",
            "title": f"Title {i}",
            "score": random.uniform(0.0, 1.0),
            "metadata": {}
        }
        for i in range(num_chunks)
    ]
    
    state = create_initial_state(
        query="test query",
        user_id="test_user",
        session_id="test_session",
        config=RAGConfig(vector_score_threshold=threshold)
    )
    state["merged_chunks"] = chunks
    
    result = filter_node(state)
    
    # 验证所有过滤后的片段 score >= threshold
    for chunk in result["filtered_chunks"]:
        assert chunk["score"] >= threshold

# Feature: knowledge-agent-system, Property 21: 置信度范围正确性
@given(query=st.text(min_size=1, max_size=200))
def test_confidence_score_range(query):
    """属性 21：验证置信度在有效范围内"""
    state = create_initial_state(
        query=query,
        user_id="test_user",
        session_id="test_session"
    )
    result = knowledge_agent.invoke(state)
    
    assert 0.0 <= result["confidence"] <= 1.0
```

### 测试覆盖目标

- **单元测试覆盖率**：> 80%
- **属性测试数量**：至少 20 个属性测试（对应 20+ 个正确性属性）
- **API 测试**：覆盖所有端点和错误情况
- **集成测试**：端到端工作流测试

### 测试执行

```bash
# 运行所有测试
pytest tests/

# 运行单元测试
pytest tests/unit/

# 运行属性测试
pytest tests/properties/

# 运行 API 测试
pytest tests/api/

# 生成覆盖率报告
pytest --cov=knowledge_agent --cov-report=html
```

### 持续集成

- 每次提交自动运行所有测试
- 属性测试使用固定的随机种子确保可重现性
- 测试失败时阻止合并
- 定期运行长时间属性测试（1000+ 迭代）

