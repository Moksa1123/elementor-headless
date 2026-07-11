# Editing Shared Elementor Templates Safely

## Why this is different from editing a normal page

A normal WordPress page's `_elementor_data` belongs to exactly one post — edit
it freely. A **Theme Builder template** (Header, Footer, an archive template,
a singular-CPT template, or a loop-item "card" used inside a Posts/Loop Grid
widget) renders for *every* post matching its condition. You cannot hardcode
per-entity content into it — "this template shows Person A's name" is not a
valid edit if the template also renders for Person B and Person C.

If the content needs to vary per-post, it must be **dynamic** (an Elementor
Dynamic Tag pulling a custom field, or a shortcode widget backed by a PHP
function reading `get_the_ID()`), not a literal string baked into the
template's JSON.

## Navigating `_elementor_data` JSON without an off-by-one

`_elementor_data` is a JSON-encoded list of top-level sections, each with a
recursive `elements` array. Tools that report a widget's location as a `path`
array (e.g. `[0, 0, 1, 1, 0]`) are describing **alternating index/`elements`
hops** — every entry in the path after the first is an index into the *next*
`elements` array, not a direct property offset. Concretely, `path=[0,0,1,1,0]`
means:

```
data[0]                          # first top-level element
  ['elements'][0]                #   its first child
    ['elements'][1]               #     that child's 2nd child
      ['elements'][1]              #       that child's 2nd child
        ['elements'][0]             #         target widget
```

That's **four** `->['elements'][idx]` hops for a 5-element path array — count
them explicitly before writing the PHP/Python navigation code. Writing one
hop short (a very easy mistake — it's tempting to count path *entries* instead
of *hops*) lands you on the wrong container and either silently corrupts the
wrong sibling or throws a clear "not what I expected" error if you verify
before writing (see below — always verify).

## The safe-edit protocol

1. **Read and cache the current value** before changing anything:
   ```bash
   wp post meta get <template_id> _elementor_data > backup-<template_id>-$(date +%s).json
   ```
2. **Decode as JSON, navigate to the target, and assert what you expect to
   find is actually there before mutating.** A script that checks
   `$element['id'] === '<expected-id>'` and aborts loudly if it doesn't match
   is worth the extra five lines — it turns a silent corruption into an
   immediate, obvious error.
3. **Re-encode and write back** with `JSON_UNESCAPED_UNICODE |
   JSON_UNESCAPED_SLASHES` (Elementor's own export format uses unescaped
   Unicode; escaping it isn't wrong per se but makes diffs unreadable) and
   `wp_slash()` before `update_post_meta()` (WordPress expects slashed data
   going into `update_post_meta`/`update_option`, and skipping this step
   silently corrupts quotes/backslashes in the stored value on some WP
   versions).
4. **Flush the Elementor CSS cache** (`wp elementor flush-css`) — Elementor
   pre-generates and caches per-post CSS; a JSON change without this can leave
   stale styles until Elementor's own cache expires or is manually rebuilt.
5. **Flush the page-cache plugin** (Breeze/WP Rocket/W3TC/etc.), then the
   **host or CDN layer** (Cloudways app cache, Cloudflare) — flush from the
   inside out: Elementor's own generated assets first, then anything that
   might be caching the *page* those assets render into, then anything caching
   the whole *response* at the edge. Flushing in the wrong order can leave an
   edge cache serving a page built from stale Elementor CSS.
6. **Verify with a hard reload / cache-bypassed fetch**, not a cached one.
   `curl -s <url>` may return a CDN-cached response identical to before your
   change; confirm the specific thing you changed is actually present in the
   fetched markup, not just that the request returned 200.

## Editing theme `functions.php` (or any always-loaded PHP)

A syntax error here takes the *entire site* down on every single request —
there is no graceful degradation. Never edit it in place blind:

1. Fetch the current file, write the *complete* new version locally (not a
   diff/patch applied remotely — a full file you can lint before it ever
   touches production).
2. Upload to a scratch path (not the live path) and run `php -l
   <scratch-path>` there. Only proceed if it reports no syntax errors.
3. Back up the live file (copy, not move) before overwriting it.
4. Overwrite the live file, then `php -l` the *live* path too, as a second
   confirmation nothing changed in transit.
5. Smoke-test: fetch a couple of live pages immediately. If anything 500s,
   restore the backup immediately — don't debug in place on a broken
   production site.

## Turning a static decorative element into a dynamic one

See `dynamic-ghost-text-pattern.md` for a worked example: a template had a
large decorative background-text element (an SVG "ghost" label) hardcoded
identically across every post that shared the template. The fix wasn't to
edit the static text — it was to add a new shortcode backed by a PHP function
that computes the text (and every proportional dimension) from the current
post at render time, then swap the template's static widget for a `shortcode`
widget calling it. The general pattern — **shared template + "this should say
something different per post" → convert to a shortcode widget, not a text
edit** — recurs any time a Theme Builder template needs personalization.
