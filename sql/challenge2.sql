-- Challenge 2: turn records into bags
--
-- Worksheet. Fill in each section in order. Answer each question in a comment
-- before moving on; the answers decide what goes into the final view.
-- Run the whole file:  .read sql/challenge2.sql
-- Run one query:       paste it at the duckdb prompt
--
-- The line below loads product_map (and any other shared views) from
-- sql/views.sql. Once bags passes grading, move it into views.sql too.
-- Creating views needs a session opened without -readonly.
.read sql/views.sql


-- Step 1: narrow down ------------------------------------------------------
-- A "record" is one row of inputevents. Count the rows for each of your
-- three products: the result has three rows (platelets, rbc, plasma), each
-- with a count. inputevents has no product column, so join it to product_map
-- on itemid; the join also drops every item that isn't one of the three
-- (patterns 5, 7).

-- Q: How many records per product?
-- A:
-- SELECT
--     inputevents.*,
--     product_map.product
-- FROM inputevents
-- JOIN product_map
--     ON inputevents.itemid = product_map.itemid
-- this just appends column with product, not count

.print
.print -- 1. Records per product
SELECT
    product_map.product,
    COUNT(*) AS COUNT
FROM inputevents
JOIN product_map
    ON inputevents.itemid = product_map.itemid
GROUP BY product_map.product
LIMIT 5;

-- Claude's version: same result, with a descriptive column name, stable
-- row order, and short table aliases (e = inputevents, m = product_map).
.print
.print -- 1. Records per product (Claude version)
SELECT
    m.product,
    COUNT(*) AS n_records
FROM inputevents AS e
JOIN product_map AS m
    ON e.itemid = m.itemid
GROUP BY m.product
ORDER BY m.product;

-- Step 2: statuses -----------------------------------------------------------
-- Same as step 1, but count rows for each value of statusdescription
-- instead of each product. Then, for each status, look at ten whole rows
-- (select * ... where statusdescription = '...' limit 10) (patterns 3, 5).

-- Q: For each status: whole bag, part of a bag, or not a bag? Which rule says so?
-- A:
-- FinishedRunning: whole bag when orderid=linkorderid, part of a bag when orderid <> linkorderid
-- by rule bullet 1, this counts as a bag.
-- Paused: part of a bag. Every Paused bag also has a later FinishedRunning record
-- by rule bullet 1
-- Stopped: whole bag by rule bullet 2.
-- Rewritten: 2i shows just mistyped. by rule bullet 3 not a bag.


-- 2a. How many records does each status have? (blood products only)
-- Result: 4 statuses. FinishedRunning = 35316, Paused = 3467,
-- Rewritten = 1827, Stopped = 1936.
.print
.print -- 2a. Records per status
SELECT
    e.statusdescription,
    COUNT(*) AS n_records
FROM inputevents as e
JOIN product_map AS m
    ON e.itemid = m.itemid
GROUP BY e.statusdescription;

-- 2b. What do records of one status look like? Sample 10.
-- Set the WHERE to one status at a time, so the sample isn't a mix.
-- Columns to compare: amount vs totalamount (whole bag or part?),
-- orderid vs linkorderid (first note of its order, or a later one?).
.print
.print -- 2b. Sample records by status
SELECT
    e.statusdescription,
    e.stay_id,
    m.product,
    e.orderid,
    e.linkorderid,
    e.starttime,
    e.endtime,
    e.amount,
    e.totalamount
FROM inputevents as e
JOIN product_map AS m
    ON e.itemid = m.itemid
WHERE e.statusdescription in ('FinishedRunning', 'Stopped', 'Rewritten', 'Paused')
LIMIT 10;

-- 2c. Is every FinishedRunning record a whole bag? Count the ones whose
-- amount differs from the bag size (amount <> totalamount).
-- Result: 3453 of 35316 differ (about 1 in 10). The other 9 in 10 are
-- whole bags in one record.
.print
.print -- 2c. FinishedRunning records with amount <> totalamount
SELECT
    COUNT(*) AS n_records,
FROM inputevents AS e
JOIN product_map AS m
    ON e.itemid = m.itemid
