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


def compute_common(widgets: dict) -> tuple[list, dict, set]:
    """
    The controls that every widget IN THE CLASSIC SYSTEM shares, byte-identical.

    Returns (common, missing, participants).

    Not every widget is in that system. Elementor V4's atomic widgets (`e-heading`,
    `e-button`, the `e-form-*` set) have their own style model and register NONE of
    the Advanced-tab controls - no `_margin`, no `_animation`, nothing. There are 20
    of them, out of 192.

    A fixed "appears on >= 90% of widgets" threshold cannot survive that, and it
    did not: `_margin` appears on 172 of 192 = 89.58%, and the whole shared set -
    all 210 controls - silently evaluated to EMPTY. The schema went from 3.2 MB to
    14 MB and every widget carried its own copy of controls it shares with 171
    others. Nothing errored.

    So who participates is MEASURED, not thresholded:

      1. candidates  = controls on more than half the widgets, byte-identical
      2. participants = widgets carrying at least 90% of the candidates
                        (a widget either speaks this control system or it does not;
                         there is nothing in between, so this split is sharp)
      3. common      = candidates present on EVERY participant

    A widget outside the participant set gets `has_common: false` and keeps its own
    controls - which is the truth about it, not a rounding error.
    """
    def scan(subset):
        appears: Counter = Counter()
        variants: dict[str, set] = {}
        canonical: dict[str, dict] = {}
        for w in subset.values():
            for c in w["controls"]:
                appears[c["name"]] += 1
                variants.setdefault(c["name"], set()).add(
                    json.dumps(c, sort_keys=True, ensure_ascii=False))
                canonical[c["name"]] = c
        return appears, variants, canonical

    appears, variants, canonical = scan(widgets)
    n = len(widgets)
    candidates = {name for name, cnt in appears.items()
                  if cnt > n * 0.5 and len(variants[name]) == 1}
    if not candidates:
        return [], {}, set(widgets)

    participants = {
        name for name, w in widgets.items()
        if len(candidates & {c["name"] for c in w["controls"]}) >= len(candidates) * COMMON_THRESHOLD
    }
    if not participants:
        return [], {}, set(widgets)

    sub = {k: widgets[k] for k in participants}
    appears, variants, canonical = scan(sub)
    np = len(participants)
    common_names = sorted(
        name for name in candidates
        if appears.get(name, 0) >= np * COMMON_THRESHOLD and len(variants.get(name, ())) == 1
    )
    common = [canonical[name] for name in common_names]

    cset = set(common_names)
    missing = {}
    for wname in participants:
        gap = sorted(cset - {c["name"] for c in widgets[wname]["controls"]})
        if gap:
            missing[wname] = gap
    return common, missing, participants


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

    # Identify promo stubs. Elementor core registers a placeholder for every Pro
    # widget when Pro is off, purely to show an upsell in the editor - and they are
    # named EXACTLY like the real thing (`woocommerce-product-price`). Take their
    # presence in the Pro-less dump at face value and 26 Pro widgets get labelled
    # free, which is the single worst mistake this schema can make.
    #
    # The `promotions` module is the exact signal (its own gate is `! has_pro()`).
    # The control-set heuristic is kept as a fallback for dumps taken before the
    # extractor recorded modules.
    free_common, _, _ = compute_common(free["widgets"])
    free_common_names = {c["name"] for c in free_common}
    stubs = {
        name for name, w in free.get("widgets", {}).items()
        if w.get("module") == "promotions"
        or not [c for c in w["controls"] if c["name"] not in free_common_names]
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


def requires_of(owner: dict, gates: dict) -> dict | None:
    """
    What must be true of an install for this widget to EXIST at all.

    The widget surface is not a property of Elementor. It is a property of the
    install. On one site the same Elementor 4.1.4 / Pro 4.1.2 registers 148
    widgets; on another it registers 192. Nothing is broken - the extra 44 are
    WooCommerce's, and they appear only when WooCommerce is active.

    A schema that just says "148 widgets" is not incomplete, it is WRONG: ask it
    for `woocommerce-product-price` and it will tell you, with total confidence,
    that Elementor has no such widget.

    So every widget carries what it needs. It is read off the module's own
    `is_active()` gate, in Elementor's source - not inferred from its name:

        module woocommerce      class_exists( 'woocommerce' )
        module atomic-widgets   experiment e_atomic_elements
        module nested-carousel  experiment nested-elements
    """
    if owner.get("wp_widget"):
        # Not Elementor's at all - a legacy WP widget that Elementor wraps. It
        # exists only while some plugin keeps registering it.
        return {"wp_widget": True}
    g = gates.get(owner.get("module") or "")
    if not g:
        return None
    if g.get("plugin_class"):
        return {"plugin": g["plugin_class"], "gate": g["gate"]}
    # An experiment is a REQUIREMENT only if the gate actually checks it. The
    # extractor also records a module's own EXPERIMENT_NAME const, and letting that
    # override the real gate claimed 21 widgets (contact-buttons, link-in-bio,
    # mega-menu variants) need experiments that are OFF on a site where every one
    # of them is registered and rendering - the module merely DECLARES the
    # experiment; its is_active() gates on class_exists. A schema that says
    # "does not exist here" about a widget the site is happily serving fails in
    # the REJECTING direction, which is the worse one.
    if g.get("experiment") and "is_feature_active" in (g.get("gate") or ""):
        return {"experiment": g["experiment"], "gate": g["gate"]}
    return None


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


def load_class_verification(path: Path | None) -> dict:
    """
    Fold the HTML sweep's results in, the same way the CSS sweep's are folded.

    A control can act by emitting CSS or by appending a class to the wrapper, and
    the two are verified by reading two different things - the compiled stylesheet
    and the rendered markup. A control with `prefix_class` and no `css` was
    completely unverified until this sweep existed, however green the CSS run was.
    """
    if not path or not path.exists():
        return {}
    out: dict = {}
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["device"] or r["legacy_value"]:
                continue        # scored separately; the base row is what stamps
            out[(r["owner"], r["control"])] = r["status"]
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
    ap.add_argument("--gated-dump", action="append", default=[], metavar="NAME=PATH",
                    help="a dump taken with NAME switched OFF (e.g. "
                         "woocommerce=iso-pro.json). Anything in the main dump but "
                         "not in this one needs NAME to exist - measured the same way "
                         "the Free/Pro split is. Repeatable. WooCommerce does not just "
                         "add widgets: it injects controls into Pro's loop widgets too, "
                         "and a control-level diff is the only thing that finds those.")
    ap.add_argument("--class-verification",
                    help="class-verification.csv from sweep-classes.py. The same, for the "
                         "controls that emit a wrapper CLASS instead of CSS - which the "
                         "stylesheet sweep cannot see at all.")
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

    # ORDER MATTERS, AND IT IS THE SAME RULE EVERY TIME.
    #
    #   ANYTHING MEASURED PER WIDGET IS STAMPED AFTER compute_common(), NEVER BEFORE.
    #
    # The common set is the controls that are byte-identical on every widget. Stamp
    # a per-widget measurement onto them first and they stop being identical, the
    # set shatters, and all 210 shared controls get copied into all 192 widgets.
    #
    # This file has now broken that rule three separate times:
    #
    #   tier            trivially "pro" on a Pro widget -> `_margin` pro on Posts,
    #                   free on Heading. (210 -> 46 shared controls)
    #   class_verified  unobservable on the 29 widgets that render no markup.
    #                   (210 -> 192)
    #   verified        THIS ONE SURVIVED FOR MONTHS because the sweep happened to
    #                   cover every widget uniformly, so the stamp was the same
    #                   everywhere and nothing shattered. The moment WooCommerce's
    #                   29 widgets entered the schema unswept, `_margin` carried
    #                   `verified` on Heading and nothing on Product Price - and the
    #                   common set collapsed to ZERO.
    #
    # A rule that only holds while your data happens to be uniform is not a rule.
    # All three are now stamped after.
    verif = load_verification(Path(args.verification) if args.verification else None)
    classv = load_class_verification(
        Path(args.class_verification) if args.class_verification else None)

    # A widget that renders no markup at all has no wrapper, so none of its class
    # controls can do anything - `_position`, `hide_tablet`, the transforms, all
    # inert. Three of these are not really widgets (`common`, `common-base`,
    # `common-optimized` are the registries Elementor injects the shared controls
    # from, and they are not placeable at all); the rest need real site content -
    # a template, a loop, a sidebar, a configured WP widget. Either way, saying so
    # is the difference between "this control is fine" and "this control cannot be
    # observed here", and only the render knows which.
    for owner in {o for (o, _), s in classv.items() if s == "no-element"}:
        if owner in widgets:
            widgets[owner]["renders_bare"] = False

    # What each widget's module demanded of the install it was extracted from.
    gates = raw["meta"].get("module_gates") or {}
    for _, e in elements.items():
        r = requires_of(e, gates)
        if r:
            e["requires"] = r

    # CONTROL-level requirements, measured by diff. A gated plugin does not only
    # bring its own widgets: WooCommerce reaches into Elementor Pro's `loop-grid`
    # and `loop-carousel` and adds `product_query_exclude*` to them. Those controls
    # sit on a widget that exists everywhere, so nothing about the widget discloses
    # them - only a dump taken with WooCommerce off does.
    for spec in args.gated_dump:
        if "=" not in spec:
            print(f"--gated-dump needs NAME=PATH, got {spec!r}", file=sys.stderr)
            return 1
        gname, gpath = spec.split("=", 1)
        gd = json.loads(Path(gpath).read_text(encoding="utf-8"))
        gowners = {**gd.get("elements", {}), **gd.get("widgets", {})}
        for owner, w in {**elements, **widgets}.items():
            if owner not in gowners:
                continue        # the whole widget is gated; the module gate says so
            without = {c["name"] for c in gowners[owner]["controls"]}
            for c in w["controls"]:
                if c["name"] not in without:
                    c["requires_plugin"] = gname
    n_v4 = sum(1 for o in list(widgets.values()) + list(elements.values())
               if o.get("control_system") == "v4-atomic")

    # WHERE each control's CSS lands. A SEPARATE FILE, on purpose.
    #
    # A control's `css` says WHICH property it sets. It does not say WHERE:
    # `title_color` on the heading targets `{{WRAPPER}} .elementor-heading-title`,
    # a node INSIDE the element. Grep the compiled stylesheet and the rule is right
    # there, so every text-level check in this repo passed without ever knowing
    # this. Ask a BROWSER what the element computes and you must query the node the
    # rule actually targets - ask the wrapper for `color` and you get the inherited
    # value, and a page that renders perfectly reads as broken.
    #
    # It does not go in the schema for two measured reasons:
    #
    #  1. 18,842 references over 1,070 distinct strings. Inlining them took the
    #     schema from 4.3 MB to 10.4 MB, and the schema's whole purpose is to be the
    #     thing you never load.
    #
    #  2. 569 of the SHARED controls have a DIFFERENT selector depending on the
    #     widget: `_background_color` lands on `{{WRAPPER}}` for some and on
    #     `{{WRAPPER}} > .elementor-widget-container` for others, because Elementor
    #     drops that inner div on some widgets and not others. Same property,
    #     different node. Putting it on the control makes those 569 controls
    #     non-identical across widgets and the shared set collapses (211 -> 135).
    #
    # So: `data/css-selectors.csv`, keyed by (owner, control), loaded only by the
    # tools that need to query a real DOM.
    sel_rows: list[tuple[str, str, str, str]] = []
    for oname, o in list(widgets.items()) + list(elements.items()):
        for c in o["controls"]:
            for entry in c.pop("css_selectors", None) or []:
                sel_rows.append((oname, c["name"], entry["sel"],
                                 " ".join(entry.get("props") or [])))

    common, common_missing, participants = compute_common(widgets)
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

    # CLASS VERIFICATION — stamped AFTER the common set, for the same reason `tier`
    # is. The result is per (owner, control), but a shared control is shared: it is
    # byte-identical on every widget, and only stays in the common set if it STAYS
    # byte-identical. 29 widgets render no markup at all, so `_position` came back
    # `verified` on 106 of them and unobservable on 29 — stamp that per widget and
    # the shared control is no longer shared. All 18 class controls fall out of the
    # common set (210 -> 192) and get copied into all 135 widgets instead.
    #
    # This is the third time this exact ordering has bitten this file. The rule:
    # anything measured PER WIDGET gets stamped after compute_common, never before.
    #
    # "no-element" is dropped entirely — it is a fact about the widget (recorded as
    # `renders_bare: false`), not about the control.
    n_broken_rwd = 0
    for owner, w in {**elements, **widgets}.items():
        for c in w["controls"]:
            if classv.get((owner, c["name"])) in ("verified", "FAILED"):
                c["class_verified"] = classv[(owner, c["name"])]
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

    # A shared control's verdict is the aggregate over the widgets where it could be
    # observed at all: FAILED anywhere is a failure; otherwise verified if it was
    # ever verified. Not every widget is in the sweep - the WooCommerce ones need a
    # WooCommerce install - and a control is not unverified just because ONE of the
    # 192 widgets carrying it has not been swept.
    for c in common:
        seen = {s for (o, n), s in classv.items() if n == c["name"] and o in widgets}
        if "FAILED" in seen:
            c["class_verified"] = "FAILED"
        elif "verified" in seen:
            c["class_verified"] = "verified"

        vs = [v for (o, n), v in verif.items() if n == c["name"] and o in widgets]
        if vs:
            st = {v.get("status") for v in vs}
            c["verified"] = ("FAILED" if "FAILED" in st
                             else "verified" if "verified" in st
                             else next(iter(st)) if st else None)
            ok = set().union(*(v["rwd_ok"] for v in vs))
            bad = set().union(*(v["rwd_bad"] for v in vs)) - ok
            claimed = set(c.get("responsive") or [])
            if claimed & bad:
                c["responsive_broken"] = sorted(claimed & bad)
            if claimed & ok:
                c["responsive_verified"] = sorted(claimed & ok)

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
        free_common, _, _ = compute_common(free["widgets"])
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
            # Measured, not inferred: this widget speaks the classic control system
            # (and therefore carries the shared Advanced tab) or it does not. The V4
            # atomic widgets do not, and saying they do would send an agent looking
            # for a `_margin` that is not there.
            "has_common": name in participants,
            "controls_own": len(own),
            "controls_total": w["controls_total"],
            "sections": w["sections"],
            "controls": own,
        }
        if name in common_missing:
            entry["common_missing"] = common_missing[name]
        if w.get("module"):
            entry["module"] = w["module"]
        req = requires_of(w, gates)
        if req:
            entry["requires"] = req
        # Elementor V4. A different data model, not a widget with no settings.
        if w.get("control_system"):
            entry["control_system"] = w["control_system"]
            entry["props"] = w.get("props", [])
        # Measured, not assumed: dropped on a bare page with settings and nothing
        # else, this widget produced no markup. Its wrapper-class controls have
        # nothing to attach to, and an agent reaching for it needs to know it will
        # render empty until the site supplies a template / loop / sidebar / post.
        if w.get("renders_bare") is False:
            entry["renders_bare"] = False
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
        # The `__dynamic__` surface: every registered tag, its group, the control
        # CATEGORIES it can bind to, its own settings, and its tier. All 51 are Pro
        # on 4.1.2 - dynamic content IS the Pro feature - and 13 need WooCommerce.
        "dynamic_tags": raw.get("dynamic_tags") or {},
        # The legal values of `_elementor_template_type`, with what each needs.
        "documents": raw.get("documents") or {},
        # `_elementor_page_settings` per document type: hide_title, the Canvas /
        # header-footer template switch, per-page margin/padding/background.
        "page_settings": raw.get("page_settings") or {},
        # The Site Settings panel, saved on the KIT post. `__globals__` references
        # (globals/colors?id=primary) resolve into its repeaters.
        "kit_settings": raw.get("kit_settings"),
        # The popup document's settings (Pro): layout, overlay, close button, open
        # rules. Triggers/timing are a separate meta - see the note inside.
        "popup_settings": raw.get("popup_settings"),
        # Theme Builder display conditions (Pro): the registry the condition strings
        # ('include/singular/post/123') are built from.
        "theme_builder_conditions": raw.get("theme_builder_conditions"),
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

    # ---- dynamic-tags.csv --------------------------------------------------
    with (out / "dynamic-tags.csv").open("w", newline="", encoding="utf-8") as f:
        w_ = csv.writer(f)
        w_.writerow(["name", "title", "group", "binds_to_categories", "tier",
                     "settings", "source"])
        for name, t in sorted((raw.get("dynamic_tags") or {}).items()):
            if "error" in t:
                continue
            w_.writerow([name, t.get("title"), t.get("group"),
                         "|".join(t.get("categories") or []), t.get("tier"),
                         " ".join(c["name"] for c in t.get("settings") or []),
                         t.get("source", "")])

    # ---- css-selectors.csv -------------------------------------------------
    # (owner, control) -> the selector path relative to `.elementor-element-<id>`.
    # A control with NO row here styles the element itself.
    with (out / "css-selectors.csv").open("w", newline="", encoding="utf-8") as f:
        w_ = csv.writer(f)
        w_.writerow(["owner", "control", "selector_template", "properties"])
        w_.writerows(sorted(sel_rows))

    # ---- widgets.csv -------------------------------------------------------
    def req_str(e: dict) -> str:
        r = e.get("requires")
        if not r:
            return ""
        if r.get("plugin"):
            return f"plugin:{r['plugin']}"
        if r.get("experiment"):
            return f"experiment:{r['experiment']}"
        return "wp-widget"

    with (out / "widgets.csv").open("w", newline="", encoding="utf-8") as f:
        w_ = csv.writer(f)
        w_.writerow(["name", "elType", "tier", "requires", "title", "categories",
                     "controls_own", "controls_total", "has_common"])
        for name, e in elements.items():
            w_.writerow([name, e["elType"], e["tier"], req_str(e), e.get("title") or name,
                         "|".join(e.get("categories", [])), e["controls_total"],
                         e["controls_total"], "no"])
        for name, e in sorted(slim_widgets.items()):
            w_.writerow([name, "widget", e["tier"], req_str(e), e.get("title") or name,
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
