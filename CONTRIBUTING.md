# Contributing to elementor-headless

Thanks for considering a contribution. This skill is distilled from real
Elementor data-model work, verified against source rather than memory — the
most valuable contributions are the same kind: a real gap in the data model,
a Free/Pro assumption that turned out wrong, and how it was actually
confirmed.

**Out of scope**: plugin/media auditing and general WordPress health-check
content. This skill is specifically about building/modifying Elementor
pages through data — that's a deliberate boundary, not an oversight.

## What's especially welcome

- **A platform install convention that's drifted.** This ecosystem moves
  fast (see `references/multiplatform-install-verification.md`) — if you've
  confirmed a platform's skill/rule loading convention has changed, that's a
  high-value, low-controversy PR. Update the platform's JSON config, its
  `verifiedAsOf` date, and the CSV row.
- **A Free/Pro labeling correction.** If you've verified (from source, not
  assumption) that something documented as Pro-only is actually Free, or
  vice versa, that's exactly the kind of fix this project exists to catch —
  see `elementor-style-system.md` for the Border/Box-Shadow example and the
  verification method to use.
- **A widget/setting shape not yet documented** in
  `elementor-widgets-and-containers.md` or `data/elementor-core-pro-controls.json`
  — especially from a popular third-party addon plugin's own widget
  registrations, or a newer Elementor/Elementor Pro version's additions.
- **A Display/Advanced Condition type not yet covered** in
  `elementor-templates-and-conditions.md` — if Elementor Pro ships a new
  condition class, confirm its `get_type()`/`get_name()` from source the
  same way the existing table was built.
- **Translations** of `README.md` (see `rankmath-seo-wp`'s multilingual
  README convention if you want to mirror that structure here).

## Before you open a PR

1. Read the **Sanitisation rules** section of `CLAUDE.md`. This is the one
   rule enforced without exception: nothing derived from a real site's real
   data — hostnames, IPs, template/post IDs, ACF field keys, client names —
   gets committed, even as "just an example." Generalize the pattern instead.
2. If you're changing the PHP extraction tool, actually run it via `wp
   eval-file` against a real WordPress + Elementor install at least once.
   `php -l` only checks syntax.
3. If you're adding/changing a platform config, verify the current
   convention independently (search current docs, don't copy from memory or
   another project) and set `verifiedAsOf` to the date you checked.
4. Keep `SKILL.md`'s frontmatter (`name`, `description`) intact — `name`
   must keep matching the repository/folder name.

## Reporting an issue

Open a GitHub issue with:
- What you were trying to do
- What the skill's guidance said to do
- What actually happened when you did it

If it's a platform-install issue specifically, include which platform,
which version, and what convention you found in its current docs instead.

## Code of conduct

Be direct and be kind. Assume good faith; this is a small project maintained
by one person in their spare time between client work.
