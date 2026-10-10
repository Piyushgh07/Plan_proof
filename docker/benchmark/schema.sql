CREATE TABLE users (
    id BIGINT PRIMARY KEY,
    email TEXT NOT NULL,
    country TEXT NOT NULL,
    is_active BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    category TEXT NOT NULL,
    name TEXT NOT NULL,
    price NUMERIC(12, 2) NOT NULL,
    stock_quantity INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    status TEXT NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE order_items (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(id),
    product_id BIGINT NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL
);

CREATE TABLE events (
    id BIGINT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    event_type TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    payload JSONB
);
-- Baseline indexes.
-- These represent indexes that already exist before Plan Proof runs.

CREATE INDEX products_category_idx
    ON products(category);

CREATE INDEX products_created_at_idx
    ON products(created_at);

CREATE INDEX orders_created_at_idx
    ON orders(created_at);

CREATE INDEX orders_status_created_at_idx
    ON orders(status, created_at);

CREATE INDEX order_items_product_id_idx
    ON order_items(product_id);

CREATE INDEX events_occurred_at_idx
    ON events(occurred_at);

CREATE INDEX events_event_type_idx
    ON events(event_type);
    