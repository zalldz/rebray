# REBRAY — Recycle Bray: From Waste to Useful

Web shop REBRAY: barang 3D print dari sisa filament & plastik daur ulang.
Flask + SQLite (stdlib). Auth, shop, keranjang, checkout (+ lanjut bayar via WhatsApp), pesanan, 3 tool desain canvas.

## Jalankan

```bash
cd /home/boo/apps/bray3d
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python app.py          # http://0.0.0.0:8095
```

DB `bray3d.db` dibuat & di-seed otomatis saat start pertama.

## Env (opsional)

| Var | Fungsi |
|---|---|
| `SECRET_KEY` | session key; kalau kosong dibuat random & disimpan di `.secret_key` |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | notifikasi order baru ke Telegram |
| `WHATSAPP_NUMBER` | nomor WA admin untuk tombol pembayaran (default `6282299130985`) |
| `ADMIN_EMAIL` | user yang daftar dengan email ini otomatis jadi admin |
| `BRAY3D_DB` | path DB lain (dipakai test; nama file/env lama dipertahankan agar DB yang ada tetap terbaca) |

Harga `/quote` (hitung harga cetak STL, di browser) diatur di `/admin` → Pengaturan, atau langsung di tabel `settings`:
`sqlite3 bray3d.db "UPDATE settings SET value='2000' WHERE key='price_per_gram_idr'"` (juga `min_price_idr`, `wa_number`, `shipping_note`).
`WHATSAPP_NUMBER` hanya dipakai untuk seed awal — setelah itu ubah lewat tabel `settings`.

Produk ready stock (`is_ready_stock=1`) dijual lewat `marketplace_url`, tidak bisa masuk keranjang (kecuali versi desain custom dari tool).

## Admin (`/admin`)

Dashboard: statistik, kelola status pesanan, edit produk (ready stock / link marketplace / harga), pengaturan harga & WA, daftar user.
Non-admin (dan yang belum login) dapat 404. Link "Admin" di nav hanya muncul untuk admin.

Admin pertama — pilih salah satu:
- Set env `ADMIN_EMAIL=email@kamu.id` sebelum start, lalu daftar dengan email itu → otomatis admin.
- Atau untuk user yang sudah terdaftar: `sqlite3 bray3d.db "UPDATE users SET is_admin=1 WHERE email='email@kamu.id'"`

## Test

```bash
.venv/bin/python test_app.py && .venv/bin/python test_tools.py && node test_quote.js
```

pm2: `pm2 start .venv/bin/python --name bray3d -- app.py` (jalankan dari folder ini).
