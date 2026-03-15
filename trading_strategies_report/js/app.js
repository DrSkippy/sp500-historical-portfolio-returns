/**
 * app.js — Main application logic for the trading strategies report.
 *
 * Fetches report_data.json, then renders all 6 sections.
 * Depends on charts.js being loaded first.
 */

"use strict";

// ─── State ─────────────────────────────────────────────────────────────────────

let APP_DATA = null;       // full parsed report_data.json
let CHARTS = {};           // active Chart.js instances keyed by name
let SORT_STATE = { col: "mean_yearly", dir: "desc" };
let SELECTED_ROW = null;   // model name highlighted in table

// ─── Boot ───────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  fetch("data/report_data.json")
    .then(r => {
      if (!r.ok) throw new Error(`HTTP ${r.status} loading report_data.json`);
      return r.json();
    })
    .then(data => {
      APP_DATA = data;
      initApp();
    })
    .catch(err => {
      document.getElementById("loading").classList.add("hidden");
      const el = document.getElementById("error");
      el.textContent = `Failed to load data: ${err.message}`;
      el.classList.remove("hidden");
    });
});

function initApp() {
  document.getElementById("loading").classList.add("hidden");

  document.querySelectorAll(".report-section").forEach(s => s.classList.remove("hidden"));

  initOverviewSection();
  initReturnCurvesSection();
  initRiskSection();
  initDistributionSection();
  initScatterSection();
  initAdviceSection();
}

// ─── Helpers ────────────────────────────────────────────────────────────────────

function pct(v, decimals = 1) { return (v * 100).toFixed(decimals) + "%"; }

function getSummaryRow(model, year) {
  return model.summary.find(s => s.year === year) || null;
}

function getBestModelByMetric(models, year, metricFn, higher = true) {
  let best = null, bestVal = higher ? -Infinity : Infinity;
  models.forEach(m => {
    const row = getSummaryRow(m, year);
    if (!row) return;
    const v = metricFn(row);
    if (higher ? v > bestVal : v < bestVal) { best = m; bestVal = v; }
  });
  return { model: best, value: bestVal };
}

function familyModels(family) {
  return APP_DATA.models.filter(m => m.family === family);
}

function destroyChart(name) {
  if (CHARTS[name]) { CHARTS[name].destroy(); delete CHARTS[name]; }
}

// ─── Section 1: Overview Table ──────────────────────────────────────────────────

function initOverviewSection() {
  const slider = document.getElementById("overview-year-slider");
  const label  = document.getElementById("overview-year-label");

  renderOverviewTable(parseInt(slider.value));
  slider.addEventListener("input", () => {
    label.textContent = slider.value;
    renderOverviewTable(parseInt(slider.value));
  });

  document.querySelectorAll("#overview-table th.sortable").forEach(th => {
    th.addEventListener("click", () => {
      const col = th.dataset.col;
      if (SORT_STATE.col === col) {
        SORT_STATE.dir = SORT_STATE.dir === "asc" ? "desc" : "asc";
      } else {
        SORT_STATE.col = col;
        SORT_STATE.dir = col === "name" ? "asc" : "desc";
      }
      renderOverviewTable(parseInt(slider.value));
    });
  });
}

function renderOverviewTable(year) {
  const rows = APP_DATA.models.map(m => {
    const row = getSummaryRow(m, year);
    return { model: m, row };
  }).filter(({ row }) => row !== null);

  // Sort
  const { col, dir } = SORT_STATE;
  rows.sort((a, b) => {
    let va, vb;
    if (col === "name") {
      va = a.model.name; vb = b.model.name;
    } else {
      const map = {
        mean_yearly: r => r.mean_yearly,
        median_yearly: r => r.median_yearly,
        sdev_yearly: r => r.sdev_yearly,
        fraction_losing: r => r.fraction_losing,
      };
      va = map[col] ? map[col](a.row) : 0;
      vb = map[col] ? map[col](b.row) : 0;
    }
    if (va < vb) return dir === "asc" ? -1 : 1;
    if (va > vb) return dir === "asc" ? 1 : -1;
    return 0;
  });

  // Update sort indicators
  document.querySelectorAll("#overview-table th.sortable").forEach(th => {
    th.classList.remove("sort-asc", "sort-desc");
    if (th.dataset.col === col) th.classList.add(`sort-${dir}`);
  });

  const tbody = document.getElementById("overview-tbody");
  tbody.innerHTML = "";
  rows.forEach(({ model, row }) => {
    const tr = document.createElement("tr");
    tr.className = `family-${model.family}`;
    if (SELECTED_ROW === model.name) tr.classList.add("selected-row");
    tr.innerHTML = `
      <td><span class="family-badge badge-${model.family}"></span>${formatModelLabel(model)}</td>
      <td>${pct(row.mean_yearly)}</td>
      <td>${pct(row.median_yearly)}</td>
      <td>${pct(row.sdev_yearly)}</td>
      <td>${pct(row.fraction_losing)}</td>
    `;
    tr.addEventListener("click", () => {
      SELECTED_ROW = SELECTED_ROW === model.name ? null : model.name;
      renderOverviewTable(year);
    });
    tbody.appendChild(tr);
  });
}

