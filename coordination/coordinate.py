#!/usr/bin/env python3
"""
Cross-workspace coordinator for:
- /Users/jim/work/moneyfan
- /Users/jim/work/freqtrade
- /Users/jim/work/trikeshed
- /Users/jim/work/curly-succotash

Focus:
- Lazy cached differential ingest from data.binance.vision zip archives into DuckDB
- Strategy-specific drawdown/safety-order risk profiles
- Daily orchestration for ML/HRM training and supporting services
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - compatibility for Python < 3.11
    import tomli as tomllib


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = SCRIPT_DIR / "config.toml"
DEFAULT_RUNTIME_DIR = SCRIPT_DIR / "runtime"


def load_toml(path: Path) -> Dict[str, Any]:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def parse_month(month: str) -> date:
    return datetime.strptime(month, "%Y-%m").date().replace(day=1)


def month_iter(start_month: str, end_month: str) -> Iterable[str]:
    start = parse_month(start_month)
    end = parse_month(end_month)
    cursor = start
    while cursor <= end:
        yield cursor.strftime("%Y-%m")
        year = cursor.year + (1 if cursor.month == 12 else 0)
        month = 1 if cursor.month == 12 else cursor.month + 1
        cursor = cursor.replace(year=year, month=month, day=1)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def sql_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def build_stage_display_name(
    name: str,
    pair_width_target: int,
    resolved_pair_width: int,
    effective_width: int,
) -> str:
    if resolved_pair_width < pair_width_target:
        return (
            f"{name} (capped at {resolved_pair_width}/{pair_width_target} pairs, "
            f"effective width {effective_width})"
        )
    return f"{name} ({resolved_pair_width} pairs, effective width {effective_width})"


def build_stage_notes(pair_width_target: int, resolved_pair_width: int) -> List[str]:
    notes: List[str] = []
    if resolved_pair_width < pair_width_target:
        notes.append(
            "pair width capped by current pair universe size; do not interpret this as a full-width stage"
        )
    return notes


def build_operating_posture() -> Dict[str, Any]:
    return {
        "baseline_trading": {
            "status": "active_now",
            "mode": "deterministic_paper",
            "rule": "Do not wait on HRM milestones to start capturing paper-trading opportunities.",
        },
        "hrm_role": {
            "current": "shadow",
            "rule": "HRM gathers evidence in shadow mode until it earns authority.",
            "promotion_ramp": ["shadow", "veto_only", "size_capped", "primary"],
            "promotion_requirements": [
                "synthetic convergence on cheap tasks such as sine and feature+1",
                "market forecasting beats naive baselines on walk-forward data",
                "cost-aware paper validation remains positive through the promotion gate",
            ],
        },
    }


def build_hrm_readiness_contract() -> Dict[str, Any]:
    return {
        "failure_states": [
            {
                "name": "FAIL_ARCH",
                "meaning": "cheap synthetic competence does not converge; architecture or implementation is suspect",
            },
            {
                "name": "FAIL_SCALE",
                "meaning": "task is learnable but current width, depth, or optimizer budget is mis-scaled",
            },
            {
                "name": "FAIL_TRANSFER",
                "meaning": "synthetic competence does not beat naive baselines on market forecasting tasks",
            },
            {
                "name": "FAIL_TRADING",
                "meaning": "forecasting competence does not survive cost-aware paper trading",
            },
        ],
        "synthetic_milestones": [
            {
                "name": "M0_identity",
                "tasks": ["x_to_x", "scalar_1x1_to_16x16", "ane_scalar_parity"],
                "expected_outcome": "near_zero",
            },
            {
                "name": "M1_sine",
                "tasks": ["single_sine", "mixed_sine", "noisy_sine", "piecewise_sine"],
                "expected_outcome": "near_zero_or_better_than_baseline",
            },
            {
                "name": "M2_feature_plus_1",
                "tasks": ["feature_plus_1"],
                "expected_outcome": "beats_persistence_and_ema",
            },
            {
                "name": "M3_feature_plus_n",
                "tasks": ["feature_plus_1_2_4_8"],
                "expected_outcome": "graceful_multi_horizon_degradation",
            },
        ],
        "market_gates": [
            {
                "name": "M4_walk_forward",
                "expected_outcome": "beats_naive_forecasting_baselines",
            },
            {
                "name": "M5_paper_promotion",
                "expected_outcome": "positive_cost_aware_shadow_edge",
            },
        ],
    }


@dataclass
class TaskSpec:
    name: str
    cwd: Path
    command: str
    background: bool = False
    timeout_seconds: Optional[int] = None
    requires_python: bool = False


@dataclass
class LaneSpec:
    lane_id: int
    archetype: str
    risk_tier: str
    weight: float
    fast: float
    slow: float
    sig: float
    sharp: float


class BinanceVisionDiffIngest:
    def __init__(self, cfg: Dict[str, Any]):
        self.base_url = str(cfg["base_url"]).rstrip("/")
        self.storage_mode = str(cfg.get("storage_mode", "permanent")).strip().lower()
        if self.storage_mode not in {"permanent", "tmp"}:
            raise RuntimeError(
                f"invalid binance storage_mode={self.storage_mode!r}; expected 'permanent' or 'tmp'"
            )

        permanent_cache_raw = str(cfg.get("cache_dir_permanent", cfg.get("cache_dir", ""))).strip()
        permanent_duckdb_raw = str(cfg.get("duckdb_path_permanent", cfg.get("duckdb_path", ""))).strip()
        tmp_root = Path(str(cfg.get("tmp_root", tempfile.gettempdir()))).expanduser()
        tmp_prefix = str(cfg.get("tmp_prefix", "curly-binance")).strip() or "curly-binance"

        if self.storage_mode == "permanent":
            if not permanent_cache_raw:
                raise RuntimeError("binance permanent cache_dir is missing")
            if not permanent_duckdb_raw:
                raise RuntimeError("binance permanent duckdb_path is missing")
            permanent_cache_dir = Path(permanent_cache_raw).expanduser()
            permanent_duckdb_path = Path(permanent_duckdb_raw).expanduser()
            self.cache_dir = permanent_cache_dir
            self.duckdb_path = permanent_duckdb_path
            self.storage_root = self.cache_dir.parent
        else:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            self.storage_root = tmp_root / f"{tmp_prefix}-{stamp}"
            self.cache_dir = self.storage_root / "archive_cache"
            self.duckdb_path = self.storage_root / "hrm_data.duckdb"

        self.start_month = str(cfg["start_month"])
        self.symbols = [str(x).strip().upper() for x in cfg.get("symbols", [])]
        self.timeframes = [str(x).strip() for x in cfg.get("timeframes", [])]

        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.duckdb_path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _ensure_schema(con: Any) -> None:
        def _table_type(name: str) -> Optional[str]:
            try:
                row = con.execute(
                    """
                    SELECT table_type
                    FROM information_schema.tables
                    WHERE lower(table_name) = lower(?)
                    LIMIT 1
                    """,
                    [name],
                ).fetchone()
                return str(row[0]) if row and row[0] is not None else None
            except Exception:
                return None

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS binance_klines (
                symbol VARCHAR NOT NULL,
                timeframe VARCHAR NOT NULL,
                open_time BIGINT NOT NULL,
                close_time BIGINT,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume DOUBLE,
                quote_volume DOUBLE,
                trades BIGINT,
                taker_buy_base_volume DOUBLE,
                taker_buy_quote_volume DOUBLE,
                source_file VARCHAR,
                source_url VARCHAR,
                ingest_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (symbol, timeframe, open_time)
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS binance_ingest_files (
                source_url VARCHAR PRIMARY KEY,
                source_file VARCHAR,
                sha256 VARCHAR,
                file_size_bytes BIGINT,
                total_rows BIGINT,
                inserted_rows BIGINT,
                ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Compatibility surfaces:
        # - moneyfan expects `binance_sequences_import` with timestamp semantics.
        # - trikeshed DiffDuckCursor expects `ohlcv` with (pair, timeframe, date, OHLCV).
        # Respect existing physical tables and only create/replace views when safe.
        seq_type = _table_type("binance_sequences_import")
        if seq_type != "BASE TABLE":
            con.execute(
                """
                CREATE OR REPLACE VIEW binance_sequences_import AS
                SELECT
                    symbol,
                    timeframe,
                    to_timestamp(open_time / 1000.0) AS timestamp,
                    open,
                    high,
                    low,
                    close,
                    volume,
                    quote_volume,
                    trades,
                    taker_buy_base_volume AS taker_buy_base,
                    taker_buy_quote_volume AS taker_buy_quote,
                    source_file,
                    source_url,
                    ingest_ts
                FROM binance_klines
                """
            )

        ohlcv_type = _table_type("ohlcv")
        if ohlcv_type != "BASE TABLE":
            con.execute(
                """
                CREATE OR REPLACE VIEW ohlcv AS
                SELECT
                    symbol AS pair,
                    timeframe,
                    CAST(open_time AS BIGINT) AS date,
                    open,
                    high,
                    low,
                    close,
                    volume
                FROM binance_klines
                """
            )

    def _archive_url(self, symbol: str, timeframe: str, month: str) -> str:
        name = f"{symbol}-{timeframe}-{month}.zip"
        return f"{self.base_url}/{symbol}/{timeframe}/{name}"

    def _archive_path(self, symbol: str, timeframe: str, month: str) -> Path:
        name = f"{symbol}-{timeframe}-{month}.zip"
        return self.cache_dir / symbol / timeframe / name

    def _download_if_needed(self, url: str, path: Path, timeout: int = 45) -> Tuple[bool, str]:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > 0:
            return False, "cached"

        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                if response.status != 200:
                    return False, f"http_{response.status}"
                with tempfile.NamedTemporaryFile(delete=False, dir=str(path.parent)) as tmp:
                    shutil.copyfileobj(response, tmp)
                    tmp_path = Path(tmp.name)
                tmp_path.replace(path)
                return True, "downloaded"
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return False, "missing"
            return False, f"http_{exc.code}"
        except Exception as exc:  # noqa: BLE001
            return False, f"error:{exc}"

    def _already_ingested(self, con: Any, source_url: str, digest: str) -> bool:
        row = con.execute(
            """
            SELECT 1
            FROM binance_ingest_files
            WHERE source_url = ? AND sha256 = ?
            LIMIT 1
            """,
            [source_url, digest],
        ).fetchone()
        return row is not None

    def _ingest_zip(self, con: Any, zip_path: Path, source_url: str, symbol: str, timeframe: str) -> Tuple[int, int]:
        with zipfile.ZipFile(zip_path, "r") as zf:
            members = [m for m in zf.namelist() if m.endswith(".csv")]
            if not members:
                return 0, 0
            member = members[0]

            with tempfile.TemporaryDirectory() as tmpdir:
                extracted = Path(tmpdir) / Path(member).name
                with zf.open(member) as src, extracted.open("wb") as dst:
                    shutil.copyfileobj(src, dst)

                csv_path_sql = sql_quote(str(extracted))
                symbol_sql = sql_quote(symbol)
                tf_sql = sql_quote(timeframe)
                source_file_sql = sql_quote(str(zip_path))
                source_url_sql = sql_quote(source_url)

                con.execute("DROP TABLE IF EXISTS staging_binance_klines")
                con.execute(
                    f"""
                    CREATE TEMP TABLE staging_binance_klines AS
                    SELECT
                        {symbol_sql}::VARCHAR AS symbol,
                        {tf_sql}::VARCHAR AS timeframe,
                        CAST(open_time AS BIGINT) AS open_time,
                        CAST(close_time AS BIGINT) AS close_time,
                        CAST(open AS DOUBLE) AS open,
                        CAST(high AS DOUBLE) AS high,
                        CAST(low AS DOUBLE) AS low,
                        CAST(close AS DOUBLE) AS close,
                        CAST(volume AS DOUBLE) AS volume,
                        CAST(quote_volume AS DOUBLE) AS quote_volume,
                        CAST(trades AS BIGINT) AS trades,
                        CAST(taker_buy_base_volume AS DOUBLE) AS taker_buy_base_volume,
                        CAST(taker_buy_quote_volume AS DOUBLE) AS taker_buy_quote_volume,
                        {source_file_sql}::VARCHAR AS source_file,
                        {source_url_sql}::VARCHAR AS source_url
                    FROM read_csv(
                        {csv_path_sql},
                        delim=',',
                        header=false,
                        columns={{
                            'open_time': 'BIGINT',
                            'open': 'DOUBLE',
                            'high': 'DOUBLE',
                            'low': 'DOUBLE',
                            'close': 'DOUBLE',
                            'volume': 'DOUBLE',
                            'close_time': 'BIGINT',
                            'quote_volume': 'DOUBLE',
                            'trades': 'BIGINT',
                            'taker_buy_base_volume': 'DOUBLE',
                            'taker_buy_quote_volume': 'DOUBLE',
                            'ignore_col': 'VARCHAR'
                        }}
                    )
                    """
                )

                total_rows = int(con.execute("SELECT COUNT(*) FROM staging_binance_klines").fetchone()[0])
                insertable_rows = int(
                    con.execute(
                        """
                        SELECT COUNT(*)
                        FROM staging_binance_klines s
                        LEFT JOIN binance_klines b
                          ON b.symbol = s.symbol
                         AND b.timeframe = s.timeframe
                         AND b.open_time = s.open_time
                        WHERE b.open_time IS NULL
                        """
                    ).fetchone()[0]
                )

                if insertable_rows > 0:
                    con.execute(
                        """
                        INSERT INTO binance_klines (
                            symbol,
                            timeframe,
                            open_time,
                            close_time,
                            open,
                            high,
                            low,
                            close,
                            volume,
                            quote_volume,
                            trades,
                            taker_buy_base_volume,
                            taker_buy_quote_volume,
                            source_file,
                            source_url
                        )
                        SELECT
                            s.symbol,
                            s.timeframe,
                            s.open_time,
                            s.close_time,
                            s.open,
                            s.high,
                            s.low,
                            s.close,
                            s.volume,
                            s.quote_volume,
                            s.trades,
                            s.taker_buy_base_volume,
                            s.taker_buy_quote_volume,
                            s.source_file,
                            s.source_url
                        FROM staging_binance_klines s
                        LEFT JOIN binance_klines b
                          ON b.symbol = s.symbol
                         AND b.timeframe = s.timeframe
                         AND b.open_time = s.open_time
                        WHERE b.open_time IS NULL
                        """
                    )

                return total_rows, insertable_rows

    def sync(self, start_month: Optional[str], end_month: Optional[str], max_archives: Optional[int]) -> Dict[str, Any]:
        end_month = end_month or date.today().strftime("%Y-%m")
        start_month = start_month or self.start_month

        try:
            import duckdb
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"duckdb import failed: {exc}") from exc

        con = duckdb.connect(str(self.duckdb_path))
        self._ensure_schema(con)

        stats = {
            "start_month": start_month,
            "end_month": end_month,
            "storage_mode": self.storage_mode,
            "storage_root": str(self.storage_root),
            "cache_dir": str(self.cache_dir),
            "duckdb_path": str(self.duckdb_path),
            "archives_checked": 0,
            "archives_downloaded": 0,
            "archives_ingested": 0,
            "archives_skipped_cached": 0,
            "archives_missing": 0,
            "rows_total_seen": 0,
            "rows_inserted": 0,
        }

        months = list(month_iter(start_month, end_month))

        for symbol in self.symbols:
            for timeframe in self.timeframes:
                for month in months:
                    if max_archives is not None and stats["archives_checked"] >= max_archives:
                        con.close()
                        return stats

                    stats["archives_checked"] += 1
                    url = self._archive_url(symbol, timeframe, month)
                    local_path = self._archive_path(symbol, timeframe, month)
                    downloaded, status = self._download_if_needed(url, local_path)

                    if status == "missing":
                        stats["archives_missing"] += 1
                        print(f"[SYNC] missing {symbol} {timeframe} {month}")
                        continue
                    if status.startswith("http_") or status.startswith("error:"):
                        print(f"[SYNC] skipped {symbol} {timeframe} {month} ({status})")
                        continue

                    if downloaded:
                        stats["archives_downloaded"] += 1

                    digest = sha256_file(local_path)
                    if self._already_ingested(con, url, digest):
                        stats["archives_skipped_cached"] += 1
                        print(f"[SYNC] cached {local_path.name}")
                        continue

                    total_rows, inserted_rows = self._ingest_zip(con, local_path, url, symbol, timeframe)
                    con.execute(
                        """
                        INSERT OR REPLACE INTO binance_ingest_files (
                            source_url,
                            source_file,
                            sha256,
                            file_size_bytes,
                            total_rows,
                            inserted_rows,
                            ingested_at
                        ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                        """,
                        [
                            url,
                            str(local_path),
                            digest,
                            int(local_path.stat().st_size),
                            int(total_rows),
                            int(inserted_rows),
                        ],
                    )

                    stats["archives_ingested"] += 1
                    stats["rows_total_seen"] += int(total_rows)
                    stats["rows_inserted"] += int(inserted_rows)
                    print(
                        "[SYNC] ingested "
                        f"{local_path.name} total_rows={total_rows} inserted_rows={inserted_rows}"
                    )

        con.close()
        return stats


class RiskProfilePublisher:
    def __init__(self, cfg: Dict[str, Any], training_contract: Dict[str, Any]):
        self.strategy_profiles_path = Path(cfg["strategy_profiles_path"]).expanduser()
        self.output_paths = [Path(x).expanduser() for x in cfg.get("output_paths", [])]
        self.training_contract = training_contract

    def publish(self) -> Dict[str, Any]:
        doc = load_toml(self.strategy_profiles_path)
        defaults = dict(doc.get("defaults", {}))
        profiles = list(doc.get("profiles", []))

        strategy_overrides: Dict[str, Dict[str, Any]] = {}
        for profile in profiles:
            profile_name = str(profile.get("name", "unnamed"))
            profile_cfg = {k: v for k, v in profile.items() if k not in {"name", "strategies"}}
            strategies = [str(s) for s in profile.get("strategies", [])]
            for strategy in strategies:
                strategy_overrides[strategy] = {
                    **defaults,
                    **profile_cfg,
                    "profile": profile_name,
                }

        payload = {
            "generated_at": now_iso(),
            "principles": {
                "drawdown_is_a_tool": True,
                "safety_orders_are_strategy_specific": True,
                "world_model_targets": self.training_contract.get("world_model_targets", []),
                "hrm_swimlanes": self.training_contract.get("hrm_swimlanes", 24),
                "countercoin_routing": self.training_contract.get("countercoin_routing", "dykstra"),
                "countercoin_graph_objective": self.training_contract.get(
                    "countercoin_graph_objective",
                    "slime_mold_sparse_surface_distance",
                ),
                "countercoin_bull_occupancy_policy": self.training_contract.get(
                    "countercoin_bull_occupancy_policy",
                    "bulls_anchor_countercoins",
                ),
                "leaf_coin_energy_pull_policy": self.training_contract.get(
                    "leaf_coin_energy_pull_policy",
                    "unilateral_draw_to_energy_events",
                ),
                "countercoin_trailing_bull_policy": self.training_contract.get(
                    "countercoin_trailing_bull_policy",
                    "strategic_trade_cost_discount",
                ),
                "routing_trade_cost_discount_enabled": self.training_contract.get(
                    "routing_trade_cost_discount_enabled",
                    True,
                ),
                "routing_trade_cost_discount_mode": self.training_contract.get(
                    "routing_trade_cost_discount_mode",
                    "emergent_policy_head",
                ),
                "routing_trade_cost_discount_emergent": self.training_contract.get(
                    "routing_trade_cost_discount_emergent",
                    True,
                ),
                "routing_trade_cost_discount_bps_floor": self.training_contract.get(
                    "routing_trade_cost_discount_bps_floor",
                    0.0,
                ),
                "routing_trade_cost_discount_bps_cap": self.training_contract.get(
                    "routing_trade_cost_discount_bps_cap",
                    12.0,
                ),
                "latent_transform": self.training_contract.get("latent_transform", "hyperbolic"),
                "universal_trade_wind_tunnel": self.training_contract.get("universal_trade_wind_tunnel", True),
                "axiom_driven_generalization": self.training_contract.get("axiom_driven_generalization", True),
                "candle_depth_required": self.training_contract.get("candle_depth_required", True),
                "horizon_compression": self.training_contract.get("horizon_compression", "hyperbolic_timeseries"),
                "volatility_time_unit_invariance": self.training_contract.get("volatility_time_unit_invariance", True),
            },
            "defaults": defaults,
            "profiles": profiles,
            "strategy_overrides": strategy_overrides,
        }

        for out_path in self.output_paths:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            print(f"[RISK] wrote {out_path}")

        return {
            "output_count": len(self.output_paths),
            "strategy_count": len(strategy_overrides),
        }


class SwimlaneManifestPublisher:
    def __init__(self, cfg: Dict[str, Any], training_contract: Dict[str, Any]):
        self.cfg = cfg
        self.training_contract = training_contract
        self.output_json_paths = [Path(x).expanduser() for x in cfg.get("output_json_paths", [])]
        self.output_dsel_paths = [Path(x).expanduser() for x in cfg.get("output_dsel_paths", [])]

    def _growth_capacity(self, target_width: int) -> Tuple[int, int, int]:
        growth_base = max(int(self.cfg.get("growth_base", 2)), 2)
        square_power = max(int(self.cfg.get("square_power", 2)), 1)
        cube_power = max(int(self.cfg.get("cube_power", 3)), 1)
        growth_factor = (growth_base**square_power) ** cube_power

        width = 1
        steps = 0
        while width < target_width:
            width *= growth_factor
            steps += 1
        return int(width), int(steps), int(growth_factor)

    def _build_lane_specs(self, lane_count: int) -> List[LaneSpec]:
        layout = list(self.cfg.get("layout", []))
        lanes: List[LaneSpec] = []

        for row in layout:
            archetype = str(row.get("archetype", "")).strip().lower()
            if not archetype:
                continue
            count = max(int(row.get("count", 0)), 0)
            risk_tier = str(row.get("risk_tier", "normal")).strip().lower()
            weight = float(row.get("weight", 1.0))
            fast = float(row.get("fast", 12.0))
            slow = float(row.get("slow", 26.0))
            sig = float(row.get("sig", 9.0))
            sharp = float(row.get("sharp", 1.0))

            for _ in range(count):
                if len(lanes) >= lane_count:
                    break
                lanes.append(
                    LaneSpec(
                        lane_id=len(lanes),
                        archetype=archetype,
                        risk_tier=risk_tier,
                        weight=weight,
                        fast=fast,
                        slow=slow,
                        sig=sig,
                        sharp=sharp,
                    )
                )
            if len(lanes) >= lane_count:
                break

        fallback_archetype = str(self.cfg.get("fallback_archetype", "momentum")).strip().lower()
        fallback_row = next(
            (
                row
                for row in layout
                if str(row.get("archetype", "")).strip().lower() == fallback_archetype
            ),
            None,
        )
        fallback_risk_tier = str((fallback_row or {}).get("risk_tier", "normal")).strip().lower()
        fallback_weight = float((fallback_row or {}).get("weight", 1.0))
        fallback_fast = float((fallback_row or {}).get("fast", 12.0))
        fallback_slow = float((fallback_row or {}).get("slow", 26.0))
        fallback_sig = float((fallback_row or {}).get("sig", 9.0))
        fallback_sharp = float((fallback_row or {}).get("sharp", 1.0))

        while len(lanes) < lane_count:
            lanes.append(
                LaneSpec(
                    lane_id=len(lanes),
                    archetype=fallback_archetype,
                    risk_tier=fallback_risk_tier,
                    weight=fallback_weight,
                    fast=fallback_fast,
                    slow=fallback_slow,
                    sig=fallback_sig,
                    sharp=fallback_sharp,
                )
            )

        required = {str(x).strip().lower() for x in self.cfg.get("required_archetypes", []) if str(x).strip()}
        present = {lane.archetype for lane in lanes}
        missing = sorted(required - present)
        if missing:
            raise RuntimeError(f"swimlane contract missing required archetypes: {', '.join(missing)}")

        return lanes

    @staticmethod
    def _q(value: float) -> str:
        return f"q({value:.6g})"

    def _render_dsel(self, payload: Dict[str, Any]) -> str:
        lines = [
            "# hrm_swimlanes.dsel v1",
            (
                "# lane_count="
                f"{payload['lane_count']} "
                f"effective_width={payload['effective_width']} "
                f"growth_factor={payload['width_growth_factor']} "
                f"growth_steps={payload['width_growth_steps']}"
            ),
        ]
        for lane in payload.get("lanes", []):
            lines.append(
                "lane "
                f"{int(lane['lane_id'])} "
                f"archetype={lane['archetype']} "
                f"risk={lane['risk_tier']} "
                f"weight={self._q(float(lane['weight']))} "
                f"fast={self._q(float(lane['fast']))} "
                f"slow={self._q(float(lane['slow']))} "
                f"sig={self._q(float(lane['sig']))} "
                f"sharp={self._q(float(lane['sharp']))}"
            )
        return "\n".join(lines) + "\n"

    def publish(self) -> Dict[str, Any]:
        lane_count = int(self.cfg.get("lane_count", self.training_contract.get("hrm_swimlanes", 24)))
        min_effective_width = max(lane_count, int(self.cfg.get("min_effective_width", lane_count)))
        effective_width, growth_steps, growth_factor = self._growth_capacity(min_effective_width)
        lanes = self._build_lane_specs(lane_count)
        required_archetypes = [str(x).strip().lower() for x in self.cfg.get("required_archetypes", [])]

        payload = {
            "generated_at": now_iso(),
            "lane_count": int(lane_count),
            "required_archetypes": required_archetypes,
            "effective_width": int(effective_width),
            "min_effective_width": int(min_effective_width),
            "width_growth_factor": int(growth_factor),
            "width_growth_steps": int(growth_steps),
            "width_growth_rule": "repeated((2^2)^3)",
            "lanes": [
                {
                    "lane_id": lane.lane_id,
                    "archetype": lane.archetype,
                    "risk_tier": lane.risk_tier,
                    "weight": lane.weight,
                    "fast": lane.fast,
                    "slow": lane.slow,
                    "sig": lane.sig,
                    "sharp": lane.sharp,
                }
                for lane in lanes
            ],
        }

        dsel_text = self._render_dsel(payload)

        for out_path in self.output_json_paths:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            print(f"[SWIMLANE] wrote json {out_path}")

        for out_path in self.output_dsel_paths:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(dsel_text, encoding="utf-8")
            print(f"[SWIMLANE] wrote dsel {out_path}")

        return {
            "lane_count": lane_count,
            "json_outputs": len(self.output_json_paths),
            "dsel_outputs": len(self.output_dsel_paths),
            "effective_width": effective_width,
            "growth_steps": growth_steps,
            "growth_factor": growth_factor,
            "required_archetypes": required_archetypes,
        }


class WorkspaceCoordinator:
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.config = load_toml(config_path)
        self.workspace_paths = {
            k: Path(v).expanduser() for k, v in self.config.get("workspace_paths", {}).items()
        }
        self.training_contract = dict(self.config.get("training_contract", {}))
        self.swimlane_contract = dict(self.config.get("swimlane_contract", {}))
        self.connectome_contract = dict(self.config.get("connectome", {}))
        self.harness_contract = dict(self.config.get("harness", {}))

    def _tasks_for_today(self, include_python: bool = False) -> List[TaskSpec]:
        tasks = []
        for raw in self.config.get("tasks", {}).get("today", []):
            task = TaskSpec(
                name=str(raw["name"]),
                cwd=Path(raw["cwd"]).expanduser(),
                command=str(raw["command"]),
                background=bool(raw.get("background", False)),
                timeout_seconds=int(raw["timeout_seconds"]) if raw.get("timeout_seconds") else None,
                requires_python=bool(raw.get("requires_python", False)),
            )
            if task.requires_python and not include_python:
                continue
            tasks.append(task)
        return tasks

    def status(self) -> int:
        print(f"Config: {self.config_path}")
        print(f"Now:    {now_iso()}")
        print("\nTraining Contract")
        for key in [
            "world_model_targets",
            "hrm_swimlanes",
            "market_scope",
            "map_reduce_groups",
            "countercoin_routing",
            "countercoin_graph_objective",
            "countercoin_bull_occupancy_policy",
            "leaf_coin_energy_pull_policy",
            "countercoin_trailing_bull_policy",
            "routing_trade_cost_discount_enabled",
            "routing_trade_cost_discount_mode",
            "routing_trade_cost_discount_emergent",
            "routing_trade_cost_discount_bps_floor",
            "routing_trade_cost_discount_bps_cap",
            "latent_transform",
            "universal_trade_wind_tunnel",
            "axiom_driven_generalization",
            "candle_depth_required",
            "horizon_compression",
            "volatility_time_unit_invariance",
        ]:
            print(f"  - {key}: {self.training_contract.get(key)}")

        binance_cfg = dict(self.config.get("binance_vision", {}))
        print("\nBinance Storage")
        print(f"  - storage_mode: {binance_cfg.get('storage_mode', 'permanent')}")
        print(f"  - cache_dir_permanent: {binance_cfg.get('cache_dir_permanent', binance_cfg.get('cache_dir'))}")
        print(
            "  - duckdb_path_permanent: "
            f"{binance_cfg.get('duckdb_path_permanent', binance_cfg.get('duckdb_path'))}"
        )
        print(f"  - tmp_root: {binance_cfg.get('tmp_root', tempfile.gettempdir())}")
        print(f"  - tmp_prefix: {binance_cfg.get('tmp_prefix', 'curly-binance')}")

        if self.swimlane_contract:
            print("\nSwimlane Contract")
            print(f"  - lane_count: {self.swimlane_contract.get('lane_count')}")
            print(f"  - required_archetypes: {self.swimlane_contract.get('required_archetypes', [])}")
            print(f"  - fallback_archetype: {self.swimlane_contract.get('fallback_archetype')}")
            print(
                "  - width_growth_rule: repeated((2^2)^3) with "
                f"base={self.swimlane_contract.get('growth_base', 2)} "
                f"square_power={self.swimlane_contract.get('square_power', 2)} "
                f"cube_power={self.swimlane_contract.get('cube_power', 3)}"
            )
            print(f"  - min_effective_width: {self.swimlane_contract.get('min_effective_width')}")
            layout = list(self.swimlane_contract.get("layout", []))
            for row in layout:
                archetype = row.get("archetype")
                count = row.get("count")
                print(f"    * {archetype}: count={count}")

        if self.connectome_contract:
            print("\nConnectome Contract")
            print(f"  - timeframe: {self.connectome_contract.get('timeframe', '5m')}")
            print(f"  - min_rows_per_symbol: {self.connectome_contract.get('min_rows_per_symbol', 256)}")
            print(f"  - max_symbols: {self.connectome_contract.get('max_symbols', 0)}")
            print(f"  - anchors: {self.connectome_contract.get('anchors', ['BTCUSDT', 'ETHUSDT', 'SOLUSDT'])}")

        if self.harness_contract:
            print("\nHarness Contract")
            stages = list(self.harness_contract.get("stages", []))
            print(f"  - stages: {len(stages)}")
            for row in stages:
                print(
                    "    * "
                    f"{row.get('name', 'stage')} "
                    f"pair_width={row.get('pair_width')} "
                    f"codec_outputs={row.get('codec_outputs')} "
                    f"effective_width={row.get('effective_width')}"
                )

        print("\nWorkspaces")
        for name, path in self.workspace_paths.items():
            exists = path.exists()
            print(f"  - {name}: {path} {'(ok)' if exists else '(missing)'}")
            if not exists:
                continue
            branch = self._safe_git(path, ["rev-parse", "--abbrev-ref", "HEAD"])
            dirty = self._safe_git(path, ["status", "--short"])
            print(f"      branch={branch.strip() if branch else 'unknown'}")
            if dirty.strip():
                first_line = dirty.strip().splitlines()[0]
                print(f"      dirty=yes sample={first_line}")
            else:
                print("      dirty=no")

        native_tasks = self._tasks_for_today(include_python=False)
        all_tasks = self._tasks_for_today(include_python=True)
        python_tasks = [task for task in all_tasks if task.requires_python]

        print("\nToday Tasks (Non-Python Domain)")
        for task in native_tasks:
            kind = "background" if task.background else "oneshot"
            print(f"  - {task.name} [{kind}] {task.command}")
        if not native_tasks:
            print("  - none")

        print("\nPython Minimum Tasks (On-Demand)")
        for task in python_tasks:
            kind = "background" if task.background else "oneshot"
            print(f"  - {task.name} [{kind}] {task.command}")
        if not python_tasks:
            print("  - none")

        return 0

    @staticmethod
    def _safe_git(repo: Path, args: List[str]) -> str:
        try:
            result = subprocess.run(
                ["git", "-C", str(repo), *args],
                check=False,
                capture_output=True,
                text=True,
            )
            return result.stdout
        except Exception:  # noqa: BLE001
            return ""

    def sync_binance(
        self,
        start_month: Optional[str],
        end_month: Optional[str],
        max_archives: Optional[int],
        storage_mode: Optional[str] = None,
    ) -> int:
        binance_cfg = dict(self.config["binance_vision"])
        if storage_mode:
            binance_cfg["storage_mode"] = storage_mode
        syncer = BinanceVisionDiffIngest(binance_cfg)
        stats = syncer.sync(start_month=start_month, end_month=end_month, max_archives=max_archives)
        DEFAULT_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        (DEFAULT_RUNTIME_DIR / "last_sync_stats.json").write_text(
            json.dumps(stats, indent=2),
            encoding="utf-8",
        )
        print("\n[SYNC] Summary")
        print(json.dumps(stats, indent=2))
        return 0

    def publish_risk(self) -> int:
        publisher = RiskProfilePublisher(self.config["risk_profiles"], self.training_contract)
        stats = publisher.publish()
        print("\n[RISK] Summary")
        print(json.dumps(stats, indent=2))
        return 0

    def publish_swimlanes(self, min_effective_width: Optional[int] = None) -> int:
        if not self.swimlane_contract:
            print("[SWIMLANE] skipped (no [swimlane_contract] in config)")
            return 0
        contract = dict(self.swimlane_contract)
        if min_effective_width is not None and int(min_effective_width) > 0:
            contract["min_effective_width"] = int(min_effective_width)
        publisher = SwimlaneManifestPublisher(contract, self.training_contract)
        stats = publisher.publish()
        print("\n[SWIMLANE] Summary")
        print(json.dumps(stats, indent=2))
        return 0

    @staticmethod
    def _normalize_symbol(raw: str) -> str:
        return "".join(ch for ch in str(raw or "").upper() if ch.isalnum())

    @staticmethod
    def _dedupe_symbols(symbols: List[str]) -> List[str]:
        out: List[str] = []
        seen = set()
        for sym in symbols:
            if not sym:
                continue
            if sym in seen:
                continue
            seen.add(sym)
            out.append(sym)
        return out

    def _resolve_binance_duckdb_path(self, storage_mode: Optional[str] = None) -> Path:
        cfg = dict(self.config.get("binance_vision", {}))
        mode = str(storage_mode or cfg.get("storage_mode", "permanent")).strip().lower()
        if mode == "permanent":
            raw = str(cfg.get("duckdb_path_permanent", cfg.get("duckdb_path", ""))).strip()
            if not raw:
                raise RuntimeError("binance_vision duckdb path is not configured")
            return Path(raw).expanduser()

        # tmp mode: try the most recent synced tmp session first.
        last_sync_file = DEFAULT_RUNTIME_DIR / "last_sync_stats.json"
        if last_sync_file.exists():
            try:
                doc = json.loads(last_sync_file.read_text(encoding="utf-8"))
                if str(doc.get("storage_mode", "")).strip().lower() == "tmp":
                    raw = str(doc.get("duckdb_path", "")).strip()
                    if raw:
                        p = Path(raw).expanduser()
                        if p.exists():
                            return p
            except Exception:
                pass

        tmp_root = Path(str(cfg.get("tmp_root", tempfile.gettempdir()))).expanduser()
        tmp_prefix = str(cfg.get("tmp_prefix", "curly-binance")).strip() or "curly-binance"
        candidates = sorted(tmp_root.glob(f"{tmp_prefix}-*/hrm_data.duckdb"))
        if candidates:
            return candidates[-1]

        raise RuntimeError(
            "tmp DuckDB path not found. Run sync-binance with --storage-mode tmp first."
        )

    @staticmethod
    def _extract_symbols_from_text_lines(lines: Iterable[str]) -> List[str]:
        out: List[str] = []
        for line in lines:
            text = str(line or "").strip()
            if not text or text.startswith("#"):
                continue
            # Supports lines like:
            # - BTCUSDT
            # - BTCUSDT/5m
            # - import/BTCUSDT/5m
            token = text.split()[0]
            parts = [p for p in token.split("/") if p]
            candidates = parts if parts else [token]
            symbol = ""
            for candidate in candidates:
                norm = "".join(ch for ch in candidate.upper() if ch.isalnum())
                if len(norm) >= 5 and norm[-3:].isalpha():
                    symbol = norm
            if not symbol:
                symbol = "".join(ch for ch in token.upper() if ch.isalnum())
            if symbol:
                out.append(symbol)
        return WorkspaceCoordinator._dedupe_symbols(out)

    def build_connectome(
        self,
        storage_mode: Optional[str] = None,
        max_symbols_override: Optional[int] = None,
    ) -> int:
        cfg = dict(self.connectome_contract or {})
        timeframe = str(cfg.get("timeframe", "5m")).strip() or "5m"
        min_rows = max(int(cfg.get("min_rows_per_symbol", 256)), 1)
        max_symbols = int(max_symbols_override if max_symbols_override is not None else cfg.get("max_symbols", 0))
        anchors = [self._normalize_symbol(x) for x in cfg.get("anchors", ["BTCUSDT", "ETHUSDT", "SOLUSDT"])]
        anchors = [x for x in anchors if x]

        out_json = Path(
            str(
                cfg.get(
                    "output_json_path",
                    DEFAULT_RUNTIME_DIR / "binance_connectome_universe.json",
                )
            )
        ).expanduser()
        out_symbols = Path(
            str(
                cfg.get(
                    "output_symbols_path",
                    DEFAULT_RUNTIME_DIR / "binance_connectome_symbols.txt",
                )
            )
        ).expanduser()

        script_symbols: List[str] = []
        script_command = str(cfg.get("script_command", "")).strip()
        script_cwd_raw = str(cfg.get("script_cwd", "")).strip()
        if script_command:
            try:
                script_cwd = Path(script_cwd_raw).expanduser() if script_cwd_raw else None
                proc = subprocess.run(
                    script_command,
                    cwd=str(script_cwd) if script_cwd else None,
                    shell=True,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    script_symbols = self._extract_symbols_from_text_lines(proc.stdout.splitlines())
                elif proc.returncode == 0:
                    print(f"[CONNECTOME] script produced no symbols cmd={script_command}")
                else:
                    print(
                        f"[CONNECTOME] script skipped rc={proc.returncode} cmd={script_command}"
                    )
            except Exception as exc:  # noqa: BLE001
                print(f"[CONNECTOME] script failed: {exc}")

        duckdb_path = self._resolve_binance_duckdb_path(storage_mode=storage_mode)
        if not duckdb_path.exists():
            raise RuntimeError(f"DuckDB corpus missing: {duckdb_path}")

        try:
            import duckdb
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"duckdb import failed: {exc}") from exc

        con = duckdb.connect(str(duckdb_path), read_only=True)
        rows_by_symbol: Dict[str, int] = {}
        symbols_in_db: List[str] = []
        try:
            tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
            if "binance_klines" in tables:
                rows = con.execute(
                    """
                    SELECT symbol, COUNT(*)::BIGINT AS n
                    FROM binance_klines
                    WHERE timeframe = ?
                    GROUP BY symbol
                    ORDER BY n DESC, symbol ASC
                    """,
                    [timeframe],
                ).fetchall()
            elif "ohlcv" in tables:
                rows = con.execute(
                    """
                    SELECT pair AS symbol, COUNT(*)::BIGINT AS n
                    FROM ohlcv
                    WHERE timeframe = ?
                    GROUP BY pair
                    ORDER BY n DESC, pair ASC
                    """,
                    [timeframe],
                ).fetchall()
            else:
                rows = []

            for symbol, n in rows:
                sym = self._normalize_symbol(symbol)
                if not sym:
                    continue
                rows_by_symbol[sym] = int(n)
            symbols_in_db = list(rows_by_symbol.keys())
        finally:
            con.close()

        if not symbols_in_db:
            raise RuntimeError(
                f"No symbols discovered in DuckDB for timeframe={timeframe} path={duckdb_path}"
            )

        if script_symbols:
            candidates = [s for s in script_symbols if s in rows_by_symbol]
            source_tag = "script+duckdb"
        else:
            candidates = list(symbols_in_db)
            source_tag = "duckdb"

        filtered = [s for s in candidates if int(rows_by_symbol.get(s, 0)) >= min_rows]
        for anchor in anchors:
            if anchor not in rows_by_symbol:
                raise RuntimeError(
                    f"Required countercoin anchor {anchor} not present in DuckDB {duckdb_path}"
                )
            if anchor not in filtered:
                filtered.append(anchor)

        filtered = self._dedupe_symbols(
            sorted(filtered, key=lambda s: (-int(rows_by_symbol.get(s, 0)), s))
        )
        if max_symbols > 0:
            filtered = filtered[:max_symbols]
            for anchor in anchors:
                if anchor not in filtered:
                    filtered.append(anchor)
            filtered = self._dedupe_symbols(filtered)

        payload = {
            "generated_at": now_iso(),
            "source": source_tag,
            "timeframe": timeframe,
            "duckdb_path": str(duckdb_path),
            "min_rows_per_symbol": min_rows,
            "max_symbols": max_symbols,
            "anchors": anchors,
            "script_command": script_command or None,
            "script_symbol_count": len(script_symbols),
            "duckdb_symbol_count": len(symbols_in_db),
            "selected_symbol_count": len(filtered),
            "selected_symbols": filtered,
            "rows_by_symbol": {s: int(rows_by_symbol.get(s, 0)) for s in filtered},
        }

        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_symbols.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        out_symbols.write_text("\n".join(filtered) + "\n", encoding="utf-8")

        print("\n[CONNECTOME] Summary")
        print(json.dumps({
            "output_json_path": str(out_json),
            "output_symbols_path": str(out_symbols),
            "selected_symbol_count": len(filtered),
            "anchors": anchors,
            "duckdb_path": str(duckdb_path),
        }, indent=2))
        return 0

    @staticmethod
    def _load_symbols_file(path: Path) -> List[str]:
        text = path.read_text(encoding="utf-8")
        symbols = []
        for line in text.splitlines():
            token = line.split("#", 1)[0].strip()
            if not token:
                continue
            sym = "".join(ch for ch in token.upper() if ch.isalnum())
            if sym:
                symbols.append(sym)
        return WorkspaceCoordinator._dedupe_symbols(symbols)

    def emit_harness(
        self,
        storage_mode: Optional[str] = None,
        pair_universe_path: Optional[str] = None,
    ) -> int:
        cfg = dict(self.harness_contract or {})
        connectome_cfg = dict(self.connectome_contract or {})

        out_json = Path(
            str(cfg.get("output_path", DEFAULT_RUNTIME_DIR / "hrm_training_harness.json"))
        ).expanduser()
        out_sh = Path(
            str(cfg.get("output_shell_path", DEFAULT_RUNTIME_DIR / "run_hrm_harness.sh"))
        ).expanduser()
        out_codex = Path(
            str(cfg.get("output_codex_path", DEFAULT_RUNTIME_DIR / "hrm_training_codex.md"))
        ).expanduser()

        if pair_universe_path:
            symbols_path = Path(pair_universe_path).expanduser()
        else:
            symbols_path = Path(
                str(
                    connectome_cfg.get(
                        "output_symbols_path",
                        DEFAULT_RUNTIME_DIR / "binance_connectome_symbols.txt",
                    )
                )
            ).expanduser()

        if not symbols_path.exists():
            print(f"[HARNESS] pair universe missing at {symbols_path}; building connectome first")
            rc = self.build_connectome(storage_mode=storage_mode, max_symbols_override=None)
            if rc != 0:
                return rc
        if not symbols_path.exists():
            raise RuntimeError(f"pair universe file missing: {symbols_path}")

        symbols = self._load_symbols_file(symbols_path)
        if not symbols:
            raise RuntimeError(f"pair universe is empty: {symbols_path}")

        duckdb_path = self._resolve_binance_duckdb_path(storage_mode=storage_mode)
        swimlane_dsel = Path(
            str(
                cfg.get(
                    "swimlane_dsel_path",
                    (self.swimlane_contract.get("output_dsel_paths", [DEFAULT_RUNTIME_DIR / "hrm_swimlanes.dsel"])[0]),
                )
            )
        ).expanduser()

        stages = list(cfg.get("stages", []))
        if not stages:
            stages = [
                {
                    "name": "convergence_4x4",
                    "pair_width": 4,
                    "codec_outputs": 4,
                    "effective_width": 4,
                    "max_training_seconds": 1800,
                    "episodes": 100000,
                    "bar_sequences_per_episode": 64,
                },
                {
                    "name": "hrm_24x24",
                    "pair_width": 24,
                    "codec_outputs": 24,
                    "effective_width": 24,
                    "max_training_seconds": 3600,
                    "episodes": 100000,
                    "bar_sequences_per_episode": 100,
                },
                {
                    "name": "hrm_24x64",
                    "pair_width": 64,
                    "codec_outputs": 24,
                    "effective_width": 64,
                    "max_training_seconds": 7200,
                    "episodes": 100000,
                    "bar_sequences_per_episode": 120,
                },
                {
                    "name": "hrm_24x512",
                    "pair_width": 512,
                    "codec_outputs": 24,
                    "effective_width": 512,
                    "max_training_seconds": 21600,
                    "episodes": 100000,
                    "bar_sequences_per_episode": 160,
                },
            ]

        moneyfan = self.workspace_paths.get("moneyfan", Path("/missing/moneyfan"))
        operating_posture = build_operating_posture()
        readiness_contract = build_hrm_readiness_contract()
        stages_out: List[Dict[str, Any]] = []
        shell_lines = [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            "",
            f"cd {shlex.quote(str(moneyfan))}",
            "",
        ]

        for stage in stages:
            name = str(stage.get("name", "stage"))
            pair_width_target = max(int(stage.get("pair_width", 24)), 1)
            codec_outputs = max(int(stage.get("codec_outputs", 24)), 1)
            effective_width = max(int(stage.get("effective_width", pair_width_target)), 1)
            max_training_seconds = max(int(stage.get("max_training_seconds", 3600)), 1)
            episodes = max(int(stage.get("episodes", 100000)), 1)
            bar_sequences = max(int(stage.get("bar_sequences_per_episode", 100)), 1)
            min_bar_window = max(int(stage.get("min_bar_window", 64)), 1)
            max_bar_window = max(int(stage.get("max_bar_window", 256)), min_bar_window)
            candles_per_extent = max(int(stage.get("candles_per_extent", 2000)), max_bar_window)

            resolved_pair_width = min(pair_width_target, len(symbols))
            display_name = build_stage_display_name(
                name=name,
                pair_width_target=pair_width_target,
                resolved_pair_width=resolved_pair_width,
                effective_width=effective_width,
            )
            stage_notes = build_stage_notes(
                pair_width_target=pair_width_target,
                resolved_pair_width=resolved_pair_width,
            )
            publish_width_cmd = (
                f"python3 coordination/coordinate.py publish-swimlanes --min-effective-width {effective_width}"
            )
            train_cmd = (
                "python3 museum/train.py "
                "--pretrain-only --timer-based "
                f"--max-training-seconds {max_training_seconds} "
                f"--episodes {episodes} "
                f"--pair-width {resolved_pair_width} "
                f"--min-pair-width {resolved_pair_width} "
                f"--max-pair-width {resolved_pair_width} "
                f"--codec-outputs {codec_outputs} "
                f"--bar-sequences-per-episode {bar_sequences} "
                f"--min-bar-window {min_bar_window} "
                f"--max-bar-window {max_bar_window} "
                f"--candles-per-extent {candles_per_extent} "
                "--ob-decay-mode hyperbolic --ob-hyperbolic-tau 24 "
                "--learning-rate 1e-4 "
                "--candle-source duckdb_sequences_import "
                f"--duckdb-corpus-path {shlex.quote(str(duckdb_path))} "
                f"--pair-universe-file {shlex.quote(str(symbols_path))}"
            )

            stages_out.append(
                {
                    "name": name,
                    "display_name": display_name,
                    "pair_width_target": pair_width_target,
                    "pair_width_resolved": resolved_pair_width,
                    "codec_outputs": codec_outputs,
                    "effective_width_target": effective_width,
                    "max_training_seconds": max_training_seconds,
                    "episodes": episodes,
                    "bar_sequences_per_episode": bar_sequences,
                    "stage_notes": stage_notes,
                    "publish_swimlane_width_command": publish_width_cmd,
                    "train_command": train_cmd,
                }
            )
            shell_lines.append(f"echo \"[HARNESS] Stage {display_name}\"")
            for note in stage_notes:
                shell_lines.append(f"echo \"[HARNESS][NOTE] {note}\"")
            shell_lines.append(f"cd {shlex.quote(str(self.workspace_paths.get('curly_succotash', SCRIPT_DIR.parent)))}")
            shell_lines.append(publish_width_cmd)
            shell_lines.append(f"cd {shlex.quote(str(moneyfan))}")
            shell_lines.append(train_cmd)
            shell_lines.append("")

        payload = {
            "generated_at": now_iso(),
            "duckdb_path": str(duckdb_path),
            "pair_universe_path": str(symbols_path),
            "pair_universe_count": len(symbols),
            "swimlane_dsel_path": str(swimlane_dsel),
            "operating_posture": operating_posture,
            "readiness_contract": readiness_contract,
            "stages": stages_out,
        }

        codex_lines = [
            "# HRM Training Codex",
            "",
            f"- generated_at: {payload['generated_at']}",
            f"- duckdb_path: {payload['duckdb_path']}",
            f"- pair_universe_path: {payload['pair_universe_path']}",
            f"- pair_universe_count: {payload['pair_universe_count']}",
            "",
            "## Operating Posture",
            "",
            f"- baseline_trading_status: {operating_posture['baseline_trading']['status']}",
            f"- baseline_trading_mode: {operating_posture['baseline_trading']['mode']}",
            f"- baseline_rule: {operating_posture['baseline_trading']['rule']}",
            f"- hrm_current_role: {operating_posture['hrm_role']['current']}",
            f"- hrm_role_rule: {operating_posture['hrm_role']['rule']}",
            "",
            "### HRM Promotion Ramp",
            *(f"- {phase}" for phase in operating_posture["hrm_role"]["promotion_ramp"]),
            "",
            "### HRM Promotion Requirements",
            *(f"- {rule}" for rule in operating_posture["hrm_role"]["promotion_requirements"]),
            "",
            "## Readiness Contract",
            "",
            "### Failure States",
            *(
                f"- {row['name']}: {row['meaning']}"
                for row in readiness_contract["failure_states"]
            ),
            "",
            "### Synthetic Milestones",
            *(
                f"- {row['name']}: tasks={','.join(row['tasks'])} | expected={row['expected_outcome']}"
                for row in readiness_contract["synthetic_milestones"]
            ),
            "",
            "### Market Gates",
            *(
                f"- {row['name']}: expected={row['expected_outcome']}"
                for row in readiness_contract["market_gates"]
            ),
            "",
            "## Stages",
            "",
        ]
        for row in stages_out:
            codex_lines.extend(
                [
                    f"### {row['display_name']}",
                    f"- stage_name: {row['name']}",
                    f"- pair_width_target: {row['pair_width_target']}",
                    f"- pair_width_resolved: {row['pair_width_resolved']}",
                    f"- codec_outputs: {row['codec_outputs']}",
                    f"- effective_width_target: {row['effective_width_target']}",
                    f"- max_training_seconds: {row['max_training_seconds']}",
                    f"- bar_sequences_per_episode: {row['bar_sequences_per_episode']}",
                    f"- publish_swimlane_width_command: `{row['publish_swimlane_width_command']}`",
                    f"- train_command: `{row['train_command']}`",
                ]
            )
            codex_lines.extend([f"- note: {note}" for note in row["stage_notes"]])
            codex_lines.append("")

        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_sh.parent.mkdir(parents=True, exist_ok=True)
        out_codex.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        out_sh.write_text("\n".join(shell_lines).rstrip() + "\n", encoding="utf-8")
        out_codex.write_text("\n".join(codex_lines).rstrip() + "\n", encoding="utf-8")
        out_sh.chmod(0o755)

        print("\n[HARNESS] Summary")
        print(json.dumps({
            "output_path": str(out_json),
            "shell_path": str(out_sh),
            "codex_path": str(out_codex),
            "stages": [row["name"] for row in stages_out],
            "pair_universe_count": len(symbols),
        }, indent=2))
        return 0

    @staticmethod
    def _file_contains(path: Path, patterns: List[str]) -> Tuple[bool, List[str]]:
        if not path.exists():
            return False, patterns
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            return False, patterns
        missing = [pattern for pattern in patterns if pattern not in text]
        return len(missing) == 0, missing

    def nexus_status(self) -> int:
        """
        Validate the concrete Kotlingrad + Cursor integration seam (the "nexus")
        across moneyfan, freqtrade, trikeshed, and this coordinator workspace.
        """
        print("[NEXUS] Kotlingrad + Cursor integration status")
        print(f"[NEXUS] Timestamp: {now_iso()}")

        freqtrade = self.workspace_paths.get("freqtrade", Path("/missing/freqtrade"))
        trikeshed = self.workspace_paths.get("trikeshed", Path("/missing/trikeshed"))
        moneyfan = self.workspace_paths.get("moneyfan", Path("/missing/moneyfan"))

        checks: List[Tuple[str, bool, str]] = []

        swimlane_json = freqtrade / "user_data" / "hrm_swimlanes.json"
        swimlane_ok = False
        swimlane_lane_count = 0
        if swimlane_json.exists():
            try:
                doc = json.loads(swimlane_json.read_text(encoding="utf-8"))
                lanes = list(doc.get("lanes", []))
                swimlane_lane_count = len(lanes)
                swimlane_ok = swimlane_lane_count >= 24
            except Exception:  # noqa: BLE001
                swimlane_ok = False
        checks.append(
            (
                "freqtrade swimlane manifest",
                swimlane_ok,
                f"{swimlane_json} (lanes={swimlane_lane_count})",
            )
        )

        kotlingrad_manifest = freqtrade / "user_data" / "hrm_kotlingrad_expressions.json"
        manifest_ok = False
        alias_count = 0
        expr_count = 0
        if kotlingrad_manifest.exists():
            try:
                doc = json.loads(kotlingrad_manifest.read_text(encoding="utf-8"))
                aliases = doc.get("aliases", {})
                expr = doc.get("expressions", [])
                alias_count = len(aliases)
                expr_count = len(expr)
                manifest_ok = alias_count >= 24 and expr_count >= 24
            except Exception:  # noqa: BLE001
                manifest_ok = False
        checks.append(
            (
                "freqtrade Kotlingrad expression manifest",
                manifest_ok,
                f"{kotlingrad_manifest} (expressions={expr_count}, aliases={alias_count})",
            )
        )

        generated_kotlin = (
            freqtrade
            / "src"
            / "kotlin-engine"
            / "src"
            / "nativeMain"
            / "kotlin"
            / "borg"
            / "trikeshed"
            / "duck"
            / "GeneratedHrmKotlingradExpressions.kt"
        )
        ok, missing = self._file_contains(
            generated_kotlin,
            [
                "internal object GeneratedHrmKotlingradExpressions",
                "internal val expressionAliases",
                "codec_01_volatility_breakout",
                "codec_06_grid_trading",
            ],
        )
        checks.append(
            (
                "freqtrade generated Kotlin registry",
                ok,
                f"{generated_kotlin} (missing={missing})",
            )
        )

        generator_script = freqtrade / "scripts" / "generate_kotlingrad_swimlane_expressions.py"
        ok, missing = self._file_contains(
            generator_script,
            [
                "Generate compositional Kotlingrad expression artifacts",
                "CODEC_IDS",
                "hrm_kotlingrad_expressions.json",
            ],
        )
        checks.append(
            (
                "freqtrade generator script",
                ok,
                f"{generator_script} (missing={missing})",
            )
        )

        duck_muxer = (
            freqtrade
            / "src"
            / "kotlin-engine"
            / "src"
            / "nativeMain"
            / "kotlin"
            / "borg"
            / "trikeshed"
            / "duck"
            / "DuckMuxer.kt"
        )
        ok, missing = self._file_contains(
            duck_muxer,
            [
                "fun getAction(sym: String, expressionId: String): Int",
                "CompositionalExpressionRegistry.resolve(expressionId)",
                "computeCursorExpression",
            ],
        )
        checks.append(
            (
                "freqtrade DuckMuxer dispatcher",
                ok,
                f"{duck_muxer} (missing={missing})",
            )
        )

        compositional_registry = (
            freqtrade
            / "src"
            / "kotlin-engine"
            / "src"
            / "nativeMain"
            / "kotlin"
            / "borg"
            / "trikeshed"
            / "duck"
            / "CompositionalExpressions.kt"
        )
        ok, missing = self._file_contains(
            compositional_registry,
            [
                "internal object CompositionalExpressionRegistry",
                "GeneratedHrmKotlingradExpressions.expressionAliases",
                "fun resolve(expressionId: String)",
            ],
        )
        checks.append(
            (
                "freqtrade compositional expression registry",
                ok,
                f"{compositional_registry} (missing={missing})",
            )
        )

        bridge_strategy = freqtrade / "freqtrade" / "strategy" / "bridge_strategy.py"
        ok, missing = self._file_contains(
            bridge_strategy,
            [
                "KOTLIN_CURSOR_EXPRESSION_ID",
                "trikeshed_get_action_expr",
                "def _get_action_ffi",
            ],
        )
        checks.append(
            (
                "freqtrade bridge strategy expression path",
                ok,
                f"{bridge_strategy} (missing={missing})",
            )
        )

        gateway = freqtrade / "services" / "kotlin_engine_gateway" / "app.py"
        ok, missing = self._file_contains(
            gateway,
            [
                "trikeshed_get_action_expr",
                "expression_id: str | None = None",
                "if req.expression_id and engine_handle.has_expr_action",
            ],
        )
        checks.append(
            (
                "freqtrade HTTP gateway expression path",
                ok,
                f"{gateway} (missing={missing})",
            )
        )

        diff_duck_cursor = trikeshed / "src" / "jvmMain" / "kotlin" / "borg" / "trikeshed" / "duck" / "DiffDuckCursor.kt"
        ok, missing = self._file_contains(
            diff_duck_cursor,
            [
                "import ai.hypergraph.kotlingrad.api.*",
                "fun pancakeKotlingrad(vararg colNames: String): Series<SFun<DReal>>",
                "fun pancakeKotlingradInfinite(vararg colNames: String): Series<SFun<DReal>>",
                "fun pancakeInfinite(vararg colNames: String): Series<Double>",
                "pancake(*colNames).infiniteOr(0.0)",
            ],
        )
        checks.append(
            (
                "trikeshed DiffDuckCursor Kotlingrad+Cursor surface",
                ok,
                f"{diff_duck_cursor} (missing={missing})",
            )
        )

        tradepair_iomux = trikeshed / "src" / "jvmMain" / "kotlin" / "borg" / "trikeshed" / "grad" / "TradePairIoMux.kt"
        ok, missing = self._file_contains(
            tradepair_iomux,
            [
                "val sharedPancakeKotlingrad: Series<SFun<DReal>>",
                "val sharedPancakeKotlingradInfinite: Series<SFun<DReal>>",
                "cursor.pancakeKotlingrad(\"open\", \"high\", \"low\", \"close\", \"volume\")",
            ],
        )
        checks.append(
            (
                "trikeshed TradePairIoMux Kotlingrad pancake wiring",
                ok,
                f"{tradepair_iomux} (missing={missing})",
            )
        )

        backtrading_conductor = (
            trikeshed
            / "src"
            / "jvmMain"
            / "kotlin"
            / "borg"
            / "trikeshed"
            / "grad"
            / "BacktradingCoroutineConductor.kt"
        )
        ok, missing = self._file_contains(
            backtrading_conductor,
            [
                "class BacktradingCoroutineConductor",
                "val candleIngress",
                "val intraEgress",
                "val signalEgress",
                "val executiveEgress",
                "fun windupFromDsel(",
                "fun interface PythonMinimumAdapter",
            ],
        )
        checks.append(
            (
                "trikeshed coroutine job conductor",
                ok,
                f"{backtrading_conductor} (missing={missing})",
            )
        )

        codec_dir = moneyfan / "codec_models"
        codec_count = 0
        if codec_dir.exists():
            codec_count = len(list(codec_dir.glob("codec_*.py")))
        checks.append(
            (
                "moneyfan codec panel",
                codec_count >= 24,
                f"{codec_dir} (codec_files={codec_count})",
            )
        )

        all_ok = True
        for label, ok, detail in checks:
            status = "ok" if ok else "missing"
            print(f"  - {label}: {status}")
            print(f"      {detail}")
            if not ok:
                all_ok = False

        if all_ok:
            print("\n[NEXUS] Result: healthy")
            print("[NEXUS] Chain: swimlanes -> kotlingrad registry -> cursor expression dispatch -> FFI/HTTP bridge")
            return 0

        print("\n[NEXUS] Result: broken")
        print("[NEXUS] At least one required nexus link is missing.")
        return 1

    def begin_today(
        self,
        execute: bool,
        start_month: Optional[str],
        end_month: Optional[str],
        max_archives: Optional[int],
        storage_mode: Optional[str],
        include_python: bool,
        skip_sync: bool,
        skip_connectome: bool,
        skip_harness: bool,
        skip_risk: bool,
        skip_swimlanes: bool,
        skip_tasks: bool,
    ) -> int:
        today = date.today().isoformat()
        print(f"[BEGIN] Coordination start date: {today}")

        session_dir = DEFAULT_RUNTIME_DIR / f"session-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        pids: List[Dict[str, Any]] = []

        if not skip_sync:
            print("\n[BEGIN] Step 1/6: Binance lazy differential sync")
            if execute:
                rc = self.sync_binance(start_month, end_month, max_archives, storage_mode=storage_mode)
                if rc != 0:
                    return rc
            else:
                mode = storage_mode or str(self.config.get("binance_vision", {}).get("storage_mode", "permanent"))
                print(f"[DRY-RUN] Would execute: sync-binance (storage_mode={mode})")

        if not skip_connectome:
            print("\n[BEGIN] Step 2/6: Build Binance connectome universe")
            if execute:
                rc = self.build_connectome(storage_mode=storage_mode, max_symbols_override=None)
                if rc != 0:
                    return rc
            else:
                mode = storage_mode or str(self.config.get("binance_vision", {}).get("storage_mode", "permanent"))
                print(f"[DRY-RUN] Would execute: build-connectome (storage_mode={mode})")

        if not skip_harness:
            print("\n[BEGIN] Step 3/6: Emit staged HRM harness + codex")
            if execute:
                rc = self.emit_harness(storage_mode=storage_mode, pair_universe_path=None)
                if rc != 0:
                    return rc
            else:
                mode = storage_mode or str(self.config.get("binance_vision", {}).get("storage_mode", "permanent"))
                print(f"[DRY-RUN] Would execute: emit-harness (storage_mode={mode})")

        if not skip_risk:
            print("\n[BEGIN] Step 4/6: Publish strategy-specific risk profiles")
            if execute:
                rc = self.publish_risk()
                if rc != 0:
                    return rc
            else:
                print("[DRY-RUN] Would execute: publish-risk")

        if not skip_swimlanes:
            print("\n[BEGIN] Step 5/6: Publish HRM swimlane manifest")
            if execute:
                rc = self.publish_swimlanes()
                if rc != 0:
                    return rc
            else:
                print("[DRY-RUN] Would execute: publish-swimlanes")

        if not skip_tasks:
            print("\n[BEGIN] Step 6/6: Workspace tasks")
            tasks = self._tasks_for_today(include_python=include_python)
            if not include_python:
                print("[BEGIN] Python minimum tasks are disabled (pass --include-python to enable)")
            if execute:
                session_dir.mkdir(parents=True, exist_ok=True)
            for task in tasks:
                if execute:
                    rc, pid = self._run_task(task, session_dir)
                    if pid is not None:
                        pids.append({"name": task.name, "pid": pid, "cwd": str(task.cwd), "command": task.command})
                    if rc != 0:
                        print(f"[TASK] failed: {task.name} rc={rc}")
                        return rc
                else:
                    kind = "background" if task.background else "oneshot"
                    print(f"[DRY-RUN] Would run ({kind}) {task.name}: {task.command}")

        if execute and pids:
            pid_file = session_dir / "background-pids.json"
            pid_file.write_text(json.dumps({"generated_at": now_iso(), "processes": pids}, indent=2), encoding="utf-8")
            print(f"\n[BEGIN] Background PID file: {pid_file}")

        print("\n[BEGIN] Coordination flow complete")
        return 0

    @staticmethod
    def _run_task(task: TaskSpec, session_dir: Path) -> Tuple[int, Optional[int]]:
        if not task.cwd.exists():
            print(f"[TASK] missing cwd for {task.name}: {task.cwd}")
            return 1, None

        print(f"[TASK] {task.name}: {task.command}")
        if task.background:
            log_path = session_dir / f"{task.name}.log"
            log_fh = log_path.open("w", encoding="utf-8")
            proc = subprocess.Popen(
                task.command,
                cwd=str(task.cwd),
                shell=True,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                text=True,
            )
            print(f"[TASK] started background pid={proc.pid} log={log_path}")
            return 0, int(proc.pid)

        try:
            result = subprocess.run(
                task.command,
                cwd=str(task.cwd),
                shell=True,
                timeout=task.timeout_seconds,
                check=False,
            )
            return int(result.returncode), None
        except subprocess.TimeoutExpired:
            print(f"[TASK] timeout: {task.name} after {task.timeout_seconds}s")
            return 124, None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cross-workspace coordination runner")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Show workspace + contract status")

    sync = sub.add_parser("sync-binance", help="Run lazy differential Binance archive ingest")
    sync.add_argument("--start-month", type=str, default=None)
    sync.add_argument("--end-month", type=str, default=None)
    sync.add_argument("--max-archives", type=int, default=None)
    sync.add_argument("--storage-mode", choices=["permanent", "tmp"], default=None)

    sub.add_parser("publish-risk", help="Publish strategy-specific safety/drawdown profiles")
    pub_swim = sub.add_parser("publish-swimlanes", help="Publish HRM swimlane archetype manifest + DSEL")
    pub_swim.add_argument("--min-effective-width", type=int, default=None)

    connectome = sub.add_parser(
        "build-connectome",
        help="Build Binance connectome symbol universe (BTC/ETH/SOL anchored)",
    )
    connectome.add_argument("--storage-mode", choices=["permanent", "tmp"], default=None)
    connectome.add_argument("--max-symbols", type=int, default=None)

    harness = sub.add_parser(
        "emit-harness",
        help="Emit staged HRM harness commands + codex (4x4, 24x24, 24x64, 24x512)",
    )
    harness.add_argument("--storage-mode", choices=["permanent", "tmp"], default=None)
    harness.add_argument("--pair-universe-path", type=str, default=None)

    sub.add_parser("nexus-status", help="Validate Kotlingrad + Cursor nexus across all linked workspaces")

    begin = sub.add_parser("begin-today", help="Run full coordination flow starting today")
    begin.add_argument("--execute", action="store_true", help="Execute tasks (default is dry-run)")
    begin.add_argument("--start-month", type=str, default=None)
    begin.add_argument("--end-month", type=str, default=None)
    begin.add_argument("--max-archives", type=int, default=120)
    begin.add_argument("--storage-mode", choices=["permanent", "tmp"], default=None)
    begin.add_argument("--include-python", action="store_true", help="Include Python minimum adapter tasks")
    begin.add_argument("--skip-sync", action="store_true")
    begin.add_argument("--skip-connectome", action="store_true")
    begin.add_argument("--skip-harness", action="store_true")
    begin.add_argument("--skip-risk", action="store_true")
    begin.add_argument("--skip-swimlanes", action="store_true")
    begin.add_argument("--skip-tasks", action="store_true")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    coordinator = WorkspaceCoordinator(args.config)

    if args.command == "status":
        return coordinator.status()
    if args.command == "sync-binance":
        return coordinator.sync_binance(
            args.start_month,
            args.end_month,
            args.max_archives,
            storage_mode=args.storage_mode,
        )
    if args.command == "publish-risk":
        return coordinator.publish_risk()
    if args.command == "publish-swimlanes":
        return coordinator.publish_swimlanes(min_effective_width=args.min_effective_width)
    if args.command == "build-connectome":
        return coordinator.build_connectome(
            storage_mode=args.storage_mode,
            max_symbols_override=args.max_symbols,
        )
    if args.command == "emit-harness":
        return coordinator.emit_harness(
            storage_mode=args.storage_mode,
            pair_universe_path=args.pair_universe_path,
        )
    if args.command == "nexus-status":
        return coordinator.nexus_status()
    if args.command == "begin-today":
        return coordinator.begin_today(
            execute=bool(args.execute),
            start_month=args.start_month,
            end_month=args.end_month,
            max_archives=args.max_archives,
            storage_mode=args.storage_mode,
            include_python=bool(args.include_python),
            skip_sync=bool(args.skip_sync),
            skip_connectome=bool(args.skip_connectome),
            skip_harness=bool(args.skip_harness),
            skip_risk=bool(args.skip_risk),
            skip_swimlanes=bool(args.skip_swimlanes),
            skip_tasks=bool(args.skip_tasks),
        )

    print(f"Unknown command: {args.command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
