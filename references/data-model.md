# The Elementor data model

An Elementor page is not stored in `post_content`. It is a JSON tree in post meta,
and the renderer walks that tree. Write the tree, and you have built the page —
no editor, no browser, no DOM.

## The meta keys, all four of them

Writing `_elementor_data` alone is the classic first mistake. The post saves, the
page loads, and it renders as though Elementor were not installed — because the
theme fell back to `post_content`.

| Meta key | Value | Why it matters |
|---|---|---|
| `_elementor_data` | the tree, JSON-encoded | the page itself |
| `_elementor_edit_mode` | `builder` | without it the theme renders `post_content` instead |
| `_elementor_template_type` | `wp-page` / `wp-post` | the editor mishandles the post without it |
| `_elementor_version` | e.g. `4.1.4` | tells Elementor which data upgrades to run |

Then the CSS. Elementor compiles each post's styling into its own file
(`uploads/elementor/css/post-<id>.css`). Until that is rebuilt the page ships the
**old** stylesheet, so a perfectly correct tree still renders wrong:

```bash
wp elementor flush-css --post-id=<id>
```

`tools/apply-page.php` does all of this — meta, slashing, CSS rebuild — and backs
up the previous tree first.

## The tree

```jsonc
[                                  // top level is a LIST of containers
  {
    "id": "1a2b3c4",               // unique 7-char lowercase hex
    "elType": "container",         // container | section | column | widget
    "settings": { ... },           // the control values
    "elements": [                  // children; [] on leaves
      {
        "id": "2b3c4d5",
        "elType": "widget",
        "widgetType": "heading",   // widgets need BOTH elType AND widgetType
        "settings": { "title": "Hello" },
        "elements": []             // yes, widgets need this too
      }
    ]
  }
]
```

Four rules that bite:

1. **`id` must be unique across the whole tree.** Duplicates break the editor in
   ways that look like data corruption rather than a duplicate id.
2. **`id` is 7 lowercase hex characters.** `eh10a01` looks fine and is not hex.
3. **Every node needs `elements`**, including widgets. Use `[]`.
4. **Widgets need `elType: "widget"` *and* `widgetType`.** One without the other
   renders nothing.

`tools/validate-page.py` checks all four, plus every control name and value shape,
before you write anything.

## elType: what actually exists

```
container   the modern layout primitive — flex or grid   356 controls
section     legacy, pre-3.6                              292 controls
column      legacy, only valid inside a section          262 controls
widget      a leaf; 135 kinds (64 free, 71 Pro)
```

Build new pages with **containers**. Section/column still render (Elementor keeps
them for backwards compatibility) but they are not where the platform is going,
and they cannot do flex or grid. You will still meet them when reading existing
pages, which is why they are in the schema.

## Nested widgets: the one place a widget has children

`nested-tabs`, `nested-accordion`, `mega-menu` (all gated on the `nested-elements`
experiment) break rule 3's spirit: their `elements` is NOT empty. Each child is a
**container**, and the Nth child is the content of the Nth item in the widget's
repeater - the pairing is by INDEX, nothing in the child points back:

```jsonc
{
  "elType": "widget", "widgetType": "nested-tabs",
  "settings": { "tabs": [
      { "_id": "a1b2c3d", "tab_title": "Alpha" },
      { "_id": "b2c3d4e", "tab_title": "Beta" } ] },
  "elements": [
    { "elType": "container",                       // content of tab 1
      "settings": { "_title": "Tab #1", "content_width": "full" },
      "elements": [ ...widgets... ] },
    { "elType": "container", ... }                 // content of tab 2
  ]
}
```

That is Elementor's own default structure (`nested-tabs.php::tab_content_container`),
and a tree built exactly like this headlessly renders correctly on a live page -
tab titles from the repeater, per-tab content from the child containers. `_title`
is the editor's element label; Elementor writes it on these children itself.

## settings: the control values

`settings` is a flat map of control name to value. Not nested by section, not
nested by tab — flat.

```json
"settings": {
  "container_type": "flex",
  "flex_direction": "column",
  "padding":        { "unit": "px", "top": "80", "right": "24", "bottom": "80", "left": "24", "isLinked": false },
  "padding_mobile": { "unit": "px", "top": "40", "right": "16", "bottom": "40", "left": "16", "isLinked": false },
  "background_background": "classic",
  "background_color": "#0F172A"
}
```

Three things are going on in those six lines, and each has its own page:

- the **value shape** depends on the control's *type* — `padding` is a
  `dimensions` control, so it takes an object, not `"80px"`. See
  [control-types.md](control-types.md).
- `padding_mobile` is the **responsive suffix** mechanism. See
  [responsive.md](responsive.md).
- `background_color` only applies when `background_background` is set — controls
  have **conditions**, and an unmet condition means the value is stored and then
  ignored. `el.py` prints them as `needs:{...}`.

