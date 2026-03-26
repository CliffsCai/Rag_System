# LangGraph 工作流模式完整指南

## 目录
1. [Graph API 基础](#graph-api-基础)
2. [模式选择决策树](#模式选择决策树)
3. [提示链模式](#1-提示链模式-prompt-chaining)
4. [并行化模式](#2-并行化模式-parallelization)
5. [路由模式](#3-路由模式-routing)
6. [协调器-工作者模式](#4-协调器-工作者模式-orchestrator-worker)
7. [评估器-优化器模式](#5-评估器-优化器模式-evaluator-optimizer)
8. [模式对比表](#模式对比表)
9. [模式组合使用](#模式组合使用)

---

## Graph API 基础

在深入了解工作流模式之前，理解 LangGraph 的 Graph API 基础概念很重要。

### 核心组件

**StateGraph**：构建图的主要接口
```python
from langgraph.graph import StateGraph, START, END

builder = StateGraph(State)
graph = builder.compile()
```

**状态 (State)**：节点间共享的数据结构
- 使用 TypedDict (Python) 或 Zod Schema (JavaScript) 定义
- 支持 Reducers 处理多节点更新同一键的情况

**节点 (Nodes)**：执行计算的函数
- 接收状态，返回状态更新
- 支持缓存、重试、延迟执行

**边 (Edges)**：控制执行流程
- 普通边：固定连接
- 条件边：动态路由
- Send API：动态创建节点实例

### 关键特性

**Reducers（状态合并）**
```python
from typing import Annotated
import operator

class State(TypedDict):
    # 列表累加
    results: Annotated[list, operator.add]
```

**条件边（动态路由）**
```python
def route_logic(state: State) -> str:
    return "next_node" if state["condition"] else END

builder.add_conditional_edges("current_node", route_logic)
```

**Send API（Map-Reduce）**
```python
from langgraph.types import Send

def distribute(state: State):
    return [Send("worker", {"task": t}) for t in state["tasks"]]

builder.add_conditional_edges("coordinator", distribute, ["worker"])
```

**Command（控制流 + 状态更新）**
```python
from langgraph.graph import Command

def node(state: State) -> Command:
    return Command(
        update={"result": "data"},
        goto="next_node"
    )
```

### 执行模型

LangGraph 基于 Pregel 模型，使用 super-step 执行：
1. 并行执行所有可执行节点
2. 收集状态更新
3. 应用 Reducers 合并更新
4. 继续下一个 super-step

### 更多详情

完整的 Graph API 文档请参考：[LangGraph Graph API 完整指南](./langgraph-api-guide.md)

该文档详细介绍：
- 状态管理（多模式 Schema、Reducers、MessagesState）
- 节点详解（缓存、重试、延迟执行）
- 边与控制流（条件边、Send API、Command）
- 高级特性（循环、异步、运行时上下文）
- 实用技巧（可视化、调试、性能优化）

---

## 模式选择决策树

```
任务需要多次迭代改进？
├─ 是 → 评估器-优化器模式
└─ 否 → 继续判断
    │
    任务需要分解成多个子任务？
    ├─ 是 → 协调器-工作者模式
    └─ 否 → 继续判断
        │
        需要根据输入选择不同处理路径？
        ├─ 是 → 路由模式
        └─ 否 → 继续判断
            │
            多个独立任务可以同时执行？
            ├─ 是 → 并行化模式
            └─ 否 → 提示链模式
```

---

## 1. 提示链模式 (Prompt Chaining)

### 核心定义
按顺序执行一系列提示，每个步骤的输出作为下一个步骤的输入，形成线性处理流程。

### 关键特征
- **顺序执行**：节点按固定顺序依次执行
- **状态传递**：每个节点更新状态，传递给下一个节点
- **可选分支**：支持条件边，根据状态决定下一步
- **单线程**：同一时间只执行一个节点

### 典型应用场景
1. **内容生成与优化**：生成文本 → 检查质量 → 改进 → 润色
2. **数据处理管道**：提取数据 → 清洗 → 转换 → 验证
3. **多步推理**：问题分析 → 制定计划 → 执行步骤 → 总结结果
4. **文档处理**：解析文档 → 提取关键信息 → 结构化 → 生成摘要
5. **代码生成流程**：理解需求 → 设计架构 → 生成代码 → 测试验证

### 实现要点

#### 状态定义
```python
class State(TypedDict):
    input: str           # 初始输入
    intermediate: str    # 中间结果
    output: str         # 最终输出
    needs_improvement: bool  # 控制分支的标志
```

#### 节点函数结构
```python
def step_1(state: State):
    """第一步处理"""
    result = llm.invoke(f"处理: {state['input']}")
    return {"intermediate": result.content}

def step_2(state: State):
    """第二步处理"""
    result = llm.invoke(f"进一步处理: {state['intermediate']}")
    return {"output": result.content}
```

#### 边连接逻辑
```python
# 固定边：按顺序连接
workflow_builder.add_edge(START, "step_1")
workflow_builder.add_edge("step_1", "step_2")

# 条件边：根据状态决定路径
def should_continue(state: State):
    return "improve" if state["needs_improvement"] else "finish"

workflow_builder.add_conditional_edges(
    "step_2",
    should_continue,
    {"improve": "step_1", "finish": END}
)
```

### 何时使用
- ✅ 任务有明确的执行顺序
- ✅ 每步依赖前一步的结果
- ✅ 需要在中间步骤做决策
- ❌ 多个步骤可以并行执行
- ❌ 需要动态决定执行哪些步骤

### 注意事项
- 避免链条过长（建议 ≤ 5 步），否则考虑拆分
- 确保每个节点的输出格式符合下一个节点的输入要求
- 使用条件边时，确保所有可能的返回值都有对应的路由

---

## 2. 并行化模式 (Parallelization)

### 核心定义
同时执行多个独立的任务，然后聚合所有结果，适用于可以并发处理的场景。

### 关键特征
- **并发执行**：多个节点同时启动
- **独立任务**：各节点之间无依赖关系
- **结果聚合**：所有并行任务完成后统一处理
- **性能优化**：显著减少总执行时间

### 典型应用场景
1. **多角度分析**：从技术、商业、用户等多个角度分析同一问题
2. **多模型对比**：同时调用多个 LLM 获取不同回答，比较结果
3. **批量数据处理**：对多个数据项执行相同操作
4. **多源信息检索**：同时从多个数据源查询信息
5. **A/B 测试**：并行测试不同的提示或参数配置

### 实现要点

#### 状态定义
```python
class State(TypedDict):
    input: str              # 共享输入
    result_1: str           # 任务1结果
    result_2: str           # 任务2结果
    result_3: str           # 任务3结果
    aggregated: str         # 聚合结果
```

#### 并行节点结构
```python
def parallel_task_1(state: State):
    """并行任务1"""
    result = llm.invoke(f"角度1: {state['input']}")
    return {"result_1": result.content}

def parallel_task_2(state: State):
    """并行任务2"""
    result = llm.invoke(f"角度2: {state['input']}")
    return {"result_2": result.content}

def aggregator(state: State):
    """聚合所有结果"""
    combined = f"{state['result_1']}\n{state['result_2']}\n{state['result_3']}"
    return {"aggregated": combined}
```

#### 并行边配置
```python
# 从 START 到多个节点：触发并行执行
workflow_builder.add_edge(START, "parallel_task_1")
workflow_builder.add_edge(START, "parallel_task_2")
workflow_builder.add_edge(START, "parallel_task_3")

# 所有并行任务都连接到聚合器
workflow_builder.add_edge("parallel_task_1", "aggregator")
workflow_builder.add_edge("parallel_task_2", "aggregator")
workflow_builder.add_edge("parallel_task_3", "aggregator")

workflow_builder.add_edge("aggregator", END)
```

### 何时使用
- ✅ 多个任务相互独立，无依赖关系
- ✅ 需要从多个角度处理同一输入
- ✅ 需要提高处理速度
- ✅ 需要对比多个结果
- ❌ 任务之间有依赖关系
- ❌ 需要根据某个任务结果决定是否执行其他任务

### 注意事项
- 确保并行任务真正独立，不共享可变状态
- 聚合器必须等待所有并行任务完成
- 考虑并行任务的资源消耗（API 调用限制、成本等）
- 处理并行任务中的错误情况

---

## 3. 路由模式 (Routing)

### 核心定义
根据输入内容或中间结果，动态选择执行路径，将请求路由到最合适的处理节点。

### 关键特征
- **动态分支**：运行时决定执行路径
- **路由节点**：专门的节点负责分类决策
- **多路径**：支持多个互斥的执行分支
- **结构化输出**：使用 Pydantic 模型确保路由决策的准确性

### 典型应用场景
1. **问题分类处理**：根据问题类型（技术/商业/法律）路由到专业处理器
2. **意图识别**：识别用户意图后执行相应操作
3. **语言检测**：根据输入语言选择对应的处理流程
4. **优先级路由**：根据任务优先级选择不同的处理策略
5. **专家系统**：根据问题领域路由到对应的专家模型

### 实现要点

#### 状态定义
```python
class State(TypedDict):
    input: str          # 原始输入
    category: str       # 路由决策结果
    output: str         # 最终输出
```

#### 路由决策模型
```python
from pydantic import BaseModel, Field
from typing import Literal

class RouteDecision(BaseModel):
    category: Literal["type_a", "type_b", "type_c"] = Field(
        description="输入的分类类型"
    )

# 使用结构化输出
router_llm = llm.with_structured_output(RouteDecision)
```

#### 路由节点
```python
def router(state: State):
    """路由决策节点"""
    decision = router_llm.invoke(f"分类这个输入: {state['input']}")
    return {"category": decision.category}

def handler_a(state: State):
    """处理类型 A"""
    result = llm.invoke(f"作为A类型处理: {state['input']}")
    return {"output": result.content}

def handler_b(state: State):
    """处理类型 B"""
    result = llm.invoke(f"作为B类型处理: {state['input']}")
    return {"output": result.content}
```

#### 条件边配置
```python
def route_decision(state: State):
    """返回路由目标"""
    return state["category"]

workflow_builder.add_edge(START, "router")
workflow_builder.add_conditional_edges(
    "router",
    route_decision,
    {
        "type_a": "handler_a",
        "type_b": "handler_b",
        "type_c": "handler_c"
    }
)

# 所有处理器都连接到 END
workflow_builder.add_edge("handler_a", END)
workflow_builder.add_edge("handler_b", END)
workflow_builder.add_edge("handler_c", END)
```

### 何时使用
- ✅ 不同类型的输入需要不同的处理逻辑
- ✅ 需要根据内容特征选择处理策略
- ✅ 有明确的分类标准
- ✅ 各个处理分支相互独立
- ❌ 所有输入都用相同方式处理
- ❌ 需要执行多个分支（应使用并行化）

### 注意事项
- 使用结构化输出确保路由决策的可靠性
- 确保条件边的映射覆盖所有可能的路由结果
- 路由节点应该轻量快速，避免复杂计算
- 考虑添加默认路由处理未知类型

---

## 4. 协调器-工作者模式 (Orchestrator-Worker)

### 核心定义
使用中央协调器分解任务并分配给多个工作者，工作者并行执行子任务，最后由协调器或合成器汇总结果。

### 关键特征
- **任务分解**：协调器将复杂任务拆分成子任务
- **动态工作者**：根据子任务数量动态创建工作者
- **并行执行**：工作者并行处理各自的子任务
- **结果合成**：将所有工作者的输出整合成最终结果

### 典型应用场景
1. **报告生成**：规划章节 → 并行撰写各章节 → 合成完整报告
2. **大规模数据处理**：分割数据集 → 并行处理各部分 → 合并结果
3. **多步骤项目**：制定计划 → 并行执行各任务 → 整合交付物
4. **研究综述**：确定研究方向 → 并行调研各方向 → 综合分析
5. **测试套件执行**：规划测试用例 → 并行执行测试 → 汇总测试报告

### 实现要点

#### 状态定义
```python
from typing import Annotated
from operator import add

class State(TypedDict):
    topic: str                                      # 主题/任务
    subtasks: list[dict]                           # 子任务列表
    completed: Annotated[list, add]                # 完成的结果（累加）
    final_output: str                              # 最终输出

class WorkerState(TypedDict):
    subtask: dict                                  # 单个子任务
    completed: Annotated[list, add]                # 工作者输出
```

#### 协调器节点
```python
from pydantic import BaseModel, Field

class Subtask(BaseModel):
    name: str = Field(description="子任务名称")
    description: str = Field(description="子任务描述")

class Plan(BaseModel):
    subtasks: list[Subtask] = Field(description="子任务列表")

planner = llm.with_structured_output(Plan)

def orchestrator(state: State):
    """协调器：规划子任务"""
    plan = planner.invoke(f"为这个任务制定计划: {state['topic']}")
    return {"subtasks": [s.dict() for s in plan.subtasks]}
```

#### 工作者节点
```python
def worker(state: WorkerState):
    """工作者：执行单个子任务"""
    result = llm.invoke(
        f"执行任务: {state['subtask']['name']}\n"
        f"描述: {state['subtask']['description']}"
    )
    return {"completed": [result.content]}
```

#### 合成器节点
```python
def synthesizer(state: State):
    """合成器：整合所有结果"""
    all_results = "\n\n---\n\n".join(state["completed"])
    return {"final_output": all_results}
```

#### 使用 Send API 动态分配工作者
```python
from langgraph.types import Send

def assign_workers(state: State):
    """为每个子任务分配一个工作者"""
    return [Send("worker", {"subtask": task}) for task in state["subtasks"]]

# 构建工作流
workflow_builder.add_edge(START, "orchestrator")
workflow_builder.add_conditional_edges(
    "orchestrator",
    assign_workers,
    ["worker"]
)
workflow_builder.add_edge("worker", "synthesizer")
workflow_builder.add_edge("synthesizer", END)
```

### 何时使用
- ✅ 任务可以分解成多个独立子任务
- ✅ 子任务可以并行执行
- ✅ 需要动态决定子任务数量
- ✅ 需要汇总多个结果
- ❌ 任务无法分解
- ❌ 子任务之间有强依赖关系

### 注意事项
- 使用 `Annotated[list, add]` 让多个工作者写入同一个状态键
- Send API 允许动态创建任意数量的工作者实例
- 确保工作者状态 (WorkerState) 包含必要的输入
- 合成器必须等待所有工作者完成
- 考虑工作者失败的处理策略

---

## 5. 评估器-优化器模式 (Evaluator-Optimizer)

### 核心定义
生成器创建输出，评估器检查质量，如果不满足标准则提供反馈并重新生成，形成迭代改进循环。

### 关键特征
- **迭代循环**：生成 → 评估 → 改进 → 再评估
- **质量控制**：明确的评估标准和反馈机制
- **自动优化**：根据反馈自动改进输出
- **终止条件**：满足标准或达到最大迭代次数

### 典型应用场景
1. **内容质量优化**：生成文本 → 检查质量 → 根据反馈改进
2. **翻译优化**：初译 → 评估准确性 → 改进翻译
3. **代码生成与修复**：生成代码 → 测试 → 修复错误
4. **创意内容生成**：生成创意 → 评估创意性 → 优化
5. **答案精炼**：生成答案 → 检查完整性 → 补充细节

### 实现要点

#### 状态定义
```python
class State(TypedDict):
    input: str              # 原始输入
    output: str             # 当前输出
    feedback: str           # 评估反馈
    quality: str            # 质量评级
    iteration: int          # 迭代次数
```

#### 评估模型
```python
from typing import Literal

class Evaluation(BaseModel):
    quality: Literal["excellent", "good", "needs_improvement"] = Field(
        description="输出质量评级"
    )
    feedback: str = Field(
        description="改进建议，仅在需要改进时提供"
    )

evaluator_llm = llm.with_structured_output(Evaluation)
```

#### 生成器节点
```python
def generator(state: State):
    """生成或改进输出"""
    if state.get("feedback"):
        # 根据反馈改进
        prompt = f"改进这个输出: {state['output']}\n反馈: {state['feedback']}"
    else:
        # 初次生成
        prompt = f"生成输出: {state['input']}"
    
    result = llm.invoke(prompt)
    iteration = state.get("iteration", 0) + 1
    return {"output": result.content, "iteration": iteration}
```

#### 评估器节点
```python
def evaluator(state: State):
    """评估输出质量"""
    evaluation = evaluator_llm.invoke(f"评估这个输出: {state['output']}")
    return {
        "quality": evaluation.quality,
        "feedback": evaluation.feedback
    }
```

#### 循环控制
```python
def should_continue(state: State):
    """决定是继续改进还是结束"""
    # 检查质量
    if state["quality"] in ["excellent", "good"]:
        return "accept"
    
    # 检查迭代次数限制
    if state.get("iteration", 0) >= 3:
        return "accept"  # 达到最大迭代次数
    
    return "improve"

workflow_builder.add_edge(START, "generator")
workflow_builder.add_edge("generator", "evaluator")
workflow_builder.add_conditional_edges(
    "evaluator",
    should_continue,
    {
        "accept": END,
        "improve": "generator"
    }
)
```

### 何时使用
- ✅ 输出有明确的质量标准
- ✅ 可以通过迭代改进质量
- ✅ 需要自动化的质量控制
- ✅ 反馈可以指导改进方向
- ❌ 无法定义清晰的评估标准
- ❌ 一次生成就能满足要求
- ❌ 反馈无法有效改进输出

### 注意事项
- 设置最大迭代次数防止无限循环
- 评估标准要明确且可执行
- 反馈要具体，能指导改进
- 考虑使用结构化输出确保评估一致性
- 记录迭代历史便于调试和分析

---

## 模式对比表

| 特性 | 提示链 | 并行化 | 路由 | 协调器-工作者 | 评估器-优化器 |
|------|--------|--------|------|---------------|---------------|
| **执行方式** | 顺序 | 并行 | 条件分支 | 分解+并行 | 循环迭代 |
| **节点依赖** | 强依赖 | 无依赖 | 互斥分支 | 部分依赖 | 循环依赖 |
| **适用任务** | 流程化任务 | 独立任务 | 分类任务 | 复杂任务 | 优化任务 |
| **执行时间** | 累加 | 最长任务 | 单路径 | 最长子任务 | 多次迭代 |
| **复杂度** | 低 | 中 | 中 | 高 | 中 |
| **灵活性** | 低 | 低 | 中 | 高 | 中 |
| **结果数量** | 1个 | 多个聚合 | 1个 | 多个合成 | 1个优化 |
| **典型节点数** | 3-5 | 3-10 | 4-8 | 5-15 | 2-3 |

---

## 模式组合使用

### 1. 路由 + 提示链
**场景**：不同类型的输入需要不同的处理流程

```
输入 → 路由器 → 类型A处理链（步骤1→2→3）
              → 类型B处理链（步骤1→2→3）
              → 类型C处理链（步骤1→2→3）
```

### 2. 协调器-工作者 + 评估器-优化器
**场景**：每个子任务都需要质量控制

```
协调器 → 工作者1（生成→评估→改进）
      → 工作者2（生成→评估→改进）
      → 工作者3（生成→评估→改进）
      → 合成器
```

### 3. 并行化 + 路由
**场景**：并行获取多个结果后，根据结果选择处理方式

```
输入 → 并行任务1 → 聚合器 → 路由器 → 处理A
    → 并行任务2 ↗              → 处理B
    → 并行任务3 ↗
```

### 4. 提示链 + 并行化
**场景**：流程中某一步需要并行处理

```
步骤1 → 步骤2 → 并行任务A → 聚合 → 步骤3 → 步骤4
              → 并行任务B ↗
              → 并行任务C ↗
```

### 5. 完整复杂工作流
**场景**：企业级应用

```
输入 → 路由器 → 类型A → 协调器 → 工作者1（评估-优化）→ 合成 → 输出
              → 类型B → 提示链 → 步骤1→2→3 → 输出
              → 类型C → 并行处理 → 聚合 → 输出
```

---

## 快速选择指南

### 按任务特征选择

| 任务特征 | 推荐模式 |
|----------|----------|
| 有明确的执行顺序 | 提示链 |
| 多个独立任务 | 并行化 |
| 需要分类处理 | 路由 |
| 复杂任务需要分解 | 协调器-工作者 |
| 需要迭代改进 | 评估器-优化器 |
| 多步骤+分类 | 路由+提示链 |
| 分解+质量控制 | 协调器-工作者+评估器-优化器 |

### 按性能需求选择

| 性能需求 | 推荐模式 |
|----------|----------|
| 最快速度 | 并行化 |
| 最高质量 | 评估器-优化器 |
| 最灵活 | 协调器-工作者 |
| 最简单 | 提示链 |
| 最智能 | 路由 |

---

## 实现检查清单

### 所有模式通用
- [ ] 定义清晰的 State 类型
- [ ] 每个节点函数返回状态更新字典
- [ ] 正确连接 START 和 END
- [ ] 编译工作流后再调用
- [ ] 处理可能的错误情况

### 提示链特定
- [ ] 确保节点顺序正确
- [ ] 条件边覆盖所有可能情况
- [ ] 避免链条过长

### 并行化特定
- [ ] 确保任务真正独立
- [ ] 所有并行节点连接到聚合器
- [ ] 聚合器处理所有结果

### 路由特定
- [ ] 使用结构化输出定义路由决策
- [ ] 条件边映射覆盖所有路由结果
- [ ] 所有分支最终都连接到 END

### 协调器-工作者特定
- [ ] 使用 Annotated[list, add] 累加结果
- [ ] 定义 WorkerState 类型
- [ ] 使用 Send API 动态分配工作者
- [ ] 合成器整合所有工作者输出

### 评估器-优化器特定
- [ ] 定义明确的评估标准
- [ ] 设置最大迭代次数
- [ ] 反馈信息具体可执行
- [ ] 循环控制逻辑正确

---

## Graph API 高级技巧在模式中的应用

### 1. 使用节点缓存优化性能

在任何模式中，对于重复或昂贵的操作，使用节点缓存：

```python
from langgraph.types import CachePolicy
from langgraph.cache.memory import InMemoryCache

# 在提示链中缓存 LLM 调用
builder.add_node(
    "expensive_llm_call",
    llm_node,
    cache_policy=CachePolicy(ttl=300)
)

graph = builder.compile(cache=InMemoryCache())
```

### 2. 使用重试策略提高可靠性

特别适用于路由模式和协调器-工作者模式：

```python
from langgraph.types import RetryPolicy

# 为路由节点添加重试
builder.add_node(
    "router",
    router_function,
    retry_policy=RetryPolicy(max_attempts=3)
)
```

### 3. 使用 Command 简化复杂逻辑

在评估器-优化器模式中特别有用：

```python
from langgraph.graph import Command

def evaluator(state: State) -> Command:
    evaluation = evaluate(state["output"])
    
    if evaluation.quality == "good":
        return Command(
            update={"final_result": state["output"]},
            goto=END
        )
    else:
        return Command(
            update={"feedback": evaluation.feedback},
            goto="generator"
        )
```

### 4. 使用递归限制防止无限循环

在评估器-优化器和提示链循环中必须设置：

```python
from langgraph.errors import GraphRecursionError

try:
    result = graph.invoke(
        input_data,
        config={"recursion_limit": 10}
    )
except GraphRecursionError:
    # 处理超出限制的情况
    pass
```

### 5. 使用运行时上下文传递配置

在所有模式中传递非状态信息：

```python
from dataclasses import dataclass
from langgraph.runtime import Runtime

@dataclass
class ContextSchema:
    model_name: str = "gpt-4"
    temperature: float = 0.7

graph = StateGraph(State, context_schema=ContextSchema)

# 在节点中访问
def node(state: State, runtime: Runtime[ContextSchema]):
    model = runtime.context.model_name
    # 使用配置
```

### 6. 使用延迟执行优化 Map-Reduce

在协调器-工作者模式中优化聚合：

```python
# 延迟聚合器执行，直到所有工作者完成
builder.add_node("aggregator", aggregate_results, defer=True)
```

---

## 相关资源

### 文档链接

- **[LangGraph Graph API 完整指南](./langgraph-api-guide.md)**
  - 状态管理详解
  - 节点和边的高级用法
  - 性能优化技巧
  - 调试和可视化

### 学习路径

1. **初学者**：从提示链模式开始，理解基本的状态、节点、边概念
2. **进阶**：学习并行化和路由模式，掌握条件边和 Reducers
3. **高级**：掌握协调器-工作者模式，使用 Send API 和 Command
4. **专家**：组合多种模式，优化性能，处理复杂场景

### 实践建议

1. **先简单后复杂**：从最简单的模式开始，逐步增加复杂度
2. **可视化验证**：使用 `graph.get_graph().draw_mermaid_png()` 验证图结构
3. **单元测试**：分别测试节点函数和条件边逻辑
4. **性能监控**：使用缓存和并行化优化性能
5. **错误处理**：添加重试策略和递归限制

---

## 总结

选择合适的工作流模式是构建高效 LangGraph 应用的关键：

1. **从简单开始**：优先考虑提示链，除非有明确理由使用其他模式
2. **按需组合**：复杂场景可以组合多种模式
3. **性能优化**：能并行就并行，能路由就不要全部执行
4. **质量保证**：关键输出使用评估器-优化器模式
5. **任务分解**：复杂任务使用协调器-工作者模式
6. **善用 API**：利用 Graph API 的高级特性（缓存、重试、Command 等）

记住：没有最好的模式，只有最适合的模式。根据具体任务特征和需求选择或组合使用这些模式。

### 下一步

- 阅读 [LangGraph Graph API 完整指南](./langgraph-api-guide.md) 深入了解底层 API
- 实践各种模式，从简单示例开始
- 尝试组合不同模式解决复杂问题
- 优化性能，使用缓存、并行和异步
