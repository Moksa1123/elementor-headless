#!/usr/bin/env python3
"""
sweep-controls.py — verify EVERY control in the schema by rendering it, one by one.

`verify-render.py` checks a page you wrote. This checks the whole schema: it
synthesises a legal value for every control that claims to drive CSS, solves the
condition chain needed to make that control take effect, writes the pages,
reads back the stylesheet Elementor compiled, and asserts the value came out.

    # 1. plan: generate the test pages
    python tools/sweep-controls.py plan --out sweep/

    # 2. apply each batch and capture the CSS Elementor compiles for it
    #    (see sweep/RUN.sh, generated for you)

    # 3. check: assert every control emitted what the schema promised
    python tools/sweep-controls.py check sweep/ --out data/control-verification.csv

WHY THIS IS HARD, AND WHY IT MATTERS

A control does not emit CSS just because you set it. 79% of them carry a
`condition` — `typography_font_size` does nothing unless `typography_typography`
is `"custom"` first; `flex_gap` does nothing unless `container_type` is `"flex"`.
So each control needs its dependency chain solved before it can be tested at all,
and controls whose dependencies contradict each other (flex vs grid) cannot share
an element and must be split across variants.

The assertion is per-VALUE, not per-property. Every control gets a value unique to
it — a distinct hex colour, a distinct pixel size — so "did `title_color` work?"
is answered by looking for that exact colour in the compiled CSS, not by noticing
that *something* set a `color`. Property-presence would pass on a page where the
wrong control happened to write the same property.

Failures here are the point. Every one is either a bug in the schema or a real
Elementor behaviour nobody wrote down.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "data" / "elementor-schema.json"

# Types we cannot synthesise a meaningful value for, or that carry no value.
SKIP_TYPES = {
    "repeater", "gallery", "wp_widget", "nested-elements-repeater",
    "form-fields-repeater", "conditions_repeater", "global-style-repeater",
    "global-style-switcher", "fields_map", "structure", "hidden",
    "media-preview", "v4_color_variable_list", "v4_typography_list",
    "template_query", "query", "date_time", "uc_mp3", "uc_hr",
    "uc_select_special", "image_dimensions",
}

COND_RE = re.compile(r"^(?P<key>[^\[!]+)(?:\[(?P<sub>[^\]]+)\])?(?P<neg>!)?$")


def stable_int(*parts: str, lo: int, hi: int) -> int:
    """Deterministic per-control number, so a rerun produces the same page."""
    h = hashlib.md5("::".join(parts).encode()).hexdigest()
    return lo + int(h[:8], 16) % (hi - lo + 1)


def stable_hex(*parts: str) -> str:
    """A colour unique to this control — that uniqueness IS the assertion."""
    h = hashlib.md5("::".join(parts).encode()).hexdigest()
    # Avoid pure black/white and keep every channel two hex digits.
    r = 0x30 + int(h[0:2], 16) % 0xC0
    g = 0x30 + int(h[2:4], 16) % 0xC0
    b = 0x30 + int(h[4:6], 16) % 0xC0
    return f"#{r:02X}{g:02X}{b:02X}"


def first_option(ctrl: dict, forbidden: set[str] | None = None) -> str | None:
    """
    Pick a usable option, skipping any the caller says are off-limits.

    `forbidden` matters more than it looks. `_border_color` is conditional on
    `_border_border! : ['', 'none']` — the border style must be neither empty NOR
    'none'. Taking "the first non-empty option" lands you on **'none'**, which is
    precisely one of the values that switches the border off, so the colour and
    width never emit and the control looks broken when it is not. A negated
    condition carrying a list is not "must be set"; it is "must avoid all of
    these".
    """
    forbidden = forbidden or set()
    opts = ctrl.get("options")
    if isinstance(opts, dict):        # truncated giant option list (fonts)
        opts = opts.get("sample") or []
    if isinstance(opts, list):
        return next((str(o) for o in opts
                     if str(o) != "" and str(o) not in forbidden), None)
    return None


MEDIA_URL = "https://example.com/eh-sweep-probe.png"


def synth(owner: str, ctrl: dict,
          forbidden: set[str] | None = None,
          device: str = "") -> tuple[object, str | None] | None:
    """
    A legal, distinctive value for this control.

    Returns (value, expected_css_fragment). The fragment is what we will look for
    in the compiled stylesheet; None means "we can only assert the property
    appeared, not which control put it there".
    """
    t = ctrl.get("type")
    name = ctrl["name"]
    if t in SKIP_TYPES:
        return None

    units = ctrl.get("units") or []
    unit = "px" if "px" in units else (units[0] if units else "px")

    if t == "color":
        v = stable_hex(owner, name, device)
        return v, v

    if t == "slider":
        # Percent/fr/custom units make the emitted string harder to predict;
        # px is the one we can assert exactly.
        size = stable_int(owner, name, device, lo=11, hi=989)
        if unit == "custom":
            return None
        return {"unit": unit, "size": size, "sizes": []}, f"{size}{unit}"

    if t == "dimensions":
        base = stable_int(owner, name, device, lo=11, hi=89)
        v = {"unit": unit, "top": str(base), "right": str(base + 1),
             "bottom": str(base + 2), "left": str(base + 3), "isLinked": False}
        if unit == "custom":
            return None
        return v, f"{base}{unit}"

    if t == "gaps":
        c = stable_int(owner, name, device, lo=11, hi=89)
        return ({"column": str(c), "row": str(c + 1), "isLinked": False, "unit": unit},
                f"{c}{unit}")

    if t == "box_shadow":
        col = stable_hex(owner, name, device)
        return ({"horizontal": 3, "vertical": 5, "blur": 7, "spread": 2, "color": col}, col)

    if t == "text_shadow":
        col = stable_hex(owner, name, device)
        return ({"horizontal": 3, "vertical": 5, "blur": 7, "color": col}, col)

    if t == "switcher":
        return ctrl.get("return_value", "yes"), None

    if t == "popover_toggle":
        return "custom", None

    if t in ("select", "select2", "choose", "visual_choice"):
        o = first_option(ctrl, forbidden)
        if o is None:
            return None
        # The option key is usually substituted straight into the declaration.
        return o, o

    if t == "font":
        return "Roboto", "Roboto"

    if t == "number":
        n = stable_int(owner, name, device, lo=2, hi=9)
        return n, str(n)

    if t in ("text", "textarea", "code", "wysiwyg", "raw_html"):
        return ("eh-sweep", None) if t != "wysiwyg" else ("<p>eh-sweep</p>", None)

    if t == "url":
        return {"url": "https://example.com/", "is_external": "",
                "nofollow": "", "custom_attributes": ""}, None

    if t == "media":
        # An empty url means `background-image: url("{{URL}}")` interpolates to
        # nothing, and Elementor drops the whole declaration. A media control
        # with no value is therefore untestable, not broken - give it one.
        # No attachment id is needed: the CSS reads the url straight out of the
        # setting.
        return {"url": MEDIA_URL, "id": "", "size": ""}, MEDIA_URL

    if t == "icons":
        return {"value": "fas fa-star", "library": "fa-solid"}, None

    if t in ("animation", "exit_animation", "hover_animation",
             "hover_animation_contact_buttons", "animation_menu_dropdown",
             "animation_slides_content"):
        o = first_option(ctrl)
        return (o, None) if o else None

    return None


def cond_holds(dep: str, expected, value) -> bool:
    """
    Does a value we have ALREADY assigned satisfy this condition?

    Without this check the solver reassigns dependencies it has already set. That
    is what manufactured most of the "contradictory chain" skips:
    `background_gradient_angle` requires `background_background = "gradient"`, then
    the solver recurses into its interpolated dependency `background_color`, whose
    own condition is `background_background in [classic, gradient, video]`, blindly
    takes the first option - "classic" - and declares the chain impossible. It was
    never impossible; "gradient" was already sitting there, satisfying it.
    """
    m = COND_RE.match(dep)
    if not m:
        return False
    sub, neg = m.group("sub"), bool(m.group("neg"))
    if sub is not None:
        if not isinstance(value, dict):
            return False
        value = value.get(sub, "")
    exp = expected if isinstance(expected, list) else [expected]
    hit = any(str(value) == str(e) for e in exp)
    return (not hit) if neg else hit


def satisfy(dep: str, expected, controls: dict[str, dict], owner: str):
    """
    What must be assigned so that `dep <op> expected` holds.

    Elementor's condition syntax, all three forms:
        "background_background": ["classic","gradient"]   membership
        "typography_typography!": ""                      trailing ! = must NOT equal
        "selected_icon[value]!": ""                       index into the value object

    Returns (key, value) or None if we cannot satisfy it.
    """
    m = COND_RE.match(dep)
    if not m:
        return None
    key, sub, neg = m.group("key"), m.group("sub"), bool(m.group("neg"))
    ctrl = controls.get(key)

    if ctrl is None:
        # The condition names a control this widget does not register. In the
        # EDITOR that makes the control permanently inert: is_control_visible
        # bails the moment `isset( $values[$key] )` fails
        # (controls-stack.php:1462). The button's `background_attachment` is the
        # classic victim - its Background group excludes the image field, yet
        # attachment/repeat/size/position are all still registered, conditioned on
        # `background_image[url]!`. There is no way to switch them on from the UI.
        #
        # Writing the data directly, we are not bound by what the editor can
        # produce: put the missing key into `settings` and isset() is satisfied.
        # Verified live, A/B on the button - without the key nothing is emitted,
        # with it background-attachment / -repeat / -size all appear.
        #
        # We do not know the missing control's type, so write the least thing that
        # makes the comparison pass.
        if sub is not None:
            return key, {sub: MEDIA_URL if sub == "url" else "eh-sweep"}
        if neg:
            return key, "eh-sweep"
        return key, (expected[0] if isinstance(expected, list) else expected)

    if not neg:
        want = expected[0] if isinstance(expected, list) else expected
        if sub:
            # e.g. grid_columns_grid[unit] == 'custom'
            s = synth(owner, ctrl)
            if not s or not isinstance(s[0], dict):
                return None
            val = dict(s[0])
            val[sub] = want
            return key, val
        if want == "":
            return key, ""
        return key, want

    # Negated: the dependency must avoid every value in `expected`. Usually that
    # is just "" ("must be set to something"), but not always - `_border_border!`
    # forbids BOTH '' and 'none', and picking 'none' silently switches the border
    # off while looking like a valid choice.
    forbidden = {str(e) for e in (expected if isinstance(expected, list) else [expected])}
    s = synth(owner, ctrl, forbidden=forbidden)
    if s is None:
        return None
    if sub:
        if not isinstance(s[0], dict):
            return None
        return key, s[0]        # its synthesised sub-values are non-empty already
    if str(s[0]) in forbidden:
        return None
    return key, s[0]


def term_holds(term: dict, req: dict) -> bool:
    """Is this leaf term already satisfied by what we have assigned?"""
    key = term["name"].split("[")[0]
    if key not in req:
        return False
    val = req[key]
    _, _, sub = term["name"].partition("[")
    sub = sub.rstrip("]")
    if sub and isinstance(val, dict):
        val = val.get(sub)
    op = term.get("operator") or "==="
    want = term.get("value")
    if op in ("===", "=="):
        return str(val) == str(want)
    if op in ("!==", "!="):
        return str(val) != str(want)
    if op == "in":
        return val in (want or [])
    if op == "!in":
        return val not in (want or [])
    try:
        if op == ">":
            return float(val) > float(want)
        if op == ">=":
            return float(val) >= float(want)
        if op == "<":
            return float(val) < float(want)
        if op == "<=":
            return float(val) <= float(want)
    except (TypeError, ValueError):
        return False
    return False


def satisfy_term(term: dict, controls: dict[str, dict], owner: str) -> dict | None:
    """
    One leaf of the ADVANCED condition form: {name, operator, value}.

    Operators are exactly Elementor's (includes/conditions.php::compare):
    ==, !=, !==, in, !in, contains, !contains, <, <=, >, >=, and === by default.
    """
    key = term["name"].split("[")[0]
    ctrl = controls.get(key)
    if ctrl is None:
        return None
    op = term.get("operator") or "==="
    want = term.get("value")

    if op in ("===", "=="):
        return {key: want}
    if op in ("!==", "!="):
        s = synth(owner, ctrl, forbidden={str(want)})
        return {key: s[0]} if s and str(s[0]) != str(want) else None
    if op == "in":
        return {key: want[0]} if isinstance(want, list) and want else None
    if op == "!in":
        s = synth(owner, ctrl, forbidden={str(w) for w in (want or [])})
        return {key: s[0]} if s else None
    if op in (">", ">="):
        try:
            n = int(want) + (1 if op == ">" else 0)
        except (TypeError, ValueError):
            return None
        return {key: n}
    if op in ("<", "<="):
        try:
            n = int(want) - (1 if op == "<" else 0)
        except (TypeError, ValueError):
            return None
        return {key: n} if n >= 0 else None
    return None      # contains/!contains operate on lists we do not synthesise


def satisfy_conditions(node: dict, controls: dict[str, dict], owner: str,
                       req: dict) -> dict | None:
    """
    The advanced `conditions` form: a boolean tree with `relation` (and/or) and
    nested `terms`.

        text-editor.column_gap:
          or( text_columns > 1 , text_columns === "" )

    `req` is what has already been assigned. A term it already satisfies costs
    nothing, and a term that would contradict it is not an option - so `or` picks
    the first term that is either already true or can be made true without
    fighting an existing assignment.
    """
    terms = node.get("terms") or []
    relation = (node.get("relation") or "and").lower()

    def one(t):
        if t.get("terms"):
            return satisfy_conditions(t, controls, owner, req)
        if term_holds(t, req):
            return {}                       # already true; assign nothing
        got = satisfy_term(t, controls, owner)
        if got is None:
            return None
        for k, v in got.items():            # would it contradict what we have?
            if k in req and req[k] != v:
                return None
        return got

    if relation == "or":
        for t in terms:
            got = one(t)
            if got is not None:
                return got
        return None

    merged: dict = {}
    for t in terms:
        got = one(t)
        if got is None:
            return None
        for k, v in got.items():
            if k in merged and merged[k] != v:
                return None
            merged[k] = v
    return merged


def requirements(ctrl: dict, controls: dict[str, dict], owner: str,
                 depth: int = 0, req: dict | None = None) -> dict | None:
    """
    The full assignment map needed for this control to take effect. THREE layers,
    and Elementor documents none of them together:

      condition    the simple form. A flat map, checked with equality/membership.
      conditions   the ADVANCED form: a boolean tree with and/or relations, nested
                   terms and comparison operators (>, !==, in, ...). 152 controls
                   use it and nothing else. Ignore it and they look dead when they
                   are merely gated.
      needs_value  not a condition at all. The control's CSS interpolates another
                   control's value ({{background_color.VALUE}}), and Elementor
                   throws away the whole declaration if that value is empty - even
                   with every condition satisfied.

    `req` is threaded through the recursion rather than rebuilt at each level, and
    a dependency that is ALREADY satisfied is left alone. Rebuilding it was the bug
    that made 1,530 controls look untestable: `background_gradient_angle` pins
    `background_background = "gradient"`, then the recursion into its interpolated
    dependency `background_color` met that control's own condition
    (`background_background in [classic, gradient, video]`), blindly took the first
    option — "classic" — and declared the chain contradictory. Nothing was
    contradictory; "gradient" already satisfied it.
    """
    if req is None:
        req = {}
    if depth > 8:
        return None

    def pin(key: str, val, dep_ctrl: dict | None) -> bool:
        """Assign, then satisfy that dependency's own requirements too."""
        if key in req:
            return req[key] == val
        req[key] = val
        if dep_ctrl is not None:
            return requirements(dep_ctrl, controls, owner, depth + 1, req) is not None
        return True

    for dep, expected in (ctrl.get("condition") or {}).items():
        m = COND_RE.match(dep)
        key = m.group("key") if m else None
        if key and key in req:
            # Already assigned. Keep it if it satisfies; otherwise this control
            # genuinely cannot coexist with what we have, and belongs in a
            # different variant.
            if not cond_holds(dep, expected, req[key]):
                return None
            continue
        got = satisfy(dep, expected, controls, owner)
        if got is None:
            return None
        k, v = got
        if not pin(k, v, controls.get(k)):
            return None

    if ctrl.get("conditions"):
        got = satisfy_conditions(ctrl["conditions"], controls, owner, req)
        if got is None:
            return None
        for k, v in got.items():
            if not pin(k, v, controls.get(k)):
                return None

    for ref in ctrl.get("needs_value") or []:
        if ref in req:
            continue
        dep_ctrl = controls.get(ref)
        if dep_ctrl is None:
            continue          # references a control this widget does not have
        s = synth(owner, dep_ctrl)
        if s is None:
            return None       # cannot give it a value, so this control is untestable
        if not pin(ref, s[0], dep_ctrl):
            return None

    return req


