# Freqtrade Retirement and Extraction Plan

## Context
As the broader macro-project shifts toward Kotlin-native backtesting (via `trikeshed`) and domain-specific DSEL execution (`moneyfan`), the legacy Python `freqtrade` components are being deliberately retired.

## Ownership Migration
1. **Indicator Logic:** All Pandas-based Python indicator logic is migrating to `trikeshed` as Kotlin-native functions backed by DuckDB.
2. **Strategy Definition:** Hardcoded Python strategies are migrating to `moneyfan` swimlane DSEL artifacts for runtime flexibility and cross-language execution.
3. **Execution/Backtesting:** `curly-succotash` handles the HRM simulation and shadow mode promotion ladder; eventually, `trikeshed` will provide the native backtesting engine, fully deprecating the `freqtrade` backtesting pipeline.

## Deprecation Schedule
- **Phase 1 (Current):** Freqtrade is running in a hybrid state, consuming HRM artifacts via the ring agent proxy (`FreqtradeRingAgent`).
- **Phase 2 (Extraction):** Indicator parity tests validate `trikeshed` against `freqtrade`. Once stable, DuckDB cursors replace Pandas dataframes.
- **Phase 3 (Retirement):** `freqtrade` repos are archived. All execution shifts to `trikeshed` native binaries.

## Remaining Dependencies
- Contract proxy mapping against Freqtrade endpoint schema (`TODO.md`).
- Kotlin indicator parity validation (`TODO.md`).
