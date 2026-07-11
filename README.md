<div align="center">

# Elementor Headless

### Build and modify Elementor pages by directly reading/writing JSON and meta data. No visual editor required. Every Pro-only feature explicitly labeled.

<p>
  <a href="https://github.com/Moksa1123/elementor-headless"><img src="https://img.shields.io/github/stars/Moksa1123/elementor-headless?style=flat-square&logo=github&logoColor=white&color=181717" alt="GitHub stars"></a>
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
  <a href="https://github.com/Moksa1123/elementor-headless"><strong>GitHub</strong></a> ·
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

## What this is

A headless approach to Elementor: a page is a JSON tree of containers and
widgets, each widget a `settings` object of typed fields. This skill gives
an AI agent the full, source-verified parameter surface — widget controls,
style groups, responsive breakpoints, template conditions, dynamic tags —
so it can build or restructure a page entirely through data, without ever
opening the visual editor.

**Not** a site health-check or plugin-audit tool — that's explicitly out of
scope. This is about construction, not diagnostics.

## What's covered

- **Templates**: create/read/apply Theme Builder templates
  (`elementor_library` CRUD, `_elementor_template_type`)
- **Display Conditions & Advanced Conditions**: the complete
  Include/Exclude condition type/name enumeration (general / singular /
  archive, every sub-condition Elementor Pro ships), plus how conflicts
  between competing templates actually resolve (specificity-based
  priority, not registration order)
- **RWD**: per-breakpoint style parameters — verified at scale that 20% of
  all Elementor controls carry a `_tablet`/`_mobile` responsive variant
- **Custom Settings**: the Group Control mechanism behind Border, Box
  Shadow, Typography, and Background (core Elementor, free), and Custom
  CSS injection (genuinely Pro-only, hook-injected — verified from source,
  not assumed)
- **Free vs Pro, verified not guessed**: every widget and feature's source
  is checked against the actual `elementor` vs `elementor-pro` plugin
  directory and license-gate code — this project got Border/Box-Shadow
  wrong once during development (assumed Pro when they're Free) before
  correcting it against source; the correction and the verification method
  are both documented

## Quick start

```bash
git clone https://github.com/Moksa1123/elementor-headless.git
cd elementor-headless
python tools/install-skill.py --list                 # see supported platforms
python tools/install-skill.py claude-code             # install into this project
python tools/install-skill.py claude-code --global    # install for all projects
```

See `SKILL.md` for the full contract and `references/` for the underlying
data model.

## Repository layout

```
elementor-headless/
├── SKILL.md                        # Skill contract — auto-loaded by AI assistants
├── README.md                       # This file (+ zh-TW / ja / ko translations)
├── CLAUDE.md                       # AI dev conventions + Free/Pro + sanitisation rules
├── LICENSE                         # MIT
├── references/
│   ├── elementor-widgets-and-containers.md   # container/widget/dynamic-tag data model, verified live
│   ├── elementor-style-system.md             # Group Controls, Custom CSS, Free vs Pro verification
│   ├── elementor-templates-and-conditions.md # template CRUD, full Display/Advanced Conditions
│   ├── elementor-safe-edit.md                # shared-template editing protocol, JSON path discipline
│   ├── dynamic-ghost-text-pattern.md         # static → per-post-dynamic worked example
│   ├── wp-cli-safe-scripting.md              # quoting/escaping/file-based execution discipline
│   └── multiplatform-install-verification.md # dated per-platform install conventions
├── tools/
│   ├── extract-elementor-controls.php # run via `wp eval-file` — reproduce the widget-control dataset on your own site
│   ├── ghost-glint-svg.py             # standalone — preview/tune the ghost-text SVG proportions
│   └── install-skill.py               # multi-platform installer
├── data/
│   ├── platform-conventions.csv          # dated install paths per platform
│   └── elementor-core-pro-controls.json  # 135 widgets' full control schemas, extracted from a live install
└── assets/templates/platforms/*.json  # per-platform install configs
```

## Verified, not guessed

- **164 widgets, 48,238 controls** extracted from a live Elementor +
  Elementor Pro install — not written from training data.
- **9 universal Advanced-tab sections found in 98% of all widgets**, full
  real control lists for each.
- **Every Display/Advanced Condition type** enumerated directly from
  Elementor Pro's `Condition_Base` subclasses, including the exact
  specificity-based priority resolution when multiple templates compete.
- **Free vs Pro boundaries checked against source** (plugin directory +
  license-gate code), not inferred from how advanced a feature feels.
- **Multi-platform install conventions**, dated and independently
  re-checked — 3 of 8 supported platforms had already drifted from this
  project's sibling skill's own table in the ~6 weeks between the two
  being written (see `multiplatform-install-verification.md`).

## Contributing

See `CONTRIBUTING.md`. Sanitisation matters here more than in most repos —
read the "Sanitisation rules" section of `CLAUDE.md` before submitting a PR.

## Author

Built and maintained by **moksa** at [moksaweb.com](https://moksaweb.com).
MIT licensed.
