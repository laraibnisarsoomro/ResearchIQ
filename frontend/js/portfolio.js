'use strict';
/* ── Portfolio Builder — self-contained module ───────────────────────────── */

const SECTORS_ALL = [
  'Information Technology','Health Care','Financials','Consumer Discretionary',
  'Communication Services','Industrials','Consumer Staples','Energy',
  'Utilities','Real Estate','Materials',
];

let _currentReport = null;  // set by app.js after report renders
let _lastFormState = null;  // persists questionnaire answers between opens

// Called from app.js to register the anchor report
function portfolioSetAnchor(report) {
  _currentReport = report;
}

// ── Inject "Build Portfolio" button below memo ─────────────────────────────
function injectPortfolioButton() {
  const existing = document.getElementById('portfolio-trigger-btn');
  if (existing) existing.remove();

  const btn = document.createElement('div');
  btn.id = 'portfolio-trigger-area';
  btn.innerHTML = `
    <button id="portfolio-trigger-btn" class="btn-portfolio-trigger" onclick="openPortfolioModal()">
      <span class="pf-btn-icon">⬡</span>
      Build Portfolio Recommendation
    </button>
  `;

  const footer = document.querySelector('.memo-footer');
  if (footer) {
    footer.parentNode.insertBefore(btn, footer);
  } else {
    const memo = document.querySelector('.memo');
    if (memo) memo.appendChild(btn);
  }
}

// ── Modal open/close ───────────────────────────────────────────────────────
function openPortfolioModal() {
  // Always tear down and rebuild so state is fully reset for every open
  const old = document.getElementById('portfolio-modal');
  if (old) old.remove();

  const modal = document.createElement('div');
  modal.id = 'portfolio-modal';
  modal.className = 'pf-modal-overlay';
  modal.innerHTML = buildModalHTML();
  document.body.appendChild(modal);
  initQuestionnaire();

  modal.style.display = 'flex';
  document.body.style.overflow = 'hidden';
}

function closePortfolioModal() {
  const modal = document.getElementById('portfolio-modal');
  if (modal) modal.remove();
  document.body.style.overflow = '';
}