WHERE e.statusdescription = 'FinishedRunning'
    AND e.amount <> e.totalamount;

-- 2d. Total FinishedRunning records, to put 2c's count in proportion.
-- Result: 35316
.print
.print -- 2d. All FinishedRunning records
SELECT
    COUNT(*) AS n_records,
FROM inputevents AS e
JOIN product_map AS m
    ON e.itemid = m.itemid
WHERE e.statusdescription = 'FinishedRunning';

-- 2e. What are the 1 in 10 FinishedRunning records that aren't whole bags?
-- Result: diff is large (not rounding), and orderid <> linkorderid every
-- time, so each is a later record of an order that started earlier.
.print
.print -- 2e. Sample of FinishedRunning records that are not whole bags
SELECT
    e.orderid,
    e.linkorderid,
    e.starttime,
    e.endtime,
    e.amount,
    e.totalamount,
    e.totalamount - e.amount AS diff
FROM inputevents AS e
JOIN product_map AS m
    ON e.itemid = m.itemid
WHERE e.statusdescription = 'FinishedRunning'
    AND e.amount <> e.totalamount
LIMIT 10;

-- 2f. Follow one order from 2e: every record sharing its linkorderid,
-- in time order.
-- Result: 2 records, Paused then FinishedRunning. Their amounts add up to
-- about totalamount: one bag charted as two pieces.
.print
.print -- 2f. Every record of order 10081336
SELECT
    e.orderid,
    e.linkorderid,
    e.starttime,
    e.endtime,
    e.amount,
    e.totalamount,
    e.totalamount - e.amount AS diff,
    e.statusdescription
FROM inputevents AS e
JOIN product_map AS m
    ON e.itemid = m.itemid
WHERE e.linkorderid = 10081336
ORDER BY e.starttime;

-- 2g. What do Stopped records look like? Sample 10.
-- Result: orderid = linkorderid every time (the first record of its order),
-- and amount is less than totalamount: the bag was started and not finished.
.print
.print -- 2g. Sample of Stopped records
SELECT
    e.orderid,
    e.linkorderid,
    e.starttime,
    e.endtime,
    e.amount,
    e.totalamount
FROM inputevents AS e
JOIN product_map AS m
    ON e.itemid = m.itemid
WHERE e.statusdescription = 'Stopped'
ORDER BY e.orderid
LIMIT 10;

-- 2h. What do Rewritten records look like? Sample 10.
-- Result: orderid <> linkorderid every time (never the first record of its
-- order), and amount is far from totalamount, often many times bigger than
-- the bag.
.print
.print -- 2h. Sample of Rewritten records
SELECT
    e.orderid,
    e.linkorderid,
    e.starttime,
    e.endtime,
    e.amount,
    e.totalamount
FROM inputevents AS e
JOIN product_map AS m
    ON e.itemid = m.itemid
WHERE e.statusdescription = 'Rewritten'
ORDER BY e.orderid
LIMIT 10;

-- 2i. Follow one order from 2h: every record sharing its linkorderid,
-- in time order.
-- Result: 3 records. Paused 117.6, FinishedRunning 207.7, Rewritten 2077.0.
-- The Rewritten record has the same starttime and endtime as the
-- FinishedRunning one, with the amount mistyped (2077.0 for 207.7).
.print
.print -- 2i. Every record of order 10000041
SELECT
    e.orderid,
    e.linkorderid,
    e.starttime,
    e.endtime,
    e.amount,
    e.totalamount,
    e.statusdescription,
    e.amountuom
FROM inputevents AS e
JOIN product_map AS m
    ON e.itemid = m.itemid
WHERE e.linkorderid = 10000041
ORDER BY e.starttime, e.orderid;


-- 2j. To prove that every Paused bag has a later FinishedRunning record, count
-- the Paused bags (distinct linkorderid) that have no FinishedRunning record.
-- The result should be 0.
-- Result: 0. The inner Paused query alone returns 3437 bags (3467 Paused
-- records, so some bags pause more than once), and none of them is missing
-- a FinishedRunning record. Without the product_map join the counts were
-- 4347 bags / 4387 records: the join drops every item that isn't one of
-- the three blood products.
.print
.print -- 2j. Paused bags with no FinishedRunning record

