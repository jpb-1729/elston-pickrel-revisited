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
