# HRM Shadow Mode Integration Guide

**Version:** 1.0
**Date:** 2026-03-06
**Status:** Ready for Integration

---

## Overview

This guide explains how to integrate HRM shadow mode into the existing curly-succotash trading simulator. Shadow mode allows HRM to run in parallel with baseline trading strategies, recording counterfactual outcomes without affecting actual trades.

### What You Get

- **Parallel Execution**: HRM runs alongside baseline strategies
- **Counterfactual Tracking**: Records what HRM *would* have traded
- **Daily Scoreboard**: Automated PnL comparison reports
- **Kill-Switch Protection**: Hard drawdown limits protect against catastrophic losses
- **Regime Awareness**: Market regime detection and adaptation

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  Trading Loop                            │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────┐         ┌──────────────┐             │
│  │   Baseline   │         │  HRM Shadow  │             │
│  │  Strategies  │         │    Engine    │             │
│  │              │         │              │             │
│  │  LONG/SHORT  │         │  LONG/SHORT  │             │
│  │     FLAT     │         │     FLAT     │             │
│  └──────┬───────┘         └──────┬───────┘             │
│         │                        │                       │
│         └──────────┬─────────────┘                       │
│                    │                                     │
│           ┌────────▼────────┐                           │
│           │  Shadow Mode    │                           │
│           │   Decision      │                           │
│           │                 │                           │
│           │  SHADOW:        │                           │
│           │  Follow baseline│                           │
│           │                 │                           │
│           │  VETO_ONLY:     │                           │
│           │  Can block      │                           │
│           │                 │                           │
│           │  SIZE_CAPPED:   │                           │
│           │  Size limits    │                           │
│           │                 │                           │
│           │  PRIMARY:       │                           │
│           │  HRM in control │                           │
│           └────────┬────────┘                           │
│                    │                                     │
│           ┌────────▼────────┐                           │
│           │  Trade Execute  │                           │
│           │  (Paper Only)   │                           │
│           └────────┬────────┘                           │
│                    │                                     │
│           ┌────────▼────────┐                           │
│           │  Kill-Switch    │                           │
│           │   Monitor       │                           │
│           │                 │                           │
│           │  Check limits:  │                           │
│           │  - Daily loss   │                           │
│           │  - Cumulative   │                           │
│           │  - Consecutive  │                           │
│           │  - Volatility   │                           │
│           └────────┬────────┘                           │
│                    │                                     │
│         ┌──────────▼──────────┐                         │
│         │   Trading Allowed?  │                         │
│         │   YES → Execute     │                         │
│         │   NO  → Halt        │                         │
│         └─────────────────────┘                         │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

## Quick Start

### 1. Install Dependencies

```bash
cd /Users/jim/work/curly-succotash/backend
source .venv/bin/activate
pip install -r requirements.txt  # Ensure numpy is available
```

### 2. Configure Shadow Mode

Create or update your configuration:

```python
from backend.src.hrm_shadow import ShadowConfig, ShadowMode
from backend.src.killswitch import KillSwitchConfig

# Shadow mode configuration
shadow_config = ShadowConfig(
    mode=ShadowMode.SHADOW,  # Start with pure observation
    symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
    timeframes=[Timeframe.ONE_HOUR],
    hrm_model_path="/path/to/hrm/model.safetensors",  # Optional for now
    hrm_confidence_threshold=0.6,
    max_position_size_pct=5.0,
    commission_pct=0.1,
    slippage_bps=5.0,
    output_dir="/Users/jim/work/curly-succotash/logs/shadow_mode"
)

# Kill-switch configuration
killswitch_config = KillSwitchConfig(
    daily_loss_limit_pct=3.0,
    cumulative_loss_limit_pct=10.0,
    max_consecutive_losses=5,
    volatility_spike_multiplier=3.0,
    cooldown_hours=24,
    output_dir="/Users/jim/work/curly-succotash/logs/killswitch"
)
```

### 3. Initialize Components

```python
from backend.src.hrm_shadow import HRMShadowEngine
from backend.src.killswitch import DrawdownKillSwitch
from backend.src.scoreboard import ScoreboardGenerator
from backend.src.models import Candle, Signal, SignalType, Timeframe

# Initialize shadow engine
shadow_engine = HRMShadowEngine(shadow_config)

# Initialize kill-switch
killswitch = DrawdownKillSwitch(
    config=killswitch_config,
    initial_capital=10000.0
)

# Initialize scoreboard generator
scoreboard_gen = ScoreboardGenerator(
    output_dir="/Users/jim/work/curly-succotash/logs/scoreboards"
)
```

