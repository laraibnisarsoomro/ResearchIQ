/* ── Equity Research Memo Generator — Frontend ─────────────────────────────── */
'use strict';

const $  = id => document.getElementById(id);
const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html !== undefined) e.innerHTML = html; return e; };

// ── State ─────────────────────────────────────────────────────────────────────
let currentEventSource = null;
let currentReport = null;

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  $('ticker-input').addEventListener('keydown', e => { if (e.key === 'Enter') submitTicker(); });
  $('generate-btn').addEventListener('click', submitTicker);
  $('new-search-btn').addEventListener('click', showLanding);
  $('print-btn').addEventListener('click', () => window.print());

  // Example ticker chips
  document.querySelectorAll('.example-tickers span').forEach(chip => {
    chip.addEventListener('click', () => {
      $('ticker-input').value = chip.textContent.trim();
      submitTicker();
    });
  });

  initLandingEffects();
});

// ── Landing page interactive effects ────────────────────────────────────────
function initLandingEffects() {
  // Animated stat counters
  document.querySelectorAll('.hs-num').forEach(el => {
    const target = parseFloat(el.dataset.target);
    const suffix = el.dataset.suffix || '';
    const dur = 1400;
    const start = performance.now();
    const tick = now => {
      const t = Math.min(1, (now - start) / dur);
      const eased = 1 - Math.pow(1 - t, 3);
      el.textContent = Math.round(target * eased) + suffix;
      if (t < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });

  // Live market index ticks (subtle drift every ~2.5s)
  const tiles = document.querySelectorAll('.mkt-tile');
  if (tiles.length) {
    setInterval(() => {
      tiles.forEach(tile => {
        const valEl = tile.querySelector('.mkt-val');
        const chgEl = tile.querySelector('.mkt-chg');
        const base  = parseFloat(valEl.dataset.mkt);
        const drift = parseFloat(valEl.dataset.drift);
        const delta = (Math.random() - 0.5) * drift * 2;
        const next  = base + delta;
        valEl.dataset.mkt = next.toFixed(2);
        const txt = next < 100 ? next.toFixed(2) : next.toFixed(2);
        const isPct = valEl.textContent.includes('%');
        const isUSD = valEl.textContent.startsWith('$');
        valEl.textContent = (isUSD ? '$' : '') + Number(txt).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}) + (isPct ? '%' : '');
        // Flash class for the tick
        valEl.classList.remove('flash-up','flash-down');
        void valEl.offsetWidth;
        valEl.classList.add(delta >= 0 ? 'flash-up' : 'flash-down');
        // Nudge change badge
        if (chgEl) {
          const pct = (delta / base * 100);
          chgEl.classList.toggle('up',   pct >= 0);
          chgEl.classList.toggle('down', pct <  0);
        }
      });
    }, 2500);
  }

  // Mouse parallax tilt on the landing card
  const card = document.querySelector('.landing-card');
  const landing = document.getElementById('landing');
  if (card && landing) {
    landing.addEventListener('mousemove', e => {
      const rect = card.getBoundingClientRect();
      const cx = rect.left + rect.width  / 2;
      const cy = rect.top  + rect.height / 2;
      const dx = (e.clientX - cx) / rect.width;
      const dy = (e.clientY - cy) / rect.height;
      const rx = (-dy * 4).toFixed(2);
      const ry = ( dx * 4).toFixed(2);
      card.style.transform = `perspective(1200px) rotateX(${rx}deg) rotateY(${ry}deg) translateY(0)`;
    });
    landing.addEventListener('mouseleave', () => {
      card.style.transform = '';
    });
  }
}

// ── Navigation helpers ────────────────────────────────────────────────────────
function clearSectorTheme() {
  document.body.className = document.body.className
    .split(' ').filter(c => !c.startsWith('sector-')).join(' ');
}

function applySectorTheme(sector) {
  clearSectorTheme();
  const s = (sector || '').toLowerCase();
  if (s.includes('information technology') || s.includes('technology') || s.includes('software') || s.includes('semiconductor')) {
    document.body.classList.add('sector-tech');
  } else if (s.includes('financ') || s.includes('bank') || s.includes('insurance') || s.includes('real estate')) {
    document.body.classList.add('sector-financials');
  } else if (s.includes('energy') || s.includes('oil') || s.includes('gas') || s.includes('utilities')) {
    document.body.classList.add('sector-energy');
  } else if (s.includes('health') || s.includes('pharma') || s.includes('biotech') || s.includes('medical')) {
    document.body.classList.add('sector-healthcare');
  } else if (s.includes('consumer')) {
    document.body.classList.add('sector-consumer');
  } else if (s.includes('industrial') || s.includes('material') || s.includes('manufactur')) {
    document.body.classList.add('sector-industrials');
  } else if (s.includes('communication') || s.includes('media') || s.includes('telecom')) {
    document.body.classList.add('sector-comms');
  }
}

function showLanding() {
  if (currentEventSource) { currentEventSource.close(); currentEventSource = null; }
  clearSectorTheme();
  const dl = $('report-deco-left');  if (dl) dl.innerHTML = '';
  const dr = $('report-deco-right'); if (dr) dr.innerHTML = '';
  const pm = document.getElementById('portfolio-memo-area'); if (pm) pm.remove();
  const pb = document.getElementById('portfolio-trigger-area'); if (pb) pb.remove();
  const pmod = document.getElementById('portfolio-modal'); if (pmod) pmod.remove();
  if (typeof teardownPortfolioGutterSwap === 'function') teardownPortfolioGutterSwap();
  clearSectorBackdrop();
  $('landing').style.display = 'flex';
  $('progress-area').style.display = 'none';
  $('report-area').style.display = 'none';
  $('ticker-input').value = '';
  $('ticker-input').focus();
}

function showProgress() {
  $('landing').style.display = 'none';
  $('progress-area').style.display = 'flex';
  $('report-area').style.display = 'none';
}

function showReport() {
  $('landing').style.display = 'none';
  $('progress-area').style.display = 'none';
  $('report-area').style.display = 'block';
}

// ── Submission ────────────────────────────────────────────────────────────────
function submitTicker() {
  const raw = $('ticker-input').value.trim().toUpperCase();
  if (!raw) { highlightInput(); return; }
  if (raw.length > 10 || !/^[A-Z0-9.\-]+$/.test(raw)) {
    showInlineError('Please enter a valid US stock ticker (e.g. AAPL, JPM, XOM).');
    return;
  }
  clearInlineError();
  startReportStream(raw);
}

function highlightInput() {
  const inp = $('ticker-input');
  inp.style.borderColor = 'var(--red)';
  inp.focus();
  setTimeout(() => inp.style.borderColor = '', 1000);
}

function showInlineError(msg) {
  let err = $('inline-error');
  if (!err) {
    err = document.createElement('p');
    err.id = 'inline-error';
    err.style.cssText = 'color:var(--red);font-size:.82rem;margin-top:.4rem;';
    $('ticker-input').parentElement.parentElement.appendChild(err);
  }
  err.textContent = msg;
}
function clearInlineError() {
  const err = $('inline-error');
  if (err) err.textContent = '';
}

// ── SSE Stream ────────────────────────────────────────────────────────────────
function startReportStream(ticker) {
  if (currentEventSource) currentEventSource.close();

  showProgress();
  setProgress(0, 7, `Starting analysis for ${ticker}…`);

  const es = new EventSource(`/api/report/stream?ticker=${encodeURIComponent(ticker)}`);
  currentEventSource = es;

  es.addEventListener('progress', e => {
    const d = JSON.parse(e.data);
    setProgress(d.stage, d.total, d.message);
  });

  es.addEventListener('report', e => {
    es.close();
    currentEventSource = null;
    const d = JSON.parse(e.data);
    if (d.report) {
      currentReport = d.report;
      renderReport(d.report, d.warnings || []);
    } else {
      renderError('Report data missing in server response.');
    }
  });

  es.addEventListener('error', e => {
    es.close();
    currentEventSource = null;
    let msg = 'Connection error. Please try again.';
    try {
      const d = JSON.parse(e.data);
      if (d && d.error) msg = d.error;
    } catch (_) {}
    renderError(msg);
  });

  es.onerror = () => {
    if (es.readyState === EventSource.CLOSED) return;
    es.close();
    currentEventSource = null;
    renderError('Connection lost. Please try again.');
  };
}