// ─── Section 2: Return Curves ───────────────────────────────────────────────────

function initReturnCurvesSection() {
  populateModelToggles();
  renderReturnCurves();

  document.querySelectorAll(".family-toggle").forEach(cb => {
    cb.addEventListener("change", () => {
      syncModelTogglesToFamily();
      renderReturnCurves();
    });
  });
}

function populateModelToggles() {
  const container = document.getElementById("model-toggles");
  container.innerHTML = "";
  APP_DATA.models.forEach(model => {
    const label = document.createElement("label");
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = true;
    cb.dataset.model = model.name;
    cb.dataset.family = model.family;
    cb.className = "model-toggle";
    cb.addEventListener("change", renderReturnCurves);
    label.appendChild(cb);
    label.append(" " + formatModelLabel(model));
    label.style.borderLeftColor = FAMILY_COLORS[model.family];
    label.style.borderLeftWidth = "3px";
    container.appendChild(label);
  });
}

function syncModelTogglesToFamily() {
  document.querySelectorAll(".family-toggle").forEach(fcb => {
    const family = fcb.dataset.family;
    const enabled = fcb.checked;
    document.querySelectorAll(`.model-toggle[data-family="${family}"]`).forEach(mcb => {
      mcb.checked = enabled;
    });
  });
}

function getVisibleModels(toggleClass = "model-toggle") {
  const visible = new Set();
  document.querySelectorAll(`.${toggleClass}:checked`).forEach(cb => {
    visible.add(cb.dataset.model || cb.dataset.family);
  });
  if (toggleClass === "model-toggle") {
    return APP_DATA.models.filter(m => visible.has(m.name));
  }
  // family toggles
  return APP_DATA.models.filter(m => visible.has(m.family));
}

function renderReturnCurves() {
  destroyChart("returnCurves");
  const models = getVisibleModels("model-toggle");
  if (models.length === 0) return;
  CHARTS.returnCurves = createLineChart(
    "return-curves-chart",
    models,
    s => s.mean_yearly,
    { yLabel: "Mean Annualized Return" }
  );
}

// ─── Section 3: Risk Over Time ──────────────────────────────────────────────────

function initRiskSection() {
  renderRiskChart();
  document.querySelectorAll(".risk-family-toggle").forEach(cb => {
    cb.addEventListener("change", renderRiskChart);
  });
}

function renderRiskChart() {
  destroyChart("risk");
  const visible = new Set();
  document.querySelectorAll(".risk-family-toggle:checked").forEach(cb => {
    visible.add(cb.dataset.family);
  });
  const models = APP_DATA.models.filter(m => visible.has(m.family));
  if (models.length === 0) return;
  CHARTS.risk = createLineChart(
    "risk-chart",
    models,
    s => s.fraction_losing,
    {
      yLabel: "Fraction of Losing Starts",
      yFormat: v => (v * 100).toFixed(0) + "%",
    }
  );
}

// ─── Section 4: Distribution Explorer ──────────────────────────────────────────

