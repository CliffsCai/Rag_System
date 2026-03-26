# Knowledge Agent

> 文档状态（2026-03）：当前实现为增强工作流（非旧版固定 7 节点线性流程）。以 `graph.py`、`state.py` 与上层 `PROJECT_STRUCTURE_MASTER.md` 为准。

Professional LangGraph-based RAG system for enterprise knowledge base Q&A.

## Architecture

This is a production-ready implementation following LangGraph best practices with a clean, modular structure.

### Enhanced Workflow (Current)

```
START
  ↓
query_rewrite     - Rewrite and normalize query
  ↓
query_classify    - Classify single-doc vs multi-doc query
  ↓
determine_retrieval_strategy - Choose keyword/hybrid strategy
  ↓
[single_doc_retrieve OR multi_doc_retrieve]
  ↓
filter_chunks     - Filter by relevance score
  ↓
rerank_chunks     - Reorder by relevance
  ↓
relevance_filter  - LLM-based relevance refinement
  ↓
generate_answer   - Generate answer with MCP tools
  ↓
check_quality     - Assess quality and apply fallback (conditional)
  ↓
finalize_metrics  - Calculate performance metrics
  ↓
END
```

## Directory Structure

```
agents/knowledge/
├── __init__.py           # Package exports
├── graph.py              # LangGraph workflow definition
├── state.py              # State management (TypedDict)
├── nodes/                # Workflow nodes (one file per node)
│   ├── __init__.py
│   ├── query_rewrite.py
│   ├── query_classify.py
│   ├── determine_retrieval_strategy.py
│   ├── single_doc_retrieve.py
│   ├── multi_doc_retrieve.py
│   ├── filter.py
│   ├── rerank.py
│   ├── relevance_filter.py
│   ├── generate.py
│   ├── quality_check.py
│   └── metrics.py
├── tools/                # MCP tools
│   ├── __init__.py
│   └── mcp_tools.py
├── services/             # External service integrations
│   ├── __init__.py
│   ├── retrieval.py      # Bailian ADB integration (TODO)
│   ├── rerank.py         # Reranking service (TODO)
│   └── llm.py            # LLM service (TODO)
└── README.md             # This file
```

## Key Features

- **Modular Design**: Each node in a separate file for clarity
- **MCP Tools**: Email, web search, database query capabilities
- **Complete State**: 40+ fields tracking all workflow data
- **Quality Control**: Built-in quality checks and fallback
- **Performance Metrics**: Duration, tokens, cost tracking
- **Production Ready**: Error handling, logging, type hints

## Usage

```python
from knowledge_agent import knowledge_agent, create_initial_state, RAGConfig

# Create initial state
initial_state = create_initial_state(
    query="什么是 LangGraph？",
    user_id="user_123",
    session_id="session_456",
    config=RAGConfig(
        model="qwen-plus",
        retrieval_strategy="hybrid",
        enable_fallback=True
    )
)

# Run agent
result = knowledge_agent.invoke(initial_state, config={
    "configurable": {
        "model": "qwen-plus",
        "session_id": "session_456"
    }
})

# Access results
print(result["answer"])
print(result["confidence"])
print(result["sources"])
```

## Integration Points

### Current (MOCK)
- **Retrieval**: Returns mock documents
- **MCP Tools**: Print-only implementations

### Future (Production)
- **Retrieval**: Bailian ADB vector search
- **MCP Tools**: Real email/search/database integrations
- **Reranking**: Bailian reranking service
- **LLM**: Enhanced with streaming support

## Development

### Adding a New Node

1. Create file in `nodes/` directory
2. Implement node function with signature: `def node_name(state: KnowledgeAgentState) -> Dict[str, Any]`
3. Add to `nodes/__init__.py`
4. Register in `graph.py`

### Adding a New Tool

1. Add tool function in `tools/mcp_tools.py` using `@tool` decorator
2. Add to `create_mcp_tools()` return list
3. Tool will be automatically available to LLM

### Replacing Mock Retrieval

1. Implement real retrieval in `services/retrieval.py`
2. Update `nodes/retrieve.py` to use real service
3. Remove MOCK data generation

## Testing

```bash
# Run complete workflow test
python test_complete_agent.py

# Start API server
python backend/main.py
```

## Notes

- Current implementation uses MOCK data for retrieval
- MCP tools are placeholder implementations
- Ready for production knowledge base integration
- Follows LangGraph best practices and patterns