function setProgress(stage, total, message) {
  const pct = total > 0 ? Math.round((stage / total) * 100) : 0;
  $('progress-fill').style.width = pct + '%';
  $('progress-label').textContent = message;
  $('progress-stage').textContent = stage > 0 ? `Step ${stage} of ${total}` : '';
}

// ── Report Rendering ──────────────────────────────────────────────────────────
function renderError(msg) {
  showReport();
  $('report-container').innerHTML = `
    <div class="error-card">
      <div class="error-icon">⚠</div>
      <div class="error-title">Unable to Generate Report</div>
      <div class="error-msg">${escHtml(msg)}</div>
      <br>
      <button class="btn-secondary" onclick="showLanding()">Try Another Ticker</button>
    </div>`;
}

function renderReport(r, warnings) {
  applySectorTheme(r.sector);
  applySectorBackdrop(r.sector);
  renderSideDecorations(r);
  showReport();

  // Update browser title
  document.title = `${r.ticker} — Equity Research Memo`;

  const upside = r.upside_pct;
  const upsideClass = upside === null ? 'neutral' : upside > 5 ? 'positive' : upside < -5 ? 'negative' : 'neutral';
  const upsideStr   = upside !== null ? `${upside > 0 ? '+' : ''}${upside.toFixed(1)}%` : 'N/M';

  const recClass = (r.recommendation || 'hold').toLowerCase();

  let html = '';

  // ── Warnings ────────────────────────────────────────────────────────────────
  if (warnings.length) {
    html += `<div class="warnings-box">`;
    warnings.forEach(w => { html += `<p>⚠ ${escHtml(w)}</p>`; });
    html += `</div>`;
  }

  // ── Memo ────────────────────────────────────────────────────────────────────
  html += `<div class="memo">`;

  // Header
  const price = fmtUSD(r.current_price);
  const fvBase = r.fair_value_base ? fmtUSD(r.fair_value_base) : 'N/M';
  const fvLow  = r.fair_value_low  ? fmtUSD(r.fair_value_low)  : '—';
  const fvHigh = r.fair_value_high ? fmtUSD(r.fair_value_high) : '—';

  const sectorBg = getSectorBackground(r.sector);
  const logoDomain = getCompanyDomain(r.ticker) || domainFromWebsite(r.website);
  const logoHtml = logoDomain
    ? `<img class="header-logo" src="https://t2.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=https://${logoDomain}&size=128" alt="" onerror="this.style.display='none'">`
    : '';

  html += `
  <div class="memo-header" style="position:relative;overflow:hidden;">
    ${sectorBg}
    ${logoHtml}
    <div class="memo-header-top" style="position:relative;z-index:2;">
      <div class="memo-ticker-block">
        <div class="memo-ticker">${escHtml(r.ticker)}</div>
        <div class="memo-company">${escHtml(r.company_name)}</div>
        <div class="memo-meta">${escHtml(r.sector)} · ${escHtml(r.exchange || 'US')} · Generated ${escHtml(r.generated_at)}</div>
      </div>
      <div class="rec-badge ${recClass}">
        <span class="rec-label">${escHtml(r.recommendation)}</span>
        <span class="rec-conf">${escHtml(r.confidence)} CONFIDENCE</span>
      </div>
    </div>
    <div class="memo-stats-strip" style="position:relative;z-index:2;">
      <div class="stat-item">
        <div class="stat-label">Current Price</div>
        <div class="stat-value">${escHtml(price)}</div>
      </div>
      <div class="stat-item">
        <div class="stat-label">Fair Value (Base)</div>
        <div class="stat-value">${escHtml(fvBase)}</div>
      </div>
      <div class="stat-item">
        <div class="stat-label">FV Range</div>
        <div class="stat-value">${escHtml(fvLow)} – ${escHtml(fvHigh)}</div>
      </div>
      <div class="stat-item">
        <div class="stat-label">Upside / Downside</div>
        <div class="stat-value ${upsideClass}">${escHtml(upsideStr)}</div>
      </div>
      <div class="stat-item">
        <div class="stat-label">Peers Used</div>
        <div class="stat-value">${r.peer_count}</div>
      </div>
      <div class="stat-item">
        <div class="stat-label">Data Completeness</div>
        <div class="stat-value">${r.data_completeness_pct}%</div>
      </div>
    </div>
  </div>`;

  // Body
  html += `<div class="memo-body">`;

  // Recommendation Rationale
  html += `<div class="rationale-section">
    <div class="section-title">Recommendation Rationale</div>
    <p class="rationale-text">${escHtml(r.rationale)}</p>
  </div>`;

  // Price return charts (if data available)
  if (r.price_history && r.price_history.dates && r.price_history.dates.length > 0) {
    html += `<div class="memo-section chart-section">
      <div class="section-title">Performance Analysis</div>
      <div class="charts-layout">
        <div class="chart-column col-price">
          <div class="chart-title">Price Return vs. S&amp;P 500</div>
          <div class="chart-wrapper"><canvas id="price-return-chart"></canvas></div>
        </div>
        <div class="chart-column col-heatmap">
          <div class="chart-title">Monthly Returns</div>
          <div class="heatmap-wrapper"><canvas id="heatmap-chart"></canvas></div>
        </div>
      </div>
    </div>`;
  }

  // FV strip
  html += `
  <div class="fv-strip">
    <div class="fv-item"><div class="fv-lbl">Low</div><div class="fv-val">${escHtml(fvLow)}</div></div>
    <div class="fv-divider"></div>
    <div class="fv-item"><div class="fv-lbl">Base</div><div class="fv-val">${escHtml(fvBase)}</div></div>
    <div class="fv-divider"></div>
    <div class="fv-item"><div class="fv-lbl">High</div><div class="fv-val">${escHtml(fvHigh)}</div></div>
    <div class="fv-divider"></div>
    <div class="fv-item">
      <div class="fv-lbl">Upside / Downside</div>
      <div><span class="upside-pill ${upsideClass}">${escHtml(upsideStr)}</span></div>
    </div>
    <div class="fv-divider"></div>
    <div class="fv-item">
      <div class="fv-lbl">Methods</div>
      <div class="fv-val" style="font-size:.78rem;font-family:var(--font)">${escHtml((r.valuation_methods || []).map(m => m.toUpperCase().replace('_', '/')).join(', ') || 'N/M')}</div>
    </div>
  </div>`;

  // Two-column: description + thesis
  html += `<div class="grid-2">`;

  // Description
  html += `<div class="memo-section">
    <div class="section-title">Business Description</div>
    <div class="section-text">${escHtml(r.description)}</div>
    <br>
    <div class="section-title" style="margin-top:.5rem">Revenue Model</div>
    <div class="section-text">${escHtml(r.revenue_model)}</div>
  </div>`;

  // Thesis
  html += `<div class="memo-section">
    <div class="section-title">Investment Thesis</div>
    <ul class="bullet-list">`;
  (r.investment_thesis || []).forEach(t => { html += `<li>${escHtml(t)}</li>`; });
  html += `</ul>
    <br>
    <div class="section-title" style="margin-top:.5rem">Sector Overview</div>
    <div class="section-text">${escHtml(r.sector_overview)}</div>
  </div>`;

  html += `</div>`; // end grid-2

  // Risks and Catalysts
  html += `<div class="grid-2">
    <div class="memo-section">
      <div class="section-title">Key Risks</div>
      <ul class="bullet-list">`;
  (r.key_risks || []).forEach(risk => { html += `<li>${escHtml(risk)}</li>`; });
  html += `</ul></div>
    <div class="memo-section">
      <div class="section-title">Key Catalysts</div>
      <ul class="bullet-list">`;
  (r.key_catalysts || []).forEach(cat => { html += `<li>${escHtml(cat)}</li>`; });
  html += `</ul></div>
  </div>`; // end grid-2

  // Valuation table
  html += `<div class="memo-section">
    <div class="section-title">Valuation &amp; Quality vs. ${escHtml(r.sector)} Sector Peers (${r.peer_count} companies)</div>
    ${buildTable(r.metrics_table)}
  </div>`;

  // Footnotes
  html += `<div class="footnotes">`;
  (r.caveats || []).forEach((c, i) => {
    html += `<div class="footnote">${i + 1}. ${escHtml(c)}</div>`;
  });
  html += `</div>`;

  html += `</div>`; // end memo-body

  // Footer
  html += `<div class="memo-footer">
    Advanced Quant Methods Project by Laraib Nisar
  </div>`;

  html += `</div>`; // end memo

  $('report-container').innerHTML = html;

  // Render price chart if data is available
  if (r.price_history && r.price_history.dates && r.price_history.dates.length > 0) {
    renderPriceChart(r.price_history);
  }

  // Portfolio builder hook
  if (typeof portfolioSetAnchor === 'function') portfolioSetAnchor(r);
  if (typeof injectPortfolioButton === 'function') injectPortfolioButton();

  showReport();
}

