# -*- coding: utf-8 -*-
"""
Enterprise Knowledge Base QA Agent State Definition
Complete state management for production RAG system
"""

from typing_extensions import TypedDict, NotRequired
from typing import List, Dict, Any, Optional, Annotated
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import operator

# LangGraph 消息处理
from langgraph.graph import add_messages
from langchain_core.messages import BaseMessage
from app.core.config import settings


# ==================== Enums ====================

class RetrievalStrategy(str, Enum):
    """Retrieval strategy types"""
    VECTOR_ONLY = "vector_only"
    KEYWORD_ONLY = "keyword_only"
    HYBRID = "hybrid"
    ADAPTIVE = "adaptive"  # 自适应选择


class FilterStrategy(str, Enum):
    """Filtering strategy types"""
    LLM_BASED = "llm_based"
    SCORE_THRESHOLD = "score_threshold"
    DIVERSITY = "diversity"
    HYBRID = "hybrid"


class AnswerQuality(str, Enum):
    """Answer quality levels"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNCERTAIN = "uncertain"


# ==================== Data Classes ====================

@dataclass
class RetrievedChunk:
    """Retrieved document chunk with comprehensive metadata"""
    # Core content
    content: str
    score: float
    
    # Source information
    source: str
    doc_id: str
    chunk_id: str
    
    # Document metadata
    title: Optional[str] = None
    url: Optional[str] = None
    page: Optional[int] = None
    section: Optional[str] = None
    
    # Rich content
    image_urls: Optional[List[str]] = None
    table_data: Optional[Dict[str, Any]] = None
    
    # Retrieval metadata
    retrieval_method: Optional[str] = None  # "vector", "keyword", "hybrid"
    vector_score: Optional[float] = None
    keyword_score: Optional[float] = None
    rerank_score: Optional[float] = None
    
    # Filtering metadata
    relevance_score: Optional[float] = None
    is_filtered: bool = False
    filter_reason: Optional[str] = None
    
    # Additional metadata
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class UserContext:
    """User context and preferences"""
    user_id: str
    session_id: str
    
    # User profile
    department: Optional[str] = None
    role: Optional[str] = None
    permissions: List[str] = field(default_factory=list)
    
    # Preferences
    preferred_language: str = "zh-CN"
    preferred_sources: List[str] = field(default_factory=list)
    excluded_sources: List[str] = field(default_factory=list)
    
    # History
    query_history: List[str] = field(default_factory=list)
    feedback_history: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class RAGConfig:
    """RAG pipeline configuration"""
    # Model settings
    model: str = "qwen-plus"
    temperature: float = 0.0
    max_tokens: int = 2000
    
    # Retrieval settings
    retrieval_strategy: RetrievalStrategy = RetrievalStrategy.HYBRID
    vector_top_k: int = 10
    keyword_top_k: int = 10
    vector_score_threshold: float = 0.0
    keyword_score_threshold: float = 0.3
    
    # Filtering settings
    filter_strategy: FilterStrategy = FilterStrategy.HYBRID
    enable_llm_filter: bool = True
    max_chunks_after_filter: int = 5
    
    # Reranking settings
    enable_rerank: bool = True
    rerank_top_k: int = 3          # 内部兼容字段，实际由 llm_context_top_k 控制
    rerank_model: Optional[str] = None
    llm_context_top_k: int = 10     # 最终送给 LLM 的切片数上限（single_doc / multi_doc 统一）
    ranker: str = "RRF"              # "RRF" | "Weight"
    rrf_k: int = 60
    hybrid_alpha: float = 0.5

    # Multi-doc retrieval (grouping search)
    multi_doc_top_k: int = 20
    multi_doc_group_size: int = 3
    strict_group_size: bool = False

    # Single-doc retrieval
    single_doc_top_k: int = 20

    # User overrides (from request)
    force_multi_doc: Optional[bool] = None   # True=跳过 LLM 分类，直接 multi_doc
    keyword_filter: Optional[str] = None     # 有值=跳过策略判断，直接 KEYWORD_ONLY + TEXT_MATCH

    # 多模态
    kb_type: str = "standard"                # "standard" | "multimodal"
    query_image_url: Optional[str] = None    # 用户上传的查询图片 OSS 预签名 URL
    image_vector_dim: int = 1024             # 图片向量维度（与 kb 配置一致）
    
    # Memory settings
    memory_turns: int = 2  # 对话记忆轮数，每轮=1问+1答，默认保留最近2轮（4条消息）

    # Generation settings
    enable_citations: bool = True
    enable_images: bool = True
    enable_tables: bool = True
    max_context_length: int = 4000
    
    # Quality control
    min_confidence_threshold: float = 0.6
    enable_fallback: bool = True
    fallback_message: str = "抱歉，我无法找到相关信息。"
    
    # Knowledge base
    collection: Optional[str] = None  # 指定知识库名称（Milvus collection name）


@dataclass
class PerformanceMetrics:
    """Performance and usage metrics"""
    # Timing
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    total_duration_ms: float = 0.0
    
    # Stage timing
    retrieval_duration_ms: float = 0.0
    filter_duration_ms: float = 0.0
    rerank_duration_ms: float = 0.0
    generation_duration_ms: float = 0.0
    
    # Token usage
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    
    # LLM calls
    llm_calls: int = 0
    
    # Retrieval stats
    total_chunks_retrieved: int = 0
    chunks_after_filter: int = 0
    chunks_after_rerank: int = 0
    
    # Quality metrics
    answer_quality: Optional[AnswerQuality] = None
    confidence_score: float = 0.0
    
    # Cost estimation
    estimated_cost: float = 0.0


@dataclass
class DebugInfo:
    """Debug information for troubleshooting"""
    query_analysis: Optional[Dict[str, Any]] = None
    retrieval_details: Optional[Dict[str, Any]] = None
    filter_decisions: Optional[List[Dict[str, Any]]] = None
    rerank_scores: Optional[List[float]] = None
    generation_prompt: Optional[str] = None
    llm_raw_response: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# ==================== Main State ====================

class KnowledgeAgentState(TypedDict):
    """
    Enterprise Knowledge Base QA Agent State
    
    Complete state management for production RAG system with:
    - Multi-stage retrieval and filtering
    - User context and permissions
    - Configuration management
    - Performance monitoring
    - Debug information
    - Multi-turn conversation memory
    
    Workflow: Query Analysis -> Retrieve -> Filter -> Rerank -> Generate -> Quality Check
    """
    
    # ========== Conversation Memory ==========
    # 消息历史：存储所有对话记录（包括工具调用）
    messages: Annotated[List[BaseMessage], add_messages]
    
    # ========== Input ==========
    query: str
    original_query: str  # 保留原始查询
    rewritten_query: Optional[str]  # 改写后的查询
    
    # User context
    user_context: UserContext
    
    # Configuration
    config: RAGConfig
    
    # ========== Query Processing ==========
    # Query classification
    query_type: Optional[str]  # "single_doc" 或 "multi_doc"
    
    # Retrieval strategy
    retrieval_strategy: Optional[RetrievalStrategy]  # 检索策略
    retrieval_strategy_reason: Optional[str]  # 策略选择原因
    
    # Query analysis results
    query_intent: Optional[str]  # "factual", "procedural", "comparative", etc.
    query_complexity: Optional[str]  # "simple", "medium", "complex"
    query_keywords: List[str]
    query_entities: List[Dict[str, Any]]  # 提取的实体
    
    # ========== Retrieval Stage ==========
    # Raw retrieval results
    vector_chunks: List[RetrievedChunk]
    keyword_chunks: List[RetrievedChunk]
    merged_chunks: List[RetrievedChunk]
    
    # Retrieval metadata
    retrieval_strategy_used: Optional[RetrievalStrategy]
    total_candidates: int
    
    # ========== Filtering Stage ==========
    # Filtered results
    filtered_chunks: List[RetrievedChunk]
    filter_decisions: List[Dict[str, Any]]  # 每个chunk的过滤决策
    
    # Filtering metadata
    filter_strategy_used: Optional[FilterStrategy]
    chunks_removed: int
    
    # ========== Reranking Stage ==========
    # Reranked results
    reranked_chunks: List[RetrievedChunk]
    rerank_scores: List[float]
    
    # ========== Context Building ==========
    # Final context for LLM
    context: str
    context_length: int
    sources: List[Dict[str, Any]]
    
    # Rich content
    images: List[Dict[str, Any]]
    tables: List[Dict[str, Any]]
    
    # ========== Generation Stage ==========
    # Generated answer
    answer: str
    confidence: float

    # 图文模式：占位符 → 代理 URL 映射，供前端渲染图片
    image_map: Optional[Dict[str, str]]

    # SSE 流式：在 interrupt_before generate 之后由服务层写入，generate 节点内短路 LLM
    precomputed_answer: NotRequired[Optional[str]]
    
    # Answer metadata
    answer_quality: Optional[AnswerQuality]
    citations: List[Dict[str, Any]]
    follow_up_questions: List[str]
    
    # ========== Quality Control ==========
    # Quality checks
    quality_passed: bool
    quality_issues: List[str]
    
    # Fallback handling
    used_fallback: bool
    fallback_reason: Optional[str]
    
    # ========== Monitoring & Analytics ==========
    # Performance metrics
    metrics: PerformanceMetrics
    
    # Debug information
    debug: Optional[DebugInfo]
    
    # ========== Error Handling ==========
    error: Optional[str]
    error_stage: Optional[str]  # 哪个阶段出错
    error_details: Optional[Dict[str, Any]]
    
    # ========== Accumulated Data (with Reducers) ==========
    # 使用 reducer 累加的数据
    all_errors: Annotated[List[str], operator.add]
    all_warnings: Annotated[List[str], operator.add]
    processing_log: Annotated[List[Dict[str, Any]], operator.add]


# ==================== Helper Functions ====================

def create_initial_state(
    query: str,
    user_id: str,
    session_id: str,
    config: Optional[RAGConfig] = None,
    messages: Optional[List[BaseMessage]] = None
) -> KnowledgeAgentState:
    """
    Create initial state for RAG pipeline
    
    Args:
        query: User query
        user_id: User identifier
        session_id: Session identifier
        config: Optional RAG configuration
        messages: Optional conversation history
        
    Returns:
        Initial state dictionary
    """
    from langchain_core.messages import HumanMessage
    
    return {
        # Conversation Memory
        "messages": messages or [HumanMessage(content=query)],
        
        # Input
        "query": query,
        "original_query": query,
        "rewritten_query": None,
        
        # User context
        "user_context": UserContext(
            user_id=user_id,
            session_id=session_id
        ),
        
        # Configuration
        "config": config or RAGConfig(
            vector_score_threshold=settings.vector_score_threshold
        ),
        
        # Query processing
        "query_type": None,
        "retrieval_strategy": None,
        "retrieval_strategy_reason": None,
        "query_intent": None,
        "query_complexity": None,
        "query_keywords": [],
        "query_entities": [],
        
        # Retrieval
        "vector_chunks": [],
        "keyword_chunks": [],
        "merged_chunks": [],
        "retrieval_strategy_used": None,
        "total_candidates": 0,
        
        # Filtering
        "filtered_chunks": [],
        "filter_decisions": [],
        "filter_strategy_used": None,
        "chunks_removed": 0,
        
        # Reranking
        "reranked_chunks": [],
        "rerank_scores": [],
        
        # Context
        "context": "",
        "context_length": 0,
        "sources": [],
        "images": [],
        "tables": [],
        
        # Generation
        "answer": "",
        "confidence": 0.0,
        "image_map": None,
        "answer_quality": None,
        "citations": [],
        "follow_up_questions": [],
        
        # Quality control
        "quality_passed": False,
        "quality_issues": [],
        "used_fallback": False,
        "fallback_reason": None,
        
        # Monitoring
        "metrics": PerformanceMetrics(start_time=datetime.now()),
        "debug": DebugInfo() if config and config.model.startswith("debug") else None,
        
        # Error handling
        "error": None,
        "error_stage": None,
        "error_details": None,
        
        # Accumulated data
        "all_errors": [],
        "all_warnings": [],
        "processing_log": []
    }
