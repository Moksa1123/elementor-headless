#!/usr/bin/env python3
"""
validate-page.py — check an Elementor page tree BEFORE you write it to the database.

    python tools/validate-page.py my-page.json
    python tools/validate-page.py my-page.json --target free   # fail on Pro-only controls

Elementor does not validate what you put in `_elementor_data`. It stores it, and
then it renders whatever it can make sense of. A misspelled control name, a
string where a dimensions object belongs, a Pro-only control on a Free site:
none of these raise an error. They just quietly do nothing, and you find out by
looking at the page and wondering why the padding did not apply.

This is the pre-flight that turns those silent no-ops into loud failures.

CHECKS
  ERROR   unknown elType / widgetType
  ERROR   duplicate element id (breaks the editor in ways that look like corruption)
  ERROR   missing `elements` array
  ERROR   control that does not exist on that widget
  ERROR   value whose JSON shape does not match the control's type
  ERROR   Pro-only control, when --target free
  WARN    Pro-only control, otherwise
  WARN    control whose `condition` is not satisfied by its siblings, so it will
          be ignored at render time even though it is spelled correctly
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "data" / "elementor-schema.json"

ID_RE = re.compile(r"^[0-9a-f]{6,8}$")

# What a value of each control type must look like. Only the types whose shape
# is a dict/list are worth checking - a `text` control accepts any string.
SHAPE_KEYS = {
    "dimensions": {"unit", "top", "right", "bottom", "left", "isLinked"},
    "slider": {"unit", "size", "sizes"},
    "box_shadow": {"horizontal", "vertical", "blur", "spread", "color"},
    "text_shadow": {"horizontal", "vertical", "blur", "color"},
    "url": {"url", "is_external", "nofollow", "custom_attributes"},
    "media": {"url", "id", "size"},
    "icons": {"value", "library"},
    "gaps": {"column", "row", "isLinked", "unit"},
    "image_dimensions": {"width", "height"},
}
LIST_TYPES = {"repeater", "gallery", "conditions_repeater", "form-fields-repeater",
              "nested-elements-repeater", "global-style-repeater", "fields_map", "wp_widget"}


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, where: str, msg: str) -> None:
        self.errors.append(f"{where}: {msg}")

    def warn(self, where: str, msg: str) -> None:
        self.warnings.append(f"{where}: {msg}")


def controls_for(schema: dict, el: dict) -> dict[str, dict] | None:
    """Every control legal on this node, common set included."""
    el_type = el.get("elType")
    if el_type == "widget":
        name = el.get("widgetType")
        w = schema["widgets"].get(name)
    else:
        name = el_type
        w = schema["elements"].get(name)
    if w is None:
        return None
    out = {c["name"]: c for c in w["controls"]}
    if w.get("has_common"):
        missing = set(w.get("common_missing", []))
        for c in schema["common_controls"]["controls"]:
            if c["name"] not in missing:
                out.setdefault(c["name"], c)
    return out


def base_control(name: str, controls: dict, breakpoints: list[str]) -> tuple[str, dict] | None:
    """Resolve `padding_tablet` back to `padding` so responsive keys validate."""
    if name in controls:
        return name, controls[name]
    for bp in breakpoints:
        suffix = f"_{bp}"
        if name.endswith(suffix):
            base = name[: -len(suffix)]
            if base in controls and bp in (controls[base].get("responsive") or []):
                return base, controls[base]
    return None


def check_shape(value, ctrl: dict, where: str, key: str, rep: Report) -> None:
    t = ctrl.get("type")
    if t in SHAPE_KEYS:
        if not isinstance(value, dict):
            rep.err(where, f"`{key}` is a `{t}` control: expected an object like "
                           f"{json.dumps({k: '' for k in sorted(SHAPE_KEYS[t])})}, got {type(value).__name__} "
                           f"{json.dumps(value, ensure_ascii=False)[:40]}")
            return
        unknown = set(value) - SHAPE_KEYS[t]
        if unknown:
            rep.warn(where, f"`{key}` has key(s) Elementor does not read: {sorted(unknown)}")
    elif t in LIST_TYPES:
        if not isinstance(value, list):
            rep.err(where, f"`{key}` is a `{t}` control: expected a list, got {type(value).__name__}")
    elif t == "switcher":
        rv = ctrl.get("return_value", "yes")
        if value not in (rv, "", None):
            rep.warn(where, f"`{key}` is a switcher: Elementor reads {rv!r} as on and '' as off, got {value!r}")
    elif t in ("select", "choose", "select2"):
        opts = ctrl.get("options")
        # PHP turns array keys that look like integers into ints, so a font-weight
        # option map comes out of json_encode as [100, 200, ...] while Elementor
        # itself stores the chosen value as the string "700". Compare as strings
        # or every numeric select produces a false error.
        if isinstance(opts, list) and opts and value not in (None, ""):
            allowed = {str(o) for o in opts}
            # `classes_dictionary` keys are legal values that are NOT in the option
            # list. They are the names this control used before Elementor moved to
            # logical properties, and the render path still maps them
            # (element-base.php:800) - `position: "top"` really does come out as
            # `elementor-position-block-start`. Rejecting them was a false error
            # that this validator shipped: it failed a page that renders correctly.
            legacy = {str(k): str(v) for k, v in (ctrl.get("classes_dictionary") or {}).items()}
            if str(value) in legacy and str(value) not in allowed:
                rep.warn(where, f"`{key}` = {value!r} is a legacy alias; Elementor "
                                f"remaps it to {legacy[str(value)]!r}. It works - the "
                                f"current name is {legacy[str(value)]!r}")
            elif str(value) not in allowed:
                rep.err(where, f"`{key}` = {value!r} is not one of its options: "
                               f"{sorted(allowed)}")

    units = ctrl.get("units")
    if units and isinstance(value, dict) and value.get("unit"):
        if value["unit"] not in units:
            rep.err(where, f"`{key}` unit {value['unit']!r} is not accepted by this control. "
                           f"Allowed: {units}")

    # A control that emits a CLASS rather than CSS has one value that behaves
    # differently in JSON than it does in the editor: zero.
    #
    #   element-base.php:809   if ( empty( $setting ) && '0' !== $setting ) continue;
    #
    # PHP's empty() is true for both 0 and "0", and the escape hatch is a STRICT
    # comparison against the string. So `"columns": "0"` emits `elementor-grid-0`
    # and `"columns": 0` emits nothing whatsoever. The editor only ever stores
    # strings, so this failure exists solely for anyone writing the JSON directly -
    # which is everyone using this skill.
    if ctrl.get("prefix_class") and value == 0 and not isinstance(value, bool):
        rep.err(where, f"`{key}` = 0 as a JSON number emits NO class. Elementor "
                       f"special-cases the STRING \"0\" only "
                       f"(`empty($v) && '0' !== $v`). Write \"0\".")


COND_RE = re.compile(r"^(?P<key>[^\[!]+)(?:\[(?P<sub>[^\]]+)\])?(?P<neg>!)?$")


def eval_condition(dep: str, expected, settings: dict, controls: dict):
    """
    Elementor's condition syntax, as it actually is:

        "background_background": ["classic", "gradient"]   plain equality / membership
        "typography_typography!": ""                       trailing ! means NOT equal
        "selected_icon[value]!": ""                        index into the value object

    Returns (True | False | None, human-readable detail). None means "cannot
    judge" - the dependency is not set in this element, so Elementor will fall
    back to the control's default and we would only be guessing.
    """
    m = COND_RE.match(dep)
    if not m:
        return None, dep
    key, sub, neg = m.group("key"), m.group("sub"), bool(m.group("neg"))

    if key in settings:
        got = settings[key]
    elif key in controls and "default" in controls[key]:
        got = controls[key]["default"]
    else:
        return None, dep

    if sub is not None:
        if not isinstance(got, dict):
            return None, dep
        got = got.get(sub, "")

    if isinstance(expected, list):
        hit = any(str(got) == str(e) for e in expected)
    else:
        hit = str(got) == str(expected)

    ok = (not hit) if neg else hit
    op = "!=" if neg else "=="
    shown = f"{key}[{sub}]" if sub else key
    return ok, f"{shown} {op} {expected!r} (you have {got!r})"


def compare(left, right, op: str) -> bool:
    """Elementor's operator table, verbatim (includes/conditions.php::compare)."""
    if op == "==":
        return str(left) == str(right)
    if op == "!=":
        return str(left) != str(right)
    if op == "!==":
        return left != right
    if op == "in":
        return left in (right or [])
    if op == "!in":
        return left not in (right or [])
    if op == "contains":
        return right in (left or [])
    if op == "!contains":
        return right not in (left or [])
    try:
        if op == "<":
            return float(left) < float(right)
        if op == "<=":
            return float(left) <= float(right)
        if op == ">":
            return float(left) > float(right)
        if op == ">=":
            return float(left) >= float(right)
    except (TypeError, ValueError):
        return False
    return left == right          # '===' and anything unrecognised


