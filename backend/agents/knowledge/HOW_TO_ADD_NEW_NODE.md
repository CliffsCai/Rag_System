# 如何添加新节点并接入 Knowledge Agent 流程

## 当前 Graph 流程

```
START
  ↓
query_rewrite          # 改写用户提问
  ↓
query_classify         # 判断 single_doc / multi_doc
  ↓
determine_retrieval_strategy  # 判断检索策略 (keyword / hybrid)
  ↓
  ┌──────────────────────────────────────────────┐
  │ [single_doc 路径]                             │
  │ single_doc_retrieve → generate_answer        │
  └──────────────────────────────────────────────┘
  ┌──────────────────────────────────────────────┐
  │ [multi_doc 路径]                              │
  │ multi_doc_retrieve → filter_chunks           │
  │   → rerank_chunks → generate_answer          │
  └──────────────────────────────────────────────┘
  ↓
check_quality (条件跳过)
  ↓
finalize_metrics
  ↓
END
```

---

## 第一步：新建节点文件

在 `backend/agents/knowledge/nodes/` 下新建文件，例如 `my_node.py`。

### 节点函数规范

```python
# -*- coding: utf-8 -*-
from typing import Dict, Any
from ..state import KnowledgeAgentState

def my_node(state: KnowledgeAgentState) -> Dict[str, Any]:
    """节点说明"""
    # 读取 state 字段
    query = state.get("query") or ""
    chunks = state.get("merged_chunks") or []

    # 处理逻辑 ...
    result = do_something(query, chunks)

    # 只返回本节点修改的字段，绝对不要 {**state, ...}
    return {
        "merged_chunks": result,
    }
```

### 关键规则

**1. 只返回变更字段**

```python
# ✅ 正确
return {"merged_chunks": new_chunks}

# ❌ 错误 —— 会触发 add_messages reducer 重复追加消息，导致状态异常
return {**state, "merged_chunks": new_chunks}
```

**2. 读取 state 用 `.get()` + `or` 默认值**

```python
# ✅ 正确 —— 避免 KeyError 静默失败
chunks = state.get("merged_chunks") or []
query  = state.get("query") or ""

# ❌ 危险 —— 字段不存在时抛 KeyError，节点静默跳过
chunks = state["merged_chunks"]
```

**3. 调试日志用 `print()`**

```python
# ✅ 正确 —— 日志立即可见
print(f"[MyNode] 处理 {len(chunks)} 个 chunk")

# ❌ 不推荐 —— logger 默认 WARNING 级别，INFO 不显示
import logging
logger = logging.getLogger(__name__)
logger.info("...")   # 生产环境看不到
```

**4. LLM 调用统一用 DashScope**

```python
import dashscope
from dashscope import Generation
from app.core.config import settings

response = Generation.call(
    api_key=settings.dashscope_api_key,
    model="qwen-plus",
    messages=[
        {"role": "system", "content": "你是..."},
        {"role": "user",   "content": query},
    ],
    result_format="message",
)

if response.status_code != 200:
    raise RuntimeError(f"DashScope error {response.status_code}: {response.message}")

answer = response.output.choices[0].message.get("content", "")
```

> 不要使用 `ChatOpenAI` 或任何 LangChain LLM wrapper。

---

## 第二步：在 `nodes/__init__.py` 导出

打开 `backend/agents/knowledge/nodes/__init__.py`，添加导入和 `__all__`：

```python
from .my_node import my_node   # 新增

__all__ = [
    # ... 已有节点 ...
    "my_node",                 # 新增
]
```

---

## 第三步：在 `graph.py` 注册节点并连边

打开 `backend/agents/knowledge/graph.py`。

### 3.1 导入节点

```python
from .nodes import (
    # ... 已有节点 ...
    my_node,   # 新增
)
```

### 3.2 注册节点

```python
builder.add_node("my_node", my_node)
```

### 3.3 连边（普通顺序边）

```python
# 例：插入到 single_doc_retrieve 和 generate_answer 之间
builder.add_edge("single_doc_retrieve", "my_node")
builder.add_edge("my_node", "generate_answer")
```

### 3.4 连边（条件路由）

如果节点需要根据 state 决定下一步走哪条路：

