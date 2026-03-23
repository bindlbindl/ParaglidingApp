/* ============================================================
   Bay Area Paragliding Conditions – Frontend JS
   ============================================================ */

let allData = [];
let currentModal = null;

// ── Day-of-week abbreviations ──────────────────────────────
function dayAbbr(dateStr) {
  const d = new Date(dateStr + 'T12:00:00');
  const today = new Date();
  today.setHours(12, 0, 0, 0);
  const diff = Math.round((d - today) / 86400000);
  if (diff === 0) return 'Today';
  if (diff === 1) return 'Tmrw';
  return d.toLocaleDateString('en-US', { weekday: 'short' });
}

function fmtDate(dateStr) {
  const d = new Date(dateStr + 'T12:00:00');
  return d.toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' });
}

// ── Load all conditions ────────────────────────────────────
async function loadConditions() {
  const btn = document.getElementById('refresh-btn');
  btn.classList.add('loading');

  document.getElementById('loading').classList.remove('hidden');
  document.getElementById('sites-grid').classList.add('hidden');
  document.getElementById('error-state').classList.add('hidden');
  document.getElementById('summary-bar').classList.add('hidden');

  try {
    const resp = await fetch('/api/conditions');
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const json = await resp.json();
    allData = json.results;
    renderGrid(allData);
    renderSummary(allData);

    const ts = new Date(json.fetched_at);
    document.getElementById('last-updated').textContent =
      `Updated ${ts.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}`;
  } catch (e) {
    document.getElementById('loading').classList.add('hidden');
    document.getElementById('error-state').classList.remove('hidden');
    console.error(e);
  } finally {
    btn.classList.remove('loading');
  }
}

// ── Summary chips ──────────────────────────────────────────
function renderSummary(data) {
  const counts = { great: 0, good: 0, marginal: 0, poor: 0, avoid: 0 };
  data.forEach(r => {
    const cls = r.current?.class;
    if (cls && counts[cls] !== undefined) counts[cls]++;
  });

  const labels = { great: 'Great', good: 'Good', marginal: 'Marginal', poor: 'Poor', avoid: 'Avoid' };
  const container = document.getElementById('summary-chips');
  container.innerHTML = '';
  Object.entries(counts).forEach(([cls, n]) => {
    if (n === 0) return;
    const chip = document.createElement('span');
    chip.className = `chip ${cls}`;
    chip.textContent = `${n} ${labels[cls]}`;
    chip.title = `${n} site(s) rated ${labels[cls]}`;
    container.appendChild(chip);
  });

  document.getElementById('summary-bar').classList.remove('hidden');
}

// ── Main grid ──────────────────────────────────────────────
function renderGrid(data) {
  const grid = document.getElementById('sites-grid');
  grid.innerHTML = '';

  data.forEach((result, idx) => {
    const card = buildCard(result, idx);
    grid.appendChild(card);
  });

  document.getElementById('loading').classList.add('hidden');
  grid.classList.remove('hidden');
}

function buildCard(result, idx) {
  const card = document.createElement('div');
  card.className = 'site-card';

  if (result.error) {
    card.innerHTML = `
      <div class="card-header">
        <div class="site-info">
          <div class="site-name">${result.site?.name || 'Unknown'}</div>
          <div class="site-location">${result.site?.location || ''}</div>
        </div>
      </div>
      <div style="padding:16px;color:var(--poor);font-size:0.85rem;">⚠️ ${result.error}</div>`;
    return card;
  }

  const { site, current, daily } = result;
  const scoreClass = `score-${current.class}`;

  // Forecast strip (7 days)
  const forecastHTML = (daily || []).map(d => `
    <div class="forecast-day">
      <span class="fd-day">${dayAbbr(d.date)}</span>
      <span class="fd-icon">${d.weather_icon}</span>
      <span class="fd-score ${d.class}">${d.score}</span>
      <span class="fd-wind">${d.wind_dir} ${d.wind_max !== null ? Math.round(d.wind_max) : '—'}</span>
    </div>`).join('');

  card.innerHTML = `
    <div class="card-header">
      <div class="site-info">
        <div class="site-name">${site.name}</div>
        <div class="site-location">${site.location}</div>
        <div class="site-meta">
          <span class="site-type-badge">${site.site_type}</span>
          &nbsp;·&nbsp; ~${site.drive_hours}h drive
        </div>
      </div>
      <div class="score-badge">
        <span class="score-number ${scoreClass}">${current.score}</span>
        <span class="score-label ${scoreClass}">${current.label}</span>
      </div>
    </div>
    <div class="card-current">
      <div class="cond-item">
        <span class="cond-label">Weather</span>
        <span class="cond-value">${current.weather_icon} ${current.weather_desc}</span>
      </div>
      <div class="cond-item">
        <span class="cond-label">Wind</span>
        <span class="cond-value">${current.wind_dir} ${fmtWind(current.wind_speed_mph)}</span>
      </div>
      <div class="cond-item">
        <span class="cond-label">Gusts</span>
        <span class="cond-value">${fmtWind(current.wind_gusts_mph)}</span>
      </div>
      <div class="cond-item">
        <span class="cond-label">Temp</span>
        <span class="cond-value">${fmtTemp(current.temperature_f)}</span>
      </div>
    </div>
    <div class="card-forecast">
      <div class="forecast-title">7-day flying forecast (10am–5pm window)</div>
      <div class="forecast-days">${forecastHTML}</div>
    </div>`;

  card.addEventListener('click', () => openModal(result));
  return card;
}

