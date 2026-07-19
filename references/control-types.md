# Control types: the JSON shape you have to write

Every value in `settings` has a shape dictated by its control's **type**. Get the
shape wrong and Elementor stores your value and ignores it — no error, no warning,
the styling just does not appear.

This is the single most common way headless Elementor work fails, and it is
entirely avoidable: the shapes are not a matter of opinion, they come from
Elementor's own `Control_Base::get_default_value()`. All 56 are in
`data/control-types.csv`; ask for one with:

```bash
python tools/el.py type slider
python tools/el.py types          # all of them
```

## The shapes that are objects

These are the ones people get wrong, because the obvious guess is a string.

| Type | Shape | Wrong guess |
|---|---|---|
| `dimensions` | `{"unit":"px","top":"","right":"","bottom":"","left":"","isLinked":true}` | `"10px"` |
| `slider` | `{"unit":"px","size":"","sizes":[]}` | `20` |
| `gaps` | `{"column":"","row":"","isLinked":true,"unit":"px"}` | `"20px"` |
| `box_shadow` | `{"horizontal":0,"vertical":0,"blur":10,"spread":0,"color":"rgba(0,0,0,0.5)"}` | a CSS string |
| `text_shadow` | `{"horizontal":0,"vertical":0,"blur":10,"color":"rgba(0,0,0,0.3)"}` | a CSS string |
| `url` | `{"url":"","is_external":"","nofollow":"","custom_attributes":""}` | `"https://…"` |
| `media` | `{"url":"","id":"","size":""}` | a URL string |
| `icons` | `{"value":"fas fa-star","library":"fa-solid"}` | `"fas fa-star"` |
| `image_dimensions` | `{"width":"","height":""}` | |

`repeater`, `gallery`, `conditions_repeater`, `form-fields-repeater`,
`nested-elements-repeater`, `global-style-repeater`, `fields_map`, `wp_widget`
take **lists**.

Everything else (`text`, `textarea`, `wysiwyg`, `color`, `select`, `choose`,
`number`, `code`, `hidden`, `font`, `query`…) takes a plain string.

## switcher is not a boolean

```json
"grid_outline": "yes"    // on
"grid_outline": ""       // off
```

`true` / `false` do nothing. The "on" value is the control's `return_value`,
which is `"yes"` almost always but not by law — `el.py` prints it when it differs.

## select / choose: the key, not the label

Write the option **key**. `el.py` lists them as `opts:`.

Two traps:

- PHP turns numeric-looking array keys into ints, so a font-weight option map
  arrives as `[100, 200, …, 900, "", "normal", "bold"]`. Elementor itself stores
  the chosen value as the **string** `"700"`, and that works. Compare as strings.
- **Options change between versions.** The Icon Box `position` control took
  `top|left|right` in Elementor 3.x. In 4.x it is
  `inline-start|inline-end|block-start|block-end` (CSS logical properties), and
  `"top"` is now simply an unknown value that gets ignored. This was caught by
  `validate-page.py` on a real page during development — the schema knew, and the
  guess did not.

## Units are constrained, per control

A `slider` or `dimensions` control declares which units it accepts. They are not
all the same:

```
container.padding             px, %, em, rem, vw, custom
heading.typography_font_size  px, em, rem, vw, custom     <- no %
```

Writing `{"unit":"pt", …}` is a silent no-op. The schema carries `units` per
control and `validate-page.py` enforces it.

## Group controls: one call, many flat keys

A group control is a bundle registered under a prefix, and it lands in `settings`
as **flat keys named `{prefix}_{field}`** — never as a nested object.

```bash
python tools/el.py group typography
python tools/el.py groups          # all 16
```

Adding `Group_Control_Typography` with prefix `title` produces
`title_typography`, `title_font_family`, `title_font_size`, `title_font_weight`, …

**Group controls have a master switch, and forgetting it is a classic silent
failure.** Every field in the typography group carries the condition
`typography_typography != ""`. So this does nothing:

```json
"typography_font_size": { "unit": "px", "size": 46, "sizes": [] }
```

and this works:

```json
"typography_typography": "custom",
"typography_font_size": { "unit": "px", "size": 46, "sizes": [] }
```

`el.py` shows the condition as `needs:{"typography_typography!":""}` and
`validate-page.py` warns when it is unmet.

### The 16 group controls, and who owns them

| Group | Tier | Fields |
|---|---|---|
| `background` | free | 35 |
| `typography` | free | 9 |
| `border` | free | 3 (`_border`, `_width`, `_color`) |
| `box-shadow` | free | 2 |
| `text-shadow` | free | 1 |
| `text-stroke` | free | 2 |
| `css-filter` | free | 5 |
| `image-size` | free | 2 |
| `flex-container` | free | 9 |
| `grid-container` | free | 12 |
| `flex-item` | free | 8 |
| `motion_fx` | **PRO** | 36 |
| `posts` | **PRO** | 3 |
| `query-group` | **PRO** | 22 |
| `related-query` | **PRO** | 22 |
| `taxonomy-query` | **PRO** | 22 |

**Border and Box Shadow are free.** They look premium and they are core — this
repo shipped them mislabelled as Pro once, on the reasoning that they "feel"
advanced, before measuring. Do not reason about tiers; measure them
([extraction-traps.md](extraction-traps.md#trap-3--a-controls-tier-is-not-its-widgets-tier)).

## Conditions: stored, then ignored

Most controls only take effect when another setting has a particular value.
`el.py` prints these as `needs:`. The syntax has three forms:

```
"background_background": ["classic","gradient"]   value must be one of these
"typography_typography!": ""                      trailing ! = must NOT equal
"selected_icon[value]!": ""                       index into the value object
```

An unmet condition is not an error. The value is written to the database, kept
there forever, and skipped at render. `validate-page.py` evaluates all three forms
against the element's own settings and warns.

## Icons must be names Elementor knows

`icons` takes `{"value": "<class>", "library": "<library>"}`. Elementor bundles
**Font Awesome 5** and renders those as inline SVG. Hand it a Font Awesome 6-only
name and it falls back to emitting `<i class="fas fa-shield-halved">`, relying on
a webfont that is not enqueued — so the icon renders as **nothing at all**, and
the surrounding box still draws.

```json
"selected_icon": { "value": "fas fa-shield-alt",    "library": "fa-solid" }   // FA5 - renders
"selected_icon": { "value": "fas fa-shield-halved", "library": "fa-solid" }   // FA6 - invisible
```

This one is not catchable from the control schema — the control accepts any
string. It was caught by looking at the rendered page, which is why the workflow
ends with a render check and not with a validator.
