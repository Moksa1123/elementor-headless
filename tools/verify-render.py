#!/usr/bin/env python3
"""
verify-render.py — prove the schema's control-to-CSS mapping is real.

verify-schema.py answers "does the schema describe your Elementor install?".
This answers the harder question: "if I build a page from the schema, does
Elementor actually emit the CSS the schema says it will?"

    # build the page headlessly, then grab what Elementor compiled
    wp eval-file tools/apply-page.php <post_id> page.json
    wp elementor flush-css --post-id=<post_id>
    cat wp-content/uploads/elementor/css/post-<post_id>.css > rendered.css

    python tools/verify-render.py page.json rendered.css --post-id <post_id>

For every setting in the page, the schema says which CSS properties that control
drives (the `css` field, parsed out of Elementor's own `selectors` map). This
script checks each one actually turned up in the compiled stylesheet, scoped to
that element's id - and for responsive keys like `padding_tablet`, that it turned
up inside a media query rather than in the base block.

That last part is the one worth having. Responsive controls are the easiest thing
in Elementor to get subtly wrong: `padding_tablet` is a legal settings key even
though no `padding_tablet` control object exists anywhere in the control stack,
so a schema can look complete and still be unable to tell you whether writing it
does anything. This turns that question into a test.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "data" / "elementor-schema.json"


def controls_for(schema: dict, el: dict) -> dict[str, dict]:
    if el.get("elType") == "widget":
        w = schema["widgets"].get(el.get("widgetType"), {})
    else:
        w = schema["elements"].get(el.get("elType"), {})
    out = {c["name"]: c for c in w.get("controls", [])}
    if w.get("has_common"):
        missing = set(w.get("common_missing", []))
        for c in schema["common_controls"]["controls"]:
            if c["name"] not in missing:
                out.setdefault(c["name"], c)
    return out


def split_media(css: str) -> tuple[str, dict[str, str]]:
    """Base rules, and each @media block's body keyed by its query."""
    media: dict[str, str] = {}
    base_parts: list[str] = []
    i = 0
    for m in re.finditer(r"@media([^{]+)\{", css):
        base_parts.append(css[i:m.start()])
        depth, j = 1, m.end()
        while j < len(css) and depth:
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
            j += 1
        query = m.group(1).strip()
        media[query] = media.get(query, "") + css[m.end():j - 1]
        i = j
    base_parts.append(css[i:])
    return "".join(base_parts), media


def blocks_for_id(css: str, el_id: str) -> str:
    """Concatenate every rule whose selector mentions this element's id."""
    out = []
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        if f"elementor-element-{el_id}" in m.group(1):
            out.append(m.group(2))
    return " ".join(out)


def walk(nodes, out):
    for el in nodes:
        out.append(el)
        walk(el.get("elements") or [], out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("page", type=Path)
    ap.add_argument("css", type=Path)
    ap.add_argument("--post-id", type=int, required=True)
    a = ap.parse_args()

    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    tree = json.loads(a.page.read_text(encoding="utf-8"))
    css = a.css.read_text(encoding="utf-8")

    breakpoints = {b: v for b, v in schema["breakpoints"].items()
                   if v.get("active") and v.get("suffix")}
    base_css, media_css = split_media(css)

    checked = passed = 0
    failures: list[str] = []
    skipped: list[str] = []

    for el in walk(tree, []):
        el_id = el.get("id")
        label = el.get("widgetType") or el.get("elType")
        controls = controls_for(schema, el)
        base_block = blocks_for_id(base_css, el_id)

        for key, value in (el.get("settings") or {}).items():
            if key in ("__globals__", "__dynamic__"):
                continue

            device = None
            ctrl = controls.get(key)
            if ctrl is None:
                for bp in breakpoints:
                    if key.endswith(f"_{bp}") and key[: -len(bp) - 1] in controls:
                        device = bp
                        ctrl = controls[key[: -len(bp) - 1]]
                        break
            if ctrl is None:
                failures.append(f"{label}#{el_id}: `{key}` is not a control at all")
                continue

            props = ctrl.get("css") or []
            if not props:
                # Plenty of controls carry content, not styling (a heading's
                # `title`), or act through a class rather than a declaration.
                # Nothing to assert; say so rather than counting a free pass.
                skipped.append(f"{label}#{el_id}.{key} (no CSS mapping in the schema)")
                continue
            if value in ("", None, [], {}):
                skipped.append(f"{label}#{el_id}.{key} (empty value)")
                continue

            if device is None:
                # Desktop (unsuffixed). Usually the base block - but not always:
                # Elementor emits the desktop value of some responsive controls
                # inside a min-width query instead (the container's `boxed_width`
                # lands in `@media(min-width:768px)`). So accept it anywhere; the
                # claim being tested is "this control drives this property", not
                # "in this exact cascade position".
                haystack = base_block + " " + " ".join(
                    blocks_for_id(body, el_id) for body in media_css.values()
                )
                where = "the stylesheet"
            else:
                # A device-suffixed key must land in THAT breakpoint's media
                # query. This is the assertion worth having: it is what proves
                # writing `padding_tablet` - a key with no control object behind
                # it anywhere in Elementor's stack - actually does something.
                bp = breakpoints[device]
                want = f"{bp.get('direction', 'max')}-width:{bp.get('value')}px"
                bodies = [
                    blocks_for_id(body, el_id)
                    for query, body in media_css.items()
                    if want.replace(" ", "") in query.replace(" ", "")
                ]
                if not bodies:
                    failures.append(
                        f"{label}#{el_id}: `{key}` set, but Elementor emitted no "
                        f"@media({want}) rule for this element at all"
                    )
                    checked += len(props)
                    continue
                haystack, where = " ".join(bodies), f"@media({want})"

            for prop in props:
                checked += 1
                if re.search(rf"(^|[;{{\s]){re.escape(prop)}\s*:", haystack):
                    passed += 1
                else:
                    failures.append(
                        f"{label}#{el_id}: `{key}` should drive CSS `{prop}` in {where}, "
                        f"but it is not there"
                    )

    print(f"page   : {a.page.name}  ({len(walk(tree, []))} elements)")
    print(f"css    : {a.css.name}  ({len(css):,} bytes, {len(media_css)} media queries)")
    print(f"schema : Elementor {schema['meta']['elementor_version']} / "
          f"Pro {schema['meta']['elementor_pro_version']}")
    print()
    print(f"CSS property assertions: {passed}/{checked} passed")
    if skipped:
        print(f"not assertable         : {len(skipped)} settings carry no CSS mapping")
    print()
    for f in failures:
        print(f"  FAIL  {f}")
    if failures:
        print()
        print(f"{len(failures)} assertion(s) failed - the schema promised CSS that Elementor did")
        print("not emit. Either the schema is stale for this version, or the value shape")
        print("written was wrong (Elementor stores bad values silently and ignores them).")
        return 1

    print("PASS - every setting the schema claims drives a CSS property produced that")
    print("       property in Elementor's compiled stylesheet, and every responsive")
    print("       key landed inside a media query.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
