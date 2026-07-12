---
name: elementor-headless
description: Build and modify Elementor pages by writing the underlying JSON directly - no visual editor, no DOM. Use when creating or editing Elementor pages, containers, widgets, templates, display conditions, responsive breakpoints, or custom CSS; when you need a control's exact name, its JSON value shape, its allowed options/units, or the CSS it drives; or when you need to know whether something requires Elementor Pro. Triggers on - elementor, _elementor_data, container, flex container, grid container, elementor widget, elementor control, elementor template, display conditions, theme builder, responsive breakpoint, tablet, mobile, motion effects, sticky, custom css, dynamic tags, global colors, elementor pro.
license: MIT
---

# Headless Elementor

Build Elementor pages by writing the data model directly. The editor is one client
of that data model; it is not the format, and you do not need it.

**Scope: page construction.** Not site health checks, not plugin audits, not media
cleanup. If a task is not "make this page exist / look like this", it is out of
scope.

## The one rule that overrides everything

**Never write a control name, value shape, option, unit or Free/Pro claim from
memory. Look it up.** Elementor accepts anything you put in `_elementor_data` — it
stores your value, renders what it understands, and silently drops the rest. There
is no error. A page that is 90% right looks exactly like a page that is 100% right
until someone notices the padding never applied.

Everything in `data/` was extracted from a live Elementor install and then
**rendered and checked, one control at a time** - written into real pages, compiled
by Elementor, and asserted against the stylesheet that came out. Each control got a
value unique to it, so a pass means *that* control produced *that* value.

```
DESKTOP     18,853 CSS-driving controls   99.1% covered   0 failures
RESPONSIVE  25,404 _tablet/_mobile keys   96.7% verified by value
```

Where Elementor's own metadata turned out to be wrong, **the rendered result wins**:
9 controls advertise a responsive breakpoint they never actually emit, and the
schema now says so. Per-control results ship in `data/control-verification.csv`.
Your memory of Elementor has not been through any of this.

## A control can be gated four different ways

Setting a control is not enough to make it do anything, and when it does nothing
there is no error. `el.py` prints every gate it has:

| Shown as | What it means |
|---|---|
| `needs:{...}` | the simple `condition` — another setting must have a given value |
| `needs-adv:...` | the **advanced** `conditions` form — a boolean tree with `and`/`or` and operators (`>`, `!==`, `in`). **152 controls are gated only this way and have no `condition` at all** |
| `needs-value-of:a,b` | not a condition. This control's CSS interpolates `a` and `b`, and **Elementor throws away the whole declaration if either is empty** — however satisfied the conditions are. 499 controls do this |
| `rwd-BROKEN:tablet` | Elementor says the `_tablet` suffix is legal. Rendering says it emits nothing. Believe the rendering |

The third is the quiet killer. Set `background_background: "gradient"` plus
`background_gradient_angle`, satisfy every documented condition, and you still get
no gradient — because the declaration interpolates `background_color`, which you
never set.

And **when you set `X_tablet`, set `_tablet` on everything X depends on too.** If a
control and its dependency are both responsive, Elementor checks the dependency's
*tablet* value when building the tablet rule. Miss it and desktop renders perfectly
while tablet is silently blank.

```bash
python tools/validate-page.py page.json     # catches all of them before you write
```

Detail: [extraction-traps.md](references/extraction-traps.md).

## Look it up like this

```bash
python tools/el.py stats                          # what version, what's in here
python tools/el.py widgets --tier free --grep box # find a widget
python tools/el.py widget heading --tab style     # one widget's style controls
python tools/el.py container --tab layout         # the container's layout surface
python tools/el.py common --grep padding          # the 211 controls every widget shares
python tools/el.py type slider                    # the JSON value shape of a control type
python tools/el.py group typography               # what a group control expands into
python tools/el.py css border-radius              # which control drives this CSS property
python tools/el.py breakpoints                    # the responsive suffixes
python tools/el.py skeleton                       # a minimal valid page tree
python tools/el.py pro                            # everything that needs Elementor Pro
python tools/el.py pro --check custom_css align   # exits 1 if any of these needs Pro
```

Add `--json` to any of them for machine-readable output.

**Never read `data/elementor-schema.json` into context.** It is 583,555 tokens. It
is a database; `el.py` is the query. One query is ~700 tokens and answers the
question completely. `data/*.csv` are there for `grep` when you want to scan.

## Which lookup answers which question

| You need to know | Ask |
|---|---|
| what widgets exist | `el.py widgets` · `data/widgets.csv` |
| a widget's control names | `el.py widget <name> [--tab style]` |
| the container's flex/grid settings | `el.py container --tab layout` |
| what shape a value takes in JSON | `el.py type <control_type>` · `data/control-types.csv` |
| what a group control expands to | `el.py group <name>` · `data/group-controls.csv` |
| padding / margin / motion FX / custom CSS | `el.py common` — they're on every widget |
| whether `X_tablet` is legal | `el.py widget <name> --grep X` → look for `rwd:` |
| which control changes a CSS property | `el.py css <property>` |
| **whether something needs Pro** | `el.py pro --check <controls>` · `data/pro-only-controls.csv` |

## Build a page

```bash
python tools/el.py skeleton > page.json         # start from something valid
# ...edit it, looking every control up as you go...

python tools/validate-page.py page.json --target free   # BEFORE writing anything
wp eval-file tools/apply-page.php <post_id> page.json   # writes meta + rebuilds CSS
```

`validate-page.py` is not optional. It catches what Elementor will not: unknown
control names, wrong value shapes, illegal units, invalid select options, duplicate
element ids, all three kinds of unmet dependency, and Pro-only controls on a Free
target.

## Reuse a block across pages and across sites

