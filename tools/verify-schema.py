#!/usr/bin/env python3
"""
verify-schema.py — prove (or disprove) that the shipped schema matches YOUR site.

The schema in data/ was extracted from one Elementor version. Yours may differ.
Rather than asking you to trust it, this tells you exactly where it is wrong:

    # on your server
    wp eval-file tools/extract-elementor-schema.php core+pro > mine.json
    wp --skip-plugins=elementor-pro eval-file tools/extract-elementor-schema.php core+pro > mine-free.json

    # locally
    python tools/verify-schema.py mine.json --free-dump mine-free.json

Exit code is 0 when the shipped schema is a safe description of your install and
1 when it is not, so it can gate a deploy.

WHAT COUNTS AS A FAILURE
  - a widget the schema claims exists, that your site does not have
  - a control the schema claims exists on a widget, that is gone
  - a control whose TYPE changed (the JSON value shape you would write is now wrong)
  - a control the schema calls free that is actually Pro on your install
    (this one is a failure even though nothing "breaks" locally, because it is
     the one that ships broken pages to Free sites)

WHAT COUNTS AS DRIFT, NOT FAILURE
  - your Elementor has controls the schema does not know about yet (newer version)
  - extra widgets from addons
  - breakpoint config differing from the reference site
  These are reported, and they mean "re-extract to get full coverage", not
  "the schema will mislead you".
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def flatten(schema: dict) -> dict[tuple[str, str], dict]:
    """(owner, control) -> control record, with the common set expanded back out."""
    flat = {}
    common = schema.get("common_controls", {}).get("controls", [])
    for owner, w in schema.get("elements", {}).items():
        for c in w["controls"]:
            flat[(owner, c["name"])] = c
    for owner, w in schema.get("widgets", {}).items():
        for c in w["controls"]:
            flat[(owner, c["name"])] = c
        if w.get("has_common"):
            missing = set(w.get("common_missing", []))
            for c in common:
                if c["name"] not in missing:
                    flat.setdefault((owner, c["name"]), c)
    return flat


def flatten_raw(raw: dict) -> dict[tuple[str, str], dict]:
    """Same shape, from an unfactored extractor dump."""
    flat = {}
    for group in ("elements", "widgets"):
        for owner, w in raw.get(group, {}).items():
            for c in w["controls"]:
                flat[(owner, c["name"])] = c
    return flat


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dump", type=Path, help="fresh dump from YOUR site")
    ap.add_argument("--free-dump", type=Path,
                    help="second dump with `wp --skip-plugins=elementor-pro` (enables the Free/Pro check)")
    ap.add_argument("--schema", type=Path, default=ROOT / "data" / "elementor-schema.json")
    ap.add_argument("--max-list", type=int, default=12)
    a = ap.parse_args()

    shipped = load(a.schema)
    mine = load(a.dump)

    if not mine["meta"].get("control_optimisation_disabled"):
        print("FAIL: your dump was taken with Elementor's control optimisation ON.", file=sys.stderr)
        print("      It is missing ~46% of controls. Use tools/extract-elementor-schema.php.", file=sys.stderr)
        return 1

    sv, mv = shipped["meta"], mine["meta"]
    print("SHIPPED  Elementor %s / Pro %s   (extracted %s)"
          % (sv["elementor_version"], sv["elementor_pro_version"], sv["extracted_at"]))
    print("YOURS    Elementor %s / Pro %s"
          % (mv["elementor_version"], mv["elementor_pro_version"]))
    same_version = sv["elementor_version"] == mv["elementor_version"]
    print("         versions %s" % ("match" if same_version else "DIFFER - drift below is expected"))
    print()

    s_flat, m_flat = flatten(shipped), flatten_raw(mine)
    failures, drift, unavailable = [], [], []

    # WHAT THIS INSTALL CAN EVEN HAVE.
    #
    # A widget the schema describes and your site does not have is only a failure if
    # your site was SUPPOSED to have it. WooCommerce contributes 29 widgets and
    # injects controls into two more; three Elementor experiments contribute another
    # 36 widgets. On a site without them, their absence is correct, and reporting it
    # as "the schema is wrong" would train people to ignore this tool.
    #
    # So the schema states each widget's requirement, and this checks it against the
    # install rather than assuming every install is the same one it came from.
    m_meta = mine.get("meta", {})
    have_plugins = {"woocommerce"} if m_meta.get("woocommerce_active") else set()
    have_exp = {k for k, v in (m_meta.get("experiments") or {}).items() if v}

    def satisfied(req: dict | None) -> bool:
        if not req:
            return True
        if req.get("plugin"):
            return req["plugin"].lower() in {p.lower() for p in have_plugins}
        if req.get("experiment"):
            return req["experiment"] in have_exp
        return False        # a WP legacy widget: never assume another plugin's widget

    s_all = {**shipped["elements"], **shipped["widgets"]}

    # 1. Widgets the schema promises that you do not have.
    s_owners = set(shipped["elements"]) | set(shipped["widgets"])
    m_owners = set(mine["elements"]) | set(mine["widgets"])
    gone = sorted(s_owners - m_owners)
    added = sorted(m_owners - s_owners)
    for w in gone:
        req = s_all[w].get("requires")
        if not satisfied(req):
            need = (req.get("plugin") or req.get("experiment") or "a WP widget from some plugin"
                    ) if req else "?"
            unavailable.append(("widget-unavailable", w,
                                f"absent because this install does not have `{need}` - "
                                f"which is exactly what the schema says it needs"))
        else:
            failures.append(("widget-missing", w,
                             "schema claims this widget exists; your site has no such widget"))
    for w in added:
        drift.append(("widget-new", w, "your site has a widget the schema does not describe"))

    # 2. Controls that vanished, and 3. controls whose type changed.
    for (owner, ctrl), c in s_flat.items():
        if owner not in m_owners:
            continue  # already reported as a missing widget
        mc = m_flat.get((owner, ctrl))
        if mc is None:
            # A control a gated plugin injects into a widget everyone has.
            rp = c.get("requires_plugin")
            if rp and rp.lower() not in {p.lower() for p in have_plugins}:
                unavailable.append(("control-unavailable", f"{owner}.{ctrl}",
                                    f"absent because `{rp}` is not active here - "
                                    f"the schema says it needs it"))
                continue
            failures.append(("control-missing", f"{owner}.{ctrl}",
                             "schema claims this control exists; it does not"))
        elif mc.get("type") != c.get("type"):
            failures.append(("control-type-changed", f"{owner}.{ctrl}",
                             f"type {c.get('type')} -> {mc.get('type')}; "
                             f"the JSON value shape you would write is now wrong"))

    for key in m_flat:
        if key not in s_flat and key[0] in s_owners:
            drift.append(("control-new", f"{key[0]}.{key[1]}", "not described by the schema"))

    # 4. The Free/Pro claim — the one that ships broken pages.
    #
    # A control's tier answers: "assuming I can use this widget at all, does
    # THIS CONTROL additionally require Pro?" On a widget that is itself Pro the
    # question is circular — the widget already needs Pro — so the per-control
    # tier there carries no information and is not checked. What is checked is
    # the case that actually bites: a Pro-only control sitting on a FREE widget.
    if a.free_dump:
        free = load(a.free_dump)
        free_flat = flatten_raw(free)
        owner_tier = {}
        for group in ("elements", "widgets"):
            for owner, w in shipped.get(group, {}).items():
                owner_tier[owner] = w["tier"]

        checked_tiers = 0
        for (owner, ctrl), c in s_flat.items():
            if (owner, ctrl) not in m_flat:
                continue
            if owner_tier.get(owner) == "pro":
                continue  # circular; the widget itself is the Pro requirement
            claimed = c.get("tier")
            if claimed not in ("free", "pro"):
                continue
            checked_tiers += 1
            actual = "free" if (owner, ctrl) in free_flat else "pro"
            if claimed == "free" and actual == "pro":
                failures.append(("tier-wrong", f"{owner}.{ctrl}",
                                 "schema says FREE, your install says it needs PRO - "
                                 "building on this ships a page that silently loses styling on Free"))
            elif claimed == "pro" and actual == "free":
                drift.append(("tier-conservative", f"{owner}.{ctrl}",
                              "schema says PRO, it is actually free here (safe direction)"))
        print(f"Free/Pro claims checked on free widgets/elements: {checked_tiers:,}")
        print()
    else:
        print("NOTE: no --free-dump, so the Free/Pro claims were NOT verified.")
        print("      That is the check that matters most. Add it:")
        print("      wp --skip-plugins=elementor-pro eval-file tools/extract-elementor-schema.php core+pro > free.json")
        print()

    # ---- report -----------------------------------------------------------
    def report(title, items, limit):
        print(f"{title}: {len(items)}")
        by_kind: dict[str, list] = {}
        for kind, what, why in items:
            by_kind.setdefault(kind, []).append((what, why))
        for kind, rows in sorted(by_kind.items()):
            print(f"  {kind}  ({len(rows)})")
            for what, why in rows[:limit]:
                print(f"     {what:<44} {why}")
            if len(rows) > limit:
                print(f"     ... and {len(rows) - limit} more")
        print()

    report("FAILURES  (the schema would mislead you)", failures, a.max_list)
    report("NOT ON THIS INSTALL  (the schema says so, and it is right)", unavailable, a.max_list)
    report("DRIFT     (your install is ahead of the schema)", drift, a.max_list)

    checked = len(s_flat)
    print(f"checked {checked:,} (owner, control) pairs from the shipped schema")
    if not failures:
        print()
        print("PASS - every control the schema describes exists on your install with the")
        print("       same type" + (", and every Free/Pro claim holds." if a.free_dump else "."))
        if drift:
            print(f"       {len(drift)} newer things exist that the schema does not know about;")
            print("       re-extract if you need them.")
        return 0

    print()
    print("FAIL - do not trust the shipped schema on this install. Re-extract:")
    print("       wp eval-file tools/extract-elementor-schema.php core+pro > raw.json")
    print("       wp --skip-plugins=elementor-pro eval-file tools/extract-elementor-schema.php core+pro > free.json")
    print("       python tools/build-indexes.py raw.json --free-dump free.json --out data/")
    return 1


if __name__ == "__main__":
    sys.exit(main())
