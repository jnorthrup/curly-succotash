#!/usr/bin/env python3
"""
Benchmark script for pandas-based technical indicators.
Measures execution time for SMA, EMA, RSI, BB, and ATR on 1M OHLCV rows.
"""

import time
import numpy as np
import pandas as pd


def generate_ohlcv_data(n_rows: int = 1_000_000, seed: int = 42) -> pd.DataFrame:
    """Generate realistic OHLCV synthetic data.
    
    Uses a random walk for prices to create realistic-looking price movements.
    Ensures High >= max(Open, Close) and Low <= min(Open, Close).
    """
    np.random.seed(seed)
    
    # Starting price
    base_price = 100.0
    
    # Generate returns using normal distribution (random walk)
    # Use small variance for realistic price movements
    returns = np.random.normal(0.0001, 0.02, n_rows)
    
    # Calculate close prices
    close_prices = base_price * np.cumprod(1 + returns)
    
    # Generate open prices (slight gap from previous close)
    open_gaps = np.random.normal(0, 0.005, n_rows)
    open_prices = np.roll(close_prices, 1) * (1 + open_gaps)
    open_prices[0] = base_price
    
    # Generate high and low to ensure OHLC validity
    # High is max of open/close plus some random upward movement
    high_offset = np.abs(np.random.normal(0, 0.01, n_rows)) * close_prices
    high_prices = np.maximum(open_prices, close_prices) + high_offset
    
    # Low is min of open/close minus some random downward movement
    low_offset = np.abs(np.random.normal(0, 0.01, n_rows)) * close_prices
    low_prices = np.minimum(open_prices, close_prices) - low_offset
    
    # Generate volume with realistic distribution (log-normal)
    base_volume = 1_000_000
    volume = np.random.lognormal(np.log(base_volume), 0.5, n_rows).astype(np.int64)
    
    df = pd.DataFrame({
        'Open': open_prices,
        'High': high_prices,
        'Low': low_prices,
        'Close': close_prices,
        'Volume': volume
    })
    
    return df


def calculate_sma(close: pd.Series, period: int = 20) -> pd.Series:
    """Simple Moving Average."""
    return close.rolling(window=period).mean()


def calculate_ema(close: pd.Series, period: int = 20) -> pd.Series:
    """Exponential Moving Average."""
    return close.ewm(span=period, adjust=False).mean()


def calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index."""
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_bollinger_bands(close: pd.Series, period: int = 20, num_std: int = 2):
    """Bollinger Bands."""
    sma = close.rolling(window=period).mean()
    std = close.rolling(window=period).std()
    
    upper_band = sma + (std * num_std)
    lower_band = sma - (std * num_std)
    
    return sma, upper_band, lower_band


def calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14):
    """Average True Range."""
    prev_close = close.shift(1)
    
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    
    return atr


def benchmark_indicator(func, *args, **kwargs):
    """Benchmark a single indicator calculation."""
    start_time = time.perf_counter()
    result = func(*args, **kwargs)
    end_time = time.perf_counter()
    
    # Force computation if result is lazy
    _ = result.iloc[-1] if hasattr(result, 'iloc') else result
    
    elapsed = end_time - start_time
    return elapsed * 1000  # Convert to milliseconds


def main():
    n_rows = 1_000_000
    
    print(f"Generating {n_rows:,} OHLCV rows...")
    df = generate_ohlcv_data(n_rows)
    
    print(f"Data shape: {df.shape}")
    print(f"Columns: {list(df.columns)}")
    print()
    
    results = {}
    
    # Benchmark SMA
    print("Benchmarking SMA (20 periods)...")
    elapsed = benchmark_indicator(calculate_sma, df['Close'], 20)
    results['SMA'] = elapsed
    print(f"  -> {elapsed:.2f} ms per million rows")
    
    # Benchmark EMA
    print("Benchmarking EMA (20 periods)...")
    elapsed = benchmark_indicator(calculate_ema, df['Close'], 20)
    results['EMA'] = elapsed
    print(f"  -> {elapsed:.2f} ms per million rows")
    
    # Benchmark RSI
    print("Benchmarking RSI (14 periods)...")
    elapsed = benchmark_indicator(calculate_rsi, df['Close'], 14)
    results['RSI'] = elapsed
    print(f"  -> {elapsed:.2f} ms per million rows")
    
    # Benchmark Bollinger Bands
    print("Benchmarking Bollinger Bands (20 periods, 2 std)...")
    elapsed = benchmark_indicator(calculate_bollinger_bands, df['Close'], 20, 2)
    results['BB'] = elapsed
    print(f"  -> {elapsed:.2f} ms per million rows")
    
    # Benchmark ATR
    print("Benchmarking ATR (14 periods)...")
    elapsed = benchmark_indicator(calculate_atr, df['High'], df['Low'], df['Close'], 14)
    results['ATR'] = elapsed
    print(f"  -> {elapsed:.2f} ms per million rows")
    
    # Print summary
    print()
    print("=" * 50)
    print("BENCHMARK RESULTS (ms per million rows)")
    print("=" * 50)
    for indicator, ms in results.items():
        print(f"  {indicator:8s}: {ms:>10.2f} ms")
    print("=" * 50)


if __name__ == '__main__':
    main()
