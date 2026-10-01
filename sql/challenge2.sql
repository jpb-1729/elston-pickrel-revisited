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
-- Records per product, using product_map (patterns 5, 7).

-- Q: How many records per product?
-- A:


-- Step 2: statuses -----------------------------------------------------------
-- Records per statusdescription, then a few raw records of each (patterns 3, 5).

-- Q: For each status: whole bag, part of a bag, or not a bag? Which rule says so?
-- A:


-- Step 3: repeats -------------------------------------------------------------
-- count(*) versus the count of select distinct * (pattern 10).

-- Q: Are there exact copies? How many?
-- A:


-- Step 4: bag IDs --------------------------------------------------------------
-- Shared IDs with more than one record, then every record of one of them,
-- ordered by starttime (patterns 3, 5).

-- Q: Which column is bag_id? What story do one bag's records tell?
-- A:


-- Step 5: units ---------------------------------------------------------------
-- min, max and distinct amounts for the item recorded in units (pattern 6).

-- Q: What does one record's amount count? Is a record still one bag?
-- A:


-- Step 6: build bags ------------------------------------------------------------
-- Step one of the with: the records that count. Check it on its own first.
-- Step two: one row per bag (patterns 11, 14).
-- Columns: bag_id, stay_id, product, itemid, starttime, endtime,
--          n_records, amount, amountuom


-- Step 7: check before grading ------------------------------------------------
-- count(*) versus count(distinct bag_id); n_records and amount per item.

