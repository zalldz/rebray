import json
import os
import re
import secrets
import sqlite3
import threading
from functools import wraps
from urllib.parse import quote

from flask import Flask, abort, flash, g, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from db import SITE_TEXTS, close_db, get_db, init_db

APP_DIR = os.path.dirname(os.path.abspath(__file__))


def load_secret_key():
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    path = os.path.join(APP_DIR, ".secret_key")
    if not os.path.exists(path):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_hex(32))
    with open(path) as f:
        return f.read().strip()


app = Flask(__name__)
app.secret_key = load_secret_key()
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["MAX_CONTENT_LENGTH"] = 40 * 1024 * 1024  # STL upload ≤ 30 MB + form
UPLOAD_DIR = os.environ.get("BRAY3D_UPLOADS", os.path.join(APP_DIR, "uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.teardown_appcontext(close_db)
init_db()


def get_settings():
    return dict(get_db().execute("SELECT key, value FROM settings").fetchall())


@app.template_filter("rupiah")
def rupiah(n):
    return "Rp" + f"{n:,}".replace(",", ".")


# ── design tools: one source of truth for UI choices + server whitelist ──

PLA_COLORS = {"hitam": "#1f2229", "putih": "#eef0f3", "merah": "#e63946",
              "hijau": "#00c389", "biru": "#3a7bff", "kuning": "#ffc93c"}
TOOLS = {
    "gantungan-kunci": {"title": "Desain Gantungan Kunci",
                        "fields": {"bentuk": ("bulat", "kotak", "hati"), "warna": tuple(PLA_COLORS)}},
    "clicker": {"title": "Desain Clicker",
                "fields": {"model": ("slider", "switcher", "clicky"),
                           "body": tuple(PLA_COLORS), "aksen": tuple(PLA_COLORS)}},
    "lithophane": {"title": "Generator Lithophane",
                   "fields": {"ukuran": ("10cm", "15cm", "20cm"), "bentuk": ("persegi", "oval")}},
}
THUMB_RE = re.compile(r"data:image/jpeg;base64,[A-Za-z0-9+/]+={0,2}")


def clean_options(slug, raw):
    """Validate client-sent design JSON; return canonical JSON string or None."""
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get("tool") != slug:
        return None
    out = {"tool": slug}
    for key, allowed in TOOLS[slug]["fields"].items():
        if data.get(key) not in allowed:
            return None
        out[key] = data[key]
    if slug == "gantungan-kunci":
        nama = str(data.get("nama", "")).strip()
        if not (0 < len(nama) <= 20 and nama.isprintable()):
            return None
        out["nama"] = nama
    if slug == "lithophane":
        thumb = data.get("thumb", "")
        if not (isinstance(thumb, str) and len(thumb) <= 60000 and THUMB_RE.fullmatch(thumb)):
            return None
        out["thumb"] = thumb
    # canonical form so identical designs merge into one cart row
    return json.dumps(out, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


@app.template_filter("opts")
def parse_opts(raw):
    return json.loads(raw) if raw else None


@app.template_filter("opts_text")
def opts_text(o):
    parts = [f'nama "{o["nama"]}"'] if o.get("nama") else []
    parts += [f"{k} {o[k]}" for k in TOOLS[o["tool"]]["fields"]]
    return ", ".join(parts)


STATUS_LABELS = {"pending": "Menunggu", "paid": "Lunas", "printing": "Dicetak", "done": "Selesai",
                 "cancelled": "Dibatalkan", "pending-quote": "Menunggu Quote"}
ORDER_STATUSES = tuple(STATUS_LABELS)


# ── auth / csrf helpers ──

@app.before_request
def load_user_and_check_csrf():
    g.user = None
    if "user_id" in session:
        g.user = get_db().execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    if request.method == "POST":
        token = session.get("csrf")
        if not token or not secrets.compare_digest(token, request.form.get("csrf", "")):
            abort(400)


@app.context_processor
def inject_globals():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    cart_count = 0
    if g.get("user"):
        cart_count = get_db().execute(
            "SELECT COALESCE(SUM(qty),0) FROM cart_items WHERE user_id=?", (g.user["id"],)).fetchone()[0]
    site = get_settings()
    return {"csrf_token": session["csrf"], "cart_count": cart_count, "tools": TOOLS, "status_labels": STATUS_LABELS,
            "wa_number": site["wa_number"], "site": site}


def login_required(view):
    @wraps(view)
    def wrapped(*a, **kw):
        if g.user is None:
            flash("Silakan login dulu.", "error")
            return redirect(url_for("login", next=request.path))
        return view(*a, **kw)
    return wrapped


def safe_next():
    nxt = request.args.get("next", "")
    return nxt if nxt.startswith("/") and not nxt.startswith("//") else url_for("index")


# ── pages ──

def active_products():
    return get_db().execute("SELECT * FROM products WHERE active=1 ORDER BY id").fetchall()


@app.route("/")
def index():
    return render_template("index.html", products=active_products())


@app.route("/media/<name>")
def media(name):
    return send_from_directory(UPLOAD_DIR, name, max_age=86400)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        name = request.form.get("name", "").strip()
        pw = request.form.get("password", "")
        if not email or "@" not in email or not name:
            flash("Nama dan email wajib diisi dengan benar.", "error")
        elif len(pw) < 8:
            flash("Password minimal 8 karakter.", "error")
        else:
            db = get_db()
            is_admin = int(email == os.environ.get("ADMIN_EMAIL", "").strip().lower())
            try:
                with db:
                    cur = db.execute("INSERT INTO users(email, password_hash, name, is_admin) VALUES (?,?,?,?)",
                                     (email, generate_password_hash(pw), name, is_admin))
            except sqlite3.IntegrityError:
                flash("Email sudah terdaftar. Silakan login.", "error")
            else:
                session.clear()
                session["user_id"] = cur.lastrowid
                flash(f"Selamat datang, {name}! Akun berhasil dibuat.")
                return redirect(safe_next())
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = get_db().execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], request.form.get("password", "")):
            session.clear()
            session["user_id"] = user["id"]
            flash(f"Halo lagi, {user['name']}!")
            return redirect(safe_next())
        flash("Email atau password salah.", "error")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Kamu sudah logout.")
    return redirect(url_for("index"))


@app.route("/shop")
def shop():
    return render_template("shop.html", products=active_products())


@app.route("/shop/<slug>")
def product(slug):
    p = get_db().execute("SELECT * FROM products WHERE slug=? AND active=1", (slug,)).fetchone()
    if p is None:
        abort(404)
    return render_template("product.html", p=p, has_tool=slug in TOOLS)


@app.route("/tools/<slug>")
def tool(slug):
    if slug not in TOOLS:
        abort(404)
    p = get_db().execute("SELECT * FROM products WHERE slug=? AND active=1", (slug,)).fetchone()
    if p is None:
        abort(404)
    return render_template(f"tool_{slug.replace('-', '_')}.html", p=p, t=TOOLS[slug], colors=PLA_COLORS)


@app.route("/quote")
def quote_page():
    s = get_settings()
    cfg = {"price_per_gram_idr": int(s["price_per_gram_idr"]), "min_price_idr": int(s["min_price_idr"]),
           "wa_number": s["wa_number"]}
    return render_template("quote.html", cfg=cfg, shipping_note=s["shipping_note"])


# ── cart ──

def cart_rows(user_id):
    return get_db().execute(
        "SELECT c.id, c.product_id, c.qty, c.options, p.name, p.emoji, p.slug, p.price_idr "
        "FROM cart_items c JOIN products p ON p.id=c.product_id WHERE c.user_id=? ORDER BY c.id",
        (user_id,)).fetchall()


@app.route("/cart")
@login_required
def cart():
    items = cart_rows(g.user["id"])
    total = sum(i["qty"] * i["price_idr"] for i in items)
    has_quote = any(i["price_idr"] == 0 for i in items)
    return render_template("cart.html", items=items, total=total, has_quote=has_quote)


@app.route("/cart/add/<slug>", methods=["POST"])
@login_required
def cart_add(slug):
    db = get_db()
    p = db.execute("SELECT id, name, is_ready_stock FROM products WHERE slug=? AND active=1", (slug,)).fetchone()
    if p is None:
        abort(404)
    if p["is_ready_stock"] and "options" not in request.form:  # designed items are custom, stock is not
        flash("Produk ready stock dibeli lewat marketplace ya.", "error")
        return redirect(url_for("product", slug=slug))
    options = ""
    if "options" in request.form:
        if slug not in TOOLS or not (options := clean_options(slug, request.form["options"])):
            flash("Desain tidak valid, coba lagi.", "error")
            return redirect(url_for("tool", slug=slug) if slug in TOOLS else url_for("product", slug=slug))
    with db:
        db.execute("INSERT INTO cart_items(user_id, product_id, qty, options) VALUES (?,?,1,?) "
                   "ON CONFLICT(user_id, product_id, options) DO UPDATE SET qty=MIN(qty+1, 99)",
                   (g.user["id"], p["id"], options))
    flash(f"{p['name']} ditambahkan ke keranjang.")
    return redirect(url_for("cart"))


@app.route("/cart/update/<int:item_id>", methods=["POST"])
@login_required
def cart_update(item_id):
    delta = {"inc": 1, "dec": -1}.get(request.form.get("action"))
    if delta is None:
        abort(400)
    db = get_db()
    with db:
        db.execute("UPDATE cart_items SET qty=MIN(qty+?, 99) WHERE user_id=? AND id=?",
                   (delta, g.user["id"], item_id))
        db.execute("DELETE FROM cart_items WHERE user_id=? AND qty<=0", (g.user["id"],))
    return redirect(url_for("cart"))


@app.route("/cart/remove/<int:item_id>", methods=["POST"])
@login_required
def cart_remove(item_id):
    db = get_db()
    with db:
        db.execute("DELETE FROM cart_items WHERE user_id=? AND id=?", (g.user["id"], item_id))
    flash("Item dihapus dari keranjang.")
    return redirect(url_for("cart"))


# ── checkout / orders ──

def order_lines(items):
    """Plain-text item list shared by the Telegram notification and the WhatsApp message."""
    return "\n".join(f"- {i['name']}" + (f" ({opts_text(parse_opts(i['options']))})" if i["options"] else "")
                     + f" x{i['qty']} = "
                     + (rupiah(i['qty'] * i['price_idr']) if i['price_idr'] else "quote") for i in items)


def notify_telegram(text):
    token, chat_id = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat_id):
        return

    def send():
        try:
            import requests
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          data={"chat_id": chat_id, "text": text}, timeout=10)
        except Exception as e:  # notification must never break checkout
            app.logger.warning("Telegram notify gagal: %s", e)

    threading.Thread(target=send, daemon=True).start()