// ── Questionnaire HTML ─────────────────────────────────────────────────────
function buildModalHTML() {
  const st = _lastFormState;  // null on first open
  const anchorSector = _currentReport ? _currentReport.sector : '';

  // Helper: mark the right <option> as selected
  const sel = (val, ...opts) => opts.map(o =>
    `<option${o === String(val || '') ? ' selected' : ''}>${o}</option>`
  ).join('');

  // Investor sub-type: generate the right set of options if type is already known
  const savedType = st ? st.investor_type : '';
  const savedSub  = st ? st.investor_subtype : '';
  let subtypeVisible = savedType ? '' : 'display:none';
  let subtypeLabel   = savedType === 'Individual' ? 'Employment Status' : 'Institution Type';
  let subtypeOpts    = '<option value="">— Select —</option>';
  if (savedType === 'Individual') {
    subtypeOpts += sel(savedSub, 'Salaried Employee', 'Business Owner', 'Self-Employed', 'Retired');
  } else if (savedType) {
    subtypeOpts += sel(savedSub, 'Pension Fund', 'Hedge Fund', 'Endowment or Foundation',
      'Family Office', 'Insurance Company', 'Sovereign Wealth Fund', 'Asset Manager or Mutual Fund');
  }

  // Sector chips: restore saved selection; fall back to anchor sector on first open
  const savedSectors = st && st.sectors && st.sectors.length
    ? st.sectors
    : (anchorSector ? [anchorSector] : []);
  const sectorChips = SECTORS_ALL.map(s => {
    const on = savedSectors.includes(s) ? 'selected' : '';
    return `<span class="pf-chip ${on}" data-sector="${s}" onclick="toggleSector(this)">${s}</span>`;
  }).join('');

  // Numeric input value helper
  const val = v => (v != null && v !== '') ? ` value="${v}"` : '';

  return `
  <div class="pf-modal">
    <div class="pf-modal-header">
      <div>
        <div class="pf-modal-title">Build Portfolio Recommendation</div>
        <div class="pf-modal-sub">Answer 5 quick sections to receive a tailored portfolio.</div>
      </div>
      <button class="pf-close-btn" onclick="closePortfolioModal()">✕</button>
    </div>

    <!-- Progress bar -->
    <div class="pf-progress-bar">
      <div class="pf-progress-fill" id="pf-progress-fill"></div>
    </div>
    <div class="pf-progress-labels">
      <span>Identity</span><span>Setup</span><span>Risk</span><span>Sectors</span><span>Constraints</span>
    </div>

    <div class="pf-modal-body" id="pf-modal-body">

      <!-- SECTION A -->
      <div class="pf-section active" id="pf-sec-a">
        <div class="pf-sec-title">A — Investor Identity</div>

        <div class="pf-field">
          <label>Your Age</label>
          <input type="number" id="pf-age" min="18" max="99" placeholder="e.g. 32" class="pf-input"${val(st && st.age)}>
        </div>

        <div class="pf-field">
          <label>Investor Type</label>
          <select id="pf-investor-type" class="pf-select" onchange="updateInvestorSub()">
            <option value="">— Select —</option>
            ${sel(savedType, 'Individual', 'Institutional')}
          </select>
        </div>

        <div class="pf-field" id="pf-subtype-field" style="${subtypeVisible}">
          <label id="pf-subtype-label">${subtypeLabel}</label>
          <select id="pf-investor-subtype" class="pf-select">
            ${subtypeOpts}
          </select>
        </div>
      </div>

      <!-- SECTION B -->
      <div class="pf-section" id="pf-sec-b">
        <div class="pf-sec-title">B — Portfolio Setup</div>

        <div class="pf-field">
          <label>Investment Amount (USD)</label>
          <div class="pf-input-prefix-wrap">
            <span class="pf-prefix">$</span>
            <input type="number" id="pf-amount" min="1000" placeholder="e.g. 100000" class="pf-input pf-input-prefixed"${val(st && st.amount)}>
          </div>
        </div>

        <div class="pf-field">
          <label>Investment Horizon</label>
          <select id="pf-horizon" class="pf-select">
            <option value="">— Select —</option>
            ${sel(st && st.horizon, 'Short-term (under 1 year)', 'Medium-term (1–3 years)', 'Long-term (3+ years)')}
          </select>
        </div>
      </div>

      <!-- SECTION C -->
      <div class="pf-section" id="pf-sec-c">
        <div class="pf-sec-title">C — Risk Profile</div>

        <div class="pf-field">
          <label>Investment Objective</label>
          <select id="pf-objective" class="pf-select">
            <option value="">— Select —</option>
            ${sel(st && st.objective, 'Capital Preservation', 'Income and Stability', 'Balanced Growth', 'Aggressive Growth', 'Maximum Return')}
          </select>
        </div>

        <div class="pf-field">
          <label>Drawdown Tolerance</label>
          <select id="pf-drawdown" class="pf-select">
            <option value="">— Select —</option>
            ${sel(st && st.drawdown, 'Up to 5%', 'Up to 10%', 'Up to 20%', 'Up to 30% or more')}
          </select>
        </div>

        <div class="pf-field">
          <label>Prior Investing Experience</label>
          <select id="pf-experience" class="pf-select">
            <option value="">— Select —</option>
            ${sel(st && st.experience, 'Beginner', 'Intermediate', 'Experienced', 'Professional')}
          </select>
        </div>
      </div>

      <!-- SECTION D -->
      <div class="pf-section" id="pf-sec-d">
        <div class="pf-sec-title">D — Sector Preferences</div>
        <p class="pf-hint">Select one or more sectors. Your anchor ticker's sector is pre-selected.</p>
        <div class="pf-chip-grid" id="pf-sector-chips">
          ${sectorChips}
        </div>
      </div>

      <!-- SECTION E -->
      <div class="pf-section" id="pf-sec-e">
        <div class="pf-sec-title">E — Portfolio Constraints</div>

        <div class="pf-field">
          <label>Maximum Number of Positions</label>
          <select id="pf-max-positions" class="pf-select">
            <option value="">— Select —</option>
            <option value="5"${st && st.max_positions == '5' ? ' selected' : ''}>5</option>
            <option value="10"${st && st.max_positions == '10' ? ' selected' : ''}>10</option>
            <option value="15"${st && st.max_positions == '15' ? ' selected' : ''}>15</option>
            <option value="20"${st && st.max_positions == '20' ? ' selected' : ''}>20 or more</option>
          </select>
        </div>

        <div class="pf-field">
          <label>Position Sizing Style</label>
          <select id="pf-sizing" class="pf-select">
            <option value="">— Select —</option>
            ${sel(st && st.sizing, 'Equal Weight', 'Conviction-Weighted', 'Sector-Concentrated')}
          </select>
        </div>
      </div>

    </div><!-- end pf-modal-body -->

    <div class="pf-modal-footer">
      <button class="pf-btn-secondary" id="pf-back-btn" onclick="pfNav(-1)" style="display:none">← Back</button>
      <div id="pf-error-msg" class="pf-error"></div>
      <button class="pf-btn-primary" id="pf-next-btn" onclick="pfNav(1)">Next →</button>
    </div>
  </div>`;
}

// ── Questionnaire state + navigation ──────────────────────────────────────
const PF_SECTIONS = ['a','b','c','d','e'];
let pfCurrentStep = 0;

function initQuestionnaire() {
  pfCurrentStep = 0;
  updateProgressUI();
  // Values are already baked into the HTML by buildModalHTML() — nothing to restore here.
}

function saveFormState() {
  const sectors = Array.from(document.querySelectorAll('#pf-sector-chips .pf-chip.selected'))
    .map(el => el.dataset.sector);
  _lastFormState = {
    age:              document.getElementById('pf-age').value,
    investor_type:    document.getElementById('pf-investor-type').value,
    investor_subtype: document.getElementById('pf-investor-subtype').value,
    amount:           document.getElementById('pf-amount').value,
    horizon:          document.getElementById('pf-horizon').value,
    objective:        document.getElementById('pf-objective').value,
    drawdown:         document.getElementById('pf-drawdown').value,
    experience:       document.getElementById('pf-experience').value,
    sectors,
    max_positions:    document.getElementById('pf-max-positions').value,
    sizing:           document.getElementById('pf-sizing').value,
  };
}