// ── Side decorations (left/right gutter panels around the memo) ──────────────
function renderSideDecorations(r) {
  const left  = $('report-deco-left');
  const right = $('report-deco-right');
  if (!left || !right) return;

  const upside = r.upside_pct;
  const upsideClass = upside === null || upside === undefined ? '' : upside > 0 ? 'up' : upside < 0 ? 'down' : '';
  const upsideStr   = (upside !== null && upside !== undefined) ? `${upside > 0 ? '+' : ''}${upside.toFixed(1)}%` : 'N/M';

  const accent = sectorAccent(r.sector);
  const sparkData = (r.price_history && r.price_history.stock) ? r.price_history.stock : null;
  const spark = sparkData ? sparklineSVG(sparkData, accent) : sectorIconSVG(r.sector, accent);

  const ph = r.price_history;
  let stockTotal = null, sp500Total = null;
  if (ph && ph.stock && ph.stock.length) stockTotal = ph.stock[ph.stock.length - 1];
  if (ph && ph.sp500 && ph.sp500.length) sp500Total = ph.sp500[ph.sp500.length - 1];

  const fmtPct = v => v === null || v === undefined ? '—' : (v > 0 ? '+' : '') + v.toFixed(1) + '%';

  // ── LEFT GUTTER ─────────────────────────────────────────────────────────────
  left.innerHTML = `
    <div class="deco-panel">
      <div class="deco-panel-label">${escHtml(r.ticker)} · 1Y Return</div>
      ${spark}
      <div class="deco-panel-value ${stockTotal !== null && stockTotal >= 0 ? 'up' : 'down'}">${fmtPct(stockTotal)}</div>
      <div class="deco-panel-sub">vs S&P 500 ${fmtPct(sp500Total)}</div>
    </div>

    <div class="deco-panel">
      <div class="deco-panel-label">Recommendation</div>
      ${recBadgeSVG(r.recommendation, accent)}
      <div class="deco-panel-value" style="color:${recColor(r.recommendation)}">${escHtml((r.recommendation || '').toUpperCase())}</div>
      <div class="deco-panel-sub">${escHtml(r.confidence || '')} confidence</div>
    </div>

    <div class="deco-vertical-text">${escHtml(r.sector || 'Equity Research')}</div>
  `;

  // ── RIGHT GUTTER ────────────────────────────────────────────────────────────
  const fvBase = r.fair_value_base ? `$${r.fair_value_base.toFixed(2)}` : 'N/M';
  const cur    = r.current_price   ? `$${r.current_price.toFixed(2)}`   : 'N/M';

  right.innerHTML = `
    <div class="deco-vertical-text">${escHtml(r.ticker)} · ${escHtml(r.exchange || 'US')}</div>

    <div class="deco-panel">
      <div class="deco-panel-label">Fair Value</div>
      ${gaugeSVG(r.current_price, r.fair_value_base, accent)}
      <div class="deco-panel-value">${escHtml(fvBase)}</div>
      <div class="deco-panel-sub">Current ${escHtml(cur)}</div>
    </div>

    <div class="deco-panel">
      <div class="deco-panel-label">Upside / Downside</div>
      ${barIndicatorSVG(upside, accent)}
      <div class="deco-panel-value ${upsideClass}">${escHtml(upsideStr)}</div>
      <div class="deco-panel-sub">${(r.peer_count || 0)} peers analysed</div>
    </div>
  `;
}

// Sector → primary accent color for SVG decorations
function sectorAccent(sector) {
  const s = (sector || '').toLowerCase();
  if (s.includes('information technology') || s.includes('technology') || s.includes('software') || s.includes('semiconductor')) return '#2a79d3';
  if (s.includes('financ') || s.includes('bank') || s.includes('insurance') || s.includes('real estate')) return '#1a7f64';
  if (s.includes('energy') || s.includes('oil') || s.includes('gas') || s.includes('utilities')) return '#c17f24';
  if (s.includes('health') || s.includes('pharma') || s.includes('biotech') || s.includes('medical')) return '#0e8a8a';
  if (s.includes('consumer')) return '#7c3aed';
  if (s.includes('industrial') || s.includes('material') || s.includes('manufactur')) return '#475569';
  if (s.includes('communication') || s.includes('media') || s.includes('telecom')) return '#6d28d9';
  return '#1e5fa8';
}

function recColor(rec) {
  const r = (rec || '').toLowerCase();
  if (r === 'buy')  return '#1a6b3c';
  if (r === 'sell') return '#7a1e1c';
  return '#7c5c10';
}

