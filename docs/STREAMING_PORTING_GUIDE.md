# 知识库问答 SSE 流式输出 — 改动范围与迁移步骤

本文档归纳本仓库中「RAG 知识库从一次性 JSON 改为 SSE 流式」的实现思路，便于你在**其他项目**中按相同模式落地。核心模式是：

1. **编排层**：LangGraph 在 `generate` 节点前 **interrupt**，先跑完检索与上下文拼装。  
2. **生成层**：用 **OpenAI 兼容接口**（千问 `compatible-mode/v1/chat/completions` + `stream: true`）在 **API 服务层** 流式读 token。  
3. **收尾层**：把完整（或已清洗）的文本写入 state 的 **`precomputed_answer`**，**`aupdate_state` + 第二次 `ainvoke(None)`** 走原图里的 `generate`（短路不调 LLM）→ `check_quality` → `finalize_metrics`，保证 **checkpoint / 会话库** 与非流式一致。  
4. **前端**：`fetch` + `ReadableStream` 解析 SSE；**同一条** assistant 气泡内先「思考动画」再 `v-html` 增量正文；注意 **CRLF、代理缓冲、Vue 响应式**。

---

## 一、后端改动范围

| 模块 | 文件（本仓库路径） | 作用 |
|------|-------------------|------|
| 配置 | `app/core/config.py` | `dashscope_base_url` 指向北京 OpenAI 兼容端点；可用环境变量 `DASHSCOPE_COMPATIBLE_BASE_URL` 覆盖。 |
| 状态 | `agents/knowledge/state.py` | `KnowledgeAgentState` 增加可选字段 **`precomputed_answer`**（`typing_extensions.NotRequired`），供流式完成后写回图状态。 |
| 图编译 | `agents/knowledge/graph.py` | `create_knowledge_agent(..., interrupt_before=None)`；流式用 **`interrupt_before=["generate_answer"]`**。 |
| Agent 入口 | `agents/knowledge/__init__.py` | 新增 **`get_knowledge_stream_prep_agent()`** 单例（与主 Agent 同 checkpointer，仅编译参数不同）。 |
| 生成节点 | `agents/knowledge/nodes/generate.py` | 抽出 **`prepare_generation_context`**（拼 messages、image_map、context 等）；**`generate_answer`** 若发现 `precomputed_answer` 则 **不调 DashScope**，直接组装 sources/confidence/AIMessage，并 **`precomputed_answer: None`** 清字段。 |
| 流式 HTTP | `agents/knowledge/openai_stream.py` | **`iter_openai_text_deltas`**：`AsyncOpenAI` + `stream=True`；DashScope 风格多模态 message → OpenAI `image_url`/`text` 片段。 |
| 业务层 | `app/services/knowledge_service.py` | **`stream_knowledge_qa_sse`** 异步生成器；**`_sse`**、**`_persist_conversation_messages`**、**`_load_kb_retrieval`**、**`_thoughts_from_state_values`**；非流式 `invoke_knowledge_qa` 可复用加载 KB 与持久化逻辑。 |
| 路由 | `app/api/v1/knowledge.py` | **`POST /knowledge/stream`** → `StreamingResponse`（`text/event-stream` + 禁用缓冲相关头）。 |
| 依赖 | `requirements.txt` | 已有 **`openai`** 即可（本仓库已包含）。 |

**不必改**（若另一项目结构不同，可等价替换）：Milvus、检索节点、`check_quality` / `finalize_metrics` 逻辑——只要保证「第二次 invoke 仍走同一套收尾」即可。

---

## 二、后端实施步骤（可照抄顺序）

### 步骤 1：OpenAI 兼容配置

- `base_url`：`https://dashscope.aliyuncs.com/compatible-mode/v1`（或国际站等，与 Key 区域一致）。  
- `api_key`：与现有 DashScope Key 相同。  
- 请求：`POST /chat/completions`，body 含 `model`、`messages`、`stream: true`，可选 `stream_options: { include_usage: true }`。

### 步骤 2：图支持 interrupt

- `graph.compile(..., interrupt_before=["generate_answer"])` **仅**用于「流式专用」编译实例；原 **`interrupt_before` 为空** 的实例继续服务 **`POST /knowledge` JSON** 非流式。  
- 两个实例 **共用同一 checkpointer、同一 `thread_id`**，状态 schema 必须一致。

### 步骤 3：generate 节点支持「预填答案」

- 在节点开头读取 `state.get("precomputed_answer")`。  
- 若非空：跳过所有 LLM 调用，用已有 **`prepare_generation_context`** 结果拼 **sources / confidence / image_map / AIMessage**，返回中带上 **`precomputed_answer: None`**，避免下一轮残留。  
- 若为空：保持原逻辑（本仓库仍用 `Generation.call` / `MultiModalConversation.call` 非流式）。

### 步骤 4：流式服务编排（核心顺序）

1. `await stream_prep_agent.ainvoke(initial_state, config)`  
   - 在 **`generate_answer` 前** 暂停（interrupt）。  