function updateInvestorSub() {
  const type = document.getElementById('pf-investor-type').value;
  const field = document.getElementById('pf-subtype-field');
  const label = document.getElementById('pf-subtype-label');
  const select = document.getElementById('pf-investor-subtype');

  if (!type) { field.style.display = 'none'; return; }

  field.style.display = '';
  select.innerHTML = '<option value="">— Select —</option>';

  if (type === 'Individual') {
    label.textContent = 'Employment Status';
    ['Salaried Employee','Business Owner','Self-Employed','Retired'].forEach(o => {
      select.innerHTML += `<option>${o}</option>`;
    });
  } else {
    label.textContent = 'Institution Type';
    ['Pension Fund','Hedge Fund','Endowment or Foundation','Family Office',
     'Insurance Company','Sovereign Wealth Fund','Asset Manager or Mutual Fund'].forEach(o => {
      select.innerHTML += `<option>${o}</option>`;
    });
  }
}

function toggleSector(el) {
  el.classList.toggle('selected');
}

function pfNav(dir) {
  if (dir === 1 && !pfValidateStep()) return;

  if (dir === 1 && pfCurrentStep === PF_SECTIONS.length - 1) {
    submitPortfolio();
    return;
  }

  document.getElementById(`pf-sec-${PF_SECTIONS[pfCurrentStep]}`).classList.remove('active');
  pfCurrentStep = Math.max(0, Math.min(PF_SECTIONS.length - 1, pfCurrentStep + dir));
  document.getElementById(`pf-sec-${PF_SECTIONS[pfCurrentStep]}`).classList.add('active');
  updateProgressUI();
}

function updateProgressUI() {
  const pct = (pfCurrentStep / (PF_SECTIONS.length - 1)) * 100;
  document.getElementById('pf-progress-fill').style.width = pct + '%';

  const backBtn = document.getElementById('pf-back-btn');
  const nextBtn = document.getElementById('pf-next-btn');
  if (backBtn) backBtn.style.display = pfCurrentStep > 0 ? '' : 'none';
  if (nextBtn) nextBtn.textContent = pfCurrentStep === PF_SECTIONS.length - 1 ? 'Generate My Portfolio' : 'Next →';
  clearPfError();
}

function showPfError(msg) {
  const el = document.getElementById('pf-error-msg');
  if (el) el.textContent = msg;
}
function clearPfError() {
  const el = document.getElementById('pf-error-msg');
  if (el) el.textContent = '';
}

function pfValidateStep() {
  const step = PF_SECTIONS[pfCurrentStep];

  if (step === 'a') {
    const age = parseInt(document.getElementById('pf-age').value);
    if (!age || age < 18 || age > 99) { showPfError('Please enter a valid age (18–99).'); return false; }
    const type = document.getElementById('pf-investor-type').value;
    if (!type) { showPfError('Please select an investor type.'); return false; }
    const sub = document.getElementById('pf-investor-subtype').value;
    if (!sub) { showPfError('Please select a sub-type.'); return false; }
  }
  if (step === 'b') {
    const amt = parseFloat(document.getElementById('pf-amount').value);
    if (!amt || amt < 1000) { showPfError('Please enter an investment amount of at least $1,000.'); return false; }
    if (!document.getElementById('pf-horizon').value) { showPfError('Please select an investment horizon.'); return false; }
  }
  if (step === 'c') {
    if (!document.getElementById('pf-objective').value) { showPfError('Please select an investment objective.'); return false; }
    if (!document.getElementById('pf-drawdown').value) { showPfError('Please select a drawdown tolerance.'); return false; }
    if (!document.getElementById('pf-experience').value) { showPfError('Please select your experience level.'); return false; }
  }
  if (step === 'd') {
    const selected = document.querySelectorAll('#pf-sector-chips .pf-chip.selected');
    if (selected.length === 0) { showPfError('Please select at least one sector.'); return false; }
  }
  if (step === 'e') {
    if (!document.getElementById('pf-max-positions').value) { showPfError('Please select a maximum number of positions.'); return false; }
    if (!document.getElementById('pf-sizing').value) { showPfError('Please select a position sizing style.'); return false; }
  }
  return true;
}

// ── Submit ─────────────────────────────────────────────────────────────────
async function submitPortfolio() {
  // Persist answers before the API call so re-opens are always pre-filled
  saveFormState();

  const nextBtn = document.getElementById('pf-next-btn');
  nextBtn.disabled = true;
  nextBtn.textContent = 'Building…';

  const sectors = Array.from(document.querySelectorAll('#pf-sector-chips .pf-chip.selected'))
    .map(el => el.dataset.sector);

  const maxPos = parseInt(document.getElementById('pf-max-positions').value);

  const payload = {
    anchor_ticker: _currentReport ? _currentReport.ticker : '',
    anchor_sector: _currentReport ? _currentReport.sector : '',
    anchor_recommendation: _currentReport ? _currentReport.recommendation : 'Hold',
    anchor_upside_pct: _currentReport ? _currentReport.upside_pct : null,
    age: parseInt(document.getElementById('pf-age').value),
    investor_type: document.getElementById('pf-investor-type').value,
    investor_subtype: document.getElementById('pf-investor-subtype').value,
    investment_amount: parseFloat(document.getElementById('pf-amount').value),
    horizon: document.getElementById('pf-horizon').value,
    objective: document.getElementById('pf-objective').value,
    drawdown_tolerance: document.getElementById('pf-drawdown').value,
    experience: document.getElementById('pf-experience').value,
    sectors: sectors,
    max_positions: maxPos,
    sizing_style: document.getElementById('pf-sizing').value,
  };

  try {
    const resp = await fetch('/api/portfolio', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(payload),
    });
    const data = await resp.json();

    if (!resp.ok || data.error) {
      showPfError(data.error || 'Portfolio generation failed. Please try again.');
      nextBtn.disabled = false;
      nextBtn.textContent = 'Generate My Portfolio';
      return;
    }

    closePortfolioModal();
    renderPortfolioMemo(data, payload);

  } catch (err) {
    showPfError('Network error. Please check the server and try again.');
    nextBtn.disabled = false;
    nextBtn.textContent = 'Generate My Portfolio';
  }
}

