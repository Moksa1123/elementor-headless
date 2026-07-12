#!/usr/bin/env python3
"""
verify-live.py - verify the page THE PUBLIC ACTUALLY GETS.

    python tools/verify-live.py examples/demo-page.json https://example.com/my-page/

Every other verifier in this repo reads an artefact from inside the machine:

    verify-render.py    a CSS file you hand it, off the server's disk
    sweep-controls.py   the same, in bulk
    sweep-classes.py    HTML from `Plugin::$instance->frontend->get_builder_content_for_display()`

None of those is what a visitor receives. Between them and the browser sit the
theme, the page cache (Breeze/WP Rocket), Varnish, and the CDN - and every one of
those layers can serve you something else entirely while all the inside-the-machine
checks stay green. That is the same blind spot as Trap 9, one layer further out:
`apply-page.php` used to leave a stale rendered-HTML cache, and every CSS-based
check passed happily for as long as that bug lived.

So this one goes through the front door:

  1. GET the public URL.
  2. GET EVERY Elementor stylesheet the page links, and concatenate them.
     Not a file off the disk - the URLs in the markup, cache-busters and all. A page
     linking `post-9176.css?ver=<old>` while the disk holds the new one renders
     stale, and reading the disk copy would call that a pass.
  3. Assert every element of the tree is in the delivered HTML.
  4. Assert every CSS-driving setting produced its property in the delivered CSS.
  5. Assert every class-emitting setting produced its class on the delivered wrapper.
  6. Print the cache headers, so a stale edge is visible rather than silent.

Step 2 is plural on purpose. **A page's styling is split across several files** -
`post-<kit_id>.css` carries the Kit's global colours and fonts, `post-<id>.css`
carries the page, and `global.css` carries the widget base styles. Reading only
`post-<id>.css` (which is what `verify-render.py` does, because you hand it one
file) sees an incomplete picture. The union of what the page LINKS is the only
honest answer to "what styles this page".

Stdlib only.
"""
from __future__ import annotations

import argparse
import html as htmllib
import json
import re
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urljoin

HERE = Path(__file__).resolve().parent
SCHEMA_PATH = HERE.parent / "data" / "elementor-schema.json"

UA = "elementor-headless/verify-live"
# Every stylesheet Elementor put on this page: the Kit (global colours/fonts), the
# post itself, the widget base styles. Not just post-<id>.css.
ELEMENTOR_CSS = re.compile(
    r'<link[^>]+href=["\']([^"\']*/uploads/elementor/css/[^"\']+\.css[^"\']*)["\']', re.I)
WRAPPER = re.compile(r'<[a-zA-Z][^>]*\bdata-id=["\']([0-9a-f]{7})["\'][^>]*>')
CLASSATTR = re.compile(r'\bclass=["\']([^"\']*)["\']')


def get(url: str) -> tuple[str, dict]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode("utf-8", "replace")
        return body, {k.lower(): v for k, v in r.headers.items()}


def controls_for(schema: dict, el: dict) -> dict[str, dict]:
    owner = el.get("widgetType") if el["elType"] == "widget" else el["elType"]
    src = schema["widgets"].get(owner) or schema["elements"].get(owner)
    if not src:
        return {}
    out = {c["name"]: c for c in src["controls"]}
    if src.get("has_common"):
        missing = set(src.get("common_missing", []))
        for c in schema["common_controls"]["controls"]:
            if c["name"] not in missing:
                out.setdefault(c["name"], c)
    return out


def blocks_for_id(css: str, el_id: str) -> str:
    """
    Every declaration block whose selector names this element, at any nesting depth.

    Two things this must get right, and the naive version gets both wrong:

    - **Brace-counting, not `[^{}]*`.** Elementor 4.1.4 emits a literal, unexpanded
      `{{VALUE}}` into the compiled CSS on the `counter` widget, and a naive body
      pattern stops dead on those braces and silently loses the rest of the rule.

    - **Recurse into at-rules.** Not every desktop value is at the top level.
      Elementor emits some of them desktop-first, inside `@media (min-width: ...)`
      - the container's `boxed_width` is one. Scanning only top-level selectors
      finds 93 of the demo page's 94 properties and calls the 94th a failure.
    """
    out, i, n = [], 0, len(css)
    while i < n:
        b = css.find("{", i)
        if b < 0:
            break
        sel = css[i:b].strip()
        depth, j = 1, b + 1
        while j < n and depth:
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
            j += 1
        body = css[b + 1:j - 1]
        if sel.startswith("@"):
            nested = blocks_for_id(body, el_id)
            if nested:
                out.append(nested)
        elif f"elementor-element-{el_id}" in sel:
            out.append(body)
        i = j
    return "\n".join(out)


