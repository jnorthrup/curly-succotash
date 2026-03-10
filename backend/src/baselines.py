import numpy as np

def persistence_baseline(x: np.ndarray) -> np.ndarray:
    """Returns the last known value for all future steps (Identity)."""
    return x.copy()

def ema_baseline(x: np.ndarray, alpha: float = 0.5) -> np.ndarray:
    """
    Exponential moving average baseline.
    Predicts the EMA of previous observations.
    """
    if x.ndim == 1:
        x = x.reshape(-1, 1)
        
    res = np.zeros_like(x)
    ema = x[0].copy()
    for i in range(x.shape[0]):
        ema = alpha * x[i] + (1 - alpha) * ema
        res[i] = ema
    return res

def linear_baseline(x: np.ndarray, window: int = 5) -> np.ndarray:
    """
    Simple linear projection baseline using ordinary least squares (OLS)
    on a sliding window of the previous N observations.
    
    If x is multi-dimensional (features), computes independent linear 
    projections for each feature.
    """
    if x.ndim == 1:
        x = x.reshape(-1, 1)
        
    n_samples, n_features = x.shape
    res = np.zeros_like(x)
    
    # Time indices for X axis of linear regression
    t = np.arange(window).reshape(-1, 1)
    
    for i in range(n_samples):
        if i < window:
            # Not enough history, fallback to identity/persistence
            res[i] = x[i]
            continue
            
        # Get history window for each feature
        history = x[i-window:i]
        
        for j in range(n_features):
            y = history[:, j].reshape(-1, 1)
            
            # Simple linear regression: y = mt + b
            # [t, 1] * [m, b]^T = y
            A = np.hstack([t, np.ones_like(t)])
            coeffs = np.linalg.lstsq(A, y, rcond=None)[0]
            m = coeffs[0, 0]
            b = coeffs[1, 0]
            
            # Predict for next step (t = window)
            res[i, j] = m * window + b
            
    return res