def eval_conditions(node: dict, settings: dict, controls: dict):
    """
    The advanced condition form: a boolean tree with `relation` (and/or) and
    nested `terms`. Returns True/False, or None when a term references a control
    we cannot resolve (in which case we do not guess).
    """
    terms = node.get("terms") or []
    relation = (node.get("relation") or "and").lower()
    results = []
    for t in terms:
        if t.get("terms"):
            r = eval_conditions(t, settings, controls)
        else:
            name = t["name"]
            base, _, sub = name.partition("[")
            sub = sub.rstrip("]")
            if base in settings:
                val = settings[base]
            elif base in controls and "default" in controls[base]:
                val = controls[base]["default"]
            else:
                val = None
            if sub and isinstance(val, dict):
                val = val.get(sub)
            r = compare(val, t.get("value"), t.get("operator") or "===")
        results.append(r)
    if not results:
        return None
    if relation == "or":
        return any(results)
    return all(results)


def describe_conditions(node: dict) -> str:
    terms = node.get("terms") or []
    rel = (node.get("relation") or "and").lower()
    parts = []
    for t in terms:
        if t.get("terms"):
            parts.append(f"({describe_conditions(t)})")
        else:
            parts.append(f"{t['name']} {t.get('operator') or '==='} {t.get('value')!r}")
    return f" {rel} ".join(parts)


