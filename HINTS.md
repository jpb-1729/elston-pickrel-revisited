# Hints

Read one hint at a time, and try again before reading the next. Within each
step, hints go from a gentle nudge to the shape of the SQL. None of them tells
you which items belong in your answer.

**Getting unstuck in general.** Break the question into a smaller one you can
answer with a single query. When a summary puzzles you, look at the raw rows
behind it: `select * from inputevents where itemid = <some id> limit 20;`.

---

## Challenge 1

### Step 1: read the dictionary

<details><summary>Hint 1</summary>

`d_items` is small. `select * from d_items;` shows all of it; you don't need a
filter yet.

</details>

<details><summary>Hint 2</summary>

`linksto` names the table where an item's records live. Which of the tables
listed there records things *given to* a patient? An item recorded somewhere
else can't be a transfusion, however its label reads.

</details>

<details><summary>Hint 3</summary>

`category` groups related items, but it isn't a membership list for your three
products. Treat it as a starting point, not the answer.

</details>

### Step 2: check against the data

<details><summary>Hint 1</summary>

Group `inputevents` by `itemid` and count the rows (pattern 5).

</details>

<details><summary>Hint 2</summary>

Join to `d_items` to put the label next to each count (pattern 7). The shape:

    select e.itemid, d.label, count(*) as n_rows
    from inputevents e
    join d_items d on d.itemid = e.itemid
    group by e.itemid, d.label
    order by n_rows desc;

</details>

<details><summary>Hint 3</summary>

The join in hint 2 only shows items that appear in `inputevents`. To also see
dictionary items with *no* records, start from `d_items` and use a
`left join`. The count for an item with no records is then 0, if you count a
column from `inputevents` (`count(e.itemid)`) rather than `count(*)`.

</details>

### Step 3: profile each candidate

<details><summary>Hint 1</summary>

Add `amountuom` to your step-2 query, in both the `select` and the
`group by`, plus `min(amount)`, `avg(amount)` and `max(amount)`.

</details>

<details><summary>Hint 2</summary>

Put `d.unitname` next to `e.amountuom`. Where they differ, ask: is it the same
unit spelled differently, or a genuinely different unit?

</details>

<details><summary>Hint 3</summary>

A bag of a blood product is typically a few hundred millilitres. If an item's
typical amount is nowhere near that, what is it counting instead? Look at raw
rows for that item.

</details>

### Step 4: decide

<details><summary>Hint 1</summary>

The three products are different parts of donated blood: red blood cells
carry oxygen, plasma is the liquid part (with clotting factors), and platelets
help blood clot. Other things come in bags or are made from blood without
being one of these three. The challenge asks only about the three.

</details>

<details><summary>Hint 2</summary>

One product can be collected or prepared in more than one way, and charted
under more than one item. For demand purposes, it's still the same product.

</details>

<details><summary>Hint 3</summary>

Look up any term in a label you don't know. For each item ask: is it the
product itself, something different made from blood, or a measurement or piece
of paperwork *about* the product?

</details>

### Step 5: build the table

<details><summary>Hint 1</summary>

Use pattern 9 with the columns `itemid, product, amountuom, note`, and name it
`product_map`. Open the database without `-readonly` so it's saved.

</details>

<details><summary>Hint 2</summary>

For `amountuom`, write down what `inputevents` actually records, not what
`d_items` says. Step 3 showed you whether those always agree.

</details>

### Step 6: check before grading

<details><summary>Hint 1</summary>

"Rows in A with no match in B" is a `left join` followed by
`where <B's column> is null`:

    select m.*
    from product_map m
    left join (select distinct itemid from inputevents) e on e.itemid = m.itemid
    where e.itemid is null;

No rows means every item in your table appears in the data. DuckDB also has a
shortcut for this: `anti join`.

</details>

<details><summary>Hint 2</summary>

Now the other direction: list the items in `inputevents` that are *not* in
`product_map`, with their labels. For each one, can you say why you left it
out?

</details>

---

## Challenge 2

**A rule for any query with `group by`:** every column in the `select` must
either be inside an aggregate (`count`, `min`, `max`, `sum`, ...) or be listed
in the `group by`. DuckDB's `group by all` lists them for you.

