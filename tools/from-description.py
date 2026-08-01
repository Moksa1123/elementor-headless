#!/usr/bin/env python3
"""
Generate Elementor JSON from natural language description.

Usage:
    python tools/from-description.py "
    - Hero section: large title + subtitle + gradient background + CTA button
    - 3-column cards: image + title + description
    - Contact form
    " --output page.json

Uses Claude to understand the description and generate _elementor_data JSON.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE.parent / "data"

# Try to import Claude SDK
try:
    import anthropic
except ImportError:
    print("❌ Claude SDK not installed. Install with: pip install anthropic", file=sys.stderr)
    sys.exit(1)


ELEMENTOR_PROMPT = """You are an expert Elementor JSON builder. Convert the user's description of a webpage into valid Elementor _elementor_data JSON.

RULES:
1. Output ONLY valid JSON (no markdown, no explanation)
2. Use unique 7-char hex IDs for each element (e.g., "a1b2c3d")
3. Always wrap top-level in a list (even single element)
4. For containers: set container_type to "flex" or "grid", flex_direction to "row"/"column"
5. For text: use "text-editor" widget with "editor" setting containing HTML
6. For buttons: use "button" widget with "text" and "link" settings
7. For headings: use "heading" widget with "title" and "header_size" ("h1"-"h6")
8. For images: use "image" widget with "image" setting {url, id, size}
9. Layout: hero sections are usually containers with flex-direction column; multi-column grids use flex-direction row
10. Every element needs: id, elType ("widget"/"container"), widgetType (null for containers), settings, elements (empty [] for leaves)

RESPONSE FORMAT:
{JSON_ONLY}

Example structure:
[
  {
    "id": "a1b2c3d",
    "elType": "container",
    "widgetType": null,
    "settings": {
      "container_type": "flex",
      "flex_direction": "column",
      "background_background": "classic",
      "background_color": "#f5f5f5"
    },
    "elements": [
      {
        "id": "e4f5a6b",
        "elType": "widget",
        "widgetType": "heading",
        "settings": {
          "title": "Section Title",
          "header_size": "h2"
        },
        "elements": []
      }
    ]
  }
]

User's description: {description}

Generate the Elementor JSON for this page layout:"""


def generate_from_description(description: str, api_key: str | None = None) -> str:
    """Generate Elementor JSON from natural language description."""
    if not api_key:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("❌ ANTHROPIC_API_KEY not set. Set it or pass --api-key", file=sys.stderr)
            sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    print(f"🤖 Generating Elementor JSON from description...", file=sys.stderr)

    prompt = ELEMENTOR_PROMPT.format(description=description)

    message = client.messages.create(
        model="claude-opus-4-1",  # Use Opus for better reasoning
        max_tokens=4000,
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
    )

    response_text = message.content[0].text

    # Try to extract JSON if wrapped in markdown code block
    if "```json" in response_text:
        start = response_text.find("```json") + 7
        end = response_text.find("```", start)
        response_text = response_text[start:end].strip()
    elif "```" in response_text:
        start = response_text.find("```") + 3
        end = response_text.find("```", start)
        response_text = response_text[start:end].strip()

    # Validate JSON
    try:
        data = json.loads(response_text)
        print(f"✓ Generated valid JSON", file=sys.stderr)
        return json.dumps(data, indent=2, ensure_ascii=False)
    except json.JSONDecodeError as e:
        print(f"❌ Failed to parse generated JSON: {e}", file=sys.stderr)
        print(f"Response was:\n{response_text}", file=sys.stderr)
        sys.exit(1)


def main():
    import os

    p = argparse.ArgumentParser(
        description="Generate Elementor JSON from natural language",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/from-description.py "Hero + 3 cards + footer form"
  python tools/from-description.py "Tall hero with gradient + contact form" \\
    --output page.json --api-key sk-...
        """,
    )
    p.add_argument("description", help="description of the page layout")
    p.add_argument("--output", "-o", help="output JSON file")
    p.add_argument("--api-key", help="Anthropic API key (or set ANTHROPIC_API_KEY env var)")

    args = p.parse_args()

    json_str = generate_from_description(args.description, args.api_key)

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(json_str + "\n", encoding="utf-8")
        print(f"✓ Written: {output_path}")
        print(f"Next: python tools/validate-page.py {output_path}")
    else:
        print(json_str)


if __name__ == "__main__":
    main()
