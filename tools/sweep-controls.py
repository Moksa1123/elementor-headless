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
          forbidden: set[str] | None = None) -> tuple[object, str | None] | None:
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
        v = stable_hex(owner, name)
        return v, v

    if t == "slider":
        # Percent/fr/custom units make the emitted string harder to predict;
        # px is the one we can assert exactly.
        size = stable_int(owner, name, lo=11, hi=989)
        if unit == "custom":
            return None
        return {"unit": unit, "size": size, "sizes": []}, f"{size}{unit}"

    if t == "dimensions":
        base = stable_int(owner, name, lo=11, hi=89)
        v = {"unit": unit, "top": str(base), "right": str(base + 1),
             "bottom": str(base + 2), "left": str(base + 3), "isLinked": False}
        if unit == "custom":
            return None
        return v, f"{base}{unit}"

    if t == "gaps":
        c = stable_int(owner, name, lo=11, hi=89)
        return ({"column": str(c), "row": str(c + 1), "isLinked": False, "unit": unit},
                f"{c}{unit}")

    if t == "box_shadow":
        col = stable_hex(owner, name)
        return ({"horizontal": 3, "vertical": 5, "blur": 7, "spread": 2, "color": col}, col)

    if t == "text_shadow":
        col = stable_hex(owner, name)
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
        n = stable_int(owner, name, lo=2, hi=9)
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
        return None

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

    if op in ("===", "==",):
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


def satisfy_conditions(node: dict, controls: dict[str, dict], owner: str) -> dict | None:
    """
    The advanced `conditions` form: a boolean tree with `relation` (and/or) and
    nested `terms`.

        text-editor.column_gap:
          or( text_columns > 1 , text_columns === "" )

    `and` needs every term; `or` needs the first term we can actually satisfy.
    """
    terms = node.get("terms") or []
    relation = (node.get("relation") or "and").lower()

    if relation == "or":
        for t in terms:
            got = (satisfy_conditions(t, controls, owner) if t.get("terms")
                   else satisfy_term(t, controls, owner))
            if got is not None:
                return got
        return None

    merged: dict = {}
    for t in terms:
        got = (satisfy_conditions(t, controls, owner) if t.get("terms")
               else satisfy_term(t, controls, owner))
        if got is None:
            return None
        for k, v in got.items():
            if k in merged and merged[k] != v:
                return None
            merged[k] = v
    return merged


def requirements(ctrl: dict, controls: dict[str, dict], owner: str,
                 depth: int = 0) -> dict | None:
    """
    The full assignment map needed for this control to take effect. THREE layers,
    and Elementor documents none of them together:

      condition    the simple form. A flat map, checked with equality/membership.
      conditions   the ADVANCED form: a boolean tree with and/or relations,
                   nested terms and comparison operators (>, !==, in, ...).
                   152 controls use it and nothing else. Ignore it and they look
                   dead when they are merely gated.
      needs_value  not a condition at all. The control's CSS interpolates another
                   control's value ({{background_color.VALUE}}), and Elementor
                   throws away the whole declaration if that value is empty -
                   even with every condition satisfied.

    Miss any one of the three and a control looks broken when it is merely lonely.
    """
    if depth > 6:
        return None
    req: dict = {}

    def add(key: str, val) -> bool:
        if key in req and req[key] != val:
            return False
        req[key] = val
        return True

    for dep, expected in (ctrl.get("condition") or {}).items():
        got = satisfy(dep, expected, controls, owner)
        if got is None:
            return None
        key, val = got
        if not add(key, val):
            return None
        sub = requirements(controls[key], controls, owner, depth + 1)
        if sub is None:
            return None
        for k, v in sub.items():
            if k in req and req[k] != v:
                return None
            req.setdefault(k, v)

    if ctrl.get("conditions"):
        got = satisfy_conditions(ctrl["conditions"], controls, owner)
        if got is None:
            return None
        for k, v in got.items():
            if not add(k, v):
                return None
            sub = requirements(controls[k], controls, owner, depth + 1)
            if sub is None:
                return None
            for kk, vv in sub.items():
                if kk in req and req[kk] != vv:
                    return None
                req.setdefault(kk, vv)

    for ref in ctrl.get("needs_value") or []:
        dep_ctrl = controls.get(ref)
        if dep_ctrl is None:
            continue          # references a control this widget does not have
        s = synth(owner, dep_ctrl)
        if s is None:
            return None       # cannot give it a value, so this control is untestable
        if not add(ref, s[0]):
            return None
        sub = requirements(dep_ctrl, controls, owner, depth + 1)
        if sub is None:
            return None
        for k, v in sub.items():
            if k in req and req[k] != v:
                return None
            req.setdefault(k, v)

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


