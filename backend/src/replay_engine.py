"""
Replay Engine - High-throughput historical data streaming with time compression.

Streams candles from DuckDB at configurable speeds, supporting real-time,
compressed, and step-through replay modes. Multi-symbol synchronization
aligns candles by timestamp across symbols for accurate replay.

Architecture:
- Callback-based (like DataIngestionService)
- Thread-safe state management
- Deterministic with optional seeding
- Multi-symbol stream synchronization
"""

import asyncio
import logging
import random
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from heapq import merge
from typing import Callable, Dict, Iterator, List, Optional, Tuple, Any

from .models import Candle, Timeframe
from .binance_client import BinanceArchiveClient

logger = logging.getLogger(__name__)


class ReplayMode(Enum):
    """
    Replay modes for different use cases.

    REALTIME: Actual delays between candles (1x speed)
    COMPRESSED: Fast-forward with time compression (Nx speed)
    STEP_THROUGH: Manual stepping for debugging/analysis
    INSTANT: Process as fast as possible (max throughput)
    """
    REALTIME = "realtime"
    COMPRESSED = "compressed"
    STEP_THROUGH = "step_through"
    INSTANT = "instant"


@dataclass
class ReplayConfig:
    """
    Configuration for the ReplayEngine.

    Attributes:
        mode: Replay mode (realtime, compressed, step_through, instant)
        compression_factor: Speed multiplier for COMPRESSED mode (1.0 to 1000.0)
        symbols: List of trading pair symbols to replay
        timeframes: List of timeframes to replay
        start_time: Optional start time filter (inclusive)
        end_time: Optional end time filter (inclusive)
        seed: Optional seed for deterministic replay ordering
        infinite_cursor: If True, fills gaps in candle streams with padding
        align_symbols: If True, aligns all symbols to the earliest common start time
    """
    mode: ReplayMode = ReplayMode.COMPRESSED
    compression_factor: float = 100.0
    symbols: List[str] = field(default_factory=list)
    timeframes: List[Timeframe] = field(default_factory=lambda: [Timeframe.ONE_HOUR])
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    seed: Optional[int] = None
    infinite_cursor: bool = False
    align_symbols: bool = False

    def __post_init__(self):
        """Validate configuration parameters."""
        if self.compression_factor < 1.0:
            logger.warning(f"[CONFIG] compression_factor {self.compression_factor} < 1.0, setting to 1.0")
            self.compression_factor = 1.0
        elif self.compression_factor > 1000.0:
            logger.warning(f"[CONFIG] compression_factor {self.compression_factor} > 1000.0, setting to 1000.0")
            self.compression_factor = 1000.0

        if self.start_time and self.end_time and self.start_time > self.end_time:
            raise ValueError("start_time cannot be after end_time")

        # Ensure timezone-aware datetimes
        if self.start_time and self.start_time.tzinfo is None:
            self.start_time = self.start_time.replace(tzinfo=timezone.utc)
        if self.end_time and self.end_time.tzinfo is None:
            self.end_time = self.end_time.replace(tzinfo=timezone.utc)