def controls_of(schema: dict, owner: str) -> dict[str, dict]:
    src = schema["widgets"].get(owner) or schema["elements"].get(owner)
    out = {c["name"]: c for c in src["controls"]}
    if src.get("has_common"):
        missing = set(src.get("common_missing", []))
        for c in schema["common_controls"]["controls"]:
            if c["name"] not in missing:
                out.setdefault(c["name"], c)
    return out


def plan_owner(schema: dict, owner: str, skipped: list,
               responsive: bool = True) -> list[dict]:
    """
    Partition this owner's assertable controls into variants whose dependency
    requirements do not contradict each other.

    Anything we cannot test is appended to `skipped` WITH A REASON. A sweep that
    quietly drops the controls it cannot handle and then reports "0 failures" is
    lying by omission - the number that matters is coverage, and coverage is only
    meaningful next to the list of what was left out.
    """
    controls = controls_of(schema, owner)
    variants: list[dict] = []

    targets = [c for c in controls.values() if c.get("css")]
    # Deterministic order so reruns produce identical pages.
    targets.sort(key=lambda c: c["name"])

    for ctrl in targets:
        s = synth(owner, ctrl)
        if s is None:
            skipped.append((owner, ctrl["name"], ctrl["type"],
                            f"no value can be synthesised for a `{ctrl['type']}` control"))
            continue
        value, expect = s
        req = requirements(ctrl, controls, owner)
        if req is None:
            skipped.append((owner, ctrl["name"], ctrl["type"],
                            "its dependency chain cannot be satisfied "
                            "(contradictory, or a dependency we cannot synthesise)"))
            continue
        if ctrl["name"] in req and req[ctrl["name"]] != value:
            skipped.append((owner, ctrl["name"], ctrl["type"],
                            "the control is its own dependency at a different value"))
            continue

        # RESPONSIVE. `padding_tablet` has no control object anywhere in Elementor's
        # stack - it is resolved at render time by looking up "{control}_{device}"
        # in the saved settings. So the ONLY way to know a suffix works is to write
        # it and check the compiled CSS for a media query. Give each device its own
        # distinct value, so a pass proves that suffix produced that value at that
        # breakpoint, rather than the desktop value leaking through.
        extra: dict = {}
        rwd_targets: list[dict] = []
        if responsive:
            for dev in ctrl.get("responsive") or []:
                ds = synth(owner, ctrl, device=dev)
                if ds is None:
                    continue
                extra[f"{ctrl['name']}_{dev}"] = ds[0]

                # An interpolated dependency that is ITSELF responsive must be set
                # at THIS breakpoint too. Elementor resolves
                # `{{_background_color_stop.SIZE}}` inside the tablet rule by
                # looking up `_background_color_stop_tablet`; if that key is empty
                # the placeholder resolves to nothing and the whole tablet rule is
                # thrown away - while desktop renders perfectly.
                #
                # So a responsive gradient with a non-responsive colour works, and
                # the same gradient silently vanishes on tablet because a *stop*
                # (which is responsive) was only set for desktop. This is the
                # needs_value trap again, one level deeper, and it is why the
                # responsive sweep exists rather than trusting the desktop pass.
                for ref in ctrl.get("needs_value") or []:
                    dep = controls.get(ref)
                    if not dep or dev not in (dep.get("responsive") or []):
                        continue
                    dsub = synth(owner, dep, device=dev)
                    if dsub is not None:
                        extra.setdefault(f"{ref}_{dev}", dsub[0])

                rwd_targets.append({"name": f"{ctrl['name']}_{dev}", "expect": ds[1],
                                    "css": ctrl["css"], "type": ctrl["type"],
                                    "device": dev, "base": ctrl["name"]})

        placed = False
        for v in variants:
            merged = dict(v["assign"])
            ok = True
            for k, val in list(req.items()) + [(ctrl["name"], value)] + list(extra.items()):
                if k in merged and merged[k] != val:
                    ok = False
                    break
                merged[k] = val
            if ok:
                v["assign"] = merged
                v["targets"].append({"name": ctrl["name"], "expect": expect,
                                     "css": ctrl["css"], "type": ctrl["type"]})
                v["targets"].extend(rwd_targets)
                placed = True
                break
        if not placed:
            variants.append({
                "assign": {**req, ctrl["name"]: value, **extra},
                "targets": [{"name": ctrl["name"], "expect": expect,
                             "css": ctrl["css"], "type": ctrl["type"]}] + rwd_targets,
            })
    return variants


