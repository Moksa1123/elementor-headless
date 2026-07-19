# Containers: flex, grid, and the 354 controls

The container is the biggest single element in Elementor — **354 settable
controls**, more than any widget — and it is where layout actually happens. It is
also the thing most likely to be missing from a schema, because it is not a widget
and does not come back from `get_widget_types()`. You have to ask
`elements_manager` for it.

```bash
python tools/el.py container --tab layout      # the layout surface
python tools/el.py container --tab style       # background, border, shape divider
python tools/el.py container --grep grid
```

## Two modes, one element

`container_type` switches the whole element between flex and CSS grid. Every
layout control is conditional on it, so the flex controls are inert in grid mode
and vice versa — they are stored and ignored, exactly like any other unmet
condition.

```json
"container_type": "flex"     // or "grid"
```

### Flex

```json
{
  "container_type": "flex",
  "content_width": "boxed",                                  // boxed | full
  "boxed_width": { "unit": "px", "size": 960, "sizes": [] }, // needs content_width=boxed
  "flex_direction": "column",                                // row | column | row-reverse | column-reverse
  "flex_justify_content": "center",
  "flex_align_items": "center",
  "flex_gap": { "column": "24", "row": "24", "isLinked": true, "unit": "px" },
  "flex_wrap": "wrap",                                       // nowrap | wrap
  "flex_align_content": "center"                             // needs flex_wrap=wrap
}
```

`flex_gap` is a `gaps` control, not a slider — `{column, row, isLinked, unit}`.

### Grid

```json
{
  "container_type": "grid",
  "grid_columns_grid": { "unit": "fr", "size": 3, "sizes": [] },
  "grid_rows_grid":    { "unit": "fr", "size": 2, "sizes": [] },
  "grid_gaps": { "column": "20", "row": "20", "isLinked": true, "unit": "px" },
  "grid_auto_flow": "row",
  "grid_justify_items": "stretch",
  "grid_align_items": "stretch"
}
```

`grid_justify_content` and `grid_align_content` carry a two-part condition —
`container_type = grid` **and** `grid_columns_grid[unit] = custom`. They do
nothing on a plain `fr` track definition. `el.py` prints the full condition.

## Everything is a CSS custom property

The container writes its layout to CSS variables, not to properties:

```css
.elementor-element-1a2b3c4{
  --display:flex;
  --flex-direction:column;
  --align-items:center;
  --gap:24px 24px;
  --padding-top:80px; --padding-bottom:80px;
}
```

This is why `el.py`'s `css:` column shows `--gap`, `--justify-content`,
`--padding-top` rather than `gap`, `justify-content`, `padding`. When you go
looking for "which control sets padding", search the custom property:

```bash
python tools/el.py css --padding-top
```

## Sizing the children

A container's children are flex items, and flex items default to
`min-width: auto` — they will not shrink below their content. Three
long-description widgets in a `flex-direction: row` container will therefore blow
past a third of the width each and wrap, even though the container is correctly
set to row. The container is not wrong; the children have no width.

Each widget carries the sizing controls in its **shared Advanced tab**:

```json
"_element_width": "initial",                                  // '' | inherit | auto | initial
"_element_custom_width":        { "unit": "%", "size": 31,  "sizes": [] },
"_element_custom_width_mobile": { "unit": "%", "size": 100, "sizes": [] },
"_flex_size": "custom",                                       // none | grow | shrink | custom
"_flex_grow": 1,
"_flex_shrink": 1
}
```

`_element_custom_width` requires `_element_width = "initial"`. `_flex_grow` and
`_flex_shrink` require `_flex_size = "custom"`. Set the value without the mode and
nothing happens.

There is also a `flex-item` group control (8 fields: `basis_type`, `basis`,
`align_self`, `order`, `order_custom`, `size`, `grow`, `shrink`) — free.

## Nesting

Containers nest. A row of cards is a column container holding a row container
holding widgets:

```
container (flex, column, boxed)
├── widget  heading
├── widget  text-editor
├── container (flex, row, wrap)      <- content_width: full
│   ├── widget  icon-box
│   ├── widget  icon-box
│   └── widget  icon-box
└── widget  button
```

That is `examples/demo-page.json`, which is a real published page:
**https://moksaweb.com/elementor-headless-demo/**

## What Pro adds to the container

79 controls, measured against a Pro-less install:

| Section | n |
|---|---|
| `section_effects` | 43 (motion FX + sticky) |
| `section_background` | 33 (background slideshow etc.) |
| `_section_attributes` | 1 (`_attributes`) |
| `section_custom_css` | 1 (`custom_css`) |
| `section_layout` | 1 |

Everything else the container does — flex, grid, gap, padding, background colour,
border, border radius, box shadow, shape dividers, responsive — is **free**.

## section and column: legacy

`section` (290 controls) and `column` (262) predate the container. They still
render, and you will meet them in existing pages, but they cannot do flex or grid
and Elementor is not investing in them. Build new pages with containers.

A `column` is only valid inside a `section`. A `container` can go anywhere.
