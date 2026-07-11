<div align="center">

# WP Elementor Ops

### Safely audit and edit WordPress + Elementor sites. Real production mistakes, and their fixes, baked in.

<p>
  <a href="https://github.com/Moksa1123/wp-elementor-ops"><img src="https://img.shields.io/github/stars/Moksa1123/wp-elementor-ops?style=flat-square&logo=github&logoColor=white&color=181717" alt="GitHub stars"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="MIT"></a>
</p>

<p>
  <img src="https://img.shields.io/badge/format-Agent%20Skill-blue?style=flat-square" alt="Agent Skill">
  <img src="https://img.shields.io/badge/python-3.9%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/php-7.4%2B-777BB4?style=flat-square&logo=php&logoColor=white" alt="PHP 7.4+">
  <img src="https://img.shields.io/badge/AI%20platforms-8-blueviolet?style=flat-square" alt="8 AI platforms">
</p>

<p>
  <a href="#quick-start"><strong>Get started</strong></a> ·
  <a href="https://github.com/Moksa1123/wp-elementor-ops"><strong>GitHub</strong></a> ·
  <a href="https://github.com/Moksa1123/rankmath-seo-wp"><strong>Sibling project</strong></a> ·
  <a href="https://moksaweb.com"><strong>moksaweb.com</strong></a>
</p>

<p>
  <strong>English</strong> ·
  <a href="README.zh-TW.md">繁體中文</a> ·
  <a href="README.ja.md">日本語</a> ·
  <a href="README.ko.md">한국어</a>
</p>

</div>

---

## What this is for

- **"Health-check this WordPress site" / "which plugins can I remove?"** —
  find a plugin's *real* block/shortcode/option signature before searching
  for it (guessing from the slug is the #1 mistake this skill exists to
  prevent), cross-reference genuine usage, guard against false-positive
  "orphaned media" matches.
- **"Edit this shared Elementor template"** — navigate `_elementor_data`
  JSON without an off-by-one, convert static per-template content into a
  dynamic per-post shortcode when it needs to vary, flush caches in the
  correct layered order.
- **"What settings does this Elementor widget even have?"** — a data file
  extracted from a live Elementor + Elementor Pro install (164 widgets,
  48,238 controls, verified not guessed) plus the universal "Advanced tab"
  sections present in 98% of all widgets, fully documented.
- **"This isn't showing up after my change"** — cache-layer and
  compression/screenshot-scaling debugging notes from real incidents.

## Quick start

```bash
git clone https://github.com/Moksa1123/wp-elementor-ops.git
cd wp-elementor-ops
python tools/install-skill.py --list                 # see supported platforms
python tools/install-skill.py claude-code             # install into this project
python tools/install-skill.py claude-code --global    # install for all projects
```

See `SKILL.md` for the full contract and `references/` for the underlying
methodology docs.

## Repository layout

```
wp-elementor-ops/
├── SKILL.md                        # Skill contract — auto-loaded by AI assistants
├── README.md                       # This file (+ zh-TW / ja / ko translations)
├── CLAUDE.md                       # AI dev conventions + sanitisation rules
├── LICENSE                         # MIT
├── references/
│   ├── plugin-audit-methodology.md         # find the REAL signature before judging usage
│   ├── elementor-safe-edit.md              # shared-template editing protocol
│   ├── elementor-widgets-and-containers.md # container/widget/dynamic-tag data model, verified live
│   ├── dynamic-ghost-text-pattern.md       # static → per-post-dynamic worked example
│   ├── wp-cli-safe-scripting.md            # quoting/escaping/file-based execution discipline
│   └── multiplatform-install-verification.md # dated per-platform install conventions
├── tools/
│   ├── audit-plugin-usage.php         # run via `wp eval-file` — cross-reference real usage
│   ├── audit-orphan-media.php         # run via `wp eval-file` — orphan detection w/ false-positive guard
│   ├── extract-elementor-controls.php # run via `wp eval-file` — reproduce the widget-control dataset on your own site
│   ├── ghost-glint-svg.py             # standalone — preview/tune the ghost-text SVG proportions
│   └── install-skill.py               # multi-platform installer
├── data/
│   ├── platform-conventions.csv          # dated install paths per platform
│   └── elementor-core-pro-controls.json  # 135 widgets' full control schemas, extracted from a live install
└── assets/templates/platforms/*.json  # per-platform install configs
```

## Why this exists

Built from real debugging on a production WooCommerce + Elementor Pro site:
a plugin was deactivated because a search for its *guessed* block name found
nothing, when the *real* name (the author's own namespace) was used in 10
live articles. A shared Elementor template's decorative text was hardcoded
identically across every post that used it. An "orphan media" sweep almost
flagged files that were actually referenced through ACF image fields, having
first mistaken unrelated view-counter metadata for real references. Every
reference doc here traces back to one of these — including the parts that
went wrong the first time, and including a real bug found in this project's
own audit tools during development (`wp eval-file` doesn't support `--`
separators or `--flag=value` syntax the way a Unix CLI would).

## Verified, not guessed

Two things in this repo exist specifically because "sounds right" wasn't
good enough:

- **Elementor's data model** (`elementor-widgets-and-containers.md`,
  `data/elementor-core-pro-controls.json`) was extracted by actually
  querying a live install's widget registry, not written from training
  data or memory. Where the live extraction had a real gap (Border/Box-
  Shadow/Custom CSS, injected by Elementor Pro via hooks a plain
  `get_controls()` call doesn't trigger), that gap is documented as a gap.
- **Multi-platform install conventions** (`multiplatform-install-verification.md`)
  are dated and independently re-checked — 3 of 8 supported platforms had
  already drifted from this project's sibling skill's own table in the ~6
  weeks between the two being written.

## Contributing

See `CONTRIBUTING.md`. Sanitisation matters here more than in most repos —
read the "Sanitisation rules" section of `CLAUDE.md` before submitting a PR
that includes anything derived from a real site.

## Author

Built and maintained by **moksa** at [moksaweb.com](https://moksaweb.com).
MIT licensed.
