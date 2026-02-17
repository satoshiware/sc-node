PRAGMA foreign_keys = ON;

CREATE TABLE "orders" (
	id INTEGER PRIMARY KEY,
	side TEXT NOT NULL CHECK (side IN ('buy','sell')),
	type TEXT NOT NULL CHECK (type IN ('limit','market')),
	price NUMERIC,
	quantity NUMERIC NOT NULL,
	remaining_quantity NUMERIC NOT NULL,
	status TEXT NOT NULL CHECK (status IN ('open','filled','cancelled')),
	created_at DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE trades (
	id INTEGER PRIMARY KEY,
	buy_order_id INTEGER NOT NULL REFERENCES "orders"(id),
	sell_order_id INTEGER NOT NULL REFERENCES "orders"(id),
	price NUMERIC NOT NULL,
	quantity NUMERIC NOT NULL,
	executed_at DATETIME NOT NULL DEFAULT (datetime('now'))
);
