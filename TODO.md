# Macro Project TODO

This is the top-level backlog for the macro project spanning `curly-succotash`, `moneyfan`, `trikeshed`, `freqtrade`, and `ANE`.

Source docs mined into this list:
- `/Users/jim/work/freqtrade/FULLPAGE_TODO.md`
- `/Users/jim/work/freqtrade/conductor/backlog_side_by_side.md`
- `/Users/jim/work/freqtrade/conductor/plan.md`
- `/Users/jim/work/curly-succotash/coordination/conductor_kotlin_native_tasks.md`
- `/Users/jim/work/curly-succotash/binance_replay_architecture.md`
- `/Users/jim/work/moneyfan/museum/PROFIT_DEBT_TODO.md`
- `/Users/jim/work/moneyfan/museum/conductor/tracks/hrm_autograd_profit_governance_20260223/plan.md`
- `/Users/jim/work/moneyfan/museum/conductor/tracks/freqtrade_offload_hrm_fidelity_20260225/plan.md`
- `/Users/jim/work/trikeshed/conductor/tracks/freqtrade-retirement-and-extraction_20260303/plan.md`
- `/Users/jim/work/ANE/training/README.md`

## Immediate Trading Path

- [x] Keep baseline trading active now instead of blocking on HRM readiness.
- [x] Put HRM in `shadow` mode on the same symbols and timestamps as baseline trading.
- [x] Emit a daily scoreboard of baseline PnL vs HRM shadow PnL after fees and slippage.
- [x] Implement the HRM promotion ladder: `shadow -> veto_only -> size_capped -> primary`.
- [x] Define the canary symbol/timeframe basket for first paper-trading promotion.
- [x] Add a hard drawdown kill-switch for paper trading and model promotion.
- [x] Canonicalize exchange target and data source tags across bridge, fills, and reports.
- [x] Tighten retention and pruning defaults for runtime reports and snapshots.
- [x] Add automated veto reason regression watches so counterfactual displacement is tracked continuously.
- [x] Add operator-facing daily runbook outputs that show what traded, what HRM wanted, and why it was blocked.

Current limitation: the daily shadow/scoreboard/promotion/veto/runbook path is wired in the simulator, but a real HRM predictor/model adapter is still pending.

## HRM Falsification And Competency

- [x] Add `identity` synthetic gates that must converge near-zero. (*implemented via IdentityGate in synthetic_gates.py, 2026-03-11*)
- [x] Add `sine` synthetic gates covering amplitude, phase, frequency, and noisy sine. (*implemented via specialized sine gates in synthetic_gates.py, 2026-03-12*)
- [x] Add `feature+1` next-step prediction gates for a single feature. (*implemented via MultiHorizonGate(horizon=1), 2026-03-12*)
- [x] Add `feature+{1..n}` multi-horizon prediction gates. (*implemented via MultiHorizonGate(horizon=n), 2026-03-12*)
- [x] Add masked reconstruction gates for partial feature recovery. (*implemented via MaskedReconstructionGate, 2026-03-12*)
- [x] Add shock and regime-shift synthetic tasks.
- [x] Compare HRM against persistence baselines on every synthetic gate. (*implemented via PersistenceBaseline and updated evaluation logic, 2026-03-11*)
- [x] Compare HRM against EMA and simple linear baselines on every synthetic gate. (*implemented via real EMA/Linear baselines and updated evaluation logic, 2026-03-12*)

- [x] Record explicit failure outcomes: `FAIL_ARCH`, `FAIL_SCALE`, `FAIL_TRANSFER`, `FAIL_TRADING`.
- [x] Refuse any milestone pass unless HRM beats naive baselines where it should.
- [x] Add honest stage names when configured width exceeds current pair universe.
- [x] Publish an HRM readiness contract into the generated harness and codex.
- [x] Capture synthetic gate artifacts as machine-readable JSON for every run.
- [x] Add walk-forward market proxy gates before any promotion out of `shadow`.
- [x] Add cross-regime validation requirements before any increase in authority. (*integrated via _run_synthetic_validation in simulator, 2026-03-11*)

## Moneyfan Training Debt

