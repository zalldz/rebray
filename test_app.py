"""Smoke test: register -> cart -> checkout -> orders. Run: python test_app.py"""
import json, os, re, sqlite3, tempfile

os.environ["BRAY3D_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ["SECRET_KEY"] = "test"
os.environ["BRAY3D_UPLOADS"] = tempfile.mkdtemp()
os.environ.pop("TELEGRAM_BOT_TOKEN", None)
from app import app  # noqa: E402

c = app.test_client()


def csrf():
    return re.search(r'name="csrf" value="([^"]+)"', c.get("/login").text).group(1)


for path in ["/", "/shop", "/shop/clicker", "/login", "/register"]:
    assert c.get(path).status_code == 200, path
home = c.get("/").text
assert "REBRAY" in home and "Bray3D" not in home and "Dari Sisa jadi Berguna" in home and "Lihat Produk" in home
assert 'id="burger"' in home and 'aria-controls="navlinks"' in home
assert "Rp25.000" in c.get("/shop").text and "Harga menyesuaikan" in c.get("/shop").text
assert c.get("/shop/nope").status_code == 404

# stage 4: quote page + ready-stock -> marketplace
q = c.get("/quote")
assert q.status_code == 200 and "price_per_gram" in q.text and "quote.js" in q.text and "Hitung Harga Cetak" in q.text
assert '"price_per_gram_idr": 1500' in q.text and '"min_price_idr": 25000' in q.text and "6282299130985" in q.text
for path in ["/", "/shop"]:
    assert 'href="/quote"' in c.get(path).text, path  # nav + landing card / shop banner
assert "Hitung Harga Cetak →" in home
pg = c.get("/shop/clicker").text
assert 'href="https://www.tokopedia.com/rebray" target="_blank"' in pg and "Beli di Marketplace" in pg
assert 'action="/cart/add/clicker"' not in pg and "Tambah ke Keranjang" not in pg and 'href="/tools/clicker"' in pg
assert c.get("/shop").text.count("Beli di Marketplace") == 4
assert c.get("/cart").status_code == 302  # login required
assert c.post("/cart/add/clicker").status_code == 400  # no csrf

t = csrf()
r = c.post("/register", data={"csrf": t, "name": "Budi", "email": "b@x.id", "password": "rahasia123"})
assert r.status_code == 302
t = csrf()  # token rotates on login
r = c.post("/cart/add/clicker", data={"csrf": t})  # ready stock: not addable
assert r.location.endswith("/shop/clicker") and "marketplace" in c.get(r.location).text
assert "badge" not in c.get("/shop").text
CK = json.dumps({"tool": "clicker", "model": "clicky", "body": "hitam", "aksen": "hijau"})
GK = json.dumps({"tool": "gantungan-kunci", "nama": "BUDI", "bentuk": "bulat", "warna": "hijau"})
c.post("/cart/add/clicker", data={"csrf": t, "options": CK})  # designed = custom: allowed
c.post("/cart/add/clicker", data={"csrf": t, "options": CK})
c.post("/cart/add/gantungan-kunci", data={"csrf": t, "options": GK})
assert 'class="badge">3<' in c.get("/shop").text
ids = re.findall(r'/cart/update/(\d+)', c.get("/cart").text)[::2]  # two forms per row
c.post("/cart/update/999", data={"csrf": t, "action": "inc"})  # no such cart item: no-op
c.post(f"/cart/update/{ids[1]}", data={"csrf": t, "action": "dec"})  # gantungan-kunci qty 1 -> removed
assert "Rp50.000" in c.get("/cart").text  # 2 x clicker

r = c.post("/checkout", data={"csrf": t})
assert r.status_code == 302 and r.location.endswith("/orders/1"), r.location
page = c.get("/orders/1").text
assert "Rp50.000" in page and "Menunggu" in page
from urllib.parse import unquote  # noqa: E402
wa = re.search(r'href="(https://wa\.me/6282299130985\?text=[^"]+)"', page).group(1)
msg = unquote(wa.split("text=", 1)[1])
assert "pesanan #1" in msg and "Nama: Budi" in msg and "- Clicker Fidget (model clicky, body hitam, aksen hijau) x2 = Rp50.000" in msg and "Total: Rp50.000" in msg, msg
assert "Lanjut Pembayaran via WhatsApp" in page
assert "kosong" in c.get("/cart").text

c.post("/cart/add/case-organizer", data={"csrf": t})
assert "kosong" in c.get("/cart").text  # ready stock, no tool -> never in cart
db = sqlite3.connect(os.environ["BRAY3D_DB"])  # turn it into a custom item to cover the quote-project path
db.execute("UPDATE products SET is_ready_stock=0 WHERE slug='case-organizer'"); db.commit()
assert 'action="/cart/add/case-organizer"' in c.get("/shop/case-organizer").text
c.post("/cart/add/case-organizer", data={"csrf": t})
c.post("/checkout", data={"csrf": t})
assert "Menunggu Quote" in c.get("/orders/2").text
assert c.get("/orders").text.count("/orders/") >= 2

# another user cannot see Budi's order
c.post("/logout", data={"csrf": t})
t = csrf()
c.post("/register", data={"csrf": t, "name": "Ani", "email": "a@x.id", "password": "rahasia123"})
t = csrf()
assert c.get("/orders/1").status_code == 404
c.post("/logout", data={"csrf": t})
t = csrf()
assert "salah" in c.post("/login", data={"csrf": t, "email": "b@x.id", "password": "wrong"}).text
assert c.post("/login", data={"csrf": t, "email": "b@x.id", "password": "rahasia123"}).status_code == 302

# stage 5: admin — hidden from non-admins
t = csrf()
assert c.get("/admin").status_code == 404
assert c.post("/admin/orders/1/status", data={"csrf": t, "new_status": "paid"}).status_code == 404
assert c.post("/admin/settings", data={"csrf": t}).status_code == 404
assert c.post("/admin/products/1", data={"csrf": t, "price_idr": "1"}).status_code == 404
assert c.post("/admin/products/new", data={"csrf": t}).status_code == 404
assert c.post("/admin/content", data={"csrf": t}).status_code == 404
assert c.post("/admin/users/1/admin", data={"csrf": t, "is_admin": "1"}).status_code == 404
assert 'href="/admin"' not in c.get("/shop").text
c.post("/logout", data={"csrf": t})
assert c.get("/admin").status_code == 404  # logged out: 404 too, not a login redirect

from werkzeug.security import generate_password_hash  # noqa: E402
db.execute("INSERT INTO users(email, password_hash, name, is_admin) VALUES (?,?,?,1)",
           ("admin@x.id", generate_password_hash("rahasia123"), "Admin")); db.commit()
t = csrf()
c.post("/login", data={"csrf": t, "email": "admin@x.id", "password": "rahasia123"})
t = csrf()
a = c.get("/admin")
assert a.status_code == 200 and 'href="/admin"' in a.text and "Dashboard" in a.text
assert "Clicker Fidget" in a.text and "b@x.id" in a.text and "Rp0" in a.text  # paid revenue still 0
assert c.post("/admin/orders/1/status", data={"new_status": "paid"}).status_code == 400  # no csrf
assert c.post("/admin/orders/1/status", data={"csrf": t, "new_status": "hacked"}).status_code == 400
r = c.post("/admin/orders/1/status", data={"csrf": t, "new_status": "paid", "status": "pending"})
assert r.status_code == 302 and "status=pending" in r.location
assert db.execute("SELECT status FROM orders WHERE id=1").fetchone()[0] == "paid"
assert "Lunas" in c.get("/orders/1").text
a = c.get("/admin").text
assert "Rp50.000" in a and '<option value="paid" selected>' in a
assert "#1<" in c.get("/admin?status=paid").text and "#2<" not in c.get("/admin?status=paid").text
assert "#2<" in c.get("/admin?q=2").text and "#1<" not in c.get("/admin?q=2").text
assert "#1<" in c.get("/admin?q=b@x").text and "#1<" not in c.get("/admin?q=a@x").text

c.post("/admin/settings", data={"csrf": t, "price_per_gram_idr": "2000", "min_price_idr": "30000",
                                "wa_number": "6281111111111", "shipping_note": "Ongkir via JNE."})
assert '"price_per_gram_idr": 2000' in c.get("/quote").text and "Ongkir via JNE." in c.get("/quote").text
assert "Harga harus angka" in c.post("/admin/settings", data={"csrf": t, "price_per_gram_idr": "abc", "min_price_idr": "1",
                                     "wa_number": "6281111111111", "shipping_note": "x"}, follow_redirects=True).text
assert db.execute("SELECT value FROM settings WHERE key='price_per_gram_idr'").fetchone()[0] == "2000"  # bad input ignored

cid = db.execute("SELECT id FROM products WHERE slug='clicker'").fetchone()[0]
pf = {"csrf": t, "name": "Clicker Fidget", "emoji": "🔷", "description": "d", "active": "1"}
c.post(f"/admin/products/{cid}", data={**pf, "price_idr": "27000", "marketplace_url": "javascript:alert(1)", "is_ready_stock": "1"})
assert db.execute("SELECT price_idr FROM products WHERE id=?", (cid,)).fetchone()[0] == 25000  # rejected
c.post(f"/admin/products/{cid}", data={**pf, "name": "", "price_idr": "1"})
assert db.execute("SELECT price_idr FROM products WHERE id=?", (cid,)).fetchone()[0] == 25000  # empty name rejected
c.post(f"/admin/products/{cid}", data={**pf, "name": "Clicker Pro", "price_idr": "27000", "marketplace_url": "https://shopee.co.id/x"})
assert db.execute("SELECT name, price_idr, is_ready_stock, marketplace_url FROM products WHERE id=?", (cid,)).fetchone() \
    == ("Clicker Pro", 27000, 0, "https://shopee.co.id/x")
assert 'action="/cart/add/clicker"' in c.get("/shop/clicker").text  # no longer ready stock
c.post(f"/admin/products/{cid}", data={**pf, "price_idr": "27000", "active": ""})  # hide
assert c.get("/shop/clicker").status_code == 404 and "/shop/clicker" not in c.get("/shop").text
c.post(f"/admin/products/{cid}", data={**pf, "price_idr": "27000"})
# new product: slug derived from name, unique
for _ in range(2):
    c.post("/admin/products/new", data={**pf, "name": "Vas Bunga!", "emoji": "🌸", "price_idr": "30000"})
assert c.get("/shop/vas-bunga").status_code == 200 and c.get("/shop/vas-bunga-2").status_code == 200
# photo + 3D model upload: validated by content, old file deleted on replace
import io, struct
up = os.environ["BRAY3D_UPLOADS"]
stl = b"\0" * 80 + struct.pack("<I", 1) + b"\0" * 50
png = b"\x89PNG\r\n\x1a\n" + b"\0" * 20
def upl(**files):
    return c.post(f"/admin/products/{cid}", data={**pf, "price_idr": "27000",
                  **{k: (io.BytesIO(v), n) for k, (v, n) in files.items()}}, content_type="multipart/form-data", follow_redirects=True)
assert "Foto harus" in upl(photo=(b"<svg onload=alert(1)>", "x.png")).text
assert "Model 3D harus" in upl(model=(b"not an stl at all" * 10, "x.stl")).text
assert db.execute("SELECT photo, model FROM products WHERE id=?", (cid,)).fetchone() == (None, None)
upl(photo=(png, "a.png"), model=(stl, "m.stl"))
photo, model = db.execute("SELECT photo, model FROM products WHERE id=?", (cid,)).fetchone()
assert photo.endswith(".png") and model.endswith(".stl") and sorted(os.listdir(up)) == sorted([photo, model])
assert c.get(f"/media/{model}").data == stl and c.get("/media/../app.py").status_code == 404
pg = c.get("/shop/clicker").text
assert f'data-model="/media/{model}"' in pg and "viewer3d.js" in pg and f'src="/media/{photo}"' in pg
assert "🧊 3D" in c.get("/shop").text
upl(photo=(png + b"x", "b.png"))  # replace: old photo removed
assert photo not in os.listdir(up) and len(os.listdir(up)) == 2
c.post(f"/admin/products/{cid}", data={**pf, "price_idr": "27000", "remove_photo": "1", "remove_model": "1"})
assert db.execute("SELECT photo, model FROM products WHERE id=?", (cid,)).fetchone() == (None, None) and os.listdir(up) == []
assert "viewer3d.js" not in c.get("/shop/clicker").text
# site content
from db import SITE_TEXTS
content = {"csrf": t, **{k: v for k, (_l, v) in SITE_TEXTS.items()}}
c.post("/admin/content", data={**content, "hero_title": "Judul <b>Baru</b>", "philosophy_text": "P1\r\n\r\nP2"})
home = c.get("/").text
assert "Judul &lt;b&gt;Baru&lt;/b&gt;" in home and "<p class=\"lead\">P1</p><p class=\"lead\">P2</p>" in home
assert "Wajib diisi" in c.post("/admin/content", data={**content, "hero_sub": ""}, follow_redirects=True).text
assert "Email kontak" in c.post("/admin/content", data={**content, "contact_email": "x"}, follow_redirects=True).text
# user role: can't demote self, can promote others
me = db.execute("SELECT id FROM users WHERE email='admin@x.id'").fetchone()[0]
c.post(f"/admin/users/{me}/admin", data={"csrf": t, "is_admin": "0"})
assert db.execute("SELECT is_admin FROM users WHERE id=?", (me,)).fetchone()[0] == 1
other = db.execute("SELECT id FROM users WHERE email!='admin@x.id'").fetchone()[0]
c.post(f"/admin/users/{other}/admin", data={"csrf": t, "is_admin": "1"})
assert db.execute("SELECT is_admin FROM users WHERE id=?", (other,)).fetchone()[0] == 1
c.post(f"/admin/users/{other}/admin", data={"csrf": t, "is_admin": "0"})
assert c.get("/admin").status_code == 200

# ADMIN_EMAIL auto-promote on register
c.post("/logout", data={"csrf": t})
os.environ["ADMIN_EMAIL"] = "Boss@X.id"
t = csrf()
c.post("/register", data={"csrf": t, "name": "Boss", "email": "boss@x.id", "password": "rahasia123"})
assert c.get("/admin").status_code == 200
print("OK")
