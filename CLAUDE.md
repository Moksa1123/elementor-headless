# Project instructions for AI assistants

This file is read by Claude Code, Cursor, and other AI coding assistants when
they open this repository. It supplements `SKILL.md` (the user-facing skill
contract) with development conventions for editing the skill itself.

## Identity

- Project: `elementor-headless`
- Author / maintainer: **moksa** ([moksaweb.com](https://moksaweb.com))
- License: MIT
- Purpose: build and modify Elementor pages entirely through their
  underlying JSON/meta data — headless, no visual editor required.
  **Not** a site health-check or plugin/media audit tool — that's
  explicitly out of scope; keep it that way.
- Sibling project: [rankmath-seo-wp](https://github.com/moksa1123/rankmath-seo-wp) — same author, same multi-platform install architecture

## Repository layout

```
elementor-headless/
├── SKILL.md                # Skill contract — auto-loaded by AI assistants
├── README.md               # Entry point (+ zh-TW / ja / ko translations)
├── CLAUDE.md               # This file — AI dev conventions
├── CONTRIBUTING.md         # Human contributor guide
├── LICENSE                 # MIT
├── data/                   # CSV/JSON — verified structured facts, with dates
├── references/             # Long-form methodology docs
├── tools/                  # extraction/build scripts (PHP + Python) + installer
└── assets/templates/platforms/*.json  # per-platform install configs
```

## When editing the skill

1. **`SKILL.md` is the contract.** Keep its YAML frontmatter (`name`,
   `description`) intact — `name` must match the parent folder name
   (`elementor-headless`), and both fields are required by the Agent Skills
   spec.
2. **Stay in scope.** This skill is about *constructing* Elementor pages
   through data, not diagnosing a site's health. Don't add plugin-usage
   auditing, orphaned-media detection, or general WordPress health-check
   content here — that was tried once during this project's history and
   deliberately removed. If a future task genuinely needs that, it belongs
   in a separate project.
3. **Extraction tools are PHP, not Python** —
   `extract-elementor-controls.php` needs full WordPress + Elementor
   context (`\Elementor\Plugin::$instance`) and is meant to run via `wp
   eval-file` against a real site. `ghost-glint-svg.py` is the one
   genuinely standalone tool (no WordPress context needed) — keep it that
   way.
4. **`wp eval-file` takes plain positional args only.** No `--` separator,
   no `--flag=value` syntax (wp-cli intercepts any `--foo=bar` token as an
   attempted *global* parameter and errors before your script runs).
5. **Every Pro-only claim must be source-verified, not assumed.** See the
   "Free vs Pro" section below — this project got Border/Box-Shadow wrong
   once (assumed Pro-hook-injected when they're actually core Free Group
   Controls) before correcting it against source. Don't repeat that
   mistake with a new feature; verify the same way every time.
6. **Use `data/*.csv` / `data/*.json` for structured, dated facts.** Widget
   control schemas and platform conventions belong in machine-readable data
   files with a verification date, with the prose rationale in the matching
   `references/*.md`.

## Free vs Pro: the standing rule

Every architecture decision, code sample, and comment — in this repo and in
anything built using this skill — must explicitly mark which
features/APIs/parameters are Elementor Pro-only. Never let Free and Pro
blur together. Concretely, before labeling anything Pro-only:

1. **Widget-level**: check which plugin's directory registers the widget
   class (`elementor-pro/` vs `elementor/`) — reflect on the class, don't
   guess from the widget's name or apparent sophistication.
2. **Feature-level, hook-injected**: grep the relevant
   `elementor-pro/modules/*/module.php` for `API::is_licence_has_feature`
   — the literal string passed as its first argument is the actual
   license-gated feature name. Custom CSS is the confirmed example.
3. **Feature-level, everything else**: if it's defined under
   `elementor/includes/` rather than `elementor-pro/`, it's core/Free — full
   stop, regardless of how advanced it looks. Border and Box Shadow are the
   confirmed example of a "feels Pro, isn't" trap.

Full detail and the exact verified field names for both in
`references/elementor-style-system.md`.

## Sanitisation rules (open-source release)

This skill is published publicly, and its whole premise is "distilled from
real production work" — which means the raw material is a real client's
site. Never commit:

- Real SSH hosts, IPs, usernames, key filenames
- Real Cloudways / managed-WP paths (`/home/<account>.cloudwaysapps.com/...`)
- Personal Windows / macOS paths (`C:\Users\<name>\...`, `~/Library/...`)
- Real plugin/theme slugs, template IDs, ACF field keys, or post IDs tied to
  an identifiable site — generalize the pattern, don't paste the specific
  numbers (an `_elementor_conditions` value like `include/singular/team` as
  an *example* of the format is fine; a real site's actual template ID `3411`
  used as if it were universal is not)
- Real client names, emails, phone numbers, social media handles, or company
  names that appeared in any source material used to derive a pattern
- Cloud project IDs, account numbers, FileBird/media-folder IDs

Always use placeholders: `user@your-wp-host.example.com`, `~/.ssh/id_rsa`,
`/path/to/wordpress`, `<template_id>`, `<cpt-slug>`.

Every example in `references/` should read as a *generalizable pattern*, not
a transcript of one specific site's data. If a worked example needs concrete
numbers to be legible (like the proportional ratios in
`dynamic-ghost-text-pattern.md`), keep the numbers but strip anything that
would let a reader identify *whose* site they came from.

`data/elementor-core-pro-controls.json` is safe by construction — it's
extracted from Elementor's own class *definitions* (control names/types/
labels), not from any site's actual content, so it carries no client data
regardless of which site it was extracted from. Verify this stays true if
the extraction script changes (don't start capturing live `settings` values
or defaults that could echo real content).

If you find a leak, sanitise it before committing and grep the entire repo
for related strings before considering it done.

## Local verification before commit

There's no local test suite (the extraction tool needs a live WordPress +
Elementor target, which isn't something to fake with fixtures). Instead:

```bash
# Lint the PHP tool for syntax errors
php -l tools/extract-elementor-controls.php

# Exercise the standalone tool end-to-end
python tools/ghost-glint-svg.py "TEST" --out /tmp/preview.html

# Exercise the installer against a scratch directory for every platform
for p in claude-code claude-ai cursor codex-cli gemini-cli windsurf copilot continue; do
  python tools/install-skill.py "$p" --to ./_test_install --dry-run
done
```

Before merging a change to the PHP extraction tool, actually run it against
a real WordPress + Elementor site via `wp eval-file` at least once — a
`php -l` pass only proves it parses, not that it returns anything useful.

## Adding a new platform config

1. **Verify the current convention independently** — don't copy an assumption
   from memory or from another skill's older config. See
   `references/multiplatform-install-verification.md` for why this matters
   (3 of 8 platforms drifted in ~6 weeks the last time this was checked).
2. Add `assets/templates/platforms/<name>.json` following the existing shape
   (`installType` one of `full`/`rule`/`instructions-append`/`zip-upload`).
3. Set `verifiedAsOf` to today's date and write a `verificationNote` if
   there's any residual uncertainty — don't mark `verified: true` with no
   caveat unless you're actually confident, and don't mark `verified: false`
   for something you've confirmed just to be extra-cautious.
4. Add a row to `data/platform-conventions.csv`.
5. Update the table in `README.md` (and its translations) if the platform
   list changed.

## Style

- English in code comments and identifiers.
- Chinese is fine in commit messages / issue discussion if that's the
  contributor's natural language — this project has a bilingual audience.
- Markdown: ATX headings (`##`), no trailing whitespace, LF endings.
- PHP: match WordPress core coding conventions (tabs for indentation, space
  after control-structure keywords) since these scripts run inside WP-CLI's
  WordPress bootstrap.
- Python: PEP 8, type hints where the signature is non-obvious, stdlib only
  (no dependencies to install before running the installer).

---

If you're an AI assistant reading this in the middle of a task: prefer
editing existing files over creating new ones, verify a claim against
Elementor's actual source or a live site before writing it into a reference
doc as fact, don't mark something `verified: true` without actually having
checked it this session, and don't reintroduce health-check/audit content
into this skill's scope.
