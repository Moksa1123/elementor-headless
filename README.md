# wp-elementor-ops

Safely audit and edit WordPress + Elementor sites. An AI-agent skill (Claude
Code, Claude.ai, Cursor, Codex CLI, Gemini CLI, Windsurf/Devin Desktop,
GitHub Copilot, Continue) that codifies the discipline needed to answer "is
this plugin/media file actually unused?" and "how do I edit a shared
Elementor template without breaking the other pages that use it?" — with
real production mistakes and their fixes baked in, not just theory.

Sibling project to [rankmath-seo-wp](https://github.com/moksa1123/rankmath-seo-wp)
(same author, same multi-platform install approach).

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
- **"This isn't showing up after my change"** — cache-layer and
  compression/screenshot-scaling debugging notes from real incidents.

## Quick start

```bash
git clone https://github.com/moksa1123/wp-elementor-ops.git
cd wp-elementor-ops
python tools/install-skill.py --list                 # see supported platforms
python tools/install-skill.py claude-code             # install into this project
python tools/install-skill.py claude-code --global    # install for all projects
```

See `SKILL.md` for the full contract and `references/` for the underlying
methodology docs (plugin/media audit, safe Elementor editing, the dynamic
ghost-text SVG pattern, Elementor's container/widget/dynamic-tag data model,
safe WP-CLI scripting over SSH).

## Repository layout

```
wp-elementor-ops/
├── SKILL.md                        # Skill contract — auto-loaded by AI assistants
├── README.md                       # This file
├── CLAUDE.md                       # AI dev conventions + sanitisation rules
├── LICENSE                         # MIT
├── references/
│   ├── plugin-audit-methodology.md         # find the REAL signature before judging usage
│   ├── elementor-safe-edit.md              # shared-template editing protocol
│   ├── elementor-widgets-and-containers.md # container/widget/dynamic-tag data model
│   ├── dynamic-ghost-text-pattern.md       # static → per-post-dynamic worked example
│   ├── wp-cli-safe-scripting.md            # quoting/escaping/file-based execution discipline
│   └── multiplatform-install-verification.md # dated per-platform install conventions
├── tools/
│   ├── audit-plugin-usage.php      # run via `wp eval-file` — cross-reference real usage
│   ├── audit-orphan-media.php      # run via `wp eval-file` — orphan detection w/ false-positive guard
│   ├── ghost-glint-svg.py          # standalone — preview/tune the ghost-text SVG proportions
│   └── install-skill.py            # multi-platform installer
├── data/
│   └── platform-conventions.csv    # dated install paths per platform
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
went wrong the first time.

## Multi-platform install verification

This ecosystem moves fast — see `references/multiplatform-install-verification.md`
for a concrete example: 3 of 8 supported platforms' install conventions had
already changed in the ~6 weeks since the sibling project's own table was
written. Every platform config here carries a `verifiedAsOf` date; re-check
before trusting an old copy.

## Contributing

See `CONTRIBUTING.md`. Sanitisation matters here more than in most repos —
read the "Sanitisation rules" section of `CLAUDE.md` before submitting a PR
that includes anything derived from a real site.

## Author

Built and maintained by **moksa** at [moksaweb.com](https://moksaweb.com).
MIT licensed.