def walk(nodes, schema, rep: Report, seen_ids: set, target: str,
         have: set, path="") -> None:
    breakpoints = [b for b, v in schema["breakpoints"].items()
                   if v.get("active") and v.get("suffix")]
    for i, el in enumerate(nodes):
        here = f"{path}[{i}]"
        el_id = el.get("id")
        if not el_id:
            rep.err(here, "no `id`")
        else:
            if el_id in seen_ids:
                rep.err(here, f"duplicate id {el_id!r} - the editor breaks on this in ways that look like data corruption")
            seen_ids.add(el_id)
            if not ID_RE.match(str(el_id)):
                rep.warn(here, f"id {el_id!r} is not the 7-char lowercase hex Elementor generates")

        if "elements" not in el:
            rep.err(here, "no `elements` array (use [] on leaf nodes - widgets need it too)")

        el_type = el.get("elType")
        if el_type not in ("container", "section", "column", "widget"):
            rep.err(here, f"elType {el_type!r} is not one of container/section/column/widget")
            continue
        if el_type == "widget" and not el.get("widgetType"):
            rep.err(here, "elType is 'widget' but there is no `widgetType`")
            continue

        label = el.get("widgetType") or el_type
        here = f"{here} {label}"

        controls = controls_for(schema, el)
        if controls is None:
            rep.err(here, f"no such {'widget' if el_type == 'widget' else 'element'} "
                          f"in the schema. `el.py widgets --grep {label}` to find the right name.")
            continue

        owner = (schema["widgets"] if el_type == "widget" else schema["elements"]).get(label, {})
        if owner.get("tier") == "pro":
            msg = f"widget `{label}` requires Elementor Pro"
            (rep.err if target == "free" else rep.warn)(here, msg)

        # Elementor Pro is not the only thing a widget can need. The surface is a
        # property of the INSTALL: WooCommerce contributes 29 widgets, and three
        # Elementor experiments contribute another 36. On a site without them the
        # widgetType simply does not resolve - the element vanishes, with no error.
        req = owner.get("requires")
        if req:
            if req.get("plugin"):
                need, kind = req["plugin"], "plugin"
            elif req.get("experiment"):
                need, kind = req["experiment"], "experiment"
            else:
                need, kind = None, "wp-widget"
            if kind == "wp-widget":
                rep.warn(here, f"`{label}` is a legacy WordPress widget that Elementor wraps. "
                               f"It exists only while some plugin registers it - it is not "
                               f"part of Elementor and may not be on the target site.")
            elif need.lower() in {h.lower() for h in have}:
                pass       # the caller told us the target site has it
            else:
                rep.err(here, f"`{label}` DOES NOT EXIST unless the {kind} `{need}` is active "
                              f"on the target site. Gate: {req.get('gate')}. "
                              f"Pass --have {need} if it is.")

        if owner.get("control_system") == "v4-atomic":
            rep.err(here, f"`{label}` is an Elementor V4 atomic element. It does not use "
                          f"`settings` + controls at all - it takes type-tagged props and a "
                          f"separate `styles` array. This validator models the classic tree "
                          f"and cannot check it. `el.py widget {label}` shows its prop schema.")
            continue

        settings = el.get("settings") or {}
        for key, value in settings.items():
            if key in ("__globals__", "__dynamic__"):
                continue  # global-value and dynamic-tag side-channels, not controls
            resolved = base_control(key, controls, breakpoints)
            if resolved is None:
                rep.err(here, f"`{key}` is not a control on {label}. "
                              f"Check: el.py widget {label} --grep {key.split('_')[0]}")
                continue
            base, ctrl = resolved
            # A responsive suffix Elementor promises and does not deliver. Measured
            # by rendering, not inferred: `hotspot.width` has is_responsive=true and
            # `width_tablet` emits no CSS at all, verified in isolation.
            if key != base:
                dev = key[len(base) + 1:]
                if dev in (ctrl.get("responsive_broken") or []):
                    rep.err(here, f"`{key}` looks legal - Elementor marks `{base}` responsive - "
                                  f"but rendering proves it emits no CSS at the {dev} "
                                  f"breakpoint on `{label}`. The key will be stored and "
                                  f"ignored. Style it at desktop, or use a different control.")
            if ctrl.get("tier") == "pro" and owner.get("tier") != "pro":
                msg = f"`{key}` is an Elementor PRO control on the free `{label}` widget"
                (rep.err if target == "free" else rep.warn)(here, msg)
            check_shape(value, ctrl, here, key, rep)

            cond = ctrl.get("condition")
            if cond:
                for dep, expected in cond.items():
                    ok, detail = eval_condition(dep, expected, settings, controls)
                    if ok is False:
                        rep.warn(here, f"`{key}` only applies when {detail} - "
                                       f"it will be stored and then ignored at render time")

            # The ADVANCED condition form. A separate mechanism with its own
            # syntax (and/or relations, nested terms, comparison operators), used
            # by 152 controls and by nothing else. A control gated only this way
            # has an empty `condition`, so checking `condition` alone reports it
            # as unconditional and lets a dead setting through.
            if ctrl.get("conditions"):
                ok = eval_conditions(ctrl["conditions"], settings, controls)
                if ok is False:
                    rep.warn(here, f"`{key}` is gated by an advanced condition that your "
                                   f"settings do not satisfy "
                                   f"({describe_conditions(ctrl['conditions'])}) - "
                                   f"it will be stored and then ignored at render time")

            # Not a condition at all: this control's CSS interpolates ANOTHER
            # control's value, and Elementor discards the entire declaration if
            # that value is empty - however satisfied the conditions are.
            for ref in ctrl.get("needs_value") or []:
                if ref in settings and settings[ref] not in ("", None, [], {}):
                    continue
                if ref in controls and controls[ref].get("default") not in (None, "", [], {}):
                    continue      # it has a non-empty default, so it is not empty
                rep.err(here, f"`{key}` builds its CSS out of `{ref}`, which you have not "
                              f"set. Elementor drops the whole declaration when an "
                              f"interpolated value is empty, so `{key}` will do nothing. "
                              f"Set `{ref}` too.")

        walk(el.get("elements") or [], schema, rep, seen_ids, target, have,
             path=f"{here}.elements")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("page", type=Path, help="JSON file holding the _elementor_data tree")
    ap.add_argument("--have", nargs="+", metavar="X", default=[],
                    help="things the TARGET site has that not every site does: a plugin "
                         "(woocommerce) or an Elementor experiment (nested-elements, "
                         "e_atomic_elements, container). Widgets that need something not "
                         "listed here are errors, because on that site they will not exist.")
    ap.add_argument("--target", choices=["free", "pro"], default="pro",
                    help="'free' turns every Pro-only usage into an error (default: pro)")
    a = ap.parse_args()

    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    tree = json.loads(a.page.read_text(encoding="utf-8"))
    if not isinstance(tree, list):
        sys.exit("The page must be a JSON list of top-level elements.")

    rep = Report()
    walk(tree, schema, rep, set(), a.target, set(a.have or []))

    m = schema["meta"]
    print(f"validating against Elementor {m['elementor_version']} / Pro {m['elementor_pro_version']}"
          f"   target={a.target}")
    print()
    for e in rep.errors:
        print(f"  ERROR  {e}")
    for w in rep.warnings:
        print(f"  WARN   {w}")
    if not rep.errors and not rep.warnings:
        print("  clean")
    print()
    print(f"{len(rep.errors)} error(s), {len(rep.warnings)} warning(s)")
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main())
