# LangGraph Graph API 完整指南

## 目录
1. [核心概念](#核心概念)
2. [状态管理](#状态管理)
3. [节点详解](#节点详解)
4. [边与控制流](#边与控制流)
5. [高级特性](#高级特性)
6. [实用技巧](#实用技巧)

---

## 核心概念

### 什么是 Graph API

LangGraph 的 Graph API 是一个用于构建有状态、基于事件的应用程序的低级 API。它基于 Pregel 模型（Google 的分布式图处理框架），提供对工作流构建的精细控制。

### 三大核心组件

```
图 (Graph)
├── 状态 (State)     - 全局共享数据
├── 节点 (Nodes)     - 计算单元
└── 边 (Edges)       - 控制流
```

### Pregel 执行模型

LangGraph 采用 super-step 执行模型：

1. **并行执行**：每个 super-step 中，所有可执行节点并行运行
2. **消息传递**：节点接收上一步的消息（状态）
3. **状态更新**：节点更新自己的状态
4. **继续或终止**：有消息则继续，无消息则结束

```
Super-step 1: [节点A] → 更新状态 → 发送消息
Super-step 2: [节点B, 节点C] → 并行执行 → 更新状态
Super-step 3: [节点D] → 聚合结果 → 结束
```

---

## 状态管理

### 状态定义方式

Python 提供三种方式定义状态：

**1. TypedDict（推荐）**
```python
from typing_extensions import TypedDict

class State(TypedDict):
    input: str
    count: int
    results: list[str]
```

**2. Dataclass**
```python
from dataclasses import dataclass

@dataclass
class State:
    input: str
    count: int = 0  # 支持默认值
```

**3. Pydantic 模型**
```python
from pydantic import BaseModel

class State(BaseModel):
    input: str
    count: int = 0
```

### Reducers（状态合并器）

当多个节点更新同一状态键时，Reducer 决定如何合并这些更新。

#### 内置 Reducers

```python
from typing import Annotated
import operator

class State(TypedDict):
    # 列表连接
    messages: Annotated[list, operator.add]
    
    # 数字相加
    count: Annotated[int, operator.add]
    
    # 字符串连接
    text: Annotated[str, operator.add]
```

#### 自定义 Reducer

```python
def custom_merge(left: dict, right: dict) -> dict:
    """自定义合并逻辑"""
    return {**left, **right, "merged": True}

class State(TypedDict):
    data: Annotated[dict, custom_merge]
```

### 多模式 Schema

支持为输入、输出和内部状态定义不同的 Schema：

```python
class InputState(TypedDict):
    user_input: str

class OverallState(InputState):
    intermediate: str
    processing_steps: list[str]

class OutputState(TypedDict):
    final_result: str

builder = StateGraph(OverallState)
# ... 添加节点和边
graph = builder.compile(output_schema=OutputState)
```

**使用场景**：
- 隐藏内部实现细节
- 简化 API 接口
- 保护敏感信息

### MessagesState（消息状态）

专为聊天应用设计的预构建状态：

```python
from langgraph.graph import MessagesState

class ChatState(MessagesState):
    user_id: str
    session_id: str
```

---

## 节点详解

### 节点基础

节点是接收状态并返回状态更新的函数。

```python
def my_node(state: State) -> dict:
    """节点函数"""
    # 读取状态
    input_value = state["input"]
    
    # 处理逻辑
    result = process(input_value)
    
    # 返回状态更新
    return {"output": result}
```

### 节点参数

节点可以接收额外的参数：

```python
from langgraph.runtime import Runtime
from langchain_core.runnables import RunnableConfig

def advanced_node(
    state: State,
    config: RunnableConfig,  # 运行时配置
    runtime: Runtime         # 运行时上下文
):
    # 访问线程 ID
    thread_id = config["configurable"]["thread_id"]
    
    # 访问自定义上下文
    llm_provider = runtime.context.llm_provider
    
    return {"result": "processed"}
```

### 特殊节点

START 和 END 是两个特殊节点：

```python
from langgraph.graph import START, END

builder.add_edge(START, "first_node")  # 入口点
builder.add_edge("last_node", END)     # 终止点
```

### 节点缓存

避免重复计算，提高性能：

```python
from langgraph.types import CachePolicy
from langgraph.cache.memory import InMemoryCache

builder.add_node(
    "expensive_node",
    expensive_function,
    cache_policy=CachePolicy(ttl=120)  # 缓存 120 秒
)

graph = builder.compile(cache=InMemoryCache())
```

**使用场景**：
- API 调用
- 数据库查询
- 复杂计算
- LLM 推理

### 节点重试策略

```python
from langgraph.types import RetryPolicy

builder.add_node(
    "api_call",
    call_api,
    retry_policy=RetryPolicy(
        max_attempts=3,
        backoff_factor=2.0,
        retry_on=lambda e: isinstance(e, APIError)
    )
)
```

**默认重试的异常**：
- 网络错误
- 5xx HTTP 状态码
- 超时错误

**不重试的异常**：
- ValueError, TypeError（逻辑错误）
- 4xx HTTP 状态码（客户端错误）

### 延迟节点执行

在分支长度不同的工作流中很有用：

```python
builder.add_node("aggregator", aggregate_results, defer=True)
```

**使用场景**：Map-Reduce 模式中的 Reduce 节点

---

## 边与控制流

### 普通边（固定边）

直接连接两个节点：

```python
builder.add_edge("node_a", "node_b")
```

### 条件边（动态路由）

根据状态动态选择下一个节点：

```python
from typing import Literal

def route_logic(state: State) -> Literal["path_a", "path_b", "path_c"]:
    if state["score"] > 0.8:
        return "path_a"
    elif state["score"] > 0.5:
        return "path_b"
    else:
        return "path_c"

builder.add_conditional_edges(
    "router_node",
    route_logic,
    {
        "path_a": "node_a",
        "path_b": "node_b",
        "path_c": "node_c"
    }
)
```

### 条件入口点

根据输入动态选择起始节点：

```python
from langgraph.graph import START

def entry_router(state: State) -> str:
    if state["type"] == "urgent":
        return "fast_track"
    return "normal_track"

builder.add_conditional_edges(START, entry_router)
```

### Send API（动态分发）

动态创建多个节点实例，实现 Map-Reduce 模式：

```python
from langgraph.types import Send

def distribute_work(state: OverallState):
    """为每个任务创建一个工作者"""
    return [
        Send("worker", {"task": task})
        for task in state["tasks"]
    ]

builder.add_conditional_edges(
    "coordinator",
    distribute_work,
    ["worker"]
)
```

**关键特性**：
- 动态数量的工作者
- 每个工作者有独立的状态
- 所有工作者并行执行
- 结果自动聚合到共享状态键

### Command 对象（控制流 + 状态更新）

在单个节点中同时执行状态更新和控制流决策：

```python
from langgraph.graph import Command
from typing import Literal

def smart_node(state: State) -> Command[Literal["next_node", END]]:
    # 处理逻辑
    result = process(state)
    
    # 同时返回状态更新和路由决策
    if result.success:
        return Command(
            update={"result": result.data},
            goto=END
        )
    else:
        return Command(
            update={"error": result.error},
            goto="retry_node"
        )
```

**使用场景**：
- 工具调用后的路由
- 错误处理和重试
- 人机交互循环

### 子图导航

在子图中导航到父图节点：

```python
def subgraph_node(state: State) -> Command:
    return Command(
        update={"data": "processed"},
        goto="parent_node",
        graph=Command.PARENT  # 导航到父图
    )
```

---

## 高级特性

### 创建循环

**基本循环结构**

```python
def should_continue(state: State) -> Literal["continue", END]:
    if state["iteration"] < state["max_iterations"]:
        return "continue"
    return END

builder.add_edge(START, "process")
builder.add_conditional_edges(
    "process",
    should_continue,
    {
        "continue": "process",  # 循环回自己
        END: END
    }
)
```

**递归限制**

防止无限循环：

```python
from langgraph.errors import GraphRecursionError

try:
    result = graph.invoke(
        {"input": "data"},
        config={"recursion_limit": 10}
    )
except GraphRecursionError:
    print("达到递归限制")
```

**默认限制**：25 个 super-steps

### 序列简写

快速创建节点序列：

```python
# 完整写法
builder.add_node("step_1", step_1)
builder.add_node("step_2", step_2)
builder.add_node("step_3", step_3)
builder.add_edge(START, "step_1")
builder.add_edge("step_1", "step_2")
builder.add_edge("step_2", "step_3")

# 简写
builder.add_sequence([step_1, step_2, step_3])
builder.add_edge(START, "step_1")
```

### 并行执行

**扇出-扇入模式**

```python
import operator
from typing import Annotated

class State(TypedDict):
    aggregate: Annotated[list, operator.add]

# 从 A 扇出到 B 和 C
builder.add_edge("a", "b")
builder.add_edge("a", "c")

# 扇入到 D
builder.add_edge("b", "d")
builder.add_edge("c", "d")
```

**执行顺序**：
```
Super-step 1: A 执行
Super-step 2: B 和 C 并行执行
Super-step 3: D 执行（等待 B 和 C 完成）
```

### 异步支持

```python
async def async_node(state: State):
    result = await llm.ainvoke(state["messages"])
    return {"messages": [result]}

builder = StateGraph(State).add_node("async_node", async_node)
graph = builder.compile()

# 异步调用
result = await graph.ainvoke({"messages": [input_message]})
```

### 运行时上下文

传递不属于状态的信息（如配置、依赖）：

```python
from dataclasses import dataclass

@dataclass
class ContextSchema:
    llm_provider: str = "openai"
    db_connection: str = "postgresql://..."

graph = StateGraph(State, context_schema=ContextSchema)

# 调用时传递上下文
result = graph.invoke(
    inputs,
    context={"llm_provider": "anthropic"}
)

# 在节点中访问
def node(state: State, runtime: Runtime[ContextSchema]):
    provider = runtime.context.llm_provider
    # 使用 provider
```

**使用场景**：
- 模型选择
- 数据库连接
- API 密钥
- 环境配置

### 图迁移

LangGraph 支持图定义的迁移：

**完全支持**：
- ✅ 添加新节点
- ✅ 添加新边
- ✅ 修改边的逻辑
- ✅ 添加/删除状态键

**部分支持**：
- ⚠️ 重命名节点（仅对未中断的线程）
- ⚠️ 删除节点（仅对未中断的线程）

**注意事项**：
- 重命名状态键会丢失现有数据
- 类型不兼容的更改可能导致错误

---

## 实用技巧

### 可视化图

**Mermaid 语法**
```python
print(graph.get_graph().draw_mermaid())
```

**PNG 图片**
```python
from IPython.display import Image, display

image = graph.get_graph().draw_mermaid_png()
display(Image(image))
```

### 调试技巧

**1. 打印状态**
```python
def debug_node(state: State):
    print(f"当前状态: {state}")
    return {}
```

**2. 记录执行路径**
```python
class State(TypedDict):
    path: Annotated[list[str], operator.add]

def node_a(state: State):
    return {"path": ["node_a"]}
```

**3. 使用递归限制**
```python
# 快速失败，避免长时间等待
graph.invoke(input, config={"recursion_limit": 5})
```

### 性能优化

**1. 使用节点缓存**
```python
builder.add_node(
    "expensive_llm_call",
    llm_node,
    cache_policy=CachePolicy(ttl=300)
)
```

**2. 并行化独立任务**
```python
# 从同一节点扇出
builder.add_edge("start", "task_1")
builder.add_edge("start", "task_2")
builder.add_edge("start", "task_3")
```

**3. 使用异步**
```python
async def fast_node(state: State):
    results = await asyncio.gather(
        api_call_1(),
        api_call_2(),
        api_call_3()
    )
    return {"results": results}
```

### 错误处理

**1. 节点级重试**
```python
builder.add_node(
    "api_node",
    call_api,
    retry_policy=RetryPolicy(max_attempts=3)
)
```

**2. 错误路由**
```python
def error_handler(state: State) -> Literal["retry", "fallback", END]:
    if state.get("error"):
        if state["retry_count"] < 3:
            return "retry"
        return "fallback"
    return END
```

**3. 使用 try-except**
```python
def safe_node(state: State):
    try:
        result = risky_operation(state)
        return {"result": result}
    except Exception as e:
        return {"error": str(e), "retry_count": state.get("retry_count", 0) + 1}
```

### 最佳实践

**1. 状态设计**
- 保持状态扁平化
- 使用 Reducer 处理列表和累加
- 为可选字段提供默认值

**2. 节点设计**
- 单一职责原则
- 保持节点函数纯净（无副作用）
- 返回明确的状态更新

**3. 边设计**
- 条件边逻辑简单明确
- 覆盖所有可能的路由情况
- 使用类型提示确保类型安全

**4. 测试**
- 单独测试节点函数
- 测试条件边的所有分支
- 使用小的递归限制快速失败

---

## 快速参考

### 常用导入

```python
from typing_extensions import TypedDict
from typing import Annotated, Literal
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send, Command
from langgraph.cache.memory import InMemoryCache
from langgraph.types import CachePolicy, RetryPolicy
import operator
```

### 基本模板

```python
# 1. 定义状态
class State(TypedDict):
    input: str
    output: str

# 2. 定义节点
def my_node(state: State):
    return {"output": process(state["input"])}

# 3. 构建图
builder = StateGraph(State)
builder.add_node("my_node", my_node)
builder.add_edge(START, "my_node")
builder.add_edge("my_node", END)

# 4. 编译
graph = builder.compile()

# 5. 执行
result = graph.invoke({"input": "hello"})
```

---

## 总结

LangGraph Graph API 提供了构建复杂工作流的强大能力：

- **状态管理**：灵活的状态定义和 Reducer 机制
- **节点系统**：支持缓存、重试、延迟执行
- **控制流**：普通边、条件边、Send API、Command
- **高级特性**：循环、并行、异步、子图
- **开发体验**：可视化、调试、迁移支持

掌握这些概念和技巧，你就能构建出高效、可维护的 LangGraph 应用。
