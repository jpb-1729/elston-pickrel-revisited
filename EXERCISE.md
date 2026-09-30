# Exercise: transfusion demand from MIMIC-style data

A SQL exercise on synthetic MIMIC-IV-shaped data made by
`generate_synthetic_mimic.py`. The data has deliberate recording problems;
finding them is part of the exercise. The generator also writes an answer key
to `synth/answer_key/`: open it only to grade a finished challenge.

**Don't read `generate_synthetic_mimic.py` while doing the exercise.** Its
code spells out the answers, just like the answer key.

Stuck? `HINTS.md` has hints for each step, from gentle nudges to the shape
of the SQL. It never gives the answer, but read it only when you need it.

## How to work

Open the database from the project root:

    duckdb -readonly synth/synth.duckdb

`-readonly` means you can't change the data by accident. It also lets you open
several sessions at once. A normal (read-write) session locks the file, and
while it's open no other session can open it.

Write your queries in files, not only at the prompt, so you keep them and can
commit them. For example, `sql/challenge1.sql`, run with either of:

    duckdb -readonly synth/synth.duckdb < sql/challenge1.sql     # from the shell
    .read sql/challenge1.sql                                      # inside duckdb

To make a table you've built (like the mapping table) stick around, open the
database without `-readonly` for that session.

## The database: a field guide

The first question to ask about any table is **what one row means**, its
*grain*. Most query mistakes come from getting that wrong.

| Table | One row is... | Key | Links to |
|---|---|---|---|
| `patients` | a person | `subject_id` | |
| `admissions` | one hospital admission of a patient | `hadm_id` | `patients` via `subject_id` |
| `icustays` | one ICU stay during an admission | `stay_id` | `admissions` via `hadm_id` |
| `d_items` | one kind of thing that can be recorded (a dictionary entry) | `itemid` | |
| `inputevents` | one charted record of something given to a patient in the ICU | `orderid` (meant to be one per row) | `icustays` via `stay_id`; `d_items` via `itemid` |

How they fit together:

    patients ─< admissions ─< icustays ─< inputevents >─ d_items
     (1 person has many admissions; 1 stay has many input records;
      1 dictionary entry describes many input records)

Things worth knowing:

- **`d_items` is a dictionary, not data.** It tells you what an `itemid` means:
  its `label`, its `category`, its `unitname`, and `linksto`, the table where
  records of that item live. `inputevents` rows hold only the number (`itemid`);
  join to `d_items` to see what it is.
- **This database has only five tables.** Real MIMIC-IV has many more
  (`chartevents`, `labevents`, ...). Records of items that link to those
  tables aren't here.
- **One record is not necessarily one unit of product.** A row is whatever a
  nurse charted: `starttime`, `endtime`, `amount`, `amountuom`,
  `statusdescription`. Keep that in mind when you start counting in later
  challenges.
- **Dates are shifted into the future** (2110s to 2190s), separately for each
  patient, to protect privacy. The day of the week and the time of day are
  real; the year isn't. Real MIMIC-IV does the same.
- **Column meanings** follow MIMIC-IV. When a column name puzzles you, look it
  up in the MIMIC-IV documentation at <https://mimic.mit.edu>.

## DuckDB and SQL starter kit

Commands inside `duckdb` (they start with a dot and need no semicolon):

| Command | Does |
|---|---|
| `.tables` | list tables |
| `.mode markdown` / `.mode box` | change how results are drawn |
| `.read file.sql` | run a file |
| `.exit` | quit |

SQL statements end with `;`. These all run on this database. None of them
answers a challenge; they show patterns you'll reuse.

**1. See the columns of a table.**

    describe icustays;

**2. Profile a whole table:** type, min, max, distinct values and nulls per column.

    summarize icustays;

**3. Look at some rows.**

    select * from icustays limit 5;

**4. Filter rows.**

    select * from admissions where admission_type = 'ELECTIVE' limit 5;

**5. Count per group.** This is the workhorse for getting to know data.

    select first_careunit, count(*) as stays
    from icustays
    group by first_careunit
    order by stays desc;

**6. Summarise numbers.**

    select round(min(los), 2) as shortest,
           round(avg(los), 2) as average,
           round(max(los), 2) as longest
    from icustays;

You can combine 5 and 6: group by one column and summarise another.

**7. Join two tables** on the column they share.

    select a.admission_type, count(*) as icu_stays
    from icustays s
    join admissions a on a.hadm_id = s.hadm_id
    group by a.admission_type
    order by icu_stays desc;

**8. Search text**, ignoring case (`%` means "anything").

    select itemid, label from d_items where label ilike '%nacl%';

**9. Save a result as a table**, including one you type in by hand.

    create or replace table my_table as
    select * from (values
        (111, 'example', 'why I included it'),
        (222, 'example', 'why I included it')
    ) as t(some_id, some_label, note);

Swap `table` for `view` to save the query instead of its result: a view
re-runs every time you use it.

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
When you're done, this query (run from the project root, in the session where
you built `product_map`) lists every difference. No rows means a perfect match.

    select 'missing' as problem, * from (
      select itemid, replace(product, 'ffp', 'plasma') as product
      from read_csv('synth/answer_key/bags.csv.gz') where product in ('platelets', 'rbc', 'ffp')
      except
      select itemid, product from product_map)
    union all
    select 'extra', * from (
      select itemid, product from product_map
      except
      select itemid, replace(product, 'ffp', 'plasma')
      from read_csv('synth/answer_key/bags.csv.gz') where product in ('platelets', 'rbc', 'ffp'))
    order by all;

### Working through it

Questions to answer in order. Each has hints in `HINTS.md`.

1. **Read the dictionary.** Look at every row of `d_items`. For each item, what
   is it, and where are its records (`linksto`)? Which items could possibly be
   a transfusion recorded in `inputevents`? *(patterns 3, 8)*
2. **Check against the data.** Which item IDs actually appear in `inputevents`,
   and how many rows does each have? Put the dictionary label next to each
   one. *(patterns 5, 7)*
3. **Profile each candidate.** For each item in `inputevents`: what units are
   its amounts in, and what do typical amounts look like? Does anything
   disagree with the dictionary, or look odd for a bag of blood? *(patterns 5, 6, 7)*
4. **Decide.** For each candidate, which product is it, if any? Write down one
   line of reasoning per item. It becomes your `note`.
5. **Build the table** as `product_map`, with the four columns above. *(pattern 9)*
6. **Check it before you grade.** Is every item in your table really in
   `inputevents`? Is every blood-product item in `inputevents` either in your
   table or deliberately left out, with a reason?

## Not yet written

These are referenced in the generator but not defined here yet:

- **Challenges 2-3:** bag counts per stay and product (graded against `bags.csv.gz`).
- **Phase 2:** fitting demand models (graded against `effective_targets.json`).
