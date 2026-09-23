/* Proof-of-work solver: runs off the main thread so animations never freeze. */
'use strict';
function zeroBits(buf) {
  const b = new Uint8Array(buf);
  let n = 0;
  for (let i = 0; i < b.length; i++) {
    if (b[i] === 0) { n += 8; continue; }
    n += Math.clz32(b[i]) - 24;
    break;
  }
  return n;
}
self.onmessage = async (e) => {
  const { salt, bits } = e.data || {};
  const enc = new TextEncoder();
  const batch = 512;
  try {
    for (let start = 0; start < 50000000; start += batch) {
      const tries = [];
      for (let i = start; i < start + batch; i++) {
        tries.push(crypto.subtle.digest('SHA-256', enc.encode(salt + i)).then((h) => (zeroBits(h) >= bits ? i : -1)));
      }
      const found = (await Promise.all(tries)).find((x) => x >= 0);
      if (found !== undefined) { self.postMessage({ nonce: found }); return; }
    }
    self.postMessage({ error: 'not found' });
  } catch (err) {
    self.postMessage({ error: String(err) });
  }
};