### 4. Integrate into Trading Loop

```python
# In your main trading loop (e.g., simulator.py)

async def process_candle(candle: Candle):
    """Process incoming candle through baseline and HRM shadow."""

    # 1. Get baseline strategy signal
    baseline_signal = await get_baseline_signal(candle)

    # 2. Get HRM shadow signal (counterfactual)
    shadow_signal = shadow_engine.process_candle(
        candle=candle,
        baseline_signal=baseline_signal,
        context=historical_context
    )

    # 3. Check kill-switch
    if not killswitch.is_trading_allowed():
        logger.warning("Trading halted by kill-switch")
        return

    # 4. Execute baseline trade (shadow mode = follow baseline)
    if shadow_signal.action_taken == "baseline_followed":
        trade = await execute_baseline_trade(baseline_signal)
        shadow_engine.execute_shadow_trade(shadow_signal)  # Record counterfactual
    elif shadow_signal.action_taken == "hrm_veto":
        logger.info(f"Trade vetoed by HRM: {shadow_signal.veto_reason}")
    elif shadow_signal.action_taken == "hrm_override":
        # Only in SIZE_CAPPED or PRIMARY mode
        trade = await execute_hrm_trade(shadow_signal)

    # 5. Record trade PnL for kill-switch monitoring
    if trade:
        killswitch.record_trade(
            pnl=trade.pnl,
            pnl_pct=trade.pnl_percent,
            symbol=trade.symbol,
            timestamp=trade.timestamp
        )

# Start new trading day
def start_trading_day():
    """Initialize new trading day."""
    killswitch.start_new_trading_day()
    shadow_engine.clear_daily_state()

# End trading day - generate scoreboard
def end_trading_day(date: datetime):
    """Generate daily scoreboard."""
    metrics = [
        shadow_engine.compute_metrics(
            symbol=symbol,
            timeframe=Timeframe.ONE_HOUR,
            baseline_trades=baseline_trades,
            start_time=date.replace(hour=0, minute=0),
            end_time=date.replace(hour=23, minute=59)
        )
        for symbol in shadow_config.symbols
    ]

    scoreboard = scoreboard_gen.generate(
        date=date,
        metrics=metrics,
        mode=shadow_config.mode.value
    )

    # Save in all formats
    paths = scoreboard_gen.save_all_formats(scoreboard)
    logger.info(f"Scoreboard saved: {paths}")

    # Save shadow log and kill-switch log
    shadow_engine.save_daily_log(date)
    killswitch.save_daily_log(date)
```

---

## Shadow Mode Stages

### Stage 1: SHADOW (Current)

**Authority**: Observation only
**Trading**: Always follows baseline
**Purpose**: Collect counterfactual data

```python
config = ShadowConfig(mode=ShadowMode.SHADOW)
```

**Behavior**:
- HRM records what it *would* have traded
- No impact on actual trading decisions
- Baseline strategies have full authority
- Daily scoreboard shows: "What if we followed HRM?"

---

### Stage 2: VETO_ONLY

**Authority**: Can block baseline trades
**Trading**: Baseline unless HRM vetoes
**Purpose**: Test HRM risk management

```python
config = ShadowConfig(
    mode=ShadowMode.VETO_ONLY,
    veto_on_confidence_below=0.5,
    veto_on_opposite_signal=True
)
```

**Behavior**:
- HRM can block trades it strongly opposes
- Veto issued when HRM confidence > 0.5 and signal differs from baseline
- Scoreboard tracks veto accuracy
- Promotion requires positive veto accuracy

---

### Stage 3: SIZE_CAPPED

**Authority**: Can trade with size limits
**Trading**: HRM when confident, baseline otherwise
**Purpose**: Gradual authority increase

```python
config = ShadowConfig(
    mode=ShadowMode.SIZE_CAPPED,
    hrm_confidence_threshold=0.7,
    max_position_size_pct=1.0  # Limited size
)
```

**Behavior**:
- HRM can override baseline when confidence > 0.7
- Position size capped at 1% (vs normal 5%)
- Scoreboard compares HRM trades vs baseline
- Promotion requires HRM outperformance

---

### Stage 4: PRIMARY

**Authority**: Full trading authority
**Trading**: HRM in full control
**Purpose**: Production deployment