@app.route("/checkout", methods=["POST"])
@login_required
def checkout():
    uid = g.user["id"]
    items = cart_rows(uid)
    if not items:
        flash("Keranjang masih kosong.", "error")
        return redirect(url_for("cart"))
    total = sum(i["qty"] * i["price_idr"] for i in items)
    status = "pending-quote" if any(i["price_idr"] == 0 for i in items) else "pending"
    db = get_db()
    with db:  # one transaction: order + items + cart clear
        oid = db.execute("INSERT INTO orders(user_id, total_idr, status) VALUES (?,?,?)",
                         (uid, total, status)).lastrowid
        db.executemany("INSERT INTO order_items(order_id, product_id, qty, price_idr, options) VALUES (?,?,?,?,?)",
                       [(oid, i["product_id"], i["qty"], i["price_idr"], i["options"] or None) for i in items])
        db.execute("DELETE FROM cart_items WHERE user_id=?", (uid,))
    lines = order_lines(items)
    notify_telegram(f"🛒 Order baru #{oid} ({status})\n{g.user['name']} <{g.user['email']}>\n{lines}\n"
                    f"Total: {rupiah(total)}" + (" + quote" if status == "pending-quote" else ""))
    flash("Pesanan berhasil dibuat! Kami akan segera menghubungimu.")
    return redirect(url_for("order_detail", order_id=oid))


