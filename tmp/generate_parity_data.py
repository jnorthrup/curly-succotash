#!/usr/bin/env python3
import json
import pandas as pd
import numpy as np

def generate_parity_data():
    df = pd.DataFrame({
        "close": np.random.randn(100).cumsum() + 100,
        "high": np.random.randn(100).cumsum() + 105,
        "low": np.random.randn(100).cumsum() + 95,
        "open": np.random.randn(100).cumsum() + 100,
        "volume": np.abs(np.random.randn(100) * 1000)
    })
    
    # Very basic "pandas" indicator output mock
    df["sma"] = df["close"].rolling(14).mean()
    df["ema"] = df["close"].ewm(span=14).mean()
    
    out = df.fillna(0.0).to_dict(orient="records")
    with open("tmp/indicator_parity_ground_truth.json", "w") as f:
        json.dump(out, f)

if __name__ == "__main__":
    generate_parity_data()