### Step 1: narrow down

<details><summary>Hint 1</summary>

Join `inputevents` to `product_map` on `itemid`; the join itself throws away
every other item. Then count per `product`.

</details>

<details><summary>Hint 2</summary>

    select m.product, count(*) as n_records
    from inputevents e
    join product_map m on m.itemid = e.itemid
    group by m.product;

</details>

### Step 2: statuses

<details><summary>Hint 1</summary>

Add `e.statusdescription` to your step-1 query, in the `select` and the
`group by`.

</details>

<details><summary>Hint 2</summary>

For each status, look at ten raw records: `where statusdescription = '...'`.
Compare `amount` with `totalamount`. Then pick one record and look at every
record with the same `linkorderid`.

</details>

<details><summary>Hint 3</summary>

What the statuses mean, in MIMIC's terms:

- **FinishedRunning:** the infusion ran to completion.
- **Stopped:** the infusion was stopped before the bag was empty.
- **Paused:** the infusion was paused; the rest of the bag shows up in a later record.
- **Rewritten:** a nurse corrected this record; the corrected version is a separate record.

Match each one to a rule under "What counts as a bag".

</details>

### Step 3: repeats

<details><summary>Hint 1</summary>

Pattern 10: compare `count(*)` with the count of `select distinct *`. If they
differ, some records are exact copies.

</details>

<details><summary>Hint 2</summary>

To see the copies themselves:

    select e.*, count(*) as copies
    from inputevents e
    group by all
    having count(*) > 1
    limit 10;

`having` filters groups, the way `where` filters rows.

</details>

<details><summary>Hint 3</summary>

`select distinct * from ...` inside a `with` step gives you the records with
the copies removed. Do it before you count or sum anything.

</details>

### Step 4: bag IDs

<details><summary>Hint 1</summary>

Reread the `linkorderid` row of the column table in the field guide.

</details>

<details><summary>Hint 2</summary>

Find IDs shared by several records with `group by ... having count(*) > 1`.
Then list every record for one of them, `order by starttime`, and read the
statuses and times in order.

</details>

<details><summary>Hint 3</summary>

All the records of one bag share a `linkorderid`. Once you've removed the
records that don't count, grouping by it gives one row per bag.

</details>

### Step 5: units

<details><summary>Hint 1</summary>

For that item, look at `min`, `max` and the distinct values of `amount`.
Do they look like millilitres?

</details>

<details><summary>Hint 2</summary>

They're the number of donor units pooled into the bag, not a number of bags.
One record of that item is still one bag. Its `amount` stays in `units`; don't
mix it with millilitres.

</details>

### Step 6: build `bags`

<details><summary>Hint 1</summary>

Step one of the `with` keeps only records that count: the right items, no
copies, nothing that was replaced. Step two groups those records by bag and
uses `min`, `max`, `count` and `sum` for the time and amount columns.

</details>

<details><summary>Hint 2</summary>

The shape, with the parts that matter left for you:

    create or replace view bags as
    with counted as (
        select ...
        from inputevents e
        join product_map m on m.itemid = e.itemid
        where ...
    )
    select
        ... as bag_id,
        stay_id, product, itemid,
        min(starttime) as starttime,
        max(endtime)   as endtime,
        count(*)       as n_records,
        sum(amount)    as amount,
        amountuom
    from counted
    group by all;

</details>

### Step 7: check before grading

<details><summary>Hint 1</summary>

    select count(*) as bags, count(distinct bag_id) as distinct_bags from bags;

The two numbers must be equal.

</details>

<details><summary>Hint 2</summary>

Count bags per `itemid` and `n_records`. How many records does a bag usually
take? Is any combination surprising?

</details>

### Reading the grading output

<details><summary>Hint</summary>

- **A missing and an extra bag in the same stay and item, a few minutes
  apart:** you have the bag, but with the wrong start time. You probably
  dropped its first record.
- **Missing bags with no extra bag nearby:** you dropped records that are
  real bags.
- **Extra bags with no missing bag nearby:** you counted records that aren't
  bags, or counted copies.

</details>
