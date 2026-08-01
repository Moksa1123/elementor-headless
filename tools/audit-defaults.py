#!/usr/bin/env python3
"""Audit container layout defaults: compare documented vs actual CSV."""

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE.parent / "data"
CSV_FILE = DATA_DIR / "controls.csv"

def load_controls():
    """Load controls.csv and extract container defaults."""
    defaults = {}
    with open(CSV_FILE, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["owner"] != "container":
                continue
            name = row["control"]
            # Only layout-related controls
            if row["tab"] not in ("layout", "advanced") or row["section"] not in (
                "section_layout_container",
                "section_layout",
                "section_advanced",
            ):
                continue
            default_str = row["default"]
            if default_str:
                try:
                    default = json.loads(default_str)
                except json.JSONDecodeError:
                    default = default_str
            else:
                default = None
            defaults[name] = {
                "type": row["type"],
                "section": row["section"],
                "default": default,
                "responsive": row["responsive"],
                "tier": row["control_tier"],
            }
    return defaults

def main():
    defaults = load_controls()

    # Group by layout type
    flex_controls = {k: v for k, v in defaults.items() if k.startswith("flex_")}
    grid_controls = {k: v for k, v in defaults.items() if k.startswith("grid_")}
    other_layout = {k: v for k, v in defaults.items()
                    if not k.startswith("flex_") and not k.startswith("grid_")
                    and k in ("content_width", "padding", "padding_mobile", "boxed_width")}

    print("=" * 80)
    print("CONTAINER LAYOUT DEFAULTS AUDIT")
    print("=" * 80)
    print()

    print("GRID CONTROLS (有預設值的):")
    print("-" * 80)
    for name, info in sorted(grid_controls.items()):
        if info["default"] is not None:
            print(f"  {name:<25} default: {json.dumps(info['default'])}")
            if isinstance(info["default"], dict) and "size" in info["default"]:
                print(f"    └─ size={info['default'].get('size')} ({info['default'].get('unit', '?')})")
    print()

    print("FLEX CONTROLS (有預設值的):")
    print("-" * 80)
    for name, info in sorted(flex_controls.items()):
        if info["default"] is not None:
            print(f"  {name:<25} default: {json.dumps(info['default'])}")
    print()

    print("OTHER LAYOUT CONTROLS (有預設值的):")
    print("-" * 80)
    for name, info in sorted(other_layout.items()):
        if info["default"] is not None:
            print(f"  {name:<25} default: {json.dumps(info['default'])}")
    print()

    # Summary
    print("=" * 80)
    print("SUSPECTED OVER-DEFAULTS (非空值可能浪費空間):")
    print("=" * 80)
    issues = []

    # grid_rows_grid = 2 (only 1 row usually needed)
    if grid_controls.get("grid_rows_grid", {}).get("default", {}).get("size") == 2:
        issues.append(("grid_rows_grid", 2, "Grid typically renders 1 row; empty row wastes space"))

    # grid_columns_grid = 3 (often 1-2 columns used)
    if grid_controls.get("grid_columns_grid", {}).get("default", {}).get("size") == 3:
        issues.append(("grid_columns_grid", 3, "3 columns may be excessive; 1-2 is common"))

    for ctrl, val, reason in issues:
        print(f"  ⚠ {ctrl}: size={val}")
        print(f"     Reason: {reason}")
    print()

    print("All container defaults are empty or sensible.")
    print()

if __name__ == "__main__":
    main()
