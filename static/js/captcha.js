(() => {
  'use strict';
  const { $, $$, t } = window.Spark;

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

  async function solveMain(ch) {
    const enc = new TextEncoder();
    const batch = 256;
    for (let start = 0; start < 50000000; start += batch) {
      const tries = [];
      for (let i = start; i < start + batch; i++) {
        tries.push(crypto.subtle.digest('SHA-256', enc.encode(ch.salt + i)).then((h) => (zeroBits(h) >= ch.bits ? i : -1)));
      }
      const found = (await Promise.all(tries)).find((x) => x >= 0);
      if (found !== undefined) return found;
      await new Promise((r) => setTimeout(r, 0)); // let the page breathe
    }
    throw new Error('not found');
  }

  const WORKER_URL = document.currentScript?.dataset.worker || '/static/js/pow-worker.js';
  function solve(ch) {
    if (!window.Worker) return solveMain(ch);
    return new Promise((resolve, reject) => {
      let w;
      try { w = new Worker(WORKER_URL); } catch (e) { solveMain(ch).then(resolve, reject); return; }
      w.onmessage = (e) => { w.terminate(); if (e.data && e.data.nonce !== undefined) resolve(e.data.nonce); else reject(new Error('pow')); };
      w.onerror = () => { w.terminate(); solveMain(ch).then(resolve, reject); };
      w.postMessage({ salt: ch.salt, bits: ch.bits });
    });
  }

  $$('[data-captcha]').forEach((box) => {
    const input = $('input[name="captcha"]', box);
    const btn = $('[data-captcha-btn]', box);
    const label = $('[data-captcha-label]', box);
    const form = box.closest('form');
    const base = label.textContent;
    let running = null;

    const FRESH_MS = 4 * 60 * 1000; // server tokens live 5 minutes
    let solvedAt = 0;
    async function run() {
      if (box.classList.contains('done') && Date.now() - solvedAt < FRESH_MS) return true;
      box.classList.remove('done');
      if (running) return running;
      box.classList.remove('fail');
      box.classList.add('busy');
      label.textContent = t('Tekshirilmoqda...');
      running = (async () => {
        try {
          if (!window.crypto?.subtle) throw new Error('no crypto');
          const res = await fetch('/api/captcha', { credentials: 'same-origin', headers: { Accept: 'application/json' } });
          const ch = await res.json();
          const nonce = await solve(ch);
          input.value = `${ch.salt}:${ch.exp}:${ch.bits}:${ch.sig}:${nonce}`;
          box.classList.remove('busy');
          box.classList.add('done');
          solvedAt = Date.now();
          label.textContent = t('Tasdiqlandi');
          return true;
        } catch (e) {
          box.classList.remove('busy');
          box.classList.add('fail');
          label.textContent = t("Xatolik. Qayta bosing.");
          setTimeout(() => { if (box.classList.contains('fail')) label.textContent = base; }, 2500);
          return false;
        } finally {
          running = null;
        }
      })();
      return running;
    }

    btn.addEventListener('click', run);
    // start quietly in the background as soon as the user starts filling the form
    let started = false;
    const kick = () => { if (!started) { started = true; run(); } };
    ['focusin', 'input', 'pointerdown', 'keydown'].forEach((ev) => form.addEventListener(ev, kick, { passive: true }));
    if (form.contains(document.activeElement)) kick(); // autofocus already inside the form
    form.addEventListener('submit', async (e) => {
      if (box.classList.contains('done') && Date.now() - solvedAt < FRESH_MS) return;
      e.preventDefault();
      e.stopImmediatePropagation();
      if (await run()) form.requestSubmit();
    }, true);
  });
})();