2. `snap = await stream_prep_agent.aget_state(config)`，取 **`snap.values`**。  
3. **`ctx = prepare_generation_context(values, config)`** → 得到 OpenAI 可用的 `messages`、`model_name`、`image_map` 等。  
4. **yield SSE `meta`**：`request_id`、`session_id`、`model`、`thoughts`、`sources`、`image_map`（与前端约定字段名）。  
5. **`async for` `iter_openai_text_deltas(ctx["messages"], ctx["model_name"])`**，每段 **yield `delta`**：`{ "text": "..." }`。  
6. 拼接全文后做与线上一致的 **占位符清洗**（如 `_sanitize_image_placeholders`）。  
7. **`await stream_prep_agent.aupdate_state(config, { "precomputed_answer": sanitized })`**  
8. **`await stream_prep_agent.ainvoke(None, config)`**（静态 interrupt 的 resume；若你使用的 LangGraph 版本要求 `Command`，以官方文档为准替换此步）。  
9. 再次 **`aget_state`** 取最终 **`answer` / `sources` / `confidence` / `image_map`**，**yield `done`**。  
10. **会话持久化**（若业务有）：用 **最终 `answer`** 写库，与原先非流式一致。

### 步骤 5：FastAPI 路由

- `StreamingResponse(async_gen(), media_type="text/event-stream")`。  
- 建议响应头：`Cache-Control: no-cache`、`Connection: keep-alive`、`X-Accel-Buffering: no`。  
- 请求体与非流式接口尽量 **同形**（便于前端切换）。

### 步骤 6：SSE 帧格式（与前端对齐）

每条事件推荐：

```text
event: meta
data: {"request_id":"...","session_id":"...","sources":[...],"image_map":{...},...}

event: delta
data: {"text":"..."}

event: done
data: {"answer":"...","sources":[...],"confidence":0.8,...}

event: error
data: {"message":"..."}
```

- `data` 行为 **单行 JSON**（避免解析器处理多行 data 的复杂度）。  
- 帧之间用 **空行 `\n\n`** 分隔（见下节「前端陷阱」）。

---

## 三、前端改动范围

| 区域 | 内容 |
|------|------|
| HTTP | 不用 axios 收 body；用 **`fetch` + `response.body.getReader()`**。 |
| 解析 | 累积 `buffer`；按 **`\\n\\n`** 切帧；**先把 `\\r\\n` 规范成 `\\n`**，避免代理改写换行导致永远切不出帧。 |
| 压缩 | `fetch` 头增加 **`Accept-Encoding: identity`**，减少「整包缓冲后再解压」。 |
| 代理 | Vite（或 Nginx）对 stream 路径转发时同样建议 **`Accept-Encoding: identity`**、`Accept: text/event-stream`。 |
| 流结束 | `reader.read()` **`done: true`** 后，再 **`TextDecoder` flush 一次**，并处理 **末尾不足 `\\n\\n` 的残留 buffer**。 |
| Vue | 流式更新 **必须写回 `messages.value[assistantIdx]`**（或 `splice` 替换），不要只改 **push 前的局部变量引用**，否则 DOM 不更新。 |
| UI | 知识库：**同一条** assistant 气泡内 **`_streamThinking`** 显示波浪动画；**首个 delta 到达后** 关动画、改 `v-html`；**不要**在 `loading` 时再画一条全局打字行（否则双气泡）。 |

---

## 四、迁移到「另一个项目」时的检查清单

- [ ] **LLM**：是否也能用 OpenAI 兼容 `chat.completions` 流式？若不能，需在「interrupt 之后」换你自己的流式客户端，但 **6～9 步顺序**不变。  
- [ ] **多模态**：用户图 + 文 message 格式是否在兼容接口下与 DashScope 字段一一映射。  
- [ ] **checkpoint**：resume 必须用 **相同 `thread_id`**；流式失败中途要想办法 **收尾或清理** 半完成 checkpoint（本仓库未做自动回滚，生产可加强）。  
- [ ] **`check_quality` / fallback**：流式阶段展示的是 **模型原文**；**`done` 与落库** 应以 **图跑完后的 `answer`** 为准（可能已被 fallback 替换）。  
- [ ] **占位符 / 安全**：流式过程中可只做 **占位符 → 图片** 的 map 替换；**非法占位符过滤**建议在 **全文收齐后** 做一次，与线上一致。  
- [ ] **兼容旧客户端**：保留原 **`POST /json`** 路由；流式用新路径 **`/stream`** 或 `Accept` 分流。  
- [ ] **超时**：流式请求时间更长，代理 / 客户端 **timeout** 需调大。

---

## 五、本仓库关键文件速查

```
backend/app/core/config.py          # dashscope_base_url
backend/app/api/v1/knowledge.py     # POST /knowledge/stream
backend/app/services/knowledge_service.py   # stream_knowledge_qa_sse, _sse
backend/agents/knowledge/graph.py   # interrupt_before
backend/agents/knowledge/__init__.py # get_knowledge_stream_prep_agent
backend/agents/knowledge/state.py     # precomputed_answer
backend/agents/knowledge/nodes/generate.py  # prepare_generation_context, 短路分支
backend/agents/knowledge/openai_stream.py   # OpenAI 流式
frontend/src/services/api.js        # knowledgeQueryStream
frontend/src/components/SimpleChat.vue      # 流式 UI、_streamThinking、双气泡处理
frontend/vite.config.js             # 代理 stream 头
```

按上述顺序在另一项目中建立「**interrupt → 外部队列流式 → precomputed → resume**」闭环，即可在不大改检索与收尾逻辑的前提下接入 SSE 流式输出。
