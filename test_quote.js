// STL parser self-check. Run: node test_quote.js
const assert = require('assert');
const { stlVolume, estimate } = require('./static/quote.js');

// 20 mm cube, outward-facing triangles
const s = 20, V = [[0,0,0],[s,0,0],[s,s,0],[0,s,0],[0,0,s],[s,0,s],[s,s,s],[0,s,s]];
const F = [[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],[1,2,6],[1,6,5],[2,3,7],[2,7,6],[3,0,4],[3,4,7]];

const toAscii = F => 'solid cube\n' + F.map(f => 'facet normal 0 0 0\nouter loop\n' +
  f.map(i => `vertex ${V[i].join(' ')}`).join('\n') + '\nendloop\nendfacet').join('\n') + '\nendsolid cube\n';
const ascii = toAscii(F);
const enc = t => new TextEncoder().encode(t).buffer;

const bin = new ArrayBuffer(84 + 50 * F.length), dv = new DataView(bin);
new Uint8Array(bin).set(new TextEncoder().encode('solid but actually binary'));  // tricky header
dv.setUint32(80, F.length, true);
F.forEach((f, t) => f.forEach((i, k) => V[i].forEach((c, j) => dv.setFloat32(84 + t * 50 + 12 + k * 12 + j * 4, c, true))));

const near = (a, b) => assert.ok(Math.abs(a - b) < 1e-6, a + ' != ' + b);
near(stlVolume(enc(ascii)).mm3, 8000);
near(stlVolume(bin).mm3, 8000);
near(stlVolume(enc(toAscii(F.map(f => [...f].reverse())))).mm3, 8000);  // inward winding: abs()

for (const [buf, re] of [[new ArrayBuffer(0), /kosong/], [enc('hello world'), /bukan file STL/],
  [enc('solid x\nendsolid x'), /tidak berisi/], [enc(ascii.replace(/vertex 0 0 0\n/, '')), /rusak/],
  [enc(ascii.replace(/20/g, '2000')), /tidak wajar/], [enc(ascii.replace(/20/g, '0.1')), /hampir nol/]])
  assert.throws(() => stlVolume(buf), re);

const cfg = { price_per_gram_idr: 1500, min_price_idr: 25000 };
const e = estimate(8000, 20, cfg);  // 8 cm3 * 1.24 * 0.36 + 5 = 8.5712 g
assert.ok(Math.abs(e.grams - 8.5712) < 1e-9 && e.price === 25000, e);
const big = estimate(100000, 100, cfg);  // 100 cm3 * 1.24 + 5 = 129 g -> 193.500
assert.ok(big.filament === 193500 && big.price === 194000, big);
console.log('quote.js OK');
