# Responsive (RWD)

Responsive design in Elementor is a **naming convention**, not a separate data
structure. Desktop is the bare control; every other breakpoint appends a suffix.

```json
"padding":        { "unit": "px", "top": "80", ... },   // desktop
"padding_tablet": { "unit": "px", "top": "56", ... },
"padding_mobile": { "unit": "px", "top": "40", ... }
```

That is the whole mechanism. It works on any control the schema marks responsive
(30.1% of them), and it works the same way for group-control fields:
`typography_font_size_mobile`, `_element_custom_width_tablet`.

```bash
python tools/el.py breakpoints
python tools/el.py widget heading --tab style     # `rwd:` marks the responsive ones
```

## Only ACTIVE breakpoints exist

Elementor registers six breakpoints and activates two by default:

| Breakpoint | Default | Suffix | Query |
|---|---|---|---|
| `widescreen` | off | `_widescreen` | min-width |
| `laptop` | off | `_laptop` | max-width |
| `tablet_extra` | off | `_tablet_extra` | max-width |
| **`tablet`** | **on** | `_tablet` | `max-width: 1024px` |
| **`mobile_extra`** | off | `_mobile_extra` | max-width |
| **`mobile`** | **on** | `_mobile` | `max-width: 767px` |
| `desktop` | on | *(none)* | base rules |

Writing `padding_laptop` on a site where `laptop` is not enabled does nothing.
Breakpoints are a **site setting** (Site Settings → Layout → Breakpoints), and
enabling one changes which suffixes are legal — so **re-extract the schema after
changing them**. `el.py breakpoints` reads the active set from the schema, not
from a hardcoded list.

## Why `padding_tablet` is not in the control stack (and works anyway)

There is no `padding_tablet` control object. Anywhere. If you enumerate
`get_controls()` on the container you will find `padding` and nothing else.

Elementor has two responsive mechanisms and this is the common one: the control is
registered once with `is_responsive => true`, and the breakpoint variants are
resolved **at render time** by looking up `"{control}_{device}"` in the saved
settings. The other mechanism (used by e.g. `sticky_offset`) does register real
suffixed siblings.

An extractor that only looks for suffixed siblings — the obvious approach — finds
mechanism B and misses mechanism A, which covers padding, margin, width, font
size and gap. The full story, and the flag to test instead, is in
[extraction-traps.md](extraction-traps.md#trap-2--responsive-is-two-mechanisms-and-the-obvious-test-only-finds-one).

The practical consequence: **you cannot verify responsive from the control stack
alone.** You have to write it, let Elementor compile, and look at the CSS. That is
what `tools/verify-render.py` does — it asserts each responsive key landed inside
*that breakpoint's* media query.

## What the CSS actually comes out as

From the demo page in `examples/demo-page.json`, compiled by Elementor:

```css
/* desktop — base rules */
.elementor-element-1a2b3c4{ --padding-top:80px; --padding-left:24px; }
.elementor-element-2b3c4d5 .elementor-heading-title{ font-size:46px; }

/* padding_tablet */
@media(max-width:1024px){
  .elementor-element-1a2b3c4{ --padding-top:56px; --padding-left:20px; }
}

/* padding_mobile + typography_font_size_mobile */
@media(max-width:767px){
  .elementor-element-1a2b3c4{ --padding-top:40px; --padding-left:16px; }
  .elementor-element-2b3c4d5 .elementor-heading-title{ font-size:30px; }
}
```

## Desktop values do not always land in the base block

Elementor emits the desktop value of *some* responsive controls inside a
**min-width** query rather than in the base rules. The container's `boxed_width`
is one:

```css
@media(min-width:768px){ .elementor-element-1a2b3c4{ --content-width:960px; } }
```

So "unsuffixed ⇒ base block" is not a safe assumption. It is safe for the
suffixed keys — those reliably land in their breakpoint's max-width query, which
is what makes them assertable.

## Making a widget full-width on mobile

Flex items default to `min-width: auto`, so a widget with a long description will
not shrink below its content width, and a three-across row wraps instead of
fitting. Give each child an explicit share, and override it on mobile:

```json
"_element_width": "initial",
"_element_custom_width":        { "unit": "%", "size": 31,  "sizes": [] },
"_element_custom_width_mobile": { "unit": "%", "size": 100, "sizes": [] }
```

`_element_custom_width` carries the condition `_element_width == "initial"` — set
the custom width without the mode and it is stored and ignored. `el.py common
--grep _element_width` shows both.
