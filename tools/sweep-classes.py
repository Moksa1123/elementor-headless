#!/usr/bin/env python3
"""
sweep-classes.py - render every class-emitting control and assert the class.

The CSS sweep (sweep-controls.py) reads the compiled stylesheet, so it can only
ever see controls that produce CSS. It is structurally blind to the OTHER thing an
Elementor control can do: append a class to the element's wrapper.

    element-base.php:815
        $this->add_render_attribute( '_wrapper', 'class',
            $controls[ $setting_key ]['prefix_class'] . $setting );

2,609 (owner, control) pairs do this, and nothing in this repo had ever checked one
of them. `_position`, `hide_tablet`, every `view`/`shape`/`align`/`position` choose
control, the whole transform popover set - all of them were shipped on the strength
of "Elementor registered a prefix_class, so presumably it works".

Three things make the class path different from the CSS path, and all three are
places to be wrong quietly:

1. The class value is NOT always the value you wrote. `classes_dictionary` remaps
   it first (element-base.php:800), so `position: "top"` renders
   `elementor-position-block-start`. The option list does not mention `top`.

2. A responsive class control has a DIFFERENT PREFIX PER DEVICE, because
   add_responsive_control() sprintf()s the device into it:
   `elementor%s-position-` -> `elementor-position-` / `elementor-tablet-position-`.
   There is no `_tablet` suffix on the class.

3. An empty value emits nothing - except the string "0", which is special-cased
   (`empty( $setting ) && '0' !== $setting`). So `columns: "0"` emits
   `elementor-grid-0` and `columns: 0` (a JSON number) emits nothing at all.

Usage:
    python tools/sweep-classes.py plan  --post-id <draft> --out classsweep
    bash classsweep/RUN.sh                     # on the server, from the WP root
    python tools/sweep-classes.py check classsweep --out data/class-verification.csv
"""
from __future__ import annotations

import argparse
import csv
import html
import importlib.util
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA_PATH = HERE.parent / "data" / "elementor-schema.json"


