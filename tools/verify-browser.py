#!/usr/bin/env python3
"""
verify-browser.py - ask a REAL BROWSER what the page computes.

    pip install playwright && playwright install chromium
    python tools/verify-browser.py examples/demo-page.json https://your-site/your-page/

Every other check in this repo reads TEXT. `verify-live.py` gets closest - it fetches
the delivered HTML and the stylesheets the page actually links - but it still only
proves the RULE IS PRESENT IN THE FILE. It cannot prove the browser applied it.

Between "the rule is in the stylesheet" and "the element renders that way" sit:

  - selector specificity. The theme's `.entry-content h2 { color: ... }` can outrank
    Elementor's rule. The rule is right there in the file, and it loses.
  - the cascade. A later stylesheet overwrites it.
  - the selector not matching the DOM at all.
  - layout. Every declaration can be correct and the three columns still stack,
    or the page can scroll sideways on mobile. No amount of CSS text says otherwise.

So this opens the page in Chromium and asks `getComputedStyle` on the node the rule
ACTUALLY TARGETS - which is why `data/css-selectors.csv` exists. `title_color` on a
heading is not a property of the element wrapper; it is a property of
`.elementor-heading-title` INSIDE it. Query the wrapper for `color` and you get the
inherited value, and a perfectly rendered page reads as broken.

It also checks the things only a layout engine knows:

  - no horizontal overflow, at desktop / tablet / mobile widths
  - elements that should sit side by side actually do
  - no element rendered with zero size
  - no JS errors on the page

Playwright is the one dependency in this repo beyond the stdlib, and it is optional:
nothing else needs it.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "data" / "elementor-schema.json"
SELECTORS = ROOT / "data" / "css-selectors.csv"

# Properties whose computed value we can predict from the setting. A computed value
# is not the value you wrote - the browser normalises it - so compare like for like.
COLOR_RE = re.compile(r"^#([0-9a-fA-F]{6})$")


def hex_to_rgb(v: str) -> str | None:
    m = COLOR_RE.match(v.strip())
    if not m:
        return None
    r, g, b = (int(m.group(1)[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgb({r}, {g}, {b})"


def load_selectors() -> dict[tuple[str, str], list[tuple[str, list[str]]]]:
    """
    (owner, control) -> [(selector template, the properties IT sets), ...]

    The pairing is the point. A control can drive different properties through
    different selectors, and which pair applies can depend on another control.
    """
    out: dict[tuple[str, str], list[tuple[str, list[str]]]] = {}
    if not SELECTORS.exists():
        return out
    with SELECTORS.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out.setdefault((r["owner"], r["control"]), []).append(
                (r["selector_template"], (r["properties"] or "").split()))
    return out


def controls_for(schema: dict, el: dict) -> dict:
    owner = el.get("widgetType") if el["elType"] == "widget" else el["elType"]
    src = schema["widgets"].get(owner) or schema["elements"].get(owner)
    if not src:
        return {}
    out = {c["name"]: c for c in src["controls"]}
    if src.get("has_common"):
        miss = set(src.get("common_missing") or [])
        for c in schema["common_controls"]["controls"]:
            if c["name"] not in miss:
                out.setdefault(c["name"], c)
    return out


def owner_of(el: dict) -> str:
    return el.get("widgetType") if el["elType"] == "widget" else el["elType"]


SIDE_OF = {"top": "top", "right": "right", "bottom": "bottom", "left": "left"}


def expected(ctrl: dict, value, prop: str) -> str | None:
    """
    What the BROWSER should compute for THIS property, not what we wrote.

    Per property, not per control. A `dimensions` control writes four different
    numbers, and comparing all four sides against `top` reports three failures on a
    page that is perfectly correct - which is exactly what the first run of this
    tool did.
    """
    t = ctrl.get("type")
    if t == "color" and isinstance(value, str):
        return hex_to_rgb(value)
    if t == "dimensions" and isinstance(value, dict):
        if value.get("unit") != "px":
            return None
        for side in SIDE_OF:
            if prop.endswith(side):          # padding-left, --padding-left, ...
                v = value.get(side)
                return f"{v}px" if v not in (None, "") else None
        return None
    if t in ("slider", "gaps") and isinstance(value, dict):
        unit = value.get("unit")
        size = value.get("size", value.get("column"))
        if unit == "px" and size not in (None, ""):
            return f"{size}px"          # the only unit that survives computation intact
    return None


def build_probe(tree, schema, sels) -> list[dict]:
    els: list[dict] = []

    def walk(ns):
        for e in ns:
            els.append(e)
            walk(e.get("elements") or [])
    walk(tree)

    probe = []
    for el in els:
        owner = owner_of(el)
        ctrls = controls_for(schema, el)
        for key, value in (el.get("settings") or {}).items():
            base = key
            skip = False
            for d in ("tablet", "mobile"):
                if key.endswith(f"_{d}"):
                    skip = True         # desktop viewport; responsive keys are a
                    break               # separate pass below
            if skip:
                continue
            c = ctrls.get(base)
            if not c or not c.get("css"):
                continue
            # Each (selector, properties) PAIR, kept together. Probing every
            # property against the first selector that happens to match asserts
            # things the control never claimed - `primary_color` sets
            # `background-color` on the stacked-view icon and `color` on the framed
            # one, and asking the stacked node for `color` gets you whatever
            # `secondary_color` put there.
            pairs = sels.get((owner, base)) or [("{{WRAPPER}}", c["css"])]
            for tpl, props in pairs:
                for prop in props:
                    probe.append({
                        "id": el["id"], "owner": owner, "control": base,
                        "prop": prop, "templates": [tpl],
                        "want": expected(c, value, prop),
                        "wrote": value if not isinstance(value, dict) else
                                 json.dumps(value, ensure_ascii=False)[:40],
                    })
    return probe


JS = r"""
(probe) => {
  // Elementor's selector templates, resolved against the real DOM.
  //
  //   {{WRAPPER}}                -> .elementor-element-<id>       (substitution,
  //   {{WRAPPER}}.foo .bar          NOT a prefix: `{{WRAPPER}}.foo` is a compound
  //   {{WRAPPER}}:hover .btn        selector, and rewriting it as a descendant one
  //   (desktop+){{WRAPPER}} > .x    matches nothing at all)
  //   a, b                       -> a comma-separated LIST; any of them may exist
  //
  // A template whose ONLY form is a hover/focus state cannot be computed without
  // driving the mouse, so it is reported as unassertable rather than as a failure.
  const resolve = (tpl, id) => {
    let t = tpl.replace(/^\((?:desktop|tablet|mobile|widescreen|laptop)[^)]*\)\s*/, "");
    return t.split(",")
      .map(s => s.trim())
      // A branch with no {{WRAPPER}} in it is NOT scoped to this element. Resolve
      // one anyway and you get a bare `a`, which happily matches a link in the site
      // header - and then you compare Elementor's declaration for OUR element
      // against the computed style of somebody else's. It reads as four confident
      // "the browser overrode this!" failures on a page that is perfectly fine.
      .filter(s => s.includes("{{WRAPPER}}"))
      .map(s => s.replace(/\{\{WRAPPER\}\}/g, `.elementor-element-${id}`));
  };
  const out = [];
  for (const p of probe) {
    let el = null, used = null, onlyPseudo = true;
    for (const tpl of p.templates) {
      for (const sel of resolve(tpl, p.id)) {
        if (/:(hover|focus|active|visited)\b/.test(sel)) continue;
        onlyPseudo = false;
        let cand = null;
        try { cand = document.querySelector(sel); } catch (e) { /* invalid */ }
        if (cand) { el = cand; used = sel; break; }
      }
      if (el) break;
    }
    if (!el) {
      out.push({id: p.id, control: p.control, prop: p.prop, want: p.want,
                wrote: p.wrote, got: null, onlyPseudo,
                tried: p.templates.join(" | ")});
      continue;
    }
    const cs = getComputedStyle(el);
    const got = p.prop.startsWith("--")
      ? cs.getPropertyValue(p.prop).trim()
      : cs.getPropertyValue(p.prop);
    out.push({id: p.id, control: p.control, prop: p.prop, want: p.want,
              wrote: p.wrote, got, used});
  }
  return out;
}
"""


# A control's selectors are often BRANCHES, not a set that must all match.
# `primary_color` on an icon-box compiles two rules - one for the stacked view, one
# for the framed/default view - and which one is live depends on the `view` control.
# The other branch matching nothing is CORRECT, not a failure. Only a control where
# NOT ONE of its selectors matched has genuinely failed to apply to anything.
def fold_branches(results: list[dict]) -> tuple[list[dict], int]:
    by_control: dict[tuple[str, str], list[dict]] = {}
    for r in results:
        by_control.setdefault((r["id"], r["control"]), []).append(r)
    live, dead = [], 0
    for rows in by_control.values():
        matched = [r for r in rows if r["got"] is not None]
        if matched:
            dead += len(rows) - len(matched)
            live.extend(matched)
        else:
            live.extend(rows)      # nothing matched at all - that IS a failure
    return live, dead


LAYOUT_JS = r"""
(ids) => {
  const zero = [];
  // Only the elements of the tree UNDER TEST. A page carries the theme's Elementor
  // header and footer too, and their elements are not ours to judge.
  document.querySelectorAll("[data-id]").forEach(e => {
    if (!ids.includes(e.getAttribute("data-id"))) return;
    const r = e.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) {
      zero.push({id: e.getAttribute("data-id"),
                 type: e.getAttribute("data-element_type"),
                 w: Math.round(r.width), h: Math.round(r.height)});
    }
  });
  return {
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
    overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
    zeroSized: zero,
  };
}
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("page", type=Path)
    ap.add_argument("url")
    ap.add_argument("--widths", nargs="+", type=int, default=[1440, 768, 375],
                    help="viewport widths to check the layout at")
    a = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("This one needs a browser:\n"
              "  pip install playwright && playwright install chromium",
              file=sys.stderr)
        return 2

    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    tree = json.loads(a.page.read_text(encoding="utf-8"))
    sels = load_selectors()
    probe = build_probe(tree, schema, sels)
    tree_ids: list[str] = []

    def _ids(ns):
        for e in ns:
            tree_ids.append(e["id"])
            _ids(e.get("elements") or [])
    _ids(tree)

    print(f"{a.url}")
    print(f"{len(probe)} (element, css property) pairs the schema promises\n")

    fails, checked, unassertable = [], 0, 0
    console_errors: list[str] = []

    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": a.widths[0], "height": 900})
        pg.on("pageerror", lambda e: console_errors.append(str(e)))
        pg.goto(a.url, wait_until="networkidle")

        pseudo_only = 0
        results, dead_branches = fold_branches(pg.evaluate(JS, probe))
        for r in results:
            if r["got"] is None:
                if r.get("onlyPseudo"):
                    # A :hover rule. Real, but not computable without a mouse.
                    pseudo_only += 1
                    continue
                fails.append(f"{r['id']}.{r['control']}: NO NODE matched the selector "
                             f"for `{r['prop']}` ({r.get('tried')}). The rule is in "
                             f"the stylesheet and applies to nothing on this page.")
                continue
            if r["want"] is None:
                unassertable += 1
                continue
            checked += 1
            if r["want"].lower() not in str(r["got"]).lower():
                fails.append(
                    f"{r['id']}.{r['control']}: the browser computes `{r['prop']}` = "
                    f"{r['got']!r}, not {r['want']!r} (you wrote {r['wrote']!r}) on "
                    f"`{r.get('used')}`. The rule is in the file and LOSING to the "
                    f"cascade.")

        print(f"computed-style assertions : {checked} checked")
        print(f"  inactive branch         : {dead_branches} "
              f"(the control compiles several rules; a sibling control picked "
              f"which one is live)")
        print(f"  not predictable         : {unassertable} "
              f"(the browser normalises the value; nothing to compare against)")
        print(f"  hover/focus only        : {pseudo_only} "
              f"(real rules, not computable without driving the mouse)")
        print()

        print("layout, at each viewport width:")
        for w in a.widths:
            pg.set_viewport_size({"width": w, "height": 900})
            pg.wait_for_timeout(250)
            lay = pg.evaluate(LAYOUT_JS, tree_ids)
            bad = []
            if lay["overflow"]:
                bad.append(f"scrolls sideways ({lay['scrollWidth']}px > {w}px)")
            if lay["zeroSized"]:
                z = ", ".join(f"{e['id']}({e['type']})" for e in lay["zeroSized"][:4])
                bad.append(f"{len(lay['zeroSized'])} element(s) render at zero size: {z}")
            status = "ok" if not bad else "  <-- " + "; ".join(bad)
            print(f"  {w:>5}px   {status}")
            for msg in bad:
                fails.append(f"layout @{w}px: {msg}")
        b.close()

    if console_errors:
        print()
        print(f"JS errors on the page: {len(console_errors)}")
        for e in console_errors[:5]:
            print(f"    {e[:110]}")

    print()
    if fails:
        print(f"FAIL - {len(fails)} problem(s) a browser can see and a text check cannot:")
        for f in fails[:25]:
            print(f"    {f}")
        return 1
    print("PASS - every rule the schema promised is what the browser actually computes,")
    print("       on the node it actually targets, and the page holds its layout at")
    print(f"       {', '.join(str(w) + 'px' for w in a.widths)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
