# Track: Indicator Performance Benchmark Scaffolding

## Objective
Satisfy the TODO item "Benchmark Kotlin indicator performance against the current pandas path."

## Scope
- Create a Python script `backend/scripts/benchmark_pandas_indicators.py` that generates a very large dataframe (e.g., 1,000,000 rows) and measures the exact execution time required to compute the standard indicator suite (SMA, EMA, RSI, BB, ATR) purely in Pandas.
- This establishes the baseline "time to beat" for the DuckDB/Kotlin extraction path.

## Stop Condition
The benchmarking script exists and prints out the measured time in milliseconds per million rows.