def _load_sweep_controls():
    """
    Import sweep-controls.py for its dependency solver.

    Deliberately NOT reimplemented. `requirements()` / `satisfy()` / `cond_holds()`
    encode Elementor's exact condition semantics - the simple `condition` form, the
    advanced `conditions` boolean tree, negated lists, and the rule that a
    dependency already satisfied must not be reassigned. Two copies of that would
    drift, and the copy that drifts is the one that starts passing things it
    should fail.
    """
    spec = importlib.util.spec_from_file_location("sweep_controls",
                                                  HERE / "sweep-controls.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SC = _load_sweep_controls()


# ---------------------------------------------------------------------------
# What class does Elementor actually put on the wrapper?
# ---------------------------------------------------------------------------
def class_prefix(ctrl: dict, device: str | None) -> str | None:
    """The prefix for this control AT THIS DEVICE. They are different strings."""
    if device is None:
        return ctrl.get("prefix_class")
    return (ctrl.get("prefix_class_devices") or {}).get(device)


def class_of(ctrl: dict, value, device: str | None) -> str | None:
    """
    Reproduce element-base.php's add_render_attributes(), exactly:

        if ( isset( $controls[$k]['classes_dictionary'][$setting] ) )
            $value = $controls[$k]['classes_dictionary'][$setting];
        else
            $value = $setting;
        if ( empty( $value ) && '0' !== $value ) continue;
        add_render_attribute( '_wrapper', 'class', $prefix . $value );
    """
    prefix = class_prefix(ctrl, device)
    if prefix is None:
        return None
    v = (ctrl.get("classes_dictionary") or {}).get(str(value), value)
    v = str(v)
    if v == "" and v != "0":            # PHP: empty('') and '0' !== ''
        return None
    return prefix + v


def synth_class(owner: str, ctrl: dict, device: str | None, rank: int):
    """
    Pick a value for a class-emitting control, and say which class it must produce.

    Returns (json_value, expected_class) or None with a reason.
    """
    t = ctrl["type"]

    # A switcher stores its `return_value`, not `true` and not `"yes"`. Get this
    # wrong and `hide_tablet: "yes"` renders the class `elementor-yes`, which
    # styles nothing and hides nothing. The default return_value IS "yes", but
    # the responsive-hide switchers override it ("hidden-tablet"), so it must be
    # read per control rather than assumed.
    if t == "switcher":
        return ctrl.get("return_value") or "yes", None

    if t == "popover_toggle":
        return ctrl.get("return_value") or "yes", None

    opts = ctrl.get("options") or SC.TYPE_OPTIONS.get(t)
    if opts:
        # Rotate through the options by rank so desktop / tablet / mobile land on
        # different values where the control has enough of them. Not required for
        # correctness (the prefixes already differ per device) but it means a
        # passing tablet assertion cannot be satisfied by a desktop value.
        usable = [o for o in opts if str(o) != ""]
        if not usable:
            return None, f"a `{t}` whose only option is the empty string"
        return str(usable[rank % len(usable)]), None

    if ctrl.get("return_value") is not None:
        return str(ctrl["return_value"]), None

    # `hidden` controls carry a prefix_class and are written by the editor's JS
    # (divider's separator_type, the pattern flags). Headlessly we write them
    # ourselves, so any stable token proves the mechanism.
    if t in ("hidden", "text"):
        return "eh" + SC.stable_hex(owner, ctrl["name"], device or "d")[:4], None

    if t == "number":
        return str(SC.stable_int(owner, ctrl["name"], device or "d", lo=1, hi=9)), None

    return None, f"no class value can be synthesised for a `{t}` control"


# A widget with nothing to show renders nothing at all - no wrapper, so no classes
# to assert, however correct its settings are. That is a property of the WIDGET, not
# of the controls under test, and the sweep must not report it as either a pass or a
# failure. Where a minimal piece of content is enough to make the widget appear, give
# it one; these are the only widgets whose own class controls were otherwise
# unreachable. Repeaters and galleries are in the solver's SKIP_TYPES (no value can
# be synthesised for them generically), which is exactly why they need naming here.
RENDER_SEED: dict[str, dict] = {
    "image-carousel": {"carousel": [{"id": "", "url": SC.MEDIA_URL}]},
    "image-gallery": {"wp_gallery": [{"id": "", "url": SC.MEDIA_URL}]},
    # Elementor's own default first item, verbatim - a repeater item missing the
    # fields the render path reads produces no list, and therefore no widget.
    "post-info": {"icon_list": [{
        "_id": "eh00001", "type": "author", "link": "yes", "show_icon": "default",
        "selected_icon": {"value": "far fa-user-circle", "library": "fa-regular"},
    }]},
    "html": {"html": "<span>eh</span>"},
    "menu-anchor": {"anchor": "eh-anchor"},
}


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------
def plan_owner(schema: dict, owner: str, skipped: list) -> list[dict]:
    controls = SC.controls_of(schema, owner)
    variants: list[dict] = []

    targets = [c for c in controls.values() if c.get("prefix_class")]
    targets.sort(key=lambda c: c["name"])

    def place(assign: dict, tgts: list[dict]):
        for v in variants:
            merged = dict(v["assign"])
            if all(merged.get(k, val) == val for k, val in assign.items()):
                merged.update(assign)
                v["assign"] = merged
                v["targets"].extend(tgts)
                return
        variants.append({"assign": dict(assign), "targets": list(tgts)})

    for ctrl in targets:
        name = ctrl["name"]
        value, reason = synth_class(owner, ctrl, None, 0)
        if value is None:
            skipped.append((owner, name, ctrl["type"], reason))
            continue
        expect = class_of(ctrl, value, None)
        if expect is None:
            skipped.append((owner, name, ctrl["type"],
                            "every synthesisable value maps to an empty class"))
            continue

        req = SC.requirements(ctrl, controls, owner)
        if req is None:
            skipped.append((owner, name, ctrl["type"],
                            "its dependency chain cannot be satisfied "
                            "(contradictory, or a dependency we cannot synthesise)"))
            continue
        if name in req and req[name] != value:
            skipped.append((owner, name, ctrl["type"],
                            "the control is its own dependency at a different value"))
            continue

        assign = {**req, name: value}
        tgts = [{"name": name, "expect": expect, "type": ctrl["type"]}]

        # Every device gets its own prefix, so assert every device's prefix.
        for rank, dev in enumerate(ctrl.get("responsive") or [], start=1):
            if not class_prefix(ctrl, dev):
                continue
            dv, _ = synth_class(owner, ctrl, dev, rank)
            if dv is None:
                continue
            dexp = class_of(ctrl, dv, dev)
            if dexp is None:
                continue
            assign[f"{name}_{dev}"] = dv
            tgts.append({"name": f"{name}_{dev}", "expect": dexp,
                         "type": ctrl["type"], "device": dev, "base": name})

        place(assign, tgts)

        # classes_dictionary is a value REMAPPER, and the only way to prove it is
        # to write a value it remaps. These are the legacy names (`top`, `left`)
        # that predate Elementor's move to logical properties; they are not in the
        # options list, which is exactly why a schema without the dictionary makes
        # them look invalid. They render.
        for legacy, mapped in (ctrl.get("classes_dictionary") or {}).items():
            if str(legacy) in {str(o) for o in (ctrl.get("options") or [])}:
                continue        # not a legacy alias, just an option
            exp = class_of(ctrl, legacy, None)
            if exp is None:
                continue
            place({**req, name: str(legacy)},
                  [{"name": name, "expect": exp, "type": ctrl["type"],
                    "legacy": str(legacy), "maps_to": str(mapped)}])

    return variants


def cmd_plan(a) -> int:
    schema = SC.load_schema(SCHEMA_PATH)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "html").mkdir(exist_ok=True)

    owners = list(schema["elements"]) + list(schema["widgets"])
    if a.only:
        owners = [o for o in owners if o in a.only]

    plan = {"batches": [], "targets": {}}
    nodes: list[tuple[str, int, dict]] = []
    skipped: list = []
    n_base = n_rwd = n_legacy = 0

    for owner in owners:
        seed = RENDER_SEED.get(owner, {})
        for vi, v in enumerate(plan_owner(schema, owner, skipped)):
            node = SC.build_node(schema, owner, vi, {**seed, **v["assign"]})
            nodes.append((owner, vi, node))
            plan["targets"][f"{owner}#{vi}"] = {
                "owner": owner,
                "element_id": SC.elem_id(owner, vi),
                "targets": v["targets"],
            }
            for t in v["targets"]:
                if t.get("device"):
                    n_rwd += 1
                elif t.get("legacy"):
                    n_legacy += 1
                else:
                    n_base += 1

    plan["skipped"] = [{"owner": o, "control": c, "type": t, "reason": r}
                       for o, c, t, r in skipped]

    batches = [nodes[i:i + a.batch_size] for i in range(0, len(nodes), a.batch_size)]
    for bi, batch in enumerate(batches):
        tree, loose = [], []
        for owner, vi, node in batch:
            (tree if node["elType"] in ("container", "section") else loose).append(node)
        if loose:
            tree.append({"id": f"d{bi:06x}"[:7], "elType": "container",
                         "settings": {}, "elements": loose})
        f = out / f"batch-{bi:03d}.json"
        f.write_text(json.dumps(tree, ensure_ascii=False, indent=1), encoding="utf-8")
        plan["batches"].append({"file": f.name,
                                "keys": [f"{o}#{v}" for o, v, _ in batch]})

    (out / "plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")

    (out / "render.php").write_text("""<?php
/**
 * Render one post's Elementor content to HTML, through Elementor's own frontend.
 *
 * Not an HTTP request on purpose: no theme wrapper, no page cache, no CDN, no
 * chance of scoring a stale response. This is the same call Elementor makes when
 * it renders into the_content, so the wrapper classes are the real ones.
 */
if ( ! defined( 'ABSPATH' ) ) { exit( 1 ); }
$post_id = (int) $args[0];
echo \\Elementor\\Plugin::$instance->frontend->get_builder_content_for_display( $post_id );
""", encoding="utf-8", newline="\n")

    # Run this from the WordPress root. TOOLS and SWEEP are overridable so the
    # sweep can live somewhere writable (/tmp) instead of inside a live web root —
    # never drop scripts into a production document root just to run them.
    (out / "RUN.sh").write_text(f"""#!/bin/bash
# Apply every batch and capture the HTML Elementor RENDERS for it.
set -u
POST={a.post_id}
TOOLS=${{TOOLS:-tools}}
SWEEP=${{SWEEP:-{out.name}}}
mkdir -p "$SWEEP/html"

ok=0; fail=0
for f in "$SWEEP"/batch-*.json; do
  b=$(basename "$f" .json)
  rm -f "$SWEEP/html/$b.html"
  if wp eval-file "$TOOLS/apply-page.php" "$POST" "$f" > /dev/null 2>&1 \\
     && wp eval-file "$SWEEP/render.php" "$POST" > "$SWEEP/html/$b.html" 2>/dev/null \\
     && [ -s "$SWEEP/html/$b.html" ]; then
    ok=$((ok+1))
  else
    echo "FAILED: $b"; rm -f "$SWEEP/html/$b.html"; fail=$((fail+1))
  fi
done
echo "rendered $ok, failed $fail"
""", encoding="utf-8", newline="\n")

    total = sum(1 for o in owners
                for c in SC.controls_of(schema, o).values() if c.get("prefix_class"))
    print(f"owners                    {len(owners)}")
    print(f"variants                  {len(nodes)}")
    print(f"batches                   {len(batches)}")
    print()
    print(f"class-emitting controls   {total:,}")
    print(f"  will be asserted        {n_base:,}  ({100 * n_base / total:.1f}%)")
    print(f"  SKIPPED, untestable     {len(skipped):,}  ({100 * len(skipped) / total:.1f}%)")
    print(f"  + per-device prefixes   {n_rwd:,}  (elementor-TABLET-position-, not a _tablet suffix)")
    print(f"  + classes_dictionary    {n_legacy:,}  (legacy values that remap to a different class)")
    for reason, n in Counter(r for *_, r in skipped).most_common():
        print(f"      {n:5}  {reason}")
    print()
    print(f"  bash {out}/RUN.sh")
    print(f"  python tools/sweep-classes.py check {out} --out data/class-verification.csv")
    return 0


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------
WRAPPER = re.compile(r'<[a-zA-Z][^>]*\bdata-id="([0-9a-f]{7})"[^>]*>')
CLASSATTR = re.compile(r'\bclass="([^"]*)"')


