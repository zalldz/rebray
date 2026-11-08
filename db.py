import os
import sqlite3

from flask import g

DB_PATH = os.environ.get("BRAY3D_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "bray3d.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  name TEXT NOT NULL,
  is_admin INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS products(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  emoji TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  price_idr INTEGER NOT NULL DEFAULT 0,
  active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS cart_items(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  product_id INTEGER NOT NULL REFERENCES products(id),
  qty INTEGER NOT NULL DEFAULT 1,
  options TEXT NOT NULL DEFAULT '',
  UNIQUE(user_id, product_id, options));
CREATE TABLE IF NOT EXISTS orders(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  total_idr INTEGER NOT NULL,
  status TEXT DEFAULT 'pending',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS order_items(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id INTEGER NOT NULL REFERENCES orders(id),
  product_id INTEGER NOT NULL REFERENCES products(id),
  qty INTEGER NOT NULL,
  price_idr INTEGER NOT NULL,
  options TEXT);
CREATE TABLE IF NOT EXISTS settings(
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL);
"""

# Stage-1 DBs: cart_items needs a table rebuild because the UNIQUE key changes.
MIGRATE_CART = """
PRAGMA foreign_keys = OFF;
BEGIN;
CREATE TABLE cart_items_new(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  product_id INTEGER NOT NULL REFERENCES products(id),
  qty INTEGER NOT NULL DEFAULT 1,
  options TEXT NOT NULL DEFAULT '',
  UNIQUE(user_id, product_id, options));
INSERT INTO cart_items_new(id, user_id, product_id, qty) SELECT id, user_id, product_id, qty FROM cart_items;
DROP TABLE cart_items;
ALTER TABLE cart_items_new RENAME TO cart_items;
COMMIT;
PRAGMA foreign_keys = ON;
"""

SEED = [
    ("gantungan-kunci", "Gantungan Kunci Custom", "🔑", "Nama, logo, atau bentuk bebas. PLA solid, ringan & kuat.", 15000),
    ("clicker", "Clicker Fidget", "🔷", "Fidget toy presisi — mekanisme klik yang memuaskan.", 25000),
    ("lithophane", "Lithophane Foto", "🖼️", "Foto favorit jadi relief 3D — makin indah dengan cahaya.", 45000),
    ("case-organizer", "Case & Organizer", "📦", "Case alat, organizer meja, holder HP — ukuran custom.", 0),
]


# Ready-stock items are sold via marketplace, not the cart.
# shortcut: placeholder shop URLs, replace with real listing links when they exist.
MARKETPLACE = {
    "gantungan-kunci": "https://shopee.co.id/shop/rebray",
    "clicker": "https://www.tokopedia.com/rebray",
    "lithophane": "https://shopee.co.id/shop/rebray",
    "case-organizer": "https://www.tokopedia.com/rebray",
}


def default_settings():
    return {"price_per_gram_idr": "1500", "min_price_idr": "25000",
            "wa_number": os.environ.get("WHATSAPP_NUMBER", "6282299130985"),
            "shipping_note": "Belum termasuk ongkir — dihitung terpisah sesuai alamat pengiriman."}


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    if "db" not in g:
        g.db = connect()
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def columns(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def init_db():
    with connect() as conn:
        conn.executescript(SCHEMA)
        if "options" not in columns(conn, "order_items"):
            conn.execute("ALTER TABLE order_items ADD COLUMN options TEXT")
        if "options" not in columns(conn, "cart_items"):
            conn.executescript(MIGRATE_CART)
        if conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO products(slug, name, emoji, description, price_idr) VALUES (?,?,?,?,?)", SEED)
        if "is_ready_stock" not in columns(conn, "products"):
            conn.execute("ALTER TABLE products ADD COLUMN is_ready_stock INTEGER DEFAULT 0")
            conn.execute("ALTER TABLE products ADD COLUMN marketplace_url TEXT")
            conn.executemany("UPDATE products SET is_ready_stock=1, marketplace_url=? WHERE slug=?",
                             [(url, slug) for slug, url in MARKETPLACE.items()])
        # OR IGNORE: values edited in the DB survive restarts
        conn.executemany("INSERT OR IGNORE INTO settings(key, value) VALUES (?,?)", default_settings().items())
