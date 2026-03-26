# -*- coding: utf-8 -*-
"""
Node 6: Quality Check
Checks answer quality and applies fallback if needed
"""

from typing import Dict, Any
from datetime import datetime

from ..state import KnowledgeAgentState, AnswerQuality


def check_quality(state: KnowledgeAgentState) -> Dict[str, Any]:
    """
    Check answer quality and apply fallback if needed
    
    Quality Checks:
        1. Answer length (must be >= 10 characters)
        2. Confidence threshold (must be >= configured threshold)
    
    Quality Levels:
        - HIGH: No issues
        - MEDIUM: 1 issue
        - LOW: 2+ issues
    
    Args:
        state: Current agent state
        
    Returns:
        State update with quality assessment
    """
    answer = state["answer"]
    confidence = state["confidence"]
    config = state["config"]
    
    print(f"\n[Node 6: Quality Check] Checking answer quality")
    
    try:
        quality_issues = []
        
        # Check 1: Answer length
        if len(answer) < 10:
            quality_issues.append("Answer too short")
        
        # Check 2: Confidence threshold
        if confidence < config.min_confidence_threshold:
            quality_issues.append(f"Confidence {confidence:.2f} below threshold {config.min_confidence_threshold}")
        
        # Determine quality level
        if not quality_issues:
            quality_level = AnswerQuality.HIGH
            quality_passed = True
        elif len(quality_issues) == 1:
            quality_level = AnswerQuality.MEDIUM
            quality_passed = True
        else:
            quality_level = AnswerQuality.LOW
            quality_passed = False
        
        # Apply fallback if needed
        used_fallback = False
        fallback_reason = None
        final_answer = answer
        
        if not quality_passed and config.enable_fallback:
            used_fallback = True
            fallback_reason = "; ".join(quality_issues)
            final_answer = config.fallback_message
        
        print(f"[Quality Check] Quality: {quality_level.value}, Passed: {quality_passed}")
        if used_fallback:
            print(f"[Quality Check] Fallback applied: {fallback_reason}")
        
        return {
            "answer": final_answer,
            "answer_quality": quality_level,
            "quality_passed": quality_passed,
            "quality_issues": quality_issues,
            "used_fallback": used_fallback,
            "fallback_reason": fallback_reason,
            "processing_log": [{
                "stage": "quality_check",
                "timestamp": datetime.now().isoformat(),
                "quality_level": quality_level.value,
                "quality_passed": quality_passed
            }]
        }
    
    except Exception as e:
        print(f"[Quality Check] Error: {str(e)}")
        return {
            "all_errors": [f"Quality check failed: {str(e)}"]
        }
