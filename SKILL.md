---
name: wp-elementor-ops
description: Safely audit and edit WordPress + Elementor sites — verify plugin/media usage before removing anything, edit shared Elementor templates without breaking other pages, and manage cache layers correctly. Use when asked to health-check a WordPress site, clean up unused plugins or media, edit an Elementor template/theme-builder element, or debug why a change "isn't showing up."
---

# WP Elementor Ops

Operational discipline for maintaining a live WordPress + Elementor site: proving
a plugin, media file, or template is actually unused before touching it, and
editing shared Elementor templates without breaking the other pages that share
them. Distilled from real production debugging on a WooCommerce + Elementor Pro
site — including the mistakes, not just the successes.

## Core rule

**Never judge "is this used?" by guessing a name.** Every one of the incidents
this skill is built from came from assuming a plugin's shortcode tag, block
name, or option key matched its slug. It usually doesn't. Always find the real
signature in source before searching for it. See `references/plugin-audit-methodology.md`.

## When to use this skill

- "Health check this WordPress site" / "which plugins can I remove?"
- "Clean up unused media" / "find orphaned images"
- "This Elementor template/section needs to show X instead of Y" (shared templates,
  Theme Builder conditions, dynamic content)
- "I changed something and it's not showing up" (cache-layer debugging)
- "Turn this static decorative element into something dynamic per page"

## Quick checklist before removing anything

```
[ ] Found the plugin's ACTUAL block.json name / add_shortcode() tag / registered
    widget name in its own source — not guessed from the plugin slug
[ ] Searched wp_posts.post_content, wp_postmeta (esp. _elementor_data), and
    wp_options for that real signature — not the slug
[ ] For Elementor library templates: checked _elementor_conditions (is it
    actually assigned to a Theme Builder location?) AND checked whether any
    other page embeds it via [elementor-template id="X"] or a template widget
[ ] For "orphaned" media: cross-referenced against _thumbnail_id, all postmeta
    containing the file path/URL, AND genuine ACF image/gallery field values —
    NOT arbitrary numeric postmeta (view counters, analytics object IDs) that
    coincidentally share the same integer as an old attachment ID
[ ] Deactivated (not deleted) first; re-verified live pages return 200 and
    render correctly; waited before permanent deletion
```

## Reading Elementor's data model without rediscovering it every session

Before editing any widget or container, see
`references/elementor-widgets-and-containers.md` — verified by actually
querying a live Elementor + Elementor Pro install's registered widgets (164
widgets, 48,238 controls, one real snapshot), not written from memory:
the container/flexbox layout model, the 9 universal "Advanced tab" sections
present in 98% of all widgets (Layout, Motion Effects, Transform, Background
w/ hover state, Masking, Responsive visibility, Custom Attributes — full
real control lists for each), control-type frequency across the whole
dataset, responsive `_tablet`/`_mobile` suffix prevalence (20% of all
controls), and the Dynamic Tags system (`__dynamic__`) that lets a shared
template pull live post data without a custom shortcode.

The full per-widget Content/Style control data (135 widgets, Elementor core
+ Pro) ships as `data/elementor-core-pro-controls.json` — query it directly
instead of re-deriving an unfamiliar widget's settings from scratch. Knowing
these patterns up front is what makes editing Elementor JSON cheap instead
of a rediscovery exercise every time.

## Editing a shared Elementor template safely

Shared templates (Header, Footer, Archive, singular-CPT templates, loop-item
cards) render for *every* post that matches their Theme Builder condition —
you cannot hardcode per-entity content in them. See
`references/elementor-safe-edit.md` for the full protocol:

1. Read `_elementor_data` as JSON; a `path` like `[0,0,1,1,0]` means **four**
   nested `->elements[idx]` hops after the outer list, not three — count them
   on your fingers before writing array-navigation code, this is the single
   most common off-by-one in this workflow.