// ── Portfolio memo renderer ────────────────────────────────────────────────
function renderPortfolioMemo(pf, req) {
  // Remove any old memo
  const old = document.getElementById('portfolio-memo-area');
  if (old) old.remove();

  const s = pf.stats;
  const fmtUSD = v => '$' + (v >= 1e6 ? (v/1e6).toFixed(1)+'M' : v >= 1e3 ? (v/1e3).toFixed(1)+'K' : v.toFixed(0));
  const fmtNum = v => v !== null && v !== undefined ? v.toFixed(2) : '—';
  // Cap displayed position upside at ±60% — backend already clamps, but guard the display too.
  // Values beyond ±60% in the table would look inconsistent with the portfolio-level return.
  const fmtUpside = v => {
    const capped = Math.max(Math.min(v, 60), -60);
    const suffix = (v > 60 || v < -60) ? '+' : '';  // trailing + signals the cap
    return (capped > 0 ? '+' : '') + capped.toFixed(1) + '%' + suffix;
  };
  const fmtPct = (v, sign=true) => (sign && v > 0 ? '+' : '') + v.toFixed(1) + '%';
  const today = new Date().toLocaleDateString('en-US', {month:'short',day:'numeric',year:'numeric'});

  const stratClass = pf.strategy.toLowerCase().replace(/[\s/()]/g, '-');

  // Long book table rows
  const longRows = (pf.long_positions || []).map(p => `
    <tr>
      <td class="pf-ticker-cell">${p.ticker}</td>
      <td>${p.company}</td>
      <td>${p.sector}</td>
      <td class="num up">${fmtPct(p.expected_return_pct)}</td>
      <td class="num">${p.weight_pct.toFixed(1)}%</td>
      <td class="num">${fmtUSD(p.dollar_amount)}</td>
    </tr>`).join('');

  // Short book table rows
  const shortRows = (pf.short_positions || []).map(p => `
    <tr>
      <td class="pf-ticker-cell">${p.ticker}</td>
      <td>${p.company}</td>
      <td>${p.sector}</td>
      <td class="num up">${fmtPct(p.expected_return_pct)}</td>
      <td class="num">${p.weight_pct.toFixed(1)}%</td>
      <td class="num">${fmtUSD(p.dollar_amount)}</td>
    </tr>`).join('');

  const shortBookHTML = pf.short_positions && pf.short_positions.length > 0 ? `
    <div class="pf-memo-section">
      <div class="pf-table-label">Short Book</div>
      <table class="pf-table">
        <thead><tr>
          <th>Ticker</th><th>Company</th><th>Sector</th>
          <th class="num">Est. Return</th><th class="num">Weight</th><th class="num">Amount</th>
        </tr></thead>
        <tbody>${shortRows}</tbody>
      </table>
      <div class="pf-book-total">Short book total: ${fmtUSD(s.short_book_usd)}</div>
    </div>` : '';

  const pairsHTML = (pf.pairs_long_ticker && pf.pairs_short_ticker) ? `
    <details class="pf-pairs-section">
      <summary>Pairs Trade Highlight</summary>
      <p>Consider going long <strong>${pf.pairs_long_ticker}</strong> (${pf.pairs_long_company})
      and short <strong>${pf.pairs_short_ticker}</strong> (${pf.pairs_short_company})
      within <strong>${pf.pairs_sector}</strong> as a focused relative-value trade.</p>
    </details>` : '';

  const warningHTML = pf.warning ? `<div class="pf-warning">⚠ ${pf.warning}</div>` : '';

  const rfNote = s.risk_free_source !== 'FRED DTB3'
    ? `<p>Risk-free rate: ${s.risk_free_rate_pct.toFixed(1)}% (${s.risk_free_source})</p>` : '';

  const html = `
  <div id="portfolio-memo-area" class="pf-memo-wrap">
    <div class="pf-memo">

      <!-- [1] Header -->
      <div class="pf-memo-header strat-${stratClass}">
        <div class="pf-memo-header-left">
          <div class="pf-memo-supertitle">Hypothetical Portfolio Memo</div>
          <div class="pf-memo-strategy">${pf.strategy}</div>
          <div class="pf-memo-meta">
            Anchor: ${_currentReport ? _currentReport.ticker + ' · ' + _currentReport.company_name : ''}
            &nbsp;·&nbsp; ${today}
          </div>
        </div>
        <div class="pf-memo-header-right">
          <div class="pf-strategy-badge">${pf.strategy}</div>
        </div>
      </div>

      ${warningHTML}

      <div class="pf-memo-body">

        <!-- [2] Investor profile -->
        <div class="pf-two-col-section">
          <div class="pf-memo-section">
            <div class="pf-section-title">Investor Profile</div>
            <table class="pf-profile-table">
              <tr><td class="pf-profile-label">Investor Type</td><td>${req.investor_type} (${req.investor_subtype})</td>
                  <td class="pf-profile-label">Age</td><td>${req.age}</td></tr>
              <tr><td class="pf-profile-label">Horizon</td><td>${req.horizon}</td>
                  <td class="pf-profile-label">Experience</td><td>${req.experience}</td></tr>
              <tr><td class="pf-profile-label">Objective</td><td>${req.objective}</td>
                  <td class="pf-profile-label">Drawdown Tolerance</td><td>${req.drawdown_tolerance}</td></tr>
            </table>
          </div>

          <!-- [3] Portfolio statistics -->
          <div class="pf-memo-section">
            <div class="pf-section-title">Portfolio Statistics</div>
            <table class="pf-profile-table">
              <tr><td class="pf-profile-label">Investment</td><td>${fmtUSD(req.investment_amount)}</td>
                  <td class="pf-profile-label">Strategy</td><td>${pf.strategy}</td></tr>
              <tr><td class="pf-profile-label">Expected Return</td><td class="up"><span data-count-to="${s.expected_return_pct}" data-count-decimals="1" data-count-sign="1" data-count-suffix="%">+0.0%</span></td>
                  <td class="pf-profile-label">Est. Volatility</td><td><span data-count-to="${s.portfolio_vol_pct}" data-count-decimals="1" data-count-suffix="%">0.0%</span></td></tr>
              <tr><td class="pf-profile-label">Sharpe (illus.)</td><td><span data-count-to="${s.sharpe_ratio}" data-count-decimals="2">0.00</span></td>
                  <td class="pf-profile-label">Portfolio Beta</td><td><span data-count-to="${s.portfolio_beta}" data-count-decimals="2">0.00</span></td></tr>
              <tr><td class="pf-profile-label">Net Exposure</td><td>${s.net_exposure_pct.toFixed(0)}%</td>
                  <td class="pf-profile-label">Gross Exposure</td><td>${s.gross_exposure_pct.toFixed(0)}%</td></tr>
              <tr><td class="pf-profile-label">Long Positions</td><td>${s.n_long}</td>
                  <td class="pf-profile-label">Short Positions</td><td>${s.n_short}</td></tr>
              <tr><td class="pf-profile-label">Sectors</td>
                  <td colspan="3">${(s.sectors_covered || []).join(', ')}</td></tr>
            </table>
          </div>
        </div>

        <!-- [4] Rationale -->
        <div class="pf-memo-section">
          <div class="pf-section-title">Investment Rationale</div>
          <p class="pf-rationale">${pf.rationale}</p>
        </div>

        <!-- [5] Long book -->
        <div class="pf-memo-section">
          <div class="pf-table-label">Long Book</div>
          <table class="pf-table">
            <thead><tr>
              <th>Ticker</th><th>Company</th><th>Sector</th>
              <th class="num">Est. Return</th><th class="num">Weight</th><th class="num">Amount</th>
            </tr></thead>
            <tbody>${longRows}</tbody>
          </table>
          <div class="pf-book-total">Long book total: ${fmtUSD(s.long_book_usd)}</div>
        </div>

        <!-- [6] Short book (omit for Long-Only) -->
        ${shortBookHTML}

        <!-- [7] Pairs trade -->
        ${pairsHTML}

        <!-- [8] Disclaimer -->
        <div class="pf-disclaimer">
          ${rfNote}
          <p>This is a hypothetical, illustrative portfolio generated for educational and research
          purposes only. It does not constitute investment advice. All return and volatility figures
          are model-generated estimates based on comparable valuation analysis and beta approximation.
          Past model performance does not guarantee future results.</p>
        </div>

      </div><!-- end pf-memo-body -->
    </div><!-- end pf-memo -->
  </div><!-- end pf-memo-wrap -->`;

  // Insert below the report area
  const reportArea = document.getElementById('report-area');
  const div = document.createElement('div');
  div.innerHTML = html;
  reportArea.parentNode.insertBefore(div.firstElementChild, reportArea.nextSibling);

  // Animate counters once memo is in DOM
  requestAnimationFrame(() => animatePortfolioCounters());

  // Set up gutter swap on scroll into portfolio memo
  setupPortfolioGutterSwap(pf, req);

  // Scroll to portfolio memo
  document.getElementById('portfolio-memo-area').scrollIntoView({behavior:'smooth', block:'start'});
}