Elementor's own JSON interchange format — the same one behind the editor's Export /
Import Template buttons — so a block built here imports cleanly anywhere.

```bash
wp eval-file tools/export-template.php <post_id> > hero-block.json

wp --user=1 eval-file tools/import-template.php hero-block.json                  # into the library
wp --user=1 eval-file tools/import-template.php hero-block.json <target_post_id> # onto a page
```

**Never move a block between sites by copying `_elementor_data`.** Media controls
store an attachment `id`, and that id means a *different image* on the other site —
or nothing. Elementor's `on_export` swaps the id for a url and `on_import`
re-downloads it into the target site's media library. Copy the raw meta and the
images silently break or, worse, silently become the wrong images. These tools call
Elementor's own import path precisely to get those hooks.

Import needs a user (`--user=1`); WP-CLI has none by default and Elementor's
importer does a capability check.

Detail: [import-export.md](references/import-export.md).

## Free vs Pro: label it, do not reason about it

**Mandatory:** every architecture note, code sample and comment must state
explicitly which features, APIs and parameters are **Elementor Pro only**. Never
let Free and Pro blur together.

And never infer a tier from how advanced something looks. Border and Box Shadow
feel premium and are **free**. `_attributes` (custom HTML attributes) feels basic
and is **Pro**. This repo shipped Border mislabelled as Pro once, by reasoning
instead of measuring.

The tier in `data/` is **measured**: extract once normally, once with
`wp --skip-plugins=elementor-pro`, then diff. On 4.1.4 + Pro 4.1.2:

- **71 of 135 widgets are Pro.**
- **Pro injects 46 controls into *every* widget, free ones included:** all
  `motion_fx_*` (37), `sticky*` (6), `custom_css`, `_attributes`,
  `e_display_conditions`.
- Pro adds **79 controls to the container**, 78 to section, 73 to column.
- Pro-only group controls: `motion_fx`, `posts`, `query-group`, `related-query`,
  `taxonomy-query`.

A Pro-only control on a free widget is the classic silent failure: it saves, it
renders for you, and it does nothing on a site without Pro. Run
`el.py pro --check` before shipping to a site you do not control.

## The data model, briefly

`_elementor_data` is a JSON list of top-level elements. Each node:

```json
{ "id": "1a2b3c4", "elType": "container", "settings": {}, "elements": [] }
```

- `id` — unique 7-char lowercase **hex**; duplicates break the editor
- `elType` — `container` | `section` | `column` | `widget`
- widgets need **both** `elType: "widget"` and `widgetType`
- **every** node needs `elements` (use `[]` on leaves, widgets included)
- `settings` is **flat** — `padding`, not `advanced.layout.padding`

Three more meta keys are required or the page renders as if Elementor were not
installed: `_elementor_edit_mode = builder`, `_elementor_template_type`,
`_elementor_version`. Then the compiled CSS must be rebuilt or the page ships the
old stylesheet. `apply-page.php` does all of it.

Responsive is a naming convention: `padding` → `padding_tablet` → `padding_mobile`.
Only **active** breakpoints exist (`el.py breakpoints`).

## Reference

| Doc | What's in it |
|---|---|
| [data-model.md](references/data-model.md) | the tree, the 4 meta keys, `__globals__`, `__dynamic__`, the active Kit, caches |
| [control-types.md](references/control-types.md) | all 59 value shapes, group controls, conditions, units, the icon-name trap |
| [containers-and-layout.md](references/containers-and-layout.md) | container flex + grid, sizing children, section/column legacy |
| [responsive.md](references/responsive.md) | breakpoints, suffixes, why `padding_tablet` has no control object |
| [templates-and-conditions.md](references/templates-and-conditions.md) | template CRUD, Display Conditions, priority resolution — **Pro** |
| [import-export.md](references/import-export.md) | Elementor's JSON interchange format; moving blocks across sites without breaking media |
| [extraction-traps.md](references/extraction-traps.md) | the three ways a schema goes silently wrong, and how this one is verified |
| [token-efficiency.md](references/token-efficiency.md) | the 89% figure, measured, with the script that reproduces it |

## Verify it rather than trusting it

The schema was extracted from Elementor 4.1.4 / Pro 4.1.2. Yours may differ. Make
it prove itself against your install:

```bash
wp eval-file tools/extract-elementor-schema.php core+pro > mine.json
wp --skip-plugins=elementor-pro eval-file tools/extract-elementor-schema.php core+pro > mine-free.json
python tools/verify-schema.py mine.json --free-dump mine-free.json    # exits 1 on drift
```

If it fails, re-extract: `build-indexes.py` regenerates every data file and the
skill then describes *your* Elementor.

Live proof, built headlessly and published:
**https://moksaweb.com/elementor-headless-demo/** — `examples/demo-page.json`,
94/94 CSS assertions passed under `verify-render.py`.

## Tools

| Tool | Does |
|---|---|
| `el.py` | query the schema — **the front door** |
| `validate-page.py` | pre-flight a page tree before writing it |
| `apply-page.php` | write the tree + meta, rebuild CSS, back up the old one |
| `extract-elementor-schema.php` | dump a live install's full control surface |
| `build-indexes.py` | turn a dump into the shipped data files |
| `verify-schema.py` | does the schema match your install? |
| `verify-render.py` | does Elementor emit the CSS the schema promised? |
| `sweep-controls.py` | render EVERY control and assert it works (16,778 asserted, 0 failures) |
| `export-template.php` | export a page/template to Elementor's own JSON format |
| `import-template.php` | import one, with media, via Elementor's own import path |
| `benchmark-tokens.py` | reproduce the token numbers |
| `install-skill.py` | install into 8 AI platforms |
