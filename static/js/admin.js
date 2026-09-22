(() => {
  'use strict';
  const { $, $$ } = window.Spark;

  // ---------- hint rows
  const hints = $('#hints');
  const tpl = $('#hintTpl');
  $('[data-add-hint]')?.addEventListener('click', () => {
    hints.append(tpl.content.cloneNode(true));
    $$('.hint-row textarea', hints).pop().focus();
  });
  hints?.addEventListener('click', (e) => {
    const b = e.target.closest('[data-remove-hint]');
    if (b) b.closest('.hint-row').remove();
  });

  // ---------- dynamic scoring fields
  const dyn = $('[data-dynamic-toggle]');
  const syncDyn = () => $$('[data-dynamic]').forEach((f) => f.classList.toggle('hidden', !dyn.checked));
  if (dyn) { dyn.addEventListener('change', syncDyn); syncDyn(); }

  // ---------- CTF window: local <-> UTC
  const pad = (n) => String(n).padStart(2, '0');
  const toLocalInput = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  const form = $('[data-time-form]');
  if (form) {
    const locals = $$('input[type="datetime-local"]', form);
    locals.forEach((inp) => {
      if (inp.dataset.utc) {
        const d = new Date(inp.dataset.utc);
        if (!isNaN(d)) inp.value = toLocalInput(d);
      }
    });
    form.addEventListener('submit', () => {
      locals.forEach((inp) => {
        form.elements[inp.dataset.target].value = inp.value ? new Date(inp.value).toISOString() : '';
      });
    });
    $('[data-clear-times]', form).addEventListener('click', () => { locals.forEach((i) => { i.value = ''; }); });
  }
})();
