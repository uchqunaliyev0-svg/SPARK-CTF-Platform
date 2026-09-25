(() => {
  'use strict';
  const { $, $$, api, toast, fmtTimes, t } = window.Spark;
  const cards = $$('.ch-card');
  const modal = $('#modal');
  let current = null;

  // ---------- announcements
  const readAnn = () => { try { return JSON.parse(localStorage.getItem('spark_ann') || '[]'); } catch (e) { return []; } };
  const hidden = readAnn();
  $$('[data-ann]').forEach((a) => {
    if (hidden.includes(a.dataset.ann)) { a.remove(); return; }
    $('[data-ann-close]', a).addEventListener('click', () => {
      a.remove();
      try { localStorage.setItem('spark_ann', JSON.stringify([...readAnn(), a.dataset.ann].slice(-50))); } catch (e) { /* storage unavailable */ }
    });
  });

  // ---------- filters
  const f = { q: '', diff: '', status: '', cat: '' };
  function applyFilters() {
    let shown = 0;
    cards.forEach((c) => {
      const ok = (!f.q || c.dataset.title.includes(f.q))
        && (!f.diff || c.dataset.diff === f.diff)
        && (!f.cat || c.dataset.cat === f.cat)
        && (!f.status || (f.status === 'solved') === c.classList.contains('solved'));
      c.classList.toggle('hidden', !ok);
      if (ok) shown++;
    });
    $$('[data-cat-section]').forEach((s) => s.classList.toggle('hidden', !$$('.ch-card:not(.hidden)', s).length));
    $('#noMatch')?.classList.toggle('hidden', shown > 0 || !cards.length);
  }
  $('#q')?.addEventListener('input', (e) => { f.q = e.target.value.trim().toLowerCase(); applyFilters(); });
  [['#cats', 'cat'], ['#diffs', 'diff'], ['#status', 'status']].forEach(([sel, key]) => {
    $$(`${sel} .side-item`).forEach((b) => b.addEventListener('click', () => {
      if (b.disabled) return;
      $$(`${sel} .side-item`).forEach((x) => x.classList.remove('on'));
      b.classList.add('on'); f[key] = b.dataset.v; applyFilters();
    }));
  });

  // ---------- helpers
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const ICON = {
    file: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12M7 10l5 5 5-5M5 21h14"/></svg>',
    bulb: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18h6M10 22h4M12 2a7 7 0 0 0-4 12.7V16h8v-1.3A7 7 0 0 0 12 2Z"/></svg>',
  };
  function linkify(target, text) {
    target.textContent = '';
    const re = /(https?:\/\/[^\s<>"']+)/g;
    let last = 0; let m;
    while ((m = re.exec(text))) {
      target.append(text.slice(last, m.index));
      const a = el('a', null, m[1]);
      a.href = m[1]; a.target = '_blank'; a.rel = 'noopener noreferrer nofollow';
      target.append(a);
      last = m.index + m[1].length;
    }
    target.append(text.slice(last));
  }
  function fileName(url) {
    try { const p = new URL(url).pathname.split('/').filter(Boolean).pop(); return decodeURIComponent(p || url); } catch (e) { return url; }
  }
  function setResult(kind, msg) {
    const r = $('#mResult');
    r.className = `result show ${kind}`;
    r.textContent = msg;
  }

  // ---------- modal
  function showTab(name) {
    $$('.tabs button', modal).forEach((b) => b.classList.toggle('on', b.dataset.tab === name));
    $$('[data-pane]', modal).forEach((p) => p.classList.toggle('hidden', p.dataset.pane !== name));
    if (name === 'solves') loadSolves();
  }
  $$('.tabs button', modal).forEach((b) => b.addEventListener('click', () => showTab(b.dataset.tab)));

  function openModal() {
    modal.classList.add('open');
    modal.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
  }
  function closeModal() {
    modal.classList.remove('open');
    modal.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
    current = null;
    if (location.hash) history.replaceState(null, '', location.pathname + location.search);
  }
  modal.addEventListener('click', (e) => { if (e.target === modal || e.target.closest('[data-close]')) closeModal(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && modal.classList.contains('open')) closeModal(); });

  function renderHints(hints) {
    const box = $('#mHints');
    box.textContent = '';
    hints.forEach((h, i) => {
      const w = el('div', 'hint-card');
      const b = el('button');
      b.type = 'button';
      const label = el('span');
      label.innerHTML = ICON.bulb;
      label.append(` Hint ${i + 1}`);
      label.style.display = 'inline-flex'; label.style.gap = '8px'; label.style.alignItems = 'center';
      b.append(label, el('span', 'mono', h.unlocked ? '' : (h.cost ? `−${h.cost} pts` : t('bepul'))));
      w.append(b);
      const body = el('div', 'body' + (h.unlocked ? '' : ' hidden'), h.content || '');
      w.append(body);
      b.addEventListener('click', async () => {
        if (h.unlocked) { body.classList.toggle('hidden'); return; }
        if (h.cost && !window.confirm(t('Bu hint {cost} ball turadi. Avval umumiy balldan, yetmasa masala mukofotidan ayriladi. Davom etasizmi?', { cost: h.cost }))) return;
        b.disabled = true;
        const res = await api(`/api/hints/${h.id}/unlock`, { method: 'POST' });
        b.disabled = false;
        if (res.status !== 'ok') { toast(res.message || t('Xatolik yuz berdi.'), 'error'); return; }
        h.unlocked = true; h.content = res.content;
        body.textContent = res.content; body.classList.remove('hidden');
        b.lastChild.textContent = '';
        if (res.score != null) updateScore(res.score);
      });
      box.append(w);
    });
  }

  async function openChallenge(id) {
    const card = cards.find((c) => c.dataset.id === String(id));
    if (!card) return;
    current = { id, card };
    showTab('info');
    $('#mMeta').textContent = '';
    $('#mTitle').textContent = card.querySelector('h3').textContent;
    $('#mSub').textContent = '';
    $('#mDesc').innerHTML = '<div class="skeleton" style="width:92%"></div><div class="skeleton" style="width:80%"></div><div class="skeleton" style="width:60%"></div>';
    $('#mFiles').textContent = ''; $('#mHints').textContent = '';
    $('#mResult').className = 'result';
    $('#mSolveCnt').textContent = '';
    $('#flagInput').value = '';
    openModal();
    history.replaceState(null, '', `#c-${id}`);
    const d = await api(`/api/challenges/${id}`);
    if (!current || current.id !== id) return;
    if (d._status !== 200) { $('#mDesc').textContent = d.message || t("Yuklab bo'lmadi."); return; }
    current.data = d;
    const meta = $('#mMeta');
    meta.append(el('span', 'badge b-cyan', d.category), el('span', `badge d-${d.difficulty}`, d.difficulty));
    $('#mTitle').textContent = d.title;
    const sub = $('#mSub');
    const v = el('span'); v.append(el('b', null, String(d.value)), ` ${t('ball')}`);
    const s = el('span'); s.append(el('b', null, String(d.solves)), ` ${t('ta yechim')}`);
    sub.append(v, s);
    if (d.author) { const a = el('span'); a.append(`${t('muallif:')} `, el('b', null, d.author)); sub.append(a); }
    $('#mSolveCnt').textContent = `(${d.solves})`;
    linkify($('#mDesc'), d.description);
    d.files.forEach((u) => {
      const a = el('a', 'file');
      a.href = u; a.target = '_blank'; a.rel = 'noopener noreferrer nofollow';
      a.innerHTML = ICON.file;
      a.append(el('span', null, fileName(u)));
      $('#mFiles').append(a);
    });
    renderHints(d.hints);
    $('#mSolvedText').textContent = t('Siz bu masalani yechgansiz!');
    $('#mSolved').classList.toggle('hidden', !d.solved);
    const closed = !d.can_submit;
    $('#flagForm').classList.toggle('hidden', d.solved || closed);
    if (!d.solved && closed) setResult('bad', t('Musobaqa yakunlangan — flag qabul qilinmaydi.'));
    if (!d.solved && !closed) setTimeout(() => $('#flagInput').focus(), 120);
  }

  async function loadSolves() {
    if (!current) return;
    const box = $('#mSolves');
    box.innerHTML = '<div class="skeleton"></div><div class="skeleton"></div>';
    const list = await api(`/api/challenges/${current.id}/solves`);
    box.textContent = '';
    if (!Array.isArray(list) || !list.length) {
      box.append(el('p', 'muted', `${t("Hali hech kim yechmagan. Birinchi bo'ling!")} 🩸`));
      return;
    }
    list.forEach((s, i) => {
      const row = el('div', 'row');
      const a = el('a', 'user-cell', s.username);
      a.href = `/users/${encodeURIComponent(s.username)}`;
      const t = el('time'); t.dataset.t = s.time;
      row.append(el('span', 'i', i === 0 ? '🩸' : `#${i + 1}`), a, t);
      box.append(row);
    });
    fmtTimes(box);
  }

  function updateScore(score) {
    const pill = $('[data-my-score]');
    if (pill) pill.textContent = `${score} pts`;
    const k = $('[data-kpi-score]'); if (k) k.textContent = score;
  }

  $('#flagForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!current) return;
    const input = $('#flagInput');
    const flag = input.value.trim();
    if (!flag) { input.focus(); return; }
    const btn = $('#flagForm button');
    btn.disabled = true;
    const res = await api(`/api/challenges/${current.id}/submit`, { method: 'POST', body: { flag } });
    btn.disabled = false;
    if (res.status === 'correct') {
      $('#mResult').className = 'result';
      $('#flagForm').classList.add('hidden');
      $('#mSolvedText').textContent = res.message;
      $('#mSolved').classList.remove('hidden');
      const [bv, bs] = $$('#mSub b');
      if (bv) bv.textContent = res.value;
      if (bs) { bs.textContent = parseInt(bs.textContent, 10) + 1; $('#mSolveCnt').textContent = `(${bs.textContent})`; }
      const c = current.card;
      c.classList.add('solved');
      const sv = $('[data-solves]', c); sv.textContent = parseInt(sv.textContent, 10) + 1;
      $('[data-val]', c).firstChild.textContent = res.value;
      updateScore(res.score);
      refreshProgress();
      confetti();
    } else {
      setResult('bad', res.message || t('Xatolik yuz berdi.'));
      input.classList.remove('shake'); void input.offsetWidth; input.classList.add('shake');
      input.select();
    }
  });

  function refreshProgress() {
    $$('[data-cat-section]').forEach((s) => {
      const all = $$('.ch-card', s).length; const done = $$('.ch-card.solved', s).length;
      $('.prog', s).textContent = `${done}/${all}`;
      $('.bar i', s).style.width = `${Math.round((done / all) * 100)}%`;
    });
    const solvedN = $$('.ch-card.solved').length;
    const head = $('[data-progress-text]');
    if (head) head.textContent = t('{solved} / {total} ta masala yechilgan', { solved: solvedN, total: cards.length });
    const k = $('[data-kpi-solved]'); if (k) k.textContent = solvedN;
    const pct = cards.length ? Math.round((solvedN / cards.length) * 100) : 0;
    const ring = $('[data-ring]'); if (ring) ring.style.strokeDashoffset = 163.36 * (1 - pct / 100);
    const rt = $('[data-ring-text]'); if (rt) rt.textContent = `${pct}%`;
    $$('[data-cat-count]').forEach((n) => {
      const cs = cards.filter((c) => c.dataset.cat === n.dataset.catCount);
      const done = cs.filter((c) => c.classList.contains('solved')).length;
      n.textContent = `${done}/${cs.length}`;
      const bar = n.parentElement.querySelector('.mini i');
      if (bar && cs.length) bar.style.width = `${Math.round((done / cs.length) * 100)}%`;
    });
    const all = $('#cats .side-item[data-v=""] .n'); if (all) all.textContent = `${solvedN}/${cards.length}`;
  }

  cards.forEach((c) => c.addEventListener('click', () => openChallenge(c.dataset.id)));
  const m = location.hash.match(/^#c-(\d+)$/);
  if (m) openChallenge(m[1]);

  // ---------- confetti
  function confetti(big) {
    if (window.Spark.reduced) return;
    const cv = el('canvas', 'confetti');
    document.body.append(cv);
    const ctx = cv.getContext('2d');
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    cv.width = innerWidth * dpr; cv.height = innerHeight * dpr;
    ctx.scale(dpr, dpr);
    const colors = big ? ['#ff3b5c', '#ff7a45', '#fbbf24', '#ffffff'] : ['#22d3ee', '#3b82f6', '#34d399', '#ff3b5c', '#ffffff'];
    const parts = Array.from({ length: big ? 260 : 170 }, () => ({
      x: innerWidth / 2 + (Math.random() - 0.5) * 120, y: innerHeight / 2,
      vx: (Math.random() - 0.5) * 18, vy: -Math.random() * 16 - 6,
      w: 5 + Math.random() * 6, h: 8 + Math.random() * 8, r: Math.random() * 6, vr: (Math.random() - 0.5) * 0.4,
      c: colors[Math.floor(Math.random() * colors.length)],
    }));
    const t0 = performance.now();
    (function draw(t) {
      const age = t - t0;
      ctx.clearRect(0, 0, innerWidth, innerHeight);
      parts.forEach((p) => {
        p.vy += 0.42; p.vx *= 0.99; p.x += p.vx; p.y += p.vy; p.r += p.vr;
        ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.r);
        ctx.globalAlpha = Math.max(0, 1 - age / 2600);
        ctx.fillStyle = p.c; ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h * Math.abs(Math.cos(p.r * 2)));
        ctx.restore();
      });
      if (age < 2600) requestAnimationFrame(draw); else cv.remove();
    })(t0);
  }
})();
