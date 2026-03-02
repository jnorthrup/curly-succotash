"""
Coinbase Trading Simulator API
REST and WebSocket endpoints for the trading simulator.

SAFETY: This API provides READ-ONLY access to market data.
        NO live trading endpoints are implemented.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .models import Timeframe, SimulatorConfig
from .simulator import get_simulator, reset_simulator, CoinbaseTradingSimulator
from .bullpen import RankingMetric
from .backtesting import BacktestConfig

logger = logging.getLogger(__name__)


class BacktestRequest(BaseModel):
    symbols: List[str] = Field(default=["BTC-USD"])
    timeframes: List[str] = Field(default=["ONE_HOUR"])
    days_back: int = Field(default=90, ge=1, le=365)
    initial_capital: float = Field(default=10000.0, gt=0)


class SimulatorConfigRequest(BaseModel):
    symbols: List[str] = Field(default=["BTC-USD", "ETH-USD", "SOL-USD"])
    timeframes: List[str] = Field(default=["ONE_HOUR"])
    initial_capital: float = Field(default=10000.0, gt=0)
    position_size_pct: float = Field(default=5.0, gt=0, le=100)
    poll_interval_seconds: int = Field(default=60, ge=10)


class ConnectionManager:
    """WebSocket connection manager for real-time updates."""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.signal_connections: List[WebSocket] = []
        self.bullpen_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket, channel: str = "signals"):
        await websocket.accept()
        if channel == "signals":
            self.signal_connections.append(websocket)
        elif channel == "bullpen":
            self.bullpen_connections.append(websocket)
        else:
            self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket, channel: str = "signals"):
        if channel == "signals" and websocket in self.signal_connections:
            self.signal_connections.remove(websocket)
        elif channel == "bullpen" and websocket in self.bullpen_connections:
            self.bullpen_connections.remove(websocket)
        elif websocket in self.active_connections:
            self.active_connections.remove(websocket)
    
    async def broadcast_signal(self, signal: Dict[str, Any]):
        """Broadcast signal to all signal subscribers."""
        message = json.dumps({"type": "signal", "data": signal})
        for connection in self.signal_connections:
            try:
                await connection.send_text(message)
            except Exception:
                pass
    
    async def broadcast_bullpen(self, bullpen: Dict[str, Any]):
        """Broadcast bullpen update to all subscribers."""
        message = json.dumps({"type": "bullpen", "data": bullpen})
        for connection in self.bullpen_connections:
            try:
                await connection.send_text(message)
            except Exception:
                pass


manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("[API] Starting Coinbase Trading Simulator API")
    simulator = get_simulator()
    
    simulator.signal_emitter.subscribe(
        lambda signal: asyncio.create_task(manager.broadcast_signal(signal))
    )
    
    yield
    
    logger.info("[API] Shutting down simulator")
    await simulator.stop()


app = FastAPI(
    title="Coinbase Trading Simulator",
    description="Paper trading simulator with 12 SOTA strategies. READ-ONLY - NO LIVE TRADING.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    """API root - returns safety notice and status."""
    return {
        "name": "Coinbase Trading Simulator",
        "version": "1.0.0",
        "safety_notice": "⚠️ PAPER TRADING ONLY - NO LIVE ORDERS ARE PLACED",
        "status": "operational",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/api/status")
def get_status():
    """Get simulator status."""
    simulator = get_simulator()
    return simulator.get_status()


@app.get("/api/strategies")
def get_strategies():
    """Get information about all 12 trading strategies."""
    simulator = get_simulator()
    return {
        "count": 12,
        "strategies": simulator.get_strategy_info(),
    }


@app.post("/api/simulator/start")
async def start_simulator(background_tasks: BackgroundTasks):
    """Start the simulator in live paper trading mode."""
    simulator = get_simulator()
    
    if simulator.state.running:
        return {"status": "already_running", "message": "Simulator is already running"}
    
    background_tasks.add_task(simulator.start_live_paper_mode)
    
    return {
        "status": "starting",
        "message": "Simulator starting in live paper trading mode",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.post("/api/simulator/stop")
async def stop_simulator():
    """Stop the simulator."""
    simulator = get_simulator()
    await simulator.stop()
    
    return {
        "status": "stopped",
        "message": "Simulator stopped",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.post("/api/simulator/configure")
async def configure_simulator(config: SimulatorConfigRequest):
    """Configure and reset the simulator."""
    timeframes = [Timeframe(tf) for tf in config.timeframes]
    
    sim_config = SimulatorConfig(
        symbols=config.symbols,
        timeframes=timeframes,
        initial_capital=config.initial_capital,
        position_size_pct=config.position_size_pct,
        poll_interval_seconds=config.poll_interval_seconds,
    )
    
    simulator = reset_simulator(sim_config)
    
    return {
        "status": "configured",
        "config": sim_config.to_dict(),
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/api/bullpen")
def get_bullpen(
    ranking: str = Query(default="total_return", description="Ranking metric"),
    symbols: Optional[str] = Query(default=None, description="Comma-separated symbols"),
    timeframes: Optional[str] = Query(default=None, description="Comma-separated timeframes"),
):
    """Get bullpen view with strategy rankings and consensus signals."""
    simulator = get_simulator()
    
    try:
        ranking_metric = RankingMetric(ranking)
    except ValueError:
        ranking_metric = RankingMetric.TOTAL_RETURN
    
    symbol_list = symbols.split(",") if symbols else None
    tf_list = [Timeframe(tf.strip()) for tf in timeframes.split(",")] if timeframes else None
    
    return simulator.get_bullpen_view(
        ranking_metric=ranking_metric,
        symbols=symbol_list,
        timeframes=tf_list,
    )


@app.get("/api/signals")
def get_signals(limit: int = Query(default=50, ge=1, le=500)):
    """Get recent trading signals."""
    simulator = get_simulator()
    return {
        "count": limit,
        "signals": simulator.get_recent_signals(limit),
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/api/positions")
def get_positions():
    """Get all open paper positions."""
    simulator = get_simulator()
    positions = simulator.get_positions()
    return {
        "count": len(positions),
        "positions": positions,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.post("/api/backtest")
def run_backtest(request: BacktestRequest):
    """Run a backtest on historical data."""
    simulator = get_simulator()
    
    timeframes = [Timeframe(tf) for tf in request.timeframes]
    
    results = simulator.run_backtest(
        symbols=request.symbols,
        timeframes=timeframes,
        days_back=request.days_back,
        initial_capital=request.initial_capital,
    )
    
    return {
        "status": "completed",
        "config": {
            "symbols": request.symbols,
            "timeframes": request.timeframes,
            "days_back": request.days_back,
            "initial_capital": request.initial_capital,
        },
        "results_count": len(results),
        "results": [r.to_dict() for r in results[:24]],
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/api/backtest/results")
def get_backtest_results():
    """Get all stored backtest results."""
    simulator = get_simulator()
    results = simulator.backtest_engine.get_all_results()
    
    return {
        "count": len(results),
        "results": [r.to_dict() for r in results],
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/api/candles/{symbol}")
def get_candles(
    symbol: str,
    timeframe: str = Query(default="ONE_HOUR"),
    limit: int = Query(default=100, ge=1, le=1000),
):
    """Get candle data for a symbol."""
    simulator = get_simulator()
    
    try:
        tf = Timeframe(timeframe)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid timeframe: {timeframe}")
    
    candles = simulator.ingestion.get_candles(symbol, tf, limit)
    
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "count": len(candles),
        "candles": [c.to_dict() for c in candles],
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/api/price/{symbol}")
def get_price(symbol: str):
    """Get current USD price for a symbol."""
    simulator = get_simulator()
    valuation = simulator.get_usd_valuation(symbol)
    
    return {
        "symbol": symbol,
        "price_usd": valuation["price_usd"],
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/api/valuation")
def get_valuation(
    symbol: str = Query(..., description="Symbol to value"),
    amount: float = Query(default=1.0, description="Amount to value"),
):
    """Get USD valuation for an amount of a symbol."""
    simulator = get_simulator()
    return simulator.get_usd_valuation(symbol, amount)


@app.get("/api/safety/verify")
def verify_safety():
    """Verify that no trading capability exists."""
    from .coinbase_client import SafetyEnforcement, CoinbaseMarketDataClient
    
    client = CoinbaseMarketDataClient()
    results = SafetyEnforcement.run_all_checks(client)
    
    return {
        "safety_verified": results["all_passed"],
        "checks": results,
        "message": "✓ READ-ONLY mode confirmed" if results["all_passed"] else "⚠️ Safety check failed",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.websocket("/ws/signals")
async def websocket_signals(websocket: WebSocket):
    """WebSocket endpoint for real-time signal streaming."""
    await manager.connect(websocket, "signals")
    
    try:
        await websocket.send_json({
            "type": "connected",
            "channel": "signals",
            "message": "Connected to signal stream",
            "timestamp": datetime.utcnow().isoformat(),
        })
        
        while True:
            data = await websocket.receive_text()
            
            if data == "ping":
                await websocket.send_json({"type": "pong"})
            elif data == "status":
                simulator = get_simulator()
                await websocket.send_json({
                    "type": "status",
                    "data": simulator.get_status(),
                })
                
    except WebSocketDisconnect:
        manager.disconnect(websocket, "signals")


@app.websocket("/ws/bullpen")
async def websocket_bullpen(websocket: WebSocket):
    """WebSocket endpoint for real-time bullpen updates."""
    await manager.connect(websocket, "bullpen")
    
    try:
        await websocket.send_json({
            "type": "connected",
            "channel": "bullpen",
            "message": "Connected to bullpen stream",
            "timestamp": datetime.utcnow().isoformat(),
        })
        
        simulator = get_simulator()
        bullpen = simulator.get_bullpen_view()
        await websocket.send_json({"type": "bullpen", "data": bullpen})
        
        while True:
            data = await websocket.receive_text()
            
            if data == "ping":
                await websocket.send_json({"type": "pong"})
            elif data == "refresh":
                bullpen = simulator.get_bullpen_view()
                await websocket.send_json({"type": "bullpen", "data": bullpen})
                
    except WebSocketDisconnect:
        manager.disconnect(websocket, "bullpen")


@app.get("/api/consensus/{symbol}")
def get_consensus(
    symbol: str,
    timeframe: Optional[str] = Query(default=None),
):
    """Get consensus signal for a specific symbol."""
    simulator = get_simulator()
    
    tf = Timeframe(timeframe) if timeframe else None
    consensus = simulator.bullpen.get_consensus_for_symbol(symbol, tf)
    
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "consensus": [c.to_dict() for c in consensus],
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/api/top-strategies")
def get_top_strategies(
    n: int = Query(default=5, ge=1, le=12),
    metric: str = Query(default="total_return"),
):
    """Get top N performing strategies."""
    simulator = get_simulator()
    
    try:
        ranking_metric = RankingMetric(metric)
    except ValueError:
        ranking_metric = RankingMetric.TOTAL_RETURN
    
    top = simulator.bullpen.get_top_strategies(n, ranking_metric)
    
    return {
        "count": len(top),
        "metric": metric,
        "strategies": top,
        "timestamp": datetime.utcnow().isoformat(),
    }