// ── Modal ──────────────────────────────────────────────────
function openModal(result) {
  currentModal = result;
  const { site, current, daily } = result;
  const content = document.getElementById('modal-content');

  const daysHTML = (daily || []).map((d, i) => `
    <div class="modal-day ${i === 0 ? 'active' : ''}" onclick="selectDay(${i})" data-idx="${i}">
      <span class="modal-day-name">${dayAbbr(d.date)}</span>
      <span class="modal-day-icon">${d.weather_icon}</span>
      <span class="modal-day-score ${d.class}">${d.score}</span>
      <span class="modal-day-temp">${fmtTempShort(d.temp_max)}/${fmtTempShort(d.temp_min)}</span>
    </div>`).join('');

  content.innerHTML = `
    <div class="modal-site-header">
      <div class="modal-site-name">${site.name}</div>
      <div class="modal-site-sub">${site.location} · ${site.site_type} site · ~${site.drive_hours}h from SF · ${site.altitude_ft.toLocaleString()} ft</div>
    </div>

    <div class="modal-score-row">
      <div class="modal-score-big score-${current.class}">${current.score}</div>
      <div class="modal-score-info">
        <div class="modal-rating score-${current.class}">${current.label} right now</div>
        <div class="modal-weather">${current.weather_icon} ${current.weather_desc} · Wind ${current.wind_dir} ${fmtWind(current.wind_speed_mph)} · Temp ${fmtTemp(current.temperature_f)}</div>
      </div>
    </div>

    <p style="font-size:0.75rem;color:var(--text-muted);margin-bottom:8px;">CURRENT FACTORS</p>
    <ul class="factors-list">
      ${(current.factors || []).map(f => `<li>${f}</li>`).join('')}
    </ul>

    <p class="modal-section-title">7-Day Forecast (10am–5pm Flying Window)</p>
    <div class="modal-daily-grid">${daysHTML}</div>
    <div id="day-detail"></div>

    <p style="font-size:0.75rem;color:var(--text-muted);margin-top:20px;">${site.description}</p>
    <p style="font-size:0.72rem;color:var(--text-muted);margin-top:6px;">Preferred wind: ${site.preferred_wind_dirs.join(', ')} · ${site.preferred_wind_min_mph}–${site.preferred_wind_max_mph} mph</p>`;

  // Show first day detail
  renderDayDetail(0);

  document.getElementById('modal-overlay').classList.remove('hidden');
  document.body.style.overflow = 'hidden';
}

function selectDay(idx) {
  document.querySelectorAll('.modal-day').forEach((el, i) => {
    el.classList.toggle('active', i === idx);
  });
  renderDayDetail(idx);
}

function renderDayDetail(idx) {
  const panel = document.getElementById('day-detail');
  if (!currentModal) return;
  const day = currentModal.daily[idx];
  if (!day) { panel.innerHTML = ''; return; }

  panel.innerHTML = `
    <div class="day-detail-panel">
      <div style="font-size:0.8rem;font-weight:600;margin-bottom:10px;">${fmtDate(day.date)} — <span class="score-${day.class}">${day.label}</span> (${day.score}/100)</div>
      <div class="day-detail-grid">
        <div class="day-detail-item">
          <span class="day-detail-label">Weather</span>
          <span class="day-detail-value">${day.weather_icon} ${day.weather_desc}</span>
        </div>
        <div class="day-detail-item">
          <span class="day-detail-label">Wind (daytime avg)</span>
          <span class="day-detail-value">${day.wind_dir} ${day.wind_max !== null ? Math.round(day.wind_max) + ' mph' : '—'}</span>
        </div>
        <div class="day-detail-item">
          <span class="day-detail-label">Temp Range</span>
          <span class="day-detail-value">${fmtTempShort(day.temp_min)} – ${fmtTempShort(day.temp_max)}</span>
        </div>
        <div class="day-detail-item">
          <span class="day-detail-label">Rain Chance</span>
          <span class="day-detail-value">${day.precip_prob !== null && day.precip_prob !== undefined ? Math.round(day.precip_prob) + '%' : '—'}</span>
        </div>
      </div>
      <ul class="day-factors">
        ${(day.factors || []).map(f => `<li>${f}</li>`).join('')}
      </ul>
    </div>`;
}

function closeModal() {
  document.getElementById('modal-overlay').classList.add('hidden');
  document.body.style.overflow = '';
  currentModal = null;
}

// Keyboard close
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeModal();
});

// ── Helpers ────────────────────────────────────────────────
function fmtWind(mph) {
  if (mph === null || mph === undefined) return '—';
  return `${Math.round(mph)} mph`;
}

function fmtTemp(f) {
  if (f === null || f === undefined) return '—';
  return `${Math.round(f)}°F`;
}

function fmtTempShort(f) {
  if (f === null || f === undefined) return '—';
  return `${Math.round(f)}°`;
}

// ── Init ───────────────────────────────────────────────────
loadConditions();
