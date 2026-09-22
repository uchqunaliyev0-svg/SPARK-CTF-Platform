(() => {
  'use strict';
  const el = document.querySelector('[data-typer]');
  if (!el) return;
  let lines;
  try { lines = JSON.parse(el.dataset.typer); } catch (e) { return; }
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { el.textContent = lines[0]; return; }
  let li = 0, ci = 0, deleting = false;
  function step() {
    const line = lines[li];
    if (!deleting) {
      ci++;
      el.textContent = line.slice(0, ci);
      if (ci === line.length) { deleting = true; return setTimeout(step, 1800); }
      return setTimeout(step, 45 + Math.random() * 60);
    }
    ci--;
    el.textContent = line.slice(0, ci);
    if (ci === 0) { deleting = false; li = (li + 1) % lines.length; return setTimeout(step, 350); }
    setTimeout(step, 22);
  }
  setTimeout(step, 900);
})();