SELECT COUNT(*)
FROM (
    SELECT DISTINCT
        e.linkorderid
    FROM inputevents AS e
    JOIN product_map AS m
        ON e.itemid = m.itemid
    WHERE e.statusdescription = 'Paused'
) AS p
WHERE p.linkorderid NOT IN (
    SELECT DISTINCT
        e.linkorderid
    FROM inputevents AS e
    JOIN product_map AS m
        ON e.itemid = m.itemid
    WHERE e.statusdescription = 'FinishedRunning'
);

-- 2k. Does a bag with a Stopped record have any other counted records?
-- Look for counterexamples: Stopped bags with more than one record.
-- Result: no rows. All 1923 Stopped bags have one record after cleaning.
-- Without cleaning, 100 bags have extra rows: Rewritten records or exact
-- duplicates. So the claim holds for counted records, not all raw rows.
.print
.print -- 2k. Stopped bags with more than one counted record

SELECT
    e.linkorderid,
    COUNT(*) AS n_records
FROM (
    -- DISTINCT removes exact copies of whole rows.
    -- <> means "not equal to": omit records replaced by a correction.
    SELECT DISTINCT *
    FROM inputevents
    WHERE statusdescription <> 'Rewritten'
) AS e
JOIN product_map AS m
    ON e.itemid = m.itemid
-- The inner query lists blood-product bag IDs with a Stopped record.
-- IN keeps every counted record for those bags, regardless of its status.
WHERE e.linkorderid IN (
    SELECT e.linkorderid
    FROM inputevents AS e
    JOIN product_map AS m
        ON e.itemid = m.itemid
    WHERE e.statusdescription = 'Stopped'
)
GROUP BY e.linkorderid
-- HAVING filters the groups after their records have been counted.
-- No rows means no Stopped bag has more than one counted record.
HAVING COUNT(*) > 1;

-- Step 3: repeats -------------------------------------------------------------
-- An exact copy is a row that matches another row in every column: same
-- orderid, same times, same amount, everything. Rule bullet 4 says such
-- copies count once, so we need to know how many there are.
--
-- Get two numbers, for blood-product rows only (keep the product_map join):
--   3a. all rows:        count(*) over inputevents joined to product_map.
--   3b. rows with copies removed: put `select distinct *` in a derived
--       table (as in 2k), then count(*) over that derived table. DuckDB
--       has no count(distinct *), so the derived table is the way.
-- The difference 3a - 3b is the number of copies (pattern 10). If it is 0,
-- there are none.
--
-- Note for 3b: the join can go inside the derived table or outside it.
-- Try both and check whether the count changes.

-- Q: Are there exact copies? How many?
-- A: all rows = 42546, distinct rows = 42243, copies = 303. Joining inside or
-- outside the derived table gives the same 42243: product_map adds one
-- column with one value per itemid, so it can't make two identical rows
-- differ or two different rows collide.

-- 3a. All blood-product rows.
-- Result: 42546
.print
.print -- 3a. All rows
SELECT COUNT(*) AS n_rows
FROM inputevents AS e
JOIN product_map AS m
    ON e.itemid = m.itemid;

-- 3b. The same rows with exact copies removed. Start with the plain
-- `select distinct *` (commented out), then nest it in a derived table.
-- Result: 42243
-- SELECT DISTINCT *
-- FROM inputevents AS e
-- JOIN product_map AS m
--     ON e.itemid = m.itemid;
.print
.print -- 3b. Distinct rows, join inside the derived table
SELECT COUNT(*) AS n_rows
FROM (
    SELECT DISTINCT *
    FROM inputevents AS e
    JOIN product_map AS m
        ON e.itemid = m.itemid
) AS d;

-- Same count with the join outside the derived table.
-- Result: 42243
.print
.print -- 3b. Distinct rows, join outside the derived table
SELECT COUNT(*) AS n_rows
FROM (
    SELECT DISTINCT *
    FROM inputevents
) AS e
JOIN product_map AS m
    ON e.itemid = m.itemid;

