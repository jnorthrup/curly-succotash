#!/usr/bin/env python3
"""
Generate OHLCV candles and technical indicators for parity testing.
"""

import pandas as pd
import numpy as np
import json
import os

def generate_ohlcv_data(n=100):
    """Generate synthetic OHLCV data."""
    np.random.seed(42)  # For reproducibility
    
    # Generate time series data
    dates = pd.date_range(start='2024-01-01', periods=n, freq='D')
    
    # Generate price series with some randomness and trend
    base_price = 100.0
    prices = base_price + np.cumsum(np.random.normal(0, 1, n))
    
    # Generate OHLCV data
    open_price = prices.copy()
    high_price = prices + np.abs(np.random.normal(0, 2, n))  # High is slightly above close
    low_price = prices - np.abs(np.random.normal(0, 2, n))   # Low is slightly below close
    close_price = prices.copy()
    volume = np.random.randint(1000, 5000, size=n)  # Random volume between 1000-5000
    
    # Ensure high >= low and high >= close >= low
    high_price = np.maximum(high_price, np.maximum(open_price, close_price))
    low_price = np.minimum(low_price, np.minimum(open_price, close_price))
    
    # Create DataFrame
    df = pd.DataFrame({
        'date': dates,
        'open': open_price,
        'high': high_price,
        'low': low_price,
        'close': close_price,
        'volume': volume
    })
    
    df['date'] = df['date'].dt.strftime('%Y-%m-%d')
    return df

def calculate_sma(df, window=20):
    """Calculate Simple Moving Average."""
    df[f'sma_{window}'] = df['close'].rolling(window=window).mean()
    return df

def calculate_ema(df, window=20):
    """Calculate Exponential Moving Average."""
    df[f'ema_{window}'] = df['close'].ewm(span=window, adjust=False).mean()
    return df

def calculate_rsi(df, window=14):
    """Calculate Relative Strength Index."""
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    df[f'rsi_{window}'] = rsi
    return df

def calculate_bollinger_bands(df, window=20, num_std=2):
    """Calculate Bollinger Bands."""
    sma = df['close'].rolling(window=window).mean()
    std = df['close'].rolling(window=window).std()
    df[f'bb_upper_{window}'] = sma + (std * num_std)
    df[f'bb_lower_{window}'] = sma - (std * num_std)
    return df

def calculate_atr(df, window=14):
    """Calculate Average True Range."""
    high_low = df['high'] - df['low']
    high_close = abs(df['high'] - df['close'].shift())
    low_close = abs(df['low'] - df['close'].shift())
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr_{}'.format(window)] = true_range.rolling(window=window).mean()
    return df

def main():
    """Main function to generate data and indicators."""
    # Generate OHLCV data
    df = generate_ohlcv_data(n=100)
    
    # Calculate technical indicators
    df = calculate_sma(df, window=20)
    df = calculate_ema(df, window=20)
    df = calculate_rsi(df, window=14)
    df = calculate_bollinger_bands(df, window=20, num_std=2)
    df = calculate_atr(df, window=14)
    
    # Convert to dictionary and save to JSON
    data_dict = df.to_dict(orient='records')
    
    output_path = 'tmp/indicator_parity_ground_truth.json'
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(data_dict, f, indent=2)
    
    print(f"Successfully generated {len(df)} OHLCV candles with indicators")
    print(f"Output saved to: {output_path}")

if __name__ == '__main__':
    main()