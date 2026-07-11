# Where the token savings come from

The claim is **89% fewer tokens than reading Elementor's source**. Here is the
whole argument, and the script that reproduces it.

```bash
pip install tiktoken
python tools/benchmark-tokens.py --elementor-src /path/to/wp-content/plugins/elementor
```

Every number below is that script's output, and it writes
`data/token-benchmark.csv` so you can check it rather than take it on faith.

## The three ways to answer "what controls does this widget have?"

**A — read the source.** What an agent does with no skill installed. Accurate,
expensive, and it leaves you converting PHP control definitions into JSON value
shapes in your head.

**B — load the schema.** Put `data/elementor-schema.json` in context. Complete,
and completely impractical: **583,555 tokens**. It does not fit in most context
windows, and you pay for 100% of it to use 0.1% of it.

**C — query the schema.** Run `tools/el.py` and read back the answer.

## Measured, on five real tasks

| Task | A: read source | B: load schema | C: query | saving vs A |
|---|---|---|---|---|
| Lay out a hero container (flex, boxed, responsive padding) | 20,182 | 583,555 | **964** | 95.2% |
| Style a heading (colour, typography, alignment) | 8,329 | 583,555 | **730** | 91.2% |
| Style a button (colour, padding, radius, hover) | 7,803 | 583,555 | **2,935** | 62.4% |
| Make any widget's spacing responsive | 11,800 | 583,555 | **243** | 97.9% |
| Find which control drives a CSS property | — | 583,555 | **363** | — |
| **Total** | **48,114** | **583,555** | **5,235** | **89.1%** |

C vs B: **99.10% fewer** (583,555 → 5,235).

## The two things that make it work

### 1. The data is a database, not a document

Nothing in `data/` is ever loaded into context. `el.py` is the query, and the
answer is the only thing you pay for:

```
data/elementor-schema.json      2.7 MB    583,555 tokens   never read
data/controls.csv               2.0 MB    531,357 tokens   grep target
data/common-controls.csv         39 KB     11,149 tokens
data/widgets.csv                8.2 KB      2,732 tokens
data/control-types.csv          4.6 KB      1,317 tokens
data/group-controls.csv         3.7 KB        972 tokens
data/breakpoints.csv            0.2 KB         72 tokens
```

`el.py widget heading --tab style` returns ~700 tokens. Reading `heading.php`
plus `typography.php` costs 8,329 and still does not tell you that
`typography_font_size` takes `{"unit":"px","size":46,"sizes":[]}`.

### 2. The Advanced tab is stored once, not 135 times

Every widget inherits the same 211 Advanced-tab controls — margin, padding, motion
effects, transform, masking, custom CSS. Elementor registers them into each
widget's own stack, so a raw dump repeats them 135 times. Measured on 4.1.4 they
occupy **75.6% of all control rows** (28,018 of 37,054).

Storing them once shrinks the schema from 37,964 rows to 10,157 — **73.2%
smaller** — and it is *more* truthful, not less: "padding works the same on every
widget" is a fact about Elementor, not 135 coincidences.

The rule is mechanical, never hand-picked: a control joins the shared set only if
it is **byte-identical everywhere it appears** and appears in **≥90% of widgets**.
The three widgets that deviate (`common-base`, `e-component`, `global`) are listed
explicitly in `common_missing` rather than being forced into the pattern.

## Honesty about the measurement

- Token counts use **tiktoken `cl100k_base`** — OpenAI's tokenizer, not Claude's.
  Absolute counts will differ by roughly ±10% on Claude. The **ratios** are what
  the claim rests on, and a ratio between two texts measured with the same
  tokenizer is stable across tokenizers.
- **Baseline A counts the files that actually contain the answer**, including the
  ones inheritance hides. `button.php` is a 163-line shell —
  `class Widget_Button … use Button_Trait` — and every one of its controls lives
  in `button-trait.php`, a file **6× its size**. An agent that opens `button.php`
  finds no controls at all and has to chase the `use` statement. Pricing only
  `button.php` would have flattered this skill by charging the baseline for a file
  that does not answer the question. The trait is counted. (Before it was, the
  button task showed the skill *losing* by 67%. That result is what prompted the
  check.)
- **Baseline B is charged once**, not once per task, even though an agent working
  across several widgets in one session would pay it repeatedly. The generous
  reading is the one reported.
- The `el.py` outputs are captured by **running the tool**, not estimated.

## The savings that do not show up in the table

Baseline A does not actually answer the question. PHP source gives you control
names; it does not give you:

- the **JSON value shape** — the part that fails silently when you get it wrong
- whether a control is **Free or Pro** (Pro injects 46 controls into every free
  widget; you cannot see that in the free widget's source, because it is not there)
- which **CSS property** a control drives, without reading its `selectors` map
- whether a **responsive suffix** is legal — `padding_tablet` has no control
  object anywhere in the source to find

Every one of those is a silent failure: the page saves, renders for you, and is
wrong. The tokens saved are the smaller half of the argument.
