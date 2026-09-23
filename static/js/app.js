(() => {
  'use strict';
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const CSRF = $('meta[name="csrf-token"]')?.content || '';
  let I18N = {};
  try { I18N = JSON.parse($('#i18n')?.textContent || '{}'); } catch (e) { I18N = {}; }
  const t = (s, vars) => {
    let out = I18N[s] || s;
    if (vars) Object.keys(vars).forEach((k) => { out = out.replace(`{${k}}`, vars[k]); });
    return out;
  };

  // ---------- theme
  $$('[data-theme-toggle]').forEach((b) => b.addEventListener('click', () => {
    const next = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem('spark_theme', next); } catch (e) { /* storage unavailable */ }
    window.dispatchEvent(new CustomEvent('spark:theme', { detail: next }));
  }));

  // ---------- toasts
  function dismiss(t) {
    t.classList.add('out');
    setTimeout(() => t.remove(), 300);
  }
  function toast(msg, type = 'info', ms = 4500) {
    const box = $('#toasts');
    const t = document.createElement('div');
    t.className = `toast ${type}`;
    const dot = document.createElement('i');
    const body = document.createElement('div');
    body.textContent = msg;
    t.append(dot, body);
    t.addEventListener('click', () => dismiss(t));
    box.appendChild(t);
    setTimeout(() => dismiss(t), ms);
  }
  $$('[data-flash]').forEach((t, i) => {
    t.addEventListener('click', () => dismiss(t));
    setTimeout(() => dismiss(t), 5000 + i * 400);
  });

  // ---------- api helper
  async function api(url, opts = {}) {
    const res = await fetch(url, {
      method: opts.method || 'GET',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': CSRF, Accept: 'application/json' },
      body: opts.body ? JSON.stringify(opts.body) : undefined,
      credentials: 'same-origin',
    });
    let data = {};
    try { data = await res.json(); } catch (e) { data = { status: 'error', message: t("Server javobi noto'g'ri.") }; }
    data._status = res.status;
    return data;
  }

  // ---------- nav + app sidebar
  const store = { get: (k) => { try { return localStorage.getItem(k); } catch (e) { return null; } }, set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* storage unavailable */ } } };
  const isApp = document.body.classList.contains('app');
  if (isApp && store.get('spark_sb') === '1') document.body.classList.add('sb-collapsed');
  $('[data-sb-collapse]')?.addEventListener('click', () => {
    const c = document.body.classList.toggle('sb-collapsed');
    store.set('spark_sb', c ? '1' : '0');
  });
  $$('[data-sb-close]').forEach((el) => el.addEventListener('click', () => document.body.classList.remove('sb-open')));
  const burger = $('[data-burger]');
  burger?.addEventListener('click', () => {
    if (isApp && window.innerWidth <= 1000) document.body.classList.toggle('sb-open');
    else $('#navLinks').classList.toggle('open');
  });
  const bell = $('[data-bell]');
  if (bell) {
    const latest = parseInt(bell.dataset.bell, 10) || 0;
    if (latest > (parseInt(store.get('spark_bell'), 10) || 0)) bell.classList.add('unread');
    bell.addEventListener('click', () => { bell.classList.remove('unread'); store.set('spark_bell', String(latest)); });
  }
  $$('[data-dropdown]').forEach((btn) => {
    const dd = document.getElementById(btn.dataset.dropdown);
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const open = dd.classList.toggle('open');
      btn.setAttribute('aria-expanded', open);
    });
    document.addEventListener('click', (e) => {
      if (!dd.contains(e.target)) { dd.classList.remove('open'); btn.setAttribute('aria-expanded', 'false'); }
    });
  });

  // ---------- time formatting (UTC -> local)
  const fmt = new Intl.DateTimeFormat(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  function fmtTimes(root = document) {
    $$('time[data-t]', root).forEach((el) => {
      const d = new Date(el.dataset.t);
      if (!isNaN(d)) { el.textContent = fmt.format(d); el.title = d.toString(); }
    });
  }
  fmtTimes();

  // ---------- countdowns
  $$('[data-countdown]').forEach((el) => {
    const target = new Date(el.dataset.countdown).getTime();
    const parts = { d: $('[data-d]', el), h: $('[data-h]', el), m: $('[data-m]', el), s: $('[data-s]', el) };
    const tick = () => {
      let left = Math.max(0, Math.floor((target - Date.now()) / 1000));
      if (left === 0 && el.dataset.reload !== undefined) { location.reload(); return; }
      const d = Math.floor(left / 86400); left %= 86400;
      const h = Math.floor(left / 3600); left %= 3600;
      const m = Math.floor(left / 60); const s = left % 60;
      parts.d.textContent = d; parts.h.textContent = String(h).padStart(2, '0');
      parts.m.textContent = String(m).padStart(2, '0'); parts.s.textContent = String(s).padStart(2, '0');
    };
    tick();
    setInterval(tick, 1000);
  });

  // ---------- reveal on scroll + counters
  const countUp = (el) => {
    const end = parseInt(el.dataset.count, 10) || 0;
    if (reduced || end === 0) { el.textContent = end; return; }
    const t0 = performance.now(); const dur = 1400;
    const step = (t) => {
      const p = Math.min((t - t0) / dur, 1);
      el.textContent = Math.round(end * (1 - Math.pow(1 - p, 3)));
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  };
  const io = 'IntersectionObserver' in window ? new IntersectionObserver((entries) => {
    entries.forEach((en) => {
      if (!en.isIntersecting) return;
      en.target.classList.add('in');
      $$('[data-count]', en.target).forEach(countUp);
      $$('.bar i[data-w]', en.target).forEach((b) => { b.style.width = b.dataset.w; });
      io.unobserve(en.target);
    });
  }, { threshold: 0.15 }) : null;
  $$('[data-reveal]').forEach((el, i) => {
    el.style.transitionDelay = `${(parseInt(el.dataset.reveal, 10) || 0) * 80}ms`;
    io ? io.observe(el) : el.classList.add('in');
  });

  // ---------- 3D tilt + spotlight
  function tilt(el, max = 8) {
    if (reduced || window.matchMedia('(hover: none)').matches) return;
    el.addEventListener('pointermove', (e) => {
      const r = el.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width; const y = (e.clientY - r.top) / r.height;
      el.style.setProperty('--mx', `${x * 100}%`); el.style.setProperty('--my', `${y * 100}%`);
      el.style.transform = `rotateX(${(0.5 - y) * max}deg) rotateY(${(x - 0.5) * max}deg) translateY(-4px)`;
    });
    el.addEventListener('pointerleave', () => { el.style.transform = ''; });
  }
  $$('[data-tilt]').forEach((el) => tilt(el, parseFloat(el.dataset.tilt) || 8));

  // ---------- password visibility + strength
  const eye = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg>';
  const eyeOff = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3l18 18M10.6 5.1A10 10 0 0 1 12 5c6.4 0 10 7 10 7a17 17 0 0 1-3.2 4.1M6.6 6.6A17 17 0 0 0 2 12s3.6 7 10 7a9.8 9.8 0 0 0 5.4-1.6M9.9 9.9a3 3 0 0 0 4.2 4.2"/></svg>';
  $$('[data-toggle-pw]').forEach((b) => b.addEventListener('click', () => {
    const inp = document.getElementById(b.dataset.togglePw);
    const show = inp.type === 'password';
    inp.type = show ? 'text' : 'password';
    b.innerHTML = show ? eyeOff : eye;
  }));
  const LEVELS = [['#ff3b5c', t('Juda zaif')], ['#ff7a45', t('Zaif')], ['#fbbf24', t("O'rtacha")], ['#34d399', t('Kuchli')]];
  $$('input[data-strength]').forEach((inp) => {
    const field = inp.closest('.field');
    const bars = $$('.strength i', field); const label = $('.strength-label', field);
    inp.addEventListener('input', () => {
      const v = inp.value; let s = 0;
      if (v.length >= 8) s++;
      if (/[a-z]/i.test(v) && /\d/.test(v)) s++;
      if (/[A-Z]/.test(v) && /[a-z]/.test(v)) s++;
      if (/[^A-Za-z0-9]/.test(v) || v.length >= 14) s++;
      if (!v) { bars.forEach((b) => { b.style.background = ''; }); label.textContent = t('Kamida 8 belgi, harf va raqam.'); label.style.color = ''; return; }
      const [c, t] = LEVELS[Math.max(s - 1, 0)];
      bars.forEach((b, i) => { b.style.background = i < s ? c : ''; });
      label.textContent = t; label.style.color = c;
    });
  });
  $$('form[data-match]').forEach((f) => f.addEventListener('submit', (e) => {
    const [a, b] = f.dataset.match.split(',').map((n) => f.elements[n]);
    if (a.value !== b.value) { e.preventDefault(); toast(t('Parollar mos kelmadi.'), 'error'); b.focus(); }
  }));

  // ---------- OTP inputs
  $$('[data-otp]').forEach((wrap) => {
    const boxes = $$('input', wrap);
    const hidden = $('[data-otp-value]', wrap.closest('form'));
    const form = wrap.closest('form');
    const sync = () => {
      hidden.value = boxes.map((b) => b.value).join('');
      boxes.forEach((b) => b.classList.toggle('filled', !!b.value));
      if (hidden.value.length === 6 && form.dataset.autosubmit !== undefined && !form.dataset.sent) form.requestSubmit();
    };
    boxes.forEach((b, i) => {
      b.addEventListener('input', () => {
        b.value = b.value.replace(/\D/g, '').slice(-1);
        if (b.value && i < 5) boxes[i + 1].focus();
        sync();
      });
      b.addEventListener('keydown', (e) => {
        if (e.key === 'Backspace' && !b.value && i > 0) { boxes[i - 1].focus(); boxes[i - 1].value = ''; sync(); }
        if (e.key === 'ArrowLeft' && i > 0) boxes[i - 1].focus();
        if (e.key === 'ArrowRight' && i < 5) boxes[i + 1].focus();
      });
      b.addEventListener('paste', (e) => {
        const digits = (e.clipboardData.getData('text') || '').replace(/\D/g, '').slice(0, 6);
        if (!digits) return;
        e.preventDefault();
        digits.split('').forEach((d, j) => { if (boxes[j]) boxes[j].value = d; });
        boxes[Math.min(digits.length, 5)].focus();
        sync();
      });
    });
    form.addEventListener('submit', (e) => {
      sync();
      if (hidden.value.length !== 6) { e.preventDefault(); toast(t("6 xonali kodni to'liq kiriting."), 'error'); boxes[0].focus(); }
    });
    boxes[0].focus();
  });

  // ---------- resend cooldown
  $$('[data-cooldown]').forEach((btn) => {
    let left = parseInt(btn.dataset.cooldown, 10) || 0;
    const base = btn.textContent;
    const tick = () => {
      if (left > 0) { btn.disabled = true; btn.textContent = `${base} (${left}s)`; left--; setTimeout(tick, 1000); } else { btn.disabled = false; btn.textContent = base; }
    };
    tick();
  });

  // ---------- submit buttons: prevent double submit
  // one submit per page load for auth/one-shot forms (autosubmit + click/Enter used to double-post)
  $$('form[data-loading], form[data-autosubmit]').forEach((f) => f.addEventListener('submit', (e) => {
    if (e.defaultPrevented) return;
    if (f.dataset.sent) { e.preventDefault(); return; }
    f.dataset.sent = '1';
  }));
  $$('form[data-loading]').forEach((f) => f.addEventListener('submit', (e) => {
    if (e.defaultPrevented) return;
    const b = $('button[type="submit"]', f);
    if (b) { b.disabled = true; b.insertAdjacentHTML('afterbegin', '<span class="spinner"></span>'); }
  }));

  // ---------- confirm dialogs
  $$('form[data-confirm]').forEach((f) => f.addEventListener('submit', (e) => {
    if (!window.confirm(f.dataset.confirm)) e.preventDefault();
  }));

  // ---------- email typo hint ("x@gmai" -> "x@gmail.com")
  const TYPOS = {
    'gmail.com': ['gmai', 'gmail', 'gmial', 'gmal', 'gmaill', 'gamil', 'gnail', 'gmsil', 'gmali', 'gmai.com', 'gmial.com',
      'gmal.com', 'gmaill.com', 'gamil.com', 'gnail.com', 'gmsil.com', 'gmali.com', 'gmail.co', 'gmail.con', 'gmail.cm',
      'gmail.om', 'gmail.comm', 'gmail.cim', 'gmail.ru'],
    'mail.ru': ['mail.r', 'mail.rh', 'mali.ru', 'mial.ru'],
    'yahoo.com': ['yahoo', 'yaho.com', 'yahoo.co', 'yahoo.con', 'yhoo.com'],
    'outlook.com': ['outlook', 'outlok.com', 'outlook.co', 'outlook.con', 'otlook.com'],
    'icloud.com': ['icloud', 'iclod.com', 'icloud.co', 'icloud.con', 'icoud.com'],
  };
  const FIX = {};
  Object.keys(TYPOS).forEach((d) => TYPOS[d].forEach((x) => { FIX[x] = d; }));
  $$('[data-email-typo]').forEach((input) => {
    const box = document.createElement('div');
    box.className = 'hint email-fix';
    box.hidden = true;
    input.insertAdjacentElement('afterend', box);
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'linkish';
    box.appendChild(btn);
    let good = '';
    btn.addEventListener('pointerdown', (e) => e.preventDefault());
    btn.addEventListener('click', () => {
      if (!good) return;
      input.value = good;
      good = '';
      box.hidden = true;
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.focus();
    });
    const check = () => {
      const v = input.value.trim().toLowerCase();
      const i = v.lastIndexOf('@');
      const fixed = i > 0 && FIX[v.slice(i + 1)];
      if (!fixed) { good = ''; box.hidden = true; return; }
      good = `${v.slice(0, i)}@${fixed}`;
      btn.textContent = t('{s} demoqchimisiz?', { s: good });
      box.hidden = false;
    };
    input.addEventListener('input', check);
    input.addEventListener('blur', check);
    check();
  });

  window.Spark = { $, $$, api, toast, fmtTimes, tilt, reduced, t };
})();
