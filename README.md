# elementor-headless

**Build Elementor pages by writing the JSON, not by driving the editor.**

An [Agent Skill](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
that gives an AI coding agent the complete Elementor authoring surface as a
queryable database — and proves every claim in it by rendering, clicking and
measuring on live sites, because Elementor never raises an error when you get
something wrong.

```
192 widgets · 13 elements · 49,857 control pairs
the Kit's 773 Site Settings · 48 page settings · 29 document types
51 dynamic tags · 39 display conditions · every repeater's item fields
```

English · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [한국어](README.ko.md)

---

## The problem

Elementor stores a page as a JSON tree in post meta. Write the tree and the page
exists. But Elementor **does not validate what you write** — it stores your value,
renders what it understands, and silently drops the rest.

There is no error. A misspelled control name, a string where an object belongs, a
Pro-only control on a Free site, a `hide_tablet: "yes"` that should have been
`"hidden-tablet"`: all of them save cleanly, and quietly do nothing. A page that
is 90% right looks exactly like a page that is 100% right until someone notices
the padding never applied.

An agent building Elementor pages therefore has two options: read Elementor's PHP
source every time (expensive, and it still doesn't tell you the JSON shape), or
guess (silently wrong). This skill is the third one:

```bash
$ python tools/el.py type slider
control type: slider   [FREE]  (elementor-core)

JSON value shape (what you write into _elementor_data settings):
  {"unit": "px", "size": "", "sizes": []}
```

## How it works

![architecture](assets/diagrams/architecture.svg)

Three phases. **Extraction** runs once per Elementor version, against a live
install, with three canaries that refuse to emit degraded data. **Verification**
renders every control, widget and interaction on live sites and folds what
actually happened back into the data. **Query** is all an agent ever does at
build time.

## Install

```bash
git clone https://github.com/Moksa1123/elementor-headless
cd elementor-headless
python tools/install-skill.py claude-code --global     # or: cursor, codex-cli, gemini-cli, ...
python tools/install-skill.py --list
```

8 platforms: Claude Code, Claude.ai, Cursor, Codex CLI, Gemini CLI, Devin
(ex-Windsurf), GitHub Copilot, Continue. Conventions re-verified 2026-07-11 —
[3 of the 8 had drifted in six weeks](references/multiplatform-install-verification.md),
so they are checked, not assumed. Upgrades prune what the previous version left
behind: an installer that leaves last year's wrong dataset next to this year's
right one is worse than no installer.

## Use

Look things up — one query costs ~700 tokens and answers completely:

```bash
python tools/el.py widgets --tier free --grep box    # find a widget
python tools/el.py widget heading --tab style        # its style controls, with every gate
python tools/el.py container --tab layout            # flex + grid, conditions included
python tools/el.py css border-radius                 # reverse lookup by CSS property
python tools/el.py type dimensions                   # the JSON value shape
python tools/el.py group typography                  # what a group control expands into
python tools/el.py tags --group post                 # dynamic tags (__dynamic__)
python tools/el.py page-settings                     # hide_title, CANVAS, page background
python tools/el.py kit --section section_global_colors   # Site Settings / global colors
python tools/el.py doctypes                          # legal _elementor_template_type values
python tools/el.py widgets --requires woocommerce    # what needs what to exist
python tools/el.py pro --check custom_css align      # exits 1 if any of these needs Pro
```

Then build, check, ship:

```bash
python tools/el.py skeleton > page.json
python tools/validate-page.py page.json --target free --have woocommerce
wp eval-file tools/apply-page.php 123 page.json page-settings.json
python tools/verify-live.py page.json https://your-site/your-page/
```

- `validate-page.py` catches what Elementor won't: unknown controls, wrong value
  shapes, illegal units, invalid options, duplicate ids, all three kinds of unmet
  dependency (including conditions evaluated against **defaults**, so setting
  `success_message` without `custom_messages` warns instead of silently falling
  back), multi-select values, `0`-as-number into class controls, Pro-only
  controls on a Free target, and **widgets the target site cannot have at all**.
- `apply-page.php` writes the 4 meta keys, the optional page settings (including
  the `template` → `_wp_page_template` split that Canvas actually needs), rebuilds
  the compiled CSS **and deletes the rendered-HTML cache** — skip that last one
  and a correct tree serves the previous page forever, with no error.
- `verify-live.py` fetches the public URL through the cache/CDN and asserts the
  tree, the CSS values and the wrapper classes against what actually came down
  the wire.

## Not every widget exists on every install

**The widget surface is a property of the SITE, not of Elementor.** The same
Elementor 4.1.4 / Pro 4.1.2 registers 148 widgets on one machine and 192 on
another, and nothing is broken — the extra ones need something the first machine
does not have. A schema without this is not incomplete, it is **wrong**: ask it
for `woocommerce-product-price` and it answers, with total confidence, that
Elementor has no such widget.

So every widget carries what it needs, read off its module's own `is_active()`
gate in Elementor's source — and the gate is authoritative, not the module's own
`EXPERIMENT_NAME` constant, which mislabelled 21 registered, rendering widgets
before that lesson was learned:

| Needs | Widgets |
|---|---|
| nothing — always there | 104 |
| `plugin:woocommerce` | 29 |
| a WP legacy widget some plugin registers | 33 |
| `experiment:container` / `nested-elements` / `e_atomic_elements` / … | 26 |

`validate-page.py` errors on a widget the target site cannot have; pass
`--have woocommerce nested-elements` to say what it does have.

**Elementor V4 atomic elements (`e-heading`, `e-flexbox`, `e-form-*`, 18 of them)
are a different data model** — type-tagged props and a separate `styles` array,
not `settings` + controls. The skill reports their prop schemas
(`el.py widget e-heading`) and refuses to pretend it can validate building them.

## Token cost, and time

**86.8% fewer tokens than reading Elementor's source. 99.4% fewer than loading
the schema. ~5× faster on model ingest, ~118× vs loading the schema.** Tool
latency is measured (median 316 ms per query); ingest time is derived from token
counts at a disclosed 1,000 tok/s reference rate — change the rate, the ratio
does not move. Reproduce it; the script writes `data/token-benchmark.csv`:

```bash
pip install tiktoken
python tools/benchmark-tokens.py --elementor-src /path/to/plugins/elementor
```

| Task | read source | load schema | **query** |
|---|---|---|---|
| Lay out a hero container (flex, boxed, responsive padding) | 20,182 | 1,082,477 | **1,209** |
| Style a heading (colour, typography, alignment) | 8,329 | 1,082,477 | **836** |
| Style a button (colour, padding, radius, hover) | 7,803 | 1,082,477 | **3,664** |
| Make any widget's spacing responsive | 11,800 | 1,082,477 | **264** |
| Find which control drives a CSS property | — | 1,082,477 | **363** |
| **Total** | **48,114** | **1,082,477** | **6,336** |

The saving used to be 89.1%. It went **down** — the schema grew from 583k to
1.08M tokens as the surface got honest (WooCommerce, the Kit, selectors, repeater
fields), and richer answers cost more tokens. Numbers that only ever improve are
being curated; these are regenerated by the script, whichever way they move.

Two things make it work: the data is **queried, never loaded**, and the 211
Advanced-tab controls every classic widget shares are **stored once instead of
168 times**. Token counts use tiktoken `cl100k_base` — OpenAI's tokenizer, not
Claude's, so absolute counts shift by roughly ±10%; ratios under one tokenizer
are stable, and the ratio is the claim
([token-efficiency.md](references/token-efficiency.md)).

## Free vs Pro is measured, not guessed

Elementor Pro **injects controls into free widgets**: the free Heading widget on
a Pro site carries Motion Effects, Sticky, Custom CSS, Display Conditions and
Custom Attributes. Inherit the widget's tier and all 46 get labelled "free" —
and the page you build renders perfectly for you, then loses its styling on a
Free install.

So the tier is measured: extract once with Pro loaded, once with
`wp --skip-plugins=elementor-pro` (affects only that one CLI process; safe on
production), and diff. Same method one axis further for WooCommerce, which does
not just add 29 widgets — it injects `product_query_exclude*` into Pro's own
loop widgets, and only a dump with WooCommerce off reveals whose controls those
are. Third-party pollution is excluded the same way: Rank Math injects into
`accordion`, Unlimited Elements into the container, and a schema extracted with
them loaded ships their controls as Elementor's.

Do not reason about tiers. **Border and Box Shadow look premium and are free.
`_attributes` looks basic and is Pro.** This repo shipped Border mislabelled as
Pro once, by reasoning instead of measuring. And Elementor core registers
**promo stubs named exactly like the real Pro widgets** when Pro is off — take
the Pro-less dump at face value and 26 Pro widgets read as free.

## Is it accurate? Make it prove it.

Don't trust it — test it. Eight checks, eight different questions, read out of
different artefacts: the control stack, the compiled stylesheet, the delivered
HTML, a real browser's computed styles, real pointer events, and the public URL
through the CDN. **A verifier only finds bugs in the channel it reads** — every
one of these exists because a greener check missed something real.

**1. Does the schema match your install?**

```bash
python tools/verify-schema.py mine.json --free-dump mine-free.json
```

Walks every (owner, control) pair, checks type and Free/Pro claims, and — because
the schema states each widget's requirements — separates "the schema is wrong"
from "this install doesn't have WooCommerce", instead of crying wolf about
either. PASSes against both extraction sites; exits non-zero on drift, so it can
gate a deploy.

**2. Does every CSS-driving control actually emit its CSS?**

Every control gets a value **unique to it** (a distinct hex colour, a distinct
pixel size), its dependency chain solved automatically, and its output asserted
in the stylesheet **the public URL delivered** — not a file off the server's
disk:

```
25,259 CSS-driving controls    99.4% covered, 0 failures
33,448 responsive suffixes     each asserted inside ITS media query, with a value
                               distinct from desktop's, so a leak cannot pass
```

Where Elementor's own metadata is wrong, the rendered result wins: 9 controls
advertise a responsive breakpoint they never emit, and the schema now says
`rwd-BROKEN` about them.

**3. Does every class-emitting control put its class on the wrapper?**

3,308 controls act by appending a wrapper class instead of emitting CSS — a
stylesheet check is structurally blind to all of them. Read out of the delivered
HTML: 99.8% swept, 0 failures, including the `classes_dictionary` legacy remaps
(`position: "top"` renders `elementor-position-block-start`) and the per-device
prefixes (`elementor-tablet-position-`, not a `_tablet` suffix).

**4. Does a real browser COMPUTE what was declared?**

A rule can be in the file and lose — to specificity, to the cascade, to a
selector that matches nothing. `sweep-browser.py` opens every page in Chromium
and compares Elementor's declaration against `getComputedStyle` **on the node
the rule actually targets** (which is what `data/css-selectors.csv` exists for):

```
48,873 probes across two live sites with different themes
25 of 26 override patterns IDENTICAL on both -> facts about Elementor,
   led by: _element_width's max-width is dead on every widget inside a
   container, killed by Elementor's own frontend.css at specificity (0,4,0)
 1 of 26 site-specific -> a fact about that theme, named by the data
```

**5. Does every widget, given content, actually render it?**

Unique markers seeded into every content control (repeater items built from the
extracted fields), **one widget per page** so a JS error or a zero-size render is
attributable to exactly one widget, element screenshot each, three viewports:

```
168/168 placeable widgets across the two sites
  126 rendered — marker echo, real site content, or hidden-by-design
   42 correctly empty without site context (cart/checkout/loop on a bare page)
    0 broken
```

**6. Do the interactive widgets actually interact?**

Real pointer events on the public page:

```
nested-tabs        click tab 2  -> content 2 shows, content 1 hides    PASS
nested-accordion   click item 2 -> <details> opens                     PASS
accordion          click item 2 -> body becomes visible                PASS
toggle             click item 1 -> body toggles open                   PASS
image-carousel     click next   -> active slide advances               PASS
```

And the `:hover` rules — unverifiable by any static read — are driven by an
actual pointer: 3,882 probes, 297 verified by value; all 113 overrides are
same-element seed collisions (two hover controls writing the same property with
deliberately different values — one must lose), classified per-row. Transitions
are disabled first and the intervention disclosed: a colour read 200 ms into a
seeded 79-second transition is a mid-animation frame, not a verdict.

**7. Do the workflows hold end to end?**

Each of these built headlessly, then verified in a browser on the live site:

- **Global colors**: a colour appended to the kit's `custom_colors`, referenced
  via `__globals__`, computes to exactly that colour
- **Dynamic tags**: a `post-title` binding delivers the post's real title
- **Display conditions**: a `logged_in`-conditioned element is absent from the
  anonymous HTML — dropped server-side, not hidden by CSS
- **Theme Builder**: a header scoped to one page renders there and nowhere else
- **Popups**: a `page_load`-triggered popup opens in an anonymous browser
- **Loop Builder**: a loop-item template + loop-grid renders three real posts
- **Forms**: anonymous fill → nonce → database row → custom success message
- **Canvas**: `template: elementor_canvas` drops the theme chrome (via
  `_wp_page_template`, which page settings alone do not reach)
- **Templates**: export/import through Elementor's own JSON format, media
  rehosted by its own hooks

**8. Does the page the PUBLIC gets contain all of it?**

```bash
python tools/verify-live.py examples/demo-page.json https://moksaweb.com/elementor-headless-demo/
```

Fetches the public URL and **every stylesheet that page links** (a page's styling
is split across several files — the Kit's globals live in a different one),
through the edge cache, and asserts tree + CSS values + wrapper classes. It
fails on a tampered tree — a verifier that has never gone red is not a verifier.

The demo page is real, published, and has never been opened in the editor:
**https://moksaweb.com/elementor-headless-demo/**

## The traps

The naive way to do any of this is wrong in **eleven numbered ways** — each one
shipped in this repo before being caught, each now a canary, a validator rule or
a data field. Full write-ups in
[extraction-traps.md](references/extraction-traps.md):

1. WP-CLI gets a stripped control stack — 46% of controls vanish silently
2. Responsive is two mechanisms; `padding_tablet` has no control object and works
3. A control's tier is not its widget's tier — Pro injects into free widgets
4. A control is gated three ways; 661 controls die on an empty interpolated value
5. Responsive dependencies are re-checked at the breakpoint
6. `is_responsive` over-promises — only rendering knows
7. CSS is only half of what a control can do — 3,308 emit classes instead
8. A class value is remapped, and its device prefix is a different string
9. Writing `_elementor_data` leaves a stale rendered-HTML cache — a correct tree
   serves the previous page, and a 17k-control sweep ran green over it
10. The widget surface is a property of the install, not of Elementor
11. A rule can be in the stylesheet and LOSE — only a browser sees it

Plus the ones documented where they live: the Canvas `template` setting is
stored in `_wp_page_template`, not page settings; a library template needs the
`elementor_library_type` **taxonomy** and the conditions **cache**, or Theme
Builder never sees it; `theme-*` widgets get their dynamic binding from the
editor at insert time, so headless trees write `__dynamic__` themselves; WP
legacy bridges take everything under `settings.wp`; `e_display_conditions` is an
array wrapping a JSON **string**, and the bare array the docs used to show
stores fine and is silently ignored.

## What's in the box

```
data/
  elementor-schema.json      the full surface - queried, never loaded
  controls.csv               every (owner, control) pair, greppable
  common-controls.csv        the 211 shared by every classic widget
  pro-only-controls.csv      the safety table       pro-only-widgets.csv
  control-types.csv          all value shapes       group-controls.csv
  widgets.csv                incl. per-widget requirements
  dynamic-tags.csv           the __dynamic__ surface, 51 tags
  css-selectors.csv          which node each control's CSS actually lands on
  control-verification.csv   per-control: does it emit the CSS it claims?
  class-verification.csv     per-control: does it emit the CLASS it claims?
  browser-verification*.csv  per-control: does Chromium COMPUTE it? (2 sites)
  widget-verification.csv    per-widget: does it render its content? (168)
  hover-verification.csv     per :hover rule, driven by a real pointer
  token-benchmark.csv        reproducible token AND latency measurements

tools/
  el.py                      query the schema - the front door
  validate-page.py           pre-flight a tree, incl. what the target site can have
  apply-page.php             meta + page settings + CSS rebuild + HTML-cache purge
  extract-elementor-schema.php   dump a live install (3 canaries)
  build-indexes.py           dumps + sweep results -> shipped data
  verify-schema.py           does the schema match your install?
  verify-render.py           does Elementor emit what was promised?
  verify-live.py             does the PUBLIC page have it, through the CDN?
  verify-browser.py          does Chromium COMPUTE it, on the right node?
  verify-interactions.py     do tabs switch, accordions open, carousels advance?
  sweep-controls.py          every CSS control, delivered stylesheet
  sweep-classes.py           every CLASS control, delivered HTML
  sweep-browser.py           declared vs computed, every control, in Chromium
  sweep-widgets.py           every widget functionally, one per page, screenshots
  sweep-hover.py             every :hover rule, real pointer
  sweep-frontend.sh          capture what the public URL actually serves, per batch
  export-template.php        Elementor's own JSON format out
  import-template.php        and back in, media handled by Elementor's own hooks
  benchmark-tokens.py        reproduce the token and time numbers
  install-skill.py           8-platform installer, prunes stale files

references/   data-model · control-types · containers-and-layout · responsive
              templates-and-conditions · import-export · extraction-traps
              token-efficiency · multiplatform-install-verification
examples/     demo-page.json - the published proof page
```

## Honest limits

- **Elementor V4 atomic elements**: query-only. Building them is a different
  data model this skill does not yet write.
- **Context-dependent widgets** (cart, checkout, post comments, product parts)
  verify as "correctly empty" on a bare page; their full behaviour needs a store
  or post context no sweep fabricates.
- **Version-bound**: every number here was measured on Elementor 4.1.4 /
  Pro 4.1.2. New versions can invalidate any of it — which is why every
  verifier ships and re-runs against *your* install.
- Popup triggers beyond `page_load`, form actions beyond `save-to-database`,
  and third-party addon widgets are extracted but not E2E-verified.

## Regenerate for your install

```bash
# three dumps, ONE axis changing at a time - see CLAUDE.md for why this matters
wp --skip-plugins="<all but elementor,elementor-pro,woocommerce>" eval-file tools/extract-elementor-schema.php core+pro > iso-woo.json
wp --skip-plugins="<all but elementor,woocommerce>"               eval-file tools/extract-elementor-schema.php core+pro > iso-free-woo.json
wp --skip-plugins="<all but elementor,elementor-pro>"             eval-file tools/extract-elementor-schema.php core+pro > iso-pro.json

python tools/build-indexes.py iso-woo.json --free-dump iso-free-woo.json \
    --gated-dump woocommerce=iso-pro.json \
    --verification data/control-verification.csv \
    --class-verification data/class-verification.csv --out data/
python tools/verify-schema.py iso-woo.json --free-dump iso-free-woo.json   # must exit 0
```

## Reuse blocks across pages and sites

```bash
wp eval-file tools/export-template.php <post_id> > hero-block.json
wp --user=1 eval-file tools/import-template.php hero-block.json
```

Never move a block between sites by copying `_elementor_data`: media controls
store attachment **ids**, and an id means a different image on the other site.
These tools go through Elementor's own import path so its `on_import` hooks
re-download the media. And `[elementor-template id="123"]` embeds any saved
template in any WordPress content — including nesting blocks into pages without
Pro, via the free shortcode widget.

## Contributing

Re-extract against a newer Elementor and open a PR with the regenerated `data/`
— `verify-schema.py` will tell you exactly what changed. See
[CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT. Built and maintained by **moksa** · [moksaweb.com](https://moksaweb.com)

Sibling skill: [rankmath-seo-wp](https://github.com/moksa1123/rankmath-seo-wp)
