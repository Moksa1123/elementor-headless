#!/usr/bin/env python3
"""
sweep-browser.py - drive EVERY control through a real browser, one at a time.

    python tools/sweep-browser.py <sweep-dir> \
        --url https://site/eh-sweep/ \
        --apply "ssh host 'cd /path/to/wp && wp eval-file /tmp/tools/apply-page.php 1203 {batch}'" \
        --out data/browser-verification.csv

This is the last honest check, and the only one that answers the question anyone
actually has: DOES THE PAGE RENDER RIGHT?

Everything else in this repo reads text.

    sweep-controls.py   the compiled stylesheet     "the rule is in the file"
    sweep-classes.py    the rendered HTML           "the class is on the wrapper"
    verify-live.py      both, through the CDN       "the file the public gets has it"

None of them can see the gap between a rule EXISTING and a rule APPLYING:

  - a theme selector with higher specificity quietly outranks Elementor's
  - a later stylesheet overwrites it
  - the selector matches no node in the actual DOM
  - the declaration is fine and the layout still collapses

So this one applies each batch, opens the page in Chromium, and asks
`getComputedStyle` on the node the rule ACTUALLY TARGETS - which is what
`data/css-selectors.csv` is for. A control's selectors are BRANCHES, not a set: the
icon-box's `primary_color` compiles one rule for the stacked view and another for
the framed one, and a sibling control decides which is live. The other matching
nothing is correct, and treating it as a failure buries the real ones.

It also checks, at 1440 / 768 / 375 px, the things only a layout engine knows: no
sideways scroll, no element rendered at zero size, no JS errors.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

# ---------------------------------------------------------------------------
# DECLARED vs COMPUTED.
#
# The first version of this tool predicted the value itself - "I wrote 486, so the
# browser should say 486px". That is the wrong question twice over. It guesses at
# Elementor's interpolation (`opacity: {{SIZE}}` takes no unit, so it demanded
# `486px` and failed a page that was perfectly correct), and it never actually asks
# the thing worth asking.
#
# The right question is: DID THE BROWSER APPLY WHAT ELEMENTOR DECLARED?
#
# Elementor's declaration is already in the compiled stylesheet - the very bytes the
# public downloaded. So read the declared value out of that, ask the browser what it
# computed, and compare. A mismatch means the rule is in the file and LOST: outranked
# by the theme, overwritten later in the cascade, or beaten on specificity. That is
# the failure mode no text-level check can ever see, and it is the only reason to
# drive a browser at all.
# ---------------------------------------------------------------------------

HEX = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
PX = re.compile(r"^-?\d+(?:\.\d+)?px$")
KEYWORD_PROPS = {
    "display", "text-align", "flex-direction", "flex-wrap", "justify-content",
    "align-items", "align-self", "position", "background-repeat", "background-size",
    "background-attachment", "text-transform", "font-style", "font-weight",
    "text-decoration", "border-style", "object-fit", "white-space", "overflow",
    "visibility", "float", "clear", "cursor", "direction",
}
COLOR_PROPS = {"color", "background-color", "border-color", "fill", "stroke",
               "outline-color", "caret-color", "column-rule-color"}


def norm_color(v: str) -> str | None:
    v = v.strip()
    m = HEX.match(v)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return f"rgb({int(h[0:2], 16)}, {int(h[2:4], 16)}, {int(h[4:6], 16)})"
    m = re.match(r"^rgba?\(([^)]+)\)$", v)
    if m:
        parts = [p.strip() for p in re.split(r"[,\s/]+", m.group(1)) if p.strip()]
        if len(parts) >= 3:
            try:
                r, g, b = (int(float(x)) for x in parts[:3])
            except ValueError:
                return None
            if len(parts) >= 4 and float(parts[3]) < 1:
                return f"rgba({r}, {g}, {b}, {float(parts[3]):g})"
            return f"rgb({r}, {g}, {b})"
    return None


def comparable(prop: str, declared: str, computed: str) -> tuple[bool, bool]:
    """
    (is it comparable at all, does it match).

    Only where the browser's normalisation is predictable. `line-height: 1.5`
    computes to `24px`; `transition` gets reordered; a font stack gets quoted. Those
    are not disagreements, and reporting them as failures would bury the real ones.
    """
    d, c = declared.strip(), computed.strip()
    if not d or "{{" in d or "var(" in d:
        return False, False
    base = prop.lstrip("-")
    if base in COLOR_PROPS or prop.startswith("--") and norm_color(d):
        nd, nc = norm_color(d), norm_color(c)
        if nd and nc:
            return True, nd == nc
        return False, False
    if PX.match(d):
        return True, c.strip() == d
    if base in KEYWORD_PROPS:
        return True, c.lower() == d.lower()
    return False, False


SEL_SPLIT = re.compile(r"\s*,\s*")


def declared_map(css: str) -> dict[str, dict[str, str]]:
    """selector -> {property: declared value}, from the stylesheet the public got."""
    out: dict[str, dict[str, str]] = {}
    i, n = 0, len(css)
    while i < n:
        b = css.find("{", i)
        if b < 0:
            break
        sel_text = css[i:b].strip()
        depth, j = 1, b + 1
        while j < n and depth:
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
            j += 1
        body = css[b + 1:j - 1]
        if sel_text.startswith("@"):
            # Only the desktop cascade; the breakpoints are the CSS sweep's job.
            if sel_text.startswith("@media") and "max-width" not in sel_text:
                for s, decls in declared_map(body).items():
                    out.setdefault(s, {}).update(decls)
        elif sel_text:
            decls: dict[str, str] = {}
            depth2 = 0
            buf = ""
            for ch in body:
                if ch == "(":
                    depth2 += 1
                elif ch == ")":
                    depth2 -= 1
                if ch == ";" and depth2 == 0:
                    if ":" in buf:
                        k, _, v = buf.partition(":")
                        decls[k.strip()] = v.strip()
                    buf = ""
                else:
                    buf += ch
            if ":" in buf:
                k, _, v = buf.partition(":")
                decls[k.strip()] = v.strip()
            for s in SEL_SPLIT.split(sel_text):
                s = re.sub(r"\s+", " ", s.strip())
                if s:
                    out.setdefault(s, {}).update(decls)
        i = j
    return out

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import importlib.util


def _load(name: str, fname: str):
    spec = importlib.util.spec_from_file_location(name, HERE / fname)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


VB = _load("verify_browser", "verify-browser.py")   # selectors, probe, JS, folding
SC = _load("sweep_controls", "sweep-controls.py")   # schema loader, controls_of


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sweep", type=Path, help="a directory made by sweep-controls.py plan")
    ap.add_argument("--url", required=True, help="the PUBLIC url of the sweep post")
    ap.add_argument("--apply", required=True,
                    help="shell command that applies one batch. `{batch}` is replaced "
                         "with the batch file path AS THE APPLYING MACHINE SEES IT.")
    ap.add_argument("--remote-dir", default=None,
                    help="the sweep directory as the applying machine sees it "
                         "(defaults to the local path)")
    ap.add_argument("--out", default="data/browser-verification.csv")
    ap.add_argument("--widths", nargs="+", type=int, default=[1440, 768, 375])
    ap.add_argument("--limit", type=int, default=0, help="only the first N batches")
    a = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("This one needs a browser:\n"
              "  pip install playwright && playwright install chromium", file=sys.stderr)
        return 2

    schema = SC.load_schema()
    sels = VB.load_selectors()
    plan = json.loads((a.sweep / "plan.json").read_text(encoding="utf-8"))
    batches = plan["batches"][: a.limit] if a.limit else plan["batches"]
    remote = a.remote_dir or str(a.sweep)

    rows: list[dict] = []
    layout_problems: list[str] = []
    console_errors: Counter = Counter()

    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": a.widths[0], "height": 1000})
        pg.on("pageerror", lambda e: console_errors.update([str(e)[:120]]))

        for bi, batch in enumerate(batches):
            # `{batch}` is the full remote path; `{name}` is just the file name.
            #
            # Prefer `{name}` when the command crosses a Windows shell. git-bash
            # rewrites any argument that LOOKS like a POSIX path into a Windows one
            # before handing it to a child, so the server's
            # `/tmp/ehx/psweep/batch-000.json` arrives as `C:/Users/.../tmp/ehx/...`
            # and every apply fails with "cannot read". Build the remote path on the
            # remote side and nothing can rewrite it.
            cmd = (a.apply
                   .replace("{batch}", f"{remote}/{batch['file']}")
                   .replace("{name}", batch["file"]))
            env = {**os.environ, "MSYS_NO_PATHCONV": "1"}
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, env=env)
            if r.returncode != 0:
                print(f"  apply FAILED for {batch['file']}: {r.stderr[:120]}")
                continue

            tree = json.loads((a.sweep / batch["file"]).read_text(encoding="utf-8"))
            probe = VB.build_probe(tree, schema, sels)
            ids: list[str] = []

            def collect(ns):
                for e in ns:
                    ids.append(e["id"])
                    collect(e.get("elements") or [])
            collect(tree)

            # A distinct URL per batch. A shared edge cache will otherwise hand back
            # the PREVIOUS batch's page and the whole sweep scores itself against one
            # render - which looks exactly like everything passing.
            pg.set_viewport_size({"width": a.widths[0], "height": 1000})
            # "networkidle" never fires on a page that keeps a connection open
            # (analytics, a chat widget) - batch 19 hung for 30s and killed the
            # whole run. "load" + a beat for Elementor's frontend JS is enough:
            # we read computed styles, not network activity.
            for attempt in (1, 2):
                try:
                    pg.goto(f"{a.url}?ehsweep={bi}", wait_until="load", timeout=45000)
                    break
                except Exception as e:
                    if attempt == 2:
                        print(f"  goto FAILED for {batch['file']}: {str(e)[:100]}")
            else:
                continue
            pg.wait_for_timeout(400)

            # What Elementor DECLARED, out of the stylesheet the public downloaded.
            css_file = a.sweep / "css" / batch["file"].replace(".json", ".css")
            decl = declared_map(css_file.read_text(encoding="utf-8", errors="replace")) \
                if css_file.exists() else {}

            results, dead = VB.fold_branches(pg.evaluate(VB.JS, probe))
            for res in results:
                sel = res.get("used") or ""
                declared = decl.get(re.sub(r"\s+", " ", sel), {}).get(res["prop"], "")
                if res["got"] is None:
                    status = "hover-only" if res.get("onlyPseudo") else "no-target-node"
                elif not declared:
                    # The browser found the node, but Elementor never wrote this
                    # property for it - a branch of the control that is not live.
                    status = "not-declared"
                else:
                    ok, match = comparable(res["prop"], declared, str(res["got"]))
                    status = ("verified" if ok and match
                              else "OVERRIDDEN" if ok
                              else "not-comparable")
                rows.append({
                    "batch": batch["file"], "element": res["id"],
                    "control": res["control"], "property": res["prop"],
                    "declared": declared, "computed": res["got"] or "",
                    "selector": sel or (res.get("tried") or ""),
                    "status": status,
                })

            for w in a.widths:
                pg.set_viewport_size({"width": w, "height": 1000})
                pg.wait_for_timeout(120)
                lay = pg.evaluate(VB.LAYOUT_JS, ids)
                if lay["overflow"]:
                    layout_problems.append(
                        f"{batch['file']} @{w}px: page scrolls sideways "
                        f"({lay['scrollWidth']}px > {w}px)")
                for z in lay["zeroSized"]:
                    layout_problems.append(
                        f"{batch['file']} @{w}px: {z['id']} ({z['type']}) renders "
                        f"at {z['w']}x{z['h']}")

            done = bi + 1
            if done % 10 == 0 or done == len(batches):
                v = sum(1 for x in rows if x["status"] == "verified")
                f = sum(1 for x in rows if x["status"] == "OVERRIDDEN")
                print(f"  {done:>3}/{len(batches)} batches   "
                      f"{v:,} verified   {f:,} failing")
        b.close()

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w_ = csv.DictWriter(f, fieldnames=["batch", "element", "control", "property",
                                           "declared", "computed", "selector", "status"])
        w_.writeheader()
        w_.writerows(rows)

    c = Counter(r["status"] for r in rows)
    total = sum(c.values())
    print()
    print(f"COMPUTED STYLE, IN A REAL BROWSER  ({total:,} (control, property) probes)")
    for k in ("verified", "OVERRIDDEN", "no-target-node", "not-declared",
              "not-comparable", "hover-only"):
        if c[k]:
            print(f"    {k:<18}{c[k]:>7,}  ({100 * c[k] / total:5.1f}%)")
    print()
    print(f"LAYOUT  ({len(a.widths)} widths x {len(batches)} pages)")
    print(f"    problems          {len(layout_problems):>7,}")
    for p in layout_problems[:15]:
        print(f"      {p}")
    if console_errors:
        print()
        print(f"JS ERRORS on the rendered pages ({sum(console_errors.values())}):")
        for e, n in console_errors.most_common(5):
            print(f"    {n:>4}x  {e}")

    # OVERRIDDEN is the only real failure: Elementor declared it, the browser found
    # the node, and computed something else. The rule is in the file and LOST.
    bad = [r for r in rows if r["status"] == "OVERRIDDEN"]
    if bad:
        print()
        print(f"{len(bad)} declarations the browser did NOT honour (the rule is in the")
        print(f"stylesheet and something outranked it):")
        for r in bad[:25]:
            print(f"    {r['control']} `{r['property']}` on `{r['selector'][:52]}`")
            print(f"        Elementor declared {r['declared']!r}, "
                  f"the browser computed {r['computed']!r}")
    print()
    print(f"  written {out}")
    return 1 if bad or layout_problems else 0


if __name__ == "__main__":
    sys.exit(main())
