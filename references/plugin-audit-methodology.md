# Plugin & Template Usage Audit Methodology

## The mistake this exists to prevent

A plugin named `code-block-pro` was flagged as "0 usage" because a search for
the literal string `wp:code-block-pro` in `post_content` found nothing. The
plugin was deactivated. It turned out to be used in 10 published articles —
its real Gutenberg block name was `kevinbatdorf/code-block-pro` (the author's
own namespace, not the plugin slug). The deactivation broke syntax highlighting
on every one of those articles until it was caught.

The root cause: judging usage by a *guessed* signature instead of the plugin's
*actual* one. This is a systematic trap because plugin slugs, block names,
shortcode tags, and option keys frequently diverge:

- Block name namespace is the **author's** choice, not the plugin slug
  (`kevinbatdorf/code-block-pro`, not `code-block-pro/code-block-pro`).
- A shortcode tag can be anything the developer typed into `add_shortcode()`.
- An option key is whatever string was passed to `update_option()` — often
  prefixed with a site's own convention (`moksa_openai_api_key`) rather than
  the plugin's name, or namespaced by a *different* plugin's convention
  (`connectors_ai_google_api_key` for a "Google AI provider" plugin).

## Step 1 — find the real signature, in the plugin's own source

Before searching for anything, read the plugin:

```bash
# Gutenberg block: the canonical name is in block.json, not the folder name
find wp-content/plugins/<slug> -name 'block.json' -exec cat {} \; | grep '"name"'

# Shortcode: find the actual tag string passed to add_shortcode()
grep -rn "add_shortcode" wp-content/plugins/<slug>/

# Elementor widget integration (many plugins ship a Compatibility/Elementor/
# adapter that registers its own widget type — check for one)
find wp-content/plugins/<slug> -iname '*elementor*'

# Settings/option keys: grep the plugin's own get_option()/update_option() calls
grep -rho "get_option( *'[a-zA-Z_]*'" wp-content/plugins/<slug>/ | sort -u
```

If a plugin integrates with a *different* system that already has a working
pattern (e.g. one AI-provider plugin's key is confirmed live), use that
pattern to derive the naming convention for the *unconfirmed* one, rather than
guessing from scratch — e.g. if `connectors_ai_google_api_key` is a real,
populated option, then `connectors_ai_openai_api_key` /
`connectors_ai_anthropic_api_key` are the right things to check for the
sibling provider plugins, not `openai_api_key`.

## Step 2 — search for the real signature everywhere it could live

Not just `post_content`. At minimum:

```sql
-- Published/draft/future content
SELECT ID FROM wp_posts WHERE post_content LIKE '%<real-signature>%';

-- Elementor page data (widgets store their type here, not in post_content)
SELECT post_id FROM wp_postmeta WHERE meta_key = '_elementor_data' AND meta_value LIKE '%<real-signature>%';

-- Site options (for settings/config-based "usage")
SELECT option_name, option_value FROM wp_options WHERE option_name LIKE '%<real-signature>%';
```

For Elementor specifically, decode `_elementor_data` as JSON and walk the
`elements` tree collecting every `widgetType` — don't rely on string search
alone, since a widget type like `elementskit-accordion` needs to be matched by
type, not assumed to appear as readable text anywhere else on the page.

## Step 3 — for Elementor Library templates, "exists" ≠ "live"

A template living in `elementor_library` (Header, Footer, single-CPT
template, loop-item card, or a leftover demo page from the original theme
purchase) only actually renders if:

1. It has a non-empty `_elementor_conditions` meta assigning it to a Theme
   Builder location (`include/singular/team`, `include/archive`, `include/general`
   for header/footer, etc.) — **or**
2. Some other page/post embeds it directly, via the `[elementor-template
   id="X"]` shortcode in `post_content`, or a "Template" widget storing
   `template_id` inside another page's own `_elementor_data`.

A template with neither is dead weight — usually a leftover from the original
purchased theme's demo-content import (look for a batch of similarly-named
duplicates: multiple "About", "Home", "Services" entries with no assigned
condition is the signature of an unused demo kit, not real site content).

**The Elementor active Kit is a different risk class.** `get_option(
'elementor_active_kit' )` names the template that supplies *global* colors and
fonts for the whole site. Even if its name looks like leftover demo content
(a purchased theme's own "Kit Styles: <Theme Name>" entry), if it's the
*active* kit, deleting it changes site-wide typography/color defaults
immediately. Check `elementor_active_kit` explicitly and treat that ID as
untouchable regardless of what its title suggests; treat *inactive* kits as a
separate, lower-risk decision from ordinary page templates, but still confirm
with whoever owns the site before deleting a design-token container.

## Step 4 — orphaned media needs a false-positive guard

Cross-referencing every attachment ID/URL against `_thumbnail_id`,
`post_content`, and every `uploads/` path substring across `wp_postmeta` and
`wp_options` gives you a first-pass "unreferenced" list. Before trusting it:

**Do not** treat "this number appears somewhere in postmeta" as proof of a
real reference. Old low-numbered attachment IDs (from an early demo-content
import) frequently collide numerically with unrelated counters — page-view
trackers (`ekit_post_views_count`), SEO analytics object IDs
(`rank_math_analytic_object_id`), or anything else that happens to store a
small integer. These meta keys reference *posts*, not media, and the
collision is coincidental (WordPress shares one auto-increment ID space
across posts, pages, *and* attachments).

The correct guard: only treat a bare-integer meta match as a real reference
if the meta key belongs to a field genuinely typed to hold an attachment ID —
concretely, an ACF `image`/`gallery` field. Look those up from the field
group definition (`acf-field` posts, `type` = `image`/`gallery`) and only
cross-check *those* meta keys, not every numeric meta key in the database.

## Step 5 — deactivate, verify, then delete

1. Deactivate (don't delete) the plugin, or make the reversible change.
2. Curl the site's key pages (home, a few representative templates) and check
   for 200s — but see the note on gzip/compression and screenshot scaling in
   `SKILL.md`'s "Cross-checking your own work" section; a 200 isn't proof of
   a correct render.
3. Give it real time before permanent deletion — deactivation can be silently
   reversed by someone else on the team, or by a plugin's own re-activation
   hook; re-check status before assuming a prior decision still holds.
