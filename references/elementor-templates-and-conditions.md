# Template Management, Display Conditions, and Advanced Conditions

Everything here is verified against Elementor Pro's Theme Builder source
(`elementor-pro/modules/theme-builder/`), not inferred from one site's
usage — the condition type/name enumeration below is the *complete* list
Elementor Pro ships, not just the handful a given site happens to use.

## Template management (create / read / apply)

A Theme Builder template is a `elementor_library` post, same post type used
for saved sections/pages in the Elementor library. Three pieces of data
define one:

| Meta key | Purpose |
|---|---|
| `_elementor_data` | The JSON widget/container tree (see `elementor-widgets-and-containers.md`) |
| `_elementor_template_type` | `header`, `footer`, `single`, `archive`, `section`, `page`, `popup`, `kit`, … — which Theme Builder slot this template is built for |
| `_elementor_conditions` | Array of condition strings controlling *where* it applies (see below) — a template can have a plausible type and **no** conditions, meaning Theme Builder never actually assigns it anywhere |

**Create**: `wp_insert_post(['post_type' => 'elementor_library', 'post_status' => 'publish', ...])`, then `update_post_meta()` the three keys above. Set `_elementor_edit_mode` to `builder` (standard on any Elementor-built post) and `_elementor_version` to match the site's installed Elementor version.

**Read**: same as any other Elementor post — `get_post_meta($id, '_elementor_data', true)`, `json_decode()`.

**Apply**: setting `_elementor_conditions` is what actually activates it — see below. Multiple templates of the same `_elementor_template_type` can coexist (e.g. several `single` templates for different post types); Theme Builder's condition-matching + priority system (below) decides which one renders for a given request.

## Display Conditions: the complete type/name enumeration

A condition string has the shape **`{action}/{type}/{name}`** —
`action` is `include` or `exclude`; `type` is one of exactly three values;
`name` identifies the specific sub-condition. Verified directly from every
`Condition_Base` subclass Elementor Pro ships
(`elementor-pro/modules/theme-builder/conditions/*.php`):

### `type: general`
- `general` — matches everything (the site-wide fallback / lowest-priority catch-all)

### `type: singular` (individual content — posts, pages, CPT entries)
- `singular` — every singular post/page of any type
- `front_page` — the site's front page specifically
- `not_found404` — the 404 page
- `<post_type>` — a specific post type, e.g. `post`, `page`, or any custom post type's own name (verified: `Post::get_name()` returns `$this->post_type->name` directly — so a CPT named `team` produces the condition name `team`, matching `include/singular/team` observed in production)
- `by_author` — any singular content by a specific author
- `<post_type>_by_author` — a specific post type's content by a specific author
- `child_of` / `any_child_of` — direct child / any descendant of a specific parent page (hierarchical pages only)
- `in_<taxonomy_name>` — singular content assigned to a specific taxonomy (e.g. `in_category`, `in_product_cat`)
- `in_<taxonomy_name>_children` — content in any child term of a given term within that taxonomy

### `type: archive` (listing/archive pages)
- `archive` — every archive page of any kind
- `author` — a specific author's archive page
- `date` — date-based archives
- `search` — search results page
- `<post_type>_archive` — a specific post type's archive (verified:
  `Post_Type_Archive::get_name()` returns `$this->post_type->name . '_archive'`
  — matching `exclude/archive/team_archive` observed in production, for a
  `team` CPT's own archive)
- `<taxonomy_name>` — a specific taxonomy's term archives (e.g. `category`, `product_cat`)

**Practical implication**: to build `include/singular/<cpt-slug>` or
`exclude/archive/<cpt-slug>_archive` programmatically for any custom post
type, you don't need to guess the naming — it's always `{post_type_name}`
for singular and `{post_type_name}_archive` for that type's archive, taken
directly from the registered post type's own `name` property.

## Advanced Conditions: how conflicts actually resolve

When two Theme Builder templates could both match the same request (e.g. a
general `singular` template and a more specific `singular/team` template),
Elementor Pro resolves the conflict by **specificity, not registration
order**:

1. Every condition class has a base `get_priority()` (default `100`, from
   `Condition_Base`). More specific condition types override this with a
   lower number.
2. `Conditions_Manager::get_condition_priority()` further **subtracts** from
   that base priority for extra specificity — a sub-condition (e.g. a
   specific post type nested under `singular`) always wins over its parent,
   and stacking more specific qualifiers (author, taxonomy term) subtracts
   further still.
3. All matching templates for a given request get collected into a
   `[template_id => priority]` map, then `asort()`'d — **ascending**, so the
   **lowest priority number (the most specific match) sorts first** and is
   the one actually used.

**What this means in practice**: you don't need to manually manage
"which template wins" — assign the most specific condition the content
actually needs (`include/singular/team` rather than a broad
`include/singular`), and Theme Builder's own specificity resolution
guarantees it takes precedence over anything more general, without needing
an explicit `exclude` on the general template. Use `exclude/...` conditions
only when a *broader* template would otherwise also legitimately match and
you specifically don't want it to for this particular narrower case (the
production example: a general `archive` template with
`exclude/archive/team_archive`, because the `team` CPT has its own
dedicated archive template that should win there instead).

## Verifying `_elementor_conditions` is actually working

Two independent checks, since "the meta value is set" isn't the same as
"Theme Builder is honoring it":

1. Fetch the target page and check the rendered markup for
   `data-elementor-id="<template_id>"` on the relevant wrapper element (a
   header/footer/singular wrapper carries this attribute identifying which
   template actually rendered it) — confirmed reliable in production use.
2. If it's not the expected template, check whether a *more specific*
   competing template exists that's winning the priority resolution above
   — the fix is usually to make your intended template's condition more
   specific, or add an explicit `exclude` to the competing one, not to
   second-guess whether conditions "work."
