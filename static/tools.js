// Live canvas previews for /tools/* pages. Vanilla JS, no network.
(() => {
  const root = document.querySelector('.tool');
  if (!root) return;
  const tool = root.dataset.tool;
  const COLORS = JSON.parse(root.dataset.colors);
  const form = document.getElementById('design');
  const cv = document.getElementById('preview');
  const ctx = cv.getContext('2d');
  const W = cv.width, H = cv.height;
  const still = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const val = n => form.elements[n].value;

  function rgb(hex) { const n = parseInt(hex.slice(1), 16); return [n >> 16, n >> 8 & 255, n & 255]; }
  // amt > 0 lightens toward white, < 0 darkens toward black
  function shade(hex, amt) {
    const t = amt < 0 ? 0 : 255, p = Math.abs(amt);
    return 'rgb(' + rgb(hex).map(v => Math.round(v + (t - v) * p)).join(',') + ')';
  }
  const lum = hex => { const [r, g, b] = rgb(hex); return (0.299 * r + 0.587 * g + 0.114 * b) / 255; };

  function rrect(c, x, y, w, h, r) {
    c.moveTo(x + r, y); c.arcTo(x + w, y, x + w, y + h, r); c.arcTo(x + w, y + h, x, y + h, r);
    c.arcTo(x, y + h, x, y, r); c.arcTo(x, y, x + w, y, r); c.closePath();
  }

  function bg() {
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = '#0f1520'; ctx.fillRect(0, 0, W, H);
    ctx.strokeStyle = 'rgba(255,255,255,.04)'; ctx.lineWidth = 1;
    ctx.beginPath();
    for (let x = 0; x <= W; x += 32) { ctx.moveTo(x + .5, 0); ctx.lineTo(x + .5, H); }
    for (let y = 0; y <= H; y += 32) { ctx.moveTo(0, y + .5); ctx.lineTo(W, y + .5); }
    ctx.stroke();
  }

  // Extruded "printed" solid: dark side + shadow, then lit face.
  function solid(path, c, depth = 12) {
    ctx.save();
    ctx.shadowColor = 'rgba(0,0,0,.55)'; ctx.shadowBlur = 30; ctx.shadowOffsetY = 18;
    ctx.translate(0, depth); ctx.beginPath(); path(); ctx.fillStyle = shade(c, -.45); ctx.fill();
    ctx.restore();
    ctx.beginPath(); path();
    const g = ctx.createLinearGradient(-170, -170, 170, 170);
    g.addColorStop(0, shade(c, .22)); g.addColorStop(1, shade(c, -.18));
    ctx.fillStyle = g; ctx.fill();
    ctx.strokeStyle = 'rgba(255,255,255,.14)'; ctx.lineWidth = 2; ctx.stroke();
  }

  function label(text) {
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.font = '600 15px system-ui, sans-serif'; ctx.fillStyle = '#8b96a5'; ctx.textAlign = 'left';
    ctx.fillText(text, 18, H - 18);
  }

  // ── gantungan kunci ──
  const KEY = {
    bulat: { top: -128, textY: 8, maxW: 200, path: () => ctx.arc(0, 0, 130, 0, Math.PI * 2) },
    kotak: { top: -96, textY: 8, maxW: 270, path: () => rrect(ctx, -165, -95, 330, 190, 30) },
    hati: {
      top: -96, textY: -18, maxW: 190, path: () => {
        ctx.moveTo(0, 135);
        ctx.bezierCurveTo(-45, 98, -178, 22, -178, -50);
        ctx.bezierCurveTo(-178, -118, -122, -148, -86, -148);
        ctx.bezierCurveTo(-40, -148, -10, -118, 0, -88);
        ctx.bezierCurveTo(10, -118, 40, -148, 86, -148);
        ctx.bezierCurveTo(122, -148, 178, -118, 178, -50);
        ctx.bezierCurveTo(178, 22, 45, 98, 0, 135);
      }
    },
  };

  function keychain(t) {
    bg();
    const c = COLORS[val('warna')], s = KEY[val('bentuk')];
    const name = document.getElementById('nama').value.trim() || 'NAMA';
    ctx.translate(W / 2, H / 2 + 34);
    ctx.rotate(Math.sin(t * 1.1) * 0.06);
    solid(() => { s.path(); ctx.moveTo(30, s.top); ctx.arc(0, s.top, 30, 0, Math.PI * 2); }, c);
    // hole + metal ring
    ctx.beginPath(); ctx.arc(0, s.top, 11, 0, Math.PI * 2); ctx.fillStyle = '#0f1520'; ctx.fill();
    ctx.beginPath(); ctx.arc(0, s.top - 34, 36, 0, Math.PI * 2);
    ctx.lineWidth = 7; ctx.strokeStyle = '#aeb6c2'; ctx.stroke();
    ctx.lineWidth = 2; ctx.strokeStyle = 'rgba(255,255,255,.6)'; ctx.stroke();
    // raised lettering, auto-fit
    let size = 78;
    do { ctx.font = `800 ${size}px system-ui, -apple-system, sans-serif`; size -= 2; }
    while (ctx.measureText(name).width > s.maxW && size > 16);
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    const light = lum(c) < 0.6;
    ctx.fillStyle = shade(c, light ? -.5 : -.7); ctx.fillText(name, 0, s.textY + 4);
    ctx.fillStyle = light ? shade(c, .8) : shade(c, -.45); ctx.fillText(name, 0, s.textY);
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    label(`${val('bentuk')} · PLA ${val('warna')}`);
  }

  // ── clicker ──
  function knob(x, y, w, h, r, c) {
    solid(() => rrect(ctx, x, y, w, h, r), c, 6);
  }
  function clicker(t) {
    bg();
    const body = COLORS[val('body')], aks = COLORS[val('aksen')], model = val('model');
    const m = still ? 0 : t;
    ctx.translate(W / 2, H / 2);
    if (model === 'slider') {
      solid(() => rrect(ctx, -210, -80, 420, 160, 80), body);
      ctx.beginPath(); rrect(ctx, -150, -15, 300, 30, 15); ctx.fillStyle = shade(body, -.6); ctx.fill();
      const x = Math.sin(m * 1.6) * 115;
      knob(x - 36, -52, 72, 104, 22, aks);
      ctx.strokeStyle = shade(aks, -.35); ctx.lineWidth = 3;
      for (const dx of [-14, 0, 14]) { ctx.beginPath(); ctx.moveTo(x + dx, -28); ctx.lineTo(x + dx, 28); ctx.stroke(); }
    } else if (model === 'switcher') {
      solid(() => rrect(ctx, -140, -140, 280, 280, 50), body);
      ctx.beginPath(); ctx.arc(0, 0, 92, 0, Math.PI * 2); ctx.fillStyle = shade(body, -.55); ctx.fill();
      ctx.save();
      ctx.rotate(Math.tanh(Math.sin(m * 1.4) * 5) * 0.55);  // snaps between two positions
      knob(-18, -112, 36, 112, 18, aks);
      solid(() => ctx.arc(0, -112, 28, 0, Math.PI * 2), aks, 5);
      ctx.restore();
      solid(() => ctx.arc(0, 0, 34, 0, Math.PI * 2), aks, 5);
    } else {
      solid(() => ctx.arc(0, 0, 150, 0, Math.PI * 2), body);
      ctx.fillStyle = shade(body, -.4);
      for (let i = 0; i < 32; i++) {
        const a = i / 32 * Math.PI * 2;
        ctx.beginPath(); ctx.arc(Math.cos(a) * 138, Math.sin(a) * 138, 5, 0, Math.PI * 2); ctx.fill();
      }
      ctx.beginPath(); ctx.arc(0, 0, 100, 0, Math.PI * 2); ctx.fillStyle = shade(body, -.55); ctx.fill();
      const press = Math.pow(Math.max(0, Math.sin(m * 3)), 8);
      ctx.save(); ctx.scale(1 - press * .07, 1 - press * .07);
      solid(() => ctx.arc(0, 0, 76, 0, Math.PI * 2), aks, 9 - press * 6);
      const g = ctx.createRadialGradient(-26, -30, 4, 0, 0, 76);
      g.addColorStop(0, 'rgba(255,255,255,.45)'); g.addColorStop(.5, 'rgba(255,255,255,0)');
      ctx.beginPath(); ctx.arc(0, 0, 76, 0, Math.PI * 2); ctx.fillStyle = g; ctx.fill();
      ctx.restore();
    }
    label(`${model} · body ${val('body')} · aksen ${val('aksen')}`);
  }

  // ── lithophane ──
  const relief = document.createElement('canvas');
  let hasPhoto = false;
  function clipShape(c, x, y, w, h) {
    c.beginPath();
    if (val('bentuk') === 'oval') c.ellipse(x + w / 2, y + h / 2, w / 2, h / 2, 0, 0, Math.PI * 2);
    else rrect(c, x, y, w, h, 8);
  }
  function lithophane() {
    bg();
    if (!hasPhoto) {
      ctx.font = '600 20px system-ui, sans-serif'; ctx.fillStyle = '#8b96a5';
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText('Pilih foto untuk melihat preview relief', W / 2, H / 2);
      return;
    }
    const w = relief.width, h = relief.height, x = (W - w) / 2, y = (H - h) / 2 - 8;
    ctx.save();
    ctx.shadowColor = 'rgba(0,0,0,.6)'; ctx.shadowBlur = 30; ctx.shadowOffsetY = 14;
    clipShape(ctx, x, y, w, h); ctx.fillStyle = '#000'; ctx.fill();
    ctx.restore();
    ctx.save(); clipShape(ctx, x, y, w, h); ctx.clip(); ctx.drawImage(relief, x, y); ctx.restore();
    clipShape(ctx, x, y, w, h); ctx.strokeStyle = 'rgba(0,229,160,.5)'; ctx.lineWidth = 2; ctx.stroke();
    label(`${val('bentuk')} · sisi terpanjang ${val('ukuran').replace('cm', ' cm')} · terang = tipis, gelap = tebal`);
  }
  function loadPhoto(file) {
    const msg = document.getElementById('foto-msg');
    if (!file) return;
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      const s = Math.min(560 / img.naturalWidth, 400 / img.naturalHeight);
      relief.width = Math.max(1, Math.round(img.naturalWidth * s));
      relief.height = Math.max(1, Math.round(img.naturalHeight * s));
      const c = relief.getContext('2d', { willReadFrequently: true });
      c.drawImage(img, 0, 0, relief.width, relief.height);
      const d = c.getImageData(0, 0, relief.width, relief.height), p = d.data;
      for (let i = 0; i < p.length; i += 4) {
        const v = 255 - (0.299 * p[i] + 0.587 * p[i + 1] + 0.114 * p[i + 2]);
        p[i] = p[i + 1] = p[i + 2] = v;
      }
      c.putImageData(d, 0, 0);
      URL.revokeObjectURL(url);
      hasPhoto = true; msg.textContent = '';
      setAddEnabled(true);
      lithophane();
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      msg.textContent = 'File tidak bisa dibaca sebagai gambar. Coba JPG/PNG lain.';
    };
    img.src = url;
  }
  function thumb() {
    const s = Math.min(200 / relief.width, 200 / relief.height, 1);
    const t = document.createElement('canvas');
    t.width = Math.round(relief.width * s); t.height = Math.round(relief.height * s);
    const c = t.getContext('2d');
    c.fillStyle = '#0a0e14'; c.fillRect(0, 0, t.width, t.height);  // JPEG has no alpha
    clipShape(c, 0, 0, t.width, t.height); c.clip();
    c.drawImage(relief, 0, 0, t.width, t.height);
    return t.toDataURL('image/jpeg', 0.6);
  }

  const addBtn = document.getElementById('add');
  function setAddEnabled(on) { if (addBtn) addBtn.disabled = !on; }

  const draw = { 'gantungan-kunci': keychain, clicker, lithophane }[tool];
  if (tool === 'lithophane') {
    setAddEnabled(false);
    document.getElementById('foto').addEventListener('change', e => loadPhoto(e.target.files[0]));
  }

  form.addEventListener('submit', e => {
    const o = { tool };
    form.querySelectorAll('input[type=radio]:checked').forEach(r => { o[r.name] = r.value; });
    if (tool === 'gantungan-kunci') o.nama = document.getElementById('nama').value.trim();
    if (tool === 'lithophane') {
      if (!hasPhoto) { e.preventDefault(); return; }
      o.thumb = thumb();
    }
    document.getElementById('options').value = JSON.stringify(o);
  });

  if (tool === 'lithophane' || still) {
    form.addEventListener('input', () => draw(0));
    draw(0);
  } else {
    (function loop(ms) { draw(ms / 1000); requestAnimationFrame(loop); })(0);
  }
})();
