(() => {
  'use strict';
  // Telegram login: our own button opens Telegram's popup (via telegram-widget.js), then the
  // signed payload is POSTed to the server together with the CSRF token.
  const btn = document.querySelector('[data-telegram-login]');
  const form = document.querySelector('[data-telegram-form]');
  if (!btn || !form) return;

  let loading = null;
  function loadWidget() {
    if (window.Telegram && window.Telegram.Login) return Promise.resolve();
    if (loading) return loading;
    loading = new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = 'https://telegram.org/js/telegram-widget.js?22';
      s.async = true;
      s.onload = resolve;
      s.onerror = () => { loading = null; reject(new Error('telegram widget failed to load')); };
      document.head.appendChild(s);
    });
    return loading;
  }

  function submit(user) {
    Object.keys(user).forEach((k) => {
      const inp = document.createElement('input');
      inp.type = 'hidden';
      inp.name = k;
      inp.value = user[k];
      form.appendChild(inp);
    });
    if (btn.dataset.next) {
      const n = document.createElement('input');
      n.type = 'hidden'; n.name = 'next'; n.value = btn.dataset.next;
      form.appendChild(n);
    }
    form.submit();
  }

  btn.addEventListener('click', () => {
    btn.disabled = true;
    loadWidget().then(() => {
      window.Telegram.Login.auth({ bot_id: btn.dataset.telegramLogin, request_access: 'write' }, (user) => {
        btn.disabled = false;
        if (user) submit(user);
      });
    }).catch(() => {
      btn.disabled = false;
      if (window.Spark) window.Spark.toast(window.Spark.t('Xatolik yuz berdi.'), 'error');
    });
  });
})();
