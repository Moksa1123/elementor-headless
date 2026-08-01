#!/usr/bin/env python3
"""Fix grid layout defaults in elementor-schema.json."""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA_FILE = HERE.parent / "data" / "elementor-schema.json"

def main():
    # Load schema
    schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))

    # Fix container controls
    container = schema["elements"]["container"]

    changes = 0
    for ctrl in container.get("controls", []):
        name = ctrl.get("name")

        if name == "grid_columns_grid":
            if isinstance(ctrl.get("default"), dict) and ctrl["default"].get("size") == 3:
                ctrl["default"]["size"] = 2
                print(f"✓ grid_columns_grid: 3 → 2")
                changes += 1

        elif name == "grid_rows_grid":
            if isinstance(ctrl.get("default"), dict) and ctrl["default"].get("size") == 2:
                ctrl["default"]["size"] = 1
                print(f"✓ grid_rows_grid: 2 → 1")
                changes += 1

    if changes > 0:
        # Save back
        SCHEMA_FILE.write_text(
            json.dumps(schema, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8"
        )
        print(f"\n✅ {changes} defaults fixed. Schema saved.")
    else:
        print("❌ No changes made - defaults not found or already fixed.")

if __name__ == "__main__":
    main()
