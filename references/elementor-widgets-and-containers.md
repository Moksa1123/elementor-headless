# Elementor Data Model — Verified From a Live Install

Everything in this file was extracted by actually querying a live
Elementor + Elementor Pro installation's registered widget controls
(`\Elementor\Plugin::$instance->widgets_manager->get_widget_types()` →
`$widget->get_controls()`), not written from memory or general knowledge.
Where the live data had a real gap, that gap is documented as a gap — not
papered over with a guess. See `data/elementor-core-pro-controls.json` for
the full underlying dataset (135 widgets, Elementor core + Pro only —
third-party addon widgets vary per install; re-run the extraction script
below against your own site for those).

**Verified scale, one snapshot (2026-07-11), one real site**: 164 registered
widgets total, 48,238 individual controls. 135 of those widgets (elementor-
core: 64, elementor-pro: 71) are covered in the shipped data file; the
remaining 29 came from third-party addon plugins on that specific site and
were excluded from the shipped dataset since they're not universal to
Elementor itself.

## How to reproduce this extraction on any site

```php
<?php
// wp eval-file this against any live WordPress + Elementor install.
$widgets_manager = \Elementor\Plugin::$instance->widgets_manager;
foreach ( $widgets_manager->get_widget_types() as $name => $widget ) {
    $controls = $widget->get_controls();
    // $controls is a flat, ORDER-PRESERVING array. Entries of type
    // "section" mark section boundaries; every control between one
    // section entry and the next belongs to that section. There is no
    // reliable per-control "tab" (Content/Style/Advanced) field on a live
    // get_controls() call — infer grouping from which SECTION NAME a
    // control falls under instead (see the universal section list below).
    echo "$name: " . count( $controls ) . " controls\n";
}
```

Two things this method does **not** capture (verified gap, not guessed):
Border/Box-Shadow group controls and the Custom CSS feature are injected by
Elementor Pro via WordPress action hooks tied to specific section IDs
(`elementor/element/{element_type}/{section_id}/before_section_end` style
hooks checking for `'section_custom_css_pro'` etc. — confirmed by reading
`elementor-pro/modules/custom-css/module.php` directly), not registered as
part of a widget's own `_register_controls()`. A plain `get_controls()` call
outside the full editor/hook-firing context won't show them. If you need
those specifically, either inspect a widget's rendered editor config (open
it in the Elementor editor and read the panel's JS config) or read the
relevant Pro module's source directly for the exact control names in your
installed version.

## The container model (current Elementor, not legacy Section/Column)

Modern Elementor pages are built from nested `container` elements (Flexbox-
based layout), not the older Section → Column → Widget hierarchy:

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

**Responsive breakpoints are separate sibling keys, not a nested object.**
`width`, `width_tablet`, `width_mobile` are three independent settings —
Elementor doesn't merge them at the data layer. Confirmed at scale: of
48,238 controls captured, **9,622 (20%) carry a `_tablet` or `_mobile`
suffix** — responsive variants are genuinely pervasive, not an edge case.
If a value looks fine on desktop but wrong on mobile, check whether the
`_mobile`/`_tablet` sibling of the setting you changed even exists and has
the value you expect — it's a separate control, not a computed override.

## Widget shape

Every leaf node is `elType: "widget"` with a `widgetType` naming the widget
class, and a `settings` object whose keys are widget-specific:

```json
{
  "id": "64ffbc2", "elType": "widget", "widgetType": "heading",
  "settings": {
    "title": "TITLE", "header_size": "div", "align": "left",
    "title_color": "#70707C",
    "typography_typography": "custom",
    "typography_font_family": "Space Grotesk",
    "typography_font_weight": "700",
    "typography_font_size": { "unit": "px", "size": 13, "sizes": [] },
    "typography_line_height": { "unit": "em", "size": 1.3, "sizes": [] },
    "typography_letter_spacing": { "unit": "px", "size": 3, "sizes": [] }
  },
  "elements": [], "isInner": true
}
```

**Dimension/size values are always `{unit, size, sizes}` objects**, never a
raw number — this applies uniformly across the 12,962 `slider`-type controls
(the single most common control type in the whole dataset — more common
than `text`, `select`, or `switcher`). Writing a bare integer instead of the
unit object is the most common way a manual JSON edit silently fails to
apply.

**`typography_typography: "custom"`** unlocks the sibling `typography_*`
keys on any widget with a text-style control; without it, the widget
inherits the site's active Kit's global typography instead.

## Control type frequency, whole dataset (164 widgets, 48,238 controls)

The most common control types, in order — useful for knowing what you're
likely to encounter and roughly how each behaves:

| Type | Count | Shape |
|---|---|---|
| `slider` | 12,962 | `{unit, size, sizes}` — a numeric value with a unit picker |
| `text` | 5,697 | plain string |
| `switcher` | 5,187 | `"yes"` / unset (boolean-ish toggle) |
| `select` | 4,656 | one string value from a fixed option list |
| `number` | 4,167 | plain numeric string |
| `popover_toggle` | 2,568 | boolean gate that reveals a popover of further controls when enabled |
| `section` | 2,415 | not a real setting — a section-boundary marker (see below) |
| `tab` | 1,353 | sub-boundary marker inside a `tabs` group (e.g. Normal/Hover state) |
| `raw_html` | 1,234 | static help text/notice rendered in the editor panel, not a value |
| `select2` | 1,229 | multi-select, value is an array |
| `color` | 884 | hex/rgba string |
| `choose` | 786 | icon-button group (e.g. alignment left/center/right), value is the chosen key |
| `tabs` | 656 | wrapper marking the start of a Normal/Hover (or similar) tab group |
| `heading` | 651 | a label-only divider within the panel, not a value |
| `alert` | 621 | static warning/info box in the editor panel, not a value |
| `animation` | 528 | entrance-animation picker |
| `hidden` | 502 | a value the editor computes/stores but doesn't expose a visible field for |
| `divider` | 498 | visual separator in the panel, not a value |
| `gallery` | 433 | array of `{id, url}` image objects |
| `media` | 395 | `{url, id, size}` single-image object |
| `repeater` | 58 | array of sub-control-groups (e.g. icon list items, FAQ items) |
| `query` | 54 | a post-query configuration (post type, taxonomy, count, order) — the backbone of `posts`/`loop-grid` widgets |
| `url` | 50 | `{url, is_external, nofollow}` object |

`section`, `tab`, `tabs`, `heading`, `alert`, `divider`, and `raw_html` are
**structural/presentational entries in the panel, not data** — they exist to
organize the Elementor *editor UI*, not to store a value in `settings`. When
reading a widget's real rendered `settings` (as opposed to its control
*definitions*), you won't see these — only the actual value-bearing control
names end up as keys in a saved widget's `settings` object.

## The universal "Advanced" tab — 9 sections present in 98% of widgets

Verified: **161 of 164 widgets (98%)** carry these same nine sections,
confirming they're injected by Elementor's shared base class, not defined
per-widget. Full real control list for each (from a representative
elementor-core widget):