def elem_id(owner: str, vi: int) -> str:
    return hashlib.md5(f"{owner}#{vi}".encode()).hexdigest()[:7]


def build_node(schema: dict, owner: str, vi: int, assign: dict) -> dict:
    """Wrap one variant's settings in whatever element structure it needs."""
    eid = elem_id(owner, vi)
    if owner in schema["elements"]:
        if owner == "container":
            return {"id": eid, "elType": "container", "settings": assign, "elements": []}
        if owner == "section":
            return {"id": eid, "elType": "section", "settings": assign,
                    "elements": [{"id": eid[:6] + "f", "elType": "column",
                                  "settings": {"_column_size": 100}, "elements": []}]}
        if owner == "column":
            # A column is only legal inside a section.
            return {"id": eid[:6] + "e", "elType": "section", "settings": {},
                    "elements": [{"id": eid, "elType": "column",
                                  "settings": {**assign, "_column_size": 100},
                                  "elements": []}]}
    return {"id": eid, "elType": "widget", "widgetType": owner,
            "settings": assign, "elements": []}


def cmd_plan(a) -> int:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "css").mkdir(exist_ok=True)

    owners = list(schema["elements"]) + list(schema["widgets"])
    if a.only:
        owners = [o for o in owners if o in a.only]

    plan = {"batches": [], "targets": {}}
    nodes: list[tuple[str, int, dict]] = []
    n_targets = 0
    skipped: list = []

    for owner in owners:
        for vi, v in enumerate(plan_owner(schema, owner, skipped)):
            node = build_node(schema, owner, vi, v["assign"])
            nodes.append((owner, vi, node))
            key = f"{owner}#{vi}"
            plan["targets"][key] = {
                "owner": owner,
                "element_id": elem_id(owner, vi),
                "targets": v["targets"],
            }
            n_targets += len(v["targets"])

    plan["skipped"] = [
        {"owner": o, "control": c, "type": t, "reason": r} for o, c, t, r in skipped
    ]

    # Pack variants into pages. Each page is one apply + one CSS read.
    batches = [nodes[i:i + a.batch_size] for i in range(0, len(nodes), a.batch_size)]
    for bi, batch in enumerate(batches):
        tree = []
        loose: list[dict] = []
        for owner, vi, node in batch:
            if node["elType"] in ("container", "section"):
                tree.append(node)
            else:
                loose.append(node)
        if loose:
            tree.append({"id": f"c{bi:06x}"[:7], "elType": "container",
                         "settings": {}, "elements": loose})
        f = out / f"batch-{bi:03d}.json"
        f.write_text(json.dumps(tree, ensure_ascii=False, indent=1), encoding="utf-8")
        plan["batches"].append({
            "file": f.name,
            "keys": [f"{o}#{v}" for o, v, _ in batch],
        })

    (out / "plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")

    # The runner, written out rather than described. It deletes the CSS file
    # before each apply on purpose: a batch that fatals must leave NO css behind,
    # otherwise the previous batch's stylesheet is still sitting there and every
    # control in the failed batch gets silently scored against the wrong CSS.
    run = out / "RUN.sh"
    run.write_text(f"""#!/bin/bash
# Apply every sweep batch and capture the CSS Elementor compiles for it.
# Run this from the WordPress root, with tools/ reachable.
set -u
POST={a.post_id}
SWEEP={out.name}
CSS=wp-content/uploads/elementor/css/post-$POST.css

ok=0; fail=0
for f in "$SWEEP"/batch-*.json; do
  b=$(basename "$f" .json)
  rm -f "$CSS"
  if wp eval-file tools/apply-page.php "$POST" "$f" > /dev/null 2>&1 && [ -f "$CSS" ]; then
    cp "$CSS" "$SWEEP/css/$b.css"; ok=$((ok+1))
  else
    echo "FAILED: $b"; fail=$((fail+1))
  fi
done
echo "applied $ok, failed $fail"
echo "now: python tools/sweep-controls.py check $SWEEP --out data/control-verification.csv"
""", encoding="utf-8")

    # Coverage, stated honestly. A sweep that only reports what it managed to test
    # can claim any pass rate it likes.
    total_css = sum(
        1 for o in owners
        for c in controls_of(schema, o).values() if c.get("css")
    )
    print(f"owners        {len(owners)}")
    print(f"variants      {len(nodes)}  (controls whose dependencies contradict "
          f"cannot share an element)")
    print(f"batches       {len(batches)}  ({a.batch_size} variants per page)")
    print()
    n_base = sum(1 for e in plan["targets"].values()
                 for t in e["targets"] if not t.get("device"))
    n_rwd = n_targets - n_base
    print(f"CSS-driving controls   {total_css:,}")
    print(f"  will be asserted     {n_base:,}  ({100 * n_base / total_css:.1f}%)")
    print(f"  SKIPPED, untestable  {len(skipped):,}  ({100 * len(skipped) / total_css:.1f}%)")
    if n_rwd:
        print(f"  + responsive suffixes {n_rwd:,}  (_tablet / _mobile keys, each asserted")
        print(f"                        inside ITS breakpoint's media query, with a value")
        print(f"                        distinct from desktop's so a leak cannot pass)")
    if skipped:
        from collections import Counter
        for reason, n in Counter(r for *_, r in skipped).most_common():
            print(f"      {n:5}  {reason}")
        print(f"  (every one is listed in {out.name}/plan.json under `skipped`, and in")
        print(f"   the report from `check`, so coverage is never quietly overstated)")
    print()
    print(f"written       {out}/  (+ RUN.sh)")
    print()
    if not a.post_id:
        print("NOTE: no --post-id given, so RUN.sh has POST=0. Point it at a DRAFT post;")
        print("      the sweep overwrites that post's content 1 batch at a time.")
        print()
    print(f"  bash {run}                                    # apply + capture CSS")
    print(f"  python tools/sweep-controls.py check {out} --out data/control-verification.csv")
    return 0


