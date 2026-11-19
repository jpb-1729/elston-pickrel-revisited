-- Challenge 2: turn records into bags
--
-- inputevents has one row per record, and records are not bags. A bag is one
-- unit of product hung and started for a patient:
--   1. A bag counts once, however many records it was charted in.
--   2. A bag counts even if it wasn't finished.
--   3. A record replaced by a corrected record doesn't count; the correction
--      does.
--   4. Two identical records are one record charted twice; count it once.
--   5. A bag counts once whatever unit its amount is recorded in.
--
-- The Result comments record an earlier synthetic run. Other runs give
-- different counts, and the order IDs looked up below may not exist.
.read sql/views.sql


-- Step 1: narrow down ------------------------------------------------------
-- Records per product. inputevents has no product column, so join it to
-- product_map on itemid; the join also drops every item that isn't one of the
-- three blood products.
select
    m.product,
    count(*) as n_records
from inputevents as e
join product_map as m
    on e.itemid = m.itemid
group by m.product
order by m.product;

-- Step 2: statuses -----------------------------------------------------------
-- Each statusdescription is a whole bag, part of a bag, or not a bag:
--   FinishedRunning  a whole bag when orderid = linkorderid, otherwise the
--                    last part of one (rule 1).
--   Paused           part of a bag; every Paused bag has a later
--                    FinishedRunning record (rule 1, 2j).
--   Stopped          a whole bag, started and not finished (rule 2).
--   Rewritten        not a bag: a mistyped copy of another record (rule 3,
--                    2i).

-- 2a. How many records does each status have? (blood products only)
-- Result: 4 statuses. FinishedRunning = 35316, Paused = 3467,
-- Rewritten = 1827, Stopped = 1936.
select
    e.statusdescription,
    count(*) as n_records
from inputevents as e
join product_map as m
    on e.itemid = m.itemid
group by e.statusdescription;

-- 2b. What do records of one status look like? Sample 10.
-- Set the WHERE to one status at a time, so the sample isn't a mix.
-- Columns to compare: amount vs totalamount (whole bag or part?),
-- orderid vs linkorderid (first note of its order, or a later one?).
select
    e.statusdescription,
    e.stay_id,
    m.product,
    e.orderid,
    e.linkorderid,
    e.starttime,
    e.endtime,
    e.amount,
    e.totalamount
from inputevents as e
join product_map as m
    on e.itemid = m.itemid
where e.statusdescription in ('FinishedRunning', 'Stopped', 'Rewritten', 'Paused')
limit 10;

-- 2c. Is every FinishedRunning record a whole bag? Count the ones whose
-- amount differs from the bag size (amount <> totalamount).
-- Result: 3453 of 35316 differ (about 1 in 10). The other 9 in 10 are
-- whole bags in one record.
select count(*) as n_records
from inputevents as e
join product_map as m
    on e.itemid = m.itemid
where
    e.statusdescription = 'FinishedRunning'
    and e.amount <> e.totalamount;

-- 2d. Total FinishedRunning records, to put 2c's count in proportion.
-- Result: 35316
select count(*) as n_records
from inputevents as e
join product_map as m
    on e.itemid = m.itemid
where e.statusdescription = 'FinishedRunning';

-- 2e. What are the 1 in 10 FinishedRunning records that aren't whole bags?
-- Result: diff is large (not rounding), and orderid <> linkorderid every
-- time, so each is a later record of an order that started earlier.
select
    e.orderid,
    e.linkorderid,
    e.starttime,
    e.endtime,
    e.amount,
    e.totalamount,
    e.totalamount - e.amount as diff
from inputevents as e
join product_map as m
    on e.itemid = m.itemid
where
    e.statusdescription = 'FinishedRunning'
    and e.amount <> e.totalamount
limit 10;

-- 2f. Follow one order from 2e: every record sharing its linkorderid,
-- in time order.
-- Result: 2 records, Paused then FinishedRunning. Their amounts add up to
-- about totalamount: one bag charted as two pieces.
select
    e.orderid,
    e.linkorderid,
    e.starttime,
    e.endtime,
    e.amount,
    e.totalamount,
    e.totalamount - e.amount as diff,
    e.statusdescription
from inputevents as e
join product_map as m
    on e.itemid = m.itemid
where e.linkorderid = 10081336
order by e.starttime;

-- 2g. What do Stopped records look like? Sample 10.
-- Result: orderid = linkorderid every time (the first record of its order),
-- and amount is less than totalamount: the bag was started and not finished.
select
    e.orderid,
    e.linkorderid,
    e.starttime,
    e.endtime,
    e.amount,
    e.totalamount
from inputevents as e
join product_map as m
    on e.itemid = m.itemid
where e.statusdescription = 'Stopped'
order by e.orderid
limit 10;

