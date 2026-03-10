#!/usr/bin/env python3
"""
Compare Report History Review Helper

Provides a CLI tool to compare two machine-readable JSON artifacts 
(e.g., synthetic competency reports, daily runbooks, or training results)
and index the differences.
"""

import sys
import os
import json
import argparse
from typing import Any, Dict, List


def get_deep(data: Dict[str, Any], path: str) -> Any:
    """Get nested value using dot notation."""
    parts = path.split(".")
    val = data
    for part in parts:
        if isinstance(val, dict) and part in val:
            val = val[part]
        else:
            return None
    return val


def compare_dicts(d1: Any, d2: Any, path: str = "") -> List[Dict[str, Any]]:
    """Recursively compare two dictionaries and return a list of diffs."""
    diffs = []
    
    if type(d1) != type(d2):
        diffs.append({
            "path": path,
            "type": "type_mismatch",
            "v1": str(type(d1)),
            "v2": str(type(d2))
        })
        return diffs

    if isinstance(d1, dict):
        keys = set(d1.keys()) | set(d2.keys())
        for k in keys:
            new_path = f"{path}.{k}" if path else k
            if k not in d1:
                diffs.append({"path": new_path, "type": "added", "v2": d2[k]})
            elif k not in d2:
                diffs.append({"path": new_path, "type": "removed", "v1": d1[k]})
            else:
                diffs.extend(compare_dicts(d1[k], d2[k], new_path))
    elif isinstance(d1, list):
        if len(d1) != len(d2):
            diffs.append({
                "path": path,
                "type": "length_mismatch",
                "v1": len(d1),
                "v2": len(d2)
            })
        # Basic list comparison (element by element if same length)
        # For complex reports we might need smarter list alignment
        for i in range(min(len(d1), len(d2))):
            diffs.extend(compare_dicts(d1[i], d2[i], f"{path}[{i}]"))
    else:
        if d1 != d2:
            diffs.append({
                "path": path,
                "type": "value_change",
                "v1": d1,
                "v2": d2
            })
            
    return diffs


def main():
    parser = argparse.ArgumentParser(description="Compare two JSON reports.")
    parser.get_default("include_pattern") # Dummy call to avoid linter noise if any
    parser.add_argument("file1", help="Path to first JSON file")
    parser.add_argument("file2", help="Path to second JSON file")
    parser.add_argument("--filter", help="Only show diffs under this path (dot notation)")
    parser.add_argument("--summary", action="store_true", help="Show only summary of changes")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.file1):
        print(f"Error: {args.file1} not found")
        sys.exit(1)
    if not os.path.exists(args.file2):
        print(f"Error: {args.file2} not found")
        sys.exit(1)
        
    with open(args.file1, 'r') as f:
        data1 = json.load(f)
    with open(args.file2, 'r') as f:
        data2 = json.load(f)
        
    diffs = compare_dicts(data1, data2)
    
    if args.filter:
        diffs = [d for d in diffs if d["path"].startswith(args.filter)]
        
    if not diffs:
        print("Reports are identical.")
        return

    print(f"Comparing {args.file1} -> {args.file2}")
    print(f"Found {len(diffs)} differences.")
    print("-" * 40)
    
    for d in diffs:
        dtype = d["type"]
        path = d["path"]
        if dtype == "value_change":
            print(f"[CHANGE] {path}: {d['v1']} -> {d['v2']}")
        elif dtype == "added":
            print(f"[ADDED]  {path}: {d['v2']}")
        elif dtype == "removed":
            print(f"[REMOVED] {path}: {d['v1']}")
        else:
            print(f"[{dtype.upper()}] {path}: {d.get('v1')} / {d.get('v2')}")


if __name__ == "__main__":
    main()