function initDistributionSection() {
  const modelSelect   = document.getElementById("dist-model-select");
  const overlaySelect = document.getElementById("dist-overlay-model-select");

  // Populate selects
  APP_DATA.models.forEach(m => {
    const opt = document.createElement("option");
    opt.value = m.name;
    opt.textContent = formatModelLabel(m);
    modelSelect.appendChild(opt.cloneNode(true));
    overlaySelect.appendChild(opt);
  });
  // Default primary to Buy_Hold, overlay to a Kelly variant
  const bh = APP_DATA.models.find(m => m.family === "buy_hold");
  if (bh) modelSelect.value = bh.name;
  const kelly = APP_DATA.models.find(m => m.family === "kelly");
  if (kelly) overlaySelect.value = kelly.name;

  renderDistribution();

  modelSelect.addEventListener("change", renderDistribution);
  overlaySelect.addEventListener("change", renderDistribution);
  document.getElementById("dist-year-select").addEventListener("change", renderDistribution);
  document.getElementById("dist-overlay-checkbox").addEventListener("change", renderDistribution);
}

function renderDistribution() {
  destroyChart("distribution");
  const modelName   = document.getElementById("dist-model-select").value;
  const year        = document.getElementById("dist-year-select").value;
  const showOverlay = document.getElementById("dist-overlay-checkbox").checked;
  const overlayName = document.getElementById("dist-overlay-model-select").value;

  const primary = APP_DATA.models.find(m => m.name === modelName);
  if (!primary || !primary.distributions[year]) return;

  let overlayModel = null;
  if (showOverlay && overlayName && overlayName !== modelName) {
    overlayModel = APP_DATA.models.find(m => m.name === overlayName);
  }

  CHARTS.distribution = createDistributionChart(
    "distribution-chart",
    primary.distributions[year],
    `${formatModelLabel(primary)} (${year}yr)`,
    primary.family,
    overlayModel && overlayModel.distributions[year] ? overlayModel.distributions[year] : null,
    overlayModel ? `${formatModelLabel(overlayModel)} (${year}yr)` : null,
    overlayModel ? overlayModel.family : null
  );
}

// ─── Section 5: Scatter ─────────────────────────────────────────────────────────

function initScatterSection() {
  const slider = document.getElementById("scatter-year-slider");
  const label  = document.getElementById("scatter-year-label");

  renderScatter(parseInt(slider.value));
  slider.addEventListener("input", () => {
    label.textContent = slider.value;
    renderScatter(parseInt(slider.value));
  });
}

function renderScatter(year) {
  destroyChart("scatter");
  CHARTS.scatter = createScatterChart("scatter-chart", APP_DATA.models, year);
}

// ─── Section 6: Practical Advice ───────────────────────────────────────────────

function initAdviceSection() {
  const container = document.getElementById("advice-content");
  container.innerHTML = buildAdviceHTML();
}