@app.route("/orders")
@login_required
def orders():
    rows = get_db().execute("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC", (g.user["id"],)).fetchall()
    return render_template("orders.html", orders=rows)


@app.route("/orders/<int:order_id>")
@login_required
def order_detail(order_id):
    db = get_db()
    order = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if order is None or (order["user_id"] != g.user["id"] and not g.user["is_admin"]):
        abort(404)
    items = db.execute(
        "SELECT oi.qty, oi.price_idr, oi.options, p.name, p.emoji, p.slug FROM order_items oi "
        "JOIN products p ON p.id=oi.product_id WHERE oi.order_id=? ORDER BY oi.id", (order_id,)).fetchall()
    name = db.execute("SELECT name FROM users WHERE id=?", (order["user_id"],)).fetchone()["name"]
    msg = (f"Halo REBRAY, saya mau lanjut pembayaran pesanan #{order['id']}\nNama: {name}\n"
           f"{order_lines(items)}\nTotal: {rupiah(order['total_idr'])}"
           + (" + quote" if order["status"] == "pending-quote" else ""))
    wa_url = f"https://wa.me/{get_settings()['wa_number']}?text={quote(msg)}"
    return render_template("order.html", order=order, items=items, wa_url=wa_url)


# ── admin ──

SETTING_KEYS = ("price_per_gram_idr", "min_price_idr", "wa_number", "shipping_note")


