#!/bin/bash
# sweep-frontend.sh - apply every sweep batch and capture WHAT THE PUBLIC GETS.
#
#   TOOLS=/path/to/tools SWEEP=/path/to/sweep POST=<id> URL=https://site/page/ \
#     bash sweep-frontend.sh
#
# The other runners read the compiled CSS off the server's disk and the HTML out of
# a PHP call. Neither is what a browser receives. Between them and the visitor sit
# the theme, the page cache, Varnish and the CDN - and a page can render perfectly
# in all of those checks and still be broken on the site.
#
# So this one goes through the front door for every single batch:
#
#   1. apply the batch          (writes the tree, rebuilds CSS, drops the HTML cache)
#   2. GET the public URL       with a per-batch query string, because a shared edge
#                               cache will otherwise hand back the PREVIOUS batch and
#                               every control in this one gets scored against the
#                               wrong page. Verified: `?ehsweep=N` -> X-Cache: MISS.
#   3. GET every stylesheet that page LINKS, and concatenate them. Not post-<id>.css
#      off the disk: a page's styling is split across several files (the Kit's
#      globals live in a different one), and the union of what it links is the only
#      complete answer.
#
# What comes out is scored by the ordinary checkers:
#   python tools/sweep-controls.py check <sweep> --css-dir <sweep>/css
#   python tools/sweep-classes.py  check <sweep> --html-dir <sweep>/html
set -u

: "${TOOLS:=tools}"
: "${SWEEP:=sweep}"
: "${POST:?POST=<post id> is required}"
: "${URL:?URL=<public url of that post> is required}"

mkdir -p "$SWEEP/css" "$SWEEP/html"
ok=0; fail=0; stale=0

for f in "$SWEEP"/batch-*.json; do
  b=$(basename "$f" .json)
  n=${b##*-}
  rm -f "$SWEEP/css/$b.css" "$SWEEP/html/$b.html"

  if ! wp eval-file "$TOOLS/apply-page.php" "$POST" "$f" > /dev/null 2>&1; then
    echo "APPLY FAILED: $b"; fail=$((fail+1)); continue
  fi

  # Cache-bust per batch. Without this the edge serves batch 0 to every batch and
  # the whole sweep silently scores itself against one page.
  page="$SWEEP/html/$b.html"
  hdr=$(curl -sS -D - -o "$page" "${URL}?ehsweep=${n}" 2>/dev/null | tr -d '\r')
  if [ ! -s "$page" ]; then
    echo "FETCH FAILED: $b"; fail=$((fail+1)); continue
  fi
  case "$hdr" in
    *"X-Cache: HIT"*|*"x-cache: HIT"*)
      echo "STALE: $b was served from the edge cache - NOT scored"
      rm -f "$page"; stale=$((stale+1)); continue ;;
  esac

  # Every Elementor stylesheet THIS PAGE links, in the order it links them.
  #
  # BOTH quote styles. WordPress prints `href='...'` with SINGLE quotes; a pattern
  # that only matches double quotes finds nothing, reports "no CSS linked" for every
  # batch, and looks exactly like Elementor failing to enqueue its stylesheet.
  : > "$SWEEP/css/$b.css"
  grep -oE "href=['\"][^'\"]*/uploads/elementor/css/[^'\"]*\.css[^'\"]*['\"]" "$page" \
    | sed -E "s/^href=['\"]//; s/['\"]$//" | sed 's/&#0*38;/\&/g' | sort -u \
    | while read -r u; do curl -sS "$u" >> "$SWEEP/css/$b.css" 2>/dev/null; echo >> "$SWEEP/css/$b.css"; done

  if [ ! -s "$SWEEP/css/$b.css" ]; then
    echo "NO CSS LINKED: $b"; fail=$((fail+1)); continue
  fi
  ok=$((ok+1))
done

echo "captured $ok, failed $fail, stale $stale"
echo "these are the bytes a browser received - not the server's copy of them"
