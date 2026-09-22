(() => {
  'use strict';
  const canvas = document.getElementById('chart');
  if (!canvas || !window.Chart) return;
  let series = [];
  try { series = JSON.parse(document.getElementById('series').textContent); } catch (e) { return; }
  if (!series.length) return;

  const colors = ['#22d3ee', '#ff3b5c', '#fbbf24', '#34d399', '#a78bfa', '#3b82f6', '#f472b6', '#fb923c', '#2dd4bf', '#e2e8f0'];
  const datasets = series.map((s, i) => {
    const pts = s.points.map((p) => ({ x: new Date(p.t).getTime(), y: p.y }));
    if (pts.length) pts.unshift({ x: pts[0].x - 60000, y: 0 });
    return {
      label: s.name, data: pts, borderColor: colors[i % colors.length], backgroundColor: colors[i % colors.length],
      stepped: true, borderWidth: 2.2, pointRadius: 2.5, pointHoverRadius: 5, tension: 0,
    };
  });
  const now = Date.now();
  datasets.forEach((d) => { if (d.data.length) d.data.push({ x: Math.max(now, d.data[d.data.length - 1].x), y: d.data[d.data.length - 1].y }); });

  const fmt = new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  Chart.defaults.color = '#8b98b4';
  Chart.defaults.font.family = 'Inter, system-ui, sans-serif';
  new Chart(canvas, {
    type: 'line',
    data: { datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      animation: window.Spark?.reduced ? false : { duration: 1200, easing: 'easeOutQuart' },
      interaction: { mode: 'nearest', intersect: false },
      scales: {
        x: { type: 'linear', grid: { color: 'rgba(130,170,255,.06)' }, ticks: { maxTicksLimit: 6, callback: (v) => fmt.format(new Date(v)) } },
        y: { beginAtZero: true, grid: { color: 'rgba(130,170,255,.06)' } },
      },
      plugins: {
        legend: { position: 'bottom', labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true, padding: 16 } },
        tooltip: {
          backgroundColor: '#0c1325', borderColor: 'rgba(130,170,255,.22)', borderWidth: 1, padding: 12,
          callbacks: { title: (items) => fmt.format(new Date(items[0].parsed.x)), label: (c) => ` ${c.dataset.label}: ${c.parsed.y} pts` },
        },
      },
    },
  });
})();
