#!/usr/bin/env python3
"""
sweep-hover.py - verify the :hover rules by actually hovering.

    python tools/sweep-hover.py <sweep-dir> --url https://site/page/ \
        --apply "bash apply.sh {name}" --out data/hover-verification.csv

The browser sweep left 8,135 probes marked `hover-only`: real rules, seeded with
real values, sitting in the delivered stylesheet - and unverifiable by any static
read, because a :hover rule only APPLIES while a pointer is over the node.

So this drives the pointer. For every control whose selector template carries
`:hover`, it resolves which node must be hovered (the compound the pseudo-class
sits on) and which node the declaration lands on, hovers with a real mouse event,
reads `getComputedStyle`, and compares against what Elementor declared in the
stylesheet the page actually linked.

One deliberate intervention, disclosed: `transition: none !important` is injected
before probing. The sweep seeds transition DURATIONS too (`border_hover_transition:
79s`), and reading a computed colour 200ms into a 79-second transition compares a
mid-animation frame against the end state. Killing transitions asserts the end
state; the transition properties themselves are asserted by the text sweeps.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, HERE / fname)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


SB = _load("sweep_browser", "sweep-browser.py")     # declared_map, comparable
VB = _load("verify_browser", "verify-browser.py")   # load_selectors

RUN_NONCE = time.strftime("%H%M%S")
DEVICE_PREFIX = re.compile(r"^\((?:desktop|tablet|mobile|widescreen|laptop)[^)]*\)\s*")

CSSOM_JS = SB.CSSOM_JS

HOVER_JS = r"""
(probes) => {
  const out = [];
  for (const p of probes) {
    let target = null;
    try { target = document.querySelector(p.computed_sel); } catch (e) {}
    out.push({i: p.i, found: !!target});
  }
  return out;
}
"""


def resolve(tpl: str, el_id: str) -> str:
    t = DEVICE_PREFIX.sub("", tpl)
    return t.replace("{{WRAPPER}}", f".elementor-element-{el_id}")


def split_hover(sel: str) -> tuple[str, str] | None:
    """
    (node to HOVER, node the declaration LANDS on).

    `.x:hover .btn`  -> hover `.x`,          read `.x .btn`
    `.x .btn:hover`  -> hover `.x .btn`,     read `.x .btn`
    Focus/active/visited states need more than a pointer; they are out of scope.
    """
    if ":hover" not in sel or re.search(r":(focus|active|visited)\b", sel):
        return None
    i = sel.index(":hover")
    hover_target = sel[:i]
    computed_target = sel.replace(":hover", "")
    # the hover target must be a complete selector - it is everything up to the
    # pseudo, which always ends a compound
    return hover_target.strip(), re.sub(r"\s+", " ", computed_target).strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sweep", type=Path)
    ap.add_argument("--url", required=True)
    ap.add_argument("--apply", required=True)
    ap.add_argument("--out", default="data/hover-verification.csv")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("pip install playwright && playwright install chromium", file=sys.stderr)
        return 2

    schema = _load("sweep_controls", "sweep-controls.py").load_schema()
    sels = VB.load_selectors()
    plan = json.loads((a.sweep / "plan.json").read_text(encoding="utf-8"))
    batches = plan["batches"][: a.limit] if a.limit else plan["batches"]
    env = {**os.environ, "MSYS_NO_PATHCONV": "1"}

    rows: list[dict] = []

    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 1440, "height": 1000})

        for bi, batch in enumerate(batches):
            cmd = a.apply.replace("{name}", batch["file"])
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, env=env)
            if r.returncode != 0:
                print(f"  apply FAILED {batch['file']}")
                continue
            try:
                pg.goto(f"{a.url}?ehh={RUN_NONCE}-{bi}", wait_until="load", timeout=45000)
            except Exception as e:
                print(f"  goto FAILED {batch['file']}: {str(e)[:60]}")
                continue
            pg.add_style_tag(content="* { transition: none !important; animation: none !important; }")
            pg.wait_for_timeout(250)

            decl = SB.declared_map(pg.evaluate(CSSOM_JS))

            # every hover-carrying (element, control, prop) on this batch's page
            tree = json.loads((a.sweep / batch["file"]).read_text(encoding="utf-8"))
            els: list[dict] = []

            def walk(ns):
                for e in ns:
                    els.append(e)
                    walk(e.get("elements") or [])
            walk(tree)

            for el in els:
                owner = el.get("widgetType") if el["elType"] == "widget" else el["elType"]
                ctrls = VB.controls_for(schema, el)
                for key in (el.get("settings") or {}):
                    base = key
                    if key.endswith(("_tablet", "_mobile")):
                        continue
                    c = ctrls.get(base)
                    if not c or not c.get("css"):
                        continue
                    for tpl, props in (sels.get((owner, base)) or []):
                        if ":hover" not in tpl:
                            continue
                        parts = split_hover(resolve(tpl, el["id"]))
                        if not parts:
                            continue
                        hover_sel, read_sel = parts
                        norm = re.sub(r"\s+", " ", resolve(tpl, el["id"]))
                        declared = decl.get(norm, {})
                        for prop in props:
                            dval = declared.get(prop, "")
                            if not dval or "{{" in dval:
                                continue
                            try:
                                loc = pg.locator(hover_sel).first
                                loc.hover(timeout=2500, force=True)
                                pg.wait_for_timeout(60)
                                got = pg.evaluate(
                                    "([s, p]) => { const e = document.querySelector(s);"
                                    "  if (!e) return null;"
                                    "  const cs = getComputedStyle(e);"
                                    "  return p.startsWith('--') ? cs.getPropertyValue(p).trim()"
                                    "                            : cs.getPropertyValue(p); }",
                                    [read_sel, prop])
                            except Exception:
                                got = None
                            if got is None:
                                status = "no-target-node"
                            else:
                                ok, match = SB.comparable(prop, dval, str(got))
                                status = ("verified" if ok and match
                                          else "OVERRIDDEN" if ok else "not-comparable")
                            rows.append({
                                "element": el["id"], "owner": owner, "control": base,
                                "property": prop, "declared": dval,
                                "computed": got or "", "status": status,
                            })
            done = bi + 1
            v = sum(1 for x in rows if x["status"] == "verified")
            o = sum(1 for x in rows if x["status"] == "OVERRIDDEN")
            print(f"  [{done:>2}/{len(batches)}] {batch['file']}  "
                  f"hover probes so far: {len(rows):,}  verified {v:,}  overridden {o}")
        b.close()

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["element", "owner", "control", "property",
                                          "declared", "computed", "status"])
        w.writeheader()
        w.writerows(rows)

    c = Counter(r["status"] for r in rows)
    t = sum(c.values())
    print()
    print(f"HOVER RULES, DRIVEN BY A REAL POINTER  ({t:,} probes)")
    for k, n in c.most_common():
        print(f"    {k:<16}{n:>7,}  ({100 * n / t:5.1f}%)")
    bad = [r for r in rows if r["status"] == "OVERRIDDEN"]
    if bad:
        pat = Counter((r["control"], r["property"]) for r in bad)
        print()
        print("overridden patterns:")
        for (ctl, prop), n in pat.most_common(10):
            ex = next(r for r in bad if r["control"] == ctl and r["property"] == prop)
            print(f"  {n:4}x {ctl:34} {prop:22} "
                  f"{ex['declared'][:18]!r} -> {ex['computed'][:22]!r}")
    print(f"\n  written {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