-- 2h. What do Rewritten records look like? Sample 10.
-- Result: orderid <> linkorderid every time (never the first record of its
-- order), and amount is far from totalamount, often many times bigger than
-- the bag.
select
    e.orderid,
    e.linkorderid,
    e.starttime,
    e.endtime,
    e.amount,
    e.totalamount
from inputevents as e
join product_map as m
    on e.itemid = m.itemid
where e.statusdescription = 'Rewritten'
order by e.orderid
limit 10;

-- 2i. Follow one order from 2h: every record sharing its linkorderid,
-- in time order.
-- Result: 3 records. Paused 117.6, FinishedRunning 207.7, Rewritten 2077.0.
-- The Rewritten record has the same starttime and endtime as the
-- FinishedRunning one, with the amount mistyped (2077.0 for 207.7).
select
    e.orderid,
    e.linkorderid,
    e.starttime,
    e.endtime,
    e.amount,
    e.totalamount,
    e.statusdescription,
    e.amountuom
from inputevents as e
join product_map as m
    on e.itemid = m.itemid
where e.linkorderid = 10000041
order by e.starttime, e.orderid;


-- 2j. To prove that every Paused bag has a later FinishedRunning record, count
-- the Paused bags (distinct linkorderid) that have no FinishedRunning record.
-- The result should be 0.
-- Result: 0. The inner Paused query alone returns 3437 bags (3467 Paused
-- records, so some bags pause more than once), and none of them is missing
-- a FinishedRunning record. Without the product_map join the counts were
-- 4347 bags / 4387 records: the join drops every item that isn't one of
-- the three blood products.

select count(*)
from (
    select distinct e.linkorderid
    from inputevents as e
    join product_map as m
        on e.itemid = m.itemid
    where e.statusdescription = 'Paused'
) as p
where p.linkorderid not in (
    select distinct e.linkorderid
    from inputevents as e
    join product_map as m
        on e.itemid = m.itemid
    where e.statusdescription = 'FinishedRunning'
);

-- 2k. Does a bag with a Stopped record have any other counted records?
-- Look for counterexamples: Stopped bags with more than one record.
-- Result: no rows. All 1923 Stopped bags have one record after cleaning.
-- Without cleaning, 100 bags have extra rows: Rewritten records or exact
-- duplicates. So the claim holds for counted records, not all raw rows.

select
    e.linkorderid,
    count(*) as n_records
from (
    -- DISTINCT removes exact copies of whole rows.
    -- <> means "not equal to": omit records replaced by a correction.
    select distinct *
    from inputevents
    where statusdescription <> 'Rewritten'
) as e
join product_map as m
    on e.itemid = m.itemid
-- The inner query lists blood-product bag IDs with a Stopped record.
-- IN keeps every counted record for those bags, regardless of its status.
where
    e.linkorderid in (
        select e.linkorderid
        from inputevents as e
        join product_map as m
            on e.itemid = m.itemid
        where e.statusdescription = 'Stopped'
    )
group by e.linkorderid
-- HAVING filters the groups after their records have been counted.
-- No rows means no Stopped bag has more than one counted record.
having count(*) > 1;

-- Step 3: repeats -------------------------------------------------------------
-- An exact copy matches another row in every column. Rule 4 counts copies
-- once. The number of copies is all rows (3a) minus distinct rows (3b).
-- DuckDB has no count(distinct *), so 3b counts a `select distinct *`
-- derived table.
--
-- Result: 42546 - 42243 = 303 copies. Joining product_map inside or outside
-- the derived table gives the same 42243: it adds one column with one value
-- per itemid, so it can't make two identical rows differ or two different
-- rows collide.

-- 3a. All blood-product rows.
-- Result: 42546
select count(*) as n_rows
from inputevents as e
join product_map as m
    on e.itemid = m.itemid;

-- 3b. The same rows with exact copies removed.
-- Result: 42243
select count(*) as n_rows
from (
    select distinct *
    from inputevents as e
    join product_map as m
        on e.itemid = m.itemid
) as d;

-- Same count with the join outside the derived table.
-- Result: 42243
select count(*) as n_rows
from (
    select distinct *
    from inputevents
) as e
join product_map as m
    on e.itemid = m.itemid;

-- Step 4: bag IDs --------------------------------------------------------------
-- Rule 1 needs a column shared by every record of one bag and different
-- between bags. Steps 2e, 2f and 2i point to linkorderid, and this step
-- confirms it: in time order, a bag's records show the amount given as it
-- was started, paused and finished, and the first record's orderid equals
-- the linkorderid.

-- 4a. Bags with more than one record, busiest first.
-- Result: 5168 bags have more than one record; the busiest have 4.

select
    e.linkorderid,
    count(*) as count
from inputevents as e
join product_map as m
    on e.itemid = m.itemid
