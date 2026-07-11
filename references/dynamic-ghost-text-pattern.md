# Pattern: Static Decorative Text → Dynamic Per-Post Shortcode

A common editorial-design technique is a large, low-opacity "ghost" background
label — decorative oversized type with an animated light-sweep effect, used
as a section label ("WHO / WE ARE", a case-study client's name split across
two lines, etc.). It's usually implemented as inline SVG (not a plain text
heading), because the effect needs a `clipPath`-masked shine animation:

```html
<svg width="W" height="H" viewBox="0 0 W H" aria-hidden="true">
  <defs>
    <linearGradient id="gs" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0"    stop-color="rgba(255,255,255,0)"/>
      <stop offset="0.38" stop-color="rgba(255,255,255,0.16)"/>
      <stop offset="0.5"  stop-color="rgba(255,255,255,0.85)"/>
      <stop offset="0.62" stop-color="rgba(255,255,255,0.16)"/>
      <stop offset="1"    stop-color="rgba(255,255,255,0)"/>
    </linearGradient>
    <clipPath id="gc"><text x="4" y="Y" font-family="'Space Grotesk',sans-serif"
      font-size="SIZE" font-weight="700" letter-spacing="3">TEXT</text></clipPath>
  </defs>
  <text x="4" y="Y" font-family="'Space Grotesk',sans-serif" font-size="SIZE"
    font-weight="700" letter-spacing="3" fill="none"
    stroke="rgba(255,255,255,0.25)" stroke-width="1.2"
    vector-effect="non-scaling-stroke">TEXT</text>
  <g clip-path="url(#gc)">
    <rect class="shine1" y="-14" width="W1" height="RECT_H" fill="url(#gs)"
      transform="translate(START1,0) skewX(-18)"/>
    <rect class="shine2" y="-14" width="W2" height="RECT_H" fill="url(#gs)"
      transform="translate(START2,0) skewX(-18)"/>
  </g>
</svg>
<style>
  .shine1{animation:k1 6s linear infinite;will-change:transform;}
  .shine2{animation:k2 6s linear infinite;animation-delay:.45s;will-change:transform;}
  @keyframes k1{0%{transform:translateX(START1px) skewX(-18deg);}
                100%{transform:translateX(END1px) skewX(-18deg);}}
  @keyframes k2{0%{transform:translateX(START2px) skewX(-18deg);}
                100%{transform:translateX(END2px) skewX(-18deg);}}
</style>
```

The visible outline text is stroked-only (`fill="none"`), and a `clipPath`
built from the *same* text masks two skewed, gradient-filled rectangles that
translate across it on a loop — producing a metallic light-sweep confined to
the glyph shapes. It's CSS-transform-only (no layout thrashing), so it's cheap
to animate continuously.

## The trap: baking it as static markup into a shared template

If this lives inside a normal page's content, hardcoding the text is fine —
that page only ever shows one thing. If it lives inside a **shared Theme
Builder template** (a template that renders for every post of a type — see
`elementor-safe-edit.md`), a hardcoded `<text>TEXT</text>` renders identically
for every post that uses the template. There is no way to make one static
HTML/SVG widget say something different depending on which post is currently
being viewed.

## The fix: compute it dynamically per post

Convert the static widget into an Elementor `shortcode` widget calling a PHP
function that derives the text (and every size-dependent number) from the
current post at render time:

```php
function example_ghost_text_sc( $atts ) {
    $a = shortcode_atts( [ 'size' => '64' ], $atts );
    $pid = get_the_ID();
    if ( ! $pid ) { return ''; }

    // Derive the label from post data — here, the title with any leading
    // CJK characters stripped, leaving just the Latin/English portion.
    $title = get_the_title( $pid );
    $text  = trim( preg_replace(
        '/^[\x{4e00}-\x{9fff}\x{3000}-\x{303f}\x{ff00}-\x{ffef}\s]+/u', '', $title
    ) );
    if ( $text === '' ) { $text = $title; }
    $text = strtoupper( $text );

    $size = (int) $a['size'];
    $len  = max( 1, mb_strlen( $text ) );

    // Proportions below were reverse-engineered from a real fixed-size
    // reference sample (measure your own font at one size, then divide
    // every dimension by that font-size to get a reusable ratio) —
    // re-derive them for your own font/weight/letter-spacing rather than
    // trusting these numbers blindly.
    $width  = (int) ceil( $len * $size * 0.719 ) + 8;
    $height = (int) ceil( $size * 1.031 );
    $y      = (int) ceil( $size * 0.771 );
    $rect_h = (int) ceil( $size * 1.333 );

    $shine_w1 = (int) round( $width * 0.34 );
    $shine_w2 = (int) round( $width * 0.097 );
    $start1   = -round( $width * 0.789 );
    $end1     = round( $width * 1.4 );
    $start2   = -round( $width * 0.695 );
    $end2     = round( $width * 1.2 );

    // Unique per-instance IDs so multiple copies on one page (e.g. an
    // archive loop) don't collide on gradient/clipPath/keyframe names.
    $uid = substr( md5( $text . '-' . $pid ), 0, 8 );

    // ... build the SVG string using $uid-suffixed ids, $width/$height/$y/
    // $rect_h and the shine start/end values, same shape as the template
    // above. Return the full <svg>...</svg><style>...</style> string.
}
add_shortcode( 'example_ghost_text', 'example_ghost_text_sc' );
```

Then in the Theme Builder template's JSON, replace the static `html` widget
with a `shortcode` widget:

```json
{
  "id": "<keep the original element id>",
  "elType": "widget",
  "widgetType": "shortcode",
  "settings": { "shortcode": "[example_ghost_text]" },
  "elements": [],
  "isInner": true
}
```

If the original static version used *two* separate widgets (e.g. one for
each visual line of a multi-line label), collapse them to **one** dynamic
widget outputting the derived text on a single line at a reduced font size —
a computed short label rarely needs the same two-line split a fixed generic
word did, and forcing a shorter, size-varying string through a fixed two-line
layout designed for one specific word is how you get inconsistent wrapping
across different entities.

## Deriving your own proportions

Don't guess the 0.719/0.34/0.789/etc. constants above — they're specific to
one font/weight/letter-spacing combination. To derive your own:

1. Take two known-good static examples at the *same* font-size with
   *different* text lengths (the more different, the better the fit).
2. For each: `width ≈ (measured_svg_width - fixed_margin) / character_count`.
   Average the per-character width across your samples — if it's consistent,
   you have your `per_char_ratio` relative to font-size.
3. Do the same ratio-extraction for `height/size`, `y/size`, and every
   shine-rectangle `width`/`start`/`end` relative to the overall computed
   `width` — every one of these should reduce to a single width-relative
   ratio if the two samples were generated by the same underlying formula.
4. Verify by plugging the ratios back into both original samples and
   confirming you reproduce their exact original numbers before trusting the
   formula on new text lengths.