// ── Animated counter helper (numbers count up from 0) ────────────────────────
function animatePortfolioCounters() {
  const els = document.querySelectorAll('#portfolio-memo-area [data-count-to]');
  els.forEach(el => {
    const target = parseFloat(el.dataset.countTo);
    const decimals = parseInt(el.dataset.countDecimals || '0');
    const prefix = el.dataset.countPrefix || '';
    const suffix = el.dataset.countSuffix || '';
    const sign = el.dataset.countSign === '1';
    const duration = 900;
    const start = performance.now();
    function tick(now) {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      const v = target * eased;
      const s = (sign && target > 0 ? '+' : '') + v.toFixed(decimals);
      el.textContent = `${prefix}${s}${suffix}`;
      if (t < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  });
}

// ── Gutter swap: equity ↔ portfolio ──────────────────────────────────────────
let _equityGutterCache = null;
let _portfolioGutterIO = null;

function setupPortfolioGutterSwap(pf, req) {
  const left  = document.getElementById('report-deco-left');
  const right = document.getElementById('report-deco-right');
  const memo  = document.getElementById('portfolio-memo-area');
  if (!left || !right || !memo) return;

  // Cache the equity gutter HTML once so we can restore on scroll-up
  if (_equityGutterCache === null) {
    _equityGutterCache = { left: left.innerHTML, right: right.innerHTML };
  }

  // Tear down any existing observer (re-build for new portfolio)
  if (_portfolioGutterIO) { _portfolioGutterIO.disconnect(); _portfolioGutterIO = null; }

  const portfolioLeft  = buildPortfolioGutterLeft(pf, req);
  const portfolioRight = buildPortfolioGutterRight(pf, req);

  let currentMode = 'equity'; // 'equity' | 'portfolio'

  function setMode(mode) {
    if (mode === currentMode) return;
    currentMode = mode;
    // Fade out → swap → fade in
    [left, right].forEach(el => el.classList.add('deco-fading'));
    setTimeout(() => {
      if (mode === 'portfolio') {
        left.innerHTML  = portfolioLeft;
        right.innerHTML = portfolioRight;
        // Trigger SVG/donut animations
        requestAnimationFrame(() => animatePortfolioGutterVisuals(pf));
      } else {
        left.innerHTML  = _equityGutterCache.left;
        right.innerHTML = _equityGutterCache.right;
      }
      [left, right].forEach(el => el.classList.remove('deco-fading'));
    }, 220);
  }

  _portfolioGutterIO = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      // Switch when the portfolio memo's top edge reaches the upper third of viewport
      if (entry.isIntersecting && entry.intersectionRatio > 0.05) {
        setMode('portfolio');
      } else if (!entry.isIntersecting) {
        setMode('equity');
      }
    });
  }, { threshold: [0, 0.05, 0.5], rootMargin: '-20% 0px -20% 0px' });

  _portfolioGutterIO.observe(memo);
}