group by e.linkorderid
having count(*) > 1
order by count desc;

-- 4b. All the records of one multi-record bag.
select
    e.orderid,
    e.statusdescription,
    e.starttime,
    e.endtime,
    e.amount,
    e.totalamount
from inputevents as e
join product_map as m
    on e.itemid = m.itemid
where e.linkorderid = 10058651
order by e.starttime;

-- Step 5: units ---------------------------------------------------------------
-- One item records amount in 'units' instead of ml (rule 5). Its amounts
-- count the donors pooled into the bag, so a record is still one bag, and
-- bag_id still decides how many rows the view has.

-- 5a. Which itemid uses 'units'?
-- Three queries, from simplest to most informative.

-- 5a-i. What values does amountuom take at all?
-- Result: two values, 'ml' and 'units' (varchar).
select distinct e.amountuom
from inputevents as e
join product_map as m
    on e.itemid = m.itemid;

-- 5a-ii. Which item carries 'units'? Filter to that value and list the items.
-- Result: one item, 990102 (platelets, "Pooled platelet product recorded
-- in units").
select distinct
    e.itemid,
    m.product,
    m.note
from inputevents as e
join product_map as m
    on e.itemid = m.itemid
where e.amountuom = 'units';

-- 5a-iii. Same answer in one query: one row per (itemid, amountuom) pair
-- with a record count. Each item appears exactly once, so no item mixes
-- units: 990102 is all 'units' (1398 records); the other four are all 'ml'.
-- m.product is in the GROUP BY because it is in the SELECT; each itemid has
-- one product so the groups are unchanged.
select
    e.itemid,
    m.product,
    e.amountuom,
    count(*) as n_records
from inputevents as e
join product_map as m
    on e.itemid = m.itemid
group by e.itemid, m.product, e.amountuom
order by e.itemid;


-- 5b. What amounts does 990102 record? Four queries: the first two read
-- every raw record, the last two only the records that count (no Rewritten,
-- no exact copies). Comparing the two pairs shows what the filter removes.

-- 5b-i. Range of amounts, before filtering.
-- Result: min 0.4, max 60.0.
select
    min(e.amount),
    max(e.amount)
from inputevents as e
join product_map as m
    on e.itemid = m.itemid
where e.itemid = 990102;

-- 5b-ii. Distinct amounts with a count, before filtering (1398 records).
-- Result: 12 values. 0.4 (9), 0.5 (15), 0.6 (9), 4 (291), 5 (515),
-- 6 (527), 8 (7), 10 (6), 12 (6), 40 (1), 50 (7), 60 (5).
select
    e.amount,
    count(*)
from inputevents as e
join product_map as m
    on e.itemid = m.itemid
group by e.amount, e.itemid
having e.itemid = 990102;

-- 5b-iii. Range of amounts, counted records only.
-- Result: min 4.0, max 6.0.
select
    min(e.amount),
    max(e.amount)
from (
    select distinct *
    from inputevents as e
    where e.statusdescription <> 'Rewritten'
) as e
where e.itemid = 990102;

-- 5b-iv. Distinct amounts with a count, counted records only (1321 records).
-- Result: 3 values. 4 (287), 5 (511), 6 (523). Every other value in 5b-ii
-- came from a Rewritten record: the decimal point slipped one place
-- (0.5, 50) or the value doubled (8, 10, 12).
select
    e.amount,
    count(*)
from (
    select distinct *
    from inputevents as e
    where
        e.statusdescription <> 'Rewritten'
        and e.itemid = 990102
) as e
group by e.amount, e.itemid;

-- Step 6: build bags ------------------------------------------------------------
-- The bags view lives in sql/views.sql. A CTE named counted keeps the records
-- that count (blood products only, no Rewritten, no exact copies), and the
-- outer query groups them by linkorderid, one row per bag:
--   bag_id      linkorderid
--   stay_id, product, itemid, amountuom
--               the same for every record of a bag, so grouping by them
--               doesn't split any bag
--   starttime   earliest start in the bag
--   endtime     latest end in the bag
--   n_records   how many counted records the bag has
--   amount      total given across the bag's records


-- Step 7: check the view ---------------------------------------------------------

-- 7a. One row per bag?
-- Result: 36,993 rows, 36,993 distinct bag_ids. Equal, so no bag is split.
select
    count(*) as n_bags,
    count(distinct b.bag_id) as n_distinct_bags
from bags as b;

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
-- double a bag. 990102 stays at 4-6 donor units, as in 5b-iv.
select
    b.itemid,
    b.amountuom,
    count(*) as n_bags,
    min(b.n_records) as min_records,
    max(b.n_records) as max_records,
    min(b.amount) as min_amount,
    max(b.amount) as max_amount
from bags as b
group by b.itemid, b.amountuom
order by b.itemid;
