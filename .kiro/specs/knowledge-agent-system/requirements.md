# 需求文档：Knowledge Agent System

> 文档状态（规格目标态）：本文定义需求目标，不等同于当前代码快照。若与现实现冲突，以 `PROJECT_STRUCTURE_MASTER.md` 和实际代码路径为准。

## 简介

Knowledge Agent System 是一个基于 LangGraph 的企业级知识库智能问答系统。系统采用完整的 7 节点 RAG（检索增强生成）工作流，集成 MCP（Model Context Protocol）工具，支持复杂的查询分析、文档检索、过滤、重排序、答案生成和质量检查。

系统当前已完成核心架构实现（方案 3），使用 Mock 数据进行检索，准备连接真实知识库（阿里云百炼 ADB）。

## 术语表

- **Knowledge_Agent**: 知识库智能代理，负责处理用户查询并生成答案的核心组件
- **RAG_Pipeline**: 检索增强生成流水线，包含查询分析、检索、过滤、重排序、生成等多个阶段
- **State**: 状态对象，在工作流节点间传递数据和上下文信息
- **Node**: 工作流节点，执行特定任务的处理单元
- **MCP_Tool**: Model Context Protocol 工具，扩展 Agent 能力的外部工具
- **Chunk**: 文档片段，知识库中的最小检索单元
- **Vector_Search**: 向量搜索，基于语义相似度的检索方法
- **Rerank**: 重排序，对检索结果进行二次排序以提高相关性
- **LLM**: 大语言模型，用于生成答案的 AI 模型
- **Bailian_ADB**: 阿里云百炼向量数据库，用于存储和检索知识库文档

## 需求

### 需求 1：完整的 RAG 工作流

**用户故事**：作为开发者，我希望系统实现完整的 7 节点 RAG 工作流，以便系统能够高质量地处理用户查询并生成准确的答案。

#### 验收标准

1. WHEN 用户发送查询 THEN THE Knowledge_Agent SHALL 按顺序执行所有 7 个节点（query_analysis → retrieve → filter → rerank → generate → quality_check → metrics）
2. WHEN 任一节点执行完成 THEN THE Knowledge_Agent SHALL 更新 State 并传递给下一个节点
3. WHEN 工作流执行完成 THEN THE Knowledge_Agent SHALL 返回包含答案、置信度、来源和性能指标的完整结果
4. WHEN 节点执行出错 THEN THE Knowledge_Agent SHALL 记录错误信息到 State 的 all_errors 字段
5. WHEN 工作流执行 THEN THE Knowledge_Agent SHALL 记录每个节点的处理日志到 processing_log 字段

### 需求 2：查询分析

**用户故事**：作为开发者，我希望系统能够分析用户查询的意图和复杂度，以便后续节点能够采用合适的处理策略。

#### 验收标准

1. WHEN 查询包含"如何"、"怎么"、"怎样"关键词 THEN THE Query_Analysis_Node SHALL 识别意图为 "procedural"
2. WHEN 查询包含"是什么"、"什么是"关键词 THEN THE Query_Analysis_Node SHALL 识别意图为 "factual"
3. WHEN 查询包含"比较"、"区别"、"差异"关键词 THEN THE Query_Analysis_Node SHALL 识别意图为 "comparative"
4. WHEN 查询长度小于 20 字符 THEN THE Query_Analysis_Node SHALL 标记复杂度为 "simple"
5. WHEN 查询长度在 20-50 字符之间 THEN THE Query_Analysis_Node SHALL 标记复杂度为 "medium"
6. WHEN 查询长度大于 50 字符 THEN THE Query_Analysis_Node SHALL 标记复杂度为 "complex"
7. WHEN 查询分析完成 THEN THE Query_Analysis_Node SHALL 提取关键词并更新 State 的 query_keywords 字段

### 需求 3：文档检索

**用户故事**：作为开发者，我希望系统能够从知识库中检索相关文档，以便为答案生成提供上下文信息。

#### 验收标准

