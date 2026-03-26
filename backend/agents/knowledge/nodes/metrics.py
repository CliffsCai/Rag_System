# -*- coding: utf-8 -*-
"""
Node 7: Metrics Finalization
Finalizes performance metrics
"""

from typing import Dict, Any
from datetime import datetime

from ..state import KnowledgeAgentState


def finalize_metrics(state: KnowledgeAgentState) -> Dict[str, Any]:
    """
    Finalize performance metrics
    
    Metrics Calculated:
        - Total duration (milliseconds)
        - Estimated cost (based on model and tokens)
    
    Args:
        state: Current agent state
        
    Returns:
        State update with finalized metrics
    """
    metrics = state["metrics"]
    config = state["config"]
    
    print(f"\n[Node 7: Metrics] Finalizing metrics")
    
    try:
        # Calculate total duration
        if metrics.start_time:
            end_time = datetime.now()
            total_duration = (end_time - metrics.start_time).total_seconds() * 1000
            
            metrics.end_time = end_time
            metrics.total_duration_ms = total_duration
        
        # Estimate cost from SUPPORTED_MODELS config
        from app.core.config import SUPPORTED_MODELS
        model_info = SUPPORTED_MODELS.get(config.model, {})
        cost_per_1k_tokens = model_info.get("cost_per_1k_tokens", 0.001)
        
        metrics.estimated_cost = (metrics.total_tokens / 1000) * cost_per_1k_tokens
        
        print(f"[Metrics] Duration: {metrics.total_duration_ms:.2f}ms")
        print(f"[Metrics] Tokens: {metrics.total_tokens}")
        print(f"[Metrics] Cost: ${metrics.estimated_cost:.4f}")
        
        return {
            "metrics": metrics,
            "processing_log": [{
                "stage": "metrics_finalization",
                "timestamp": datetime.now().isoformat(),
                "total_duration_ms": metrics.total_duration_ms
            }]
        }
    
    except Exception as e:
        print(f"[Metrics] Error: {str(e)}")
        return {
            "all_errors": [f"Metrics finalization failed: {str(e)}"]
        }
