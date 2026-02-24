const tbody = document.getElementById('tbody');
const meta = document.getElementById('meta');
const detailHint = document.getElementById('detail_hint');
const detailBody = document.getElementById('detail_body');
const runErrors = document.getElementById('run_errors');

const statusFields = {
  status: document.getElementById('st_status'),
  started: document.getElementById('st_started'),
  finished: document.getElementById('st_finished'),
  offers: document.getElementById('st_offers'),
  snapshots: document.getElementById('st_snapshots'),
  evaluations: document.getElementById('st_evaluations'),
  salco: document.getElementById('st_salco'),
  cruz: document.getElementById('st_cruz'),
  fala: document.getElementById('st_fala'),
};

const fields = {
  label: document.getElementById('label'),
  retailer: document.getElementById('retailer'),
  brand: document.getElementById('brand'),
  min_score: document.getElementById('min_score'),
  visible_ge: document.getElementById('visible_ge'),
  cross_positive: document.getElementById('cross_positive'),
};

function money(v) {
  if (v === null || v === undefined) return '-';
  return new Intl.NumberFormat('es-CL', { style: 'currency', currency: 'CLP', maximumFractionDigits: 0 }).format(v);
}

function pct(v) {
  if (v === null || v === undefined) return '-';
  return `${(v * 100).toFixed(2)}%`;
}

function fmtDate(value) {
  if (!value) return '-';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString('es-CL');
}

function sourceLabel(value) {
  if (value === 'live') return 'en vivo';
  if (value === 'error') return 'error';
  return value || '-';
}

function updateStatusCard(data) {
  if (!data) {
    statusFields.status.textContent = 'Sin ejecuciones';
    statusFields.started.textContent = '-';
    statusFields.finished.textContent = '-';
    statusFields.offers.textContent = '-';
    statusFields.snapshots.textContent = '-';
    statusFields.evaluations.textContent = '-';
    statusFields.salco.textContent = '-';
    statusFields.cruz.textContent = '-';
    statusFields.fala.textContent = '-';
    runErrors.classList.add('hidden');
    runErrors.textContent = '';
    return;
  }

  statusFields.status.textContent = data.status;
  statusFields.started.textContent = fmtDate(data.started_at);
  statusFields.finished.textContent = fmtDate(data.finished_at);
  statusFields.offers.textContent = String(data.total_offers);
  statusFields.snapshots.textContent = String(data.total_snapshots);
  statusFields.evaluations.textContent = String(data.total_evaluations);
  statusFields.salco.textContent = `${sourceLabel(data.salcobrand_source)} (${data.salcobrand_count})`;
  statusFields.cruz.textContent = `${sourceLabel(data.cruzverde_source)} (${data.cruzverde_count})`;
  statusFields.fala.textContent = `${sourceLabel(data.falabella_source)} (${data.falabella_count})`;

  const errors = [];
  if (data.salcobrand_error) errors.push(`Salcobrand: ${data.salcobrand_error}`);
  if (data.cruzverde_error) errors.push(`Cruz Verde: ${data.cruzverde_error}`);
  if (data.falabella_error) errors.push(`Falabella: ${data.falabella_error}`);
  if (data.error_message) errors.push(`Pipeline: ${data.error_message}`);

  if (errors.length) {
    runErrors.classList.remove('hidden');
    runErrors.textContent = errors.join(' | ');
  } else {
    runErrors.classList.add('hidden');
    runErrors.textContent = '';
  }
}

async function loadStatus() {
  try {
    const res = await fetch('/status/latest');
    const data = await res.json();
    updateStatusCard(data);
  } catch (err) {
    statusFields.status.textContent = 'Error';
    runErrors.classList.remove('hidden');
    runErrors.textContent = `No se pudo cargar estado: ${err?.message || err}`;
  }
}

function parseRuleTrace(raw) {
  if (!raw) return {};
  if (typeof raw === 'object') return raw;
  try {
    return JSON.parse(raw);
  } catch {
    return {};
  }
}

function passFail(v) {
  return v ? 'OK' : 'FALLA';
}

function explainLabel(x, rt) {
  const messages = [];
  if (rt.R6_visible_discount_ge_10pct === false) {
    messages.push('El descuento visible es menor a 10%, por lo que no puede ser LIKELY_REAL ni REAL.');
  }
  if (rt.R3_cross_store_ge_5pct === false && x.cross_store_delta_pct !== null) {
    messages.push('El precio no es al menos 5% mejor que pares, por lo que la competitividad es débil.');
  }
  if (rt.R2_anchor_spike_le_10pct === false) {
    messages.push('El precio de lista/original parece inflado (riesgo de ancla artificial).');
  }
  if (!messages.length) {
    messages.push('La etiqueta se define por el puntaje ponderado y las reglas.');
  }
  return messages.join(' ');
}

