# The Style System: Group Controls, Custom CSS, and Free vs Pro

Most of a widget's Style-tab fields aren't defined per-widget — they come
from a small set of **Group Control** classes that any widget can plug in
with one line. Understanding this mechanism means you don't need to
memorize Border/Shadow/Typography field names per widget; you need to know
the *mechanism* once, and where to verify it for anything new.

## The Group Control mechanism, verified from source

A widget adds a whole family of related fields with one call:

```php
$this->add_group_control(
    Group_Control_Border::get_type(),
    [ 'name' => '_border', 'selector' => '{{WRAPPER}} .my-element' ]
);
```

The group class's `init_fields()` returns a map of sub-field keys; the
actual registered control names are **`{name}_{sub_field_key}`**. For
`Group_Control_Border` (confirmed from `elementor/includes/controls/groups/border.php`,
core Elementor since v1.0.0 — **not Pro**):

| Sub-field | Registered control name (with `name: '_border'`) | Type | Notes |
|---|---|---|---|
| `border` | `_border_border` | select | `''` (Default) / `none` / `solid` / `double` / `dotted` / `dashed` / `groove` |
| `width` | `_border_width` | dimensions, **responsive: true** | → also produces `_border_width_tablet` / `_border_width_mobile`; condition: `border!` is `''`/`none` |
| `color` | `_border_color` | color | same condition as width |

`_border_radius` is registered as a *separate* `add_responsive_control`
call right after the group (not part of the group itself) — confirmed in
`elementor/includes/widgets/common-base.php`'s `register_border_section()`,
which every widget calls as part of its shared "Advanced" tab setup.

**Box Shadow** (`Group_Control_Box_Shadow`, `elementor/includes/controls/groups/box-shadow.php`,
also core, also **not Pro**) follows the identical naming pattern: with
`name: '_box_shadow'` you'd get `_box_shadow_box_shadow` (a compound
{horizontal, vertical, blur, spread, color, position} value) plus whatever
additional sub-fields that group's `init_fields()` defines.

**This generalizes.** Any `Group_Control_*` class in
`elementor/includes/controls/groups/` (Typography, Background, CSS Filter,
Text Shadow, Image Size, and others) follows the same contract: read its
`init_fields()` method once, and you know the exact real control names for
every widget that uses it, with whatever `name` prefix that specific widget
chose.

```bash
# Find every Group Control class shipped with core Elementor:
ls wp-content/plugins/elementor/includes/controls/groups/
# Read one's field map directly:
cat wp-content/plugins/elementor/includes/controls/groups/typography.php
```

## Why a live `get_controls()` dump can still miss these

Group-control fields registered via `register_border_section()` and
similar shared private methods on `common-base.php` are added synchronously
during a widget's own registration — they should appear in a `get_controls()`
call. If your extraction shows the section marker (e.g. `_section_border`)
but nothing inside it, the gap is in *how* you're instantiating/reading the
widget, not in Elementor's architecture (unlike Custom CSS below, which is
a genuine hook-based injection that a bare `get_controls()` call
legitimately cannot see without also firing the relevant action). Verify
against the actual PHP source (as above) rather than trusting an
incomplete live dump for these specifically.

## Custom CSS: the one feature that really is hook-injected and Pro-only

Confirmed from `elementor-pro/modules/custom-css/module.php` — this is the
canonical example of a feature that's genuinely Pro-gated and genuinely
invisible to a plain `get_controls()` call, for a *real* architectural
reason (not a limitation of the extraction method):

- **Registration**: hooks `elementor/element/after_section_end`, checking
  for `$section_id === 'section_custom_css_pro'` (a placeholder banner
  section that core Elementor registers by default for Free users). If the
  site's Elementor Pro license has the `custom-css` feature
  (`API::is_licence_has_feature( 'custom-css', ... )`), the module removes
  the placeholder and registers the real section + control in its place.
  Free-tier sites keep the placeholder (an upgrade promotion), never the
  real field.
- **The real control**: `custom_css`, type `Controls_Manager::CODE`
  (language: css). Stored in the widget's own `settings` object exactly
  like any other control — `"settings": { "custom_css": "selector { ... }" }`.
  The literal string `selector` in the CSS gets replaced at render time with
  the widget's actual unique CSS class (`$post_css->get_element_unique_selector($element)`),
  so you write `selector { color: red; }` and it becomes scoped to that one
  element instance.
- **Page-level custom CSS** (as opposed to per-widget) is a *different*
  setting: `$document->get_settings( 'custom_css' )` — the page/document's
  own settings, not a widget's. Both get concatenated into the final
  generated stylesheet via the `elementor/element/parse_css` and
  `elementor/css-file/post/parse` action hooks respectively.

**To write custom CSS into a widget programmatically**, set `custom_css` in
its `settings` object directly — no different from setting any other
control, as long as the target site's Elementor Pro license actually has
this feature (verify with the license-feature check above, or just
empirically: does editing an existing widget's Style panel on that site
show a "Custom CSS" section at all?).

## Free vs Pro: how to actually verify it, not guess it

Three concrete techniques, in order of reliability:

1. **Widget-level**: check which plugin registers the widget class (its PHP
   file's path). `data/elementor-core-pro-controls.json`'s `source` field
   already has this for the shipped 135-widget dataset — `elementor-core`
   or `elementor-pro`.
2. **Feature-level, hook-injected features** (Custom CSS is the known
   example): grep the relevant `elementor-pro/modules/*/module.php` for
   `API::is_licence_has_feature` — the string literal passed as the first
   argument is the feature's actual license-gate name.
3. **Feature-level, everything else**: if it's defined in
   `elementor/includes/` (not `elementor-pro/`), it's core/Free, full stop
   — Elementor's directory boundary between the two plugins is the ground
   truth, not a feature's apparent sophistication. (Border and Box Shadow
   "feel" like premium features but are core — don't infer Pro-ness from a
   feature seeming advanced.)

**Do not** default to labeling something "Pro-only" just because it seems
powerful, and don't default to "Free" just because it's common — verify
with one of the three techniques above every time, and mark the source
inline in any generated code/documentation (`// Elementor Pro only —
verified via elementor-pro/modules/custom-css/module.php`).
