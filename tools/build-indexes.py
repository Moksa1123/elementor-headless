#!/usr/bin/env python3
"""
build-indexes.py — turn the raw dump from extract-elementor-schema.php into the
skill's shipped data files.

    python tools/build-indexes.py raw-dump.json --out data/

Two things happen here, and both are load-bearing.

1. FACTORING OUT THE COMMON CONTROLS
   Every Elementor widget inherits the same ~211 Advanced-tab controls
   (margin, padding, motion effects, transform, masking, custom CSS…). They are
   registered separately into each widget's own stack, so a raw dump repeats
   them 135 times: measured on Elementor 4.1.4 they occupy 75.6% of all control
   rows (28,018 of 37,054). Storing them once and marking each widget
   `has_common: true` is both smaller and more truthful — "padding works the
   same on every widget" is a fact about Elementor, not 135 coincidences.

   The rule is mechanical, not hand-picked: a control joins the common set only
   if it is byte-identical everywhere it appears AND appears in >=90% of
   widgets. Widgets that deviate are recorded explicitly in `common_missing`
   rather than being quietly forced into the pattern.

2. PER-CONTROL FREE/PRO TIER, DERIVED EMPIRICALLY
   A widget's tier can be read off the filesystem (which plugin defines the
   class). A *control's* tier cannot: Elementor Pro reaches into the free
   widgets and injects controls into them. Motion Effects, Sticky, Custom CSS,
   Display Conditions and Custom Attributes all appear on the free Heading
   widget - and all of them vanish on a site without Pro.

   Inheriting the owner's tier would therefore mislabel every one of them as
   free, and a page built on that assumption renders on your machine and
   silently loses its styling on a Free install. So the tier is measured, not
   assumed: extract twice, once normally and once with Pro not loaded, and diff.

       wp eval-file extract-elementor-schema.php core+pro > pro.json
       wp --skip-plugins=elementor-pro eval-file extract-elementor-schema.php core+pro > free.json
       python tools/build-indexes.py pro.json --free-dump free.json --out data/

   `--skip-plugins` only affects that one CLI process, so this is safe to run
   against a production site: nothing is deactivated.

   Measured on Elementor 4.1.4 + Pro 4.1.2, Pro injects exactly 46 controls
   into every widget, 79 into the container.

   Without --free-dump the build still works, but every control is marked
   `tier=unknown` rather than being quietly guessed.

3. CSV INDEXES FOR KEYWORD LOOKUP
   The JSON is the complete truth but is far too big to read into a model's
   context. The CSVs exist so an agent can `grep` for a keyword and pull back
   only the handful of matching lines. See tools/el.py, which is the intended
   front door.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

COMMON_THRESHOLD = 0.90  # a control must appear in >=90% of widgets to be "common"


def jdump(v) -> str:
    """Compact JSON for a CSV cell, or '' for empty."""
    if v is None or v == "" or v == [] or v == {}:
        return ""
    if isinstance(v, str):
        return v
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"))


def compute_common(widgets: dict) -> tuple[list, dict]:
    """The controls every widget shares, identical wherever they appear."""
    n = len(widgets)
    appears: Counter = Counter()
    variants: dict[str, set] = {}
    canonical: dict[str, dict] = {}

    for w in widgets.values():
        for c in w["controls"]:
            name = c["name"]
            appears[name] += 1
            key = json.dumps(c, sort_keys=True, ensure_ascii=False)
            variants.setdefault(name, set()).add(key)
            canonical[name] = c

    common_names = sorted(
        name
        for name, count in appears.items()
        if count >= n * COMMON_THRESHOLD and len(variants[name]) == 1
    )
    common = [canonical[name] for name in common_names]

    cset = set(common_names)
    missing = {}
    for wname, w in widgets.items():
        have = {c["name"] for c in w["controls"]}
        gap = sorted(cset - have)
        if gap:
            missing[wname] = gap
    return common, missing


def tier_map(raw: dict, free: dict | None) -> dict:
    """
    Per-owner, per-control tier, measured by diffing a Pro build against a
    Pro-less build. Anything present with Pro and absent without it is Pro-only,
    no matter which plugin's file the *widget* lives in.

    Elementor core registers stub "upgrade to Pro" widgets when Pro is inactive
    (they carry a `promotion_control` and no real controls of their own), so a
    widget merely *existing* in the Pro-less build does not make it free. Those
    stubs are recognised and their controls are not treated as free.
    """
    if free is None:
        return {}

    free_owners = {**free.get("elements", {}), **free.get("widgets", {})}

    # Identify promo stubs: a widget whose entire control set is the shared
    # common set has no functionality of its own and is an upsell placeholder.
    free_common, _ = compute_common(free["widgets"])
    free_common_names = {c["name"] for c in free_common}
    stubs = {
        name for name, w in free.get("widgets", {}).items()
        if not [c for c in w["controls"] if c["name"] not in free_common_names]
    }

    tiers: dict[str, dict[str, str]] = {}
    for owner, w in {**raw.get("elements", {}), **raw.get("widgets", {})}.items():
        if owner not in free_owners or owner in stubs:
            # Not present without Pro (or only present as a stub): all Pro.
            tiers[owner] = {c["name"]: "pro" for c in w["controls"]}
            continue
        free_names = {c["name"] for c in free_owners[owner]["controls"]}
        tiers[owner] = {
            c["name"]: ("free" if c["name"] in free_names else "pro")
            for c in w["controls"]
        }
    return tiers


def load_verification(path: Path | None) -> dict:
    """
    Fold the render sweep's results back into the schema.

    The extractor can only report what Elementor *claims*. The sweep reports what
    Elementor *does*. Where they disagree, the sweep wins, because it wrote the
    value into a real page and read the compiled CSS back.

    The clearest case is responsiveness. `hotspot.width` carries
    `is_responsive: true`, exactly like `container.padding` — but writing
    `width_tablet` emits nothing, verified in isolation with no other settings on
    the element. The flag over-promises. Left alone, the schema would keep telling
    people to write a key that silently does nothing, which is the precise failure
    this whole project exists to prevent.
    """
    if not path:
        return {}
    out: dict = {}
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            key = (r["owner"], r["control"].rsplit("_", 1)[0] if r.get("device") else r["control"])
            e = out.setdefault(key, {"rwd_ok": set(), "rwd_bad": set()})
            if r.get("device"):
                (e["rwd_ok"] if r["status"] in ("verified", "property")
                 else e["rwd_bad"]).add(r["device"])
            else:
                e["status"] = r["status"]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("raw", help="raw dump from extract-elementor-schema.php (Pro active)")
    ap.add_argument("--free-dump",
                    help="second dump taken with `wp --skip-plugins=elementor-pro`. "
                         "Without it, control tiers are marked 'unknown' rather than guessed.")
    ap.add_argument("--verification",
                    help="control-verification.csv from sweep-controls.py. Folds the "
                         "RENDERED result back in, so the schema stops claiming a control "
                         "or a breakpoint works when it demonstrably does not.")
    ap.add_argument("--out", default="data", help="output directory (default: data)")
    args = ap.parse_args()

    raw = json.loads(Path(args.raw).read_text(encoding="utf-8"))
    free = json.loads(Path(args.free_dump).read_text(encoding="utf-8")) if args.free_dump else None
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    widgets = raw["widgets"]
    elements = raw["elements"]

    # Refuse to build indexes from a degraded dump. The extractor asserts this
    # too, but a dump can also arrive by email — check it here as well.
    if not raw["meta"].get("control_optimisation_disabled"):
        print(
            "REFUSING: this dump was taken with Elementor's control optimisation ON.\n"
            "It is missing ~46% of controls and all tab/label metadata.\n"
            "Re-extract with tools/extract-elementor-schema.php.",
            file=sys.stderr,
        )
        return 1

    # ORDER MATTERS. The common set must be computed on the untouched controls:
    # a control joins it only if it is byte-identical across widgets, and
    # stamping `tier` first would break that — every control on a Pro-only
    # widget is trivially "pro" (the widget itself needs Pro), so `_margin`
    # would read as pro on the Posts widget and free on Heading, and the shared
    # set would shatter into per-widget copies.
    #
    # The verification results ARE stamped before it, deliberately: a control that
    # renders on one widget and not another is not the same control, and the shared
    # set should not pretend otherwise.
    verif = load_verification(Path(args.verification) if args.verification else None)
    n_broken_rwd = 0
    for owner, w in {**elements, **widgets}.items():
        for c in w["controls"]:
            v = verif.get((owner, c["name"]))
            if not v:
                continue
            if v.get("status"):
                c["verified"] = v["status"]
            claimed = set(c.get("responsive") or [])
            if claimed and (v["rwd_ok"] or v["rwd_bad"]):
                broken = sorted(claimed & v["rwd_bad"])
                if broken:
                    # Elementor's `is_responsive` says the suffix is legal.
                    # Rendering says it emits nothing. Rendering wins.
                    c["responsive_broken"] = broken
                    n_broken_rwd += 1
                c["responsive_verified"] = sorted(claimed & v["rwd_ok"])

    common, common_missing = compute_common(widgets)
    common_names = {c["name"] for c in common}

    # DEAD CONDITIONS. A control whose `condition` names a control that this widget
    # does not register can never become visible, because
    # controls-stack.php::is_control_visible bails at
    #
    #     if ( ! isset( $values[ $pure_condition_key ] ) ) { return false; }
    #
    # The button widget is the clearest case: its Background group excludes the
    # `image` field, yet background_attachment / _repeat / _size / _position are
    # still registered conditioned on `background_image[url]!`. In the editor they
    # are inert - there is no way to satisfy them.
    #
    # Writing the data directly, there is: put the missing key in `settings`
    # yourself and isset() becomes true. Verified on a live install (A/B: without
    # the key, nothing; with it, background-attachment/repeat/size all emit).
    #
    # So these are flagged rather than hidden: `dead_dep` lists the missing
    # control(s), and el.py / validate-page.py tell you what to write to revive it.
    for owner, w in {**elements, **widgets}.items():
        own = {c["name"] for c in w["controls"]}
        for c in w["controls"]:
            missing = []
            for dep in (c.get("condition") or {}):
                key = dep.split("[")[0].rstrip("!")
                if key not in own:
                    missing.append(key)
            if missing:
                c["dead_dep"] = sorted(set(missing))

    tiers = tier_map(raw, free)

    def ctier(owner: str, control: str) -> str:
        if not tiers:
            return "unknown"
        return tiers.get(owner, {}).get(control, "unknown")

    for owner, w in {**elements, **widgets}.items():
        for c in w["controls"]:
            c["tier"] = ctier(owner, c["name"])

    # The shared controls get their tier from the *free* widgets, where the
    # question is meaningful: "does this control disappear when Pro is off?"
    # Asking it of a Pro-only widget is circular.
    if free:
        free_common, _ = compute_common(free["widgets"])
        free_common_names = {c["name"] for c in free_common}
        for c in common:
            c["tier"] = "free" if c["name"] in free_common_names else "pro"
    else:
        for c in common:
            c["tier"] = "unknown"

    # ---- elementor-schema.json (factored) ---------------------------------
    slim_widgets = {}
    for name, w in widgets.items():
        own = [c for c in w["controls"] if c["name"] not in common_names]
        entry = {
            "name": name,
            "elType": "widget",
            "widgetType": name,
            "title": w.get("title"),
            "tier": w["tier"],
            "categories": w.get("categories", []),
            "has_common": name not in common_missing or len(common_missing[name]) < len(common_names),
            "controls_own": len(own),
            "controls_total": w["controls_total"],
            "sections": w["sections"],
            "controls": own,
        }
        if name in common_missing:
            entry["common_missing"] = common_missing[name]
        slim_widgets[name] = entry

    # Control types and group controls: tier by presence, same method.
    free_types = set(free["control_types"]) if free else set()
    free_groups = set(free["group_controls"]) if free else set()
    for t, c in raw["control_types"].items():
        c["tier"] = "unknown" if not free else ("free" if t in free_types else "pro")
    for g, c in raw["group_controls"].items():
        c["tier"] = "unknown" if not free else ("free" if g in free_groups else "pro")

    pro_common = [c for c in common if c.get("tier") == "pro"]
    pro_by_element = {
        name: sum(1 for c in e["controls"] if c.get("tier") == "pro")
        for name, e in elements.items()
    }

    schema = {
        "meta": {
            **raw["meta"],
            "generated_by": "tools/build-indexes.py",
            "common_controls_factored": len(common),
            "common_threshold": COMMON_THRESHOLD,
            "tier_source": (
                "measured by diffing against a `wp --skip-plugins=elementor-pro` dump"
                if free else "NOT MEASURED - all control tiers are 'unknown'"
            ),
            "pro_injected_into_every_widget": len(pro_common),
            "pro_injected_into_elements": pro_by_element,
            "pro_only_control_types": sorted(set(raw["control_types"]) - free_types) if free else [],
            "pro_only_group_controls": sorted(set(raw["group_controls"]) - free_groups) if free else [],
            "free_only_control_types": sorted(free_types - set(raw["control_types"])) if free else [],
        },
        "breakpoints": raw["breakpoints"],
        "control_types": raw["control_types"],
        "group_controls": raw["group_controls"],
        "common_controls": {
            "note": (
                "Registered into every widget's own stack by Elementor, so they behave "
                "identically on all of them. Stored once here. Widgets listing "
                "`common_missing` are the documented exceptions. NOTE the per-control "
                "`tier`: Elementor Pro injects some of these (Motion FX, Sticky, "
                "Custom CSS, Display Conditions, Custom Attributes) into free widgets, "
                "so 'this control is on the free Heading widget' does NOT mean it works "
                "without Pro."
            ),
            "count": len(common),
            "pro_count": len(pro_common),
            "controls": common,
        },
        "elements": elements,
        "widgets": slim_widgets,
    }
    (out / "elementor-schema.json").write_text(
        json.dumps(schema, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )

    # ---- widgets.csv -------------------------------------------------------
    with (out / "widgets.csv").open("w", newline="", encoding="utf-8") as f:
        w_ = csv.writer(f)
        w_.writerow(["name", "elType", "tier", "title", "categories",
                     "controls_own", "controls_total", "has_common"])
        for name, e in elements.items():
            w_.writerow([name, e["elType"], e["tier"], e.get("title") or name,
                         "|".join(e.get("categories", [])), e["controls_total"],
                         e["controls_total"], "no"])
        for name, e in sorted(slim_widgets.items()):
            w_.writerow([name, "widget", e["tier"], e.get("title") or name,
                         "|".join(e.get("categories", [])), e["controls_own"],
                         e["controls_total"], "yes" if e["has_common"] else "no"])

    # ---- controls.csv (element/widget-specific only) ------------------------
    # `tier` here is the CONTROL's measured tier, not the widget's. A free
    # widget can carry Pro-only controls; that is the whole point of measuring.
    def control_rows(owner, owner_tier, controls):
        for c in controls:
            yield [
                owner,
                c["name"],
                c["type"],
                c.get("tab", ""),
                c.get("section", ""),
                "|".join(c.get("responsive", [])),
                c.get("tier", "unknown"),
                owner_tier,
                jdump(c.get("default")),
                jdump(c.get("options")),
                jdump(c.get("condition")),
                "|".join(c.get("css", [])),
                c.get("label", "") or "",
            ]

    header = ["owner", "control", "type", "tab", "section", "responsive",
              "control_tier", "owner_tier", "default", "options", "condition",
              "css", "label"]

    with (out / "controls.csv").open("w", newline="", encoding="utf-8") as f:
        w_ = csv.writer(f)
        w_.writerow(header)
        for name, e in elements.items():
            for row in control_rows(name, e["tier"], e["controls"]):
                w_.writerow(row)
        for name, e in sorted(slim_widgets.items()):
            for row in control_rows(name, e["tier"], e["controls"]):
                w_.writerow(row)

    # ---- common-controls.csv ----------------------------------------------
    with (out / "common-controls.csv").open("w", newline="", encoding="utf-8") as f:
        w_ = csv.writer(f)
        w_.writerow(header)
        for row in control_rows("*ALL_WIDGETS*", "free", common):
            w_.writerow(row)

    # ---- control-types.csv -------------------------------------------------
    with (out / "control-types.csv").open("w", newline="", encoding="utf-8") as f:
        w_ = csv.writer(f)
        w_.writerow(["type", "tier", "defined_in", "value_shape", "php_class"])
        for t, c in sorted(raw["control_types"].items()):
            w_.writerow([t, c["tier"], c["source"],
                         jdump(c.get("value_shape")), c["class"]])

    # ---- group-controls.csv ------------------------------------------------
    with (out / "group-controls.csv").open("w", newline="", encoding="utf-8") as f:
        w_ = csv.writer(f)
        w_.writerow(["group", "tier", "source", "field_count", "fields", "php_class"])
        for g, c in sorted(raw["group_controls"].items()):
            fields = "|".join(fl["field"] for fl in c.get("fields", []))
            w_.writerow([g, c["tier"], c["source"], c.get("field_count", ""),
                         fields, c["class"]])

    # ---- breakpoints.csv ---------------------------------------------------
    with (out / "breakpoints.csv").open("w", newline="", encoding="utf-8") as f:
        w_ = csv.writer(f)
        w_.writerow(["breakpoint", "active", "direction", "value_px", "control_suffix"])
        for b, c in raw["breakpoints"].items():
            w_.writerow([b, "yes" if c.get("active") else "no",
                         c.get("direction", ""), c.get("value", ""), c.get("suffix", "")])

    # ---- pro-only-controls.csv ---------------------------------------------
    # The safety table. Every control here silently does nothing on a site
    # without Elementor Pro. Grep this before shipping anything to a Free site.
    if free:
        with (out / "pro-only-controls.csv").open("w", newline="", encoding="utf-8") as f:
            w_ = csv.writer(f)
            w_.writerow(["scope", "control", "type", "tab", "section", "note"])
            for c in common:
                if c.get("tier") == "pro":
                    w_.writerow(["*ALL_WIDGETS*", c["name"], c["type"], c.get("tab", ""),
                                 c.get("section", ""),
                                 "Pro injects this into every widget, free ones included"])
            for name, e in elements.items():
                for c in e["controls"]:
                    if c.get("tier") == "pro":
                        w_.writerow([name, c["name"], c["type"], c.get("tab", ""),
                                     c.get("section", ""),
                                     f"Pro injects this into the free {name} element"])
            for name, e in sorted(slim_widgets.items()):
                if e["tier"] == "pro":
                    continue  # the whole widget is Pro; listing each control adds noise
                for c in e["controls"]:
                    if c.get("tier") == "pro":
                        w_.writerow([name, c["name"], c["type"], c.get("tab", ""),
                                     c.get("section", ""),
                                     f"Pro-only control on the FREE {name} widget"])
        with (out / "pro-only-widgets.csv").open("w", newline="", encoding="utf-8") as f:
            w_ = csv.writer(f)
            w_.writerow(["widget", "title", "categories"])
            for name, e in sorted(slim_widgets.items()):
                if e["tier"] == "pro":
                    w_.writerow([name, e.get("title") or name,
                                 "|".join(e.get("categories", []))])

    # ---- report ------------------------------------------------------------
    total_rows = sum(w["controls_total"] for w in widgets.values()) + \
                 sum(e["controls_total"] for e in elements.values())
    own_rows = sum(e["controls_own"] for e in slim_widgets.values()) + \
               sum(e["controls_total"] for e in elements.values())

    print(f"Elementor {raw['meta']['elementor_version']} / Pro {raw['meta']['elementor_pro_version']}")
    print(f"  elements       {len(elements)}")
    print(f"  widgets        {len(widgets)} ({raw['meta']['counts']['widgets_free']} free, "
          f"{raw['meta']['counts']['widgets_pro']} pro)")
    print(f"  control rows   {total_rows} raw -> {own_rows + len(common)} stored "
          f"({len(common)} common factored out, "
          f"{100 * (total_rows - own_rows - len(common)) / total_rows:.1f}% saved)")
    print(f"  control types  {len(raw['control_types'])}")
    print(f"  group controls {len(raw['group_controls'])}")
    print()
    if verif:
        vc = sum(1 for w in {**elements, **slim_widgets}.values()
                 for c in w["controls"] if c.get("verified"))
        print(f"  RENDER-VERIFIED (folded back in from the sweep):")
        print(f"    controls with a rendered result   {vc:,}")
        print(f"    controls whose responsive suffix  {n_broken_rwd:,}  <- `is_responsive` promises")
        print(f"      is claimed but emits NOTHING            a breakpoint Elementor never renders")
        print()
    else:
        print("  NOTE: no --verification given, so the schema records what Elementor")
        print("        CLAIMS, not what it was seen to do. Run the sweep and rebuild:")
        print("        python tools/sweep-controls.py plan ... && bash sweep/RUN.sh")
        print("        python tools/sweep-controls.py check sweep/ --out data/control-verification.csv")
        print("        python tools/build-indexes.py raw.json --free-dump free.json \\")
        print("               --verification data/control-verification.csv --out data/")
        print()
    if free:
        all_ctrls = [c for w in {**elements, **slim_widgets}.values() for c in w["controls"]] + common
        n_pro = sum(1 for c in all_ctrls if c.get("tier") == "pro")
        print(f"  FREE/PRO measured against a Pro-less dump:")
        print(f"    Pro-only controls          {n_pro} of {len(all_ctrls)} stored")
        print(f"    injected into EVERY widget {len(pro_common)}  "
              f"(motion fx, sticky, custom css, display conditions, custom attributes)")
        for el, n in pro_by_element.items():
            print(f"    injected into {el:<14} {n}")
        print(f"    Pro-only control types     {len(schema['meta']['pro_only_control_types'])}")
        print(f"    Pro-only group controls    {len(schema['meta']['pro_only_group_controls'])}")
    else:
        print("  WARNING: no --free-dump given. Every control tier is 'unknown'.")
        print("  Re-run with a Pro-less dump to get a trustworthy Free/Pro split:")
        print("    wp --skip-plugins=elementor-pro eval-file tools/extract-elementor-schema.php "
              "core+pro > free.json")
    print()
    for p in sorted(out.glob("*.csv")) + [out / "elementor-schema.json"]:
        print(f"  {p.name:26} {p.stat().st_size / 1024:9.1f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
