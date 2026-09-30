# Exercise: transfusion demand from MIMIC-style data

A SQL exercise on synthetic MIMIC-IV-shaped data made by
`generate_synthetic_mimic.py`. The data has deliberate recording problems;
finding them is part of the exercise. The generator also writes an answer key
to `synth/answer_key/`: open it only to grade a finished challenge.

## Setup

    uv run python generate_synthetic_mimic.py --out synth    # no --seed: hidden parameters
    cd synth && duckdb synth.duckdb < load_duckdb.sql        # already done for the current synth/
    duckdb synth/synth.duckdb                                # from the project root

Tables: `patients`, `admissions` (hosp), `icustays`, `d_items`, `inputevents` (icu).

## Challenge 1: build a product mapping table

**The goal.** Figure out which item IDs in the data represent the three blood products you care about: platelets, packed red blood cells, and plasma. Every later query filters on this table, so if it's wrong, everything downstream is wrong.

**Where to look.** `d_items` is the dictionary of every item that can be charted, with labels, categories, units, and which table each item's records live in. `inputevents` is where the actual transfusions are recorded.

**What to produce.** A small table, one row per item ID that belongs to one of the three products:

| Column | What goes in it |
|---|---|
| `itemid` | The item's ID |
| `product` | `platelets`, `rbc`, or `plasma` |
| `amountuom` | The unit its amounts are recorded in |
| `note` | One line on why you included it |

You can build it as a view from a query, or as a hand-written `VALUES` table if you decide membership by inspection. Either is fine, as long as the reasoning is in the note.

**What makes it tricky.** Some items look related but aren't transfusions, and a product may be spread over more than one item ID, possibly recorded in different units. Profiling `inputevents` by item alongside the dictionary will tell you more than the labels alone.

**How you'll know it's right.** The answer key's `bags.csv.gz` records the `itemid` and `product` for every true bag. Once you're done, compare your mapping with the distinct item-product pairs there. Your table should match exactly: no missing items, no extras.

**Grading note.** The answer key labels plasma `ffp`, not `plasma`. Compare
against the key's `platelets`, `rbc` and `ffp` pairs, treating `ffp` as `plasma`.

## Not yet written

These are referenced in the generator but not defined here yet:

- **Challenges 2-3:** bag counts per stay and product (graded against `bags.csv.gz`).
- **Phase 2:** fitting demand models (graded against `effective_targets.json`).