// SVG: sparkline of cumulative returns
function sparklineSVG(values, color) {
  if (!values || values.length < 2) return '';
  const w = 220, h = 60, pad = 4;
  const min = Math.min(...values), max = Math.max(...values);
  const range = (max - min) || 1;
  const stepX = (w - 2 * pad) / (values.length - 1);
  const points = values.map((v, i) => {
    const x = pad + i * stepX;
    const y = pad + (h - 2 * pad) * (1 - (v - min) / range);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  const path = `M ${points.split(' ').join(' L ')}`;
  const filled = `${path} L ${w - pad},${h - pad} L ${pad},${h - pad} Z`;
  return `<svg class="deco-panel-svg" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">
    <defs><linearGradient id="sparkFill" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="${color}" stop-opacity="0.25"/>
      <stop offset="100%" stop-color="${color}" stop-opacity="0"/>
    </linearGradient></defs>
    <path d="${filled}" fill="url(#sparkFill)"/>
    <path d="${path}" fill="none" stroke="${color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>`;
}

// SVG: small recommendation badge (chevrons up/down/sideways)
function recBadgeSVG(rec, color) {
  const r = (rec || '').toLowerCase();
  const w = 220, h = 60;
  if (r === 'buy') {
    return `<svg class="deco-panel-svg" viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg">
      <g stroke="#1a6b3c" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="40,40 70,15 100,40"/>
        <polyline points="80,40 110,15 140,40" opacity="0.6"/>
        <polyline points="120,40 150,15 180,40" opacity="0.3"/>
      </g>
    </svg>`;
  }
  if (r === 'sell') {
    return `<svg class="deco-panel-svg" viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg">
      <g stroke="#7a1e1c" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="40,20 70,45 100,20"/>
        <polyline points="80,20 110,45 140,20" opacity="0.6"/>
        <polyline points="120,20 150,45 180,20" opacity="0.3"/>
      </g>
    </svg>`;
  }
  // Hold
  return `<svg class="deco-panel-svg" viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg">
    <g stroke="${color}" stroke-width="2" fill="none" stroke-linecap="round">
      <line x1="40" y1="30" x2="180" y2="30" opacity="0.35"/>
      <line x1="60" y1="20" x2="160" y2="20" opacity="0.25"/>
      <line x1="60" y1="40" x2="160" y2="40" opacity="0.25"/>
      <circle cx="110" cy="30" r="6" fill="${color}" opacity="0.85" stroke="none"/>
    </g>
  </svg>`;
}

// SVG: Half-circle gauge showing current price vs fair value
function gaugeSVG(currentPrice, fairValue, color) {
  const w = 220, h = 80;
  const cx = w / 2, cy = 65, r = 50;
  let pct = 0.5;
  if (currentPrice && fairValue && fairValue > 0) {
    pct = Math.max(0.05, Math.min(0.95, currentPrice / (2 * fairValue)));
  }
  const angle = Math.PI * (1 - pct);
  const x = cx + r * Math.cos(angle);
  const y = cy - r * Math.sin(angle);
  return `<svg class="deco-panel-svg" viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg">
    <path d="M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}"
          fill="none" stroke="${color}" stroke-opacity="0.18" stroke-width="6" stroke-linecap="round"/>
    <path d="M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${x.toFixed(1)} ${y.toFixed(1)}"
          fill="none" stroke="${color}" stroke-width="6" stroke-linecap="round"/>
    <circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="5" fill="${color}"/>
    <text x="${cx - r}" y="${cy + 14}" font-family="JetBrains Mono, monospace" font-size="9" fill="#9aa3af">UNDER</text>
    <text x="${cx + r - 22}" y="${cy + 14}" font-family="JetBrains Mono, monospace" font-size="9" fill="#9aa3af">OVER</text>
  </svg>`;
}

// SVG: horizontal bar showing upside/downside relative to a centered zero line
function barIndicatorSVG(upsidePct, color) {
  const w = 220, h = 60;
  const cx = w / 2, cy = h / 2;
  const maxAbs = 50;
  const up = Math.max(-maxAbs, Math.min(maxAbs, upsidePct || 0));
  const barW = (Math.abs(up) / maxAbs) * (w / 2 - 20);
  const isUp = up >= 0;
  const barColor = isUp ? '#1a7f64' : '#b92b27';
  return `<svg class="deco-panel-svg" viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg">
    <line x1="20" y1="${cy}" x2="${w - 20}" y2="${cy}" stroke="${color}" stroke-opacity="0.15" stroke-width="2" stroke-linecap="round"/>
    <line x1="${cx}" y1="${cy - 10}" x2="${cx}" y2="${cy + 10}" stroke="${color}" stroke-opacity="0.4" stroke-width="2"/>
    ${isUp
      ? `<rect x="${cx}" y="${cy - 6}" width="${barW.toFixed(1)}" height="12" rx="2" fill="${barColor}"/>`
      : `<rect x="${(cx - barW).toFixed(1)}" y="${cy - 6}" width="${barW.toFixed(1)}" height="12" rx="2" fill="${barColor}"/>`}
    <text x="20"  y="${cy + 22}" font-family="JetBrains Mono, monospace" font-size="9" fill="#9aa3af">-50%</text>
    <text x="${w - 36}" y="${cy + 22}" font-family="JetBrains Mono, monospace" font-size="9" fill="#9aa3af">+50%</text>
  </svg>`;
}

// SVG: fallback sector icon (used when no price history is available)
function sectorIconSVG(sector, color) {
  const w = 220, h = 60;
  const s = (sector || '').toLowerCase();
  if (s.includes('tech')) {
    return `<svg class="deco-panel-svg" viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg">
      <g stroke="${color}" stroke-width="2" fill="none">
        <rect x="80" y="15" width="60" height="30" rx="3"/>
        <circle cx="95" cy="30" r="3" fill="${color}"/>
        <circle cx="110" cy="30" r="3" fill="${color}"/>
        <circle cx="125" cy="30" r="3" fill="${color}"/>
      </g>
    </svg>`;
  }
  return `<svg class="deco-panel-svg" viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg">
    <path d="M20,45 L60,30 L100,38 L140,18 L180,25 L200,15" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>`;
}

// ── Sector background SVGs ────────────────────────────────────────────────────
function getSectorBackground(sector) {
  const s = (sector || '').toLowerCase();

  // Technology — circuit board traces
  if (s.includes('information technology') || s.includes('technology') || s.includes('software') || s.includes('semiconductor')) {
    return `<svg class="header-bg-svg" viewBox="0 0 900 180" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid slice">
      <g stroke="rgba(255,255,255,0.07)" stroke-width="1.5" fill="none">
        <line x1="0" y1="40" x2="120" y2="40"/><circle cx="120" cy="40" r="4" fill="rgba(255,255,255,0.07)"/>
        <line x1="120" y1="40" x2="120" y2="100"/><line x1="120" y1="100" x2="260" y2="100"/>
        <circle cx="260" cy="100" r="4" fill="rgba(255,255,255,0.07)"/><line x1="260" y1="100" x2="260" y2="60"/>
        <line x1="260" y1="60" x2="400" y2="60"/><circle cx="400" cy="60" r="4" fill="rgba(255,255,255,0.07)"/>
        <line x1="400" y1="60" x2="400" y2="130"/><line x1="400" y1="130" x2="540" y2="130"/>
        <circle cx="540" cy="130" r="4" fill="rgba(255,255,255,0.07)"/><line x1="540" y1="130" x2="540" y2="80"/>
        <line x1="540" y1="80" x2="700" y2="80"/><circle cx="700" cy="80" r="4" fill="rgba(255,255,255,0.07)"/>
        <line x1="700" y1="80" x2="700" y2="40"/><line x1="700" y1="40" x2="900" y2="40"/>
        <line x1="80" y1="0" x2="80" y2="40"/><line x1="200" y1="100" x2="200" y2="180"/>
        <line x1="320" y1="60" x2="320" y2="0"/><line x1="460" y1="130" x2="460" y2="180"/>
        <line x1="620" y1="80" x2="620" y2="0"/><line x1="760" y1="40" x2="760" y2="180"/>
        <circle cx="80" cy="0" r="5" fill="rgba(42,121,211,0.25)"/><circle cx="200" cy="180" r="5" fill="rgba(42,121,211,0.25)"/>
        <circle cx="320" cy="0" r="5" fill="rgba(42,121,211,0.25)"/><circle cx="460" cy="180" r="5" fill="rgba(42,121,211,0.25)"/>
        <circle cx="620" cy="0" r="5" fill="rgba(42,121,211,0.25)"/><circle cx="760" cy="180" r="5" fill="rgba(42,121,211,0.25)"/>
      </g>
    </svg>`;
  }

  // Financials — candlestick chart
  if (s.includes('financ') || s.includes('bank') || s.includes('insurance') || s.includes('real estate')) {
    return `<svg class="header-bg-svg" viewBox="0 0 900 180" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid slice">
      <g opacity="0.12">
        ${[
          [60,120,60,30,50,65,'rgba(26,127,100,1)'],
          [120,115,35,25,110,50,'rgba(26,127,100,1)'],
          [180,130,45,20,170,60,'rgba(185,43,39,1)'],
          [240,110,50,30,230,55,'rgba(26,127,100,1)'],
          [300,105,55,25,290,42,'rgba(26,127,100,1)'],
          [360,125,45,22,350,65,'rgba(185,43,39,1)'],
          [420,100,60,28,410,45,'rgba(26,127,100,1)'],
          [480,95,50,20,470,38,'rgba(26,127,100,1)'],
          [540,118,48,25,530,62,'rgba(185,43,39,1)'],
          [600,90,55,22,590,35,'rgba(26,127,100,1)'],
          [660,85,52,18,650,32,'rgba(26,127,100,1)'],
          [720,110,42,20,710,55,'rgba(185,43,39,1)'],
          [780,80,58,25,770,30,'rgba(26,127,100,1)'],
          [840,75,48,22,830,28,'rgba(26,127,100,1)'],
        ].map(([x, top, h, bh, bx, bt, col]) =>
          `<line x1="${x}" y1="${top}" x2="${x}" y2="${top+h}" stroke="${col}" stroke-width="1.5"/>
           <rect x="${bx}" y="${bt}" width="20" height="${bh}" fill="${col}" rx="1"/>`
        ).join('')}
      </g>
    </svg>`;
  }

  // Energy — sine wave / pulse
  if (s.includes('energy') || s.includes('oil') || s.includes('gas') || s.includes('utilities')) {
    return `<svg class="header-bg-svg" viewBox="0 0 900 180" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid slice">
      <g fill="none" stroke="rgba(255,255,255,0.08)" stroke-width="1.5">
        <path d="M0,90 C50,90 50,30 100,30 C150,30 150,90 200,90 C250,90 250,140 300,140 C350,140 350,90 400,90 C450,90 450,40 500,40 C550,40 550,90 600,90 C650,90 650,130 700,130 C750,130 750,90 800,90 C850,90 850,50 900,50"/>
        <path d="M0,110 C60,110 60,50 120,50 C180,50 180,110 240,110 C300,110 300,155 360,155 C420,155 420,110 480,110 C540,110 540,60 600,60 C660,60 660,110 720,110 C780,110 780,148 840,148 C880,148 890,118 900,115" stroke-opacity="0.05"/>
      </g>
      <g fill="rgba(255,255,255,0.04)">
        <path d="M0,90 C50,90 50,30 100,30 C150,30 150,90 200,90 C250,90 250,140 300,140 C350,140 350,90 400,90 C450,90 450,40 500,40 C550,40 550,90 600,90 C650,90 650,130 700,130 C750,130 750,90 800,90 C850,90 850,50 900,50 L900,180 L0,180 Z"/>
      </g>
    </svg>`;
  }

  // Healthcare — ECG / pulse line
  if (s.includes('health') || s.includes('pharma') || s.includes('biotech') || s.includes('medical')) {
    return `<svg class="header-bg-svg" viewBox="0 0 900 180" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid slice">
      <g fill="none" stroke="rgba(255,255,255,0.09)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
        <path d="M0,90 L80,90 L100,90 L115,40 L130,140 L145,90 L160,90 L240,90 L260,90 L275,40 L290,140 L305,90 L320,90 L400,90 L420,90 L435,40 L450,140 L465,90 L480,90 L560,90 L580,90 L595,40 L610,140 L625,90 L640,90 L720,90 L740,90 L755,40 L770,140 L785,90 L800,90 L900,90"/>
      </g>
      <g fill="none" stroke="rgba(255,255,255,0.04)" stroke-width="1.2">
        <path d="M0,110 L80,110 L100,110 L115,70 L130,150 L145,110 L160,110 L240,110 L260,110 L275,70 L290,150 L305,110 L320,110 L400,110 L420,110 L435,70 L450,150 L465,110 L480,110 L560,110 L580,110 L595,70 L610,150 L625,110 L640,110 L720,110 L740,110 L755,70 L770,150 L785,110 L800,110 L900,110"/>
      </g>
    </svg>`;
  }

  // Consumer / Industrials / Materials — bar/area chart
  if (s.includes('consumer') || s.includes('industrial') || s.includes('material') || s.includes('manufactur')) {
    return `<svg class="header-bg-svg" viewBox="0 0 900 180" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid slice">
      <g fill="rgba(255,255,255,0.06)">
        <rect x="30"  y="110" width="28" height="70" rx="2"/>
        <rect x="90"  y="85"  width="28" height="95" rx="2"/>
        <rect x="150" y="95"  width="28" height="85" rx="2"/>
        <rect x="210" y="70"  width="28" height="110" rx="2"/>
        <rect x="270" y="80"  width="28" height="100" rx="2"/>
        <rect x="330" y="60"  width="28" height="120" rx="2"/>
        <rect x="390" y="65"  width="28" height="115" rx="2"/>
        <rect x="450" y="50"  width="28" height="130" rx="2"/>
        <rect x="510" y="55"  width="28" height="125" rx="2"/>
        <rect x="570" y="40"  width="28" height="140" rx="2"/>
        <rect x="630" y="45"  width="28" height="135" rx="2"/>
        <rect x="690" y="30"  width="28" height="150" rx="2"/>
        <rect x="750" y="35"  width="28" height="145" rx="2"/>
        <rect x="810" y="20"  width="28" height="160" rx="2"/>
        <rect x="862" y="25"  width="28" height="155" rx="2"/>
      </g>
      <path d="M44,110 L104,85 L164,95 L224,70 L284,80 L344,60 L404,65 L464,50 L524,55 L584,40 L644,45 L704,30 L764,35 L824,20 L876,25"
            fill="none" stroke="rgba(255,255,255,0.12)" stroke-width="1.5"/>
    </svg>`;
  }

  // Communication / Media — signal waves
  if (s.includes('communication') || s.includes('media') || s.includes('telecom')) {
    return `<svg class="header-bg-svg" viewBox="0 0 900 180" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid slice">
      <g fill="none" stroke="rgba(255,255,255,0.07)" stroke-width="1.5">
        <path d="M450,90 m-20,0 a20,20 0 1,1 40,0 a20,20 0 1,1 -40,0"/>
        <path d="M450,90 m-50,0 a50,50 0 0,1 100,0" stroke-dasharray="4,3"/>
        <path d="M450,90 m-80,0 a80,80 0 0,1 160,0"/>
        <path d="M450,90 m-115,0 a115,115 0 0,1 230,0" stroke-dasharray="4,3"/>
        <path d="M450,90 m-150,0 a150,150 0 0,1 300,0"/>
        <path d="M450,90 m-190,0 a190,190 0 0,1 380,0" stroke-dasharray="4,3"/>
        <path d="M450,90 m-230,0 a230,230 0 0,1 460,0"/>
        <path d="M450,90 m-270,0 a270,270 0 0,1 540,0" stroke-dasharray="4,3"/>
        <path d="M450,90 m-310,0 a310,310 0 0,1 620,0"/>
        <path d="M450,90 m-355,0 a355,355 0 0,1 710,0" stroke-dasharray="4,3"/>
        <path d="M450,90 m-400,0 a400,400 0 0,1 800,0"/>
        <path d="M450,90 m-440,0 a440,440 0 0,1 880,0" stroke-dasharray="4,3"/>
      </g>
    </svg>`;
  }

  // Default — subtle price-return line
  return `<svg class="header-bg-svg" viewBox="0 0 900 180" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid slice">
    <defs>
      <linearGradient id="defFill" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="rgba(255,255,255,0.06)"/>
        <stop offset="100%" stop-color="rgba(255,255,255,0)"/>
      </linearGradient>
    </defs>
    <path d="M0,140 C80,135 120,120 200,105 C280,90 320,95 400,80 C480,65 520,60 600,48 C680,36 720,38 800,28 C850,22 880,18 900,15 L900,180 L0,180 Z" fill="url(#defFill)"/>
    <path d="M0,140 C80,135 120,120 200,105 C280,90 320,95 400,80 C480,65 520,60 600,48 C680,36 720,38 800,28 C850,22 880,18 900,15" fill="none" stroke="rgba(255,255,255,0.12)" stroke-width="1.5"/>
  </svg>`;
}

// ── Company logo domain lookup ─────────────────────────────────────────────────
function getCompanyDomain(ticker) {
  const map = {
    AAPL:'apple.com', MSFT:'microsoft.com', GOOGL:'google.com', GOOG:'google.com',
    META:'meta.com', AMZN:'amazon.com', NVDA:'nvidia.com', TSLA:'tesla.com',
    NFLX:'netflix.com', ADBE:'adobe.com', CRM:'salesforce.com', ORCL:'oracle.com',
    INTC:'intel.com', AMD:'amd.com', QCOM:'qualcomm.com', TXN:'ti.com',
    AVGO:'broadcom.com', AMAT:'appliedmaterials.com', MU:'micron.com',
    JPM:'jpmorganchase.com', BAC:'bankofamerica.com', WFC:'wellsfargo.com',
    GS:'goldmansachs.com', MS:'morganstanley.com', C:'citigroup.com',
    BLK:'blackrock.com', AXP:'americanexpress.com', V:'visa.com', MA:'mastercard.com',
    BRK:'berkshirehathaway.com',
    JNJ:'jnj.com', PFE:'pfizer.com', MRK:'merck.com', ABBV:'abbvie.com',
    LLY:'lilly.com', BMY:'bms.com', AMGN:'amgen.com', GILD:'gilead.com',
    UNH:'unitedhealthgroup.com', CVS:'cvshealth.com',
    XOM:'exxonmobil.com', CVX:'chevron.com', COP:'conocophillips.com',
    SLB:'slb.com', EOG:'eogresources.com', PXD:'pioneernaturalresources.com',
    NEE:'nexteraenergy.com', DUK:'duke-energy.com', SO:'southerncompany.com',
    WMT:'walmart.com', COST:'costco.com', TGT:'target.com', HD:'homedepot.com',
    LOW:'lowes.com', NKE:'nike.com', SBUX:'starbucks.com', MCD:'mcdonalds.com',
    PG:'pg.com', KO:'coca-cola.com', PEP:'pepsico.com', PM:'pmi.com',
    CAT:'caterpillar.com', DE:'deere.com', BA:'boeing.com', GE:'ge.com',
    MMM:'3m.com', HON:'honeywell.com', RTX:'rtx.com', LMT:'lockheedmartin.com',
    T:'att.com', VZ:'verizon.com', CMCSA:'comcast.com', DIS:'disney.com',
    NWSA:'newscorp.com',
  };
  return map[ticker.toUpperCase()] || null;
}

function renderPriceChart(data) {
  const priceCanvas = $('price-return-chart');
  const heatmapCanvas = $('heatmap-chart');

  if (!priceCanvas || !heatmapCanvas || !data.dates || !data.stock || !data.sp500) return;

  const ticker = currentReport ? currentReport.ticker : 'STOCK';

  // Keep all dates, we'll thin out the display labels
  const allDates = data.dates;

  // ═══════════════════════════════════════════════════════════════════════════════════
  // CHART 1: Price Return Line Chart
  // ═══════════════════════════════════════════════════════════════════════════════════
  new Chart(priceCanvas, {
    type: 'line',
    data: {
      labels: allDates,
      datasets: [
        {
          label: ticker,
          data: data.stock,
          borderColor: 'var(--blue-lt)',
          backgroundColor: 'rgba(42, 121, 211, 0.05)',
          borderWidth: 2.5,
          tension: 0.4,
          fill: false,
          pointRadius: 0,
          pointHoverRadius: 5,
          pointBackgroundColor: 'var(--blue-lt)',
        },
        {
          label: 'S&P 500',
          data: data.sp500,
          borderColor: '#9ca3af',
          backgroundColor: 'rgba(156, 163, 175, 0.05)',
          borderWidth: 2.5,
          tension: 0.4,
          fill: false,
          pointRadius: 0,
          pointHoverRadius: 5,
          pointBackgroundColor: '#9ca3af',
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      layout: {
        padding: { bottom: 30, left: 0, right: 10, top: 5 },
      },
      plugins: {
        legend: {
          position: 'top',
          labels: {
            font: { family: 'var(--font)', size: 11, weight: '600' },
            color: 'var(--gray-700)',
            padding: 10,
            usePointStyle: true,
            pointStyle: 'rect',
            boxWidth: 10,
            boxHeight: 6,
          },
        },
        tooltip: {
          backgroundColor: 'rgba(13, 27, 42, 0.9)',
          padding: 8,
          titleFont: { family: 'var(--font)', size: 11, weight: '600' },
          bodyFont: { family: 'var(--mono)', size: 10 },
          borderColor: 'var(--blue-lt)',
          borderWidth: 1,
          callbacks: {
            label: function(ctx) {
              const val = ctx.parsed.y;
              return ctx.dataset.label + ': ' + (val >= 0 ? '+' : '') + val.toFixed(1) + '%';
            },
          },
        },
      },
      scales: {
        y: {
          beginAtZero: false,
          ticks: {
            font: { family: 'var(--mono)', size: 9 },
            color: 'var(--gray-400)',
            maxTicksLimit: 5,
            callback: function(value) {
              return (value >= 0 ? '+' : '') + value.toFixed(0) + '%';
            },
          },
          grid: { color: '#f3f4f6', drawBorder: false },
        },
        x: {
          ticks: {
            font: { family: 'var(--mono)', size: 9 },
            color: 'var(--gray-400)',
            maxRotation: 45,
            minRotation: 45,
            stepSize: Math.max(1, Math.floor(allDates.length / 5)),
            callback: function(index) {
              return allDates[index] || '';
            },
          },
          grid: { display: false },
        },
      },
    },
  });

  // ═══════════════════════════════════════════════════════════════════════════════════
  // CHART 2: Monthly Returns Heatmap
  // ═══════════════════════════════════════════════════════════════════════════════════
  const monthlyData = calculateMonthlyReturns(data.dates, data.stock, data.sp500);
  renderHeatmap(heatmapCanvas, monthlyData, ticker);
}

function calculateMonthlyReturns(dates, stockReturns, sp500Returns) {
  const months = {};

  for (let i = 0; i < dates.length; i++) {
    const date = new Date(dates[i]);
    const year = date.getFullYear();
    const month = date.getMonth();
    const key = `${year}-${String(month + 1).padStart(2, '0')}`;

    if (!months[key]) {
      months[key] = { stock: 0, sp500: 0, count: 0 };
    }
    months[key].stock = stockReturns[i];
    months[key].sp500 = sp500Returns[i];
    months[key].count++;
  }

  return months;
}

function renderHeatmap(canvas, monthlyData, ticker) {
  const months = Object.keys(monthlyData).sort();
  const monthLabels = months.map(m => m.split('-')[1] + '/' + m.split('-')[0].slice(-2));

  const stockData = months.map(m => monthlyData[m].stock);
  const sp500Data = months.map(m => monthlyData[m].sp500);
  const outperformance = stockData.map((s, i) => s - sp500Data[i]);

  new Chart(canvas, {
    type: 'bar',
    data: {
      labels: monthLabels,
      datasets: [
        {
          label: 'Outperformance',
          data: outperformance,
          backgroundColor: outperformance.map(v => {
            if (v > 5) return '#10b981';
            if (v > 0) return '#6ee7b7';
            if (v > -5) return '#fed7aa';
            return '#f97316';
          }),
          borderRadius: 3,
          borderSkipped: false,
        },
      ],
    },
    options: {
      indexAxis: undefined,
      responsive: true,
      maintainAspectRatio: true,
      layout: {
        padding: { bottom: 30, left: 0, right: 10, top: 5 },
      },
      plugins: {
        legend: {
          labels: {
            font: { family: 'var(--font)', size: 11, weight: '600' },
            color: 'var(--gray-700)',
            padding: 10,
          },
        },
        tooltip: {
          backgroundColor: 'rgba(13, 27, 42, 0.9)',
          padding: 8,
          titleFont: { family: 'var(--font)', size: 11, weight: '600' },
          bodyFont: { family: 'var(--mono)', size: 10 },
          borderColor: 'var(--blue-lt)',
          borderWidth: 1,
          callbacks: {
            title: function() {
              return ticker + ' vs S&P 500';
            },
            label: function(ctx) {
              const val = ctx.parsed.y;
              return (val >= 0 ? '+' : '') + val.toFixed(1) + '%';
            },
            afterLabel: function(ctx) {
              return ctx.label;
            },
          },
        },
      },
      scales: {
        y: {
          ticks: {
            font: { family: 'var(--mono)', size: 9 },
            color: 'var(--gray-400)',
            maxTicksLimit: 5,
            callback: function(value) {
              return (value >= 0 ? '+' : '') + value.toFixed(0) + '%';
            },
          },
          grid: { color: '#f3f4f6', drawBorder: false },
        },
        x: {
          ticks: {
            font: { family: 'var(--mono)', size: 9 },
            color: 'var(--gray-400)',
            maxRotation: 45,
            minRotation: 45,
          },
          grid: { display: false },
        },
      },
    },
  });
}

function buildTable(rows) {
  if (!rows || !rows.length) return '<p style="color:var(--gray-400);font-size:.82rem">No metrics available.</p>';

  // Group rows
  const valuation = rows.filter(r => ['P/E (TTM)', 'P/E (Fwd)', 'P/B', 'P/S', 'P/FCF', 'EV/EBITDA', 'EV/Sales'].includes(r.metric));
  const leverage  = rows.filter(r => ['D/E Ratio', 'Net Debt/EBITDA', 'Current Ratio'].includes(r.metric));
  const quality   = rows.filter(r => ['ROE', 'ROA', 'Gross Margin', 'Operating Margin', 'Net Margin', 'FCF Margin'].includes(r.metric));
  const growth    = rows.filter(r => r.metric.includes('Growth'));
  const rest      = rows.filter(r =>
    !valuation.includes(r) && !leverage.includes(r) && !quality.includes(r) && !growth.includes(r)
  );

  let html = `<table class="valuation-table">
    <thead>
      <tr>
        <th style="text-align:left;width:160px">Metric</th>
        <th>Company</th>
        <th>Sector Mean</th>
        <th>Sector Median</th>
        <th>vs. Peers</th>
      </tr>
    </thead>
    <tbody>`;

  const addGroup = (label, group) => {
    if (!group.length) return;
    html += `<tr><td class="metric-group" colspan="5">${label}</td></tr>`;
    group.forEach(row => {
      const vs = row.vs_peers || '—';
      const vsCls = vs === '—' ? '' : vsClass(vs);
      html += `<tr>
        <td>${escHtml(row.metric)}</td>
        <td>${escHtml(row.company || 'N/M')}</td>
        <td>${escHtml(row.sector_mean || 'N/M')}</td>
        <td>${escHtml(row.sector_median || 'N/M')}</td>
        <td><span class="vs-badge ${vsCls}">${escHtml(vs)}</span></td>
      </tr>`;
    });
  };

  addGroup('VALUATION MULTIPLES', valuation);
  addGroup('LEVERAGE', leverage);
  addGroup('PROFITABILITY & QUALITY', quality);
  addGroup('GROWTH', growth);
  if (rest.length) addGroup('OTHER', rest);

  html += `</tbody></table>`;
  return html;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function escHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function fmtUSD(v) {
  if (v === null || v === undefined) return 'N/M';
  return '$' + v.toFixed(2);
}

function vsClass(vs) {
  const map = {
    'PREMIUM':  'premium',
    'DISCOUNT': 'discount',
    'INLINE':   'inline',
    'SUPERIOR': 'superior',
    'BELOW':    'below',
    'ELEVATED': 'elevated',
    'FAVORABLE':'favorable',
  };
  return map[vs.toUpperCase()] || '';
}

// ── Domain extraction from yfinance website ──────────────────────────────────
function domainFromWebsite(url) {
  if (!url) return null;
  try {
    let u = url.trim();
    if (!u.match(/^https?:\/\//i)) u = 'http://' + u;
    const host = new URL(u).hostname.replace(/^www\./i, '');
    return host || null;
  } catch { return null; }
}

// ── Sector backdrop: full-page ambient pattern behind everything ─────────────
function applySectorBackdrop(sector) {
  let bd = document.getElementById('sector-backdrop');
  if (!bd) {
    bd = document.createElement('div');
    bd.id = 'sector-backdrop';
    bd.setAttribute('aria-hidden', 'true');
    document.body.insertBefore(bd, document.body.firstChild);
  }
  bd.className = 'sector-backdrop';
  bd.innerHTML = sectorBackdropSVG(sector);
  // Trigger fade-in
  requestAnimationFrame(() => bd.classList.add('visible'));
}

function clearSectorBackdrop() {
  const bd = document.getElementById('sector-backdrop');
  if (bd) { bd.classList.remove('visible'); bd.innerHTML = ''; }
}

function sectorBackdropSVG(sector) {
  const s = (sector || '').toLowerCase();
  const accent = sectorAccent(sector);

  // Tech / Semiconductors → circuit traces
  if (s.includes('technology') || s.includes('software') || s.includes('semiconductor') || s.includes('communication')) {
    return circuitBackdrop(accent);
  }
  // Financials → geometric grid + currency wave
  if (s.includes('financ') || s.includes('bank') || s.includes('insurance') || s.includes('real estate')) {
    return financialBackdrop(accent);
  }
  // Energy / Utilities → flowing pipelines
  if (s.includes('energy') || s.includes('oil') || s.includes('gas') || s.includes('utilities')) {
    return energyBackdrop(accent);
  }
  // Healthcare → molecular hex pattern
  if (s.includes('health') || s.includes('pharma') || s.includes('biotech') || s.includes('medical')) {
    return healthcareBackdrop(accent);
  }
  // Consumer → retail bag silhouettes / shopping cart trails
  if (s.includes('consumer')) {
    return consumerBackdrop(accent);
  }
  // Industrials / Materials → blueprint gear pattern
  if (s.includes('industrial') || s.includes('material') || s.includes('manufactur')) {
    return industrialBackdrop(accent);
  }
  return defaultBackdrop(accent);
}

function _bgFrame(content) {
  return `
    <div class="bd-side bd-left">
      <svg viewBox="0 0 220 1000" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">${content}</svg>
    </div>
    <div class="bd-side bd-right">
      <svg viewBox="0 0 220 1000" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">
        <g transform="translate(220 0) scale(-1 1)">${content}</g>
      </svg>
    </div>`;
}

function circuitBackdrop(c) {
  // Subtle PCB traces with nodes
  const content = `
    <defs>
      <pattern id="grid-tech" width="40" height="40" patternUnits="userSpaceOnUse">
        <path d="M 40 0 L 0 0 0 40" fill="none" stroke="${c}" stroke-width="0.4" opacity="0.18"/>
      </pattern>
    </defs>
    <rect width="220" height="1000" fill="url(#grid-tech)"/>
    <g stroke="${c}" stroke-width="1" fill="none" opacity="0.32">
      <path d="M20 80 L60 80 L60 130 L120 130 L120 200 L180 200"/>
      <path d="M40 280 L40 340 L100 340 L100 400 L160 400 L160 480"/>
      <path d="M180 540 L180 600 L120 600 L120 680 L60 680 L60 760"/>
      <path d="M30 820 L90 820 L90 880 L160 880 L160 940"/>
    </g>
    <g fill="${c}" opacity="0.45">
      <circle cx="60" cy="80" r="2.2"/><circle cx="120" cy="200" r="2.2"/>
      <circle cx="100" cy="340" r="2.2"/><circle cx="160" cy="480" r="2.2"/>
      <circle cx="180" cy="540" r="2.2"/><circle cx="60" cy="760" r="2.2"/>
      <circle cx="90" cy="820" r="2.2"/><circle cx="160" cy="940" r="2.2"/>
    </g>
    <g fill="none" stroke="${c}" stroke-width="0.6" opacity="0.22">
      <rect x="50" y="160" width="40" height="20" rx="2"/>
      <rect x="130" y="430" width="50" height="22" rx="2"/>
      <rect x="40" y="700" width="40" height="20" rx="2"/>
    </g>`;
  return _bgFrame(content);
}

function financialBackdrop(c) {
  // Skyscraper silhouettes + grid + faint upward arrow
  const content = `
    <defs>
      <pattern id="grid-fin" width="50" height="50" patternUnits="userSpaceOnUse">
        <path d="M 50 0 L 0 0 0 50" fill="none" stroke="${c}" stroke-width="0.4" opacity="0.15"/>
      </pattern>
    </defs>
    <rect width="220" height="1000" fill="url(#grid-fin)"/>
    <g fill="${c}" opacity="0.18">
      <rect x="20" y="640" width="28" height="280"/>
      <rect x="55" y="580" width="34" height="340"/>
      <rect x="95" y="520" width="40" height="400"/>
      <rect x="140" y="610" width="32" height="310"/>
      <rect x="178" y="680" width="26" height="240"/>
    </g>
    <g fill="${c}" opacity="0.32">
      <rect x="62" y="610" width="4" height="6"/><rect x="74" y="610" width="4" height="6"/>
      <rect x="62" y="640" width="4" height="6"/><rect x="74" y="640" width="4" height="6"/>
      <rect x="105" y="555" width="4" height="6"/><rect x="118" y="555" width="4" height="6"/>
      <rect x="105" y="585" width="4" height="6"/><rect x="118" y="585" width="4" height="6"/>
      <rect x="148" y="640" width="4" height="6"/><rect x="160" y="640" width="4" height="6"/>
    </g>
    <g stroke="${c}" stroke-width="1.2" fill="none" opacity="0.28">
      <path d="M30 400 L70 360 L110 380 L150 320 L190 280" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M180 280 L188 290 M180 280 L178 268" stroke-linecap="round"/>
    </g>
    <g fill="${c}" opacity="0.18" font-family="JetBrains Mono, monospace" font-size="10" letter-spacing="2">
      <text x="40" y="120">$ — — — —</text>
      <text x="30" y="200">▲ ▼ ▲ ▼</text>
    </g>`;
  return _bgFrame(content);
}

function energyBackdrop(c) {
  // Pipelines + flow droplets
  const content = `
    <g stroke="${c}" stroke-width="1.6" fill="none" opacity="0.28" stroke-linecap="round">
      <path d="M30 100 L30 250 L80 300 L80 460 L150 530 L150 720 L100 770 L100 940"/>
      <path d="M170 80 L170 200 L120 250 L120 380 L180 430 L180 600 L130 660 L130 880"/>
    </g>
    <g fill="${c}" opacity="0.36">
      <circle cx="30" cy="100" r="3"/><circle cx="80" cy="300" r="3"/>
      <circle cx="150" cy="530" r="3"/><circle cx="100" cy="940" r="3"/>
      <circle cx="170" cy="80" r="3"/><circle cx="120" cy="380" r="3"/>
      <circle cx="180" cy="600" r="3"/><circle cx="130" cy="880" r="3"/>
    </g>
    <g fill="${c}" opacity="0.18">
      <ellipse cx="55" cy="180" rx="3" ry="5"/><ellipse cx="55" cy="380" rx="3" ry="5"/>
      <ellipse cx="115" cy="490" rx="3" ry="5"/><ellipse cx="125" cy="850" rx="3" ry="5"/>
      <ellipse cx="145" cy="160" rx="3" ry="5"/><ellipse cx="155" cy="540" rx="3" ry="5"/>
    </g>
    <g stroke="${c}" stroke-width="0.6" fill="none" opacity="0.16">
      <path d="M0 500 Q 110 470 220 510" /><path d="M0 530 Q 110 500 220 540" />
    </g>`;
  return _bgFrame(content);
}

function healthcareBackdrop(c) {
  // Hex molecular lattice
  const content = `
    <defs>
      <pattern id="hex-health" width="46" height="40" patternUnits="userSpaceOnUse" patternTransform="translate(0 0)">
        <polygon points="23,2 43,12 43,32 23,42 3,32 3,12" fill="none" stroke="${c}" stroke-width="0.7" opacity="0.22"/>
      </pattern>
    </defs>
    <rect width="220" height="1000" fill="url(#hex-health)"/>
    <g fill="${c}" opacity="0.34">
      <circle cx="60" cy="180" r="3"/><circle cx="160" cy="240" r="3"/>
      <circle cx="80" cy="380" r="3"/><circle cx="170" cy="460" r="3"/>
      <circle cx="50" cy="600" r="3"/><circle cx="140" cy="680" r="3"/>
      <circle cx="100" cy="820" r="3"/>
    </g>
    <g stroke="${c}" stroke-width="1" fill="none" opacity="0.28">
      <path d="M60 180 L160 240"/><path d="M80 380 L170 460"/>
      <path d="M50 600 L140 680"/><path d="M160 240 L80 380"/>
      <path d="M170 460 L50 600"/><path d="M140 680 L100 820"/>
    </g>`;
  return _bgFrame(content);
}

function consumerBackdrop(c) {
  // Concentric "scan" arcs + small tags
  const content = `
    <g stroke="${c}" stroke-width="1" fill="none" opacity="0.22">
      <circle cx="20" cy="160" r="60"/><circle cx="20" cy="160" r="100"/>
      <circle cx="20" cy="160" r="140"/>
      <circle cx="200" cy="500" r="70"/><circle cx="200" cy="500" r="115"/>
      <circle cx="40" cy="820" r="60"/><circle cx="40" cy="820" r="100"/>
    </g>
    <g fill="${c}" opacity="0.3">
      <rect x="80" y="320" width="22" height="14" rx="2"/>
      <rect x="140" y="380" width="22" height="14" rx="2"/>
      <rect x="60" y="540" width="22" height="14" rx="2"/>
      <rect x="130" y="700" width="22" height="14" rx="2"/>
    </g>
    <g fill="none" stroke="${c}" stroke-width="0.7" opacity="0.22">
      <path d="M0 250 Q 110 220 220 260"/>
      <path d="M0 480 Q 110 450 220 490"/>
      <path d="M0 740 Q 110 710 220 750"/>
    </g>`;
  return _bgFrame(content);
}

function industrialBackdrop(c) {
  // Blueprint gears + frame lines
  const content = `
    <g stroke="${c}" stroke-width="0.8" fill="none" opacity="0.24">
      <path d="M0 0 L220 0 L220 1000 L0 1000 Z" stroke-dasharray="4 6"/>
      <path d="M20 20 L200 20 L200 980 L20 980 Z"/>
    </g>
    <g stroke="${c}" stroke-width="1" fill="none" opacity="0.3">
      <circle cx="80" cy="220" r="34"/>
      <g transform="translate(80 220)">
        <g><line x1="0" y1="-44" x2="0" y2="-34"/><line x1="0" y1="34" x2="0" y2="44"/>
           <line x1="-44" y1="0" x2="-34" y2="0"/><line x1="34" y1="0" x2="44" y2="0"/>
           <line x1="-31" y1="-31" x2="-24" y2="-24"/><line x1="24" y1="24" x2="31" y2="31"/>
           <line x1="-31" y1="31" x2="-24" y2="24"/><line x1="24" y1="-24" x2="31" y2="-31"/></g>
        <circle r="14"/>
      </g>
      <circle cx="160" cy="600" r="26"/>
      <g transform="translate(160 600)">
        <line x1="0" y1="-34" x2="0" y2="-26"/><line x1="0" y1="26" x2="0" y2="34"/>
        <line x1="-34" y1="0" x2="-26" y2="0"/><line x1="26" y1="0" x2="34" y2="0"/>
        <circle r="11"/>
      </g>
      <circle cx="60" cy="850" r="30"/>
      <circle cx="60" cy="850" r="12"/>
    </g>
    <g stroke="${c}" stroke-width="0.5" fill="none" opacity="0.18">
      <path d="M0 420 L220 420"/><path d="M0 750 L220 750"/>
      <text x="30" y="412" font-family="JetBrains Mono, monospace" font-size="7" fill="${c}">SECT A</text>
      <text x="30" y="742" font-family="JetBrains Mono, monospace" font-size="7" fill="${c}">SECT B</text>
    </g>`;
  return _bgFrame(content);
}

function defaultBackdrop(c) {
  const content = `
    <defs>
      <pattern id="grid-def" width="50" height="50" patternUnits="userSpaceOnUse">
        <path d="M 50 0 L 0 0 0 50" fill="none" stroke="${c}" stroke-width="0.4" opacity="0.16"/>
      </pattern>
    </defs>
    <rect width="220" height="1000" fill="url(#grid-def)"/>`;
  return _bgFrame(content);
}
