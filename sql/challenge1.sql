-- Challenge 1: build a product mapping table
-- The view itself lives in sql/views.sql.
.read sql/views.sql

SELECT *
FROM product_map
ORDER BY itemid;