function teardownPortfolioGutterSwap() {
  if (_portfolioGutterIO) { _portfolioGutterIO.disconnect(); _portfolioGutterIO = null; }
  _equityGutterCache = null;
}

// ── Portfolio gutter content builders ────────────────────────────────────────
function buildPortfolioGutterLeft(pf, req) {
  const s = pf.stats;
  const stratClass = pf.strategy.toLowerCase().replace(/[\s/()]/g, '-');
  const stratColor = strategyAccent(pf.strategy);
  const anchorTicker = (typeof _currentReport !== 'undefined' && _currentReport) ? _currentReport.ticker : '—';

  return `
    <div class="deco-panel pf-deco-panel pf-deco-strategy strat-bg-${stratClass}" data-anim="slide-up">
      <div class="deco-panel-label">Strategy</div>
      ${strategyBadgeSVG(pf.strategy, stratColor)}
      <div class="deco-panel-value pf-deco-strategy-name">${escapeHtml(pf.strategy)}</div>
      <div class="deco-panel-sub">${escapeHtml(s.strategy_description || '')}</div>
    </div>

    <div class="deco-panel pf-deco-panel" data-anim="slide-up" style="animation-delay:.12s">
      <div class="deco-panel-label">Sector Allocation</div>
      ${sectorDonutSVG(pf.long_positions || [], pf.short_positions || [])}
      <div class="pf-deco-legend">${sectorDonutLegendHTML(pf.long_positions || [], pf.short_positions || [])}</div>
    </div>

    <div class="deco-vertical-text">${escapeHtml(pf.strategy.toUpperCase())}</div>
  `;
}

function buildPortfolioGutterRight(pf, req) {
  const s = pf.stats;
  const sharpe = s.sharpe_ratio || 0;
  const beta   = s.portfolio_beta || 0;
  const expRet = s.expected_return_pct || 0;
  const vol    = s.portfolio_vol_pct || 0;
  const stratColor = strategyAccent(pf.strategy);

  return `
    <div class="deco-vertical-text">PORTFOLIO · ${escapeHtml((s.strategy || '').toUpperCase())}</div>

    <div class="deco-panel pf-deco-panel" data-anim="slide-up">
      <div class="deco-panel-label">Sharpe Ratio</div>
      ${sharpeGaugeSVG(sharpe, stratColor)}
      <div class="deco-panel-value" data-count-to="${sharpe}" data-count-decimals="2">0.00</div>
      <div class="deco-panel-sub">${sharpeQualitative(sharpe)} · β ${beta.toFixed(2)}</div>
    </div>

    <div class="deco-panel pf-deco-panel" data-anim="slide-up" style="animation-delay:.12s">
      <div class="deco-panel-label">Risk / Return</div>
      ${riskReturnBarSVG(expRet, vol, stratColor)}
      <div class="deco-panel-value up" data-count-to="${expRet}" data-count-decimals="1" data-count-sign="1" data-count-suffix="%">+0.0%</div>
      <div class="deco-panel-sub">vol <span data-count-to="${vol}" data-count-decimals="1" data-count-suffix="%">0.0%</span> · ${s.n_long} long · ${s.n_short} short</div>
    </div>
  `;
}

function strategyAccent(strategy) {
  const s = (strategy || '').toLowerCase();
  if (s.includes('long-only'))                       return '#1a7f64';
  if (s.includes('long-biased') || s.includes('130')) return '#2a79d3';
  if (s.includes('long-short'))                       return '#7c3aed';
  if (s.includes('market'))                           return '#c17f24';
  return '#1e5fa8';
}