### `_section_style` (Layout)
`_element_width`, `_element_width_tablet`, `_element_width_mobile` (select —
constrains the widget's own width within its container independent of the
container's flex settings), `_position` (select), `_element_id` / `_css_classes`
(text — the widget's HTML `id`/`class` attributes), `e_display_conditions`
(conditional visibility rules), `_element_cache` (select).

### `section_effects` (Motion Effects)
Scrolling effects: `motion_fx_motion_fx_scrolling` (switcher gate) then per-
effect triples of `{effect}_effect` (popover_toggle) / `{effect}_direction`
(select) / `{effect}_speed` or `_level` (slider) / `{effect}_range` or
`_affectedRange` (slider) for `translateY`, `translateX`, `opacity`, `blur`,
`rotateZ`, `scale` — each independently togglable. Mouse-track effects:
`motion_fx_mouseTrack_*`, `motion_fx_tilt_*`. Device scope:
`motion_fx_devices` (select2, default `["desktop","tablet","mobile"]`).
Sticky positioning: `sticky` (select), `sticky_on` (select2, same device
default), `sticky_offset`/`sticky_effects_offset`/`sticky_anchor_link_offset`
(number, each with `_tablet`/`_mobile` variants), `sticky_parent` (switcher).
Entrance animation: `_animation` (+ `_tablet`/`_mobile`), `animation_duration`,
`_animation_delay`.

### `_section_transform` (Transform)
A `tabs` group with `_tab_positioning` (Normal) and
`_tab_positioning_hover` (Hover) — every transform below exists in both
states (the `_hover` suffix duplicates the whole set). Per state:
rotate (`_transform_rotateZ/X/Y_effect` sliders + `_transform_rotate_3d`
switcher), perspective, translate (`_transform_translateX/Y_effect`), scale
(`_transform_scale_effect` uniform + `_transform_scaleX/Y_effect` +
`_transform_keep_proportions` switcher), skew (`_transform_skewX/Y_effect`),
flip (`_transform_flipX/Y_effect`, type `choose`). Every numeric transform
control has independent `_tablet`/`_mobile` variants — this section alone
accounts for a large share of the dataset's 9,622 responsive-suffixed
controls.

### `_section_background` (Background)
A `tabs` group: Normal (`_tab_background_normal`) and Hover
(`_tab_background_hover`), each with the **identical** full field set (Hover
fields are the same names prefixed `_hover_`): `_background_color` +
`_background_color_b` (a second color, for gradient — default
`#f2295b`), `_background_image` (media object), video background
(`_background_video_link/_start/_end`, `_background_play_once`,
`_background_play_on_mobile`, `_background_privacy_mode`), and a slideshow
mode (`_background_slideshow_gallery` + loop/duration/transition/lazyload/
Ken-Burns-zoom settings).

### `_section_masking`
Just `_mask_switch` (switcher) at the base-widget level — the fuller mask
shape/image/size controls appear only when enabled, and (like Border/Custom
CSS) may be injected via a hook not fully captured by a plain
`get_controls()` call; verify directly if you need the enabled-state fields.

### `_section_responsive` (Responsive visibility)
Exactly three controls: `hide_desktop`, `hide_tablet`, `hide_mobile`
(switcher each) — the entire mechanism for "show this on mobile only" /
"hide this on desktop" style visibility rules. Nothing more elaborate lives
here; per-breakpoint *value* overrides (not visibility) are handled by the
`_tablet`/`_mobile` sibling-key pattern on individual controls elsewhere,
not by this section.

### `_section_attributes` (Custom Attributes)
One `_attributes` textarea — raw `key|value` pairs (one per line, per
Elementor's own documented syntax) applied as literal HTML attributes on the
widget's wrapper element.

### `_section_border` and `section_custom_css` — the documented gap
Both sections exist as section *markers* in every widget (98% presence,
same as the rest), but their actual field controls (border width/style/
color/radius; box-shadow; the raw custom-CSS textarea) are injected by
Elementor Pro's hook-based feature modules at a later stage than a direct
`get_controls()` call captures — see "How to reproduce this extraction"
above for why, and how to get them directly from source if you need the
exact current field names for your installed version.

## Dynamic tags: pulling live post data into any widget

Instead of hardcoding a widget's `title`/`text`/etc., bind it to post data
via the `__dynamic__` sibling key:

```json
{
  "title": "成員姓名",
  "__dynamic__": { "title": "[elementor-tag id=\"374ddab\" name=\"post-title\" settings=\"%7B%7D\"]" }
}
```

or for a custom field:

```json
{
  "title": "職稱",
  "__dynamic__": { "title": "[elementor-tag id=\"c79959a\" name=\"post-custom-field\" settings=\"%7B%22key%22%3A%20%22job_title%22%7D\"]" }
}
```

The plain key (`title`) stays as an editor-preview fallback; the **actual
rendered value comes from `__dynamic__.title`** when present. The tag's
`settings` attribute is URL-encoded JSON (`%7B%22key%22...` →
`{"key":"job_title"}`) — decode it to see which field a tag pulls from.

**Priority order when a shared template needs to vary per post:**
1. An existing Dynamic Tag (post title, featured image, a plain ACF field)
   — no code needed.
2. Light computation on top of a field value → a `shortcode` widget backed
   by a small PHP function (see `dynamic-ghost-text-pattern.md`).
3. A full custom Elementor widget class, registered via the Widget API —
   only when the shortcode approach can't express the needed
   layout/interactivity. This is real plugin development, not a template
   edit; scope it as such.

## Template types and Theme Builder conditions

An `elementor_library` post's `_elementor_template_type` (`header`,
`footer`, `single-post`, `archive`, `section`, `page`, `kit`, …) combined
with `_elementor_conditions` (`include/general`,
`include/singular/<cpt-slug>`, `include/archive`,
`exclude/archive/<taxonomy-or-cpt>`, etc.) is what Theme Builder uses to
decide *where* a shared template renders. Check both together — a template
can have a plausible type and *no* condition, meaning it never actually
renders anywhere (see `plugin-audit-methodology.md` Step 3).

The site's active Kit (global colors/fonts/spacing defaults) is a different
`elementor_library` entry, referenced by the `elementor_active_kit` option —
see the Kit-specific warning in `plugin-audit-methodology.md`.

## Widget-specific Content/Style controls: use the data file, not prose

The remaining ~38,000 controls (everything outside the 9 universal
Advanced-tab sections above) are genuinely widget-specific — a Progress Bar
widget's controls have nothing in common with a Testimonial Carousel's.
Hand-writing prose for all 135 widgets individually would be enormous and
would go stale the moment Elementor ships an update. Instead:

```bash
python -c "
import json
data = json.load(open('data/elementor-core-pro-controls.json', encoding='utf-8'))
w = data['icon-box']  # any widgetType from the JSON's top-level keys
print(w['title'], w['source'], w['control_count'], 'controls')
for c in w['controls']:
    print(' ', c['name'], c['type'], c.get('section'))
"
```

This is the actual token saving the size of this dataset is for: a future
session doesn't need to `wp eval-file` a fresh extraction or read Elementor's
PHP source to find out what an unfamiliar widget's controls are called —
it's already sitting in `data/`, queryable in one read instead of a
multi-step live investigation.