def wrapper_classes(doc: str, el_id: str) -> set[str] | None:
    """The class list on the element whose data-id is el_id, or None if absent."""
    for m in WRAPPER.finditer(doc):
        if m.group(1) != el_id:
            continue
        cm = CLASSATTR.search(m.group(0))
        if not cm:
            return set()
        return set(html.unescape(cm.group(1)).split())
    return None


def cmd_check(a) -> int:
    sweep = Path(a.sweep)
    plan = json.loads((sweep / "plan.json").read_text(encoding="utf-8"))
    hdir = Path(a.html_dir) if a.html_dir else sweep / "html"

    rows: list[dict] = []
    missing_batches = []

    for b in plan["batches"]:
        f = hdir / (b["file"].replace(".json", ".html"))
        if not f.exists():
            missing_batches.append(b["file"])
            continue
        doc = f.read_text(encoding="utf-8", errors="replace")
        for key in b["keys"]:
            e = plan["targets"][key]
            classes = wrapper_classes(doc, e["element_id"])
            for t in e["targets"]:
                # A prefix_class is not always a prefix for ONE class. Two of them
                # carry a space and therefore emit two:
                #   'elementor-nav-menu--toggle elementor-nav-menu--' + 'burger'
                #     -> elementor-nav-menu--toggle  AND  elementor-nav-menu--burger
                # Treating the whole string as a single token fails a control that
                # is working perfectly. Split, and require every token.
                want = set(t["expect"].split())
                if classes is None:
                    status, note = "no-element", "the element renders nothing without site content"
                elif want <= classes:
                    status, note = "verified", ""
                else:
                    status = "FAILED"
                    absent = " ".join(sorted(want - classes))
                    note = f"expected class `{absent}` absent from the wrapper"
                rows.append({
                    "owner": e["owner"], "control": t["name"], "type": t["type"],
                    "device": t.get("device", ""), "legacy_value": t.get("legacy", ""),
                    "expected_class": t["expect"], "status": status, "note": note,
                })

    for s in plan.get("skipped", []):
        rows.append({"owner": s["owner"], "control": s["control"], "type": s["type"],
                     "device": "", "legacy_value": "", "expected_class": "",
                     "status": "skipped", "note": s["reason"]})

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["owner", "control", "type", "device",
                                          "legacy_value", "expected_class",
                                          "status", "note"])
        w.writeheader()
        w.writerows(rows)

    def bucket(pred):
        return [r for r in rows if pred(r)]

    base = bucket(lambda r: not r["device"] and not r["legacy_value"]
                  and r["status"] != "skipped")
    rwd = bucket(lambda r: r["device"])
    leg = bucket(lambda r: r["legacy_value"])
    skip = bucket(lambda r: r["status"] == "skipped")
    total = len(base) + len(skip)

    def line(label, sel, denom):
        n = len(sel)
        pct = f"  ({100 * n / denom:5.1f}%)" if denom else ""
        print(f"    {label:<24}{n:>7,}{pct}")

    ok = [r for r in base if r["status"] == "verified"]
    bad = [r for r in base if r["status"] == "FAILED"]
    dead = [r for r in base if r["status"] == "no-element"]

    print(f"CLASS-EMITTING CONTROLS  ({total:,})")
    line("verified by class", ok, total)
    line("FAILED", bad, total)
    line("host never rendered", dead, total)
    line("skipped, untested", skip, total)
    # Coverage counts only what was actually asserted. A control on a widget that
    # renders nothing was NOT tested, and rolling it into the pass rate would be
    # the exact dishonesty this sweep exists to remove.
    print(f"    {'covered':<24}{100 * len(ok) / total:>6.1f}%")
    print()
    print(f"PER-DEVICE CLASS PREFIXES  ({len(rwd):,})")
    line("verified", [r for r in rwd if r["status"] == "verified"], len(rwd))
    line("FAILED", [r for r in rwd if r["status"] == "FAILED"], len(rwd))
    print()
    print(f"classes_dictionary REMAPS  ({len(leg):,})")
    line("verified", [r for r in leg if r["status"] == "verified"], len(leg))
    line("FAILED", [r for r in leg if r["status"] == "FAILED"], len(leg))

    if dead:
        hosts = Counter(r["owner"] for r in dead)
        print()
        print(f"  NOT TESTED - {len(hosts)} widgets render no markup at all on a bare page,")
        print(f"  so there is no wrapper to carry a class ({len(dead):,} controls):")
        for owner, n in hosts.most_common():
            print(f"      {n:3}  {owner}")

    if missing_batches:
        print()
        print(f"  {len(missing_batches)} batch(es) produced no HTML and were NOT scored:")
        for f in missing_batches[:10]:
            print(f"      {f}")

    if bad:
        print()
        print(f"  {len(bad)} FAILURES:")
        for r in bad[:25]:
            dev = f"[{r['device']}]" if r["device"] else ""
            leg_s = f"(legacy {r['legacy_value']})" if r["legacy_value"] else ""
            print(f"      {r['owner']}.{r['control']}{dev}{leg_s}  {r['note']}")
    print()
    print(f"  written {out}")
    return 1 if bad or missing_batches else 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("plan")
    s.add_argument("--out", default="classsweep")
    s.add_argument("--batch-size", type=int, default=12)
    s.add_argument("--post-id", type=int, default=0)
    s.add_argument("--only", nargs="+")
    s.set_defaults(fn=cmd_plan)

    c = sub.add_parser("check")
    c.add_argument("sweep")
    c.add_argument("--html-dir")
    c.add_argument("--out", default="data/class-verification.csv")
    c.set_defaults(fn=cmd_check)

    a = p.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
