// /quote: parse STL in the browser, estimate weight & price. Vanilla JS, file never leaves the device.
const PLA_DENSITY = 1.24;   // g/cm3
const WASTE_G = 5;          // support, brim, purge
const MAX_BYTES = 100e6;
const MAX_CM3 = 30000;      // ~31 cm cube; above this the file is probably not in mm

// Signed tetrahedron volume vs origin per triangle (divergence theorem); sum, abs at the end.
function tri(a, b, c) {
  return (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0]) + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6;
}

// Returns {tris, mm3}; throws Error with an Indonesian message.
function stlVolume(buf) {
  if (!buf.byteLength) throw new Error('File kosong.');
  const dv = new DataView(buf);
  let vol = 0, tris = 0;
  // binary STL: 80-byte header + uint32 count + 50 bytes per triangle. Some binaries start with "solid" too, so size decides.
  if (buf.byteLength >= 84 && 84 + 50 * dv.getUint32(80, true) === buf.byteLength) {
    tris = dv.getUint32(80, true);
    for (let i = 0, o = 84; i < tris; i++, o += 50) {
      const v = k => [dv.getFloat32(o + 12 + k * 12, true), dv.getFloat32(o + 16 + k * 12, true), dv.getFloat32(o + 20 + k * 12, true)];
      vol += tri(v(0), v(1), v(2));
    }
  } else {
    const text = new TextDecoder().decode(buf);
    if (!/^\s*solid/i.test(text)) throw new Error('Ini bukan file STL yang valid.');
    const re = /vertex\s+(\S+)\s+(\S+)\s+(\S+)/gi;
    const pts = [];
    for (let m; (m = re.exec(text));) pts.push([+m[1], +m[2], +m[3]]);
    if (pts.length % 3) throw new Error('File STL ASCII rusak (jumlah vertex tidak lengkap).');
    tris = pts.length / 3;
    for (let i = 0; i < pts.length; i += 3) vol += tri(pts[i], pts[i + 1], pts[i + 2]);
  }
  if (!tris) throw new Error('File STL tidak berisi segitiga (model kosong).');
  vol = Math.abs(vol);
  if (!isFinite(vol)) throw new Error('Angka di file STL tidak valid.');
  if (vol < 1) throw new Error('Volume hampir nol — model mungkin tidak tertutup (bukan solid) atau satuannya bukan mm.');
  if (vol / 1000 > MAX_CM3) throw new Error('Ukuran tidak wajar (lebih dari 30 liter). Pastikan satuan file dalam mm, bukan µm/inci.');
  return { tris, mm3: vol };
}

function estimate(mm3, infillPct, cfg) {
  const cm3 = mm3 / 1000;
  const grams = cm3 * PLA_DENSITY * (0.2 + 0.8 * infillPct / 100) + WASTE_G;
  const filament = Math.round(grams * cfg.price_per_gram_idr);
  const price = Math.ceil(Math.max(filament, cfg.min_price_idr) / 1000) * 1000;
  return { cm3, grams, filament, price };
}

if (typeof module !== 'undefined') module.exports = { stlVolume, estimate };

if (typeof document !== 'undefined') (() => {
  const root = document.getElementById('quote');
  if (!root) return;
  const cfg = JSON.parse(root.dataset.cfg);
  const $ = id => document.getElementById(id);
  const input = $('stl'), err = $('qerr'), wa = $('wa');
  const rp = n => 'Rp' + Math.round(n).toLocaleString('id-ID');
  const num = (n, d) => n.toLocaleString('id-ID', { maximumFractionDigits: d });
  let model = null;  // {name, mm3}

  function render() {
    const infill = +document.querySelector('input[name=infill]:checked').value;
    const set = (id, t) => { $(id).textContent = t; };
    if (!model) {
      ['o-vol', 'o-wt', 'o-fil', 'o-price'].forEach(id => set(id, '—'));
      wa.setAttribute('aria-disabled', 'true');
      wa.href = 'https://wa.me/' + cfg.wa_number;
      return;
    }
    const e = estimate(model.mm3, infill, cfg);
    set('o-vol', num(e.cm3, 2) + ' cm³');
    set('o-wt', '±' + num(e.grams, 1) + ' g');
    set('o-fil', rp(e.filament));
    set('o-price', rp(e.price));
    const msg = 'Halo REBRAY, saya mau cetak file STL:\n' +
      'File: ' + model.name + '\n' +
      'Volume: ' + num(e.cm3, 2) + ' cm³\n' +
      'Estimasi berat: ±' + num(e.grams, 1) + ' g (PLA)\n' +
      'Infill: ' + infill + '%\n' +
      'ESTIMASI harga: ' + rp(e.price) + '\n' +
      '(estimasi otomatis dari website, mohon konfirmasi harga final — file STL saya kirim di chat ini)';
    wa.href = 'https://wa.me/' + cfg.wa_number + '?text=' + encodeURIComponent(msg);
    wa.removeAttribute('aria-disabled');
  }

  const preview = buf => dispatchEvent(new CustomEvent('stl-loaded', { detail: buf }));  // 3D preview (viewer3d.js)
  function fail(text) { model = null; preview(null); err.textContent = text; err.hidden = false; render(); }

  input.addEventListener('change', async () => {
    const f = input.files[0];
    err.hidden = true;
    if (!f) return;
    $('fname').textContent = f.name;
    if (!/\.stl$/i.test(f.name)) return fail('File harus berformat .stl.');
    if (f.size > MAX_BYTES) return fail('File terlalu besar (maks 100 MB).');
    try {
      const buf = await f.arrayBuffer();
      model = { name: f.name, mm3: stlVolume(buf).mm3 };
      render();
      preview(buf);
    } catch (e) { fail(e.message); }
  });
  document.querySelectorAll('input[name=infill]').forEach(r => r.addEventListener('change', render));
  wa.addEventListener('click', e => {
    if (!model) { e.preventDefault(); fail('Pilih file STL dulu untuk menghitung estimasi.'); }
  });
  render();
})();
