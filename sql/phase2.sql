-- Phase 2: fitting demand models (SQL part)
--
-- Model fitting and grading are in phase2/fit.py and phase2/grade.py.
-- Creating views and exporting files needs a session opened without -readonly.
-- The Result comments record one synthetic run; other runs, and the MIMIC-IV
-- demo, give different numbers.
.read sql/views.sql


-- Step 1: gaps between bags ---------------------------------------------------
-- For each stay and product, in time order, how long after the previous bag
-- ended did this bag start? Count the gaps in whole hours.
-- Result: the counts are nearly empty from 3 to 11 hours, depending on what
-- counts as empty. A gap of more than 7 hours, about halfway, starts a new
-- episode.
with bags_with_prev_end as (
    select
        b.stay_id,
        b.product,
        b.starttime,
        b.endtime,
        lag(b.endtime, 1)
            over (partition by b.product, b.stay_id order by b.starttime)
            as prev_end
    from bags as b
    order by b.stay_id, b.product, b.starttime
),

gaps as (
    select
        *,
        floor(extract(epoch from b.starttime - b.prev_end) / 3600) as gap_hours
    from bags_with_prev_end as b
),

piles as (
    select
        gap_hours,
        count(*)
    from gaps
    where gap_hours is not null
    group by gap_hours
    order by gap_hours
)

select *
from piles;


-- Step 2: build the episodes ---------------------------------------------------
-- Flag each bag that starts a new episode, number the episodes, then make one
-- row per episode.
-- Columns: stay_id, product, episode_no, episode_start, n_bags
--
-- Every episode has at least one bag, and every stay that received the
-- product has at least one episode, so stays <= episodes <= bags must hold.
-- Result: it holds for every product.
--   product    n_stays  n_episodes  n_bags
--   plasma        6554        6635   10095
--   platelets     3705        4484    7306
--   rbc          11972       12402   19957
create or replace view episodes as
with bags_with_prev_end as (
    select
        b.stay_id,
        b.product,
        b.starttime,
        b.endtime,
        lag(b.endtime, 1) over (
            partition by b.product, b.stay_id
            order by b.starttime
        ) as prev_end
    from bags as b
    order by b.stay_id, b.product, b.starttime
),

gaps as (
    select
        *,
        floor(extract(epoch from b.starttime - b.prev_end) / 3600) as gap_hours
    from bags_with_prev_end as b
),

numbered as (
    select
        stay_id,
        product,
        case
            when gap_hours is null then 1
            when gap_hours > 7 then 1
            else 0
        end as is_episode,
        sum(is_episode) over (
            partition by stay_id, product
            order by starttime
        ) as episode_no,
        starttime as episode_start
    from gaps
)

select
    stay_id,
    product,
    episode_no,
    min(episode_start) as episode_start,
    count(*) as n_bags
from numbered
group by stay_id, product, episode_no;

select
    product,
    count(distinct stay_id) as n_stays,
    count(episode_no) as n_episodes,
    sum(n_bags) as n_bags
from episodes
group by product
order by product;

-- Step 3: check the episodes ----------------------------------------------------
-- Per product, the episodes' n_bags should add up to the number of bags, and
-- no episode should have n_bags below 1.
-- Result: both hold.
select
    product,
    sum(n_bags) as n_bags
from episodes
group by product;

select
    product,
    count(*)
from bags
group by product;

-- `summarize episodes;` shows the minimum n_bags, which is 1.

-- Step 4: episodes per day, first attempt ---------------------------------------
-- Count episodes per product per calendar day of episode_start. Fill in days
-- with no episodes as 0, from the first date in the data to the last. Then
-- take the mean per product.
-- Result: 30149 days, about 82.5 years, which can't be one hospital's
-- records: the shifted dates spread across the 2110s to 2190s. Mean per day:
-- plasma 0.22, platelets 0.15, rbc 0.41.
with counts as (
    select
        product,
        episode_start::date as day,
        count(*) as num_episodes
    from episodes
    group by product, day
),