2. If the change needs to vary per-post (a name, a client, a category), don't
   edit static widget content — convert it to a `shortcode` widget backed by a
   PHP function that reads `get_the_ID()` / ACF fields at render time. See
   `references/dynamic-ghost-text-pattern.md` for a worked example (turning a
   static decorative label into a per-entity one).
3. Before touching `functions.php` or any executed PHP: write the full new file
   locally, upload to a scratch path, run `php -l` against it, and only then
   overwrite the live file. A syntax error in a theme's `functions.php` takes
   the entire site down on every request.
4. Back up the current `_elementor_data` value before writing a new one.
5. After saving: flush the Elementor CSS cache, then the page-cache plugin
   (Breeze/WP Rocket/etc.), then the host/CDN layer (Cloudways, Cloudflare) —
   in that order, layer by layer, inside-out. Reload with cache bypassed and
   verify visually, not just a 200 status code (a 200 can still be a broken
   layout or the old cached HTML).

## Cross-checking your own work

Scripted checks and screenshots disagree with reality sometimes:

- Curl output can be gzip/br-compressed garbage if you forget `--compressed` —
  garbled CJK text in a fetched HTML file is almost always this, not a real
  encoding bug on the site.
- A shrunk full-page screenshot cannot be trusted to read small (~11px) text
  accurately — verify small text against the actual DOM/source, not by eyeballing
  a scaled-down screenshot.
- When a user describes on-screen text that doesn't match anything you can find,
  consider: (a) it's generated by CSS/SVG, not literal HTML text — search
  `<text>`/`content:` in the raw source, not just plain grep for the word;
  (b) they may be looking at a different page/section than you assumed — ask
  "which page, roughly where" before spending cycles guessing.

## Tools (in `tools/`)

The audit tools need full WordPress context (`get_post_meta()`, ACF field
introspection, `wp_upload_dir()`) — they're PHP, meant to run via `wp
eval-file` against the target site, not standalone scripts. Upload once,
run, done:

```bash
cat tools/audit-plugin-usage.php | ssh user@host "cat > /tmp/audit.php"
ssh user@host "cd /path/to/wordpress && wp eval-file /tmp/audit.php '<real-signature>'"
```

Note: `wp eval-file` takes plain positional arguments only — it does **not**
support a Unix-style `--` separator, and any `--flag=value` token is
intercepted by wp-cli itself as an attempted global parameter and errors out
before your script runs. Pass the signature as a quoted positional argument.

| Tool | Run via | Purpose |
|------|---------|---------|
| `audit-plugin-usage.php` | `wp eval-file audit-plugin-usage.php '<real-signature>'` | Cross-reference a plugin's real block/shortcode/option signature across posts, `_elementor_data`, and options |
| `audit-orphan-media.php` | `wp eval-file` | Find genuinely-unreferenced attachments, with a guard against false positives from unrelated numeric postmeta (view counters, analytics IDs) — only trusts bare-integer matches against real ACF image/gallery fields |
| `ghost-glint-svg.py` | standalone (`python3 tools/ghost-glint-svg.py "TEXT"`) | Generate the dynamic "ghost text" SVG (outline stroke + animated shine clipPath) for arbitrary text, proportionally sized — this one needs no WordPress context, so it's plain Python for previewing/tuning proportions before wiring it into a shortcode |
| `extract-elementor-controls.php` | `wp eval-file` | Re-run the extraction behind `data/elementor-core-pro-controls.json` against your own site — gets current data for your Elementor version and any third-party addon widgets it has |

## Multi-platform install

See `references/multiplatform-install-verification.md` — dated findings for
8 AI coding platforms' skill/rule conventions, since this space moves fast
enough that a 6-week-old assumption can already be wrong. **Re-verify before
trusting**, don't just copy the table.

```bash
python tools/install-skill.py --list
python tools/install-skill.py claude-code
python tools/install-skill.py cursor --to /path/to/proj
```

## Data (in `data/`)

- `platform-conventions.csv` — install paths + verified-as-of date per platform

## Author

Built and maintained by **moksa** at [moksaweb.com](https://moksaweb.com).
MIT licensed. Issues and PRs welcome.
