-- Challenge 3: bags per stay
--
-- stay_bags and bag_distribution live in sql/views.sql.
-- Creating tables needs a session opened without -readonly.
-- The Result comments record one synthetic run; other runs give different
-- numbers.
.read sql/views.sql


-- Step 1: count what's there ------------------------------------------------
-- Bags for each stay and product, and the number of stays that received at
-- least one platelet bag.
-- Result: 3705 stays received platelets.

-- Look at the first 10 rows: bags per (stay, product), one row per pair.
select
    b.stay_id,
    b.product,
    count(b.bag_id) as num_bags
from bags as b
group by b.stay_id, b.product
limit 10;

-- Same counts as a CTE, then count the platelet rows.
-- Only stays with at least one bag appear here; stays with none are missing.
with stays as (
    select
        b.stay_id,
        b.product,
        count(b.bag_id) as num_bags
    from bags as b
    group by b.stay_id, b.product
)

select count(*)
-- one row per stay, so this counts stays
from stays as s
where
    s.product = 'platelets'
    and s.num_bags >= 1;  -- always true here (no zero-bag rows); harmless


-- Step 2: the full list ------------------------------------------------------
-- Every ICU stay paired with every product: three rows per stay.
-- Result: 61165 ICU stays, 183495 rows in the full list.

-- how many distinct ICU stays?
select count(distinct i.stay_id) as num_stays
from icustays as i;

-- one row for every ICU stay, paired with every product
create or replace table stay_products as
with stays as (
    select distinct i.stay_id
    from icustays as i
),

product_types as (
    select distinct product from product_map
)

select
    s.stay_id,
    p.product
from stays as s
cross join product_types as p;

-- look at the table
select
    count(*),
    count(distinct s.stay_id),
    count(distinct s.product)
from stay_products as s;


-- Step 3: fill in the zeros --------------------------------------------------
-- Attach the counts from step 1 to the full list from step 2, so stays with
-- no bags show 0, never null.
-- Result: 161264 zero rows. The nonzero rows equal step 1's row count, and
-- the two add up to the full list.
with bag_counts as (
    select
        b.stay_id,
        b.product,
        count(b.bag_id) as n_bags
    from bags as b
    group by b.stay_id, b.product
),

filled as (
    select
        s.stay_id,
        s.product,
        coalesce(b.n_bags, 0) as n_bags
    from stay_products as s
    left join bag_counts as b
        on b.stay_id = s.stay_id
        and b.product = s.product
)

select
    count(*) as total_rows,
    count(*) filter (where f.n_bags = 0) as zero_rows,
    count(*) filter (where f.n_bags > 0) as nonzero_rows,
    count(*) filter (where f.n_bags is null) as null_rows,
    (select count(*) from bag_counts) as step1_rows
from filled as f;

-- Step 4: first bag -----------------------------------------------------------
-- The stay_bags view in sql/views.sql adds first_bag_start: the starttime of
-- the stay's first bag of that product, and null when n_bags = 0.
-- Columns: stay_id, product, n_bags, first_bag_start

-- Step 5: check the shape -----------------------------------------------------
-- One row per stay and product, no duplicates, and no null n_bags.
-- Result: 183495 rows as expected, 0 duplicates, 0 null n_bags.
select
    count(*) as n_rows,
    3 * (select count(distinct stay_id) from icustays) as expected_rows,
    count(*) - count(distinct s.stay_id || '|' || s.product) as duplicate_rows,
    count(*) filter (where s.n_bags is null) as null_n_bags
from stay_bags as s;


-- Step 6: summarise -----------------------------------------------------------
-- The bag_distribution view in sql/views.sql counts stays for each product
-- and n_bags, with share: n_stays as a fraction of all ICU stays, rounded to
-- 4 decimals.
-- Columns: product, n_bags, n_stays, share


-- Step 7: check the shares ----------------------------------------------------
-- Result: share adds to 1 for each product, within 0.0001 of rounding, and
-- n_stays adds to the 61165 ICU stays from step 2.
select
    b.product,
    sum(b.share) as total_share,
    sum(b.n_stays) as total_stays
from bag_distribution as b
group by b.product
order by b.product;

-- Step 8: questions -----------------------------------------------------------

-- Q1: What share of ICU stays received no platelets? No red cells? No plasma?
-- A: platelets 0.9394, red cells 0.8043, plasma 0.8928.

select
    b.product,
    b.n_stays,
    b.share
from bag_distribution as b
where b.n_bags = 0;

-- Q2: Of the stays that received platelets, what share received exactly one
--     bag?
-- A: 2177 of 3705, or 0.59. The numerator and denominator need different
--    conditions on n_bags, so each takes a filter instead of a shared WHERE.
select
    sum(b.n_stays) filter (where b.n_bags = 1) as numerator,
    sum(b.n_stays) filter (where b.n_bags > 0) as denominator,
    sum(b.n_stays) filter (where b.n_bags = 1)
    / sum(b.n_stays) filter (where b.n_bags > 0) as share_one_bag
from bag_distribution as b
where b.product = 'platelets';

-- Q3: What is the most platelet bags any single stay received, and how many
--     stays received 10 or more?
-- A: 33 bags; 44 stays received 10 or more.

select *
from bag_distribution as b
where b.product = 'platelets'
order by b.n_bags desc
limit 1;

select sum(b.n_stays)
from bag_distribution as b
where b.n_bags >= 10 and b.product = 'platelets';


-- Q4: Compare the three products: which one has the most stays with large
--     counts (5 or more bags)?
-- A: red cells, with 451 stays (platelets 261, plasma 177).

select
    b.product,
    sum(b.n_stays) filter (where b.n_bags >= 5) as stays
from bag_distribution as b
group by b.product;
