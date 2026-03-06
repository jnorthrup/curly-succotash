# Blocker Tracking by Repository

**Last Updated:** 2026-03-06
**Owner:** All repo maintainers
**Update Cadence:** Daily during standup, or when blockers change

---

## Resolved Blockers (This Sprint)

| ID | Blocker | Resolved Date | Resolution |
|----|---------|---------------|------------|
| IT4 | HRM promotion ladder not implemented | 2026-03-06 | Created `hrm_promotion.py` and wired daily promotion evaluation into the simulator |
| IT9 | Veto reason tracking schema not defined | 2026-03-06 | Created `veto_regression_watch.py` and wired simulator veto recording/resolution |
| IT10 | Daily runbook outputs not implemented | 2026-03-06 | Created `daily_runbook.py` and wired simulator-backed Markdown/JSON/CSV generation |
| VQ1 | Unit tests for new modules | 2026-03-06 | Focused runtime suite passes 106 tests across runbook, veto, promotion, shadow runtime, and simulator coverage |

---

## Active Blockers

### curly-succotash

| ID | Blocker | Owner | Next Artifact | ETA | Blocked Tasks |
|----|---------|-------|---------------|-----|---------------|
| CS-001 | HRM shadow path is wired, but real HRM predictor/model serving is still not connected | @jim | `shadow_model_adapter.py` | 2026-03-13 | IT2, IT3, IT9, IT10 |
| CS-002 | Manual scoreboard/runbook generation is wired, but scheduled daily automation is not configured | @jim | `daily_shadow_report_job.py` | 2026-03-10 | IT3, IT10 |
| CS-003 | Kill-switch is wired and tested, but promotion guardrails are not enforced across all execution paths | @jim | `promotion_guardrails.md` | 2026-03-13 | IT4, IT6 |
| CS-004 | Veto tracking is integrated in the simulator, but external reporting schema/contracts are still pending | @jim | `veto_schema.json` | 2026-03-08 | IT9 |

**Immediate Actions (This Week):**
- [x] Implement HRM promotion ladder (IT4) - **DONE**
- [x] Implement veto regression watch (IT9) - **DONE**
- [x] Implement daily runbook generator (IT10) - **DONE**
- [ ] Connect a real HRM predictor/model adapter (CS-001)
- [ ] Configure scheduled daily scoreboard/runbook automation (CS-002)
- [ ] Define veto schema for external integration (CS-004)

---

### moneyfan

| ID | Blocker | Owner | Next Artifact | ETA | Blocked Tasks |
|----|---------|-------|---------------|-----|---------------|
| MF-001 | Identity synthetic gate implementation not started | @ml-team | `identity_gate.py` + tests | 2026-03-10 | HF1 |
| MF-002 | Sine gate dataset generation not implemented | @ml-team | `sine_dataset.py` | 2026-03-10 | HF2 |
| MF-003 | Baseline models (persistence, EMA, linear) not implemented | @ml-team | `baseline_models.py` | 2026-03-13 | HF7, HF8 |
| MF-004 | Failure outcome taxonomy not defined | @jim | `failure_taxonomy.md` | 2026-03-07 | HF9 |
| MF-005 | Regime manifest and coverage policy not defined | @jim | `regime_manifest.json` | 2026-03-08 | MT3 |
| MF-006 | Cost-aware trade objective not implemented | @ml-team | `cost_aware_loss.py` | 2026-03-20 | MT10 |
| MF-007 | Model versioning system not implemented | @ml-team | `model_registry.py` | 2026-03-15 | MT18 |

**Immediate Actions (This Week):**
- [ ] Define failure taxonomy (MF-004)
- [ ] Create regime manifest (MF-005)
- [ ] Start identity gate implementation (MF-001)

---

### freqtrade

| ID | Blocker | Owner | Next Artifact | ETA | Blocked Tasks |
|----|---------|-------|---------------|-----|---------------|
| FT-001 | Contract proxy mapping not tuned to real endpoint schema | @integration-team | `proxy_mapping.json` | 2026-03-13 | FO1 |
| FT-002 | Compare-report history helpers not implemented | @integration-team | `report_diff_tool.py` | 2026-03-08 | FO3 |
| FT-003 | HRM serving integration blocked on HF12 readiness | @ml-team | `hrm_readiness_contract.md` | TBD | FO4, FO5, FO6 |
| FT-004 | Load testing framework not configured | @qa-team | `load_test_config.yaml` | 2026-03-20 | FO8 |

**Immediate Actions (This Week):**
- [ ] Start proxy mapping validation (FT-001)
- [ ] Implement report diff tool (FT-002)

---

### trikeshed

| ID | Blocker | Owner | Next Artifact | ETA | Blocked Tasks |
|----|---------|-------|---------------|-----|---------------|
| TS-001 | Indicator mapping spec (Python → Kotlin) not started | @kotlin-team | `indicator_mapping_spec.md` | 2026-03-20 | TE1 |
| TS-002 | DuckDB C API cinterop not complete | @native-team | `duckdb_cinterop.kt` | 2026-03-27 | TE8 |
| TS-003 | Kotlin indicator validation framework not implemented | @qa-team | `kotlin_validation.kt` | 2026-04-03 | TE3 |