def blocks_for_id(css: str, el_id: str) -> str:
    """
    Every declaration block whose selector names this element.

    Brace-aware on purpose. The naive `[^{}]*` body pattern breaks on real
    Elementor output, because Elementor can emit a literal, UNEXPANDED
    placeholder into the compiled stylesheet:

        .elementor-element-0994e53 .elementor-counter-number-wrapper{
            text-align:{{VALUE}};      <- invalid CSS, straight from Elementor
            gap:245px;                 <- our value, right there after it
        }

    Observed on the `counter` widget, Elementor 4.1.4. The stray braces made a
    naive parser stop mid-rule and report `gap` as never emitted - a false
    failure that looked exactly like a schema bug. Count the braces instead.
    """
    out = []
    i = 0
    n = len(css)
    while i < n:
        j = css.find("{", i)
        if j < 0:
            break
        selector = css[i:j]
        depth, k = 1, j + 1
        while k < n and depth:
            if css[k] == "{":
                depth += 1
            elif css[k] == "}":
                depth -= 1
            k += 1
        body = css[j + 1:k - 1]
        # An @media wrapper's "body" is itself rules; recurse into it.
        if selector.strip().startswith("@"):
            out.append(blocks_for_id(body, el_id))
        elif f"elementor-element-{el_id}" in selector:
            out.append(body)
        i = k
    return " ".join(out)