def wrapper_classes(doc: str, el_id: str) -> set[str] | None:
    for m in WRAPPER.finditer(doc):
        if m.group(1) != el_id:
            continue
        cm = CLASSATTR.search(m.group(0))
        return set(htmllib.unescape(cm.group(1)).split()) if cm else set()
    return None


def expected_css_value(ctrl: dict, value) -> str | None:
    """
    The literal fragment this value must produce in the stylesheet, or None if it
    is not predictable.

    Asserting only that the PROPERTY appeared is a much weaker check than it looks:
    it passes whatever the value is. Rewrite a page's `background_color` to a colour
    it was never given and a property-only check still reports a pass, because
    `background-color:` is right there in the block - just with the old value in it.
    That is exactly what this verifier did on its first run, and a negative-control
    tamper is what caught it.
    """
    t = ctrl.get("type")
    if t == "color" and isinstance(value, str) and value.startswith("#"):
        return value
    if t in ("slider", "dimensions", "gaps") and isinstance(value, dict):
        unit = value.get("unit")
        size = value.get("size", value.get("top", value.get("column")))
        if unit and unit != "custom" and size not in (None, ""):
            return f"{size}{unit}"
    if t in ("select", "choose", "select2") and isinstance(value, str) and value:
        return value
    if t == "number" and isinstance(value, (int, float)):
        return str(value)
    return None


def expected_class(ctrl: dict, value, device: str | None) -> str | None:
    prefix = (ctrl.get("prefix_class") if device is None
              else (ctrl.get("prefix_class_devices") or {}).get(device))
    if prefix is None:
        return None
    v = str((ctrl.get("classes_dictionary") or {}).get(str(value), value))
    if v == "":
        return None
    return prefix + v


