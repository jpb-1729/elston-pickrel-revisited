-- The views from sql/views.sql, ported to real MIMIC-IV (v2.2 item IDs).
-- Only product_map differs. Load from the project root, in a session opened
-- on a MIMIC-IV database (for example mimic_demo/mimic_demo.duckdb):
--   .read sql/views_mimic.sql
-- Order matters: a view must come after any view it uses.


-- The item IDs of the three blood products, from d_items (category
-- 'Blood Products/Colloids', linksto 'inputevents').
-- Left out on purpose:
--   * The 'OR ... Intake' and 'PACU ... Intake' items (226368, 226369,
--     226367, 227070, 227071, 227072). Each is one total volume given in
--     theatre or recovery before the ICU stay, so it can't be counted in bags.
--   * 220996 'Packed Red Cells', 221013 'Whole Blood' and 220971 'ESDEP', in
--     category 'Fluids - Other (Not In Use)'. No records in the demo; check
--     for records on full MIMIC-IV.
--   * Cryoprecipitate, albumin, cell saver and the other colloids: not one of
--     the three products.
create or replace view product_map as
select
    m.itemid,
    m.product,
    e.amountuom,
    m.note
from (
    values
    (225170, 'platelets', 'Platelets.'),
    (225168, 'rbc', 'Packed Red Blood Cells.'),
    (220970, 'plasma', 'Fresh Frozen Plasma.')
) as m (itemid, product, note)
join (
    select distinct
        itemid,
        amountuom
    from inputevents
) as e on e.itemid = m.itemid;


-- One row per bag (sql/02_bags.sql). Keeps the blood-product records that
-- count (no Rewritten records, no exact copies) and groups them by
-- linkorderid.
-- amount is in amountuom, which is ml for all three items.
create or replace view bags as
with counted as (
    select distinct
        e.*,
        m.product
    from inputevents as e
    join product_map as m
        on e.itemid = m.itemid
    where e.statusdescription <> 'Rewritten'
)

select
    c.linkorderid as bag_id,
    c.stay_id,
    c.product,
    c.itemid,
    c.amountuom,
    min(c.starttime) as starttime,
    max(c.endtime) as endtime,
    count(*) as n_records,
    sum(c.amount) as amount
from counted as c
group by c.linkorderid, c.stay_id, c.product, c.itemid, c.amountuom;


-- Bag count and first bag time for every stay and product
-- (sql/03_stay_bags.sql).
-- Stays with no bags of a product get n_bags = 0 and a null first_bag_start.
create or replace view stay_bags as
with stay_products as (
    select
        s.stay_id,
        p.product
    from (select distinct stay_id from icustays) as s
    cross join (select distinct product from product_map) as p
),

bag_counts as (
    select
        b.stay_id,
        b.product,
        min(b.starttime) as first_bag_start,
        count(b.bag_id) as n_bags
    from bags as b
    group by b.stay_id, b.product
)

select
    s.stay_id,
    s.product,
    coalesce(b.n_bags, 0) as n_bags,
    b.first_bag_start
from stay_products as s
left join bag_counts as b
    on b.stay_id = s.stay_id
    and b.product = s.product;


-- How many stays got each bag count, per product (sql/03_stay_bags.sql).
-- share is n_stays as a fraction of all ICU stays.
create or replace view bag_distribution as
select
    s.product,
    s.n_bags,
    count(s.stay_id) as n_stays,
    round(count(s.stay_id) / (select count(*) from icustays), 4) as share
from stay_bags as s
group by s.product, s.n_bags
order by s.product, s.n_bags;
