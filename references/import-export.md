# Import / export: reusing blocks across pages and across sites

Elementor has its own JSON interchange format — the one behind the editor's
**Export Template** and **Import Templates** buttons. This skill speaks it, so a
block you build headlessly on one site imports cleanly on another, through the UI
or through WP-CLI.

```bash
# take any Elementor page or template off this site
wp eval-file tools/export-template.php <post_id> > hero-block.json

# put it on another site: into the library...
wp --user=1 eval-file tools/import-template.php hero-block.json

# ...or straight onto a page
wp --user=1 eval-file tools/import-template.php hero-block.json <target_post_id>
```

The file that comes out is the same file the editor produces, and it imports
through the editor's own button. That compatibility is the point, so the format is
not invented here — `export-template.php` calls Elementor's document API and
assembles exactly what `Local::prepare_template_export()` assembles.

## The format

Verified against `includes/template-library/sources/local.php`:

```jsonc
{
  "content":       [ /* the element tree, same shape as _elementor_data */ ],
  "page_settings": { /* document settings */ },
  "version":       "0.4",        // \Elementor\DB::DB_VERSION - read it, don't hardcode
  "title":         "Hero block",
  "type":          "page"        // page | section | container | header | footer | single | archive | popup | ...
}
```

`type` decides which Theme Builder slot the template lands in on import. A normal
page exports as `page`; something already in the library keeps its declared type.

## Do not just copy `_elementor_data` between sites

This is the whole reason the tools exist, and the failure is silent.

`get_export_data()` runs every control through its `on_export()` hook.
`Control_Media::on_export()` **strips the attachment `id`** and keeps the `url`. On
the way back in, `on_import()` **re-downloads that url into the target site's media
library** and rewrites the id to the new attachment.

Copy `_elementor_data` verbatim to another site and the attachment ids survive —
pointing at ids that on the other site mean a **different image**, or nothing at
all. Nothing errors. The block imports, renders, and shows the wrong pictures.

The same applies to a hand-rolled importer that writes `_elementor_data` directly:
it skips `on_import()`, so the media never arrives. `import-template.php` hands the
file to Elementor's own `import_template()` for exactly this reason, then (with a
target post id) copies the **post-import** tree — the one with remapped ids — onto
the page.

## Element ids are regenerated, on purpose

```
authored : 1a2b3c4  2b3c4d5  3c4d5e6  4d5e6f7
exported : 64fdc668 7a9ad78c dd8bc0b  222ea882
imported : 7f3e5013 6327135e 15daf9dd 2f409409
```

Both export and import mint fresh ids. This is correct and you want it: ids must be
unique across a tree, and importing the same block twice onto one page would
otherwise duplicate them and break the editor in ways that look like data
corruption.

It also means **an exported block is not diffable against its source by id.** Diff
it by structure and settings.

## Import needs a user

```bash
wp eval-file tools/import-template.php block.json
# Import failed: 拒絕存取。  (access denied)
```

Elementor's importer runs a capability check, and WP-CLI has no current user by
default. Pass one:

```bash
wp --user=1 eval-file tools/import-template.php block.json
```

`--user` is a real WP-CLI global parameter, so it is allowed alongside `eval-file`'s
positional args. (Your *script's* own arguments still cannot be `--flags` — WP-CLI
would eat them.)

## What survives a round trip

Measured, by exporting the demo page, importing it back, and comparing every
setting against the original:

```
settings authored     82
  lost in round trip   0
  changed              0
keys Elementor added  43   (empty media/gallery placeholders it materialises)
```

Nothing authored is lost or altered. Elementor fills in empty `{"url":"","id":"","size":""}`
objects for media controls that were never set — harmless, and worth knowing so you
do not mistake them for a diff.

## Practical uses

- **Reuse a block across pages.** Export once, import onto each target post id.
- **Ship a design system.** Keep a folder of `*.json` blocks in the repo, import
  them onto a fresh site to bootstrap it.
- **Move a page between staging and production.** Export, import, done — media
  travels with it.
- **Hand a block to a non-technical colleague.** They import it through the editor's
  own Import Templates button; they never need WP-CLI.