function sharpeQualitative(s) {
  if (s >= 2.0) return 'Excellent';
  if (s >= 1.0) return 'Strong';
  if (s >= 0.5) return 'Moderate';
  if (s >= 0.0) return 'Modest';
  return 'Poor';
}

function escapeHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

// ── Strategy badge SVG (concentric rings, animated) ──────────────────────────
function strategyBadgeSVG(strategy, color) {
  const s = (strategy || '').toLowerCase();
  // Ring count varies by aggressiveness
  let rings = 2;
  if (s.includes('long-biased')) rings = 3;
  if (s.includes('long-short')) rings = 4;
  if (s.includes('market')) rings = 4;

  const w = 220, h = 80, cx = w/2, cy = h/2;
  let circles = '';
  for (let i = 1; i <= rings; i++) {
    const r = 8 + i * 9;
    const op = (0.85 - i * 0.15).toFixed(2);
    circles += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${color}" stroke-width="1.2" opacity="${op}" class="pf-strat-ring" style="animation-delay:${i*0.08}s"/>`;
  }
  // Center hex shape
  const hex = `<polygon points="${cx-7},${cy-4} ${cx},${cy-8} ${cx+7},${cy-4} ${cx+7},${cy+4} ${cx},${cy+8} ${cx-7},${cy+4}" fill="${color}" opacity="0.85"/>`;

  return `<svg class="deco-panel-svg pf-strat-svg" viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg">${circles}${hex}</svg>`;
}

// ── Sector donut SVG ─────────────────────────────────────────────────────────
function sectorDonutSVG(longs, shorts) {
  // Aggregate weights by sector across long and short positions
  const sectorWeights = {};
  longs.forEach(p => { sectorWeights[p.sector] = (sectorWeights[p.sector] || 0) + p.weight_pct; });
  shorts.forEach(p => { sectorWeights[p.sector] = (sectorWeights[p.sector] || 0) + p.weight_pct; });

  const entries = Object.entries(sectorWeights).sort((a,b) => b[1] - a[1]);
  const total = entries.reduce((sum, [,w]) => sum + w, 0) || 1;

  const w = 220, h = 110, cx = w/2, cy = h/2 + 4, rOuter = 38, rInner = 24;
  const colors = ['#2a79d3','#1a7f64','#c17f24','#7c3aed','#0e8a8a','#475569','#6d28d9','#b92b27','#1e5fa8','#1a6b3c','#7a1e1c'];

  let acc = 0;
  let arcs = '';
  entries.forEach(([sector, weight], i) => {
    const frac = weight / total;
    const startA = acc * 2 * Math.PI - Math.PI/2;
    const endA   = (acc + frac) * 2 * Math.PI - Math.PI/2;
    acc += frac;
    const largeArc = frac > 0.5 ? 1 : 0;
    const x1 = cx + rOuter * Math.cos(startA), y1 = cy + rOuter * Math.sin(startA);
    const x2 = cx + rOuter * Math.cos(endA),   y2 = cy + rOuter * Math.sin(endA);
    const x3 = cx + rInner * Math.cos(endA),   y3 = cy + rInner * Math.sin(endA);
    const x4 = cx + rInner * Math.cos(startA), y4 = cy + rInner * Math.sin(startA);
    const path = `M ${x1.toFixed(2)} ${y1.toFixed(2)}
                  A ${rOuter} ${rOuter} 0 ${largeArc} 1 ${x2.toFixed(2)} ${y2.toFixed(2)}
                  L ${x3.toFixed(2)} ${y3.toFixed(2)}
                  A ${rInner} ${rInner} 0 ${largeArc} 0 ${x4.toFixed(2)} ${y4.toFixed(2)} Z`;
    const color = colors[i % colors.length];
    arcs += `<path d="${path}" fill="${color}" class="pf-donut-slice" style="animation-delay:${(i*0.08).toFixed(2)}s" data-sector="${escapeHtml(sector)}"/>`;
  });

  // Center label: sector count
  const centerLabel = `
    <text x="${cx}" y="${cy - 2}" text-anchor="middle" font-size="13" font-weight="700" fill="#0d1b2a" font-family="JetBrains Mono, monospace">${entries.length}</text>
    <text x="${cx}" y="${cy + 10}" text-anchor="middle" font-size="6.5" fill="#64748b" letter-spacing="1.2" font-family="Inter, sans-serif">SECTORS</text>
  `;

  return `<svg class="deco-panel-svg pf-donut-svg" viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg">
    ${arcs}
    ${centerLabel}
  </svg>`;
}

function sectorDonutLegendHTML(longs, shorts) {
  const sectorWeights = {};
  longs.forEach(p => { sectorWeights[p.sector] = (sectorWeights[p.sector] || 0) + p.weight_pct; });
  shorts.forEach(p => { sectorWeights[p.sector] = (sectorWeights[p.sector] || 0) + p.weight_pct; });
  const entries = Object.entries(sectorWeights).sort((a,b) => b[1] - a[1]).slice(0, 4);
  const total = Object.values(sectorWeights).reduce((s,w) => s+w, 0) || 1;
  const colors = ['#2a79d3','#1a7f64','#c17f24','#7c3aed','#0e8a8a','#475569','#6d28d9','#b92b27','#1e5fa8','#1a6b3c','#7a1e1c'];

  return entries.map(([sector, weight], i) => {
    const pct = (weight / total * 100).toFixed(0);
    const short = sector.length > 14 ? sector.slice(0, 13) + '…' : sector;
    return `<div class="pf-legend-row">
      <span class="pf-legend-dot" style="background:${colors[i % colors.length]}"></span>
      <span class="pf-legend-name">${escapeHtml(short)}</span>
      <span class="pf-legend-val">${pct}%</span>
    </div>`;
  }).join('');
}

