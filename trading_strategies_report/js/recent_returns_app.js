/**
 * recent_returns_app.js
 *
 * Fetches recent_returns_data.json and renders three histogram sections
 * (daily, weekly, monthly) with Chart.js annotation lines for recent values.
 *
 * Depends on charts.js being loaded first (uses buildHistogram, hexToRgba).
 */

"use strict";

const DATA_URL = "data/recent_returns_data.json";

// ── Helpers ──────────────────────────────────────────────────────────────────

function pct(v, decimals = 2) {
  return (v * 100).toFixed(decimals) + "%";
}

function ordinal(n) {
  const n_ = Math.round(n);
  const s = ["th", "st", "nd", "rd"];
  const v = n_ % 100;
  return n_ + (s[(v - 20) % 10] || s[v] || s[0]);
}

function formatDate(isoStr) {
  if (!isoStr) return "";
  const [y, m, d] = isoStr.split("-");
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return `${months[parseInt(m, 10) - 1]} ${parseInt(d, 10)}`;
}

/**
 * Find the label in a histogram labels array whose numeric value (parsed from
 * the "X.X%" string) is nearest to `value` (a fraction, e.g. -0.0056).
 */
function findNearestBinLabel(labels, value) {
  const parsed = labels.map(l => parseFloat(l) / 100);
  let bestIdx = 0;
  let bestDist = Infinity;
  for (let i = 0; i < parsed.length; i++) {
    const dist = Math.abs(parsed[i] - value);
    if (dist < bestDist) {
      bestDist = dist;
      bestIdx = i;
    }
  }
  return labels[bestIdx];
}

// ── Stats strip ───────────────────────────────────────────────────────────────

function renderStatsStrip(containerId, stats, recentEntries) {
  const el = document.getElementById(containerId);
  if (!el) return;
  const last = recentEntries[recentEntries.length - 1];
  const signClass = last && last.value >= 0 ? "positive" : "negative";
  el.innerHTML = `
    <div class="stat">
      <span class="stat-label">Historical Mean</span>
      <span class="stat-value">${pct(stats.mean)}</span>
    </div>
    <div class="stat">
      <span class="stat-label">Std Dev</span>
      <span class="stat-value">${pct(stats.std)}</span>
    </div>
    <div class="stat">
      <span class="stat-label">Most Recent</span>
      <span class="stat-value ${signClass}">${last ? pct(last.value) : "—"}</span>
    </div>
    <div class="stat">
      <span class="stat-label">Percentile</span>
      <span class="stat-value">${last ? ordinal(last.percentile) : "—"}</span>
    </div>
    <div class="stat">
      <span class="stat-label">Most Recent Date</span>
      <span class="stat-value">${last ? formatDate(last.date) : "—"}</span>
    </div>
  `;
}

// ── Recent returns table ──────────────────────────────────────────────────────

function renderRecentTable(containerId, recentEntries, maxRows = 10) {
  const wrap = document.getElementById(containerId);
  if (!wrap) return;
  const rows = recentEntries.slice(-maxRows).reverse(); // most recent first
  const tbody = rows.map(r => {
    const cls = r.value >= 0 ? "positive" : "negative";
    return `<tr>
      <td>${formatDate(r.date)}</td>
      <td class="${cls}">${pct(r.value)}</td>
      <td>${ordinal(r.percentile)}</td>
    </tr>`;
  }).join("");

  wrap.innerHTML = `
    <table class="recent-returns-table">
      <thead>
        <tr><th>Date</th><th>Return</th><th>Historical Percentile</th></tr>
      </thead>
      <tbody>${tbody}</tbody>
    </table>
  `;
}

// ── Histogram + annotation chart ─────────────────────────────────────────────

function createReturnHistogram(canvasId, histValues, recentEntries) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return null;
  const ctx = canvas.getContext("2d");

  const { labels, counts } = buildHistogram(histValues, 60);

  const annotations = {};
  recentEntries.forEach((r, i) => {
    const age = recentEntries.length - 1 - i; // 0 = most recent
    const opacity = Math.max(0.3, 1.0 - age * 0.06);
    const color = r.value >= 0
      ? `rgba(44,160,44,${opacity})`
      : `rgba(214,39,40,${opacity})`;
    const binLabel = findNearestBinLabel(labels, r.value);
    const isMostRecent = i === recentEntries.length - 1;

    annotations[`r${i}`] = {
      type: "line",
      xMin: binLabel,
      xMax: binLabel,
      borderColor: color,
      borderWidth: isMostRecent ? 3 : 2,
      label: {
        content: `${formatDate(r.date)}: ${pct(r.value)} (${ordinal(r.percentile)})`,
        display: isMostRecent,
        position: "end",
        font: { size: 10 },
        color: color,
        backgroundColor: "rgba(255,255,255,0.85)",
        padding: 4,
      },
    };
  });

  return new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "Historical Returns",
          data: counts,
          backgroundColor: "rgba(26,111,175,0.55)",
          borderColor: "#1a6faf",
          borderWidth: 1,
          barPercentage: 1.0,
          categoryPercentage: 1.0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        annotation: { annotations },
        tooltip: {
          callbacks: {
            label: ctx => ` ${ctx.parsed.y} trading days`,
          },
        },
      },
      scales: {
        x: {
          title: { display: true, text: "Return" },
          ticks: { maxTicksLimit: 14 },
          grid: { display: false },
        },
        y: {
          title: { display: true, text: "Count (trading days)" },
        },
      },
    },
  });
}

// ── Show/hide sections ────────────────────────────────────────────────────────

function showSection(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove("hidden");
}

// ── Main ──────────────────────────────────────────────────────────────────────

async function init() {
  const loadingEl = document.getElementById("loading");
  const errorEl = document.getElementById("error");

  try {
    const resp = await fetch(DATA_URL);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${resp.url}`);
    const data = await resp.json();

    if (loadingEl) loadingEl.classList.add("hidden");

    // ── Daily ──────────────────────────────────────────────────────────────
    showSection("section-daily");
    renderStatsStrip("daily-stats", data.daily.stats, data.daily.recent);
    createReturnHistogram("daily-chart", data.daily.values, data.daily.recent);
    renderRecentTable("daily-table-wrap", data.daily.recent, 10);

    // ── Weekly ─────────────────────────────────────────────────────────────
    showSection("section-weekly");
    renderStatsStrip("weekly-stats", data.weekly.stats, data.weekly.recent);
    createReturnHistogram("weekly-chart", data.weekly.values, data.weekly.recent);
    renderRecentTable("weekly-table-wrap", data.weekly.recent, 10);

    // ── Monthly ────────────────────────────────────────────────────────────
    showSection("section-monthly");
    renderStatsStrip("monthly-stats", data.monthly.stats, data.monthly.recent);
    createReturnHistogram("monthly-chart", data.monthly.values, data.monthly.recent);
    renderRecentTable("monthly-table-wrap", data.monthly.recent, 4);

  } catch (err) {
    if (loadingEl) loadingEl.classList.add("hidden");
    if (errorEl) {
      errorEl.classList.remove("hidden");
      errorEl.textContent = `Failed to load data: ${err.message}. Run bin/generate_recent_returns.py first.`;
    }
    console.error(err);
  }
}

document.addEventListener("DOMContentLoaded", init);
