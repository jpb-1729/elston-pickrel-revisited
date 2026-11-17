-- Phase 2: fitting demand models (SQL part)
--
-- Model fitting and grading are in phase2/fit.py and phase2/grade.py.
-- Creating views and exporting files needs a session opened without -readonly.
.read sql/views.sql


-- Step 1: gaps between bags ---------------------------------------------------
-- For each stay and product, in time order, how long after the previous bag
-- ended did this bag start? Count the gaps in whole hours (pattern 15).

-- Q: Where is the empty stretch in the gaps? What gap will you use to split
--    one episode from the next?
-- A: The empty stretch in the gaps is 3 to 11 hours depending on definition of empty.
-- use halfway point as split point, which is 7.
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
-- row per episode (patterns 11, 15). Develop it as a plain SELECT, then wrap
-- it in `create or replace view episodes as ...`.
-- Columns: stay_id, product, episode_no, episode_start, n_bags

-- Q: For each product, how many distinct stays, episodes and bags are there?
--    Every episode has at least one bag, and every stay that received the
--    product has at least one episode. So does stays <= episodes <= bags hold
--    for every product?
-- A:
-- ───────────┬─────────┬────────────┬────────┐
-- │  product  │ n_stays │ n_episodes │ n_bags │
-- │  varchar  │  int64  │   int64    │ int128 │
-- ├───────────┼─────────┼────────────┼────────┤
-- │ plasma    │    6554 │       6635 │  10095 │
-- │ platelets │    3705 │       4484 │   7306 │
-- │ rbc       │   11972 │      12402 │  19957 │
-- └───────────┴─────────┴────────────┴────────┘
-- the inequality holds/
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
-- Do the episodes' n_bags add up to the number of bags, per product? Is any
-- n_bags below 1? Print true/false.

-- Q: For each product, does the total of n_bags across episodes equal the
--    number of bags? Does every episode have an n_bags of at least 1? Report
--    both checks as true or false.
-- A: yes, equality holds. Every episode has n_bags=>1.
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

-- note that `summarize episodes;` in cli answers if any n_bags<1 and min=1.

-- Step 4: episodes per day, first attempt ---------------------------------------
-- Count episodes per product per calendar day of episode_start. Fill in days
-- with no episodes as 0, from the first date in the data to the last
-- (pattern 12). Then take the mean per product.

-- Q: From the first date to the last, how many days does your calendar span,
--    and how many years is that? Is that a believable length of time for one
--    hospital's records? What mean episodes per day did you get per product?
-- A: 30149 days, about 82.5 years. Not believable: the shifted dates spread
--    across the 2110s to 2190s. Mean per day: plasma 0.22, platelets 0.15,
--    rbc 0.41.
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
-- Reread the field guide's notes on dates, and look at patients.anchor_year_group.
-- Work out how many real days the data covers, then compute episodes per day.

-- Q: How many real days does the data cover, and how did you work that out?
--    Can the mean from step 4 be used as episodes per day? Explain why or why
--    not. What episodes per day do you get per product using the real days?
-- A: 4383 real days (2008-01-01 to 2019-12-31, exactly 12 years). The four
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

-- Q: For each product, do all seven days of the week have about the same number
--    of episodes? If not, which days stand out? Why can you trust the day of
--    the week here when you couldn't trust the calendar in step 4?
-- A: No. Weekends are low for all three: Saturday about 10% and Sunday about
--    15-20% below the weekday average. Weekdays are within about 5% of each
--    other. The date shift changes each patient's year but keeps the real day
--    of the week, so weekday counts survive it. Step 4's calendar length
--    doesn't.

select
    product,
    dayname(episode_start) as day,
    count(*) as n_episodes
from episodes
group by product, dayname(episode_start), isodow(episode_start)
order by product, isodow(episode_start);

-- Step 7: per stay --------------------------------------------------------------
-- From stay_bags, per product: the share of stays with at least one bag, and
-- the mean and var_samp of n_bags among those stays only (patterns 5, 6).

-- Q: Which product or products do most stays never receive, meaning fewer than
--    half of stays have at least one bag? Among stays with at least one bag,
--    is the variance of n_bags above the mean for each product?
-- A: All three (share_any: plasma 0.11, platelets 0.06, rbc 0.20).
--    Variance above mean only for platelets (var/mean: plasma 0.69,
--    platelets 1.94, rbc 0.82).

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