**Immediate Actions (This Week):**
- [ ] Start indicator mapping spec (TS-001)
- [ ] Continue DuckDB cinterop (TS-002)

---

### coordination (Rust/QUIC/DHT)

| ID | Blocker | Owner | Next Artifact | ETA | Blocked Tasks |
|----|---------|-------|---------------|-----|---------------|
| QD-001 | QUIC handshake state machine not complete | @rust-team | `quic_handshake.rs` | 2026-03-27 | QD1 |
| QD-002 | DHT peer_id port not started | @rust-team | `peer_id.rs` | 2026-03-13 | QD7 |
| QD-003 | TLS 1.3 integration strategy not defined | @security-team | `tls_integration_plan.md` | 2026-03-20 | QD4 |

**Immediate Actions (This Week):**
- [ ] Start peer_id port (QD-002)

---

### ANE (Apple Neural Engine)

| ID | Blocker | Owner | Next Artifact | ETA | Blocked Tasks |
|----|---------|-------|---------------|-----|---------------|
| ANE-001 | Viable ANE candidate models not identified | @research-team | `ane_candidate_analysis.md` | 2026-03-13 | AH1 |
| ANE-002 | ANE parity test framework not implemented | @ml-team | `ane_parity_tests.py` | 2026-04-10 | AH2 |
| ANE-003 | ANE role decision pending (research/training/dead-end) | @research-team | `ane_role_decision.md` | 2026-05-01 | AH10 |

**Immediate Actions (This Week):**
- [ ] Analyze ANE candidate models (ANE-001)

---

## Cross-Repo Dependencies

### Critical Path Dependencies

```
MF-004 (failure taxonomy)
  → HF9 (failure outcomes)
    → HF12 (readiness contract)
      → FT-003 (HRM serving)

MF-005 (regime manifest)
  → MT3 (regime policy)
    → MT7 (regime-aware scheduling)

CS-001 (shadow mode)
  → IT2 (HRM shadow)
    → IT3 (scoreboard)
      → IT4 (promotion ladder)
```

### Blocked by External Factors

| Blocker | External Dependency | Contact | Status |
|---------|---------------------|---------|--------|
| FT-003 | HF12 readiness contract | @ml-team | Waiting on synthetic gates |
| TS-003 | TE2 cursor extraction | @kotlin-team | Waiting on mapping spec |
| QD-003 | TLS 1.3 library selection | @security-team | Research phase |

---

## Resolved Blockers (Last 7 Days)

| ID | Blocker | Resolved Date | Resolution |
|----|---------|---------------|------------|
| CS-000 | Canary basket definition | 2026-03-06 | Created `canary_basket.json` |
| CS-000 | Exchange tag canonicalization | 2026-03-06 | Created `exchange_data_tags.json` |
| CS-000 | Retention/pruning defaults | 2026-03-06 | Created `retention_pruning_config.json` |
| CS-000 | Honest stage names | 2026-03-06 | Updated `config.toml` |
| CS-000 | Artifact requirements | 2026-03-06 | Created `artifact_requirements.md` |

---

## Blocker Metrics

### Current State
- **Total Active Blockers:** 20
- **Critical Path Blockers:** 7 (CS-001, MF-001, MF-004, MF-005, HF12, FT-003, TS-001)
- **Blocked Tasks:** 45+
- **Oldest Blocker:** CS-001 (HRM shadow mode - identified 2026-03-06)

### Targets
- **Week 1 Goal:** Resolve 5 quick-win blockers (MF-004, MF-005, CS-002, CS-004, FT-002)
- **Week 2 Goal:** Start critical path work (CS-001, MF-001, TS-001)
- **Week 4 Goal:** Resolve 15 blockers, unblock 30+ tasks

---

## Update Process

### How to Add a Blocker

1. **Create blocker entry** in appropriate repo section
2. **Assign owner** - Person responsible for resolution
3. **Define next artifact** - Concrete deliverable to resolve blocker
4. **Estimate ETA** - Realistic completion date
5. **List blocked tasks** - TODO.md tasks blocked by this

### How to Resolve a Blocker

1. **Complete next artifact** - Deliver the defined artifact
2. **Update blocker status** - Move to "Resolved Blockers" table
3. **Document resolution** - Brief description of how it was resolved
4. **Notify blocked owners** - Inform owners of blocked tasks

### Daily Standup Questions

1. What blockers did I resolve yesterday?
2. What blockers will I work on today?
3. Am I blocked by anyone else?
4. Are any blockers becoming critical path?

---

## Escalation Path

If a blocker remains unresolved for >7 days:

1. **Day 1-3:** Owner works on resolution (normal)
2. **Day 4-5:** Owner provides update in standup (status check)
3. **Day 6-7:** Escalate to repo maintainer (priority review)
4. **Day 8+:** Escalate to project coordinator (resource reallocation)

---

## Contact

**Project Coordinator:** @jim
**Repo Maintainers:**
- curly-succotash: @jim
- moneyfan: @ml-team
- freqtrade: @integration-team
- trikeshed: @kotlin-team
- coordination: @rust-team
- ANE: @research-team

**Standup Time:** Daily at 9:00 AM PST
**Blocker Review:** Weekly on Monday at 10:00 AM PST

---

**REMEMBER:** A blocker documented is a blocker half-resolved. A blocker ignored is a project risk.
