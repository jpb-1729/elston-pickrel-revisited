-- Views shared by the challenges. Load them at the top of any file or
-- session, from the project root:
--   .read sql/views.sql
-- Add each challenge's view here once it passes grading. Order matters:
-- a view must come after any view it uses.


-- Challenge 1: the item IDs of the three blood products
CREATE OR REPLACE VIEW product_map AS
SELECT
    m.itemid,
    m.product,
    e.amountuom,
    m.note
FROM (VALUES
    (990101, 'platelets', 'Platelet product recorded in inputevents.'),
    (990102, 'platelets', 'Pooled platelet product recorded in units.'),
    (990103, 'platelets', 'Apheresis platelet product; included with platelets.'),
    (990111, 'rbc', 'Packed red blood cell product recorded in inputevents.'),
    (990121, 'plasma', 'Fresh frozen plasma product recorded in inputevents.')
) AS m(itemid, product, note)
JOIN (
    SELECT DISTINCT itemid, amountuom
    FROM inputevents
) AS e ON e.itemid = m.itemid;


-- Challenge 2: one row per bag. Keeps the blood-product records that count
-- (no Rewritten records, no exact copies) and groups them by linkorderid.
-- amount is in amountuom: ml for most items, donor units for 990102.
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
GROUP BY c.linkorderid, c.stay_id, c.product, c.itemid, c.amountuom;


-- Challenge 3: bag count and first bag time for every stay and product.
-- Stays with no bags of a product get n_bags = 0 and a null first_bag_start.
CREATE OR REPLACE VIEW stay_bags AS
WITH stay_products AS (
    SELECT s.stay_id, p.product
    FROM (SELECT DISTINCT stay_id FROM icustays) AS s
    CROSS JOIN (SELECT DISTINCT product FROM product_map) AS p
),
bag_counts AS (
    SELECT
        b.stay_id,
        b.product,
        MIN(b.starttime) AS first_bag_start,
        COUNT(b.bag_id) AS n_bags
    FROM bags AS b
    GROUP BY b.stay_id, b.product
)
SELECT
    s.stay_id,
    s.product,
    COALESCE(b.n_bags, 0) AS n_bags,
    b.first_bag_start
FROM stay_products AS s
LEFT JOIN bag_counts AS b
    ON b.stay_id = s.stay_id
    AND b.product = s.product;


-- Challenge 3: how many stays got each bag count, per product. share is
-- n_stays as a fraction of all ICU stays.
CREATE OR REPLACE VIEW bag_distribution AS
SELECT
    s.product,
    s.n_bags,
    COUNT(s.stay_id) AS n_stays,
    ROUND(COUNT(s.stay_id) / (SELECT COUNT(*) FROM icustays), 4) AS share
FROM stay_bags AS s
GROUP BY s.product, s.n_bags
ORDER BY s.product, s.n_bags;
