# Track: Replay Engine Muxing & Infinite Cursors

**Objective:**
Enhance `ReplayEngine` and `ArchiveIngester` with multi-symbol synchronization (klinemuxer), "first candle" alignment, and "infinite cursor" behavior, referencing implementations from `mp-superproject`.

**Why this now:**
Matches user directive to port missing data-handling features from the master project (`mp-superproject`) to `curly-succotash` for more robust training and backtesting.

**Scope:**
1.  **`backend/src/archive_ingester.py`**:
    *   Enhance `fetchklines` logic to better align with `fetchklines.sh` (e.g. better error handling for missing months).
2.  **`backend/src/replay_engine.py`**:
    *   Implement `KlineMuxer` logic to synchronize "first candles" across multiple symbols (ensuring all streams start at the same time or handle leading gaps correctly).
    *   Implement "infinite cursor" behavior (e.g. padding missing periods with last known values or zeros to prevent stream breaks).
3.  **`backend/src/tests/test_replay_muxing.py`**:
    *   Add tests for multi-symbol synchronization with staggered start times.
    *   Add tests for infinite cursor padding on gapped data.

**Stop condition:**
`pytest backend/src/tests/test_replay_muxing.py` passes.
