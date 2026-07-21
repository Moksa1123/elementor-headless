# Project instructions for AI assistants

Read by Claude Code, Cursor and other agents when they open this repository. It
supplements `SKILL.md` (the user-facing contract) with conventions for editing the
skill itself.

## Identity

- Project: `elementor-headless`
- Maintainer: **moksa** ([moksaweb.com](https://moksaweb.com)) · MIT
- Purpose: build and modify Elementor pages entirely through `_elementor_data` —
  headless, no visual editor.
- **Not** a site health-check, plugin-audit or media-cleanup tool. That was tried
  once in this project's history and deliberately removed. Keep it out.
- Sibling: [rankmath-seo-wp](https://github.com/moksa1123/rankmath-seo-wp) — same
  multi-platform install architecture.

## Layout

```
SKILL.md                     the contract, auto-loaded by agents
README.md (+ zh-TW/ja/ko)    entry point
data/                        generated. NEVER hand-edit.
references/                  long-form docs
tools/                       extract -> build -> query -> validate -> apply -> verify
examples/demo-page.json      the published proof page
assets/diagrams/             architecture.svg
assets/templates/platforms/  per-platform install configs
```

## The rule this whole project exists to enforce

**Nothing about Elementor gets written from memory. It gets measured.**

Elementor does not validate `_elementor_data`. It stores whatever you give it and
renders what it understands. Every mistake is therefore silent, which means a
confident guess and a correct answer are indistinguishable until a human notices
the padding never applied. So: no claim about a control name, a value shape, an
option, a unit, or a Free/Pro boundary goes into this repo unless it came out of
an extraction or a verifier.

This is not a stylistic preference. This repo has shipped wrong data every single
time it reasoned instead of measuring:

- Border and Box Shadow were labelled **Pro** because they "feel" premium. They
  are core, free, and always have been.
- The schema was extracted through WP-CLI without disabling Elementor's frontend
  control optimisation, silently losing **46% of all controls**.
- Responsive controls were detected by looking for `_tablet` siblings in the
  control stack. The common mechanism does not create any, so `padding_tablet` —
  which works fine — was being rejected as an unknown control.
- 2,573 controls emit a wrapper **class** rather than CSS. They shipped unverified
  for the entire life of the CSS sweep, on the reasoning that "Elementor registered
  a `prefix_class`, so presumably it works". 1,894 of them emit no CSS at all, so
  the sweep could not see them even in principle.
- `apply-page.php` left Elementor's rendered-HTML cache in place, so a correct tree
  served the **previous page**. A 17,421-control sweep ran green with that bug live.
- The shared controls' tier was derived from membership in the free dump's common
  set instead of from presence, and the free dump was not normalised the way the
  main dump is — so `_margin` and 73 other unambiguously free controls shipped
  labelled **Pro**, and verify-schema PASSed, because "Pro claimed, actually free"
  is filed as safe-direction drift. Watch the drift count, not just the verdict.

All nine are written up in `references/extraction-traps.md`. Read it before touching
the extractor.

**The generalisable lesson, and the one that keeps being re-learned here: a verifier
only finds bugs in the channel it reads.** Green in one channel says nothing about
the others. Before adding a "verified" claim anywhere, ask what artefact it was read
out of, and what an identical bug in a different artefact would look like.

## Regenerating data/

`data/` is generated output. Do not hand-edit it. Two dumps are required, not one:

**Three dumps, and every other plugin switched off.** Not two, and not on a site with
its plugins running:

```bash
# build the skip-list: everything active EXCEPT the ones whose surface you want
ALL=$(wp plugin list --field=name --status=active)

wp --skip-plugins="<all but elementor>"                    eval-file tools/extract-elementor-schema.php core+pro > iso-core.json
wp --skip-plugins="<all but elementor,elementor-pro>"      eval-file tools/extract-elementor-schema.php core+pro > iso-pro.json
wp --skip-plugins="<all but elementor,elementor-pro,woocommerce>" eval-file tools/extract-elementor-schema.php core+pro > iso-woo.json

python tools/build-indexes.py iso-woo.json \
    --free-dump   iso-core.json \
    --gated-dump  woocommerce=iso-pro.json \
    --verification data/control-verification.csv \
    --class-verification data/class-verification.csv --out data/
python tools/verify-schema.py iso-woo.json --free-dump iso-core.json   # must exit 0
```

Each dump answers a different question:

| dump | plugins | answers |
|---|---|---|
| `iso-core` | elementor | what is FREE |
| `iso-pro` | + elementor-pro | what Pro adds — the per-control tier |
| `iso-woo` | + woocommerce | what WooCommerce adds — the `requires` |

`--skip-plugins` affects only that one CLI process, so all three are safe against a
production site. Without `--free-dump`, `build-indexes.py` marks every control
`tier: unknown` rather than guessing, and that is the correct behaviour: leave it
that way.

**Extracting on a site with its other plugins loaded pollutes the schema.** Rank Math
injects `rank_math_add_faq_schema` into `accordion`; Unlimited Elements injects
`uc_background_*` into the container. The schema shipped both, as if they were
Elementor's. Isolate the plugins or the data is about your site, not about Elementor.

**And extract from a site that has WooCommerce.** Without it, Elementor Pro's
`woocommerce` module does not load, its 29 widgets do not exist, and the schema will
confidently tell people Elementor has no `woocommerce-product-price`. Trap 10.

The two `--*-verification` files are what let the RENDERED result override
Elementor's own metadata (`responsive_broken`, `class_verified`, `renders_bare`).
Without them the schema falls back to what Elementor claims, which is wrong in at
least 9 + 29 known places.

`build-indexes.py` refuses a dump taken with control optimisation on. Do not
"fix" that by loosening the check.

### The ordering rule

**Anything measured PER WIDGET is stamped onto controls AFTER `compute_common()`,
never before.** A shared control stays in the common set only while it is
byte-identical across all participating widgets. Stamp a per-widget measurement on it first
and the set shatters — 210 shared controls became 192, and the schema grew half a
megabyte. This has now happened with `tier` and again with `class_verified`. It will
happen a third time to whoever ignores this paragraph.

`extract-elementor-schema.php` has **three canaries** that abort rather than emit
degraded data (control stack intact / `container.padding` responsive /
`icon-box.position` keeps its per-device prefix and its `classes_dictionary`). Do
not weaken them to make a build pass.

## Free vs Pro

Every architecture note, code sample and comment must state explicitly which
features, APIs and parameters are **Elementor Pro only**. Never let Free and Pro
blur together — that is the skill's headline promise.

Never infer a tier from how advanced a feature looks. The tier comes from the
Free-vs-Pro diff, full stop. Note the semantics: a *control's* tier answers
"assuming I can use this widget at all, does this control additionally need Pro?"
On a widget that is itself Pro that question is circular, so per-control tier there
carries no information and is not checked.

## wp eval-file takes positional args only

No `--` separator, no `--flag=value`. WP-CLI intercepts any `--foo=bar` token as
one of its own global parameters and errors out before your script runs.

```bash
wp eval-file tools/apply-page.php 123 page.json        # yes
wp eval-file tools/apply-page.php --post-id=123        # no - WP-CLI eats the flag
wp --skip-plugins=elementor-pro eval-file tools/…      # fine: a real WP-CLI global
```

## Local checks before committing

```bash
for f in tools/*.php; do php -l "$f"; done
python tools/el.py stats
python tools/validate-page.py examples/demo-page.json --target free   # must be clean
python tools/benchmark-tokens.py --elementor-src /path/to/plugins/elementor
```

Anything generated for the SERVER (`RUN.sh`, `render.php`) must be written with
`newline="\n"`. Python's `write_text()` on Windows emits CRLF, and bash reads
`set -u\r` as an invalid option.

Any change to the extractor must be run against a live WordPress + Elementor at
least once. `php -l` only proves it parses.

If you change `examples/demo-page.json`, re-verify it end to end — apply it, then
run **`verify-live.py` against the public URL**. It is the repo's proof that the data
is real; a demo that renders wrong is worse than no demo.

```bash
python tools/verify-live.py examples/demo-page.json https://<the-demo-page-url>/
```

(The demo page lives on the maintainer's site; its URL is deliberately not
published anywhere in this repo.)

Prefer `verify-live.py` over `verify-render.py` for the demo. `verify-render.py`
reads one CSS file you hand it off the disk, and a page's styling is spread across
several (the Kit's globals live in a different file from the page's own). The live
check reads what the page actually links, through the cache, which is the only
definition of "it works" a visitor would recognise.

## Sanitisation

This is published publicly and distilled from a real client's site. Never commit
real SSH hosts, IPs, usernames, key filenames, managed-WP paths, personal Windows
paths, client names, or template/post IDs presented as if universal. Use
placeholders: `user@your-wp-host.example.com`, `/path/to/wordpress`,
`<template_id>`.

`data/elementor-schema.json` is safe by construction: it is extracted from
Elementor's own *class definitions* (control names, types, defaults), never from a
site's content. Keep it that way — if the extractor ever starts capturing live
`settings` values, that changes.

The demo page URL was once the deliberate exception, published as the skill's
proof. That decision was reversed: the URL now appears nowhere in the repo —
`examples/demo-page.json` plus the verify-live output stand as the proof. Do not
reintroduce it.

## Adding a platform config

Verify the current convention independently — do not copy it from another skill or
from memory. 3 of 8 platforms drifted in six weeks the last time this was checked
(`references/multiplatform-install-verification.md`). Set `verifiedAsOf`, and write
a `verificationNote` if any doubt remains.

## Style

- English in code, comments and identifiers.
- Markdown: ATX headings, LF endings, no trailing whitespace.
- PHP: WordPress core conventions (tabs) — these run inside WP-CLI's bootstrap.
- Python: PEP 8, stdlib only. `tiktoken` is the single exception and it is needed
  only by `benchmark-tokens.py`.
- No emoji.
