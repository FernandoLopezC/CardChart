(() => {
  document.querySelectorAll('[data-history-chart]').forEach(chart => {
    const points = JSON.parse(chart.dataset.points);
    if (!points.length) return;
    const svg = chart.querySelector('svg'), lines = chart.querySelector('.chart-lines'), grid = chart.querySelector('.chart-grid');
    const cursor = chart.querySelector('.chart-cursor'), marker = chart.querySelector('.chart-marker'), readout = chart.querySelector('.chart-readout');
    const values = points.map(point => point.gbp === null || point.gbp === '' ? null : Number(point.gbp));
    const valid = values.filter(value => value !== null && Number.isFinite(value));
    const low = valid.length ? Math.min(...valid) : 0, high = valid.length ? Math.max(...valid) : 0, span = high - low || 1;
    chart.querySelector('[data-chart-high]').textContent = valid.length ? `\u00a3${high.toFixed(2)}` : 'Unavailable';
    chart.querySelector('[data-chart-low]').textContent = valid.length ? `\u00a3${low.toFixed(2)}` : 'Unavailable';
    const dates = points.map(point => Date.parse(point.observed_at));
    const timed = dates.every(Number.isFinite) && dates[dates.length - 1] > dates[0];
    const coords = values.map((value, index) => ({x: timed ? 20 + (dates[index] - dates[0]) * 760 / (dates[dates.length - 1] - dates[0]) : 20 + index * 760 / Math.max(1, points.length - 1), y: value === null || !Number.isFinite(value) ? null : 220 - (value - low) * 190 / span}));
    const ns = 'http://www.w3.org/2000/svg';
    [30, 125, 220].forEach(y => { const tick = document.createElementNS(ns, 'line'); tick.setAttribute('x1',20); tick.setAttribute('x2',780); tick.setAttribute('y1',y); tick.setAttribute('y2',y); grid.append(tick); });
    [20, 400, 780].forEach(x => { const tick = document.createElementNS(ns, 'line'); tick.setAttribute('x1',x); tick.setAttribute('x2',x); tick.setAttribute('y1',30); tick.setAttribute('y2',220); grid.append(tick); });
    let run = [];
    function draw() { if (run.length > 1) { const line = document.createElementNS(ns, 'polyline'); line.setAttribute('points',run.join(' ')); line.setAttribute('class','chart-line'); lines.append(line); } run = []; }
    coords.forEach(p => { if (p.y === null) draw(); else run.push(`${p.x},${p.y}`); }); draw();
    let selected = points.length - 1;
    function show(index) {
      selected = Math.max(0, Math.min(points.length - 1, index));
      const p = coords[selected], point = points[selected];
      cursor.setAttribute('x1', p.x); cursor.setAttribute('x2', p.x); cursor.setAttribute('y1', 20); cursor.setAttribute('y2', 230);
      marker.hidden = p.y === null; marker.setAttribute('visibility', p.y === null ? 'hidden' : 'visible');
      if (p.y !== null) {
        const bounds = svg.getBoundingClientRect();
        const width = 8 * 800 / bounds.width, height = 8 * 250 / (bounds.height || 250);
        marker.setAttribute('x', p.x - width / 2); marker.setAttribute('y', p.y - height / 2);
        marker.setAttribute('width', width); marker.setAttribute('height', height);
      }
      const value = p.y === null ? 'Value unavailable' : `\u00a3${point.gbp}`;
      const change = values[0] !== null && Number.isFinite(values[0]) && p.y !== null ? ` \u00b7 Period change \u00a3${(values[selected] - values[0]).toFixed(2)}` : '';
      const changes = point.quantity_changes || [];
      const added = changes.reduce((sum, entry) => sum + Math.max(0, entry.quantity_change), 0);
      const removed = changes.reduce((sum, entry) => sum + Math.max(0, -entry.quantity_change), 0);
      const quantities = added || removed ? ` \u00b7 Added ${added}, removed ${removed} since previous observation` : '';
      const date = point.observed_at.slice(0, 19).replace('T', ' ') + ' UTC';
      readout.textContent = `${date} \u00b7 ${value} \u00b7 ${point.priced_count} of ${point.inventory_count} lines priced \u00b7 Qty ${point.quantity}${quantities}${change}`;
    }
    function pointer(event) { const rect = svg.getBoundingClientRect(); const x = (event.clientX - rect.left) * 800 / rect.width; show(coords.reduce((best, p, index) => Math.abs(p.x - x) < Math.abs(coords[best].x - x) ? index : best, 0)); }
    svg.addEventListener('pointermove', pointer); svg.addEventListener('pointerdown', pointer);
    svg.addEventListener('keydown', event => { let next = selected; if (event.key === 'ArrowLeft') next--; else if (event.key === 'ArrowRight') next++; else if (event.key === 'Home') next = 0; else if (event.key === 'End') next = points.length - 1; else return; event.preventDefault(); show(next); });
    show(selected);
  });
})();
