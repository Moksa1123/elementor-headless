# Elementor Data Model — Containers, Widgets, Dynamic Tags

Elementor's own widget library has hundreds of widget types and thousands of
settings keys — enumerating all of it here would be both incomplete and
stale within a release cycle. What's actually worth pre-loading into a skill
is the **shape** of the data: once you know the recurring patterns below, you
can read *any* unfamiliar widget's settings by pulling one real example from
the site and pattern-matching, instead of guessing or re-deriving the schema
from scratch every session. That's the token saving — not memorizing every
widget, but never having to rediscover the *shape*.

## The container model (current Elementor, not legacy Section/Column)

Modern Elementor pages are built from nested `container` elements (Elementor's
Flexbox-based layout system), not the older Section → Column → Widget
hierarchy. A container's settings drive CSS flexbox properties directly:

```json
{
  "id": "6e43aa1",
  "elType": "container",
  "settings": {
    "content_width": "full",
    "flex_direction": "column",
    "flex_align_items": "flex-start",
    "flex_justify_content": "flex-start",
    "width": { "unit": "%", "size": 62, "sizes": [] },
    "width_tablet": { "unit": "%", "size": 100, "sizes": [] },
    "width_mobile": { "unit": "%", "size": 100, "sizes": [] },
    "padding": { "unit": "px", "top": "0", "right": "0", "bottom": "0", "left": "0", "isLinked": true },
    "flex_gap": { "unit": "px", "size": 10, "column": "10", "row": "10", "isLinked": true }
  },
  "elements": [ /* nested widgets or containers */ ],
  "isInner": true
}
```

**Responsive breakpoints are separate keys, not a nested object**: `width`,
`width_tablet`, `width_mobile` are three independent settings — Elementor
doesn't merge them into one responsive value at the data layer, the frontend
CSS generator does that. If a container looks fine on desktop but wrong on
mobile, check whether the `_mobile`/`_tablet` variant of the setting you
changed even exists on that element — it's easy to edit only the base key
and leave a stale responsive override in place.

**`isInner: true`** marks a container/widget nested inside another
container's `elements` array (as opposed to a top-level section). It's
informational for Elementor's own editor UI; you don't need to compute it
yourself when editing JSON directly, just carry over whatever the sibling
elements already have.

## Widget shape

Every leaf node is `elType: "widget"` with a `widgetType` naming which
widget class renders it, and a `settings` object whose keys are entirely
widget-specific:

```json
{
  "id": "64ffbc2",
  "elType": "widget",
  "widgetType": "heading",
  "settings": {
    "title": "TITLE",
    "header_size": "div",
    "align": "left",
    "title_color": "#70707C",
    "typography_typography": "custom",
    "typography_font_family": "Space Grotesk",
    "typography_font_weight": "700",
    "typography_font_size": { "unit": "px", "size": 13, "sizes": [] },
    "typography_line_height": { "unit": "em", "size": 1.3, "sizes": [] },
    "typography_letter_spacing": { "unit": "px", "size": 3, "sizes": [] }
  },
  "elements": [],
  "isInner": true
}
```

**The `typography_typography: "custom"` pattern** recurs across every widget
that has a text-style control (heading, text-editor, button, icon-box, etc.):
setting it to `"custom"` unlocks the sibling `typography_*` keys
(`_font_family`, `_font_weight`, `_font_size`, `_line_height`,
`_letter_spacing`, sometimes `_text_transform`). Without `"custom"`, the
widget inherits from the site's active Kit's global typography instead — if
a text style looks like it's "not applying," check whether
`typography_typography` is actually set to `"custom"` before assuming the
individual `typography_*` values are wrong.

**Dimension/size values are objects, not raw numbers**: `{ "unit": "px",
"size": 13, "sizes": [] }`, not `13`. This applies to font sizes, spacing,
widths, gaps — anywhere Elementor lets the user pick a unit (px/%/em/vh).
Writing a raw integer into one of these fields (instead of the unit object)
either gets silently ignored by Elementor's frontend or throws in the editor,
depending on version — always match the existing shape.

## Dynamic tags: pulling live post data into any widget

Instead of hardcoding a widget's `title`/`text`/etc., a value can be bound to
post data via the `__dynamic__` sibling key:

```json
{
  "title": "成員姓名",
  "__dynamic__": {
    "title": "[elementor-tag id=\"374ddab\" name=\"post-title\" settings=\"%7B%7D\"]"
  }
}
```

or, for a custom field:

```json
{
  "title": "職稱",
  "__dynamic__": {
    "title": "[elementor-tag id=\"c79959a\" name=\"post-custom-field\" settings=\"%7B%22key%22%3A%20%22job_title%22%7D\"]"
  }
}
```