1. WHEN 检索策略为 "hybrid" THEN THE Retrieve_Node SHALL 同时使用向量搜索和关键词搜索
2. WHEN 检索完成 THEN THE Retrieve_Node SHALL 返回至少 1 个文档片段
3. WHEN 检索完成 THEN THE Retrieve_Node SHALL 为每个片段包含 id、content、title、score 和 metadata 字段
4. WHEN 检索完成 THEN THE Retrieve_Node SHALL 更新 State 的 retrieved_chunks 和 metrics.total_chunks_retrieved 字段
5. WHEN 使用 Mock 数据 THEN THE Retrieve_Node SHALL 在处理日志中标注 "MOCK DATA"

### 需求 4：文档过滤

**用户故事**：作为开发者，我希望系统能够过滤低相关性的文档片段，以便提高答案质量并减少 LLM 处理成本。

#### 验收标准

1. WHEN 文档片段的 score 低于配置的阈值 THEN THE Filter_Node SHALL 移除该片段
2. WHEN 过滤完成 THEN THE Filter_Node SHALL 更新 State 的 filtered_chunks 和 metrics.chunks_after_filter 字段
3. WHEN 过滤完成 THEN THE Filter_Node SHALL 记录过滤前后的片段数量到处理日志

### 需求 5：文档重排序

**用户故事**：作为开发者，我希望系统能够对过滤后的文档进行重排序，以便最相关的文档排在前面。

#### 验收标准

1. WHEN 重排序执行 THEN THE Rerank_Node SHALL 按 score 降序排列文档片段
2. WHEN 重排序完成 THEN THE Rerank_Node SHALL 选择 top-K 个片段（K 由配置指定）
3. WHEN 重排序完成 THEN THE Rerank_Node SHALL 更新 State 的 reranked_chunks 和 metrics.chunks_after_rerank 字段

### 需求 6：答案生成与 MCP 工具集成

**用户故事**：作为开发者，我希望系统能够基于检索的上下文生成答案，并在需要时调用 MCP 工具扩展功能。

#### 验收标准

1. WHEN 生成答案 THEN THE Generate_Node SHALL 使用配置的 LLM 模型（如 qwen-plus）
2. WHEN 生成答案 THEN THE Generate_Node SHALL 将重排序后的文档片段作为上下文传递给 LLM
3. WHEN LLM 决定调用工具 THEN THE Generate_Node SHALL 执行相应的 MCP 工具并将结果返回给 LLM
4. WHEN 工具调用完成 THEN THE Generate_Node SHALL 记录使用的工具名称到 State 的 tools_used 字段
5. WHEN 答案生成完成 THEN THE Generate_Node SHALL 计算置信度分数并更新 State 的 confidence 字段
6. WHEN 答案生成完成 THEN THE Generate_Node SHALL 提取来源信息并更新 State 的 sources 字段
7. WHEN 答案生成完成 THEN THE Generate_Node SHALL 增加 metrics.llm_calls 计数

### 需求 7：MCP 工具功能

**用户故事**：作为用户，我希望 Agent 能够使用工具扩展功能，以便完成发送邮件、搜索网络、查询数据库等任务。

#### 验收标准

1. WHEN 用户请求发送邮件 THEN THE send_email_tool SHALL 接受 to、subject、body 参数并返回成功消息
2. WHEN 用户请求搜索网络 THEN THE web_search_tool SHALL 接受 query 和 num_results 参数并返回搜索结果摘要
3. WHEN 用户请求查询数据库 THEN THE query_database_tool SHALL 接受 sql 参数并返回查询执行结果
4. WHEN 工具执行成功 THEN THE MCP_Tool SHALL 返回包含执行结果的字符串
5. WHEN 工具执行失败 THEN THE MCP_Tool SHALL 返回包含错误信息的字符串

### 需求 8：质量检查与回退

**用户故事**：作为开发者，我希望系统能够检查答案质量，并在质量不达标时提供回退机制。

#### 验收标准

