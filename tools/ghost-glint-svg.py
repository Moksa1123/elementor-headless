#!/usr/bin/env python3
"""Generate the "ghost text" SVG (outline-stroke text + animated shine
clipPath) for arbitrary text, standalone — no WordPress context needed.

Use this to preview/tune the proportions before wiring the same formula into
a PHP shortcode (see references/dynamic-ghost-text-pattern.md for the
PHP version and how these ratios were derived).

Usage:
    python tools/ghost-glint-svg.py "LING"
    python tools/ghost-glint-svg.py "RYE LIN" --size 64 --out preview.svg
    python tools/ghost-glint-svg.py "TEXT" --font-family "Space Grotesk" --weight 700
"""
from __future__ import annotations

import argparse
import hashlib
import math
import sys


# Ratios below were reverse-engineered from a real reference sample at one
# font-size with known text lengths (see the reference doc for the
# derivation method). Re-derive these for your own font/weight/spacing
# rather than trusting them blindly for a very different typeface.
PER_CHAR_WIDTH_RATIO = 0.719
HEIGHT_RATIO = 1.031
BASELINE_Y_RATIO = 0.771
RECT_HEIGHT_RATIO = 1.333
SHINE1_WIDTH_RATIO = 0.34
SHINE2_WIDTH_RATIO = 0.097
SHINE1_START_RATIO = -0.789
SHINE1_END_RATIO = 1.4
SHINE2_START_RATIO = -0.695
SHINE2_END_RATIO = 1.2


def build_svg(text: str, size: int, font_family: str, weight: int) -> str:
    text = text.upper()
    length = max(1, len(text))

    width = math.ceil(length * size * PER_CHAR_WIDTH_RATIO) + 8
    height = math.ceil(size * HEIGHT_RATIO)
    y = math.ceil(size * BASELINE_Y_RATIO)
    rect_h = math.ceil(size * RECT_HEIGHT_RATIO)

    shine_w1 = round(width * SHINE1_WIDTH_RATIO)
    shine_w2 = round(width * SHINE2_WIDTH_RATIO)
    start1 = -round(width * abs(SHINE1_START_RATIO)) if SHINE1_START_RATIO < 0 else round(width * SHINE1_START_RATIO)
    end1 = round(width * SHINE1_END_RATIO)
    start2 = -round(width * abs(SHINE2_START_RATIO)) if SHINE2_START_RATIO < 0 else round(width * SHINE2_START_RATIO)
    end2 = round(width * SHINE2_END_RATIO)

    uid = hashlib.md5(text.encode("utf-8")).hexdigest()[:8]
    esc = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    svg = (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg" aria-hidden="true" '
        f'style="max-width:100%;height:auto;display:block;overflow:visible;">'
        f'<defs><linearGradient id="gs{uid}" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="rgba(255,255,255,0)"/>'
        f'<stop offset="0.38" stop-color="rgba(255,255,255,0.16)"/>'
        f'<stop offset="0.5" stop-color="rgba(255,255,255,0.85)"/>'
        f'<stop offset="0.62" stop-color="rgba(255,255,255,0.16)"/>'
        f'<stop offset="1" stop-color="rgba(255,255,255,0)"/></linearGradient>'
        f'<clipPath id="gc{uid}"><text x="4" y="{y}" font-family="\'{font_family}\',sans-serif" '
        f'font-size="{size}" font-weight="{weight}" letter-spacing="3">{esc}</text></clipPath></defs>'
        f'<text x="4" y="{y}" font-family="\'{font_family}\',sans-serif" font-size="{size}" '
        f'font-weight="{weight}" letter-spacing="3" fill="none" stroke="rgba(255,255,255,0.25)" '
        f'stroke-width="1.2" vector-effect="non-scaling-stroke">{esc}</text>'
        f'<g clip-path="url(#gc{uid})">'
        f'<rect class="gb{uid}" x="0" y="-14" width="{shine_w1}" height="{rect_h}" '
        f'fill="url(#gs{uid})" transform="translate({start1},0) skewX(-18)"/>'
        f'<rect class="gb2{uid}" x="0" y="-14" width="{shine_w2}" height="{rect_h}" '
        f'fill="url(#gs{uid})" transform="translate({start2},0) skewX(-18)"/></g></svg>'
        f'<style>.gb{uid}{{animation:gk{uid} 6s linear infinite;will-change:transform;}}'
        f'.gb2{uid}{{animation:gk2{uid} 6s linear infinite;animation-delay:.45s;will-change:transform;}}'
        f'@keyframes gk{uid}{{0%{{transform:translateX({start1}px) skewX(-18deg);}}'
        f'100%{{transform:translateX({end1}px) skewX(-18deg);}}}}'
        f'@keyframes gk2{uid}{{0%{{transform:translateX({start2}px) skewX(-18deg);}}'
        f'100%{{transform:translateX({end2}px) skewX(-18deg);}}}}</style>'
    )
    return svg


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate a dynamic ghost-text SVG for previewing.")
    ap.add_argument("text", help="Text to render (will be upper-cased)")
    ap.add_argument("--size", type=int, default=64, help="Font size in px (default: 64)")
    ap.add_argument("--font-family", default="Space Grotesk", help="Font family (default: Space Grotesk)")
    ap.add_argument("--weight", type=int, default=700, help="Font weight (default: 700)")
    ap.add_argument("--out", help="Write to a file instead of stdout")
    args = ap.parse_args()

    svg = build_svg(args.text, args.size, args.font_family, args.weight)
    html = f"<!doctype html><html><body style=\"background:#0A0A0C;padding:60px;\">{svg}</body></html>"

    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(html)
        print(f"Wrote preview HTML to {args.out} — open it in a browser to check proportions/animation.")
    else:
        print(svg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
