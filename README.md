# elementor-headless

**Build Elementor pages by writing the JSON, not by driving the editor.**

An [Agent Skill](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
that gives an AI coding agent the complete Elementor authoring surface —
**49,857 controls across 192 widgets and 13 elements** — as a queryable database
instead of a document it can never afford to read.

Every widget also carries **what a site must have for it to exist at all**: 29 need
the WooCommerce plugin, 36 need an Elementor experiment. A schema that omits that is
not incomplete, it is wrong — ask it for `woocommerce-product-price` and it tells you,
with total confidence, that Elementor has no such widget.

English · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [한국어](README.ko.md)

---

## Why

Elementor stores a page as a JSON tree in post meta. Write the tree and the page
exists. But Elementor **does not validate what you write** — it stores your value,
renders what it understands, and silently drops the rest.

There is no error. A misspelled control, a string where an object belongs, a
Pro-only control on a Free site: all of them save cleanly, render fine on your
machine, and quietly do nothing where it matters.

So an agent building Elementor pages has two options: read Elementor's PHP source
every time (expensive — and it still doesn't tell you the JSON shape), or guess
(silently wrong). This skill is the third one.

```bash
$ python tools/el.py type slider
control type: slider   [FREE]  (elementor-core)

JSON value shape (what you write into _elementor_data settings):
  {"unit": "px", "size": "", "sizes": []}
```

## How it works

![architecture](assets/diagrams/architecture.svg)

Three phases. Extraction runs once per Elementor version, against **your** site.
Everything after that is a query.

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
so they are checked, not assumed.

## Use

```bash
python tools/el.py widgets --tier free --grep box   # find a widget
python tools/el.py widget heading --tab style       # its style controls
python tools/el.py container --tab layout           # flex + grid, with conditions
python tools/el.py css border-radius                # reverse lookup by CSS property
python tools/el.py group typography                 # what a group control expands into
python tools/el.py breakpoints                      # the responsive suffixes
python tools/el.py pro --check custom_css align     # exits 1 if any of these needs Pro
```

Then build, check, ship:

```bash
python tools/el.py skeleton > page.json
python tools/validate-page.py page.json --target free
wp eval-file tools/apply-page.php 123 page.json
```

`validate-page.py` catches what Elementor won't: unknown control names, wrong value
shapes, illegal units, invalid options, duplicate ids, unmet conditions, and
Pro-only controls on a Free target.

## Token cost

**89.1% fewer tokens than reading Elementor's source. 99.1% fewer than loading the
schema.** Reproduce it — the script writes `data/token-benchmark.csv`:

```bash
pip install tiktoken
python tools/benchmark-tokens.py --elementor-src /path/to/plugins/elementor
```

| Task | read source | load schema | **query** |
|---|---|---|---|
| Lay out a hero container (flex, boxed, responsive padding) | 20,182 | 583,555 | **964** |
| Style a heading (colour, typography, alignment) | 8,329 | 583,555 | **730** |
| Style a button (colour, padding, radius, hover) | 7,803 | 583,555 | **2,935** |
| Make any widget's spacing responsive | 11,800 | 583,555 | **243** |
| Find which control drives a CSS property | — | 583,555 | **363** |
| **Total** | **48,114** | **583,555** | **5,235** |

Two things make it work: the data is **queried, never loaded**, and the 211
Advanced-tab controls that every widget shares are **stored once instead of 135
times** — they are 75.6% of all rows, so factoring them out shrinks the schema by
73.2%.

Measured with tiktoken `cl100k_base` — OpenAI's tokenizer, not Claude's, so
absolute counts shift by roughly ±10%. Ratios between two texts under the same
tokenizer are stable, and the ratio is the claim. Method and caveats:
[token-efficiency.md](references/token-efficiency.md).

## Free vs Pro is measured, not guessed

Elementor Pro **injects controls into free widgets**. Open the free Heading widget
on a site with Pro and you'll find Motion Effects, Sticky, Custom CSS, Display
Conditions and Custom Attributes sitting in its Advanced tab. Inherit the widget's
tier and every one of them gets labelled "free" — and the page you build renders
perfectly for you, then loses its styling on a Free install.

So the tier is measured. Extract twice — once with Pro loaded, once with
`wp --skip-plugins=elementor-pro` (which affects only that one CLI process; nothing
is deactivated, so it is safe on production) — and diff:

| | Free 4.1.4 | + Pro 4.1.2 |
|---|---|---|
| widgets | 64 | **135** |
| controls on every widget | 165 | **211** (+46) |
| controls on `container` | 277 | **356** (+79) |
| control types | 52 | **59** |
| group controls | 11 | **16** |

The 46 that Pro injects into **every** widget: all `motion_fx_*` (37), `sticky*`
(6), `custom_css`, `_attributes`, `e_display_conditions`.

Do not reason about tiers. **Border and Box Shadow look premium and are free.
`_attributes` looks basic and is Pro.** This repo shipped Border mislabelled as Pro
once, by reasoning instead of measuring.

## Is it accurate? Make it prove it.

The schema came from Elementor 4.1.4 / Pro 4.1.2. Yours may differ. Don't trust it
— test it. Five checks, five different questions, read out of five different artefacts.

**1. Does the schema match your install?**

```bash
wp eval-file tools/extract-elementor-schema.php core+pro > mine.json
wp --skip-plugins=elementor-pro eval-file tools/extract-elementor-schema.php core+pro > mine-free.json
python tools/verify-schema.py mine.json --free-dump mine-free.json
```

```
checked 37,964 (owner, control) pairs from the shipped schema
Free/Pro claims checked on free widgets/elements: 15,969
FAILURES: 0
PASS
```

Exits non-zero on drift, so it can gate a deploy.

**2. Does a page built from the schema render the CSS the schema promised?**

The schema says which CSS properties each control drives. This builds the page for
real, reads back the stylesheet Elementor compiled, and checks every one — including
that each responsive key landed inside *that breakpoint's* media query.

```bash
python tools/verify-render.py examples/demo-page.json rendered.css --post-id 9176
```

```
CSS property assertions: 94/94 passed
PASS
```

**3. Does EVERY control in the schema actually work?**

`verify-render.py` only covers the controls a given page happens to use — 94, on the
demo page. `sweep-controls.py` covers the rest: it synthesises a legal value for
every control that claims to drive CSS, solves the dependency chain needed to make
it take effect, renders it, and asserts the value came out. Each control gets a
value **unique to it** (a distinct hex colour, a distinct pixel size), so a pass
means *that control* produced *that value* — not that something wrote a similar
property.

```bash
python tools/sweep-controls.py plan --out sweep/ --post-id <draft post>
# apply each batch, capture post-<id>.css
python tools/sweep-controls.py check sweep/ --out data/control-verification.csv
```

```
DESKTOP  (18,853 CSS-driving controls)
  verified by value   17,421  (92.4%)   the exact value we wrote is in the CSS
  property only        1,270  ( 6.7%)   right property, value not literally assertable
  FAILED                   0  ( 0.0%)
  skipped, untested      162  ( 0.9%)   no test could be built for these
  covered                      99.1%

RESPONSIVE SUFFIXES  (25,404 _tablet / _mobile keys, each asserted inside ITS
                      breakpoint's media query, with a value distinct from
                      desktop's, so a leak cannot pass)
  verified by value   24,568  (96.7%)
  FAILED                  17  ( 0.1%)
```

Per-control results ship in `data/control-verification.csv` - including the
`skipped` ones, so the coverage number can never be read without them.

**And the sweep corrects the extractor.** `build-indexes.py --verification` folds
the rendered result back into the schema: 9 controls advertise a responsive
breakpoint they never emit (`hotspot.width_tablet` produces no CSS at all, verified
in isolation). They are now flagged `responsive_broken`, `el.py` prints
`rwd-BROKEN:`, and `validate-page.py` errors if you write one. Without rendering,
all 9 would still be in the schema as working responsive controls.

**4. Sweep every control that emits a CLASS instead of CSS.** A stylesheet sweep
cannot see these at all — and there are 2,573 of them (`_position`, `hide_tablet`,
every `view` / `shape` / `align` control, the transforms). This one reads the
**rendered HTML** and asserts the class on the wrapper.

```bash
python tools/sweep-classes.py plan --out classsweep/ --post-id <draft post>
bash classsweep/RUN.sh
python tools/sweep-classes.py check classsweep/ --out data/class-verification.csv
```

```
CLASS-EMITTING CONTROLS  (2,573)
  verified by class     2,042  (79.4%)   the class we predicted is on the wrapper
  FAILED                    0  ( 0.0%)
  host never rendered     523  (20.3%)   the WIDGET produces no markup on a bare page,
                                         so there is no wrapper - not a pass, not a fail
  skipped, untestable       8  ( 0.3%)
PER-DEVICE CLASS PREFIXES  306    246 verified
classes_dictionary REMAPS   10     10 verified
```

Running it found three things nothing else could:

- **`apply-page.php` was leaving a stale rendered-HTML cache.** Elementor keeps the
  markup it rendered in a `_elementor_element_cache` post meta and serves it straight
  back. Its own save path clears it; writing the meta directly does not. So the post
  updated, the CSS rebuilt correctly, `_elementor_data` read back exactly right — and
  the page kept serving the **previous markup**, with no error. The CSS sweep ran green
  across 17,421 controls with this bug live, because CSS is a separate file we always
  rebuilt. The first HTML sweep caught it in a minute: all 14 batches came back
  byte-identical.
- **`validate-page.py` was rejecting a page that renders perfectly.** `icon-box`
  `position: "top"` is not in the option list, and Elementor's `classes_dictionary`
  remaps it to `block-start` anyway. A false error, now a note.
- **The schema was claiming the wrong class on tablet.** A responsive class control
  has a *different prefix per device* (`elementor-tablet-position-`, not a `_tablet`
  suffix), and the extractor had been collapsing the variants and throwing the device
  prefixes away.

**5. Verify the page the PUBLIC gets.** Everything above reads an artefact from
inside the machine — a CSS file off the server's disk, HTML out of a PHP call.
**None of it is what a visitor receives.** The theme, the page cache, Varnish and
the CDN all sit in between, and any of them can serve something else while every
server-side check stays green. That is Trap 9 one layer further out.

```bash
python tools/verify-live.py examples/demo-page.json https://moksaweb.com/elementor-headless-demo/
```

```
GET https://moksaweb.com/elementor-headless-demo/
    113,397 bytes   x-cache=HIT  age=200
GET .../elementor/css/post-11.css      1,238 bytes     <- the Kit's globals
GET .../elementor/css/post-9176.css    5,411 bytes     <- the page
GET .../elementor/css/post-47.css      9,009 bytes
GET .../elementor/css/post-52.css     18,470 bytes
    -> 4 stylesheet(s), 34,131 bytes total

elements delivered      : 8/8
CSS properties delivered: 94  (across 46 settings)
  value-exact           : 43  (the exact value this tree asks for is in the delivered CSS)
  property only         : 3  (Elementor rewrites the value; the sweep already proved which)
wrapper-class assertions: 17 passed
not assertable          : 24 settings drive neither CSS nor a class

PASS - the page a visitor receives contains every element of the tree,
       the stylesheet it links carries every property the schema promised,
       and every wrapper carries the classes it should.
```

Note the four stylesheets. **A page's styling is split across several files** — the
Kit carries the global colours and fonts, the page carries its own. Every other
verifier here reads a single `post-<id>.css` off the disk, which is an incomplete
picture by construction. This one reads whatever the page actually *links*, through
the cache (`x-cache=HIT`), which is the only definition of "it works" that a visitor
would recognise.

**6. Look at it.** `examples/demo-page.json` is a real published page, built with
nothing but this skill. The Elementor editor has never been opened on it.

**https://moksaweb.com/elementor-headless-demo/**

## Reuse blocks across pages and sites

Elementor's own JSON interchange format — the file behind the editor's Export /
Import Template buttons:

```bash
wp eval-file tools/export-template.php <post_id> > hero-block.json
wp --user=1 eval-file tools/import-template.php hero-block.json <target_post_id>
```

**Never move a block between sites by copying `_elementor_data`.** Media controls
store an attachment id, and that id points at a *different image* on the other site
— or nothing. Elementor's `on_export` swaps the id for a url and `on_import`
re-downloads it into the target's media library. Copy the raw meta and the images
silently break, or silently become the wrong images. These tools call Elementor's
own import path to get those hooks. Round trip measured: 82 settings authored, 0
lost, 0 changed.

## What's in the box

```
data/
  elementor-schema.json    3.2 MB   the full surface - queried, never loaded
  controls.csv             2.0 MB   every widget/element-specific control
  common-controls.csv       39 KB   the 210 shared by every widget
  pro-only-controls.csv     33 KB   the safety table
  pro-only-widgets.csv     3.0 KB
  control-types.csv        4.6 KB   all 59 JSON value shapes
  group-controls.csv       3.7 KB   16 groups, and the flat keys they expand to
  widgets.csv              8.3 KB   135 widgets + 3 elements
  breakpoints.csv          0.2 KB
  control-verification.csv          per-control: does it emit the CSS it claims?
  class-verification.csv            per-control: does it emit the CLASS it claims?
  token-benchmark.csv               reproducible measurements

tools/
  el.py                          query the schema - the front door
  validate-page.py               pre-flight a page tree
  apply-page.php                 write it: meta + CSS rebuild + HTML cache + backup
  extract-elementor-schema.php   dump a live install
  build-indexes.py               dump + sweep results -> shipped data files
  verify-schema.py               does the schema match your install?
  verify-render.py               does Elementor emit what the schema promised?
  verify-live.py                 does the PUBLIC page have it, through the CDN?
  sweep-controls.py              render every CSS control, assert the stylesheet
  sweep-classes.py               render every CLASS control, assert the HTML
  export-template.php            export to Elementor's own JSON format
  import-template.php            import one, with media, via Elementor's own path
  benchmark-tokens.py            reproduce the token numbers
  install-skill.py               8-platform installer

references/   data-model · control-types · containers-and-layout · responsive
              templates-and-conditions · import-export · extraction-traps
              token-efficiency
examples/     demo-page.json - the published page above
```

## The nine traps

The naive way to do this is wrong in nine separate ways, each producing a skill that
looks complete and lies. **All nine were shipped in this repo before being caught** —
some by reading Elementor's source, the rest only by rendering every control and
looking at what came out. Write-ups in
[extraction-traps.md](references/extraction-traps.md):

1. **WP-CLI looks like the front end to Elementor**, so it hands back the lean
   control stack: **46% of controls and ~100% of tab/label metadata vanish**, with
   no error. The extractor disables that path, and has three canaries that abort
   rather than emit degraded data.
2. **Responsive is two mechanisms**, and the obvious test finds only one. There is
   no `padding_tablet` control object *anywhere* — and `padding_tablet` works.
   Detecting responsive by looking for suffixed siblings missed padding, margin,
   width, font size and gap. (9.8% → 30.1% of controls after the fix.)
3. **A control's tier is not its widget's tier**, because Pro injects into free
   widgets. Measured, not inherited.
4. **A control can be gated three different ways**, and `condition` is only one of
   them. 152 controls are gated *only* by an advanced boolean form with its own
   operators. And 499 controls interpolate *another* control's value into their CSS
   — Elementor throws away the whole declaration if that other value is empty, with
   every documented condition satisfied and no error. Set a gradient angle without a
   gradient colour and you get nothing, silently.
5. **A responsive control's dependencies are re-checked at the breakpoint.** Set
   `X_tablet` but not `Y_tablet` and desktop renders perfectly while tablet is
   silently blank. 1,433 responsive suffixes emitted nothing for exactly this reason.
6. **`is_responsive` over-promises.** `hotspot.width` carries the same flag as
   `container.padding`; `padding_tablet` works and `width_tablet` emits nothing at
   all. Only rendering knows — so the sweep feeds its result back and corrects the
   schema.
7. **CSS is only half of what a control can do.** 2,573 controls act by putting a
   **class** on the wrapper, and 1,894 of them emit no CSS at all — so a stylesheet
   sweep cannot see they exist, however green it runs. They were all shipped here on
   the strength of "Elementor registered a `prefix_class`, so presumably it works".
8. **A class control's value is remapped, and its prefix changes per device.**
   `position: "top"` is not in the option list and renders `elementor-position-block-start`
   anyway (`classes_dictionary`). `position_tablet` renders
   `elementor-**tablet**-position-…`, not a `_tablet` suffix on the class. A switcher
   stores its `return_value`, so `hide_tablet: "yes"` renders `elementor-yes` and hides
   nothing. And `"columns": 0` emits nothing while `"columns": "0"` works.
9. **Writing `_elementor_data` leaves a stale rendered-HTML cache.** The post updates,
   the CSS rebuilds, the meta reads back exactly right — and the page serves its
   **previous markup**, forever, with no error. A 17,421-control CSS sweep ran green
   with this bug live, because CSS is a separate file we always rebuilt.

Trap 9 is the whole argument for this project in one line: **a verifier only finds
bugs in the channel it reads.** A green run in one channel says nothing about the
others.

## Contributing

Re-extract against a newer Elementor and open a PR with the regenerated `data/` —
`verify-schema.py` will tell you exactly what changed. See
[CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT. Built and maintained by **moksa** · [moksaweb.com](https://moksaweb.com)

Sibling skill: [rankmath-seo-wp](https://github.com/moksa1123/rankmath-seo-wp)
