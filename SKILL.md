---
name: elementor-headless
description: Build and modify Elementor pages by directly reading/writing the underlying JSON and meta data — no visual editor (DOM) required. Covers the full parameter surface (widgets, containers, style groups, RWD, dynamic tags), template CRUD, Display/Advanced Conditions, and custom CSS/style injection, with every Elementor Pro-only feature explicitly labeled. Use when asked to build, design, or restructure an Elementor page/template programmatically.
---

# Elementor Headless

**Role**: Headless Elementor development — building and modifying Elementor
pages entirely through their underlying data structures, without ever
loading the visual editor. This skill is about *construction*, not
diagnostics: it does not cover plugin/media auditing or site health checks
(see `references/wp-cli-safe-scripting.md` for the execution discipline
those tasks would share, but the audit methodology itself lives outside this
skill's scope).

## Objective

Treat Elementor as a headless page-building API: a page is a JSON tree of
containers and widgets, each widget a `settings` object of typed fields.
Building or modifying a page means writing that JSON directly and correctly
— not clicking through panels. Everything below exists to make that
possible without guessing a field name or a data shape.

## Technical execution

**Low-level parsing.** A page's structure lives in the `_elementor_data`
postmeta as a JSON tree (`elType: container|widget`, nested `elements`).
Read `references/elementor-widgets-and-containers.md` for the container
model, widget shape, and the exact JSON-path navigation discipline (path
arrays are alternating `->elements[idx]` hops — an easy off-by-one).

**Parameter mapping.** Every field Elementor exposes — widget-specific
Content controls, the universal Style/Advanced groups, RWD breakpoint
variants — is catalogued from a live extraction, not memory:
`data/elementor-core-pro-controls.json` (135 widgets, verified 2026-07-11)
plus `references/elementor-style-system.md` for the reusable Group Control
mechanism (Border, Box Shadow, Typography, Background, CSS Filters) that
underlies most Style-tab fields across every widget.

## Core features

| Feature | Where it's covered |
|---|---|
| **Template management** (create / read / apply) | `references/elementor-templates-and-conditions.md` |
| **Display Conditions** (Include/Exclude) | `references/elementor-templates-and-conditions.md` |
| **Advanced Conditions** (complex dynamic display logic) | `references/elementor-templates-and-conditions.md` |
| **RWD** (per-breakpoint style parameters: Desktop/Tablet/Mobile) | `references/elementor-widgets-and-containers.md` ("Responsive breakpoints") |
| **Custom Settings** (advanced style controls + custom CSS injection) | `references/elementor-style-system.md` |

## Environment & strict constraints

**Base environment**: Elementor Free + Elementor Pro. No assumption of any
specific theme or third-party addon plugin — those vary per install; re-run
`tools/extract-elementor-controls.php` against the target site if a widget
outside core Elementor/Elementor Pro needs to be built against.

**Mandatory labeling rule**: every architecture decision, data-parsing
approach, code sample, and comment in this skill — and in anything built
using it — **must explicitly mark which features/APIs/parameters are
Elementor Pro-only**. Never let Free and Pro capabilities blur together.
Concretely:

- A **widget** is Pro-only if it's registered from `elementor-pro/`
  (confirmed via the widget class's file path — see
  `data/elementor-core-pro-controls.json`'s `source` field, `elementor-core`
  vs `elementor-pro`).
- A **control/feature shared across widgets** is Pro-only only if you've
  confirmed it in Elementor Pro's own source, gated behind a license check
  (`API::is_licence_has_feature(...)`) — don't assume; verify. Example:
  Custom CSS (`custom_css` control) is genuinely Pro-only, gated exactly
  this way. Border and Box Shadow, by contrast, are **not** Pro — they're
  core Elementor Group Controls (`Group_Control_Border`,
  `Group_Control_Box_Shadow`), free in every widget. Getting this
  distinction wrong (assuming something's Pro when it's Free, or vice
  versa) previously happened during this skill's own development — see
  `references/elementor-style-system.md` for exactly how it was corrected
  and how to verify any new case yourself rather than guessing.

## Reproducing the verified data on your own install

```bash
cat tools/extract-elementor-controls.php | ssh user@host "cat > /tmp/x.php"
ssh user@host "cd /path/to/wordpress && wp eval-file /tmp/x.php > controls.json"
```

Do this whenever the target site's Elementor/Elementor Pro version differs
meaningfully from what `data/elementor-core-pro-controls.json` was extracted
from, or when building against a third-party addon widget not covered by
the shipped dataset.

## Tools (in `tools/`)

| Tool | Run via | Purpose |
|------|---------|---------|
| `extract-elementor-controls.php` | `wp eval-file` | Reproduce the widget-control dataset on any live site |
| `ghost-glint-svg.py` | standalone | Generate a dynamic per-entity decorative SVG (worked example of static→dynamic conversion, see `dynamic-ghost-text-pattern.md`) |
| `install-skill.py` | standalone | Multi-platform installer |

## Multi-platform install

See `references/multiplatform-install-verification.md` — dated findings for
8 AI coding platforms' skill/rule conventions. Re-verify before trusting,
don't just copy the table.

```bash
python tools/install-skill.py --list
python tools/install-skill.py claude-code
```

## Author

Built and maintained by **moksa** at [moksaweb.com](https://moksaweb.com).
MIT licensed. Sibling project:
[rankmath-seo-wp](https://github.com/moksa1123/rankmath-seo-wp).