Anything you write that Elementor does not recognise is kept in the database and
ignored. There is no error. This is the single most important fact about the
format, and the reason this skill ships a validator.

## Two side-channels that are not controls

`settings` has two reserved keys that are not control values.

**`__globals__`** points a control at a Global Colour or Global Font instead of a
literal value. The referenced value lives in the active Kit, so changing it in
Site Settings updates every element that points at it:

```json
"settings": {
  "__globals__": {
    "title_color": "globals/colors?id=primary",
    "typography_typography": "globals/typography?id=text"
  }
}
```

**`__dynamic__`** binds a control to a dynamic tag — a post field, an ACF field,
a shortcode — resolved at render time:

```json
"settings": {
  "__dynamic__": {
    "title": "[elementor-tag id=\"a1b2c3d\" name=\"post-title\" settings=\"%7B%7D\"]"
  }
}
```

The `settings` attribute is a **URL-encoded JSON object**. `%7B%7D` is `{}`.

Both keys sit alongside the normal controls, and both override whatever literal
value the control also has. `validate-page.py` skips them rather than treating
them as unknown controls.

## The active Kit

`get_option('elementor_active_kit')` is the post ID of the template that supplies
the site's global colours, fonts and layout defaults. It looks like leftover demo
content and it is not: **delete it and every global reference on the site breaks.**
Nothing else in Elementor will warn you about this.

## `_elementor_page_settings` — the page's own settings, beside the tree

`_elementor_data` styles what is INSIDE the page. The page itself - its template,
its title, its background - is a separate meta, one serialized array:

```php
update_post_meta( $id, '_elementor_page_settings', wp_slash( [
    'template'   => 'elementor_canvas',   // no theme header/footer at all
    'hide_title' => 'yes',
    'padding'    => [ 'unit' => 'px', 'top' => '0', ... ],
] ) );
```

`template` is the one everyone needs: `default` / `elementor_canvas` /
`elementor_header_footer` / `elementor_theme`. A landing page built headlessly
keeps the site chrome until this is set, and nothing in the tree can change that.

**And `template` is the exception to the mechanism.** It appears in the page
settings panel, but Elementor does not act on it from there - it is a WordPress
page template, stored in `_wp_page_template`, and WordPress is what applies it.
Write it only into `_elementor_page_settings` and nothing changes; verified on a
live site (settings saved, body class absent, header still rendered). Write both
- `apply-page.php` does - and the theme chrome disappears.
`el.py page-settings` lists all 48 keys (page background, per-page margin/padding,
custom CSS...); `apply-page.php` takes the object as an optional third argument.

**The Kit is the same mechanism, site-wide.** `get_option('elementor_active_kit')`
is a post id, and ITS `_elementor_page_settings` is the entire Site Settings panel
- 773 controls: global colors (`system_colors` / `custom_colors` repeaters),
global fonts, theme style, layout defaults, lightbox. A `__globals__` reference
like `globals/colors?id=primary` resolves to the repeater item whose `_id`
matches. After editing the kit, regenerate CSS for the whole site
(`wp elementor flush-css`), not one post. `el.py kit` queries the surface.

## Caches, flushed inside-out

Getting the tree right and still seeing the old page almost always means a cache.
There are **four** layers, and the innermost one is the one nobody expects:

```bash
# 1. the rendered HTML  <- a POST META, and the one that catches people out
wp post meta delete <id> _elementor_element_cache

# 2. the compiled CSS
wp elementor flush-css --post-id=<id>

# 3. the page cache
wp breeze purge --cache=all

# 4. the CDN / Varnish layer
```

`apply-page.php` does 1 and 2. You still own 3 and 4.

### `_elementor_element_cache` — the one that makes a correct tree render wrong

Elementor stores **the HTML it rendered for each element** in a post meta
(`Document::CACHE_META_KEY`) and serves it straight back out of
`get_builder_content_for_display()`. Its own `Document::save()` deletes the meta on
every save. Writing `_elementor_data` directly does not.

So the headless failure looks like this:

- the post updates
- `_elementor_data` reads back exactly what you wrote
- the compiled CSS file changes, and is correct
- **and the page keeps serving the previous markup**

No error, anywhere. It is the single most convincing way to conclude that your
JSON is wrong when it is perfectly right.

This project shipped that bug. An entire control-by-control verification sweep ran
green against it, because that sweep read the compiled CSS — a separate file, which
we always rebuilt. It surfaced the moment a sweep read the **HTML** instead, and
every batch came back byte-identical to the first one.

```php
delete_post_meta( $post_id, \Elementor\Core\Base\Document::CACHE_META_KEY );
```

Reference the constant, not the string. If Elementor renames the key, that line
should break loudly rather than quietly clear nothing.