1. WHEN 答案长度小于 10 字符 THEN THE Quality_Check_Node SHALL 标记质量问题 "Answer too short"
2. WHEN 置信度低于配置的阈值 THEN THE Quality_Check_Node SHALL 标记质量问题 "Confidence below threshold"
3. WHEN 没有质量问题 THEN THE Quality_Check_Node SHALL 设置 answer_quality 为 "HIGH"
4. WHEN 有 1 个质量问题 THEN THE Quality_Check_Node SHALL 设置 answer_quality 为 "MEDIUM"
5. WHEN 有 2 个或更多质量问题 THEN THE Quality_Check_Node SHALL 设置 answer_quality 为 "LOW"
6. WHEN 质量为 "LOW" 且启用回退 THEN THE Quality_Check_Node SHALL 使用配置的回退消息替换答案
7. WHEN 使用回退 THEN THE Quality_Check_Node SHALL 设置 used_fallback 为 True 并记录回退原因

### 需求 9：性能指标统计

**用户故事**：作为开发者，我希望系统能够统计性能指标，以便监控系统性能和优化资源使用。

#### 验收标准

1. WHEN 工作流开始 THEN THE System SHALL 记录 start_time 到 metrics
2. WHEN 工作流结束 THEN THE Metrics_Finalization_Node SHALL 计算 total_duration_ms
3. WHEN 指标统计完成 THEN THE Metrics_Finalization_Node SHALL 估算 token 使用成本
4. WHEN 指标统计完成 THEN THE Metrics_Finalization_Node SHALL 更新 metrics 的 end_time、total_duration_ms 和 estimated_cost 字段

### 需求 10：State 管理

**用户故事**：作为开发者，我希望系统能够正确管理 State 对象，以便在节点间传递数据和保持上下文一致性。

#### 验收标准

1. WHEN 创建初始 State THEN THE System SHALL 包含所有必需字段（query、user_context、config、metrics 等）
2. WHEN 节点更新 State THEN THE System SHALL 保留其他节点设置的字段值
3. WHEN 使用 reducer 字段（all_errors、all_warnings、processing_log）THEN THE System SHALL 累加新值而不是覆盖
4. WHEN 工作流完成 THEN THE State SHALL 包含完整的执行历史和结果数据

### 需求 11：API 接口

**用户故事**：作为前端开发者，我希望系统提供 RESTful API 接口，以便前端应用能够与 Agent 交互。

#### 验收标准

1. WHEN 访问 GET / 端点 THEN THE API SHALL 返回健康检查信息和系统配置
2. WHEN 访问 GET /models 端点 THEN THE API SHALL 返回支持的模型列表
3. WHEN 发送 POST /api/v1/chat/ 请求 THEN THE API SHALL 接受 messages、model、temperature 参数并返回对话响应
4. WHEN 发送 POST /api/v1/knowledge/ 请求 THEN THE API SHALL 接受 query、session_id、model 参数并返回知识库问答响应
5. WHEN API 请求成功 THEN THE API SHALL 返回 HTTP 200 状态码和正确格式的响应
6. WHEN API 请求失败 THEN THE API SHALL 返回适当的 HTTP 错误状态码和错误信息
7. WHEN 使用不支持的模型 THEN THE API SHALL 返回 HTTP 400 错误和可用模型列表

### 需求 12：配置管理

**用户故事**：作为开发者，我希望系统支持灵活的配置管理，以便根据不同场景调整系统行为。

#### 验收标准

1. WHEN 创建 RAGConfig THEN THE System SHALL 支持配置 model、temperature、max_tokens 等模型参数
2. WHEN 创建 RAGConfig THEN THE System SHALL 支持配置 retrieval_strategy、vector_top_k 等检索参数
3. WHEN 创建 RAGConfig THEN THE System SHALL 支持配置 enable_llm_filter、max_chunks_after_filter 等过滤参数
4. WHEN 创建 RAGConfig THEN THE System SHALL 支持配置 enable_rerank、rerank_top_k 等重排序参数
5. WHEN 创建 RAGConfig THEN THE System SHALL 支持配置 enable_fallback、min_confidence_threshold 等质量控制参数
6. WHEN 未提供配置 THEN THE System SHALL 使用合理的默认值

### 需求 13：错误处理

**用户故事**：作为开发者，我希望系统能够优雅地处理错误，以便提高系统稳定性和可调试性。

#### 验收标准