The plain `title` key stays as a fallback/editor-preview placeholder; the
**actual rendered value comes from `__dynamic__.title`** when present.
`settings` inside the tag string is URL-encoded JSON (`%7B%22key%22...` →
`{"key":"job_title"}`) — decode it if you need to read which custom field
a tag pulls from. This is Elementor Pro's Dynamic Tags system: it's how a
single shared Theme Builder template shows different content per post
*without* needing a custom shortcode — reach for this first for simple
field-binding needs, and only build a custom shortcode (see
`dynamic-ghost-text-pattern.md`) when the content needs actual computation
(derived text, generated markup) beyond a raw field value.

**This is the "read before you write" priority order** when a shared
template needs to show something different per post:
1. Does an existing Elementor Dynamic Tag already do this (post title,
   featured image, a plain ACF field value)? Use it — no code needed.
2. Does it need light computation on top of a field value (string
   manipulation, conditional formatting)? A `shortcode` widget backed by a
   small PHP function is next.
3. Only reach for a custom Elementor widget class (a whole new PHP widget
   registered via Elementor's Widget API) if the shortcode approach can't
   express the layout/interactivity needed — this is real development work,
   not a template edit, and should be scoped as such.

## Common widget types and what to expect in their settings

| `widgetType` | Typical settings to look for |
|---|---|
| `heading` | `title` (or `__dynamic__.title`), `header_size` (h1-h6 or `div`), `align`, `title_color`, `typography_*` |
| `text-editor` | `editor` (raw HTML string) |
| `image` | `image` (`{url, id, ...}` object), `image_size`, `align` |
| `button` | `text`, `link` (`{url, is_external, nofollow}`), `align`, `button_type`, typography/color controls prefixed similarly |
| `icon-list` | `icon_list` (array of `{text, selected_icon, link}`) |
| `spacer` / `divider` | `space` (unit object), minimal other settings |
| `html` | `html` (raw string — static markup; see `elementor-safe-edit.md` for why this can't vary per-post in a shared template) |
| `shortcode` | `shortcode` (a single string like `[my_tag attr="val"]`) — the escape hatch for per-post dynamic content, see above |
| `posts` / `loop-grid` | `posts_post_type`, `posts_per_page`, query/pagination settings — pulls a live post query, not static content |
| `nav-menu` | `menu` (menu ID/slug), layout settings |
| `form` | Elementor Pro Forms — field array, actions-after-submit, integration settings |
| `countdown` | `due_date`, per-unit labels, `actions` for expiry behaviour |
| `image-carousel` | `carousel` (array of images), slides-to-show, autoplay settings |

Third-party page-builder-addon plugins (ElementsKit, Unlimited Elements,
JetSmartFilters, etc.) register their own `widgetType` values, commonly
prefixed with the plugin's own namespace (`elementskit-accordion`,
`ucaddon_post_grid`, `jet-smart-filters-select`). Their settings shapes are
plugin-specific — same rule as `plugin-audit-methodology.md`: check whether
a widget type is genuinely rendering anywhere live before deciding it's safe
to remove the plugin that provides it (a widget registered by a plugin can
sit unused in a dead demo template just like any other content).

## Template types and Theme Builder conditions

An `elementor_library` post's `_elementor_template_type` postmeta value
(`header`, `footer`, `single-post`, `archive`, `section`, `page`, `kit`, …)
combined with its `_elementor_conditions` postmeta (`include/general`,
`include/singular/<cpt-slug>`, `include/archive`, `exclude/archive/<taxonomy-or-cpt>`,
etc.) is what Theme Builder actually uses to decide *where* a shared template
renders. Both must be checked together — a template can have a plausible
`_elementor_template_type` and *no* condition at all, meaning Theme Builder
never assigns it anywhere (see `plugin-audit-methodology.md` Step 3 for how
this shows up as harmless-looking dead weight from an old theme's demo
import).

The site's active Kit (global colors/fonts/spacing defaults) is a *different*
`elementor_library` entry, referenced by the `elementor_active_kit` option —
see the Kit-specific warning in `plugin-audit-methodology.md`.

## How to read an unfamiliar widget/setting fast, without guessing

1. Find one real example already on the live site (`_elementor_data` of any
   page using it) and read its actual JSON — don't guess a settings key name
   from Elementor's admin-UI label; the stored key is often a different,
   more technical name (`typography_font_family`, not "Font Family").
2. If nothing on the site uses it yet, check the widget's own PHP source
   (`wp-content/plugins/elementor*/includes/widgets/<name>.php` or the
   relevant addon plugin) for its `register_controls()` method — that's the
   authoritative list of every setting key and its default/type.
3. Prefer copying the shape of a working sibling element over hand-writing a
   new settings object from memory — dimension objects, color formats, and
   responsive-suffix conventions are easy to get subtly wrong by hand.
