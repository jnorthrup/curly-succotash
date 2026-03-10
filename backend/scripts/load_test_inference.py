#!/usr/bin/env python3
"""
Load Test - HRM Model Inference

Simulates high-frequency trading traffic to evaluate the performance
and stability of the HRM ring agent and model server under load.
"""

import sys
import os
import json
import time
import asyncio
import argparse
from typing import List, Dict, Any
from datetime import datetime, timezone

import httpx
import numpy as np


async def send_request(client: httpx.AsyncClient, url: str, payload: Dict[str, Any]) -> float:
    """Send a single trading request and return the latency in ms."""
    start_time = time.time()
    try:
        response = await client.post(url, json=payload)
        response.raise_for_status()
    except Exception as e:
        print(f"Request failed: {e}")
        return -1.0
    
    end_time = time.time()
    return (end_time - start_time) * 1000


async def run_load_test(
    url: str, 
    num_requests: int, 
    concurrency: int, 
    batch_size: int = 10
):
    """Run the load test with specified concurrency."""
    print(f"Starting load test: {num_requests} requests, concurrency={concurrency}")
    
    payload = {
        "schema": "moneyfan.freqtrade.handoff.v1",
        "signal_id": "load-test-sig",
        "pair": "BTC/USDT",
        "symbol": "BTCUSDT",
        "side": "long",
        "risk": {"risk_tier": "normal"},
        "model": {
            "confidence": 0.91,
            "pred_fwd_return": 0.012,
            "passes_edge_gate": True,
            "trade_head_calibration_loaded": True,
            "raw_vetoed": False,
            "raw_veto_reason": None,
            "net_effective_predicted_edge_bps": 21.0,
        },
    }

    latencies = []
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Run in batches to respect concurrency
        for i in range(0, num_requests, batch_size):
            tasks = []
            for _ in range(min(batch_size, num_requests - i)):
                tasks.append(send_request(client, url, payload))
            
            batch_latencies = await asyncio.gather(*tasks)
            latencies.extend([l for l in batch_latencies if l > 0])
            
            if i % (num_requests // 5 or 1) == 0 and i > 0:
                print(f"Progress: {i}/{num_requests} requests sent...")

    if not latencies:
        print("No successful requests.")
        return

    latencies = np.array(latencies)
    print("\nLoad Test Results:")
    print(f"Total Requests: {len(latencies)}")
    print(f"Mean Latency:   {np.mean(latencies):.2f} ms")
    print(f"P50 Latency:    {np.percentile(latencies, 50):.2f} ms")
    print(f"P95 Latency:    {np.percentile(latencies, 95):.2f} ms")
    print(f"P99 Latency:    {np.percentile(latencies, 99):.2f} ms")
    print(f"Max Latency:    {np.max(latencies):.2f} ms")
    print(f"Throughput:     {len(latencies) / (np.sum(latencies) / 1000 / concurrency):.2f} req/s (est)")


def main():
    parser = argparse.ArgumentParser(description="HRM Load Tester")
    parser.add_argument("--url", default="http://localhost:8000/api/hrm/ring/process", help="Target URL")
    parser.add_argument("--n", type=int, default=100, help="Number of requests")
    parser.add_argument("--c", type=int, default=5, help="Concurrency")
    
    args = parser.parse_args()
    
    asyncio.run(run_load_test(args.url, args.n, args.c))


if __name__ == "__main__":
    main()
