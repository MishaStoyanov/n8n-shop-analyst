-- Deterministic synthetic data: same rows on every fresh start.
SELECT setseed(0.42);

INSERT INTO categories (name) VALUES
    ('Coffee'), ('Tea'), ('Brewing gear'), ('Mugs & cups'), ('Snacks'), ('Gift sets');

INSERT INTO products (sku, name, category_id, price, is_active)
SELECT 'SKU-' || LPAD(g::TEXT, 4, '0'),
       (ARRAY['Ethiopia Yirgacheffe', 'Colombia Huila', 'Kenya AA', 'Brazil Santos', 'Guatemala Antigua',
              'Sencha', 'Earl Grey', 'Oolong', 'Rooibos', 'Matcha',
              'V60 Dripper', 'French Press', 'Moka Pot', 'Hand Grinder', 'Gooseneck Kettle',
              'Ceramic Mug', 'Glass Cup', 'Travel Mug', 'Espresso Cup', 'Tea Bowl',
              'Almond Biscotti', 'Dark Chocolate', 'Granola Bar', 'Cantucci', 'Shortbread',
              'Morning Kit', 'Tea Lover Box', 'Barista Starter', 'Office Pack', 'Holiday Box'])[g],
       ((g - 1) / 5) + 1,
       ROUND((CASE (g - 1) / 5
                WHEN 0 THEN 12 + random() * 10
                WHEN 1 THEN 6 + random() * 12
                WHEN 2 THEN 25 + random() * 60
                WHEN 3 THEN 8 + random() * 15
                WHEN 4 THEN 3 + random() * 6
                ELSE 35 + random() * 40 END)::NUMERIC, 2),
       g NOT IN (9, 24)
FROM generate_series(1, 30) g;

INSERT INTO customers (full_name, email, country, city, signed_up)
SELECT f || ' ' || l,
       LOWER(f) || '.' || LOWER(l) || g || '@example.com',
       CASE WHEN random() < 0.04 THEN NULL ELSE c.country END,
       c.city,
       DATE '2024-01-01' + (random() * 650)::INT
FROM generate_series(1, 400) g
CROSS JOIN LATERAL (SELECT (ARRAY['Anna', 'Ben', 'Chloe', 'Daniel', 'Emma', 'Felix', 'Grace', 'Hugo', 'Ivy', 'Jonas',
                                  'Klara', 'Leo', 'Mia', 'Noah', 'Olga', 'Paul', 'Rosa', 'Sam', 'Tara', 'Victor'])[1 + (random() * 19)::INT] AS f,
                           (ARRAY['Smith', 'Novak', 'Muller', 'Rossi', 'Garcia', 'Kowalski', 'Dubois', 'Jensen', 'Silva', 'Kim',
                                  'Brown', 'Weber', 'Costa', 'Nagy', 'Ivanova'])[1 + (random() * 14)::INT] AS l,
                           (random() * 7)::INT AS ci) n
CROSS JOIN LATERAL (SELECT (ARRAY['Germany', 'Poland', 'France', 'Italy', 'Spain', 'Netherlands', 'Ukraine', 'Czechia'])[n.ci + 1] AS country,
                           (ARRAY['Berlin', 'Warsaw', 'Lyon', 'Milan', 'Valencia', 'Utrecht', 'Kyiv', 'Brno'])[n.ci + 1] AS city) c;

INSERT INTO orders (customer_id, ordered_at, status, channel)
SELECT 1 + (random() * 399)::INT,
       TIMESTAMP '2025-01-01' + (random() * 690) * INTERVAL '1 day' + (random() * 86400) * INTERVAL '1 second',
       CASE WHEN r < 0.06 THEN 'refunded' WHEN r < 0.10 THEN 'cancelled' WHEN r < 0.20 THEN 'paid'
            WHEN r < 0.35 THEN 'shipped' ELSE 'delivered' END,
       CASE WHEN random() < 0.55 THEN 'web' WHEN random() < 0.7 THEN 'mobile' ELSE 'marketplace' END
FROM (SELECT random() AS r FROM generate_series(1, 3000)) s;

INSERT INTO order_items (order_id, product_id, quantity, unit_price)
SELECT o.id, p.id, 1 + (random() * 2)::INT,
       ROUND(p.price * (CASE WHEN random() < 0.2 THEN 0.85 ELSE 1 END), 2)
FROM orders o
CROSS JOIN LATERAL generate_series(1, 1 + ((random() + o.id * 0) * 3)::INT) k  -- o.id forces a new count per order
CROSS JOIN LATERAL (SELECT id, price FROM products WHERE k > 0 ORDER BY random() LIMIT 1) p;

INSERT INTO reviews (product_id, customer_id, rating, created_at)
SELECT DISTINCT ON (oi.product_id, o.customer_id)
       oi.product_id, o.customer_id,
       LEAST(5, GREATEST(1, ROUND(3.9 + random() * 2 - 1.2 * (oi.product_id % 7 = 0)::INT)))::INT,
       (o.ordered_at + INTERVAL '10 days')::DATE
FROM order_items oi
JOIN orders o ON o.id = oi.order_id
WHERE o.status = 'delivered' AND random() < 0.25;