def blocks_by_media(css: str, el_id: str) -> dict[str, str]:
    """
    This element's declaration blocks, keyed by media query ("" = base rules).

    Responsive assertions live or die on this separation. `padding_tablet` is only
    proven if its value lands inside `@media(max-width:1024px)` - finding it in the
    base rules would mean the desktop value leaked, which is the exact bug the
    assertion exists to catch.
    """
    out: dict[str, str] = {}
    i, n = 0, len(css)
    while i < n:
        j = css.find("{", i)
        if j < 0:
            break
        selector = css[i:j]
        depth, k = 1, j + 1
        while k < n and depth:
            if css[k] == "{":
                depth += 1
            elif css[k] == "}":
                depth -= 1
            k += 1
        body = css[j + 1:k - 1]
        if selector.strip().startswith("@"):
            query = selector.strip().lstrip("@media").strip().replace(" ", "")
            inner = blocks_by_media(body, el_id)
            if inner.get(""):
                out[query] = out.get(query, "") + " " + inner[""]
        elif f"elementor-element-{el_id}" in selector:
            out[""] = out.get("", "") + " " + body
        i = k
    return out


def declarations(block: str) -> list[tuple[str, str]]:
    """
    (property, value) pairs from a declaration block.

    Splitting on ';' is not enough: a value can legitimately contain one, inside
    url(...) or a data: URI. Track parenthesis depth.
    """
    out, buf, depth = [], [], 0
    for ch in block:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == ";" and depth == 0:
            decl = "".join(buf)
            buf = []
            if ":" in decl:
                p, _, v = decl.partition(":")
                out.append((p.strip(), v.strip()))
            continue
        buf.append(ch)
    decl = "".join(buf)
    if ":" in decl:
        p, _, v = decl.partition(":")
        out.append((p.strip(), v.strip()))
    return out


