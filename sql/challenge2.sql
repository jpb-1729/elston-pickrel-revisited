-- Challenge 2: turn records into bags
--
-- Worksheet. Fill in each section in order. Answer each question in a comment
-- before moving on; the answers decide what goes into the final view.
-- Run the whole file:  .read sql/challenge2.sql
-- Run one query:       paste it at the duckdb prompt
--
-- Needs product_map from Challenge 1. Check with .tables; if it's missing,
-- run .read sql/challenge1.sql first. Creating views (product_map in
-- Challenge 1, bags in step 6) needs a session opened without -readonly.


-- Step 1: narrow down ------------------------------------------------------
-- A "record" is one row of inputevents. Count the rows for each of your
-- three products: the result has three rows (platelets, rbc, plasma), each
-- with a count. inputevents has no product column, so join it to product_map
-- on itemid; the join also drops every item that isn't one of the three
-- (patterns 5, 7).

-- Q: How many records per product?
-- A:


-- Step 2: statuses -----------------------------------------------------------
-- Same as step 1, but count rows for each value of statusdescription
-- instead of each product. Then, for each status, look at ten whole rows
-- (select * ... where statusdescription = '...' limit 10) (patterns 3, 5).

-- Q: For each status: whole bag, part of a bag, or not a bag? Which rule says so?
-- A:


-- Step 3: repeats -------------------------------------------------------------
-- An exact copy is a row identical to another row in every column. Count
-- all the rows, then count them again with copies removed (select distinct *).
-- If the two numbers differ, the difference is how many copies there are
-- (pattern 10).

-- Q: Are there exact copies? How many?
-- A:


-- Step 4: bag IDs --------------------------------------------------------------
-- Count rows for each linkorderid, and keep only the ones with more than
-- one row (group by ... having count(*) > 1). Pick one of those IDs and
-- list all its rows, ordered by starttime (patterns 3, 5).

-- Q: Which column is bag_id? What story do one bag's records tell?
-- A:


-- Step 5: units ---------------------------------------------------------------
-- One of your items records amount in 'units' instead of 'ml'. For that
-- item, look at the smallest and largest amount, and the list of distinct
-- amounts (pattern 6).

-- Q: What does one record's amount count? Is a record still one bag?
-- A:


-- Step 6: build bags ------------------------------------------------------------
-- Write the view in two steps with `with` (patterns 11, 14):
--   first: a query that keeps only the rows that count, using your answers
--          to steps 2 to 4. Run and check it on its own before going on.
--   then:  group those rows so there is one row per bag.
-- Columns: bag_id, stay_id, product, itemid, starttime, endtime,
--          n_records, amount, amountuom


-- Step 7: check before grading ------------------------------------------------
-- Count the rows of bags, and count the distinct bag_id values: they must be
-- equal. Then, for each itemid, look at the smallest and largest n_records
-- and amount: do they look sensible?

