-- db/init/01-esquema.sql — esquema de la tienda (se ejecuta una sola vez, al crear el volumen).
-- Montado en /docker-entrypoint-initdb.d/ del contenedor postgres (solo lectura).

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- digest() para las contraseñas de prueba
CREATE EXTENSION IF NOT EXISTS pg_trgm;    -- índice para búsquedas ILIKE '%texto%'

CREATE TABLE products (
    id          SERIAL PRIMARY KEY,
    sku         TEXT        NOT NULL UNIQUE,
    name        TEXT        NOT NULL,
    category    TEXT        NOT NULL,
    price       NUMERIC(10,2) NOT NULL CHECK (price >= 0),
    stock       INTEGER     NOT NULL CHECK (stock >= 0),
    description TEXT        NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX products_category_idx ON products (category);
CREATE INDEX products_name_trgm_idx ON products USING gin (name gin_trgm_ops);

CREATE TABLE users (
    id        SERIAL PRIMARY KEY,
    username  TEXT NOT NULL UNIQUE,
    salt      TEXT NOT NULL,
    -- SHA-256(salt || contraseña) en hexadecimal. Suficiente para un entorno de pruebas;
    -- en producción se usaría scrypt/argon2 (documentado en el README).
    pass_hash TEXT NOT NULL
);

CREATE TABLE orders (
    id         BIGSERIAL PRIMARY KEY,
    user_id    INTEGER     NOT NULL REFERENCES users(id),
    total      NUMERIC(12,2) NOT NULL,
    items      INTEGER     NOT NULL,
    node       TEXT        NOT NULL,      -- réplica del backend que procesó el pedido
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX orders_user_idx ON orders (user_id, created_at DESC);
CREATE INDEX orders_created_idx ON orders (created_at);

CREATE TABLE order_items (
    order_id   BIGINT  NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id),
    qty        INTEGER NOT NULL CHECK (qty > 0),
    price      NUMERIC(10,2) NOT NULL,
    PRIMARY KEY (order_id, product_id)
);
