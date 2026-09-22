(() => {
  'use strict';
  const canvas = document.getElementById('myChart');
  if (!canvas || !window.Chart) return;
  let pts = [];
  try { pts = JSON.parse(document.getElementById('mySeries').textContent); } catch (e) { return; }
  if (!pts.length) return;
  const data = pts.map((p) => ({ x: new Date(p.t).getTime(), y: p.y }));
  data.unshift({ x: data[0].x - 3600000, y: 0 });
  data.push({ x: Math.max(Date.now(), data[data.length - 1].x), y: data[data.length - 1].y });
  const fmt = new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' });
  const ctx = canvas.getContext('2d');
  const grad = ctx.createLinearGradient(0, 0, 0, 240);
  grad.addColorStop(0, 'rgba(34, 211, 238, .35)');
  grad.addColorStop(1, 'rgba(34, 211, 238, 0)');
  Chart.defaults.color = getComputedStyle(document.documentElement).getPropertyValue('--muted').trim() || '#8b98b4';
  Chart.defaults.font.family = 'Inter, system-ui, sans-serif';
  new Chart(canvas, {
    type: 'line',
    data: { datasets: [{ data, borderColor: '#22d3ee', backgroundColor: grad, fill: true, stepped: true, borderWidth: 2.2, pointRadius: 0, pointHoverRadius: 5 }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      animation: window.Spark?.reduced ? false : { duration: 1000 },
      interaction: { mode: 'nearest', intersect: false },
      plugins: { legend: { display: false }, tooltip: { callbacks: { title: (i) => fmt.format(new Date(i[0].parsed.x)), label: (c) => ` ${c.parsed.y} pts` } } },
      scales: {
        x: { type: 'linear', grid: { color: 'rgba(130,170,255,.06)' }, ticks: { maxTicksLimit: 5, callback: (v) => fmt.format(new Date(v)) } },
        y: { beginAtZero: true, grid: { color: 'rgba(130,170,255,.06)' } },
      },
    },
  });
})();
