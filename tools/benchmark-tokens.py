#!/usr/bin/env python3
"""
benchmark-tokens.py — measure what this skill actually costs, and what it saves.

Run it yourself; every number in the README comes from this script:

    pip install tiktoken
    python tools/benchmark-tokens.py --elementor-src /path/to/plugins/elementor

Without --elementor-src the source-reading baseline is skipped and the rest
still runs.

WHAT IS BEING COMPARED
An agent that has to write Elementor JSON needs to know, for the widgets it is
touching: the control names, their value shapes, their defaults, their allowed
options, and which settings each control depends on. There are three ways to
get that, and this script prices all three on the same tasks:

  A. READ THE SOURCE  - open Elementor's PHP and read _register_controls().
     This is what an agent does today with no skill installed. It is accurate
     but expensive, and it still leaves the agent converting PHP control
     definitions into JSON value shapes in its head.

  B. LOAD THE SCHEMA  - put data/elementor-schema.json in context. Complete,
     and completely impractical: it does not fit in most context windows, and
     you pay for 100% of it to use 0.1% of it.

  C. QUERY THE SCHEMA - run tools/el.py and read back only the answer.
     This is what the skill does.

HONESTY NOTES
  - Token counts use tiktoken cl100k_base. That is OpenAI's tokenizer, not
    Claude's, so absolute counts will differ by roughly +-10% on Claude. The
    RATIOS are what matter here, and a ratio between two texts measured with
    the same tokenizer is stable across tokenizers.
  - Baseline A counts exactly the files that contain the control definitions a
    task needs - the widget/element file plus any trait or group-control class
    whose fields the task touches. Elementor spreads control definitions across
    inheritance: `button.php` is a 163-line shell whose controls all live in
    `button-trait.php`, a file 6x its size. Pricing only `button.php` would
    flatter the skill by charging the baseline for a file that does not
    actually answer the question, so the trait is counted.
  - The el.py outputs measured are the exact commands an agent runs, captured
    by invoking the tool for real, not estimated.
  - Baseline B is charged once, not once per task, even though an agent working
    across several widgets in one session would in practice pay it repeatedly.
    The generous reading is the one reported.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import subprocess
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

try:
    import tiktoken
except ImportError:
    sys.exit("pip install tiktoken")

ENC = tiktoken.get_encoding("cl100k_base")


def tok(text: str) -> int:
    return len(ENC.encode(text))


QUERY_MS: list[float] = []


def run_el(args: list[str]) -> str:
    """Invoke el.py exactly as an agent would, capture what it prints - and time it.

    The latency recorded is the REAL tool-side cost (process spawn + schema load +
    query), measured, not estimated. It is the only wall-clock number here that can
    be measured honestly; the rest of "how long does an agent take" is model
    ingest, which is derived from tokens at a disclosed rate below.
    """
    t0 = time.perf_counter()
    out = subprocess.run(
        [sys.executable, str(HERE / "el.py"), *args],
        capture_output=True, text=True, encoding="utf-8",
    )
    QUERY_MS.append((time.perf_counter() - t0) * 1000)
    if out.returncode != 0:
        raise RuntimeError(f"el.py {' '.join(args)} failed: {out.stderr}")
    return out.stdout


# The tasks are real ones: each is something you actually have to do to build a
# page, and each names the el.py commands that answer it.
TASKS = [
    {
        "task": "Lay out a hero container (flex, boxed, responsive padding)",
        "cmds": [["container", "--tab", "layout"], ["type", "dimensions"]],
        # The container's layout controls come from container.php plus the two
        # group-control classes it composes in; you cannot learn the flex field
        # names from container.php alone.
        "src": [
            "includes/elements/container.php",
            "includes/controls/groups/flex-container.php",
            "includes/controls/groups/grid-container.php",
        ],
    },
    {
        "task": "Style a heading (colour, typography, alignment)",
        "cmds": [["widget", "heading", "--tab", "style"], ["group", "typography"]],
        "src": [
            "includes/widgets/heading.php",
            "includes/controls/groups/typography.php",
        ],
    },
    {
        "task": "Style a button (colour, padding, border radius, hover)",
        "cmds": [["widget", "button", "--tab", "style"], ["type", "dimensions"]],
        # button.php is a 163-line shell: `class Widget_Button ... use Button_Trait`.
        # Every control it has is defined in the trait. An agent that opens
        # button.php alone finds no controls at all and has to chase the `use`
        # statement to a second file 6x the size. Counting only button.php would
        # flatter this baseline by pricing a file that does not answer the
        # question.
        "src": [
            "includes/widgets/button.php",
            "includes/widgets/traits/button-trait.php",
            "includes/controls/groups/border.php",
        ],
    },
    {
        "task": "Make any widget's spacing responsive",
        "cmds": [["breakpoints"], ["common", "--grep", "padding"]],
        # padding/margin are registered on every widget by the base class.
        "src": ["includes/base/element-base.php"],
    },
    {
        "task": "Find which control drives a given CSS property",
        "cmds": [["css", "border-radius"]],
        # No single file answers this. You would grep the whole plugin and read
        # every hit. Priced as 0 rather than guess a number in the skill's favour.
        "src": [],
    },
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--elementor-src", type=Path,
                    help="path to wp-content/plugins/elementor (enables the source baseline)")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "token-benchmark.csv")
    a = ap.parse_args()

    schema = json.loads((ROOT / "data" / "elementor-schema.json").read_text(encoding="utf-8"))
    schema_raw = (ROOT / "data" / "elementor-schema.json").read_text(encoding="utf-8")
    schema_tokens = tok(schema_raw)

    print("SHIPPED DATA FILES")
    print("=" * 78)
    total_data = 0
    for p in sorted((ROOT / "data").glob("*")):
        t = tok(p.read_text(encoding="utf-8"))
        total_data += t
        print(f"  {p.name:28} {p.stat().st_size / 1024:9.1f} KB   {t:>9,} tokens")
    print(f"  {'TOTAL':28} {'':9}      {total_data:>9,} tokens")
    print()
    print("  None of this is ever loaded into context. It is queried. That is the whole")
    print("  design: the schema is a database, el.py is the query, the answer is the cost.")
    print()

    rows = []
    print("PER-TASK COST")
    print("=" * 78)
    print(f"  {'task':<48} {'A:src':>8} {'B:schema':>9} {'C:query':>8}  {'saving':>7}")
    print("  " + "-" * 76)

    for t in TASKS:
        # C — what the skill actually costs.
        query_tokens = sum(tok(run_el(c)) for c in t["cmds"])

        # B — load the whole schema.
        b = schema_tokens

        # A — read the PHP source.
        src_tokens = 0
        if a.elementor_src:
            for rel in t["src"]:
                f = a.elementor_src / rel
                if f.exists():
                    src_tokens += tok(f.read_text(encoding="utf-8", errors="replace"))

        saving = (1 - query_tokens / src_tokens) * 100 if src_tokens else float("nan")
        print(f"  {t['task']:<48} {src_tokens:>8,} {b:>9,} {query_tokens:>8,}  "
              f"{saving:>6.1f}%" if src_tokens else
              f"  {t['task']:<48} {'-':>8} {b:>9,} {query_tokens:>8,}  {'-':>7}")

        rows.append({
            "task": t["task"],
            "commands": " ; ".join("el.py " + " ".join(c) for c in t["cmds"]),
            "tokens_read_source": src_tokens or "",
            "tokens_load_schema": b,
            "tokens_query": query_tokens,
            "saving_vs_source_pct": f"{saving:.1f}" if src_tokens else "",
            "saving_vs_schema_pct": f"{(1 - query_tokens / b) * 100:.2f}",
        })

    print()
    tot_src = sum(r["tokens_read_source"] for r in rows if r["tokens_read_source"])
    tot_q = sum(r["tokens_query"] for r in rows)
    print("TOTALS ACROSS THE 5 TASKS")
    print("=" * 78)
    if tot_src:
        print(f"  A. read Elementor's PHP source   {tot_src:>9,} tokens")
    print(f"  B. load the whole schema         {schema_tokens:>9,} tokens  (x5 if re-read per task)")
    print(f"  C. query it with el.py           {tot_q:>9,} tokens")
    if tot_src:
        print()
        print(f"  C vs A: {(1 - tot_q / tot_src) * 100:.1f}% fewer tokens "
              f"({tot_src:,} -> {tot_q:,})")
    print(f"  C vs B: {(1 - tot_q / schema_tokens) * 100:.2f}% fewer tokens "
          f"({schema_tokens:,} -> {tot_q:,})")
    print()
    print("  And baseline A does not even answer the question fully: PHP source gives")
    print("  you control names but not the JSON value shape you have to write, which is")
    print("  the part that silently fails when you get it wrong.")

    # ---- TIME ---------------------------------------------------------------
    # Two different clocks, kept separate because only one of them is measured:
    #
    #   TOOL LATENCY (measured)  - the wall-clock of every el.py invocation made
    #     above, process spawn + 4.5MB schema load + query, on this machine.
    #
    #   MODEL INGEST (derived)   - an agent does not "read" tokens for free; the
    #     model has to process them. There is no portable measured number for
    #     that, so it is DERIVED from the token counts at a disclosed reference
    #     rate and clearly labelled an estimate. Change the rate; the ratio
    #     does not move, and the ratio is the claim.
    RATE = 1000.0   # tokens/second ingest, reference rate - disclosed, adjustable
    print()
    print("TIME")
    print("=" * 78)
    if QUERY_MS:
        import statistics
        print(f"  el.py tool latency (MEASURED, n={len(QUERY_MS)}): "
              f"median {statistics.median(QUERY_MS):.0f} ms, "
              f"max {max(QUERY_MS):.0f} ms per query")
    if tot_src:
        t_a = tot_src / RATE
        t_c = tot_q / RATE + sum(QUERY_MS) / 1000
        print(f"  model ingest at {RATE:.0f} tok/s (DERIVED estimate):")
        print(f"    A. read the source   ~{t_a:7.1f} s  for the 5 tasks")
        print(f"    B. load the schema   ~{schema_tokens / RATE:7.1f} s  once")
        print(f"    C. query             ~{t_c:7.1f} s  including measured tool latency")
        print(f"    C vs A: ~{t_a / t_c:.0f}x faster on ingest alone; the unpriced part")
        print(f"    of A is larger still - converting PHP control registrations into")
        print(f"    JSON value shapes in-head, which is where the silent mistakes live.")

    with a.out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print()
    print(f"  written: {a.out.relative_to(ROOT)}")
    print(f"  tokenizer: tiktoken cl100k_base (proxy for Claude's; ratios hold)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
