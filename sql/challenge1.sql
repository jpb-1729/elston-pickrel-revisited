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

SELECT *
FROM product_map
ORDER BY itemid;
