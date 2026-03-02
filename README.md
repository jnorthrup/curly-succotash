# Coinbase Trading Simulator

A paper trading dashboard for cryptocurrency with 12 algorithmic trading strategies. Simulates trades using live Coinbase market data without placing real orders.

**⚠️ SAFETY**: This is READ-ONLY. No live trading endpoints exist. All positions are paper-only.

---

## Features

- **12 Trading Strategies**: From MA Crossover to Volume-Price Confirmation
- **Real-time Signals**: WebSocket streaming of trading signals
- **Backtesting**: Run historical simulations with configurable parameters
- **"Bullpen" Rankings**: Strategy performance leaderboard with consensus signals
- **Paper Trading**: Simulated positions with P&L tracking
- **Multi-timeframe**: Support for various timeframes (1H default)

---

## The 12 Strategies

| Strategy | Description | Style |
|----------|-------------|-------|
| MA_Crossover | 21/55 SMA crossover with trend regime filter | Trend Following |
| RSI_Mean_Reversion | RSI oversold/overbought with volatility filter | Mean Reversion |
| Bollinger_Breakout | Bollinger Band squeeze breakouts | Breakout |
| MACD_Momentum | MACD crossover with histogram divergence | Momentum |
| Supertrend | ATR-based dynamic support/resistance | Trend Following |
| ADX_Trend_Filter | ADX > 25 with DI crossover | Trend Strength |
| Volatility_Regime_Switch | Adapts between mean-reversion and breakout | Adaptive |
| Donchian_Breakout | 20-period channel breakout (turtle trading) | Breakout |
| Keltner_Channel | EMA + 2x ATR channel breakouts | Breakout |
| Stochastic_Oscillator | %K/%D crossover with 20/80 levels | Oscillator |
| EMA_Ribbon | 8/13/21/34/55 EMA alignment confirmation | Trend Following |
| Volume_Price_Confirmation | OBV divergence + volume spike confirmation | Volume |

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20+
- Bun (or npm)

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # .venv\Scripts\activate on Windows
pip install -r requirements.txt
cd src
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

API will be available at `http://localhost:8000`

### Frontend

```bash
cd frontend
bun install
bun run dev
```

Frontend will be available at `http://localhost:5173`

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Root with safety notice |
| GET | `/api/status` | Simulator status |
| GET | `/api/strategies` | List all 12 strategies |
| POST | `/api/simulator/start` | Start live paper trading |
| POST | `/api/simulator/stop` | Stop simulator |
| POST | `/api/simulator/configure` | Configure symbols/timeframes |
| GET | `/api/bullpen` | Strategy rankings & consensus |
| GET | `/api/signals` | Recent trading signals |
| GET | `/api/positions` | Open paper positions |
| POST | `/api/backtest` | Run backtest |
| GET | `/api/backtest/results` | All backtest results |
| GET | `/api/candles/{symbol}` | Candle data |
| GET | `/api/price/{symbol}` | Current price |
| GET | `/api/top-strategies` | Top N performers |
| WS | `/ws/signals` | Real-time signal stream |
| WS | `/ws/bullpen` | Real-time bullpen updates |

---

## Docker

```bash
# Build and run
docker build -t trading-simulator .
docker run -p 8000:8000 -e COINBASE_API_KEY=your_key trading-simulator
```

---

## Project Structure

```
.
├── backend/
│   ├── src/
│   │   ├── main.py              # FastAPI app
│   │   ├── strategies.py          # 12 trading strategies
│   │   ├── indicators.py          # Technical indicators
│   │   ├── simulator.py           # Trading simulator
│   │   ├── bullpen.py             # Strategy ranking
│   │   ├── backtesting.py         # Backtest engine
│   │   ├── data_ingestion.py      # Coinbase data feed
│   │   └── models.py              # Data models
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/            # UI components
│   │   └── lib/
│   │       ├── api.ts             # API client
│   │       └── types.ts           # TypeScript types
│   └── package.json
└── Dockerfile
```

---

## Environment Variables

```bash
# Optional - for higher rate limits
COINBASE_API_KEY=your_api_key
COINBASE_API_SECRET=your_api_secret
```

All data fetching is read-only. No trading permissions required.

---

## License

MIT
