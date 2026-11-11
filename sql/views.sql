-- Views shared by the challenges. Load them at the top of any file or
-- session, from the project root:
--   .read sql/views.sql
-- Add each challenge's view here once it passes grading. Order matters:
-- a view must come after any view it uses.


-- Challenge 1: the item IDs of the three blood products
create or replace view product_map as
select
    m.itemid,
    m.product,
    e.amountuom,
    m.note
from (
    values
    (990101, 'platelets', 'Platelet product recorded in inputevents.'),
    (990102, 'platelets', 'Pooled platelet product recorded in units.'),
    (990103, 'platelets', 'Apheresis platelet product; included with platelets.'),
    (990111, 'rbc', 'Packed red blood cell product recorded in inputevents.'),
    (990121, 'plasma', 'Fresh frozen plasma product recorded in inputevents.')
) as m (itemid, product, note)
join (
    select distinct
        itemid,
        amountuom
    from inputevents
) as e on e.itemid = m.itemid;


-- Challenge 2: one row per bag. Keeps the blood-product records that count
-- (no Rewritten records, no exact copies) and groups them by linkorderid.
-- amount is in amountuom: ml for most items, donor units for 990102.
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


-- Challenge 3: bag count and first bag time for every stay and product.
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


-- Challenge 3: how many stays got each bag count, per product. share is
-- n_stays as a fraction of all ICU stays.
create or replace view bag_distribution as
select
    s.product,
    s.n_bags,
    count(s.stay_id) as n_stays,
    round(count(s.stay_id) / (select count(*) from icustays), 4) as share
from stay_bags as s
group by s.product, s.n_bags
order by s.product, s.n_bags;