```python
config = ShadowConfig(
    mode=ShadowMode.PRIMARY,
    hrm_confidence_threshold=0.6,
    max_position_size_pct=5.0
)
```

**Behavior**:
- HRM has full authority
- Baseline strategies run in shadow for comparison
- Daily scoreboard shows HRM performance
- Demotion if drawdown limits hit

---

## Kill-Switch Configuration

### Default Settings

```python
KillSwitchConfig(
    daily_loss_limit_pct=3.0,       # Halt after 3% daily loss
    cumulative_loss_limit_pct=10.0, # Halt after 10% total loss
    max_consecutive_losses=5,       # Halt after 5 losing trades in a row
    volatility_spike_multiplier=3.0,# Halt if volatility > 3x normal
    cooldown_hours=24               # Wait 24h before can restart
)
```

### Trigger Conditions

1. **Daily Loss Limit**: Halts trading for the day
2. **Cumulative Loss Limit**: Halts all trading until manual reset
3. **Consecutive Losses**: Indicates strategy breakdown
4. **Volatility Spike**: Protects against flash crashes

### Manual Override

```python
# Manual halt
killswitch.manual_halt("Market emergency")

# Manual reset (after cooldown)
killswitch.manual_reset()
```

---

## Scoreboard Output

### JSON Format

Location: `/Users/jim/work/curly-succotash/logs/scoreboards/scoreboard_2026-03-06.json`

```json
{
  "date": "2026-03-06",
  "trading_day": "2026-03-05",
  "mode": "shadow",
  "summary": {
    "total_symbols": 3,
    "total_baseline_pnl": 150.00,
    "total_hrm_pnl": 225.00,
    "total_pnl_difference": 75.00,
    "avg_baseline_sharpe": 1.2,
    "avg_hrm_sharpe": 1.5,
    "symbols_hrm_outperformed": 2,
    "outperformance_rate": 66.7
  },
  "entries": [
    {
      "symbol": "BTCUSDT",
      "timeframe": "1h",
      "baseline_net_pnl": 100.00,
      "hrm_shadow_net_pnl": 150.00,
      "pnl_difference": 50.00,
      "hrm_outperformance": true
    }
  ],
  "notes": [
    "✓ HRM shadow outperformed baseline by $75.00 total",
    "✓ HRM outperformed on 66.7% of symbols (MODERATE)"
  ]
}
```

### Markdown Format

Location: `/Users/jim/work/curly-succotash/logs/scoreboards/scoreboard_2026-03-06.md`

```markdown
# Daily Trading Scoreboard

**Date:** 2026-03-05
**Generated:** 2026-03-06T00:00:00Z
**Mode:** SHADOW

## Summary

| Metric | Baseline | HRM Shadow | Difference |
|--------|----------|------------|------------|
| Total PnL | $150.00 | $225.00 | $75.00 |
| Trades | 10 | 12 | - |
| Avg Sharpe | 1.20 | 1.50 | 0.30 |

**HRM Outperformance Rate:** 66.7% (2/3 symbols)

## Notes

- ✓ HRM shadow outperformed baseline by $75.00 total
- ✓ HRM outperformed on 66.7% of symbols (MODERATE)
- ℹ Mode: SHADOW - HRM has no trading authority

## Detailed Results

| Symbol | Timeframe | Baseline PnL | HRM PnL | Difference | HRM Win? |
|--------|-----------|--------------|---------|------------|----------|
| BTCUSDT | 1h | $100.00 | $150.00 | $50.00 | ✓ |
| ETHUSDT | 1h | $50.00 | $75.00 | $25.00 | ✓ |
| SOLUSDT | 1h | $0.00 | $0.00 | $0.00 | ✗ |
```

---

## Artifact Requirements

All shadow mode runs MUST produce:

1. **Daily Scoreboard** (JSON + Markdown)
   - Location: `/Users/jim/work/curly-succotash/logs/scoreboards/`
   - Filename: `scoreboard_YYYY-MM-DD.{json,md}`

2. **Shadow Trade Log** (JSON)
   - Location: `/Users/jim/work/curly-succotash/logs/shadow_mode/`
   - Filename: `shadow_log_YYYY-MM-DD.json`

3. **Kill-Switch Log** (JSON)
   - Location: `/Users/jim/work/curly-succotash/logs/killswitch/`
   - Filename: `killswitch_log_YYYY-MM-DD.json`

4. **Veto Decisions** (if in VETO_ONLY mode or higher)
   - Location: `/Users/jim/work/curly-succotash/logs/vetoes/`
   - Filename: `veto_decisions_YYYY-MM-DD.json`