-- Step 4: bag IDs --------------------------------------------------------------
-- Rule bullet 1 says a bag counts once however many records it has, so the
-- view needs a column that is the same for every record of one bag and
-- different between bags: that column becomes bag_id. Step 2 (2e, 2f, 2i)
-- already pointed at it; this step confirms the choice on more bags.
--
--   4a. Group the blood-product rows by your candidate column and count
--       rows per group. Keep only groups with more than one row
--       (group by ... having count(*) > 1). Order by the count, biggest
--       first, so the busiest bags are at the top. Two numbers to note:
--       how many bags have more than one record in total (the number of
--       rows this query returns), and how many records the busiest bag has.
--   4b. Pick one ID from 4a that you haven't looked at yet (not 10081336
--       or 10000041) and list all its rows: orderid, the candidate column,
--       statusdescription, starttime, endtime, amount, totalamount. Order
--       by starttime.
--
-- On track: most bags have one record and some have several. Ordered by
-- starttime, the records read like a story: started, paused, resumed,
-- finished or stopped. The first record's orderid equals the shared ID
-- (patterns 3, 5).

-- Q: Which column is bag_id? What story do one bag's records tell?
-- A: The linkorderid column is the bag_id. records show amounts given over time.

-- 4a.
-- there are 4 records in the busiest bags. There are 5168 bags with >1 records.
.print -- 4a.

SELECT
    e.linkorderid,
    COUNT(*) as count
FROM inputevents AS e
JOIN product_map AS m
    ON e.itemid = m.itemid
GROUP BY e.linkorderid
HAVING COUNT(*) > 1
ORDER BY count DESC;

-- 4b.
.print -- 4b.
SELECT
    e.orderid,
    e.statusdescription,
    e.starttime,
    e.endtime,
    e.amount,
    e.totalamount,
FROM inputevents AS e
JOIN product_map AS m
    ON e.itemid = m.itemid
WHERE e.linkorderid = 10058651
ORDER BY e.starttime;

-- Step 5: units ---------------------------------------------------------------
-- Rule bullet 5 says a bag counts once whatever unit its amount is in. One
-- of your three items records amount in 'units' instead of 'ml'. Find it
-- and check whether its records behave like the others.
--
--   5a. Which itemid uses 'units'? Group the blood-product rows by itemid
--       and amountuom with a count. One item should show a different uom.
--   5b. For that item, over the records you decided to count in steps 2
--       and 3 (so: drop Rewritten, drop exact copies), get min(amount),
--       max(amount) and the list of distinct amounts with a count of each
--       (pattern 6). Compare with the ml items: hundreds of ml per bag.
--
-- On track: the amounts are small whole numbers. Ask what one 'unit' is for
-- this product, and whether a record saying amount = 2 is one bag or two.
-- Whatever you decide here, bag_id still decides how many rows the view has.

-- Q: What does one record's amount count? Is a record still one bag?
-- A: The amount counts pooled donors. A record is still one bag.

-- 5a. Which itemid uses 'units'?
-- Three queries, from simplest to most informative.

-- 5a-i. What values does amountuom take at all?
-- Result: two values, 'ml' and 'units' (varchar).
.print -- 5a-i. distinct amountuom values
SELECT DISTINCT
    e.amountuom
FROM inputevents AS e
JOIN product_map AS m
    ON e.itemid = m.itemid;

