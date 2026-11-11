-- Challenge 3: bags per stay
--
-- Worksheet. Fill in each section in order. Answer each question in a comment
-- before moving on; the answers decide what goes into the final views.
-- Run the whole file:  .read sql/challenge3.sql
-- Run one query:       paste it at the duckdb prompt
--
-- The line below loads the views from sql/views.sql, including stay_bags and
-- bag_distribution from this challenge.
-- Creating views needs a session opened without -readonly.
.read sql/views.sql


-- Step 1: count what's there ------------------------------------------------
-- From bags, count bags for each stay and product (pattern 5).

-- Q: How many stays received at least one platelet bag?
-- A: 3705

.print ''
.print '=== Step 1: count what is there ==='
.print '-- First 10 rows: bags per (stay, product)'
-- Look at the first 10 rows: bags per (stay, product), one row per pair.
select
    b.stay_id,
    b.product,
    count(b.bag_id) as num_bags
from bags as b
group by b.stay_id, b.product
limit 10;

.print '-- Stays with at least one platelet bag'
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
-- Count the ICU stays. Then build every stay paired with every product:
-- three rows per stay (patterns 9, 12).

-- Q: How many ICU stays are there? How many rows does the full list have?
-- A: 61165 icu stays, 183495 rows in the full list.

.print ''
.print '=== Step 2: the full list ==='
.print '-- Number of ICU stays'
-- how many distinct ICU stays?
select count(distinct i.stay_id) as num_stays
from icustays as i;

.print '-- Saving stay_products (prints nothing on success)'
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

.print '-- stay_products: total rows, distinct stays, distinct products'
-- look at the table
select
    count(*),
    count(distinct s.stay_id),
    count(distinct s.product)
from stay_products as s;


-- Step 3: fill in the zeros --------------------------------------------------
-- Attach your counts from step 1 to the full list from step 2, so stays with
-- no bags show 0, never null (pattern 12).

-- Q: How many rows have n_bags = 0? Does step 1's count plus this add up?
-- A: 161264, which adds up to step 1 count when adding nonzero rows.

-- WITH stays AS (
--     SELECT DISTINCT
--         i.stay_id
--     FROM icustays as i
-- ),
-- product_types as (
--     SELECT DISTINCT product from product_map
-- ),
-- bag_counts as (
--     SELECT
--         b.stay_id,
--         b.product,
--         COUNT(b.bag_id) as n_bags
--     FROM bags as b
--     GROUP BY b.stay_id, b.product
-- )
-- SELECT
--     s.stay_id,
--     p.product,
--     COALESCE(b.n_bags, 0) as n_bags
-- FROM stays as s
-- CROSS JOIN product_types as p
-- LEFT JOIN bag_counts as b
--     ON b.stay_id = s.stay_id
--     AND b.product = p.product;

-- above approach matches pattern 12 closely but does not use stay_products. hard to read.

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
-- Add first_bag_start: the starttime of the stay's first bag of that
-- product, and null when there are no bags (patterns 6, 12).
--
-- Develop it as a plain SELECT, and only once step 5 passes wrap it in
-- `create or replace view stay_bags as ...`.
-- Columns: stay_id, product, n_bags, first_bag_start

-- Q: For a stay with n_bags = 0, what is first_bag_start? With n_bags > 0?
-- A: with n_bags=0 first_bag_start in NULL, and with n_bags>0 its the MIN(starttime)
-- The stay_bags view now lives in sql/views.sql.

-- Step 5: check the shape -----------------------------------------------------
-- Run the "Shape" grading query from EXERCISE.md. rows must equal
-- expected_rows; duplicate_rows and null_counts must be 0.

-- Result: it's correct.


-- Step 6: summarise -----------------------------------------------------------
-- From stay_bags, count stays for each product and n_bags, then add share:
-- n_stays as a fraction of all ICU stays, rounded to 4 decimals
-- (patterns 5, 13).
--
-- Wrap it in `create or replace view bag_distribution as ...` once step 7
-- passes.
-- Columns: product, n_bags, n_stays, share

-- The bag_distribution view now lives in sql/views.sql.


-- Step 7: check the shares ----------------------------------------------------
-- For each product, add up share (and n_stays) (pattern 5).

-- Q: Does share add to 1 for each product? Does n_stays add to the number of
--    ICU stays from step 2?
-- A:


-- Step 8: answer the questions -----------------------------------------------
-- Answer each with a query on stay_bags or bag_distribution, not by eye.
-- Put the query under its question and the answer in the comment.

-- Q1: What share of ICU stays received no platelets? No red cells? No plasma?
-- A:

select
    b.product,
    b.n_stays,
    b.share
from bag_distribution as b
where b.n_bags == 0;

-- Q2: Of the stays that received platelets, what share received exactly one
--     bag?
-- A:

select b.n_stays
from bag_distribution as b
where b.product = 'platelets' and b.n_bags = 1;

-- above is n_stays for 1 bag
select sum(b.n_stays)
from bag_distribution as b
where b.product = 'platelets' and b.n_bags > 0;

-- use filters since AND logic in first select makes WHERE inapplicable

select
    sum(b.n_stays) filter (where b.n_bags = 1) as numerator,
    sum(b.n_stays) filter (where b.n_bags > 0) as denominator,
    sum(b.n_stays) filter (where b.n_bags = 1)
    / sum(b.n_stays) filter (where b.n_bags > 0)
from bag_distribution as b
where b.product = 'platelets';

-- Q3: What is the most platelet bags any single stay received, and how many
--     stays received 10 or more?
-- A:

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
-- A:

select
    b.product,
    sum(b.n_stays) filter (where b.n_bags >= 5) as stays
from bag_distribution as b
group by b.product;