def admin_required(view):
    @wraps(view)
    def wrapped(*a, **kw):
        if g.user is None or not g.user["is_admin"]:
            abort(404)  # do not reveal that an admin area exists
        return view(*a, **kw)
    return wrapped


def back_to_admin(anchor):
    args = {k: v for k in ("status", "q") if (v := request.form.get(k))}
    return redirect(url_for("admin", **args) + anchor)


@app.route("/admin")
@admin_required
def admin():
    db = get_db()
    status = request.args.get("status", "")
    status = status if status in ORDER_STATUSES else ""
    q = request.args.get("q", "").strip()
    where, params = [], []
    if status:
        where.append("o.status=?"); params.append(status)
    if q:
        where.append("(o.id=? OR u.email LIKE ?)"); params += [q.lstrip("#"), f"%{q}%"]
    orders = db.execute(
        "SELECT o.*, u.email, "
        "(SELECT p.name FROM order_items oi JOIN products p ON p.id=oi.product_id "
        " WHERE oi.order_id=o.id ORDER BY oi.id LIMIT 1) AS first_item, "
        "(SELECT COUNT(*) FROM order_items WHERE order_id=o.id) AS n_items "
        "FROM orders o JOIN users u ON u.id=o.user_id "
        + ("WHERE " + " AND ".join(where) if where else "") + " ORDER BY o.id DESC", params).fetchall()
    stats = db.execute(
        "SELECT (SELECT COUNT(*) FROM orders), "
        "(SELECT COUNT(*) FROM orders WHERE status IN ('pending','pending-quote')), "
        "(SELECT COALESCE(SUM(total_idr),0) FROM orders WHERE status='paid' "
        " AND strftime('%Y-%m', created_at)=strftime('%Y-%m','now')), "
        "(SELECT COUNT(*) FROM users)").fetchone()
    users = db.execute("SELECT u.id, u.email, u.name, u.is_admin, u.created_at, COUNT(o.id) AS n_orders FROM users u "
                       "LEFT JOIN orders o ON o.user_id=u.id GROUP BY u.id ORDER BY u.id DESC").fetchall()
    products = db.execute("SELECT * FROM products ORDER BY id").fetchall()
    return render_template("admin.html", orders=orders, stats=stats, users=users, products=products,
                           settings=get_settings(), statuses=ORDER_STATUSES, status=status, q=q,
                           site_texts=SITE_TEXTS)


