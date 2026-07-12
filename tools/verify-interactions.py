#!/usr/bin/env python3
"""
verify-interactions.py - do the interactive widgets actually INTERACT?

    python tools/verify-interactions.py --url https://site/page/ \
        --apply "bash apply.sh {name}" --sweep <single-widget-sweep-dir>

Rendering right is half of an interactive widget. The other half is behaviour:
a tab that does not switch, an accordion that does not expand, a carousel whose
arrow does nothing - all of them pass every render check and are broken.

Five behaviours, each driven with real pointer events on the public page:

    nested-tabs        click tab 2  -> tab 2's content becomes visible, tab 1's hides
    nested-accordion   click item 2 -> item 2 opens (native <details>)
    accordion          click item 2 -> its body becomes visible
    toggle             click item 1 -> its body toggles open
    image-carousel     click next   -> the active slide changes

The single-widget sweep pages are reused: each widget is alone on its page, so
whatever happens is its doing.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN_NONCE = time.strftime("%H%M%S")


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, HERE / fname)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


SC = _load("sweep_controls", "sweep-controls.py")

# Each scenario: the widget, and a JS/action script returning {before, after, pass}.
SCENARIOS = {
    "nested-tabs": dict(
        act=lambda pg, root: (
            pg.locator(f"{root} .e-n-tab-title").nth(1).click(timeout=5000)),
        judge=r"""
(root) => {
  const titles = document.querySelectorAll(root + " .e-n-tab-title");
  const contents = document.querySelectorAll(root + " .e-n-tabs-content > .e-con");
  const sel1 = titles[1] && titles[1].getAttribute("aria-selected") === "true";
  const c0 = contents[0] ? getComputedStyle(contents[0]).display : "?";
  const c1 = contents[1] ? getComputedStyle(contents[1]).display : "?";
  return {detail: `tab2 aria-selected=${sel1} content1=${c0} content2=${c1}`,
          pass: sel1 && c1 !== "none" && c0 === "none"};
}"""),
    "nested-accordion": dict(
        act=lambda pg, root: (
            pg.locator(f"{root} details > summary").nth(1).click(timeout=5000)),
        judge=r"""
(root) => {
  const items = document.querySelectorAll(root + " details");
  const open1 = items[1] && items[1].hasAttribute("open");
  return {detail: `item2 open=${open1}`, pass: !!open1};
}"""),
    "accordion": dict(
        act=lambda pg, root: (
            pg.locator(f"{root} .elementor-tab-title").nth(1).click(timeout=5000)),
        judge=r"""
(root) => {
  const bodies = document.querySelectorAll(root + " .elementor-tab-content");
  const b1 = bodies[1] ? getComputedStyle(bodies[1]).display : "?";
  return {detail: `item2 body display=${b1}`, pass: b1 !== "none"};
}"""),
    "toggle": dict(
        act=lambda pg, root: (
            pg.locator(f"{root} .elementor-tab-title").first.click(timeout=5000)),
        judge=r"""
(root) => {
  const bodies = document.querySelectorAll(root + " .elementor-tab-content");
  const b0 = bodies[0] ? getComputedStyle(bodies[0]).display : "?";
  return {detail: `item1 body display=${b0}`, pass: b0 !== "none"};
}"""),
    "image-carousel": dict(
        act=lambda pg, root: (
            pg.locator(f"{root} .elementor-swiper-button-next").first.click(timeout=5000)),
        judge=r"""
(root) => {
  const active = document.querySelector(root + " .swiper-slide-active");
  const idx = active ? active.getAttribute("data-swiper-slide-index") : null;
  return {detail: `active slide index=${idx}`, pass: idx !== null && idx !== "0"};
}"""),
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True)
    ap.add_argument("--apply", required=True,
                    help="applies one single-widget batch; {name} = batch file name")
    ap.add_argument("--sweep", required=True, type=Path,
                    help="the one-widget-per-page sweep dir (its plan maps widget->batch)")
    a = ap.parse_args()

    from playwright.sync_api import sync_playwright

    plan = json.loads((a.sweep / "plan.json").read_text(encoding="utf-8"))
    batch_of = {}
    for b in plan["batches"]:
        for w in b["widgets"]:
            batch_of[w] = b["file"]      # later entries win: fixtures override
    env = {**os.environ, "MSYS_NO_PATHCONV": "1"}

    results = []
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        pg = br.new_page(viewport={"width": 1440, "height": 1000})

        for i, (widget, sc) in enumerate(SCENARIOS.items()):
            if widget not in batch_of:
                results.append((widget, "SKIP", "not in this sweep plan"))
                continue
            cmd = a.apply.replace("{name}", batch_of[widget])
            if subprocess.run(cmd, shell=True, capture_output=True, env=env).returncode:
                results.append((widget, "APPLY-FAILED", ""))
                continue
            pg.goto(f"{a.url}?ehi={RUN_NONCE}-{i}", wait_until="load", timeout=45000)
            pg.wait_for_timeout(900)          # widget JS handlers attach on init
            root = f".elementor-element-{plan['widgets'][widget]['element_id']}"
            before = pg.evaluate(sc["judge"], root)
            try:
                sc["act"](pg, root)
                pg.wait_for_timeout(600)
                after = pg.evaluate(sc["judge"], root)
            except Exception as e:
                results.append((widget, "ACTION-FAILED", str(e)[:90]))
                continue
            verdict = "PASS" if after["pass"] else "FAIL"
            results.append((widget, verdict,
                            f"before[{before['detail']}] after[{after['detail']}]"))
            print(f"  {widget:<18} {verdict:<6} {results[-1][2]}")
        br.close()

    fails = [r for r in results if r[1] not in ("PASS", "SKIP")]
    print()
    print(f"INTERACTIONS: {sum(1 for r in results if r[1] == 'PASS')}/"
          f"{len([r for r in results if r[1] != 'SKIP'])} behaviours pass")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
