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

The `inputevents` columns you'll use most:

| Column | Meaning |
|---|---|
| `stay_id` | the ICU stay the record belongs to |
| `itemid` | what was given (look it up in `d_items`, or your `product_map`) |
| `starttime`, `endtime` | when this record's infusion started and ended |
| `amount`, `amountuom` | how much was given during this record, and in what unit |
| `totalamount` | the size of the whole bag or order |
| `statusdescription` | the state of the infusion when the record was charted |
| `orderid` | identifies the record |
| `linkorderid` | links records that belong to the same order over time; for the first record of an order it equals `orderid` |

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

**10. Distinct values and distinct rows.** `distinct` removes repeats.

    select count(*) as stays, count(distinct first_careunit) as units from icustays;
    select distinct admission_type from admissions;
    select count(*) from (select distinct * from icustays);   -- rows that differ in at least one column

**11. Build a query in steps** with `with` (a *common table expression*, or
CTE). Each step is a named query the next step can use, which is easier to
read and check than one big query.

    with elective as (
        select hadm_id from admissions where admission_type = 'ELECTIVE'
    ),
    elective_stays as (
        select s.* from icustays s join elective e on e.hadm_id = s.hadm_id
    )
    select first_careunit, count(*) as stays
    from elective_stays
    group by first_careunit;

Check each step on its own as you go: temporarily end the query with
`select * from elective limit 10;` instead.

## Challenge 1: build a product mapping table

**The goal.** Find **every** item ID in `inputevents` that records one of three blood products: platelets, packed red blood cells, or plasma. A product can be charted under more than one item ID, so expect more rows than products; you need all of them, not one per product. Save the result as a table or view named `product_map`.

Every later query filters `inputevents` through this table. A missing item means that product is undercounted everywhere downstream; an extra item means counting something that isn't one of the three.

**Where to look.** `d_items` is the dictionary of every item that can be charted, with labels, categories, units, and which table each item's records live in. `inputevents` is where the actual transfusions are recorded.

**What to produce.** A small table, one row per item ID that belongs to one of the three products:

| Column | What goes in it |
|---|---|
| `itemid` | The item's ID |
| `product` | Exactly `platelets`, `rbc`, or `plasma` |
| `amountuom` | The unit its amounts are recorded in, as `inputevents` records it |
| `note` | One line of data evidence for including it, e.g. what the label, `linksto` or units showed. No medical knowledge needed. |

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

## Challenge 2: turn records into bags

**The goal.** Build a view named `bags` with exactly **one row per physical bag** of platelets, red blood cells or plasma given in the ICU. `inputevents` has one row per *record*, and records are not bags: some bags are charted across several records, and some records shouldn't be counted at all. Every demand number later in the exercise is a count of rows in `bags`, so this is where counting goes right or wrong.

**What counts as a bag.** A bag is one unit of product that was hung and started for a patient.

- A bag counts **once**, however many records it was charted in.
- A bag counts even if it **wasn't finished**.
- A record that was **replaced by a corrected record** doesn't count; the correction does.
- **Two identical records** are one record charted twice; count it once.
- A bag counts once whatever **unit** its amount is recorded in.

**Where to look.** `inputevents`, and your `product_map` from Challenge 1. Choose items by joining to `product_map`; don't type the item IDs again.

**What to produce.** A view named `bags`, one row per bag:

| Column | What goes in it |
|---|---|
| `bag_id` | A value that is the same for every record of the same bag and different between bags. The data already has one. |
| `stay_id` | The ICU stay |
| `product` | `platelets`, `rbc` or `plasma`, from `product_map` |
| `itemid` | The item the bag was charted under |
| `starttime` | When the bag started: the earliest `starttime` among the records you counted for it |
| `endtime` | When it ended: the latest `endtime` among those records |
| `n_records` | How many records you counted for the bag |
| `amount` | The total amount given from the bag: the sum of `amount` over those records |
| `amountuom` | The unit of `amount` |

**What makes it tricky.** Several different recording habits sit between records and bags, and each matches one of the rules above. You'll find each by profiling a column, not by reading labels. Dropping records you should keep is as wrong as keeping records you should drop. `HINTS.md` names the habits one at a time if you get stuck.

