CREATE OR REPLACE VIEW my_view AS
SELECT
    itemid,
    label AS product,
    unitname AS amountuom
FROM d_items
WHERE label IN ('Platelets', 'Packed Red Blood Cells', 'Fresh Frozen Plasma');

SELECT *
FROM my_view;