-- 5a-ii. Which item carries 'units'? Filter to that value and list the items.
-- Result: one item, 990102 (platelets, "Pooled platelet product recorded
-- in units").
.print -- 5a-ii. items recorded in units
SELECT DISTINCT
    e.itemid,
    m.product,
    m.note
FROM inputevents AS e
JOIN product_map AS m
    ON e.itemid = m.itemid
WHERE e.amountuom = 'units';

-- 5a-iii. Same answer in one query: one row per (itemid, amountuom) pair
-- with a record count. Each item appears exactly once, so no item mixes
-- units: 990102 is all 'units' (1398 records); the other four are all 'ml'.
-- m.product is in the GROUP BY because it is in the SELECT; each itemid has
-- one product so the groups are unchanged.
.print -- 5a-iii. records per item and unit
SELECT
    e.itemid,
    m.product,
    e.amountuom,
    COUNT(*) AS n_records
FROM inputevents AS e
JOIN product_map AS m
    ON e.itemid = m.itemid
GROUP BY e.itemid, m.product, e.amountuom
ORDER BY e.itemid;


-- 5b. What amounts does 990102 record? Four queries: the first two read
-- every raw record, the last two only the records that count (no Rewritten,
-- no exact copies). Comparing the two pairs shows what the filter removes.

-- 5b-i. Range of amounts, before filtering.
-- Result: min 0.4, max 60.0.
.print
.print -- 5b-i. 990102 min/max amount, before filtering
SELECT
    MIN(e.amount),
    MAX(e.amount)
FROM inputevents AS e
JOIN product_map AS m
    ON e.itemid = m.itemid
WHERE e.itemid = 990102;

-- 5b-ii. Distinct amounts with a count, before filtering (1398 records).
-- Result: 12 values. 0.4 (9), 0.5 (15), 0.6 (9), 4 (291), 5 (515),
-- 6 (527), 8 (7), 10 (6), 12 (6), 40 (1), 50 (7), 60 (5).
.print
.print -- 5b-ii. 990102 amounts with counts, before filtering
SELECT
    e.amount,
    COUNT(*)
FROM inputevents as e
JOIN product_map AS m
    ON e.itemid = m.itemid
GROUP BY e.amount, e.itemid
HAVING e.itemid = 990102;

-- 5b-iii. Range of amounts, counted records only.
-- Result: min 4.0, max 6.0.
.print
.print -- 5b-iii. 990102 min/max amount, counted records only
SELECT
    MIN(e.amount),
    MAX(e.amount)
FROM(
SELECT DISTINCT *
FROM inputevents AS e
WHERE e.statusdescription <> 'Rewritten'
) as e
WHERE e.itemid = 990102;

-- 5b-iv. Distinct amounts with a count, counted records only (1321 records).
-- Result: 3 values. 4 (287), 5 (511), 6 (523). Every other value in 5b-ii
-- came from a Rewritten record: the decimal point slipped one place
-- (0.5, 50) or the value doubled (8, 10, 12).
.print
.print -- 5b-iv. 990102 amounts with counts, counted records only
SELECT
    e.amount,
    COUNT(*)
FROM(
    SELECT DISTINCT *
    FROM inputevents AS e
    WHERE e.statusdescription <> 'Rewritten'
        AND e.itemid = 990102
) AS e
GROUP BY e.amount, e.itemid; 

-- Step 6: build bags ------------------------------------------------------------
-- Write the view with a CTE (`with ... as (...)`) in two parts
-- (patterns 11, 14):
--
--   first  `counted`: the blood-product rows that count, applying your
--          answers from steps 2 to 4 as filters: the product_map join,
--          a WHERE on statusdescription, and `select distinct` for copies.
--          Run this part on its own first and check it two ways:
--            - select statusdescription, count(*) from counted group by all:
--              only the statuses you decided to keep appear.
--            - count(*) of counted equals count(*) of select distinct *
--              from counted (no copies left).
--   then   `bags`: group `counted` by the bag ID so there is one row per
--          bag, and build each output column from the group:
--            bag_id      the grouping column
--            stay_id, product, itemid, amountuom
--                        same for every record of a bag, so group by them
--                        too (or take min/max, either works)
--            starttime   earliest start in the bag
--            endtime     latest end in the bag
--            n_records   how many counted records the bag has
--            amount      total given across the bag's records
--
-- Develop it as a plain SELECT, and only once Step 7 passes wrap it in
-- `create or replace view bags as ...`. That needs a session opened
-- without -readonly.

-- 6a. One row per bag. `counted` keeps the records that count (blood
-- products only, no Rewritten, no exact copies); the outer query groups
-- them by linkorderid. stay_id, product, itemid and amountuom are the same
-- for every record of a bag, so grouping by them doesn't split any bag.
-- Result: 36,993 bags. LIMIT 10 is only for the preview; leave it out of
-- the view.
.print
.print -- 6a. bags, first 10
CREATE OR REPLACE VIEW bags AS
WITH counted AS (
    SELECT DISTINCT e.*, m.product
    FROM inputevents AS e
    JOIN product_map AS m
        ON e.itemid = m.itemid
    WHERE e.statusdescription <> 'Rewritten'
)
SELECT
    c.linkorderid AS bag_id,
    c.stay_id,
    c.product,
    c.itemid,
    c.amountuom,
    MIN(c.starttime) AS starttime,
    MAX(c.endtime) AS endtime,
    COUNT(*) AS n_records,
    SUM(c.amount) AS amount
FROM counted AS c
GROUP BY c.linkorderid, c.stay_id, c.product, c.itemid, c.amountuom
ORDER BY bag_id;

-- Step 7: check before grading ------------------------------------------------
-- Count the rows of bags, and count the distinct bag_id values: they must be
-- equal. Then, for each itemid, look at the smallest and largest n_records
-- and amount: do they look sensible?
--
-- The view doesn't exist yet, so each check repeats the 6a query as a second
-- CTE named `bags` and reads from that.

-- 7a. One row per bag?
-- Result: 36,993 rows, 36,993 distinct bag_ids. Equal, so no bag is split.
.print
.print -- 7a. rows vs distinct bag_ids
WITH counted AS (
    SELECT DISTINCT e.*, m.product
    FROM inputevents AS e
    JOIN product_map AS m
        ON e.itemid = m.itemid
    WHERE e.statusdescription <> 'Rewritten'
),
bags AS (
    SELECT
        c.linkorderid AS bag_id,
        c.stay_id,
        c.product,
        c.itemid,
        c.amountuom,
        MIN(c.starttime) AS starttime,
        MAX(c.endtime) AS endtime,
        COUNT(*) AS n_records,
        SUM(c.amount) AS amount
    FROM counted AS c
    GROUP BY c.linkorderid, c.stay_id, c.product, c.itemid, c.amountuom
)
SELECT
    COUNT(*) AS n_bags,
    COUNT(DISTINCT b.bag_id) AS n_distinct_bags
FROM bags AS b;

-- 7b. Records and amounts per item.
-- Result:
--   itemid  unit   n_bags  records  amount
--   990101  ml       6842    1-2    65.3-352.4
--   990102  units    1321    1-1     4-6
--   990103  ml       1924    1-2    57.9-328.8
--   990111  ml      17613    1-2    87.3-395.1
--   990121  ml       9293    1-2    72.8-329.6
-- max_records is 2: a bag is paused at most once, and nothing extra (copies,
-- Rewritten) slipped into counted. 990102 is never paused (always 1 record),
-- which fits its amount being a count of pooled donors that can't be split
-- across records. The ml ranges are realistic bag volumes, with nothing near
-- double a bag. 990102 stays at 4-6 donor units, as in 5b-iv. Step 7 passes.
.print
.print -- 7b. records and amounts per item
WITH counted AS (
    SELECT DISTINCT e.*, m.product
    FROM inputevents AS e
    JOIN product_map AS m
        ON e.itemid = m.itemid
    WHERE e.statusdescription <> 'Rewritten'
),
bags AS (
    SELECT
        c.linkorderid AS bag_id,
        c.stay_id,
        c.product,
        c.itemid,
        c.amountuom,
        MIN(c.starttime) AS starttime,
        MAX(c.endtime) AS endtime,
        COUNT(*) AS n_records,
        SUM(c.amount) AS amount
    FROM counted AS c
    GROUP BY c.linkorderid, c.stay_id, c.product, c.itemid, c.amountuom
)
SELECT
    b.itemid,
    b.amountuom,
    COUNT(*) AS n_bags,
    MIN(b.n_records) AS min_records,
    MAX(b.n_records) AS max_records,
    MIN(b.amount) AS min_amount,
    MAX(b.amount) AS max_amount
FROM bags AS b
GROUP BY b.itemid, b.amountuom
ORDER BY b.itemid;
