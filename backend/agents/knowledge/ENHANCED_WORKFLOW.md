# 知识库查询Agent增强功能说明

## 概述
在原有的7节点RAG workflow基础上,新增了6个节点,实现了更智能、更精准的知识库检索功能。

## 新增节点

### 1. Query Rewrite Node (query_rewrite.py)
**功能**: 增强改写用户提问

**作用**:
- 将用户的原始问题改写得更清楚、准确
- 补充必要的上下文信息
- 规范化表达方式
- 去除口语化和冗余信息

**输入**: `original_query`
**输出**: `rewritten_query` (更新到state["query"])

**示例**:
- 原始: "那个东西怎么用啊" → 改写: "请问如何使用该功能"
- 原始: "上次说的那个bug修了吗" → 改写: "之前提到的bug是否已经修复"

---

### 2. Query Classify Node (query_classify.py)
**功能**: 问题分类

**作用**:
- 判断问题是单文档查询还是多文档查询
- 单文档: 问题针对特定文档或明确指定文档名称
- 多文档: 问题需要跨多个文档查找信息

**输出**: `query_type` ("single_doc" 或 "multi_doc")

**分类标准**:
- **单文档查询**: 明确提到文档名称、使用指代词、针对单一主题
- **多文档查询**: 需要综合多个文档、涉及对比总结、范围较广

---

### 3. Retrieval Strategy Node (retrieval_strategy.py)
**功能**: 判断检索策略

**作用**:
- 判断使用关键词检索还是混合检索(关键词+向量)
- 规则: 包含错误代码、日志、命令等精确匹配内容 → 关键词检索
- 其他情况 → 混合检索

**输出**: `retrieval_strategy` (KEYWORD_ONLY 或 HYBRID)

**判断规则**:
1. 检查是否包含错误代码模式 (error:, exception:, 404 error等)
2. 检查是否包含命令或代码片段 (反引号、代码块、函数调用等)
3. 检查是否包含精确匹配关键词 (精确、完全匹配、原文等)

---

### 4. Single Doc Retrieve Node (single_doc_retrieve.py)
**功能**: 单文档查询

**作用**:
- 针对特定文档进行检索
- 返回top 10结果
- 根据retrieval_strategy使用相应的检索方式

**参数**:
- `query`: 改写后的查询
- `retrieval_strategy`: 检索策略
- `top_k`: 10

**检索方式**:
- KEYWORD_ONLY: 仅关键词检索
- HYBRID: 混合检索(关键词+向量)

---

### 5. Multi Doc Retrieve Node (multi_doc_retrieve.py)
**功能**: 多文档查询

**作用**:
- 跨多个文档进行检索
- 返回top 20结果 (比单文档多,覆盖更广)
- 根据retrieval_strategy使用相应的检索方式

**参数**:
- `query`: 改写后的查询
- `retrieval_strategy`: 检索策略
- `top_k`: 20

---

### 6. Relevance Filter Node (relevance_filter.py)
**功能**: 检索切片二次过滤

**作用**:
- 使用LLM判断每个切片与query的相关性
- 过滤掉不相关的切片
- 返回匹配后的切片列表

**处理方式**:
- 批量处理(每次5个切片)
- LLM判断每个切片是否相关
- 过滤掉不相关的切片

**输出**: `filtered_chunks` (相关的切片列表)

---

## 新的Workflow流程

```
START
  ↓
query_rewrite (增强改写用户提问)
  ↓
query_classify (判断单文档/多文档查询)
  ↓
determine_retrieval_strategy (判断检索策略: 关键词/混合)
  ↓
[条件路由]
  ├─ single_doc_retrieve (单文档查询, top 10)
  └─ multi_doc_retrieve (多文档查询, top 20)
  ↓
filter_chunks (按相关性分数过滤)
  ↓
rerank_chunks (重排序)
  ↓
relevance_filter (LLM二次过滤相关性)
  ↓
generate_answer (生成答案, 含MCP工具)
  ↓
[条件路由]
  ├─ check_quality (质量检查和降级)
  └─ finalize_metrics (计算性能指标)
  ↓
END
```

## State字段更新

新增以下状态字段:

