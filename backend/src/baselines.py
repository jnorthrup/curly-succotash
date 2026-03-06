import numpy as np

def persistence_baseline(x: np.ndarray) -> np.ndarray:
    """Returns the last known value for all future steps."""
    return x.copy()

def ema_baseline(x: np.ndarray, alpha: float = 0.5) -> np.ndarray:
    """Exponential moving average baseline."""
    res = np.zeros_like(x)
    ema = x[0].copy()
    for i in range(x.shape[0]):
        ema = alpha * x[i] + (1 - alpha) * ema
        res[i] = ema
    return res

def linear_baseline(x: np.ndarray) -> np.ndarray:
    """Simple linear projection baseline (fallback to identity for now)."""
    return x.copy()