```python
def route_after_my_node(state: KnowledgeAgentState) -> Literal["generate_answer", "fallback_node"]:
    if state.get("confidence", 0) > 0.8:
        return "generate_answer"
    return "fallback_node"

builder.add_conditional_edges(
    "my_node",
    route_after_my_node,
    {
        "generate_answer": "generate_answer",
        "fallback_node":   "fallback_node",
    }
)
```

---

## 扩展 State 字段

如果新节点需要在 state 中存储新数据，在 `backend/agents/knowledge/state.py` 的 `KnowledgeAgentState` 中添加字段：

```python
class KnowledgeAgentState(TypedDict):
    # ... 已有字段 ...

    # 新增字段（普通字段）
    my_result: Optional[str]
    my_scores: List[float]
```

同时在 `create_initial_state()` 函数中初始化：

```python
return {
    # ... 已有初始化 ...
    "my_result": None,
    "my_scores": [],
}
```

### 累加型字段（Reducer）

如果字段需要跨节点累加（而不是覆盖），使用 `Annotated` + reducer：

```python
import operator
from typing import Annotated

class KnowledgeAgentState(TypedDict):
    # 每个节点返回的列表会被 operator.add 拼接，而不是覆盖
    processing_log: Annotated[List[Dict[str, Any]], operator.add]
```

> `messages` 字段使用的是 `add_messages` reducer，这就是为什么节点返回 `{"messages": [...]}` 时是追加而非覆盖。

---

## 注意事项

| 事项 | 说明 |
|------|------|
| 不要用 MemorySaver | `graph.compile()` 不带任何参数，加 checkpointer 会导致节点执行顺序异常 |
| `merged_chunks` 是 single_doc 路径的 chunk 传递字段 | `single_doc_retrieve` 把结果写入 `merged_chunks`，`generate_answer` 从 `merged_chunks` 读取 |
| multi_doc 路径的 chunk 流转 | `multi_doc_retrieve` → `filter_chunks` → `rerank_chunks`，最终也写入 `merged_chunks` 供 generate 使用 |
| 节点抛异常会中断整个 graph | 在节点内部 `try/except`，出错时返回错误信息到 state，不要让异常向上冒泡 |
| 不要在节点内修改 `messages` 字段（除非必要） | `messages` 有 `add_messages` reducer，每次返回都会追加，容易造成消息重复 |

---

## 完整示例：添加一个"摘要压缩"节点

**场景**：在 `rerank_chunks` 之后、`generate_answer` 之前，对 chunk 内容做摘要压缩。

### 1. 新建 `nodes/summarize.py`

```python
# -*- coding: utf-8 -*-
from typing import Dict, Any
import dashscope
from dashscope import Generation
from ..state import KnowledgeAgentState
from app.core.config import settings

def summarize_chunks(state: KnowledgeAgentState) -> Dict[str, Any]:
    chunks = state.get("merged_chunks") or []
    if not chunks:
        return {}

    print(f"[Summarize] 压缩 {len(chunks)} 个 chunk")

    compressed = []
    for chunk in chunks:
        content = chunk.get("content", "") if isinstance(chunk, dict) else getattr(chunk, "content", "")
        if len(content) <= 300:
            compressed.append(chunk)
            continue

        resp = Generation.call(
            api_key=settings.dashscope_api_key,
            model="qwen-plus",
            messages=[
                {"role": "system", "content": "请将以下内容压缩为100字以内的摘要，保留关键信息。"},
                {"role": "user",   "content": content},
            ],
            result_format="message",
        )
        if resp.status_code == 200:
            summary = resp.output.choices[0].message.get("content", content)
            if isinstance(chunk, dict):
                compressed.append({**chunk, "content": summary})
            else:
                chunk.content = summary
                compressed.append(chunk)
        else:
            compressed.append(chunk)

    print(f"[Summarize] 压缩完成")
    return {"merged_chunks": compressed}
```

### 2. 导出 `nodes/__init__.py`

```python
from .summarize import summarize_chunks

__all__ = [
    # ...
    "summarize_chunks",
]
```

### 3. 接入 `graph.py`

```python
from .nodes import (
    # ...
    summarize_chunks,
)

# 注册
builder.add_node("summarize_chunks", summarize_chunks)

# 原来：rerank_chunks → generate_answer
# 改为：rerank_chunks → summarize_chunks → generate_answer
builder.add_edge("rerank_chunks", "summarize_chunks")
builder.add_edge("summarize_chunks", "generate_answer")
```