def plan_owner(schema: dict, owner: str) -> list[dict]:
    """
    Partition this owner's assertable controls into variants whose condition
    requirements do not contradict each other.
    """
    controls = controls_of(schema, owner)
    variants: list[dict] = []

    targets = [c for c in controls.values() if c.get("css")]
    # Deterministic order so reruns produce identical pages.
    targets.sort(key=lambda c: c["name"])

    for ctrl in targets:
        s = synth(owner, ctrl)
        if s is None:
            continue
        value, expect = s
        req = requirements(ctrl, controls, owner)
        if req is None:
            continue  # unsatisfiable condition chain; recorded as skipped later
        if ctrl["name"] in req and req[ctrl["name"]] != value:
            continue  # the control is its own dependency at a different value

        placed = False
        for v in variants:
            merged = dict(v["assign"])
            ok = True
            for k, val in list(req.items()) + [(ctrl["name"], value)]:
                if k in merged and merged[k] != val:
                    ok = False
                    break
                merged[k] = val
            if ok:
                v["assign"] = merged
                v["targets"].append({"name": ctrl["name"], "expect": expect,
                                     "css": ctrl["css"], "type": ctrl["type"]})
                placed = True
                break
        if not placed:
            variants.append({
                "assign": {**req, ctrl["name"]: value},
                "targets": [{"name": ctrl["name"], "expect": expect,
                             "css": ctrl["css"], "type": ctrl["type"]}],
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

    for owner in owners:
        for vi, v in enumerate(plan_owner(schema, owner)):
            node = build_node(schema, owner, vi, v["assign"])
            nodes.append((owner, vi, node))
            key = f"{owner}#{vi}"
            plan["targets"][key] = {
                "owner": owner,
                "element_id": elem_id(owner, vi),
                "targets": v["targets"],
            }
            n_targets += len(v["targets"])

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

    print(f"owners        {len(owners)}")
    print(f"variants      {len(nodes)}  (controls whose conditions contradict "
          f"cannot share an element)")
    print(f"targets       {n_targets:,} controls to assert")
    print(f"batches       {len(batches)}  ({a.batch_size} variants per page)")
    print(f"written       {out}/")
    print()
    print("Now apply each batch and capture the CSS Elementor compiles:")
    print()
    print(f"  for f in {out}/batch-*.json; do")
    print(f"    wp eval-file tools/apply-page.php {a.post_id} \"$f\"")
    print(f"    cp wp-content/uploads/elementor/css/post-{a.post_id}.css \\")
    print(f"       {out}/css/$(basename \"$f\" .json).css")
    print(f"  done")
    print()
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


def cmd_check(a) -> int:
    sweep = Path(a.sweep)
    plan = json.loads((sweep / "plan.json").read_text(encoding="utf-8"))
    css_dir = Path(a.css_dir) if a.css_dir else sweep / "css"

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
            block = blocks_for_id(css, entry["element_id"])
            for t in entry["targets"]:
                prop_hit = any(
                    re.search(rf"(^|[;{{\s]){re.escape(p)}\s*:", block)
                    for p in t["css"]
                )
                if t["expect"] is None:
                    status = "property" if prop_hit else "FAIL"
                    detail = "" if prop_hit else "no CSS emitted for this control"
                else:
                    val_hit = t["expect"].lower() in block.lower()
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

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["owner", "control", "type", "css",
                                          "expected", "status", "detail"])
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["status"] != "FAIL", r["owner"], r["control"])))

    n = len(rows)
    ver = sum(1 for r in rows if r["status"] == "verified")
    prop = sum(1 for r in rows if r["status"] == "property")
    bad = sum(1 for r in rows if r["status"] == "FAIL")
    print(f"controls asserted     {n:,}")
    print(f"  verified by value   {ver:,}  ({100 * ver / n:.1f}%)  the exact value we wrote is in the CSS")
    print(f"  property only       {prop:,}  ({100 * prop / n:.1f}%)  right property, value not literally assertable")
    print(f"  FAILED              {bad:,}  ({100 * bad / n:.1f}%)  nothing came out")
    print()
    print(f"written: {out}")

    if bad:
        print()
        print("Top failures by owner:")
        from collections import Counter
        c = Counter(r["owner"] for r in rows if r["status"] == "FAIL")
        for o, k in c.most_common(12):
            print(f"   {o:26} {k}")
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
