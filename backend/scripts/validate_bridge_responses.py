#!/usr/bin/env python3
"""
Bridge Response Validator

Validates end-to-end responses from the HRM bridge under production-like traffic.
Ensures that the action (execute_trade/hold), blocked_reason, and prediction
envelope are consistent and conform to the contract.
"""

import sys
import os
import json
import argparse
from typing import Dict, Any

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.src import freqtrade_proxy


def validate_response(request: Dict[str, Any], response: Dict[str, Any]):
    """Validate that a bridge response is consistent with its request."""
    print(f"Validating response for signal: {request.get('signal_id')}")
    
    # Check basic fields
    for field in ("action", "prediction", "ring_context", "agent_latency_ms"):
        if field not in response:
            print(f"❌ FAIL: Missing field '{field}' in response")
            return False
            
    action = response["action"]
    prediction = response["prediction"]
    blocked_reason = response.get("blocked_reason")
    
    # Action consistency
    if action == "execute_trade":
        if blocked_reason is not None:
            print(f"❌ FAIL: Action is execute_trade but blocked_reason is {blocked_reason}")
            return False
    elif action == "hold":
        if blocked_reason is None:
            print(f"❌ FAIL: Action is hold but blocked_reason is None")
            return False
            
    # Schema-specific validation
    schema = request.get("schema")
    if schema == "moneyfan.freqtrade.handoff.v1":
        req_model = request.get("model", {})
        if prediction["confidence"] != req_model.get("confidence"):
            print(f"❌ FAIL: Confidence mismatch in response")
            return False
            
    print(f"✓ Response valid: action={action}, latency={response['agent_latency_ms']}ms")
    return True


def main():
    parser = argparse.ArgumentParser(description="Bridge Response Validator")
    parser.add_argument("--request", help="Path to request JSON")
    parser.add_argument("--response", help="Path to response JSON")
    
    args = parser.parse_args()
    
    if args.request and args.response:
        with open(args.request, 'r') as f:
            req = json.load(f)
        with open(args.response, 'r') as f:
            res = json.load(f)
        
        success = validate_response(req, res)
        sys.exit(0 if success else 1)
    else:
        # Run a self-test with mock data
        print("Running self-test...")
        mock_req = {
            "schema": "moneyfan.freqtrade.handoff.v1",
            "signal_id": "test-1",
            "model": {"confidence": 0.9}
        }
        mock_res = {
            "action": "execute_trade",
            "prediction": {"confidence": 0.9},
            "ring_context": {"active_version": "v1"},
            "agent_latency_ms": 10.5
        }
        success = validate_response(mock_req, mock_res)
        
        # Test failure case
        print("\nTesting failure case (inconsistent action)...")
        mock_res["action"] = "hold" # Should have blocked_reason
        success_fail = validate_response(mock_req, mock_res)
        
        if success and not success_fail:
            print("\n✓ Self-test passed.")
        else:
            print("\n❌ Self-test failed.")
            sys.exit(1)


if __name__ == "__main__":
    main()
