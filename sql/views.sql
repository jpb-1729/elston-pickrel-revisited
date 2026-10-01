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