1. WHEN 节点执行出错 THEN THE Node SHALL 捕获异常并返回包含错误信息的 State 更新
2. WHEN 节点执行出错 THEN THE Node SHALL 将错误信息添加到 State 的 all_errors 字段
3. WHEN 节点执行出错 THEN THE Node SHALL 打印错误日志到控制台
4. WHEN API 请求处理出错 THEN THE API SHALL 返回 HTTP 500 错误和错误详情
5. WHEN 工作流执行出错 THEN THE System SHALL 确保已执行的节点结果被保留在 State 中

### 需求 14：前端界面

**用户故事**：作为用户，我希望有一个友好的聊天界面，以便与 Knowledge Agent 进行交互。

#### 验收标准

1. WHEN 用户访问前端应用 THEN THE Frontend SHALL 显示聊天界面
2. WHEN 用户输入消息并发送 THEN THE Frontend SHALL 调用后端 API 并显示响应
3. WHEN Agent 使用工具 THEN THE Frontend SHALL 显示工具使用标签（绿色标签）
4. WHEN 用户选择模型 THEN THE Frontend SHALL 在后续请求中使用选定的模型
5. WHEN 用户点击清空对话 THEN THE Frontend SHALL 清除所有消息历史
6. WHEN API 返回错误 THEN THE Frontend SHALL 显示错误通知

### 需求 15：知识库集成准备

**用户故事**：作为开发者，我希望系统架构能够轻松集成真实知识库，以便从 Mock 数据过渡到生产环境。

#### 验收标准

1. WHEN 替换 Retrieve_Node 实现 THEN THE System SHALL 保持其他节点不变
2. WHEN 连接真实知识库 THEN THE Retrieve_Node SHALL 调用 Bailian_ADB 向量搜索 API
3. WHEN 连接真实知识库 THEN THE Retrieve_Node SHALL 返回与 Mock 数据相同格式的 RetrievedChunk 对象
4. WHEN 集成真实检索服务 THEN THE System SHALL 支持向量搜索、关键词搜索和混合搜索策略

## 非功能需求

### 性能需求

1. THE System SHALL 在 3 秒内完成单次查询处理（不包括 LLM 调用时间）
2. THE System SHALL 支持并发处理多个用户请求
3. THE API SHALL 在 100ms 内响应健康检查请求

### 可扩展性需求

1. THE System SHALL 支持添加新的工作流节点而不影响现有节点
2. THE System SHALL 支持注册新的 MCP 工具而不修改核心代码
3. THE System SHALL 支持切换不同的 LLM 模型而不修改工作流逻辑

### 可维护性需求

1. THE System SHALL 为每个节点提供清晰的日志输出
2. THE System SHALL 在 State 中记录完整的处理历史
3. THE System SHALL 使用类型注解提高代码可读性

### 可靠性需求

1. WHEN LLM 调用失败 THEN THE System SHALL 重试最多 3 次
2. WHEN 节点执行超时 THEN THE System SHALL 记录超时错误并继续执行后续节点（如果可能）
3. WHEN 工具调用失败 THEN THE System SHALL 返回错误信息给 LLM 而不是崩溃

## 约束条件

### 技术栈约束

1. THE System SHALL 使用 Python 3.8+ 作为开发语言
2. THE System SHALL 使用 LangGraph 作为工作流编排框架
3. THE System SHALL 使用 FastAPI 作为 API 框架
4. THE System SHALL 使用 Vue 3 作为前端框架
5. THE System SHALL 使用阿里云百炼（DashScope）作为 LLM 服务提供商

### 依赖项约束

1. THE System SHALL 依赖 langgraph、langchain-core、langchain-openai 库
2. THE System SHALL 依赖 fastapi、uvicorn、pydantic 库
3. THE System SHALL 依赖 httpx 库进行 HTTP 请求
4. THE Frontend SHALL 依赖 vue、axios 库

### 环境约束

1. THE System SHALL 从环境变量或 .env 文件读取 DASHSCOPE_API_KEY
2. THE System SHALL 支持禁用 SSL 验证（用于开发环境）
3. THE System SHALL 支持配置 API 主机和端口

### 数据约束

1. THE System SHALL 使用 UTF-8 编码处理所有文本数据
2. THE System SHALL 支持中文和英文查询
3. THE RetrievedChunk SHALL 包含 content、score、source、doc_id、chunk_id 等必需字段