@app.route("/admin/orders/<int:order_id>/status", methods=["POST"])
@admin_required
def admin_order_status(order_id):
    status = request.form.get("new_status")
    if status not in ORDER_STATUSES:
        abort(400)
    db = get_db()
    with db:
        if db.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id)).rowcount == 0:
            abort(404)
    flash(f"Status pesanan #{order_id} diubah ke {status}.")
    return back_to_admin("#pesanan")


@app.route("/admin/settings", methods=["POST"])
@admin_required
def admin_settings():
    vals = {k: request.form.get(k, "").strip() for k in SETTING_KEYS}
    if not (vals["price_per_gram_idr"].isdigit() and vals["min_price_idr"].isdigit()):
        flash("Harga harus angka bulat ≥ 0.", "error")
    elif not (vals["wa_number"].isdigit() and 8 <= len(vals["wa_number"]) <= 15):
        flash("Nomor WA harus angka saja, format internasional (contoh 6281234567890).", "error")
    elif not 0 < len(vals["shipping_note"]) <= 300:
        flash("Catatan ongkir wajib diisi (maks. 300 karakter).", "error")
    else:
        db = get_db()
        with db:
            db.executemany("UPDATE settings SET value=? WHERE key=?", [(str(int(v)) if k.endswith("_idr") else v, k)
                                                                     for k, v in vals.items()])
        flash("Pengaturan disimpan.")
    return back_to_admin("#pengaturan")


def product_form():
    """Validated product fields from the admin form, or None after flashing the error."""
    f = {k: request.form.get(k, "").strip() for k in ("name", "emoji", "description", "price_idr", "marketplace_url")}
    f["is_ready_stock"] = int(request.form.get("is_ready_stock") == "1")
    f["active"] = int(request.form.get("active") == "1")
    if not 0 < len(f["name"]) <= 80:
        flash("Nama produk wajib diisi (maks. 80 karakter).", "error")
    elif not 0 < len(f["emoji"]) <= 8:
        flash("Ikon/emoji wajib diisi (contoh 🔑).", "error")
    elif len(f["description"]) > 500:
        flash("Deskripsi maks. 500 karakter.", "error")
    elif not f["price_idr"].isdigit():
        flash("Harga harus angka bulat ≥ 0 (0 = quote project).", "error")
    elif f["marketplace_url"] and not (f["marketplace_url"].startswith("https://") and len(f["marketplace_url"]) <= 500):
        flash("Link marketplace harus diawali https://", "error")  # rendered as href: block javascript: etc.
    elif f["is_ready_stock"] and not f["marketplace_url"]:
        flash("Produk ready stock wajib punya link marketplace.", "error")
    else:
        f["price_idr"] = int(f["price_idr"])
        f["marketplace_url"] = f["marketplace_url"] or None
        return f
    return None


PRODUCT_COLS = ("name", "emoji", "description", "price_idr", "marketplace_url", "is_ready_stock", "active")

# Checked by content, not by the client-sent filename/MIME.
PHOTO_MAGIC = {b"\xff\xd8\xff": ".jpg", b"\x89PNG\r\n\x1a\n": ".png", b"RIFF": ".webp"}
MAX_PHOTO = 5 * 1024 * 1024
MAX_MODEL = 30 * 1024 * 1024


def upload_kind(field, data):
    """File extension if `data` is a valid upload for `field`, else None."""
    if field == "photo":
        if len(data) > MAX_PHOTO:
            return None
        ext = next((e for m, e in PHOTO_MAGIC.items() if data.startswith(m)), None)
        return None if ext == ".webp" and data[8:12] != b"WEBP" else ext
    if len(data) > MAX_MODEL or len(data) < 84:
        return None
    n = int.from_bytes(data[80:84], "little")
    return ".stl" if 84 + 50 * n == len(data) and n or data.lstrip()[:5].lower() == b"solid" else None


