#!/usr/bin/env python3
"""
sweep-widgets.py - a FUNCTIONAL render test for every widget, one by one.

    python tools/sweep-widgets.py plan  --post-id <id> --out wsweep --have container nested-elements
    python tools/sweep-widgets.py check wsweep --url https://site/page/ \
        --apply "bash apply.sh {name}" --out data/widget-verification.csv

The control sweeps answer "does each SETTING work". This answers the question
before it: **does each widget, given content, actually render that content?**

The method is marker echo. Every content-ish control gets a value UNIQUE to that
(widget, control) - `EHW-video-caption`, a probe URL, a seeded repeater item built
from the repeater's own extracted fields - and the widget passes when its wrapper
exists in the delivered DOM, renders at non-zero size, and at least one of its
markers made it into its output. A widget that eats its settings and renders its
placeholder instead (exactly what `theme-post-title` did inside loops) fails the
marker check while every style-level sweep stays green.

Everything is asserted through a real browser on the PUBLIC url, batch by batch,
with per-batch JS-error attribution.
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
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent

# A per-RUN cache-buster, not just a per-batch one. `?ehw=0` is a different page on
# every run, but to an edge cache with a 3600s TTL it is the SAME url - so a re-run
# inside the TTL gets served the PREVIOUS run's page for every batch, and scores 13
# working widgets as NOT-IN-DOM. The number was the tell: everything absent at once.
import time as _time
RUN_NONCE = _time.strftime("%H%M%S")


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, HERE / fname)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


SC = _load("sweep_controls", "sweep-controls.py")

MEDIA_URL = "https://moksaweb.com/wp-content/uploads/2026/06/moksa-logo.png"
YT_URL = "https://www.youtube.com/watch?v=XHOmBV4js_E"
TEXTISH = {"text", "textarea", "wysiwyg"}

# Widgets whose emptiness IS the correct render outside a post/comment context.
# Saying "EMPTY" about them is a statement about the TEST PAGE, not the widget.
CONTEXTUAL = {"read-more", "post-comments", "wp-widget-text"}
# Product widgets render empty outside a product page - correctly.
CONTEXT_PREFIX = ("woocommerce-product-", "wc-single-")
# Renders nothing visible by design until user interaction opens it.
HIDDEN_BY_DESIGN = {"off-canvas", "popup"}
# Renders empty space ON PURPOSE; size is the whole assertion.
SPACE_ONLY = {"spacer", "divider", "menu-anchor"}

# Types whose value we can seed inside a repeater item, from its extracted fields.
def seed_field(widget: str, ctrl: str, f: dict, i: int):
    t = f.get("type")
    marker = f"EHW-{widget}-{ctrl}-{f['name']}"
    if t in TEXTISH:
        # A text control whose NAME says it holds a URL gets a real one. Seeding a
        # marker into video-playlist's youtube_url produced "Invalid video id" in
        # the console and pinned a JS error on a perfectly working widget.
        if "url" in f["name"] or "link" in f["name"]:
            return YT_URL, None
        return marker, marker
    if t == "select" and f.get("options"):
        return str(f["options"][0] if str(f["options"][0]) != "" else
                   (f["options"][1] if len(f["options"]) > 1 else "")), None
    if t == "media":
        return {"url": MEDIA_URL, "id": ""}, None
    if t == "icons":
        return {"value": "fas fa-star", "library": "fa-solid"}, None
    if t == "url":
        return {"url": "https://example.com/", "is_external": "", "nofollow": ""}, None
    if t == "switcher":
        return f.get("default", ""), None
    if f.get("default") not in (None, ""):
        return f["default"], None
    return None, None


def seed_widget(widget: str, controls: dict) -> tuple[dict, list[str]]:
    """
    Minimal content for this widget, plus the markers we expect to see rendered.

    Statics defaults render on their own (get_settings falls back to the control
    default), so only the holes are filled: text controls WITHOUT a default,
    media, icons, and one item per repeater - built from the repeater's own
    extracted fields, which is what capturing them was for.
    """
    settings: dict = {}
    markers: list[str] = []

    def condition_met_by_defaults(cond: dict) -> bool:
        """
        Seed a conditioned control when its condition is ALREADY satisfied by the
        defaults. The Pro gallery's image source is `gallery`, conditioned on
        `gallery_type: single` - which is the default. Skipping every conditioned
        control left the widget with no images and scored it NOT-IN-DOM, a
        statement about the seeder, not the widget.
        """
        for dep, want in cond.items():
            if dep.endswith("!") or "[" in dep:
                return False               # negations/sub-keys: leave to the CSS sweep
            have = controls.get(dep, {}).get("default", "")
            wants = want if isinstance(want, list) else [want]
            if not any(str(have) == str(x) for x in wants):
                return False
        return True

    for c in controls.values():
        if c.get("tab") not in (None, "content"):
            continue
        if c.get("conditions"):
            continue
        if c.get("condition") and not condition_met_by_defaults(c["condition"]):
            continue                       # do not fight dependency chains here
        name, t = c["name"], c.get("type")
        if t in TEXTISH:
            m = f"EHW-{widget}-{name}"
            settings[name] = m if t != "wysiwyg" else f"<p>{m}</p>"
            markers.append(m)
        elif t == "media":
            settings[name] = {"url": MEDIA_URL, "id": ""}
        elif t == "icons":
            settings[name] = {"value": "fas fa-star", "library": "fa-solid"}
        elif t == "gallery":
            # image-carousel / image-gallery / gallery render NOTHING without
            # images - invisible in the first run, not because they are broken but
            # because the seeder did not speak their value type.
            settings[name] = [{"id": "", "url": MEDIA_URL},
                              {"id": "", "url": MEDIA_URL}]
        elif t == "code":
            m = f"EHW-{widget}-{name}"
            settings[name] = f"<span>{m}</span>"
            markers.append(m)
        elif t and t.endswith("repeater") or t == "repeater":
            fields = c.get("fields")
            if not fields:
                continue
            item = {"_id": f"eh{abs(hash(widget+name)) % 0xFFFFF:05x}"}
            for f in fields:
                v, m = seed_field(widget, name, f, 0)
                if v is not None:
                    item[f["name"]] = v
                if m:
                    markers.append(m)
            settings[name] = [item, dict(item, _id=item["_id"][:-1] + "b")]
    return settings, markers


def cmd_plan(a) -> int:
    schema = SC.load_schema()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    have = {h.lower() for h in (a.have or [])}

    def available(name, w):
        if w.get("control_system") == "v4-atomic":
            return False                    # a different data model; not built here
        r = w.get("requires")
        if not r:
            return True
        if r.get("wp_widget"):
            return a.include_wp_widgets
        need = (r.get("plugin") or r.get("experiment") or "").lower()
        return bool(need) and need in have

    plan = {"batches": [], "widgets": {}}
    nodes = []
    for name, w in schema["widgets"].items():
        if name in ("common", "common-base", "common-optimized", "global",
                    "e-component", "inner-section"):
            continue                        # registries / structural, not placeable
        if not available(name, w):
            continue
        controls = SC.controls_of(schema, name)
        settings, markers = seed_widget(name, controls)
        eid = SC.elem_id(name, 0)
        nodes.append({"id": eid, "elType": "widget", "widgetType": name,
                      "settings": settings, "elements": []})
        plan["widgets"][name] = {
            "element_id": eid, "markers": markers,
            "known_bare": w.get("renders_bare") is False,
        }

    size = a.batch_size
    for bi in range(0, len(nodes), size):
        batch = nodes[bi:bi + size]
        tree = [{"id": f"w{bi:06x}"[:7], "elType": "container", "settings": {},
                 "elements": batch}]
        f = out / f"batch-{bi // size:03d}.json"
        f.write_text(json.dumps(tree, ensure_ascii=False, indent=1),
                     encoding="utf-8", newline="\n")
        plan["batches"].append({"file": f.name,
                                "widgets": [n["widgetType"] for n in batch]})

    (out / "plan.json").write_text(json.dumps(plan, ensure_ascii=False),
                                   encoding="utf-8", newline="\n")
    print(f"{len(nodes)} widgets across {len(plan['batches'])} pages -> {out}/")
    return 0


JS = r"""
(widgets) => {
  const out = {};
  for (const [name, info] of Object.entries(widgets)) {
    const el = document.querySelector(`.elementor-element-${info.element_id}`);
    if (!el) { out[name] = {present: false}; continue; }
    const r = el.getBoundingClientRect();
    const html = el.innerHTML;
    const text = el.innerText || "";
    out[name] = {
      present: true,
      w: Math.round(r.width), h: Math.round(r.height),
      contentful: html.replace(/\s/g, "").length > 80,
      markers_hit: (info.markers || []).filter(m => html.includes(m)),
      media_used: html.includes("moksa-logo.png"),
    };
  }
  return out;
}
"""


def cmd_check(a) -> int:
    sweep = Path(a.sweep)
    plan = json.loads((sweep / "plan.json").read_text(encoding="utf-8"))

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("pip install playwright && playwright install chromium", file=sys.stderr)
        return 2

    rows = []
    js_errors: Counter = Counter()
    env = {**os.environ, "MSYS_NO_PATHCONV": "1"}

    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 1440, "height": 1000})
        pg.on("pageerror", lambda e: js_errors.update([str(e)[:100]]))

        batches = plan["batches"][: a.limit] if a.limit else plan["batches"]
        if a.only:
            batches = [b for b in batches if any(w in a.only for w in b["widgets"])]
        for bi, batch in enumerate(batches):
            cmd = a.apply.replace("{name}", batch["file"])
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, env=env)
            if r.returncode != 0:
                print(f"  apply FAILED {batch['file']}: {r.stderr[:100]}")
                continue
            errs_before = sum(js_errors.values())
            try:
                pg.goto(f"{a.url}?ehw={RUN_NONCE}-{bi}", wait_until="load", timeout=45000)
            except Exception as e:
                print(f"  goto FAILED {batch['file']}: {str(e)[:80]}")
                continue
            pg.wait_for_timeout(700)

            info = {w: plan["widgets"][w] for w in batch["widgets"]}
            res = pg.evaluate(JS, info)
            batch_errs = sum(js_errors.values()) - errs_before

            # One widget per page (the default): check IT at every viewport, and
            # screenshot IT, before moving on. Careful beats fast here - the whole
            # point of stepping widget by widget is that nothing shares the blame.
            responsive_bad = []
            for width in (1440, 768, 375):
                pg.set_viewport_size({"width": width, "height": 1000})
                pg.wait_for_timeout(200)
                lay = pg.evaluate(
                    "(ids) => ids.map(id => {"
                    "  const e = document.querySelector(`.elementor-element-${id}`);"
                    "  if (!e) return null;"
                    "  const r = e.getBoundingClientRect();"
                    "  return {id, w: Math.round(r.width), h: Math.round(r.height),"
                    "          overflow: document.documentElement.scrollWidth > window.innerWidth + 1};"
                    "})",
                    [plan["widgets"][w]["element_id"] for w in batch["widgets"]])
                for x in lay:
                    if x and x["overflow"]:
                        responsive_bad.append(f"{width}px:page-overflows")
                    if x and x["w"] == 0 and x["h"] == 0:
                        responsive_bad.append(f"{width}px:zero-size")
            pg.set_viewport_size({"width": 1440, "height": 1000})

            for name in batch["widgets"]:
                w, r_ = plan["widgets"][name], res.get(name) or {}
                if not r_.get("present"):
                    status = ("expected-empty" if w["known_bare"]
                              else "needs-post-context" if name in CONTEXTUAL
                              else "NOT-IN-DOM")
                elif name in SPACE_ONLY and (r_.get("w", 0) > 0 or r_.get("h", 0) > 0):
                    status = "rendered"        # empty space at real size IS its job
                elif name in HIDDEN_BY_DESIGN and r_.get("markers_hit"):
                    status = "rendered-hidden-by-design"
                elif w["markers"] and r_["markers_hit"]:
                    status = "rendered+markers"
                elif w["markers"] and not r_["markers_hit"]:
                    # "contentful but none of MY markers" splits two ways: a widget
                    # that queries REAL site content (posts, portfolio, author-box -
                    # the markers sat in its nothing-found message, which correctly
                    # did not render) vs one that swallowed its settings.
                    status = ("rendered-site-content" if r_["contentful"]
                              and (r_.get("h", 0) or 0) > 60
                              else "rendered-DEFAULTS-ONLY" if r_["contentful"]
                              else "needs-post-context" if name in CONTEXTUAL
                              or name.startswith(CONTEXT_PREFIX)
                              else "EMPTY")
                elif r_["contentful"] or r_.get("media_used"):
                    status = "rendered"
                else:
                    status = ("expected-empty" if w["known_bare"]
                              else "needs-post-context" if name in CONTEXTUAL
                              else "EMPTY")
                if (status.startswith("rendered") and name not in HIDDEN_BY_DESIGN
                        and r_.get("w", 0) == 0 and r_.get("h", 0) == 0):
                    status = ("needs-post-context"
                              if name in CONTEXTUAL or name.startswith(CONTEXT_PREFIX)
                              else "ZERO-SIZE")

                shot = ""
                if r_.get("present") and a.shots:
                    shots_dir = sweep / "shots"
                    shots_dir.mkdir(exist_ok=True)
                    shot = f"shots/{name}.png"
                    try:
                        pg.locator(f".elementor-element-{w['element_id']}").first                           .screenshot(path=str(sweep / shot), timeout=6000)
                    except Exception:
                        shot = ""

                rows.append({
                    "widget": name, "status": status,
                    "size": f"{r_.get('w', 0)}x{r_.get('h', 0)}" if r_.get("present") else "",
                    "markers_expected": len(w["markers"]),
                    "markers_rendered": len(r_.get("markers_hit") or []),
                    "responsive": ";".join(sorted(set(responsive_bad))) or "ok",
                    "js_errors": batch_errs,
                    "screenshot": shot,
                })
                print(f"  [{bi + 1:>2}/{len(plan['batches'])}] {name:<30} {status:<22} "
                      f"{rows[-1]['size']:>9}  markers {rows[-1]['markers_rendered']}/"
                      f"{rows[-1]['markers_expected']}  rwd:{rows[-1]['responsive']}"
                      + (f"  JS-ERRORS:{batch_errs}" if batch_errs else ""))
        b.close()

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    c = Counter(r["status"] for r in rows)
    print()
    print(f"WIDGET FUNCTIONAL RENDER  ({len(rows)} widgets, on the public URL)")
    for k, n in c.most_common():
        print(f"    {k:<24}{n:>4}")
    bad = [r for r in rows if r["status"] in ("NOT-IN-DOM", "EMPTY", "ZERO-SIZE")]
    if bad:
        print()
        print("needs a look:")
        for r in bad:
            print(f"    {r['widget']:<28} {r['status']}")
    if js_errors:
        print()
        print("JS errors seen:")
        for e, n in js_errors.most_common(6):
            print(f"    {n:>3}x {e}")
    print()
    print(f"  written {out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--out", default="wsweep")
    p.add_argument("--post-id", type=int, default=0)
    p.add_argument("--batch-size", type=int, default=1,
                   help="widgets per page. Default 1 - ONE widget per page, so a JS "
                        "error, an overflow or a zero-size render is attributable to "
                        "exactly one widget instead of to whichever of six shared the "
                        "page with it.")
    p.add_argument("--have", nargs="+", default=[])
    p.add_argument("--include-wp-widgets", action="store_true",
                   help="also test the WP legacy-widget bridges. They are OTHER "
                        "plugins' widgets, so only meaningful on the site whose "
                        "plugin set the schema was extracted from.")
    p.set_defaults(fn=cmd_plan)
    c = sub.add_parser("check")
    c.add_argument("sweep")
    c.add_argument("--url", required=True)
    c.add_argument("--apply", required=True)
    c.add_argument("--out", default="data/widget-verification.csv")
    c.add_argument("--shots", action="store_true", default=True,
                   help="save a per-widget element screenshot into <sweep>/shots/")
    c.add_argument("--limit", type=int, default=0)
    c.add_argument("--only", nargs="+", help="re-test just these widgets")
    c.set_defaults(fn=cmd_check)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