def cmd_check(a) -> int:
    sweep = Path(a.sweep)
    plan = json.loads((sweep / "plan.json").read_text(encoding="utf-8"))
    css_dir = Path(a.css_dir) if a.css_dir else sweep / "css"

    sch = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    breakpoints = {b: v for b, v in sch["breakpoints"].items()
                   if v.get("active") and v.get("suffix")}

    rows = []
    missing_css = []
    for batch in plan["batches"]:
        cssf = css_dir / (Path(batch["file"]).stem + ".css")
        if not cssf.exists():
            missing_css.append(cssf.name)
            continue
        css = cssf.read_text(encoding="utf-8")
        for key in batch["keys"]:
            entry = plan["targets"][key]
            by_media = blocks_by_media(css, entry["element_id"])
            base_decls = declarations(by_media.get("", ""))
            for t in entry["targets"]:
                dev = t.get("device")
                if dev:
                    # A device-suffixed key must land in THAT breakpoint's query.
                    # Its value is seeded with the device, so it differs from the
                    # desktop value - a desktop value leaking down would NOT pass
                    # here, which is the whole point of the assertion.
                    bp = breakpoints.get(dev, {})
                    want = f"{bp.get('direction', 'max')}-width:{bp.get('value')}px"
                    decls = declarations(" ".join(
                        body for q, body in by_media.items() if want in q
                    ))
                else:
                    # Desktop is the base rules PLUS any min-width query: Elementor
                    # emits the desktop value of some responsive controls
                    # desktop-first (the container's `boxed_width` lands in
                    # `@media(min-width:768px)`, not in the base block). It is not
                    # searched in the max-width queries - that is where the tablet
                    # and mobile values live, and they are different values.
                    decls = base_decls + declarations(" ".join(
                        body for q, body in by_media.items() if "min-width" in q
                    ))
                # The values of just this control's own declarations. Asserting
                # inside them - rather than anywhere in the element's CSS - is what
                # makes a pass mean "THIS control wrote THIS value" instead of
                # "someone wrote something that looks similar".
                mine = [v for p, v in decls if p in t["css"]]
                prop_hit = bool(mine)

                if t["expect"] is None:
                    status = "property" if prop_hit else "FAIL"
                    detail = "" if prop_hit else "no CSS emitted for this control"
                else:
                    hay = " ".join(mine).lower()
                    want = t["expect"].lower()
                    val_hit = want in hay
                    if not val_hit:
                        # A selector may interpolate {{SIZE}} without {{UNIT}}
                        # (`opacity: {{SIZE}}`), so the unit we wrote never reaches
                        # the CSS. Fall back to the bare magnitude, which is still
                        # unique to this control.
                        m = re.match(r"^(\d+)[a-z%]*$", want)
                        if m and re.search(rf"(^|[^\d.]){m.group(1)}([^\d]|$)", hay):
                            val_hit = True
                    if val_hit:
                        status = "verified"
                        detail = ""
                    elif prop_hit:
                        status = "property"
                        detail = f"property present but not the value {t['expect']!r}"
                    else:
                        status = "FAIL"
                        detail = "no CSS emitted for this control"
                rows.append({
                    "owner": entry["owner"],
                    "control": t["name"],
                    "device": t.get("device", ""),
                    "type": t["type"],
                    "css": "|".join(t["css"]),
                    "expected": t["expect"] or "",
                    "status": status,
                    "detail": detail,
                })

    if missing_css:
        print(f"WARNING: {len(missing_css)} batch(es) have no CSS captured "
              f"({', '.join(missing_css[:4])}...). Their controls are not counted.")
        print()

    # The controls the planner could not test go into the SAME file, marked
    # `skipped`. Anyone reading control-verification.csv then sees the untested
    # ones next to the passing ones, instead of having to know to go looking.
    for s in plan.get("skipped", []):
        rows.append({
            "owner": s["owner"], "control": s["control"], "device": "",
            "type": s["type"], "css": "", "expected": "", "status": "skipped",
            "detail": s["reason"],
        })

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    order = {"FAIL": 0, "skipped": 1, "property": 2, "verified": 3}
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["owner", "control", "device", "type",
                                          "css", "expected", "status", "detail"])
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (order.get(r["status"], 9),
                                                r["owner"], r["control"])))

    def tally(rs):
        return (sum(1 for r in rs if r["status"] == "verified"),
                sum(1 for r in rs if r["status"] == "property"),
                sum(1 for r in rs if r["status"] == "FAIL"),
                sum(1 for r in rs if r["status"] == "skipped"))

    base = [r for r in rows if not r.get("device")]
    rwd = [r for r in rows if r.get("device")]

    ver, prop, bad, skip = tally(base)
    n = len(base)
    print(f"DESKTOP  ({n:,} CSS-driving controls)")
    print(f"  verified by value   {ver:,}  ({100 * ver / n:.1f}%)  the exact value we wrote is in the CSS")
    print(f"  property only       {prop:,}  ({100 * prop / n:.1f}%)  right property, value not literally assertable")
    print(f"  FAILED              {bad:,}  ({100 * bad / n:.1f}%)  nothing came out")
    print(f"  skipped, untested   {skip:,}  ({100 * skip / n:.1f}%)  the planner could not build a test for these")
    print(f"  covered             {100 * (ver + prop) / n:.1f}%")

    if rwd:
        from collections import Counter
        rver, rprop, rbad, _ = tally(rwd)
        rn = len(rwd)
        print()
        print(f"RESPONSIVE SUFFIXES  ({rn:,} _tablet / _mobile keys)")
        print(f"  landed in the right media query, with the right value:")
        print(f"    verified by value {rver:,}  ({100 * rver / rn:.1f}%)")
        print(f"    property only     {rprop:,}  ({100 * rprop / rn:.1f}%)")
        print(f"    FAILED            {rbad:,}  ({100 * rbad / rn:.1f}%)")
        for dev, k in Counter(r["device"] for r in rwd).most_common():
            dv = [r for r in rwd if r["device"] == dev]
            ok = sum(1 for r in dv if r["status"] in ("verified", "property"))
            print(f"      _{dev:<8} {ok:,}/{k:,}")
    print()
    print(f"written: {out}")

    from collections import Counter
    if bad:
        print()
        print("Failures by owner:")
        for o, k in Counter(r["owner"] for r in rows if r["status"] == "FAIL").most_common(12):
            print(f"   {o:26} {k}")
    if skip:
        print()
        print("Skipped, by reason:")
        for reason, k in Counter(r["detail"] for r in rows
                                 if r["status"] == "skipped").most_common():
            print(f"   {k:5}  {reason}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("plan", help="generate the test pages")
    s.add_argument("--out", default="sweep")
    s.add_argument("--batch-size", type=int, default=10)
    s.add_argument("--post-id", type=int, default=0, help="the draft post to write batches into")
    s.add_argument("--only", nargs="+", help="restrict to these owners")
    s.set_defaults(fn=cmd_plan)

    s = sub.add_parser("check", help="assert every control emitted its CSS")
    s.add_argument("sweep")
    s.add_argument("--css-dir")
    s.add_argument("--out", default="data/control-verification.csv")
    s.set_defaults(fn=cmd_check)

    a = p.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
