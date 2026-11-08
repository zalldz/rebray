"""Stage-2 sanity test: tool pages, custom cart items, options in orders, schema migration.
Run: python test_tools.py"""
import json, os, re, sqlite3, tempfile

DB = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ["BRAY3D_DB"] = DB
os.environ["SECRET_KEY"] = "test"
os.environ.pop("TELEGRAM_BOT_TOKEN", None)

# Stage-1 schema with existing data: migration must keep it.
old = sqlite3.connect(DB)
old.executescript("""
CREATE TABLE cart_items(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, product_id INTEGER NOT NULL,
  qty INTEGER NOT NULL DEFAULT 1, UNIQUE(user_id, product_id));
CREATE TABLE order_items(id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL, product_id INTEGER NOT NULL,
  qty INTEGER NOT NULL, price_idr INTEGER NOT NULL);
INSERT INTO cart_items(user_id, product_id, qty) VALUES (999, 2, 3);
INSERT INTO order_items(order_id, product_id, qty, price_idr) VALUES (77, 2, 1, 25000);
""")
old.commit(); old.close()

from app import app, init_db  # noqa: E402  (import runs init_db -> migration)
init_db()  # second run must be a no-op

db = sqlite3.connect(DB)
assert db.execute("SELECT qty, options FROM cart_items WHERE user_id=999").fetchone() == (3, "")
assert db.execute("SELECT qty, options FROM order_items WHERE order_id=77").fetchone() == (1, None)
db.execute("DELETE FROM cart_items WHERE user_id=999"); db.execute("DELETE FROM order_items"); db.commit()
print("migration: ok")

c = app.test_client()


def csrf():
    return re.search(r'name="csrf" value="([^"]+)"', c.get("/login").text).group(1)


home = c.get("/").text
for slug in ["gantungan-kunci", "clicker", "lithophane"]:
    r = c.get(f"/tools/{slug}")
    assert r.status_code == 200 and "<canvas" in r.text and "tools.js" in r.text, slug
    assert f'href="/tools/{slug}"' in home, slug  # landing card + nav
assert c.get("/tools/case-organizer").status_code == 404
assert "cdn" not in c.get("/static/tools.js").text.lower()
print("tool pages: ok")

t = csrf()
c.post("/register", data={"csrf": t, "name": "Boo", "email": "boo@x.id", "password": "rahasia123"})
t = csrf()

key = {"tool": "gantungan-kunci", "nama": "BOO", "bentuk": "hati", "warna": "hijau"}
r = c.post("/cart/add/gantungan-kunci", data={"csrf": t, "options": json.dumps(key)})
assert r.status_code == 302 and r.location.endswith("/cart"), r.location
c.post("/cart/add/gantungan-kunci", data={"csrf": t, "options": json.dumps(dict(reversed(key.items())))})  # same design
assert c.post("/cart/add/gantungan-kunci", data={"csrf": t}).location.endswith("/shop/gantungan-kunci")  # ready stock

for bad in [dict(key, nama=""), dict(key, nama="X" * 21), dict(key, warna="ungu"), dict(key, tool="clicker"), "nope"]:
    r = c.post("/cart/add/gantungan-kunci", data={"csrf": t, "options": json.dumps(bad)})
    assert r.status_code == 302 and r.location.endswith("/tools/gantungan-kunci"), bad
assert c.post("/cart/add/lithophane", data={"csrf": t, "options": json.dumps(
    {"tool": "lithophane", "ukuran": "15cm", "bentuk": "oval", "thumb": "javascript:alert(1)"})}).location.endswith("/tools/lithophane")

thumb = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQ=="
c.post("/cart/add/clicker", data={"csrf": t, "options": json.dumps(
    {"tool": "clicker", "model": "clicky", "body": "hitam", "aksen": "hijau"})})
c.post("/cart/add/lithophane", data={"csrf": t, "options": json.dumps(
    {"tool": "lithophane", "ukuran": "15cm", "bentuk": "oval", "thumb": thumb})})

cart = c.get("/cart").text
assert "nama &#34;BOO&#34;, bentuk hati, warna hijau" in cart, cart
assert "model clicky, body hitam, aksen hijau" in cart
assert f'src="{thumb}"' in cart and "ukuran 15cm, bentuk oval" in cart
rows = db.execute("SELECT qty, options FROM cart_items ORDER BY id").fetchall()
assert [q for q, _ in rows] == [2, 1, 1], rows  # identical designs merged
assert 'class="badge">4<' in cart
print("cart: ok")

r = c.post("/checkout", data={"csrf": t})
oid = int(r.location.rsplit("/", 1)[1])
items = db.execute("SELECT qty, price_idr, options FROM order_items WHERE order_id=? ORDER BY id", (oid,)).fetchall()
assert len(items) == 3
assert json.loads(items[0][2]) == key and items[0][0] == 2
assert json.loads(items[2][2])["thumb"] == thumb
total = db.execute("SELECT total_idr FROM orders WHERE id=?", (oid,)).fetchone()[0]
assert total == 2 * 15000 + 25000 + 45000, total
page = c.get(f"/orders/{oid}").text
assert "nama &#34;BOO&#34;" in page and f'src="{thumb}"' in page
from urllib.parse import unquote  # noqa: E402
msg = unquote(re.search(r'href="https://wa\.me/\d+\?text=([^"]+)"', page).group(1))
assert 'nama "BOO", bentuk hati, warna hijau) x2' in msg and "base64" not in msg, msg  # options yes, thumb no
print(f"checkout: ok (order #{oid}, {len(items)} items)")
print("OK")