function buildAdviceHTML() {
  const models = APP_DATA.models;

  // Helper: get summary row for a model at a given year
  const at = (m, yr) => m.summary.find(s => s.year === yr);

  // Find best mean_yearly per family at year 10
  const bestKelly10 = getBestModelByMetric(familyModels("kelly"), 10, r => r.mean_yearly);
  const bestIns10   = getBestModelByMetric(familyModels("insurance"), 10, r => r.mean_yearly);
  const bh10        = at(models.find(m => m.family === "buy_hold"), 10);

  // Short horizon: fraction_losing at year 3
  const year3Losing = models.map(m => ({ m, fl: at(m, 3)?.fraction_losing }))
    .filter(({ fl }) => fl !== undefined)
    .sort((a, b) => a.fl - b.fl);
  const under15Pct = year3Losing.filter(({ fl }) => fl < 0.15);

  // Medium horizon: break-even (year where fraction_losing < 5%)
  function breakEvenYear(model) {
    for (const row of model.summary) {
      if (row.fraction_losing < 0.05) return row.year;
    }
    return ">15";
  }
  const bhBreakEven = breakEvenYear(models.find(m => m.family === "buy_hold"));

  // Long horizon: best mean at year 15
  const best15 = getBestModelByMetric(models, 15, r => r.mean_yearly);

  // Insurance vs Kelly overhead at year 10
  const insVsKellyDiff = bestKelly10.value - bestIns10.value;

  // Build recommendation rows
  const recRows = [
    [
      "1–3 years",
      year3Losing[0] ? formatModelLabel(year3Losing[0].m) : "—",
      `Lowest fraction of losing starts at year 3 (${pct(year3Losing[0]?.fl || 0)})`
    ],
    [
      "5–7 years",
      bestKelly10.model ? formatModelLabel(bestKelly10.model) : "Buy & Hold",
      `Kelly strategies typically outperform Buy & Hold by this horizon`
    ],
    [
      "10–15 years",
      best15.model ? formatModelLabel(best15.model) : "Buy & Hold",
      `Highest mean annualized return at 15 years (${pct(best15.value)})`
    ],
  ];

  const recTableRows = recRows.map(([horizon, strategy, reason]) => `
    <tr>
      <td><strong>${horizon}</strong></td>
      <td>${strategy}</td>
      <td>${reason}</td>
    </tr>
  `).join("");

  const under15List = under15Pct.length > 0
    ? under15Pct.map(({ m, fl }) => `${formatModelLabel(m)} (${pct(fl)})`).join(", ")
    : "None at this threshold";

  return `
    <div class="advice-block horizon-short">
      <h3>Short Horizon (1–3 years)</h3>
      <p>When investing for 1–3 years, the dominant concern is capital preservation — what fraction of starting points end in a loss?</p>
      <p>At year 3, strategies with fewer than 15% losing starts: <strong>${under15List || "none meet this threshold"}</strong>.</p>
      <p>Buy &amp; Hold has a losing-start rate of <strong>${pct(at(models.find(m => m.family === "buy_hold"), 3)?.fraction_losing || 0)}</strong> at year 3.
         All strategies carry meaningful drawdown risk at short horizons — size positions accordingly.</p>
    </div>

    <div class="advice-block horizon-medium">
      <h3>Medium Horizon (5–7 years)</h3>
      <p>By year 5–7 the market's compounding power reduces losing-start rates substantially.
         Buy &amp; Hold typically reaches &lt;5% losing starts around year <strong>${bhBreakEven}</strong>.</p>
      <p>The best Fractional Kelly variant at year 10 earns <strong>${pct(bestKelly10.value)}</strong> mean annualized return
         vs Buy &amp; Hold's <strong>${pct(bh10?.mean_yearly || 0)}</strong> —
         a ${pct(Math.abs(bestKelly10.value - (bh10?.mean_yearly || 0)))} gap.</p>
      <p>Kelly strategies add meaningful alpha without dramatically increasing drawdown risk over this horizon.</p>
    </div>

    <div class="advice-block horizon-long">
      <h3>Long Horizon (10–15 years)</h3>
      <p>Over 10–15 years essentially all strategies converge on very low losing-start rates (&lt;5%).
         The differentiator becomes <em>upside potential</em>.</p>
      <p>The best strategy at year 15 by mean annualized return is
         <strong>${best15.model ? formatModelLabel(best15.model) : "Buy & Hold"}</strong>
         at <strong>${pct(best15.value)}</strong>.</p>
      <p>If your time horizon is ≥10 years and you can tolerate moderate tracking error, active rebalancing strategies offer a compelling case.</p>
    </div>

    <div class="advice-block insurance-block">
      <h3>Insurance Strategies: Protection vs. Cost</h3>
      <p>Insurance strategies buy downside protection by allocating a fraction of the portfolio to a synthetic hedge, at the cost of reduced upside participation.</p>
      <p>At year 10, the best Insurance variant earns <strong>${pct(bestIns10.value)}</strong> mean annualized return
         vs the best Kelly variant at <strong>${pct(bestKelly10.value)}</strong>
         — an overhead of <strong>${pct(insVsKellyDiff)}</strong> per year.</p>
      <p>${insVsKellyDiff > 0.005
        ? "The insurance cost is material. Consider Insurance strategies only if your risk tolerance genuinely demands the additional downside protection beyond what Kelly's bond allocation already provides."
        : "The insurance cost is modest relative to the protection it provides. Investors with lower risk tolerance may find the trade-off worthwhile."
      }</p>
    </div>

    <div class="advice-block" style="border-color:#6b7280; background:#f9fafb;">
      <h3>Quick-Reference Recommendation Table</h3>
      <div id="recommendation-table-wrapper">
        <table id="recommendation-table">
          <thead>
            <tr><th>If you plan to hold…</th><th>Consider this strategy</th><th>Because…</th></tr>
          </thead>
          <tbody>${recTableRows}</tbody>
        </table>
      </div>
      <p style="margin-top:.75rem; font-size:.8rem; color:#6c757d;">
        Based on historical S&amp;P 500 data. All strategies are exposed to sequence-of-returns risk.
        Past performance does not guarantee future results.
      </p>
    </div>
  `;
}

// formatModelLabel and FAMILY_COLORS are defined in charts.js (loaded before app.js)