def save_media(product_id, old):
    """Apply photo/model uploads + remove checkboxes. Returns False after flashing an error."""
    updates = {}
    for field, label in (("photo", "Foto harus JPG/PNG/WebP maks. 5 MB."),
                         ("model", "Model 3D harus file STL maks. 30 MB.")):
        f = request.files.get(field)
        if f and f.filename:
            data = f.read()
            if not (ext := upload_kind(field, data)):
                flash(label, "error")
                return False
            name = secrets.token_hex(8) + ext
            with open(os.path.join(UPLOAD_DIR, name), "wb") as out:
                out.write(data)
            updates[field] = name
        elif request.form.get(f"remove_{field}") == "1":
            updates[field] = None
    if updates:
        db = get_db()
        with db:
            db.execute(f"UPDATE products SET {', '.join(k + '=?' for k in updates)} WHERE id=?",
                       [*updates.values(), product_id])
        for k in updates:  # drop replaced files only after the DB points elsewhere
            if old and old[k]:
                try:
                    os.remove(os.path.join(UPLOAD_DIR, old[k]))
                except OSError:
                    pass
    return True


@app.route("/admin/products/<int:product_id>", methods=["POST"])
@admin_required
def admin_product(product_id):
    if (f := product_form()) is not None:
        db = get_db()
        old = db.execute("SELECT photo, model FROM products WHERE id=?", (product_id,)).fetchone()
        with db:
            if db.execute(f"UPDATE products SET {', '.join(c + '=?' for c in PRODUCT_COLS)} WHERE id=?",
                          [f[c] for c in PRODUCT_COLS] + [product_id]).rowcount == 0:
                abort(404)
        if save_media(product_id, old):
            flash(f"Produk \"{f['name']}\" disimpan.")
    return back_to_admin("#produk")


@app.route("/admin/products/new", methods=["POST"])
@admin_required
def admin_product_new():
    if (f := product_form()) is not None:
        db = get_db()
        base = re.sub(r"[^a-z0-9]+", "-", f["name"].lower()).strip("-") or "produk"
        slug, n = base, 2
        while db.execute("SELECT 1 FROM products WHERE slug=?", (slug,)).fetchone():
            slug, n = f"{base}-{n}", n + 1
        with db:
            pid = db.execute(f"INSERT INTO products(slug, {', '.join(PRODUCT_COLS)}) VALUES (?{',?' * len(PRODUCT_COLS)})",
                             [slug] + [f[c] for c in PRODUCT_COLS]).lastrowid
        if save_media(pid, None):
            flash(f"Produk \"{f['name']}\" ditambahkan.")
    return back_to_admin("#produk")


@app.route("/admin/content", methods=["POST"])
@admin_required
def admin_content():
    vals = {k: request.form.get(k, "").strip().replace("\r\n", "\n") for k in SITE_TEXTS}
    if bad := [SITE_TEXTS[k][0] for k, v in vals.items() if not 0 < len(v) <= 2000]:
        flash(f"Wajib diisi (maks. 2000 karakter): {', '.join(bad)}.", "error")
    elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", vals["contact_email"]):
        flash("Email kontak tidak valid.", "error")
    else:
        db = get_db()
        with db:
            db.executemany("UPDATE settings SET value=? WHERE key=?", [(v, k) for k, v in vals.items()])
        flash("Konten website disimpan.")
    return back_to_admin("#konten")


@app.route("/admin/users/<int:user_id>/admin", methods=["POST"])
@admin_required
def admin_user_role(user_id):
    if user_id == g.user["id"]:
        flash("Tidak bisa mengubah akses admin akun sendiri.", "error")  # avoid locking yourself out
    else:
        make = int(request.form.get("is_admin") == "1")
        db = get_db()
        with db:
            if db.execute("UPDATE users SET is_admin=? WHERE id=?", (make, user_id)).rowcount == 0:
                abort(404)
        flash("Akses admin diberikan." if make else "Akses admin dicabut.")
    return back_to_admin("#user")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8095, debug=False)
