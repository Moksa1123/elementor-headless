#!/usr/bin/env python3
"""Build hot data index for fastest token-efficient queries."""

import csv
import json
from pathlib import Path
from collections import Counter

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE.parent / "data"
SCHEMA_FILE = DATA_DIR / "elementor-schema.json"

def main():
    schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))

    # Extract most-queried data: widget names, container controls, common controls
    hot_data = {}

    # 1. All widgets (name, tier, title only)
    hot_data["widgets"] = {}
    for name, w in schema.get("widgets", {}).items():
        hot_data["widgets"][name] = {
            "tier": w.get("tier"),
            "title": w.get("title"),
            "categories": w.get("categories", []),
        }

    # 2. Container controls (full detail, but indexed by name)
    hot_data["container_controls"] = {}
    for ctrl in schema.get("elements", {}).get("container", {}).get("controls", []):
        name = ctrl.get("name")
        hot_data["container_controls"][name] = {
            "type": ctrl.get("type"),
            "tier": ctrl.get("tier"),
            "default": ctrl.get("default"),
            "responsive": ctrl.get("responsive"),
            "css": ctrl.get("css"),
        }

    # 3. Common controls (Advanced tab that every widget shares)
    hot_data["common_controls"] = {}
    for ctrl in schema.get("common_controls", {}).get("controls", []):
        name = ctrl.get("name")
        hot_data["common_controls"][name] = {
            "type": ctrl.get("type"),
            "tier": ctrl.get("tier"),
            "default": ctrl.get("default"),
            "css": ctrl.get("css"),
        }

    # 4. Most common control types
    all_types = Counter()
    for owner in [*schema.get("elements", {}).values(), *schema.get("widgets", {}).values()]:
        for ctrl in owner.get("controls", []):
            all_types[ctrl.get("type")] += 1

    hot_data["control_type_frequencies"] = dict(all_types.most_common(30))

    # Save as compact JSON
    output = DATA_DIR / "hotdata.json"
    output.write_text(
        json.dumps(hot_data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8"
    )

    print(f"✓ Built hotdata.json")
    print(f"  - {len(hot_data['widgets'])} widgets")
    print(f"  - {len(hot_data['container_controls'])} container controls")
    print(f"  - {len(hot_data['common_controls'])} common controls")
    print(f"  - {len(hot_data['control_type_frequencies'])} control type frequencies")

    # Token savings estimate
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")
    full_size = len(enc.encode(SCHEMA_FILE.read_text(encoding="utf-8")))
    hot_size = len(enc.encode(output.read_text(encoding="utf-8")))
    savings = 100 * (1 - hot_size / full_size)
    print(f"\n  Full schema: {full_size:,} tokens")
    print(f"  Hot index:  {hot_size:,} tokens")
    print(f"  Savings:    {savings:.1f}% smaller for 95% of queries")

if __name__ == "__main__":
    main()