function renderDetail(x) {
  const rt = parseRuleTrace(x.rule_trace);
  const reason = explainLabel(x, rt);
  detailHint.classList.add('hidden');
  detailBody.classList.remove('hidden');
  detailBody.innerHTML = `
    <div class="detail-top">
      <div>
        <span class="badge ${x.label}">${x.label}</span>
        <strong>${x.brand}</strong> - ${x.canonical_name}
      </div>
      <a href="${x.product_url}" target="_blank" rel="noreferrer">Abrir producto</a>
    </div>
    <p class="reason">${reason}</p>
    <div class="stats-grid">
      <div><span>Retailer</span><strong>${x.retailer}</strong></div>
      <div><span>Puntaje</span><strong>${x.score.toFixed(4)}</strong></div>
      <div><span>Actual</span><strong>${money(x.price_current)}</strong></div>
      <div><span>Lista</span><strong>${money(x.price_list)}</strong></div>
      <div><span>Descuento</span><strong>${pct(x.discount_pct)}</strong></div>
      <div><span>Vs mercado</span><strong>${pct(x.cross_store_delta_pct)}</strong></div>
    </div>
    <div class="rules">
      <h3>Trazabilidad de Reglas</h3>
      <ul>
        <li>R1 Delta histórica >= 15%: <strong>${passFail(rt.R1_hist_delta_ge_15pct)}</strong></li>
        <li>R2 Spike de ancla <= 10%: <strong>${passFail(rt.R2_anchor_spike_le_10pct)}</strong></li>
        <li>R3 Delta vs mercado >= 5%: <strong>${passFail(rt.R3_cross_store_ge_5pct)}</strong></li>
        <li>R4 Visto en múltiples snapshots: <strong>${passFail(rt.R4_seen_multiple_snapshots)}</strong></li>
        <li>R5 Historial suficiente: <strong>${passFail(rt.R5_has_enough_history)}</strong></li>
        <li>R6 Descuento visible >= 10%: <strong>${passFail(rt.R6_visible_discount_ge_10pct)}</strong></li>
        <li>Spike de ancla (%): <strong>${rt.anchor_spike_pct ?? '-'}</strong></li>
      </ul>
    </div>
  `;
}

function render(items) {
  tbody.innerHTML = '';
  detailHint.classList.remove('hidden');
  detailBody.classList.add('hidden');
  detailBody.innerHTML = '';

  for (const x of items) {
    const tr = document.createElement('tr');
    tr.className = 'deal-row';
    tr.innerHTML = `
      <td><span class="badge ${x.label}">${x.label}</span></td>
      <td>${x.retailer}</td>
      <td>${x.brand}</td>
      <td>${x.canonical_name}</td>
      <td>${money(x.price_current)}</td>
      <td>${money(x.price_list)}</td>
      <td>${pct(x.discount_pct)}</td>
      <td>${pct(x.cross_store_delta_pct)}</td>
      <td>${x.score.toFixed(4)}</td>
      <td><a href="${x.product_url}" target="_blank" rel="noreferrer">abrir</a></td>
    `;
    tr.addEventListener('click', (ev) => {
      if (ev.target && ev.target.tagName === 'A') return;
      renderDetail(x);
    });
    tbody.appendChild(tr);
  }
}

function buildQuery() {
  const p = new URLSearchParams();
  p.set('limit', '200');
  p.set('min_score', fields.min_score.value || '0');
  if (fields.label.value) p.set('label', fields.label.value);
  if (fields.retailer.value.trim()) p.set('retailer', fields.retailer.value.trim());
  if (fields.brand.value.trim()) p.set('brand', fields.brand.value.trim());
  if (fields.visible_ge.value.trim()) p.set('only_visible_discount_ge', fields.visible_ge.value.trim());
  if (fields.cross_positive.checked) p.set('only_cross_store_positive', 'true');
  return p;
}

async function loadDeals() {
  meta.textContent = 'Cargando...';
  const started = performance.now();
  const query = buildQuery();
  const res = await fetch(`/deals?${query.toString()}`);
  const json = await res.json();
  render(json.items || []);
  const ms = Math.round(performance.now() - started);
  meta.textContent = `${json.items.length} filas en ${ms}ms`;
}

document.getElementById('apply_btn').addEventListener('click', loadDeals);
document.getElementById('reset_btn').addEventListener('click', () => {
  fields.label.value = '';
  fields.retailer.value = '';
  fields.brand.value = '';
  fields.min_score.value = '0';
  fields.visible_ge.value = '';
  fields.cross_positive.checked = false;
  loadDeals();
});

loadDeals().catch((err) => {
  meta.textContent = `Error al cargar ofertas: ${err?.message || err}`;
});
loadStatus();