// ── Sharpe gauge SVG (semicircle with animated needle) ──────────────────────
function sharpeGaugeSVG(sharpe, color) {
  const w = 220, h = 110, cx = w/2, cy = h - 18, r = 60;
  // Map sharpe -2 → 4 onto -90deg → +90deg
  const minS = -2, maxS = 4;
  const clamped = Math.max(minS, Math.min(maxS, sharpe));
  const t = (clamped - minS) / (maxS - minS);
  const angle = -Math.PI + t * Math.PI; // -180° → 0°
  const needleX = cx + r * 0.85 * Math.cos(angle);
  const needleY = cy + r * 0.85 * Math.sin(angle);

  // Background arc (gradient: red → yellow → green)
  const segCount = 30;
  let segs = '';
  for (let i = 0; i < segCount; i++) {
    const a1 = -Math.PI + (i / segCount) * Math.PI;
    const a2 = -Math.PI + ((i + 1) / segCount) * Math.PI;
    const x1 = cx + r * Math.cos(a1), y1 = cy + r * Math.sin(a1);
    const x2 = cx + r * Math.cos(a2), y2 = cy + r * Math.sin(a2);
    const x3 = cx + (r-9) * Math.cos(a2), y3 = cy + (r-9) * Math.sin(a2);
    const x4 = cx + (r-9) * Math.cos(a1), y4 = cy + (r-9) * Math.sin(a1);
    // Hue from red(10) → yellow(50) → green(140)
    const hue = 10 + (i / segCount) * 130;
    segs += `<path d="M ${x1} ${y1} L ${x2} ${y2} L ${x3} ${y3} L ${x4} ${y4} Z" fill="hsl(${hue},65%,55%)" opacity="0.85"/>`;
  }

  return `<svg class="deco-panel-svg pf-gauge-svg" viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg">
    ${segs}
    <line class="pf-gauge-needle" x1="${cx}" y1="${cy}" x2="${needleX.toFixed(2)}" y2="${needleY.toFixed(2)}" stroke="${color}" stroke-width="2.4" stroke-linecap="round" data-target-angle="${angle}"/>
    <circle cx="${cx}" cy="${cy}" r="5" fill="${color}"/>
    <circle cx="${cx}" cy="${cy}" r="2" fill="#fff"/>
    <text x="${cx - r}" y="${cy + 12}" font-size="7" fill="#94a3b8" text-anchor="middle" font-family="Inter,sans-serif">−2</text>
    <text x="${cx + r}" y="${cy + 12}" font-size="7" fill="#94a3b8" text-anchor="middle" font-family="Inter,sans-serif">+4</text>
  </svg>`;
}

// ── Risk/return bar ──────────────────────────────────────────────────────────
function riskReturnBarSVG(expRet, vol, color) {
  const w = 220, h = 60;
  const maxScale = Math.max(50, expRet * 1.2, vol * 1.2);
  const retW = (Math.abs(expRet) / maxScale) * (w - 50);
  const volW = (vol / maxScale) * (w - 50);
  const retColor = expRet >= 0 ? '#1a7f64' : '#b92b27';

  return `<svg class="deco-panel-svg pf-rr-svg" viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="none">
    <text x="4" y="14" font-size="7" fill="#64748b" font-family="Inter,sans-serif" letter-spacing="1">RETURN</text>
    <rect x="44" y="7" width="${w-50}" height="9" fill="#e2e8f0" rx="2"/>
    <rect x="44" y="7" width="${retW.toFixed(1)}" height="9" fill="${retColor}" rx="2" class="pf-rr-bar"/>
    <text x="4" y="40" font-size="7" fill="#64748b" font-family="Inter,sans-serif" letter-spacing="1">VOL</text>
    <rect x="44" y="33" width="${w-50}" height="9" fill="#e2e8f0" rx="2"/>
    <rect x="44" y="33" width="${volW.toFixed(1)}" height="9" fill="${color}" opacity="0.7" rx="2" class="pf-rr-bar" style="animation-delay:.15s"/>
  </svg>`;
}

// Animations triggered when the gutter content swaps in
function animatePortfolioGutterVisuals(pf) {
  // Counters within the gutters
  const els = document.querySelectorAll('.report-deco [data-count-to]');
  els.forEach(el => {
    const target = parseFloat(el.dataset.countTo);
    const decimals = parseInt(el.dataset.countDecimals || '0');
    const prefix = el.dataset.countPrefix || '';
    const suffix = el.dataset.countSuffix || '';
    const sign = el.dataset.countSign === '1';
    const duration = 1100;
    const start = performance.now();
    function tick(now) {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      const v = target * eased;
      const s = (sign && target > 0 ? '+' : '') + v.toFixed(decimals);
      el.textContent = `${prefix}${s}${suffix}`;
      if (t < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  });
}
