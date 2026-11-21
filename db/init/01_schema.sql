-- Demo online shop: customers buy products in orders; reviews and refunds add a bit of realism.
CREATE TABLE categories (
    id   SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE products (
    id          SERIAL PRIMARY KEY,
    sku         TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    category_id INT  NOT NULL REFERENCES categories (id),
    price       NUMERIC(10, 2) NOT NULL CHECK (price > 0),
    is_active   BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE customers (
    id         SERIAL PRIMARY KEY,
    full_name  TEXT NOT NULL,
    email      TEXT NOT NULL UNIQUE,
    country    TEXT,
    city       TEXT,
    signed_up  DATE NOT NULL
);

CREATE TABLE orders (
    id          SERIAL PRIMARY KEY,
    customer_id INT  NOT NULL REFERENCES customers (id),
    ordered_at  TIMESTAMP NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('paid', 'shipped', 'delivered', 'refunded', 'cancelled')),
    channel     TEXT NOT NULL CHECK (channel IN ('web', 'mobile', 'marketplace'))
);

CREATE TABLE order_items (
    id         SERIAL PRIMARY KEY,
    order_id   INT NOT NULL REFERENCES orders (id),
    product_id INT NOT NULL REFERENCES products (id),
    quantity   INT NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(10, 2) NOT NULL
);

CREATE TABLE reviews (
    id          SERIAL PRIMARY KEY,
    product_id  INT NOT NULL REFERENCES products (id),
    customer_id INT NOT NULL REFERENCES customers (id),
    rating      INT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    created_at  DATE NOT NULL
);

COMMENT ON TABLE orders IS 'One purchase. Revenue counts only paid, shipped and delivered orders.';
COMMENT ON COLUMN order_items.unit_price IS 'Price at the moment of purchase, may differ from products.price.';

-- Revenue per order, so the agent does not have to rebuild the join every time.
CREATE VIEW order_totals AS
SELECT o.id AS order_id, o.customer_id, o.ordered_at, o.status, o.channel,
       SUM(oi.quantity * oi.unit_price)::NUMERIC(12, 2) AS total
FROM orders o
JOIN order_items oi ON oi.order_id = o.id
GROUP BY o.id;