```python
# Query processing
rewritten_query: Optional[str]  # 改写后的查询
query_type: Optional[str]  # "single_doc" 或 "multi_doc"
retrieval_strategy: Optional[RetrievalStrategy]  # 检索策略
retrieval_strategy_reason: Optional[str]  # 策略选择原因
```

## 优势

1. **更准确的查询理解**: 通过query rewrite规范化用户问题
2. **智能路由**: 根据问题类型选择最优检索策略
3. **精确匹配支持**: 对错误代码等场景使用关键词检索
4. **更高的召回率**: 多文档查询返回更多结果
5. **更高的精确率**: LLM二次过滤提升相关性
6. **灵活的检索策略**: 自动判断使用关键词还是混合检索

## 使用示例

### 示例1: 错误代码查询
```
用户输入: "error: ECONNREFUSED 怎么解决"
↓
query_rewrite: "如何解决 error: ECONNREFUSED 错误"
↓
query_classify: "multi_doc" (需要查找多个文档)
↓
retrieval_strategy: "KEYWORD_ONLY" (包含错误代码)
↓
multi_doc_retrieve: 返回20个包含该错误代码的切片
↓
filter_chunks: 按分数过滤
↓
rerank_chunks: 重排序
↓
relevance_filter: LLM过滤,保留真正相关的切片
```

### 示例2: 概念查询
```
用户输入: "什么是向量数据库"
↓
query_rewrite: "什么是向量数据库" (已经清晰)
↓
query_classify: "multi_doc" (概念性问题,需要多文档)
↓
retrieval_strategy: "HYBRID" (常规查询,使用混合检索)
↓
multi_doc_retrieve: 返回20个相关切片
↓
filter_chunks: 按分数过滤
↓
rerank_chunks: 重排序
↓
relevance_filter: LLM过滤,保留相关的切片
```

### 示例3: 特定文档查询
```
用户输入: "README.md中如何配置数据库"
↓
query_rewrite: "README.md文档中如何配置数据库"
↓
query_classify: "single_doc" (明确指定文档)
↓
retrieval_strategy: "HYBRID" (常规查询)
↓
single_doc_retrieve: 返回10个README.md中的相关切片
↓
filter_chunks: 按分数过滤
↓
rerank_chunks: 重排序
↓
relevance_filter: LLM过滤,保留相关的切片
```

## 性能指标

新增的节点会记录以下性能指标:
- `query_rewrite`: 改写耗时
- `query_classify`: 分类耗时
- `retrieval_strategy`: 策略判断耗时
- `single/multi_doc_retrieve`: 检索耗时
- `relevance_filter`: 过滤耗时

所有指标都记录在 `state["processing_log"]` 中。

## 注意事项

1. **LLM调用**: 新增节点会增加LLM调用次数,注意成本控制
2. **错误处理**: 所有节点都有完善的错误处理,失败时会降级到默认行为
3. **日志记录**: 所有节点都有详细的日志记录,便于调试
4. **SSL配置**: 确保 `settings.ssl_verify` 配置正确

## 文件清单

新增文件:
- `backend/agents/knowledge/nodes/query_rewrite.py`
- `backend/agents/knowledge/nodes/query_classify.py`
- `backend/agents/knowledge/nodes/retrieval_strategy.py`
- `backend/agents/knowledge/nodes/single_doc_retrieve.py`
- `backend/agents/knowledge/nodes/multi_doc_retrieve.py`
- `backend/agents/knowledge/nodes/relevance_filter.py`

修改文件:
- `backend/agents/knowledge/state.py` (新增状态字段)
- `backend/agents/knowledge/graph.py` (更新workflow)
- `backend/agents/knowledge/nodes/__init__.py` (导出新节点)

## 测试建议

1. 测试query rewrite功能: 输入口语化问题,检查改写效果
2. 测试query classify功能: 输入单文档和多文档问题,检查分类准确性
3. 测试retrieval strategy: 输入包含错误代码的问题,检查是否使用关键词检索
4. 测试单文档检索: 明确指定文档名称,检查是否返回10个结果
5. 测试多文档检索: 输入概念性问题,检查是否返回20个结果
6. 测试relevance filter: 检查LLM过滤效果,是否移除不相关切片