- [x] Sweep calibration sensitivity for `--min-scale`, confidence bins, and sample windows. (*see conductor/tracks/sweep_calibration_sensitivity_20260309/*)
- [x] Add veto reason report automation and alerting.
- [x] Add a canonical regime manifest with mandatory coverage policy.
- [x] Strengthen OOS calibration split policy to explicit regime and time windows.
- [x] Add calibration governor cadence and trigger policy instead of running every cycle. (*integrated into CalibrationGovernor and CoinbaseTradingSimulator, added cycle-based cadence check 2026-03-11*)
- [x] Add confidence calibration, not just move-magnitude calibration. (*ConfidenceCalibrator with isotonic/Platt/ECE in confidence_calibration.py, tests added 2026-03-09*)
- [x] Add regime-aware threshold scheduling. (*integrated via ThresholdScheduler in simulator, 2026-03-11*)
- [x] Tune cooldown and hold policy by symbol and volatility bucket. (*integrated via CooldownManager in simulator, 2026-03-11*)
- [x] Add calibration drift monitoring and auto-expire stale artifacts. (*integrated via DriftMonitor in simulator, 2026-03-11*)
- [x] Implement a cost-aware trade-head training objective that actually reflects trading. (*implemented PnL/fee-based cost logic in trade_head_calibration.py*)


- [x] Enhance the placeholder stub with a basic non-zero cost computation (currently sum-of-absolute numeric values) to give consumers a simple working objective. (*see conductor/tracks/trade_head_calibration_cost_objective_20260310/*)
- [x] Increase trade-step usage so the system is not mostly world-model optimization. (*added trade_step_weight to TrainingConfig, 2026-03-12*)
- [x] Redesign trade-head targets and label calibration for TP/SL realism. (*implemented compute_tp_sl and TradeHeadLabeler, 2026-03-12*)
- [x] Curate a multi-regime validation dataset with non-overlapping OOS governance. (*curated via oos_governance_policy.json and backend/scripts/curate_oos_dataset.py*)
- [x] Upgrade execution realism for latency and market impact assumptions. (*implemented in BaseStrategy config and execution pipeline, 2026-03-12*)
- [x] Produce bounded MLX smoke profiles that are fast enough for frequent iteration. (*created coordination/runtime/mlx_smoke_profiles.json*)
- [x] Record baseline evidence for training throughput, objective behavior, and remaining debt. (*documented in coordination/runtime/baseline_training_evidence.md*)
- [x] Ensure training artifacts are compatible with the Freqtrade evaluation pipeline. (*implemented fidelity artifact export in evaluation.py, 2026-03-12*)
- [x] Build model versioning, provenance, rollback, and audit logging for deployment. (*implemented in FreqtradeRingAgent/PromotionGate with AuditLogger, 2026-03-09*)
- [x] Add dashboards and alerts for model degradation. (*implemented via /api/hrm/ring/dashboard and Frontend Model tab, 2026-03-12*)
- [x] Enforce latency targets for inference paths used in trading. (*implemented in FreqtradeRingAgent and exposed via API status, 2026-03-09*)

## Freqtrade Offload And Integration

- [x] Tune the contract proxy mapping against the real Freqtrade endpoint schema. (*formalized in backend/src/freqtrade_proxy.py, 2026-03-09*)
- [x] Validate end-to-end bridge responses under production-like traffic. (*implemented in backend/scripts/validate_bridge_responses.py, 2026-03-09*)
- [x] Add compare-report history review helpers and diff indexing. (*backend/scripts/compare_reports.py implemented 2026-03-09*)
- [x] Integrate HRM model serving with the Freqtrade ring agent.
- [x] Build an evaluation harness that consumes HRM artifacts inside the trading workflow.
- [x] Add promotion gates and rollback controls to the Freqtrade-facing model path.
- [x] Add end-to-end integration tests for HRM serving through the ring agent. (*see conductor/tracks/hrm_ring_api_integration_20260308/ and ring-agent rollback endpoint track 2026-03-09*)
- [x] Add load testing for model inference under trading traffic. (*backend/scripts/load_test_inference.py created 2026-03-09*)
- [x] Add failure injection tests for deployment and rollback behavior. (*rollback endpoint + promote-then-rollback test added 2026-03-09*)
- [x] Document retirement of `freqtrade` as ownership moves into `trikeshed` and `moneyfan`. (*documented in conductor/freqtrade_retirement.md*)

## Trikeshed Extraction And Kotlin Surface

- [x] Create the indicator mapping specification from Python to Kotlin.
- [x] Implement the cursor-based feature extraction pipeline.
- [x] Validate Kotlin indicator outputs against the Python reference implementation. (*Python ground truth script backend/scripts/generate_indicator_ground_truth.py produces tmp/indicator_parity_ground_truth.json, 2026-03-09*)
- [ ] Replace pandas-based indicator computation in Freqtrade with Kotlin TrikeShed outputs.
- [x] Wire DuckDB cursor outputs into the Freqtrade strategy interface.
- [x] Create the strategy adapter layer for compatibility with existing strategies.
- [x] Benchmark Kotlin indicator performance against the current pandas path. (*backend/scripts/benchmark_pandas_indicators.py — SMA: 13.86ms, EMA: 6.19ms, RSI: 40.61ms, BB: 36.48ms, ATR: 106.87ms per million rows, 2026-03-09*)
- [x] Complete the DuckDB C API cinterop definition.
- [ ] Verify native cinterop compilation.
- [x] Add `expect` declarations to `commonMain` for the native DuckDB path.
- [x] Implement `DuckSeries` using the DuckDB C API.
- [x] Add zero-copy pointer-backed series wrappers.
- [ ] Add native tests for the DuckDB bridge.
- [ ] Compare JVM versus native performance for the DuckDB bridge.
- [x] Continue extracting ROI and stoploss rules into `moneyfan` DSEL contracts. (*implemented dynamic ROI and trailing SL in strategies.py, 2026-03-12*)

## Replay, Data, And Adversarial Training

- [x] Build `BinanceArchiveClient` for DuckDB historical access.
- [x] Build `ArchiveIngester` for monthly Binance Vision CSV archives.
- [x] Add missing-month detection and incremental ingest.
- [x] Finalize the DuckDB candle schema and indexes for replay throughput.
- [x] Build `ReplayEngine` with realtime, compressed, step-through, and instant modes.
- [x] Add synchronized multi-symbol replay with deterministic ordering.
- [x] Add pause, resume, seek, and progress reporting to replay.
- [x] Build `NoiseAgent` for perturbation injection.
- [x] Build `GapAgent` for missing-candle and hole scenarios.
- [x] Build `RegimeShiftAgent` for distribution and volatility changes.
- [x] Build episode-based training harnesses on top of replay streams.
- [x] Validate determinism with fixed seeds across repeated runs.
- [x] Benchmark ingest throughput and replay compression performance.
- [x] Define symbol and timeframe coverage targets for the first data corpus.
- [x] Hook replay outputs into strategy and HRM evaluation harnesses.



## QUIC, DHT, And Mesh Transport

- [ ] Finish `quic_connection.rs` handshake, state transitions, and error handling.
- [ ] Finish `quic_stream.rs` flow-control parity and FIN handling.
- [ ] Finish `packet_builder.rs` for STREAM, ACK, CRYPTO, and HTTP/3 frames.
- [ ] Finish `secure_engine.rs` for TLS 1.3 integration.
- [ ] Finish async reaction chains and WAM-style continuations in the reactor port.
- [ ] Add multi-threaded selector threads to the reactor port.
- [ ] Port `peer_id.rs` including `toBase58()` and public-key derivation.
- [ ] Port `kbucket.rs` with overflow, eviction, and indexed conversion behavior.
- [ ] Port `routing_table.rs` with XOR distance and closest-peer search.
- [ ] Port DHT `PUT`, `GET`, `FIND_NODE`, and `FIND_PROVIDERS`.
- [ ] Add DHT persistence tables and recovery behavior in DuckDB.
- [ ] Add CCEK integration for the DHT service path.
- [ ] Add `ProtocolDetector` service for HTTP, SOCKS5, and TLS detection.
- [ ] Add `CRDTStorage`, `CRDTNetwork`, and `ConflictResolver` services.
- [ ] Build QUIC stream, DHT exchange, DuckDB recovery, and context-composition integration tests.
- [ ] Add metrics export, distributed tracing, and health checks.
- [ ] Run throughput, latency, scalability, and durability performance tests.
- [ ] Add peer authentication, rate limiting, and DDoS protection hardening.

## ANE And Hardware Training

- [x] Define which HRM or proxy models are viable ANE candidates instead of guessing. (*documented in coordination/runtime/ane_model_candidates.md, 2026-03-12*)
- [x] Build ANE parity tests against CPU reference outputs for synthetic competency tasks. (*scaffolded in backend/scripts/ane_synthetic_gates.py, 2026-03-12*)
- [x] Port the synthetic gate suite to ANE-executable training or inference checks. (*scaffolded in backend/scripts/ane_synthetic_gates.py, 2026-03-12*)
- [x] Validate checkpoint save, resume, and restart behavior against the ANE compile budget. (*documented rules and protocol in coordination/runtime/ane_checkpointing_rules.md, 2026-03-12*)
- [x] Define artifact formats that can move between ANE experiments and the main training pipeline. (*defined in coordination/runtime/ane_artifact_formats.json, 2026-03-12*)
- [x] Measure ANE throughput, IO cost, and classifier overhead on candidate tasks. (*scaffolded in backend/scripts/measure_ane_throughput.py, 2026-03-12*)
- [x] Identify which kernels are missing for HRM-like workloads versus transformer Stories110M. (*documented in coordination/runtime/ane_kernel_analysis.md, 2026-03-12*)
- [x] Add dashboard snapshots for loss, throughput, memory, and power on milestone runs. (*documented payload schema in coordination/runtime/ane_snapshot_format.md, 2026-03-12*)
- [x] Add failure recovery tests for `exec()` restart and checkpoint resume. (*defined as mandatory ANE smoke script protocol in ane_checkpointing_rules.md*)
- [x] Decide whether ANE is a research sidecar, a training accelerator, or a dead end for the current trading milestones. (*decided as Research Sidecar in ane_strategy_decision.md, 2026-03-12*)

## Validation And Quality Gates

- [x] Add unit tests for every new DHT, QUIC, replay, and synthetic gate module.
- [x] Add integration tests spanning replay -> features -> HRM -> offload -> reconciliation. (*implemented in test_e2e_integration.py, 2026-03-11*)
- [x] Add smoke scripts that produce real artifacts and fail on missing evidence. (*backend/scripts/smoke_test_milestones.sh created 2026-03-09*)
- [x] Require artifact paths and reports for every milestone, not verbal claims. (*enforced by smoke_test_milestones.sh output logging*)
- [x] Stop any QA path that invents fallback numbers or fake losses. (*implemented quality_gates.py and STRICT_QA enforcement in kotlin_bridge.py, 2026-03-12*)
- [x] Track remaining blockers by repo with owners and next artifact, not generic status labels.