@dataclass
class ReplayStatus:
    """
    Current status of the ReplayEngine.

    Attributes:
        is_running: Whether the replay is currently running
        is_paused: Whether the replay is paused
        progress_pct: Progress percentage (0.0 to 100.0)
        current_time: Current timestamp in the replay
        candles_processed: Total candles processed
        candles_total: Total candles to process
        symbols_completed: List of symbols that have completed
        current_symbol: Symbol currently being processed
        elapsed_seconds: Elapsed time since start
        estimated_remaining_seconds: Estimated time remaining
    """
    is_running: bool = False
    is_paused: bool = False
    progress_pct: float = 0.0
    current_time: Optional[datetime] = None
    candles_processed: int = 0
    candles_total: int = 0
    symbols_completed: List[str] = field(default_factory=list)
    current_symbol: Optional[str] = None
    elapsed_seconds: float = 0.0
    estimated_remaining_seconds: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert status to dictionary."""
        return {
            "is_running": self.is_running,
            "is_paused": self.is_paused,
            "progress_pct": round(self.progress_pct, 2),
            "current_time": self.current_time.isoformat() if self.current_time else None,
            "candles_processed": self.candles_processed,
            "candles_total": self.candles_total,
            "symbols_completed": self.symbols_completed,
            "current_symbol": self.current_symbol,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "estimated_remaining_seconds": round(self.estimated_remaining_seconds, 2)
                if self.estimated_remaining_seconds else None,
        }


class ReplayEngine:
    """
    High-throughput historical candle replay engine with time compression.

    Supports multiple replay modes, multi-symbol synchronization, and
    callback-based architecture for integration with strategies.

    Thread Safety:
    - All state mutations are protected by _state_lock
    - Callbacks may be called from different threads

    Example:
        client = BinanceArchiveClient()
        config = ReplayConfig(
            mode=ReplayMode.COMPRESSED,
            compression_factor=100.0,
            symbols=["BTCUSDT", "ETHUSDT"],
            timeframes=[Timeframe.ONE_HOUR]
        )
        engine = ReplayEngine(client, config)
        engine.set_callbacks(on_candle, on_complete)
        engine.start()
    """

    def __init__(self, client: BinanceArchiveClient, config: ReplayConfig):
        """
        Initialize the ReplayEngine.

        Args:
            client: BinanceArchiveClient for data access
            config: ReplayConfig with replay settings
        """
        self.client = client
        self.config = config

        # Callbacks
        self._candle_callback: Optional[Callable[[Candle], None]] = None
        self._completed_callback: Optional[Callable[[], None]] = None

        # State management (thread-safe)
        self._state_lock = threading.Lock()
        self._is_running = False
        self._is_paused = False
        self._should_stop = False
        self._current_index = 0
        self._candles: List[Candle] = []
        self._start_time: Optional[datetime] = None
        self._current_time: Optional[datetime] = None

        # Step-through mode state
        self._step_event = threading.Event()
        self._step_queue: List[Candle] = []

        # Progress tracking
        self._candles_processed = 0
        self._candles_total = 0
        self._symbols_completed: List[str] = []
        self._current_symbol: Optional[str] = None

        # Deterministic random for shuffling
        self._rng = random.Random(config.seed) if config.seed else None

        # Async loop for non-blocking replay
        self._replay_task: Optional[asyncio.Task] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        logger.info(f"[INIT] ReplayEngine initialized - Mode: {config.mode.value}, "
                   f"Symbols: {config.symbols}, Timeframes: {[tf.value for tf in config.timeframes]}")

    def set_callbacks(
        self,
        candle_callback: Callable[[Candle], None],
        completed_callback: Optional[Callable[[], None]] = None
    ) -> None:
        """
        Set callbacks for candle events and completion.

        Args:
            candle_callback: Called for each candle during replay
            completed_callback: Optional callback when replay completes
        """
        self._candle_callback = candle_callback
        self._completed_callback = completed_callback
        logger.debug(f"[CALLBACKS] Registered candle callback and "
                    f"{'completed callback' if completed_callback else 'no completed callback'}")

    def start(self) -> None:
        """
        Begin the replay.

        Loads candles and starts the replay loop based on configured mode.
        Raises RuntimeError if already running or no callbacks registered.
        """
        with self._state_lock:
            if self._is_running:
                raise RuntimeError("Replay is already running")
            if not self._candle_callback:
                raise RuntimeError("No candle callback registered. Call set_callbacks() first.")

            self._is_running = True
            self._is_paused = False
            self._should_stop = False
            self._start_time = datetime.now(timezone.utc)
            self._candles_processed = 0
            self._symbols_completed = []

        logger.info(f"[START] Starting replay in {self.config.mode.value} mode")

        # Load candles from database
        self._load_candles()

        if not self._candles:
            logger.warning("[START] No candles loaded, nothing to replay")
            self._on_completed()
            return

        # Start replay based on mode
        if self.config.mode == ReplayMode.STEP_THROUGH:
            # Step-through mode: just load, wait for step() calls
            logger.info(f"[START] Step-through mode ready with {len(self._candles)} candles")
        else:
            # Other modes: run in async loop
            self._run_replay_loop()

    def pause(self) -> None:
        """Pause the replay. No-op if not running or already paused."""
        with self._state_lock:
            if not self._is_running or self._is_paused:
                return
            self._is_paused = True
        logger.info("[PAUSE] Replay paused")

    def resume(self) -> None:
        """Resume the replay. No-op if not running or not paused."""
        with self._state_lock:
            if not self._is_running or not self._is_paused:
                return
            self._is_paused = False
        logger.info("[RESUME] Replay resumed")

    def stop(self) -> None:
        """Stop the replay. Can be resumed with start()."""
        with self._state_lock:
            if not self._is_running:
                return
            self._should_stop = True
            self._is_running = False
            self._is_paused = False
        logger.info("[STOP] Replay stopped")

    def step(self) -> Optional[Candle]:
        """
        Process a single candle (for STEP_THROUGH mode).

        Returns:
            The candle that was processed, or None if replay complete/not in step mode
        """
        if self.config.mode != ReplayMode.STEP_THROUGH:
            logger.warning("[STEP] step() only works in STEP_THROUGH mode")
            return None

        with self._state_lock:
            if not self._is_running:
                logger.warning("[STEP] Replay not started")
                return None
            if self._current_index >= len(self._candles):
                logger.info("[STEP] Replay complete")
                self._on_completed()
                return None

            candle = self._candles[self._current_index]
            self._current_index += 1
            self._candles_processed += 1
            self._current_time = candle.timestamp

        self._emit_candle(candle)
        logger.debug(f"[STEP] Processed candle {self._candles_processed}/{self._candles_total}")
        return candle

    def get_status(self) -> ReplayStatus:
        """
        Get current replay status.

        Returns:
            ReplayStatus with current progress and state
        """
        with self._state_lock:
            elapsed = 0.0
            if self._start_time:
                elapsed = (datetime.now(timezone.utc) - self._start_time).total_seconds()

            progress_pct = 0.0
            estimated_remaining = None
            if self._candles_total > 0:
                progress_pct = (self._candles_processed / self._candles_total) * 100
                if self._candles_processed > 0 and elapsed > 0:
                    rate = self._candles_processed / elapsed
                    remaining_candles = self._candles_total - self._candles_processed
                    estimated_remaining = remaining_candles / rate if rate > 0 else None

            return ReplayStatus(
                is_running=self._is_running,
                is_paused=self._is_paused,
                progress_pct=progress_pct,
                current_time=self._current_time,
                candles_processed=self._candles_processed,
                candles_total=self._candles_total,
                symbols_completed=self._symbols_completed.copy(),
                current_symbol=self._current_symbol,
                elapsed_seconds=elapsed,
                estimated_remaining_seconds=estimated_remaining,
            )

    def seek_to(self, timestamp: datetime) -> None:
        """
        Seek to a specific timestamp in the replay.

        Args:
            timestamp: Target timestamp to seek to
        """
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        with self._state_lock:
            # Find the index of the first candle at or after the timestamp
            for i, candle in enumerate(self._candles):
                if candle.timestamp >= timestamp:
                    self._current_index = i
                    self._current_time = candle.timestamp
                    logger.info(f"[SEEK] Seeked to index {i}, timestamp {timestamp}")
                    return

            # If not found, seek to end
            self._current_index = len(self._candles)
            logger.warning(f"[SEEK] Timestamp {timestamp} not found, seeked to end")

    def _load_candles(self) -> None:
        """
        Load candles from DuckDB for all configured symbols and timeframes.

        Uses multi-symbol synchronization to align candles by timestamp.
        """
        logger.info(f"[LOAD] Loading candles for {len(self.config.symbols)} symbols, "
                   f"{len(self.config.timeframes)} timeframes")

        all_candles: List[Candle] = []

        # Optional: Pre-calculate earliest start time if align_symbols is requested
        # and no explicit start_time is provided.
        start_override = None
        if self.config.align_symbols and not self.config.start_time:
            for symbol in self.config.symbols:
                for timeframe in self.config.timeframes:
                    try:
                        db_start, _ = self.client.get_date_range(symbol, timeframe)
                        if start_override is None or db_start < start_override:
                            start_override = db_start
                    except Exception:
                        continue
            if start_override:
                logger.info(f"[LOAD] Aligned start time to {start_override}")

        for symbol in self.config.symbols:
            for timeframe in self.config.timeframes:
                try:
                    # Determine date range
                    db_start, db_end = self.client.get_date_range(symbol, timeframe)

                    start = self.config.start_time or start_override or db_start
                    end = self.config.end_time or db_end

                    if start < db_start:
                        start = db_start
                    if end > db_end:
                        end = db_end

                    # Query candles
                    candles = self.client.query_candles(symbol, timeframe, start, end)

                    if candles:
                        all_candles.extend(candles)
                        logger.info(f"[LOAD] Loaded {len(candles)} candles for {symbol} {timeframe.value}")
                    else:
                        logger.warning(f"[LOAD] No candles found for {symbol} {timeframe.value}")

                except Exception as e:
                    logger.error(f"[LOAD] Failed to load candles for {symbol} {timeframe.value}: {e}")

        if not all_candles:
            logger.warning("[LOAD] No candles loaded from database")
            self._candles = []
            self._candles_total = 0
            return

        # Synchronize and sort candles
        self._candles = self._synchronize_candles(all_candles)
        self._candles_total = len(self._candles)

        logger.info(f"[LOAD] Total synchronized candles: {self._candles_total}")

    def _synchronize_candles(self, candles: List[Candle]) -> List[Candle]:
        """
        Synchronize candles across multiple symbols by timestamp.

        Uses a heap-based merge sort to efficiently combine candles from
        different symbols while maintaining chronological order.
        Supports infinite cursor mode for gap filling and symbol alignment.

        Args:
            candles: List of candles from potentially multiple symbols

        Returns:
            Sorted list of candles by timestamp (chronological order)
        """
        if not candles:
            return []

        # Group candles by (symbol, timeframe)
        symbol_streams: Dict[Tuple[str, Timeframe], List[Candle]] = {}
        for candle in candles:
            key = (candle.symbol, candle.timeframe)
            if key not in symbol_streams:
                symbol_streams[key] = []
            symbol_streams[key].append(candle)

        # Sort each stream
        for key in symbol_streams:
            symbol_streams[key].sort(key=lambda c: c.timestamp)

        # Determine global time range for synchronization/padding
        all_timestamps = [c.timestamp for c in candles]
        global_start = min(all_timestamps)
        global_end = max(all_timestamps)

        # Optionally align to user-specified start time if earlier
        if self.config.align_symbols and self.config.start_time:
            if self.config.start_time < global_start:
                global_start = self.config.start_time

        processed_streams = []

        if self.config.infinite_cursor or self.config.align_symbols:
            # Multi-symbol synchronization with padding
            for (symbol, timeframe), stream in symbol_streams.items():
                delta = timedelta(seconds=Timeframe.to_seconds(timeframe))
                padded_stream = []
                last_candle = None

                # Start alignment: align to global_start if align_symbols is ON
                # Grid alignment: ensure current_ts follows the stream's candle grid
                first_real_ts = stream[0].timestamp
                current_ts = global_start if self.config.align_symbols else first_real_ts

                # Adjust current_ts to align with timeframe grid defined by first_real_ts
                diff_seconds = (first_real_ts - current_ts).total_seconds()
                if diff_seconds > 0:
                    offset = diff_seconds % delta.total_seconds()
                    if offset != 0:
                        current_ts += timedelta(seconds=offset)

                stream_idx = 0
                while current_ts <= global_end:
                    # Match real candle
                    if stream_idx < len(stream) and stream[stream_idx].timestamp == current_ts:
                        candle = stream[stream_idx]
                        padded_stream.append(candle)
                        last_candle = candle
                        stream_idx += 1
                        current_ts += delta
                    elif stream_idx < len(stream) and stream[stream_idx].timestamp < current_ts:
                        # Skip stale candles (should not happen if sorted and grid aligned)
                        stream_idx += 1
                    else:
                        # Gap or Padding
                        is_padding_needed = False
                        if current_ts < first_real_ts:
                            if self.config.align_symbols:
                                is_padding_needed = True
                        elif stream_idx >= len(stream):
                            if self.config.infinite_cursor:
                                is_padding_needed = True
                            else:
                                break # No more data and no infinite padding
                        else: # Gap between candles
                            if self.config.infinite_cursor:
                                is_padding_needed = True
                            else:
                                # Skip to next real candle to maintain original behavior for gaps
                                current_ts = stream[stream_idx].timestamp
                                continue

                        if is_padding_needed:
                            padded_stream.append(Candle(
                                timestamp=current_ts,
                                open=last_candle.close if last_candle else 0.0,
                                high=last_candle.close if last_candle else 0.0,
                                low=last_candle.close if last_candle else 0.0,
                                close=last_candle.close if last_candle else 0.0,
                                volume=0.0,
                                symbol=symbol,
                                timeframe=timeframe
                            ))
                            current_ts += delta
                        else:
                            break
                processed_streams.append(iter(padded_stream))
        else:
            # Standard merge sort
            for stream in symbol_streams.values():
                processed_streams.append(iter(stream))

        # Use heapq.merge for efficient multi-way merge
        def candle_key(candle):
            return candle.timestamp

        merged = list(merge(*processed_streams, key=candle_key))

        # If deterministic ordering requested, shuffle with seed
        if self._rng and self.config.seed:
            # Note: We maintain timestamp order but can shuffle within same timestamp
            # Group by timestamp and shuffle groups
            timestamp_groups: Dict[datetime, List[Candle]] = {}
            for candle in merged:
                ts = candle.timestamp
                if ts not in timestamp_groups:
                    timestamp_groups[ts] = []
                timestamp_groups[ts].append(candle)

            # Shuffle each group and flatten
            result = []
            for ts in sorted(timestamp_groups.keys()):
                group = timestamp_groups[ts]
                self._rng.shuffle(group)
                result.extend(group)

            logger.info(f"[SYNC] Synchronized {len(result)} candles with deterministic ordering (seed={self.config.seed})")
            return result

        logger.info(f"[SYNC] Synchronized {len(merged)} candles")
        return merged

    def _run_replay_loop(self) -> None:
        """
        Run the main replay loop in an async task.

        Handles REALTIME, COMPRESSED, and INSTANT modes.
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        self._loop = loop
        self._replay_task = loop.create_task(self._replay_loop())

    async def _replay_loop(self) -> None:
        """
        Main replay loop - async generator with timing control.

        Iterates through candles and applies appropriate delays based on mode.
        Handles pause/resume and stop signals.
        """
        logger.info(f"[LOOP] Starting replay loop with {self._candles_total} candles")

        last_candle_time: Optional[datetime] = None

        while True:
            # Check stop signal
            with self._state_lock:
                if self._should_stop:
                    logger.info("[LOOP] Stop signal received")
                    break

                # Check pause
                if self._is_paused:
                    await asyncio.sleep(0.1)
                    continue

                # Check if complete
                if self._current_index >= len(self._candles):
                    logger.info("[LOOP] All candles processed")
                    break

                candle = self._candles[self._current_index]
                self._current_index += 1
                self._candles_processed += 1
                self._current_time = candle.timestamp
                self._current_symbol = candle.symbol

            # Calculate and apply delay
            if last_candle_time and self.config.mode != ReplayMode.INSTANT:
                delay = self._calculate_delay(last_candle_time, candle.timestamp)
                if delay > 0:
                    await asyncio.sleep(delay)

            # Emit candle
            self._emit_candle(candle)

            last_candle_time = candle.timestamp

        # Completion
        with self._state_lock:
            self._is_running = False

        self._on_completed()

    def _calculate_delay(
        self,
        previous_time: datetime,
        current_time: datetime
    ) -> float:
        """
        Calculate sleep delay based on replay mode and compression factor.

        Args:
            previous_time: Timestamp of previous candle
            current_time: Timestamp of current candle

        Returns:
            Sleep duration in seconds
        """
        # Calculate actual time difference
        time_diff_seconds = (current_time - previous_time).total_seconds()

        if self.config.mode == ReplayMode.REALTIME:
            # Real-time: sleep the actual time difference
            return max(0, time_diff_seconds)

        elif self.config.mode == ReplayMode.COMPRESSED:
            # Compressed: divide by compression factor
            return max(0, time_diff_seconds / self.config.compression_factor)

        elif self.config.mode == ReplayMode.INSTANT:
            # Instant: no delay
            return 0.0

        elif self.config.mode == ReplayMode.STEP_THROUGH:
            # Step-through: no automatic delay
            return 0.0

        return 0.0

    def _emit_candle(self, candle: Candle) -> None:
        """
        Emit a candle to the registered callback.

        Args:
            candle: Candle to emit
        """
        if self._candle_callback:
            try:
                # Check if callback is async
                if asyncio.iscoroutinefunction(self._candle_callback):
                    # Schedule in event loop if available
                    if self._loop and self._loop.is_running():
                        asyncio.run_coroutine_threadsafe(
                            self._candle_callback(candle),
                            self._loop
                        )
                    else:
                        # Fallback: run in new event loop
                        asyncio.run(self._candle_callback(candle))
                else:
                    # Synchronous callback
                    self._candle_callback(candle)

            except Exception as e:
                logger.error(f"[EMIT] Callback error for candle {candle.symbol} @ {candle.timestamp}: {e}")

    def _on_completed(self) -> None:
        """Handle replay completion."""
        logger.info(f"[COMPLETE] Replay completed - {self._candles_processed} candles processed")

        if self._completed_callback:
            try:
                if asyncio.iscoroutinefunction(self._completed_callback):
                    if self._loop and self._loop.is_running():
                        asyncio.run_coroutine_threadsafe(
                            self._completed_callback(),
                            self._loop
                        )
                    else:
                        asyncio.run(self._completed_callback())
                else:
                    self._completed_callback()
            except Exception as e:
                logger.error(f"[COMPLETE] Completed callback error: {e}")

    def stream(self) -> Iterator[Candle]:
        """
        Synchronous streaming generator.

        Yields candles in chronological order with appropriate timing.
        Useful for integration with synchronous code.

        Yields:
            Candles in chronological order
        """
        if not self._candles:
            self._load_candles()

        last_candle_time: Optional[datetime] = None

        for i, candle in enumerate(self._candles):
            with self._state_lock:
                self._current_index = i + 1
                self._candles_processed = i + 1
                self._current_time = candle.timestamp
                self._current_symbol = candle.symbol

            # Apply delay based on mode
            if last_candle_time and self.config.mode not in [ReplayMode.INSTANT, ReplayMode.STEP_THROUGH]:
                delay = self._calculate_delay(last_candle_time, candle.timestamp)
                if delay > 0:
                    time.sleep(delay)

            yield candle
            last_candle_time = candle.timestamp

        with self._state_lock:
            self._is_running = False

        self._on_completed()

    def get_candles_for_symbol(
        self,
        symbol: str,
        timeframe: Optional[Timeframe] = None
    ) -> List[Candle]:
        """
        Get loaded candles filtered by symbol and optional timeframe.

        Args:
            symbol: Symbol to filter by
            timeframe: Optional timeframe to filter by

        Returns:
            List of matching candles
        """
        result = [c for c in self._candles if c.symbol == symbol]
        if timeframe:
            result = [c for c in result if c.timeframe == timeframe]
        return result

    def get_available_date_range(self) -> Tuple[Optional[datetime], Optional[datetime]]:
        """
        Get the date range of loaded candles.

        Returns:
            Tuple of (min_timestamp, max_timestamp) or (None, None) if no candles
        """
        if not self._candles:
            return (None, None)

        timestamps = [c.timestamp for c in self._candles]
        return (min(timestamps), max(timestamps))