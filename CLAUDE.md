# Project instructions for AI assistants

This file is read by Claude Code, Cursor, and other AI coding assistants when
they open this repository. It supplements `SKILL.md` (the user-facing skill
contract) with development conventions for editing the skill itself.

## Identity

- Project: `wp-elementor-ops`
- Author / maintainer: **moksa** ([moksaweb.com](https://moksaweb.com))
- License: MIT
- Purpose: safely audit and edit WordPress + Elementor sites via AI agents
- Sibling project: [rankmath-seo-wp](https://github.com/moksa1123/rankmath-seo-wp) — same author, same multi-platform install architecture

## Repository layout

```
wp-elementor-ops/
├── SKILL.md                # Skill contract — auto-loaded by AI assistants
├── README.md               # Entry point
├── CLAUDE.md               # This file — AI dev conventions
├── CONTRIBUTING.md         # Human contributor guide
├── LICENSE                 # MIT
├── data/                   # CSV — platform install conventions with dates
├── references/             # Long-form methodology docs
├── tools/                  # audit scripts (PHP, run via wp eval-file) + installer (Python)
└── assets/templates/platforms/*.json  # per-platform install configs
```

## When editing the skill

1. **`SKILL.md` is the contract.** Keep its YAML frontmatter (`name`,
   `description`) intact — `name` must match the parent folder name
   (`wp-elementor-ops`), and both fields are required by the Agent Skills
   spec. Other platforms (Cursor, Codex, Gemini CLI) depend on the same
   shape.
2. **The audit tools are PHP, not Python** — `audit-plugin-usage.php` and
   `audit-orphan-media.php` need full WordPress context (`get_post_meta()`,
   `$wpdb`, ACF field introspection) and are meant to run via `wp eval-file`
   against a real site. Don't "port" them to standalone Python; there's
   nothing for a local Python script to query without a live WP-CLI
   connection. `ghost-glint-svg.py` is the one genuinely standalone tool
   (no WordPress context needed) — keep it that way.
3. **`wp eval-file` takes plain positional args only.** No `--` separator,
   no `--flag=value` syntax (wp-cli intercepts any `--foo=bar` token as an
   attempted *global* parameter and errors before your script runs). This
   bit a real version of `audit-plugin-usage.php` during development —
   don't reintroduce flag-style argument parsing into these tools.
4. **Use `data/*.csv` for structured, dated facts.** The platform
   conventions table belongs in CSV (machine-readable, has a
   `verified_as_of` column) with the prose rationale in
   `references/multiplatform-install-verification.md`.

## Sanitisation rules (open-source release)

This skill is published publicly, and its whole premise is "distilled from
real production debugging" — which means the raw material is a real client's
site. Never commit:

- Real SSH hosts, IPs, usernames, key filenames
- Real Cloudways / managed-WP paths (`/home/<account>.cloudwaysapps.com/...`)
- Personal Windows / macOS paths (`C:\Users\<name>\...`, `~/Library/...`)
- Real plugin/theme slugs, template IDs, ACF field keys, or post IDs tied to
  an identifiable site — generalize the pattern, don't paste the specific
  numbers (an `_elementor_conditions` value like `include/singular/team` as
  an *example* of the format is fine; a real site's actual template ID `3411`
  used as if it were universal is not — it's specific to one install and
  invites a reader to trust a number that means nothing on their own site)
- Real client names, emails, phone numbers, social media handles, or company
  names that appeared in any source material used to derive a pattern
- Cloud project IDs, account numbers, FileBird/media-folder IDs

Always use placeholders: `user@your-wp-host.example.com`, `~/.ssh/id_rsa`,
`/path/to/wordpress`, `<template_id>`, `<real-signature>`.

Every example in `references/` should read as a *generalizable pattern*, not
a transcript of one specific site's data. If a worked example needs concrete
numbers to be legible (like the proportional ratios in
`dynamic-ghost-text-pattern.md`), keep the numbers but strip anything that
would let a reader identify *whose* site they came from.

If you find a leak, sanitise it before committing and grep the entire repo
for related strings before considering it done.

## Local verification before commit

There's no local test suite (the PHP tools need a live WordPress + wp-cli
target, which isn't something to fake with fixtures — see
`elementor-safe-edit.md`'s emphasis on verifying against reality). Instead:

```bash
# Lint every PHP tool for syntax errors
php -l tools/audit-plugin-usage.php
php -l tools/audit-orphan-media.php

# Exercise the standalone tool end-to-end
python tools/ghost-glint-svg.py "TEST" --out /tmp/preview.html

# Exercise the installer against a scratch directory for every platform
for p in claude-code claude-ai cursor codex-cli gemini-cli windsurf copilot continue; do
  python tools/install-skill.py "$p" --to ./_test_install --dry-run
done
```

Before merging a change to a PHP tool, actually run it against a real
WordPress site via `wp eval-file` at least once — a `php -l` pass only
proves it parses, not that it does the right thing.

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
   for something you've confirmed just to be extra-cautious; both under- and
   over-claiming confidence make the table less useful.
4. Add a row to `data/platform-conventions.csv`.
5. Update the table in `README.md` if the platform list changed.

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
editing existing files over creating new ones, verify a claim against the
live target before writing it into a reference doc as fact, and don't mark
something `verified: true` without actually having checked it this session.