def walk(nodes, out):
    for e in nodes:
        out.append(e)
        walk(e.get("elements", []), out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("page", type=Path, help="the page tree you applied")
    ap.add_argument("url", help="the public URL a visitor would open")
    a = ap.parse_args()

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    tree = json.loads(a.page.read_text(encoding="utf-8"))
    els: list[dict] = []
    walk(tree, els)

    print(f"GET {a.url}")
    doc, headers = get(a.url)
    cache_bits = {k: headers[k] for k in
                  ("x-cache", "age", "cf-cache-status", "x-varnish", "cache-control")
                  if k in headers}
    print(f"    {len(doc):,} bytes   " +
          "  ".join(f"{k}={v}" for k, v in cache_bits.items()))

    hrefs = list(dict.fromkeys(ELEMENTOR_CSS.findall(doc)))
    if not hrefs:
        print("\nFAIL - the delivered page links NO compiled Elementor stylesheet.")
        print("       The tree may be right and the page will still render unstyled.")
        return 1
    parts = []
    for h in hrefs:
        u = urljoin(a.url, h)
        body, ch = get(u)
        parts.append(body)
        tag = "  ".join(f"{k}={ch[k]}" for k in ("x-cache", "age") if k in ch)
        print(f"GET {u}\n    {len(body):,} bytes   {tag}")
    css = "\n".join(parts)
    print(f"    -> {len(hrefs)} stylesheet(s), {len(css):,} bytes total")
    print()

    fails: list[str] = []
    n_html = n_css = n_class = n_css_prop_only = n_props = 0
    not_assertable = 0

    for el in els:
        eid = el["id"]
        classes = wrapper_classes(doc, eid)
        if classes is None:
            fails.append(f"element {eid} ({el.get('widgetType') or el['elType']}) "
                         f"is NOT in the delivered HTML at all")
            continue
        n_html += 1

        ctrls = controls_for(schema, el)
        block = blocks_for_id(css, eid)

        for key, value in (el.get("settings") or {}).items():
            base, device = key, None
            for d in ("tablet", "mobile"):
                if key.endswith(f"_{d}"):
                    base, device = key[: -len(d) - 1], d
                    break
            ctrl = ctrls.get(base)
            if not ctrl:
                continue

            if ctrl.get("prefix_class"):
                want = expected_class(ctrl, value, device)
                if want:
                    missing = set(want.split()) - classes
                    if missing:
                        fails.append(
                            f"{eid}.{key} = {value!r}: class `{' '.join(sorted(missing))}` "
                            f"is NOT on the delivered wrapper")
                    else:
                        n_class += 1

            if ctrl.get("css"):
                if not block:
                    fails.append(f"{eid}.{key}: the delivered CSS has no rule for "
                                 f"this element at all")
                    continue
                # Only assert the literal value when the CSS sweep has already proven
                # this control puts its value in the stylesheet verbatim. 1,270
                # controls do NOT: Elementor rewrites them on the way out through
                # `selectors_dictionary`, so `_element_width: "initial"` emits
                # `width: var( --container-widget-width, 31% )` and the string
                # "initial" appears nowhere. The sweep stamped those `verified:
                # "property"`, and reusing its verdict is better than re-deriving a
                # worse one here.
                want = (expected_css_value(ctrl, value)
                        if ctrl.get("verified") != "property" else None)
                seen_value = False
                missing_props = []
                for prop in ctrl["css"]:
                    # EVERY declaration of this property on this element, not the
                    # first. An icon-box's `primary_color` and `title_color` both
                    # emit `color:`, on different sub-selectors - taking the first
                    # match compares the title's expected colour against the icon's
                    # actual one and calls a correct page broken.
                    decls = [m.group(1) for m in re.finditer(
                        rf"(?:^|[;{{\s]){re.escape(prop)}\s*:([^;}}]*)", block)]
                    if not decls:
                        missing_props.append(prop)
                        continue
                    n_props += 1
                    if want and any(want.lower() in d.lower() for d in decls):
                        seen_value = True

                # A control drives SEVERAL properties and its value lands in only
                # some of them. `_element_custom_width: 31%` emits
                # `--container-widget-width: 31%` AND `--container-widget-flex-grow: 0`
                # - a constant. Demanding the value in every property it touches
                # fails a page that is completely correct. The honest assertion is:
                # every property it claims must be present, and the value must turn
                # up in at least ONE of them.
                if missing_props:
                    fails.append(f"{eid}.{key} = {value!r}: "
                                 f"{', '.join('`' + p + '`' for p in missing_props)} "
                                 f"NOT in the delivered CSS")
                elif want and not seen_value:
                    fails.append(
                        f"{eid}.{key}: the properties are in the delivered CSS, but "
                        f"none of them carries the {want!r} this tree asks for - "
                        f"the page is serving something else")
                elif want:
                    n_css += 1
                else:
                    n_css_prop_only += 1
            elif not ctrl.get("prefix_class"):
                not_assertable += 1

    print(f"elements delivered      : {n_html}/{len(els)}")
    print(f"CSS properties delivered: {n_props}  (across {n_css + n_css_prop_only} settings)")
    print(f"  value-exact           : {n_css}  (the exact value this tree asks for is in the delivered CSS)")
    print(f"  property only         : {n_css_prop_only}  (Elementor rewrites the value; the sweep already proved which)")
    print(f"wrapper-class assertions: {n_class} passed")
    print(f"not assertable          : {not_assertable} settings drive neither CSS nor a class")
    print()
    if fails:
        print(f"FAIL - {len(fails)} problem(s) in what the public actually receives:")
        for f in fails[:30]:
            print(f"    {f}")
        if len(fails) > 30:
            print(f"    ... and {len(fails) - 30} more")
        print()
        print("    If the server-side checks pass and this one does not, the tree is")
        print("    fine and a CACHE is serving something else. Purge, then re-run.")
        return 1

    print("PASS - the page a visitor receives contains every element of the tree,")
    print("       the stylesheet it links carries every property the schema promised,")
    print("       and every wrapper carries the classes it should.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
