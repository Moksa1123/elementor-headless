#!/usr/bin/env python3
"""
el.py — keyword lookup into the Elementor schema. This is the skill's front door.

The point is token economy. data/elementor-schema.json holds every control of
every widget (~4.8 MB, roughly 1.08M tokens). No agent should ever read it. Ask
it a question instead and get back the few lines that actually answer it:

    python tools/el.py widget heading --tab style     # style controls of one widget
    python tools/el.py container --tab layout         # the container's layout surface
    python tools/el.py search padding                 # where does padding live?
    python tools/el.py css border-radius              # which control drives this CSS prop?
    python tools/el.py type slider                    # what JSON shape does a slider take?
    python tools/el.py group typography               # what fields does a group control expand to?
    python tools/el.py common --section _section_background
    python tools/el.py widgets --tier pro --grep form
    python tools/el.py skeleton                       # a valid, minimal page tree
    python tools/el.py breakpoints

Every command takes --json for machine-readable output. Free/Pro tier is printed
on everything that has one, because mixing them up ships a page that renders on
your machine and breaks on a Free install.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA_PATH = HERE.parent / "data" / "elementor-schema.json"

_schema: dict | None = None


def schema() -> dict:
    global _schema
    if _schema is None:
        if not SCHEMA_PATH.exists():
            sys.exit(
                f"Missing {SCHEMA_PATH}.\n"
                "Regenerate it:\n"
                "  wp eval-file tools/extract-elementor-schema.php core+pro > raw.json\n"
                "  python tools/build-indexes.py raw.json --out data/"
            )
        _schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return _schema


def owners() -> dict:
    """Elements and widgets in one lookup table — both can own controls."""
    s = schema()
    return {**s["elements"], **s["widgets"]}


def emit(obj, as_json: bool, lines: list[str]) -> None:
    if as_json:
        print(json.dumps(obj, ensure_ascii=False, indent=2))
    else:
        print("\n".join(lines))


def tier_tag(t: str) -> str:
    return {"free": "FREE", "pro": "PRO ", "third-party": "3RD "}.get(t, "?   ")


def fmt_control(c: dict, indent: str = "  ") -> str:
    # The PRO marker is the most important thing on this line. A Pro-only
    # control on a free widget is the classic silent failure: it saves, it
    # renders for you, and it does nothing on a site without Pro.
    mark = "PRO " if c.get("tier") == "pro" else "    "
    bits = [f"{indent}{mark}{c['name']:<30} {c['type']:<14}"]
    if c.get("responsive"):
        # `responsive` is what Elementor's is_responsive flag CLAIMS.
        # `responsive_broken` is what rendering the page proved it does not do.
        broken = c.get("responsive_broken") or []
        works = [d for d in c["responsive"] if d not in broken]
        if works:
            bits.append("rwd:" + ",".join(works))
        if broken:
            bits.append("rwd-BROKEN:" + ",".join(broken)
                        + " (Elementor claims the suffix; it emits nothing)")
    if c.get("options"):
        o = c["options"]
        if isinstance(o, dict) and "__truncated__" in o:
            opts = f"{o['__truncated__']} options"
        else:
            opts = "|".join(str(x) for x in o)
            if len(opts) > 60:
                opts = opts[:57] + "..."
        bits.append(f"opts:{opts}")
    if c.get("default") not in (None, ""):
        d = json.dumps(c["default"], ensure_ascii=False, separators=(",", ":"))
        if len(d) > 40:
            d = d[:37] + "..."
        bits.append(f"def:{d}")
    if c.get("units"):
        bits.append("units:" + ",".join(c["units"]))
    # A switcher does not store true, and it does not always store "yes". It stores
    # its own `return_value`, and that value is what gets concatenated onto a
    # prefix_class. Write "yes" into `hide_tablet` and Elementor renders the class
    # `elementor-yes`, which hides nothing.
    if c.get("type") == "switcher":
        bits.append(f"on:{c.get('return_value', 'yes')!r}  off:''")
    if c.get("css"):
        bits.append("css:" + ",".join(c["css"]))
    # The OTHER thing a control can do. `css:` is only half the story - 2,573
    # (owner, control) pairs act by putting a class on the element wrapper instead
    # of, or as well as, emitting CSS. Without this line a reader sees a control
    # with no `css:` and concludes it does nothing.
    if c.get("prefix_class"):
        bits.append(f"class:{c['prefix_class']}<value>")
        # The device prefixes are DIFFERENT STRINGS, not a `_tablet` suffix on the
        # class. Elementor sprintf()s the device into the prefix at registration.
        pcd = c.get("prefix_class_devices") or {}
        if pcd:
            bits.append("class-rwd:" + " ".join(
                f"{d}={p}<value>" for d, p in sorted(pcd.items())))
    # Values that are NOT in `opts:` but are legal anyway: Elementor remaps them
    # before building the class, so they render as something else entirely.
    if c.get("classes_dictionary"):
        bits.append("legacy:" + ",".join(
            f"{k}->{v}" for k, v in c["classes_dictionary"].items()))
    # A repeater's value is a LIST of items; these are the item's keys. Without
    # them "slides is a repeater" is the whole answer, which is no answer.
    if c.get("fields"):
        bits.append("item:{" + ",".join(f["name"] for f in c["fields"]) + "}")
    if c.get("condition"):
        cond = json.dumps(c["condition"], ensure_ascii=False, separators=(",", ":"))
        bits.append(f"needs:{cond}")
    # The advanced condition form. 152 controls are gated ONLY this way, and they
    # have no `condition` at all - so a reader who only looks for `needs:` above
    # would conclude they are unconditional and wonder why they do nothing.
    if c.get("conditions"):
        bits.append("needs-adv:" + _fmt_conditions(c["conditions"]))
    # Not a condition: this control's CSS interpolates another control's value,
    # and Elementor discards the whole declaration if that value is empty.
    if c.get("needs_value"):
        bits.append("needs-value-of:" + ",".join(c["needs_value"]))
    return "  ".join(bits)


def _fmt_conditions(node: dict) -> str:
    rel = (node.get("relation") or "and").lower()
    parts = []
    for t in node.get("terms") or []:
        if t.get("terms"):
            parts.append("(" + _fmt_conditions(t) + ")")
        else:
            op = t.get("operator") or "==="
            parts.append(f"{t['name']}{op}{json.dumps(t.get('value'), ensure_ascii=False)}")
    return f" {rel} ".join(parts)


# ---------------------------------------------------------------------------


def requires_tag(w: dict) -> str:
    """
    What an install must have before this widget EXISTS. Not a nicety: a schema
    that lists `woocommerce-product-price` without saying it needs WooCommerce is
    telling you to build a page out of a widget that will not be there.
    """
    r = w.get("requires")
    if not r:
        return ""
    if r.get("plugin"):
        return f"needs plugin:{r['plugin']}"
    if r.get("experiment"):
        return f"needs experiment:{r['experiment']}"
    return "needs a WP widget some plugin registers"


def cmd_widgets(a) -> None:
    s = schema()
    rows = []
    for name, w in sorted(owners().items()):
        if a.tier and w["tier"] != a.tier:
            continue
        cats = "|".join(w.get("categories", []))
        hay = f"{name} {w.get('title') or ''} {cats}".lower()
        if a.grep and a.grep.lower() not in hay:
            continue
        if a.requires and requires_tag(w).find(a.requires.lower()) < 0:
            continue
        rows.append({
            "name": name,
            "elType": w.get("elType", "widget"),
            "tier": w["tier"],
            "title": w.get("title"),
            "requires": w.get("requires"),
            "controls_own": w.get("controls_own", w.get("controls_total")),
        })
    lines = [f"{len(rows)} match  (Elementor {s['meta']['elementor_version']} / Pro {s['meta']['elementor_pro_version']})"]
    for r in rows:
        req = requires_tag(r)
        lines.append(f"  [{tier_tag(r['tier'])}] {r['name']:<30} {str(r['title'] or '')[:26]:<28} "
                     f"{r['controls_own']:>4} own" + (f"  {req}" if req else ""))
    lines.append("")
    lines.append("Every widget also has the 210 shared Advanced-tab controls: el.py common")
    n_req = sum(1 for r in rows if r.get("requires"))
    if n_req:
        lines.append(f"{n_req} of these do not exist on every install - see the `needs` column.")
    emit(rows, a.json, lines)


def cmd_widget(a) -> None:
    o = owners()
    name = a.name
    if name not in o:
        near = [k for k in o if a.name.lower() in k.lower()]
        sys.exit(f"No element/widget '{name}'." + (f" Did you mean: {', '.join(near[:8])}" if near else ""))
    w = o[name]

    # Elementor V4. These do not have controls, they have a PROP SCHEMA, and their
    # values are type-tagged. Printing an empty control list under the classic
    # headings would say "this widget has no settings", which is false and would
    # send an agent off to write `settings: {}` and wonder why nothing rendered.
    if w.get("control_system") == "v4-atomic":
        lines = [
            f"{name}  [{w['tier'].upper()}]  \"{w.get('title') or name}\"  "
            f"elType={w.get('elType', 'widget')}",
            "",
            "!! ELEMENTOR V4 ATOMIC ELEMENT - a DIFFERENT data model from everything",
            "   else in this schema. It has no `controls`. It has a prop schema, its",
            "   values are type-tagged, and its styling lives in a separate `styles`",
            "   array rather than in `settings`:",
            "",
            '       classic:  "header_size": "h2"',
            '       atomic:   "tag": { "$$type": "string", "value": "h2" }',
            "",
        ]
        req = w.get("requires")
        if req and req.get("experiment"):
            lines.append(f"   It only exists when the `{req['experiment']}` experiment is on.")
            lines.append("")
        lines.append(f"prop schema ({len(w.get('props') or [])}):")
        for p in w.get("props") or []:
            d = json.dumps(p.get("default"), ensure_ascii=False)
            if len(d) > 70:
                d = d[:67] + "..."
            lines.append(f"    {p['name']:<22} {str(p.get('type')):<10} default:{d}")
        lines += [
            "",
            "This skill's validate-page.py / apply-page.php model the CLASSIC tree.",
            "The prop schema above is reported so you know the element exists and what",
            "it takes - not as a claim that building V4 elements here is verified.",
        ]
        emit(w, a.json, lines)
        return

    ctrls = w["controls"]
    if a.tab:
        ctrls = [c for c in ctrls if c.get("tab") == a.tab]
    if a.section:
        ctrls = [c for c in ctrls if c.get("section") == a.section]
    if a.grep:
        ctrls = [c for c in ctrls if a.grep.lower() in json.dumps(c, ensure_ascii=False).lower()]

    secmap = {s["name"]: s for s in w.get("sections", [])}
    n_common = schema()["common_controls"]["count"]
    lines = [
        f"{name}  [{w['tier'].upper()}]  \"{w.get('title') or name}\"  elType={w.get('elType', 'widget')}",
        f"{w.get('controls_own', w.get('controls_total'))} own controls"
        + (f"  +{n_common} shared Advanced controls (el.py common)" if w.get("has_common") else ""),
    ]
    if w["tier"] == "pro":
        lines.append("")
        lines.append("!! This whole widget requires Elementor Pro. Everything below is Pro.")
    # Elementor Pro is not the only thing a widget can depend on. A module that
    # does not load registers nothing, and its widgets are simply not there - no
    # error, no placeholder, the widgetType just does not resolve.
    req = w.get("requires")
    if req:
        lines.append("")
        if req.get("plugin"):
            lines.append(f"!! This widget DOES NOT EXIST unless the `{req['plugin']}` plugin is active.")
        elif req.get("experiment"):
            lines.append(f"!! This widget DOES NOT EXIST unless Elementor's `{req['experiment']}` "
                         f"experiment is on.")
        else:
            lines.append("!! This is a legacy WordPress widget that Elementor wraps. It exists only "
                         "while some plugin keeps registering it - it is not part of Elementor.")
        lines.append(f"   Gate, from Elementor's source: {req.get('gate', '?')}")
    # Measured by rendering it: dropped on a page with nothing but its settings,
    # this widget produced no markup at all. Not a bug - it has nothing to show
    # until the site gives it something. But an agent that places it and walks away
    # has built an invisible page, and no error was raised anywhere.
    if w.get("renders_bare") is False:
        lines.append("")
        lines.append("!! This widget renders NOTHING on a bare page. It needs real site "
                     "content (a template, a loop, a sidebar, a post context, a configured "
                     "WP widget). Its wrapper-class controls have no wrapper to attach to "
                     "until then.")
    lines.append("")
    by_sec: dict[str, list] = {}
    for c in ctrls:
        by_sec.setdefault(c.get("section", "?"), []).append(c)
    for sec, cs in by_sec.items():
        meta = secmap.get(sec, {})
        lines.append(f"[{meta.get('tab', '?')}] {sec}  \"{meta.get('label') or ''}\"")
        for c in cs:
            lines.append(fmt_control(c))
        lines.append("")
    if not ctrls:
        lines.append("(no controls match this filter)")
    emit({"widget": name, "tier": w["tier"], "controls": ctrls}, a.json, lines)


def cmd_search(a) -> None:
    q = a.q.lower()
    hits = []
    for owner, w in owners().items():
        if a.owner and owner != a.owner:
            continue
        for c in w["controls"]:
            if q in c["name"].lower() or q in (c.get("label") or "").lower():
                hits.append((owner, w["tier"], c))
    for c in schema()["common_controls"]["controls"]:
        if a.owner:
            break
        if q in c["name"].lower() or q in (c.get("label") or "").lower():
            hits.append(("*ALL_WIDGETS*", "free", c))

    lines = [f"{len(hits)} control(s) matching '{a.q}'"]
    shown = hits if a.all else hits[: a.limit]
    for owner, tier, c in shown:
        lines.append(f"  [{tier_tag(tier)}] {owner}")
        lines.append(fmt_control(c, indent="      "))
    if len(hits) > len(shown):
        lines.append(f"  ... {len(hits) - len(shown)} more (--all, or narrow with --owner)")
    emit([{"owner": o, "tier": t, **c} for o, t, c in shown], a.json, lines)


def cmd_css(a) -> None:
    """Reverse lookup: which control writes this CSS property?"""
    prop = a.prop.lower()
    hits = []
    for owner, w in owners().items():
        for c in w["controls"]:
            if any(prop == p.lower() for p in c.get("css", [])):
                hits.append((owner, w["tier"], c))
    for c in schema()["common_controls"]["controls"]:
        if any(prop == p.lower() for p in c.get("css", [])):
            hits.append(("*ALL_WIDGETS*", "free", c))

    lines = [f"{len(hits)} control(s) drive CSS `{a.prop}`"]
    for owner, tier, c in (hits if a.all else hits[: a.limit]):
        lines.append(f"  [{tier_tag(tier)}] {owner:<24} {c['name']:<30} ({c['type']})")
    if len(hits) > a.limit and not a.all:
        lines.append(f"  ... {len(hits) - a.limit} more (--all)")
    emit([{"owner": o, "tier": t, **c} for o, t, c in hits], a.json, lines)


def cmd_type(a) -> None:
    ct = schema()["control_types"]
    if a.name not in ct:
        near = [k for k in ct if a.name.lower() in k.lower()]
        sys.exit(f"No control type '{a.name}'." + (f" Did you mean: {', '.join(near[:8])}" if near else ""))
    c = ct[a.name]
    shape = c.get("value_shape")
    lines = [
        f"control type: {a.name}   [{c['tier'].upper()}]  ({c['source']})",
        "",
        "JSON value shape (what you write into _elementor_data settings):",
        "  " + json.dumps(shape, ensure_ascii=False),
    ]
    # Some control types carry their allowed values on the CONTROL CLASS, so no
    # individual control lists them and the value shape above is just "". The
    # animations are the ones that bite: they are camelCase Animate.css names
    # (`fadeInUp`), and a guessed `fade-in-up` stores fine and animates nothing.
    if c.get("options"):
        lines += ["", f"allowed values ({len(c['options'])}) - these live on the "
                      f"control class, not on any one control:"]
        opts = [str(o) for o in c["options"]]
        for i in range(0, len(opts), 6):
            lines.append("  " + "  ".join(f"{o:<18}" for o in opts[i:i + 6]).rstrip())
    lines += ["", f"php class: {c['class']}"]
    emit(c, a.json, lines)


def cmd_types(a) -> None:
    ct = schema()["control_types"]
    lines = [f"{len(ct)} control types"]
    for t, c in sorted(ct.items()):
        shape = json.dumps(c.get("value_shape"), ensure_ascii=False)
        if len(shape) > 72:
            shape = shape[:69] + "..."
        lines.append(f"  [{tier_tag(c['tier'])}] {t:<28} {shape}")
    emit(ct, a.json, lines)


def cmd_group(a) -> None:
    g = schema()["group_controls"]
    if a.name not in g:
        sys.exit(f"No group control '{a.name}'. Available: {', '.join(sorted(g))}")
    c = g[a.name]
    lines = [
        f"group control: {a.name}   [{c['tier'].upper()}]  ({c['source']})",
        "",
        "A group control expands into several flat settings keys, named",
        "{prefix}_{field}. E.g. with prefix `title` the typography group writes",
        "title_typography, title_font_family, title_font_size, ...",
        "",
        f"{c.get('field_count', 0)} fields:",
    ]
    for f in c.get("fields", []):
        r = " rwd" if f.get("responsive") else ""
        lines.append(f"  {f['field']:<26} {f.get('type', '?'):<14}{r}")
    emit(c, a.json, lines)


def cmd_groups(a) -> None:
    g = schema()["group_controls"]
    lines = [f"{len(g)} group controls"]
    for n, c in sorted(g.items(), key=lambda x: (x[1]["tier"], x[0])):
        lines.append(f"  [{tier_tag(c['tier'])}] {n:<18} {c.get('field_count', 0):>3} fields")
    emit(g, a.json, lines)


def cmd_common(a) -> None:
    cc = schema()["common_controls"]
    ctrls = cc["controls"]
    if a.section:
        ctrls = [c for c in ctrls if c.get("section") == a.section]
    if a.grep:
        ctrls = [c for c in ctrls if a.grep.lower() in json.dumps(c, ensure_ascii=False).lower()]

    lines = [
        f"{cc['count']} controls shared by every widget (Advanced tab).",
        "Written into each widget's own stack by Elementor, so they work the same on all of them.",
        "",
    ]
    by_sec: dict[str, list] = {}
    for c in ctrls:
        by_sec.setdefault(c.get("section", "?"), []).append(c)
    for sec, cs in by_sec.items():
        lines.append(f"[{cs[0].get('tab', '?')}] {sec}  ({len(cs)})")
        if not a.list_only:
            for c in cs:
                lines.append(fmt_control(c))
        lines.append("")
    emit(ctrls, a.json, lines)


def cmd_pro(a) -> None:
    """
    Everything that needs Elementor Pro. Run this before shipping to a site you
    do not control, or before assuming a control you found on a free widget is
    actually free.
    """
    s = schema()
    m = s["meta"]
    o = owners()

    if a.check:
        # Given control names, say which ones need Pro. Exits 1 if any do, so
        # it can be used as a gate in a script.
        names = set(a.check)
        found = {}
        for c in s["common_controls"]["controls"]:
            if c["name"] in names:
                found[c["name"]] = ("*ALL_WIDGETS*", c.get("tier"))
        for owner, w in o.items():
            for c in w["controls"]:
                if c["name"] in names and c["name"] not in found:
                    found[c["name"]] = (owner, c.get("tier"))
        lines, bad = [], False
        for n in a.check:
            owner, tier = found.get(n, (None, None))
            if tier is None:
                lines.append(f"  ?     {n:<32} not found in the schema")
            elif tier == "pro":
                lines.append(f"  PRO   {n:<32} (on {owner}) REQUIRES ELEMENTOR PRO")
                bad = True
            else:
                lines.append(f"  free  {n:<32} (on {owner})")
        emit(found, a.json, lines)
        if bad and not a.json:
            print("\nAt least one control needs Pro. On a Free install these save fine")
            print("and then do nothing: no error, no warning, just missing styling.")
        sys.exit(1 if bad else 0)

    pro_widgets = sorted(n for n, w in o.items() if w["tier"] == "pro")
    injected = [c for c in s["common_controls"]["controls"] if c.get("tier") == "pro"]
    lines = [
        f"Elementor Pro {m['elementor_pro_version']} adds, on top of Free {m['elementor_version']}:",
        "",
        f"  {len(pro_widgets)} widgets",
        f"  {len(injected)} controls injected into EVERY widget, free ones included",
        f"  {len(m.get('pro_only_control_types', []))} control types: "
        + ", ".join(m.get("pro_only_control_types", [])),
        f"  {len(m.get('pro_only_group_controls', []))} group controls: "
        + ", ".join(m.get("pro_only_group_controls", [])),
        "",
        "Controls Pro injects into every widget (this is the trap: they show up on",
        "the FREE Heading widget, and they are not free):",
    ]
    by_sec: dict[str, list] = {}
    for c in injected:
        by_sec.setdefault(c.get("section", "?"), []).append(c["name"])
    for sec, names in by_sec.items():
        lines.append(f"  [{sec}] {len(names)}")
        lines.append("     " + ", ".join(sorted(names)))
    lines += [
        "",
        "Per-element injection counts: "
        + ", ".join(f"{k}={v}" for k, v in m.get("pro_injected_into_elements", {}).items()),
        "",
        "Pro widgets: " + ", ".join(pro_widgets),
        "",
        f"Tier source: {m.get('tier_source')}",
    ]
    emit({"pro_widgets": pro_widgets, "injected": injected, "meta": m}, a.json, lines)


def cmd_breakpoints(a) -> None:
    b = schema()["breakpoints"]
    lines = [
        "Responsive works by suffixing the control name. Desktop is the bare",
        "control; every other breakpoint appends its suffix.",
        "",
        "  \"padding\":        {...}   <- desktop (no suffix)",
        "  \"padding_tablet\": {...}",
        "  \"padding_mobile\": {...}",
        "",
    ]
    for name, c in b.items():
        state = "ACTIVE " if c.get("active") else "off    "
        val = f"{c.get('direction', '')} {c.get('value') or ''}".strip()
        lines.append(f"  {state} {name:<14} suffix={c.get('suffix') or '(none)':<16} {val}")
    lines.append("")
    lines.append("Only ACTIVE breakpoints have controls registered. Enabling more is a")
    lines.append("site setting (Site Settings > Layout > Breakpoints), and it changes")
    lines.append("which suffixes exist: re-extract the schema after changing them.")
    emit(b, a.json, lines)


def cmd_skeleton(a) -> None:
    """A minimal, valid _elementor_data tree. IDs must be unique 7-char hex."""
    tree = [
        {
            "id": "a1b2c3d",
            "elType": "container",
            "settings": {
                "container_type": "flex",
                "content_width": "boxed",
                "flex_direction": "column",
                "padding": {"unit": "px", "top": "60", "right": "20",
                            "bottom": "60", "left": "20", "isLinked": False},
                "padding_mobile": {"unit": "px", "top": "40", "right": "16",
                                   "bottom": "40", "left": "16", "isLinked": False},
                "background_background": "classic",
                "background_color": "#F7F7F7",
            },
            "elements": [
                {
                    "id": "e4f5a6b",
                    "elType": "widget",
                    "widgetType": "heading",
                    "settings": {
                        "title": "Built without opening the editor",
                        "header_size": "h2",
                        "align": "center",
                        "title_color": "#111111",
                    },
                    "elements": [],
                }
            ],
        }
    ]
    lines = [
        "Minimal valid _elementor_data (a list of top-level containers).",
        "",
        json.dumps(tree, indent=2, ensure_ascii=False),
        "",
        "Rules that bite:",
        "  - `id` is a unique 7-char lowercase hex string. Duplicate ids silently",
        "    break the editor, so generate fresh ones per element.",
        "  - every node needs `elements` (use [] on leaves), even widgets.",
        "  - widgets need BOTH elType='widget' and widgetType='<name>'.",
        "  - the whole tree is stored JSON-encoded in the `_elementor_data` post",
        "    meta, and the post also needs `_elementor_edit_mode` = 'builder'.",
        "  - after writing, flush the CSS cache or the page renders unstyled:",
        "    wp elementor flush-css",
    ]
    emit(tree, a.json, lines)


def cmd_doctypes(a) -> None:
    """The legal values of `_elementor_template_type` - install-dependent, like widgets."""
    docs = schema().get("documents") or {}
    lines = [f"{len(docs)} document types  (the legal `_elementor_template_type` values)", ""]
    for t, d in sorted(docs.items()):
        mod = f"  module:{d['module']}" if d.get("module") else ""
        lines.append(f"  [{tier_tag(d['tier'])}] {t:<24}{mod}")
    lines += ["", "wp-page / wp-post are ordinary content. The rest are elementor_library",
              "posts (header, footer, single, archive, popup, loop-item...) - create them",
              "as that CPT with `_elementor_template_type` set, then Display Conditions",
              "decide where they apply (references/templates-and-conditions.md)."]
    emit(docs, a.json, lines)


def cmd_page_settings(a) -> None:
    """
    `_elementor_page_settings` - the page's OWN settings, beside `_elementor_data`.

    This is where Canvas lives. `template: "elementor_canvas"` renders the page
    with no theme header/footer at all; miss this surface and a landing page keeps
    the site chrome no matter what you put in the tree.
    """
    ps = (schema().get("page_settings") or {}).get(a.doc or "wp-page")
    if not ps:
        sys.exit(f"no page settings for document type {a.doc!r}")
    ctrls = ps["controls"]
    if a.grep:
        ctrls = [c for c in ctrls if a.grep.lower() in json.dumps(c).lower()]
    lines = [f"_elementor_page_settings on a {a.doc or 'wp-page'}  ({len(ctrls)} settings)",
             "written as ONE meta value: update_post_meta(id, '_elementor_page_settings', array)", ""]
    for c in ctrls:
        lines.append(fmt_control(c))
    emit(ctrls, a.json, lines)


def cmd_kit(a) -> None:
    """
    Site Settings. Saved as `_elementor_page_settings` ON THE KIT POST
    (`get_option('elementor_active_kit')` is its id). Global colors and fonts are
    repeaters here, and `__globals__` references resolve to their items' `_id`.
    """
    ks = schema().get("kit_settings")
    if not ks or "controls" not in ks:
        sys.exit("no kit settings in this schema - re-extract")
    ctrls = ks["controls"]
    if a.section:
        secs = {x["name"] for x in ks.get("sections", [])}
        ctrls = [c for c in ctrls if c.get("section") == a.section]
        if not ctrls:
            sys.exit(f"no such section. Sections: {', '.join(sorted(secs))}")
    if a.grep:
        ctrls = [c for c in ctrls if a.grep.lower() in json.dumps(c).lower()]
    lines = [f"Site Settings (the Kit)  ({len(ctrls)} shown / {len(ks['controls'])} total)",
             ks.get("note", ""), ""]
    if not a.section and not a.grep:
        lines += ["sections (use --section):"]
        for x in ks.get("sections", []):
            lines.append(f"  {x['name']:<40} {x.get('label') or ''}")
    else:
        for c in ctrls[:120]:
            lines.append(fmt_control(c))
    emit(ctrls, a.json, lines)


def cmd_tags(a) -> None:
    """
    The `__dynamic__` surface. A control with dynamic support does not take a tag
    NAME - it takes a binding, and which tags are legal is matched by CATEGORY:

        "__dynamic__": { "title": "[elementor-tag id=\"x\" name=\"post-title\" settings=\"...\"]" }

    A text control accepts tags whose categories include `text`, a media control
    `image`, and so on. Every tag here is Elementor Pro; 13 also need WooCommerce.
    """
    tags = schema().get("dynamic_tags") or {}
    rows = []
    for name, t in sorted(tags.items()):
        if "error" in t:
            continue
        if a.group and t.get("group") != a.group:
            continue
        if a.grep and a.grep.lower() not in json.dumps(t).lower():
            continue
        rows.append(t)
    lines = [f"{len(rows)} dynamic tags  (ALL require Elementor Pro; the woocommerce "
             f"group also needs WooCommerce)", ""]
    for t in rows:
        st = " ".join(c["name"] for c in t.get("settings") or [])
        lines.append(f"  {t['name']:<28} {str(t.get('group')):<12} "
                     f"binds-to:{'|'.join(t.get('categories') or []):<18}"
                     + (f" settings:{st}" if st else ""))
    lines += ["",
              "Bind one in `settings.__dynamic__.<control>`; the tag's own settings",
              "(an ACF tag's `key`, a meta tag's field name) go inside the shortcode's",
              "settings attribute, URL-encoded JSON. Unset settings render EMPTY, silently."]
    emit(rows, a.json, lines)


def cmd_stats(a) -> None:
    s = schema()
    m = s["meta"]
    o = owners()
    v4 = [n for n, w in o.items() if w.get("control_system") == "v4-atomic"]
    reqs: dict[str, int] = {}
    for w in o.values():
        r = w.get("requires")
        if r:
            k = (f"plugin:{r['plugin']}" if r.get("plugin")
                 else f"experiment:{r['experiment']}" if r.get("experiment")
                 else "a WP widget some plugin registers")
            reqs[k] = reqs.get(k, 0) + 1
    lines = [
        f"Elementor {m['elementor_version']} / Pro {m['elementor_pro_version']}  (extracted {m['extracted_at']})",
        f"  elements        {m['counts']['elements']}",
        f"  widgets         {m['counts']['widgets']}  = {m['counts']['widgets_free']} free + {m['counts']['widgets_pro']} pro",
        f"  control types   {m['counts']['control_types']}",
        f"  group controls  {m['counts']['group_controls']}",
        f"  shared controls {s['common_controls']['count']}  (every classic widget's Advanced tab)",
        f"  stored controls {sum(w.get('controls_own', w.get('controls_total', 0)) for w in o.values())}",
        f"  raw control rows before factoring: {sum(w.get('controls_total', 0) for w in o.values())}",
    ]
    if v4:
        lines += ["",
                  f"  {len(v4)} of these are Elementor V4 ATOMIC elements. They have no controls -",
                  f"  they have a prop schema and type-tagged values. Different data model.",
                  f"  (el.py widget e-heading)"]
    if reqs:
        lines += ["",
                  "  NOT EVERY WIDGET EXISTS ON EVERY INSTALL. The surface is a property of",
                  "  the site, not of Elementor:"]
        for k, n in sorted(reqs.items(), key=lambda kv: -kv[1]):
            lines.append(f"    {n:4} widgets need {k}")
        lines.append(f"    (`el.py widgets --requires woocommerce` etc.)")
    lines += ["",
              f"  extracted with WooCommerce active: {m.get('woocommerce_active')}",
              f"  control optimisation disabled during extraction: {m.get('control_optimisation_disabled')}",
              f"  responsive-collapse anomalies: {len(m.get('responsive_collapse_anomalies', []))}"]
    emit(m, a.json, lines)


def main() -> int:
    p = argparse.ArgumentParser(prog="el.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--json", action="store_true", help="machine-readable output")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("widgets", help="list widgets/elements")
    s.add_argument("--tier", choices=["free", "pro"])
    s.add_argument("--requires", metavar="X",
                   help="only widgets that need X to exist at all "
                        "(e.g. woocommerce, e_atomic_elements, nested-elements)")
    s.add_argument("--grep")
    s.set_defaults(fn=cmd_widgets)

    s = sub.add_parser("widget", help="one widget's controls")
    s.add_argument("name")
    s.add_argument("--tab", help="content | style | advanced | layout")
    s.add_argument("--section")
    s.add_argument("--grep")
    s.set_defaults(fn=cmd_widget)

    s = sub.add_parser("container", help="shorthand for `widget container`")
    s.add_argument("--tab")
    s.add_argument("--section")
    s.add_argument("--grep")
    s.set_defaults(fn=lambda a: cmd_widget(argparse.Namespace(name="container", **{
        k: getattr(a, k) for k in ("tab", "section", "grep", "json")})))

    s = sub.add_parser("search", help="find a control by name/label")
    s.add_argument("q")
    s.add_argument("--owner", help="restrict to one widget/element")
    s.add_argument("--limit", type=int, default=25)
    s.add_argument("--all", action="store_true")
    s.set_defaults(fn=cmd_search)

    s = sub.add_parser("css", help="which control drives a CSS property")
    s.add_argument("prop")
    s.add_argument("--limit", type=int, default=25)
    s.add_argument("--all", action="store_true")
    s.set_defaults(fn=cmd_css)

    s = sub.add_parser("type", help="JSON value shape of a control type")
    s.add_argument("name")
    s.set_defaults(fn=cmd_type)

    s = sub.add_parser("types", help="all control types + value shapes")
    s.set_defaults(fn=cmd_types)

    s = sub.add_parser("group", help="fields a group control expands to")
    s.add_argument("name")
    s.set_defaults(fn=cmd_group)

    s = sub.add_parser("groups", help="all group controls")
    s.set_defaults(fn=cmd_groups)

    s = sub.add_parser("common", help="the Advanced controls every widget shares")
    s.add_argument("--section")
    s.add_argument("--grep")
    s.add_argument("--list-only", action="store_true")
    s.set_defaults(fn=cmd_common)

    s = sub.add_parser("pro", help="what needs Elementor Pro (and what silently won't work without it)")
    s.add_argument("--check", nargs="+", metavar="CONTROL",
                   help="exit 1 if any of these control names needs Pro")
    s.set_defaults(fn=cmd_pro)

    s = sub.add_parser("breakpoints", help="responsive suffixes")
    s.set_defaults(fn=cmd_breakpoints)

    s = sub.add_parser("skeleton", help="a minimal valid page tree")
    s.set_defaults(fn=cmd_skeleton)

    s = sub.add_parser("doctypes", help="legal _elementor_template_type values")
    s.set_defaults(fn=cmd_doctypes)

    s = sub.add_parser("page-settings", help="_elementor_page_settings surface (hide_title, Canvas, page background)")
    s.add_argument("--doc", choices=["wp-page", "wp-post"], default="wp-page")
    s.add_argument("--grep")
    s.set_defaults(fn=cmd_page_settings)

    s = sub.add_parser("kit", help="Site Settings: global colors/fonts, theme style, layout defaults")
    s.add_argument("--section")
    s.add_argument("--grep")
    s.set_defaults(fn=cmd_kit)

    s = sub.add_parser("tags", help="the dynamic tags a control can be bound to (__dynamic__)")
    s.add_argument("--group", help="post / site / archive / author / woocommerce / media / action / comments")
    s.add_argument("--grep")
    s.set_defaults(fn=cmd_tags)

    s = sub.add_parser("stats", help="what's in the schema")
    s.set_defaults(fn=cmd_stats)

    a = p.parse_args()
    a.fn(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