calendar as (
    select day::date as day
    from generate_series(
        (select min(day) from counts),
        (select max(day) from counts),
        interval 1 day
    ) as t (day)
),

products as (
    select distinct product
    from product_map
),

daily_counts as (
    select
        cal.day,
        p.product,
        coalesce(c.num_episodes, 0) as num_episodes
    from calendar as cal
    cross join products as p
    left join counts as c
        on c.product = p.product
        and c.day = cal.day
)

select
    product,
    count(*) as n_days,  -- one row per calendar day, so this counts days
    count(*) / 365.25 as n_years,
    avg(num_episodes) as mean_per_day
from daily_counts
group by product
order by product;

-- Step 5: what a day means ------------------------------------------------------
-- Each patient's dates are shifted into the future by a different amount.
-- patients.anchor_year_group gives the real years, so it gives the real
-- length of time the data covers.
-- Result: 4383 real days (2008-01-01 to 2019-12-31, exactly 12 years). The four
--    anchor_year_group ranges sit side by side with no gaps or overlaps.
--    Step 4's mean can't be used: each patient's dates are shifted by a
--    different number of years, so the calendar from first to last shifted
--    date is far too long and mostly filled with zero days. The real-year
--    groups give the true length of time, so they make the right denominator.
--    Episodes per real day (episodes / 4383):
--      plasma     6635 / 4383 = 1.51
--      platelets  4484 / 4383 = 1.02
--      rbc       12402 / 4383 = 2.83

select
    anchor_year_group,
    count(*) as n_patients
from patients
group by anchor_year_group
order by anchor_year_group;


-- The four groups run side by side from 2008 to 2019, so the real stretch is
-- 2008-01-01 to 2019-12-31. The +1 counts the last day too.
select
    date '2019-12-31' - date '2008-01-01' + 1 as real_days,  -- 4383
    real_days / 365.25 as real_years;  -- 12.0

select
    product,
    count(episode_no) / 4383.0 as episodes_per_day
from episodes
group by product
order by product;

-- Step 6: what survives ---------------------------------------------------------
-- Count episodes per product per day of the week, with dayname(episode_start).
-- Result: weekends are low for all three products: Saturday about 10% and
-- Sunday about 15-20% below the weekday average. Weekdays are within about 5%
-- of each other. The synthetic date shifts keep the real day of the week, so
-- weekday counts survive them. MIMIC-IV's shifts don't, so on real data this
-- step can't measure a weekday effect.

select
    product,
    dayname(episode_start) as day,
    count(*) as n_episodes
from episodes
group by product, dayname(episode_start), isodow(episode_start)
order by product, isodow(episode_start);

-- Step 7: per stay --------------------------------------------------------------
-- From stay_bags, per product: the share of stays with at least one bag, and
-- the mean and var_samp of n_bags among those stays only.
-- Result: most stays never receive any of the three products (share_any:
-- plasma 0.11, platelets 0.06, rbc 0.20). Among stays with at least one bag,
-- the variance is above the mean only for platelets (var/mean: plasma 0.69,
-- platelets 1.94, rbc 0.82).

select
    product,
    count(*) as n_stays,  -- every stay, zeros included
    count(*) filter (where n_bags >= 1) as n_stays_any,
    n_stays_any / n_stays as share_any,
    -- the mean and variance below cover only stays with at least one bag
    avg(n_bags) filter (where n_bags >= 1) as mean_any,
    var_samp(n_bags) filter (where n_bags >= 1) as var_any,
    var_any / mean_any as var_to_mean  -- above 1 means variance > mean
from stay_bags
group by product
order by product;


-- Export ------------------------------------------------------------------------
-- phase2/fit.py reads these files, so it doesn't need the database open.

copy (
    select
        stay_id,
        product,
        episode_no,
        episode_start,
        n_bags
    from episodes
    order by stay_id, product, episode_no
) to 'phase2/episodes.csv' (header);

copy (
    select
        stay_id,
        product,
        n_bags
    from stay_bags
    order by stay_id, product
) to 'phase2/stay_bags.csv' (header);