**How you'll know it's right.** The answer key's `bags.csv.gz` has one row per true bag, with its `stay_id`, `itemid`, `product` and `shifted_start`, which is the bag's start time as it appears in your data. Run these from the project root, in the session where `bags` exists. Like Challenge 1, they rename the key's `ffp` to `plasma` and skip the key's bags of other products.

Bags per product. Your counts should equal the key's:

    with key as (
        select replace(product, 'ffp', 'plasma') as product
        from read_csv('synth/answer_key/bags.csv.gz')
        where product in ('platelets', 'rbc', 'ffp')
    )
    select k.product, k.key_bags, m.your_bags
    from (select product, count(*) as key_bags from key group by product) k
    left join (select product, count(*) as your_bags from bags group by product) m
        on m.product = k.product
    order by k.product;

Bag by bag. Matches each of your bags to a true bag by stay, item and start
time, and lists the first 50 that don't match. No rows means every bag is right:

    with key as (
        select stay_id, itemid, shifted_start as starttime
        from read_csv('synth/answer_key/bags.csv.gz')
        where product in ('platelets', 'rbc', 'ffp')
    ),
    mine as (
        select stay_id, itemid, starttime from bags
    )
    select 'missing' as problem, * from (select * from key except all select * from mine)
    union all
    select 'extra', * from (select * from mine except all select * from key)
    order by stay_id, starttime
    limit 50;

A *missing* bag is in the key but not in your view: you dropped records you
needed, or gave a bag the wrong start time. An *extra* bag is in your view but
not in the key: you counted something that isn't a bag, or counted a bag twice.

Records and amounts. For bags that match, checks `n_records` and `amount`
against the true records of each bag (amounts rounded to 1 decimal). This
catches records counted that shouldn't be, even when the bag count is right.
No rows means every matched bag is right:

    with key_records as (
        select k.bag_id, e.orderid, any_value(e.amount) as amount
        from read_csv('synth/answer_key/row_key.csv.gz') k
        join inputevents e on e.orderid = k.orderid
        where k.is_valid
        group by k.bag_id, e.orderid
    ),
    key_bags as (
        select b.stay_id, b.itemid, b.shifted_start as starttime,
               count(*) as n_records, round(sum(r.amount), 1) as amount
        from key_records r
        join read_csv('synth/answer_key/bags.csv.gz') b on b.bag_id = r.bag_id
        where b.product in ('platelets', 'rbc', 'ffp')
        group by all
    )
    select k.stay_id, k.itemid, k.starttime,
           k.n_records as key_records, m.n_records as your_records,
           k.amount as key_amount, round(m.amount, 1) as your_amount
    from key_bags k
    join bags m
        on m.stay_id = k.stay_id and m.itemid = k.itemid and m.starttime = k.starttime
    where k.n_records <> m.n_records or k.amount <> round(m.amount, 1)
    order by k.stay_id, k.starttime
    limit 50;

**You're done when all three pass:** the counts match *and* the last two
queries return no rows. Matching counts alone isn't enough: a view can have
the right number of bags with wrong start times or wrong amounts.

### Working through it

1. **Narrow down.** Keep only records of your three products by joining
   `inputevents` to `product_map`. How many records are there per product?
   *(patterns 5, 7)*
2. **Statuses.** What values does `statusdescription` take, and how many
   records have each? Look at a few raw records for each value. For each one,
   decide: is it a whole bag, part of a bag, or not a bag at all? *(patterns 3, 5)*
3. **Repeats.** Are some records exact copies of each other? How many?
   *(pattern 10)*
4. **Bag IDs.** Which column ties together the records of one bag? Find bags
   with more than one record and look at all their records side by side.
   *(patterns 3, 5)*
5. **Units.** For the item recorded in units, what does one record's `amount`
   count? Does that change how many bags one record is? *(pattern 6)*
6. **Build `bags`** in two steps with `with`: first the records you count,
   then one row per bag. *(patterns 5, 6, 11)*
7. **Check it before you grade.** Does any `bag_id` appear twice? Compare
   `count(*)` with `count(distinct bag_id)`. Does every bag's `n_records` and
   `amount` look sensible for its item?

## Not yet written

These are referenced in the generator but not defined here yet:

- **Challenge 3:** more counting graded against `bags.csv.gz`.
- **Phase 2:** fitting demand models (graded against `effective_targets.json`).