---

## Monitoring and Alerts

### Dashboard Metrics

Export these metrics to your dashboard:

```python
# Kill-switch state
metrics = killswitch.get_metrics()
dashboard.gauge("killswitch.state", metrics.state.value)
dashboard.gauge("killswitch.daily_pnl_pct", metrics.daily_pnl_pct)
dashboard.gauge("killswitch.cumulative_pnl_pct", metrics.cumulative_pnl_pct)

# Shadow performance
dashboard.counter("shadow.trades", len(shadow_engine.shadow_trades))
dashboard.gauge("shadow.pnl", sum(t.net_pnl for t in shadow_engine.shadow_trades))
```

### Alert Conditions

```python
# Alert on kill-switch trigger
if killswitch.get_metrics().state == KillSwitchState.TRIGGERED:
    send_alert("Kill-switch triggered! Trading halted.")

# Alert on HRM underperformance
if scoreboard.outperformance_rate < 40:
    send_alert("HRM underperforming on >60% of symbols")

# Alert on high veto rate
if scoreboard.total_vetoes > 10:
    send_alert(f"High veto activity: {scoreboard.total_vetoes} vetoes today")
```

---

## Promotion Criteria

### Shadow → VETO_ONLY

**Requirements**:
- Minimum 7 days in shadow mode
- Minimum 100 trades
- HRM shadow Sharpe > baseline Sharpe
- HRM shadow win rate > baseline win rate
- No kill-switch triggers

**Artifacts**:
- 7 daily scoreboards
- Shadow period summary report
- Baseline beat evidence (statistical test)

---

### VETO_ONLY → SIZE_CAPPED

**Requirements**:
- Minimum 14 days in veto_only mode
- Minimum 200 trades
- Veto accuracy > 60%
- HRM shadow max drawdown < baseline max drawdown
- No kill-switch triggers

**Artifacts**:
- 14 daily scoreboards
- Veto reason analysis
- Counterfactual displacement report

---

### SIZE_CAPPED → PRIMARY

**Requirements**:
- Minimum 30 days in size_capped mode
- Minimum 500 trades
- HRM Sharpe ratio > 1.5
- HRM win rate > 55%
- No kill-switch triggers

**Artifacts**:
- 30 daily scoreboards
- Slippage analysis
- Operator runbook archive

---

## Troubleshooting

### HRM Always Returns FLAT

**Problem**: HRM model not loaded or not predicting

**Solution**:
```python
# Check if model is loaded
if shadow_engine._hrm_model is None:
    shadow_engine.load_hrm_model("/path/to/model.safetensors")

# Or implement placeholder prediction
def predict_hrm_signal(self, candle, context):
    # Temporary placeholder
    return "LONG", 0.6
```

### Scoreboard Not Generated

**Problem**: Metrics not computed

**Solution**:
```python
# Ensure compute_metrics is called before generating scoreboard
metrics = shadow_engine.compute_metrics(
    symbol="BTCUSDT",
    timeframe=Timeframe.ONE_HOUR,
    baseline_trades=baseline_trades,
    start_time=start,
    end_time=end
)
```

### Kill-Switch Won't Reset

**Problem**: Cooldown period not expired

**Solution**:
```python
# Check cooldown status
metrics = killswitch.get_metrics()
print(f"Cooldown ends: {metrics.cooldown_ends_at}")

# Wait for cooldown or adjust config
killswitch.config.cooldown_hours = 12  # Reduce for testing
```

---

## Next Steps

1. **Implement HRM Model Integration**
   - Replace placeholder `predict_hrm_signal()` with actual HRM inference
   - Load model weights from moneyfan training artifacts

2. **Add Real-Time Dashboard**
   - WebSocket stream of shadow signals
   - Live PnL comparison charts

3. **Implement Synthetic Gates**
   - Identity gate (HF1)
   - Sine gate (HF2)
   - Feature prediction gates (HF3-HF5)

4. **Build Model Versioning**
   - Track which HRM model version produced which results
   - Enable rollback to previous versions

---

## Support

**Documentation**: `/Users/jim/work/curly-succotash/TODO.md`
**Blocker Tracking**: `/Users/jim/work/curly-succotash/coordination/runtime/blocker_tracking.md`
**Artifact Requirements**: `/Users/jim/work/curly-succotash/coordination/runtime/artifact_requirements.md`

**Contact**: @jim (Project Coordinator)
