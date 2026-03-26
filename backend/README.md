# Knowledge Agent Backend

> 文档状态（2026-03）：本文件已按当前实现更新。若与历史描述冲突，请以 `../PROJECT_STRUCTURE_MASTER.md` 与 `app/`、`agents/` 下代码为准。

Professional LangGraph-based RAG system for enterprise knowledge base Q&A.

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and configure your API keys:

```bash
cp .env.example .env
```

Edit `.env`:
```
DASHSCOPE_API_KEY=your_api_key_here
```

### 3. Run API Server

```bash
python main.py
```

The server will start at `http://localhost:8000`

**Note**: `main.py` is the entry point. It imports and runs the FastAPI app from `app/main.py`.

### 4. Test the API

```bash
# Health check
curl http://localhost:8000/api/v1/

# Chat endpoint
curl -X POST http://localhost:8000/api/v1/chat/ \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "你好"}], "model": "qwen-plus"}'

# Knowledge endpoint
curl -X POST http://localhost:8000/api/v1/knowledge/ \
  -H "Content-Type: application/json" \
  -d '{"query": "什么是 LangGraph？", "model": "qwen-plus"}'
```

## Project Structure

```
backend/
├── main.py                   # Main entry point
├── requirements.txt          # Python dependencies
├── .env.example              # Environment variables template
├── langgraph.json            # LangGraph configuration
├── app/                      # FastAPI application layer
│   ├── main.py               # App factory and lifespan
│   ├── api/v1/               # chat/knowledge/system/documents/admin
│   ├── core/config.py        # Settings and constants
│   └── models/               # Request/response models
└── agents/                   # LangGraph agents and graphs
  ├── preload.py            # Graph preloader
  ├── supervisor/           # Supervisor chat graph
  ├── knowledge/            # Knowledge RAG graph
  ├── document_upload/      # Document upload graph
  └── specialized/          # email/search specialists
```

## Architecture

### Enhanced Knowledge Workflow (Current)

```
START
  ↓
query_rewrite     - Rewrite and normalize query
  ↓
query_classify    - Classify single-doc vs multi-doc intent
  ↓
determine_retrieval_strategy - Choose retrieval strategy
  ↓
[single_doc_retrieve OR multi_doc_retrieve]
  ↓
filter_chunks     - Filter by relevance score
  ↓
rerank_chunks     - Reorder by relevance
  ↓
relevance_filter  - LLM relevance refinement
  ↓
generate_answer   - Generate answer with MCP tools
  ↓
check_quality     - Assess quality and apply fallback (conditional)
  ↓
finalize_metrics  - Calculate performance metrics
  ↓
END
```

### Key Features

- **Complete RAG Pipeline**: 7 specialized nodes for high-quality Q&A
- **MCP Tools**: Email, web search, database query capabilities
- **State Management**: 40+ fields tracking all workflow data
- **Quality Control**: Built-in quality checks and fallback
- **Performance Metrics**: Duration, tokens, cost tracking
- **Production Ready**: Error handling, logging, type hints

## API Endpoints

### GET /

Health check and system information

**Response:**
```json
{
  "status": "ok",
  "architecture": "Solution 3: Complete Knowledge Agent with Full Workflow",
  "workflow": "query_analysis → retrieve → filter → rerank → generate → quality_check → metrics",
  "models": ["qwen-turbo", "qwen-plus", "qwen-max"],
  "mcp_tools": ["send_email", "web_search", "query_database"]
}
```

### GET /models

List supported models

**Response:**
```json
{
  "models": ["qwen-turbo", "qwen-plus", "qwen-max"],
  "default": "qwen-turbo"
}
```

### POST /api/v1/chat/

Multi-turn conversation endpoint

**Request:**
```json
{
  "messages": [
    {"role": "user", "content": "你好！"}
  ],
  "model": "qwen-plus",
  "temperature": 0.0
}
```

**Response:**
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

### POST /api/v1/knowledge/

Knowledge base Q&A endpoint

**Request:**
```json
{
  "query": "什么是 LangGraph？",
  "session_id": "user_123",
  "model": "qwen-plus"
}
```

**Response:**
```json
{
  "answer": "LangGraph 是一个用于构建有状态的多 Agent 应用的框架...",
  "confidence": 0.95,
  "sources": [...],
  "model": "qwen-plus",
  "error": null
}
```

## Development

### Adding a New Node

1. Create file in `agents/knowledge/nodes/`
2. Implement node function: `def node_name(state: KnowledgeAgentState) -> Dict[str, Any]`
3. Add to `agents/knowledge/nodes/__init__.py`
4. Register in `agents/knowledge/graph.py`

### Adding a New Tool

1. Add tool function in `agents/knowledge/tools/mcp_tools.py` using `@tool` decorator
2. Add to `create_mcp_tools()` return list
3. Tool will be automatically available to LLM

### Replacing Mock Retrieval

1. Implement real retrieval in `agents/knowledge/services/retrieval.py`
2. Update `agents/knowledge/nodes/*retrieve*.py` to use real service
3. Remove MOCK data generation

## Configuration

### Environment Variables

- `DASHSCOPE_API_KEY`: Alibaba Cloud DashScope API key (required)
- `DASHSCOPE_BASE_URL`: API base URL (default: https://dashscope.aliyuncs.com/compatible-mode/v1)
- `DEFAULT_MODEL`: Default LLM model (default: qwen-turbo)
- `TEMPERATURE`: Generation temperature (default: 0.0)
- `MAX_RETRIES`: Max retry attempts (default: 3)
- `TIMEOUT`: Request timeout in seconds (default: 60)
- `SSL_VERIFY`: Enable SSL verification (default: false for development)

### Supported Models

- `qwen-turbo`: Fast, cost-effective
- `qwen-plus`: Balanced performance and cost (recommended)
- `qwen-max`: Highest quality

## Current Status

### Implemented ✅

- Enhanced Knowledge workflow with adaptive retrieval routing
- MCP tools integration (mock)
- FastAPI server with all endpoints
- State management (40+ fields)
- Quality control and fallback
- Performance metrics
- Error handling and logging

### TODO ⏳

- Connect to real knowledge base (Bailian ADB)
- Implement real MCP tools (email, search, database)
- Add authentication and authorization
- Implement caching
- Add streaming support
- Performance optimization

## Documentation

- [Knowledge Agent Documentation](agents/knowledge/README.md) - Detailed agent documentation
- [Project Structure Master](../PROJECT_STRUCTURE_MASTER.md) - Single source of truth

## License

Proprietary - Internal Use Only
