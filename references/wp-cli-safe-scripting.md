# Safe WP-CLI Scripting Over SSH

## File-based execution beats inline one-liners

Multi-layer quoting (local shell → SSH → remote shell → PHP/Python string →
an embedded expression) breaks down fast — every additional layer of tooling
adds its own escaping rules, and human working memory runs out before the
shell's parser does. Symptoms that mean you've hit this wall: `unexpected EOF`
from a heredoc that "should" be fine, a local shell expanding a `$VARIABLE`
that was meant for the remote host, a Python string literal breaking on a
single quote nested inside a double-quoted f-string.

**Rule of thumb: past two layers of quoting, stop and write a file instead.**

```bash
# Write the script locally with a normal editor/tool (no quoting gymnastics)
# then:
cat local-script.php | ssh user@host "cat > /tmp/script.php"
ssh user@host "wp eval-file /tmp/script.php"
```

This applies to PHP (`wp eval-file`), Python, and shell scripts alike — any
time the content has its own quotes, backslashes, or `$` characters that would
otherwise need to survive multiple shells intact.

## Specific escaping traps

- **CSS in a Python/PHP string literal**: `content: ''` inside a single-quoted
  host-language string gets the closing `''` misparsed as the string's own
  terminator. Use `content: ""` (double quotes) for the CSS value, or switch
  the host string to double quotes and escape internally — don't leave a bare
  `''` sequence inside a single-quoted wrapper.
- **An expression containing its own single quote**, e.g. building a
  templating-language expression like `"'" + value + "'"`: wrap the *whole*
  thing in a double-quoted string and escape the inner double quotes
  (`"={{ \"'\" + value + \"'\" }}"`), rather than trying to single-quote it
  and back-slash-escape the apostrophes — the latter reads as a line
  continuation in some contexts and throws a confusing syntax error nowhere
  near the actual mistake.
- **`$` in a command destined for a remote host**: a local double-quoted
  shell string expands `$VAR` *before* it ever reaches SSH. If the variable
  is meant to be evaluated remotely, escape it (`\$VAR`) or avoid the
  ambiguity entirely by writing a file and running it with `wp eval-file` /
  `python script.py` instead of `ssh host "php -r '...$var...'"`.
- **PowerShell with `%` or embedded quotes**: use the `--%` stop-parsing token,
  or do the operation in a POSIX shell instead.

## `update_post_meta` / `update_option` need `wp_slash()`

When writing a re-encoded JSON blob (or any string containing quotes/backslashes)
back into post meta or an option via PHP, pass it through `wp_slash()` first.
WordPress's data layer expects incoming values pre-slashed the way `$_POST`
data naturally is; skipping this step can silently corrupt quotes/backslashes
in the stored value on some code paths.

## Windows-authored files need forced LF line endings

If any part of the pipeline runs on Windows (writing files locally before
uploading), default text-mode writes emit `\r\n`. This breaks WordPress
Gutenberg block-comment parsing and PHP heredocs alike. Force LF explicitly
when writing (`newline='\n'` in Python, or an editor/tool that defaults to LF)
rather than relying on the platform default.

## Verify before you trust a diff

- `curl` output can be gzip/br-compressed garbage if the request didn't ask
  for decompression (`--compressed` in curl, or an equivalent header) — mangled
  multi-byte (e.g. CJK) text in a locally-saved HTML file is almost always
  this, not a real site bug. Re-fetch with compression handled before
  concluding anything about the page's actual content.
- A "0 matches" from a grep/string search is only meaningful if you've first
  confirmed you're searching for the *real* signature — see
  `plugin-audit-methodology.md`.
