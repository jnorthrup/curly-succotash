"""
Quality Gates - Enforcement of evidence-based execution.

Provides decorators and utilities to ensure that critical paths
(e.g., training, evaluation, indicators) do not use hidden fallbacks,
invented numbers, or "fake" success modes.
Satisfies the mandate to "Stop any QA path that invents fallback numbers."
"""

import os
import functools
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Environment variable to enable strict quality gates
STRICT_QA = os.environ.get("STRICT_QA", "false").lower() == "true"


def forbid_mock_fallbacks(func: Callable) -> Callable:
    """
    Decorator that prevents a function from returning mocked/fallback values
    when STRICT_QA environment variable is set to true.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        
        if STRICT_QA:
            # Check for common mock signatures
            if result is None and "None" not in str(func.__annotations__.get("return")):
                raise RuntimeError(f"Quality Gate Violation: {func.__name__} returned None (unexpected fallback)")
            
            # Check for dicts with 'is_mock' or 'mocked' keys
            if isinstance(result, dict):
                if result.get("is_mock") or result.get("mocked") or result.get("fallback"):
                    raise RuntimeError(f"Quality Gate Violation: {func.__name__} returned a mocked payload")
            
            # Check for Pandas DataFrames
            if result.__class__.__name__ == 'DataFrame':
                # We check columns for 'fallback' or 'mock'
                cols = [str(c).lower() for c in result.columns]
                if 'fallback' in cols or 'is_mock' in cols or 'mocked' in cols:
                    raise RuntimeError(f"Quality Gate Violation: {func.__name__} returned a DataFrame with fallback columns")
                    
            # Check for strings indicating fallbacks
            if isinstance(result, str) and ("mock" in result.lower() or "fallback" in result.lower()):
                raise RuntimeError(f"Quality Gate Violation: {func.__name__} returned a mock/fallback string")
                
        return result
    return wrapper


def validate_artifact_evidence(artifact_path: str):
    """Ensure an artifact exists and is not a placeholder."""
    if not os.path.exists(artifact_path):
        raise FileNotFoundError(f"Missing artifact evidence: {artifact_path}")
        
    if os.path.getsize(artifact_path) == 0:
        raise ValueError(f"Empty artifact evidence (placeholder): {artifact_path}")
        
    # Optional: check if file was generated recently
    # In a real pipeline, we'd check the generation timestamp inside the JSON
