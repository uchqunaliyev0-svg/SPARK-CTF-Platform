(function () {
  var t = null;
  try { t = localStorage.getItem('spark_theme'); } catch (e) { /* storage unavailable */ }
  document.documentElement.dataset.theme = t === 'light' ? 'light' : 'dark';
})();
