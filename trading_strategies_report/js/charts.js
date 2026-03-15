/**
 * charts.js — Chart.js factory helpers for the trading strategies report.
 *
 * All functions return a Chart instance.  Callers are responsible for
 * destroying existing instances before creating new ones.
 */

"use strict";

const FAMILY_COLORS = {
  buy_hold:  "#1a6faf",
  kelly:     "#2ca02c",
  insurance: "#d62728",
};

const FAMILY_BG = {
  buy_hold:  "rgba(26,111,175,.15)",
  kelly:     "rgba(44,160,44,.15)",
  insurance: "rgba(214,39,40,.15)",
};

/** Generate a palette of shades within a family colour. */
function familyShade(family, index, total) {
  const base = {
    buy_hold:  [26,  111, 175],
    kelly:     [44,  160,  44],
    insurance: [214,  39,  40],
  }[family] || [100, 100, 100];

  // Lighten/darken by spreading index across a brightness range
  const t = total <= 1 ? 0.5 : index / (total - 1);
  const factor = 0.55 + t * 0.45;  // 0.55 → darkest, 1.0 → lightest
  const [r, g, b] = base.map(c => Math.round(Math.min(255, c / factor)));
  return `rgb(${r},${g},${b})`;
}

/**
 * Build datasets for a line chart from models, applying per-family shade.
 * @param {Array} models - filtered model objects
 * @param {Function} yFn - (summaryRow) => yValue
 * @param {Object} familyCounters - mutable {family: {count, idx}} accumulator
 * @param {Object} familyTotals  - {family: totalModelCount}
 */
function buildLineDatasets(models, yFn, familyTotals) {
  // Count index per family for shading
  const familyIdx = {};
  return models.map(model => {
    const f = model.family;
    if (!(f in familyIdx)) familyIdx[f] = 0;
    const idx = familyIdx[f]++;
    const total = familyTotals[f] || 1;
    const color = familyShade(f, idx, total);
    const isBuyHold = model.family === "buy_hold";

    return {
      label: formatModelLabel(model),
      data: model.summary.map(s => ({ x: s.year, y: yFn(s) })),
      borderColor: color,
      backgroundColor: color,
      borderWidth: isBuyHold ? 3 : 1.5,
      borderDash: isBuyHold ? [] : undefined,
      pointRadius: 3,
      tension: 0.3,
      family: f,
      modelName: model.name,
    };
  });
}

/** Human-readable label for a model. */
function formatModelLabel(model) {
  if (model.family === "buy_hold") return "Buy & Hold";
  if (model.family === "kelly") {
    const p = model.params;
    return `Kelly ${p.bond_frac * 100}% / ${p.rebalance}d`;
  }
  if (model.family === "insurance") {
    const p = model.params;
    return `Ins ${p.ins_frac * 100}% ded${p.deductible * 100}%`;
  }
  return model.name;
}

/** Count models per family in a list. */
function countByFamily(models) {
  const counts = {};
  models.forEach(m => { counts[m.family] = (counts[m.family] || 0) + 1; });
  return counts;
}

/* ─── Line chart (return curves & risk) ───────────────────────────────────── */

/**
 * Create or update a line chart.
 * @param {string} canvasId
 * @param {Array} models
 * @param {Function} yFn - (summaryRow) => number
 * @param {Object} opts  - { yLabel, yFormat, title }
 * @returns {Chart}
 */
function createLineChart(canvasId, models, yFn, opts = {}) {
  const ctx = document.getElementById(canvasId).getContext("2d");
  const totals = countByFamily(models);
  const datasets = buildLineDatasets(models, yFn, totals);

  return new Chart(ctx, {
    type: "line",
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          display: true,
          position: "right",
          labels: { boxWidth: 12, font: { size: 11 }, padding: 6 },
        },
        tooltip: {
          callbacks: {
            label: ctx => {
              const v = ctx.parsed.y;
              const fmt = opts.yFormat || (v => (v * 100).toFixed(1) + "%");
              return ` ${ctx.dataset.label}: ${fmt(v)}`;
            },
          },
        },
        title: opts.title
          ? { display: true, text: opts.title, font: { size: 13 } }
          : { display: false },
      },
      scales: {
        x: {
          type: "linear",
          title: { display: true, text: "Holding Period (years)" },
          ticks: { stepSize: 1 },
          min: 1, max: 15,
        },
        y: {
          title: { display: true, text: opts.yLabel || "Value" },
          ticks: {
            callback: opts.yFormat
              ? v => opts.yFormat(v)
              : v => (v * 100).toFixed(0) + "%",
          },
        },
      },
    },
  });
}

/* ─── Scatter chart ────────────────────────────────────────────────────────── */

/**
 * Create a risk/return scatter plot.
 * @param {string} canvasId
 * @param {Array} models
 * @param {number} year  - selected holding year
 * @returns {Chart}
 */
function createScatterChart(canvasId, models, year) {
  const ctx = document.getElementById(canvasId).getContext("2d");

  // One dataset per family for legend grouping
  const familyDatasets = {};
  models.forEach(model => {
    const f = model.family;
    if (!familyDatasets[f]) {
      familyDatasets[f] = {
        label: { buy_hold: "Buy & Hold", kelly: "Fractional Kelly", insurance: "Insurance" }[f] || f,
        data: [],
        backgroundColor: FAMILY_COLORS[f],
        borderColor: "#fff",
        borderWidth: 1.5,
        pointRadius: 7,
        pointHoverRadius: 9,
      };
    }
    const row = model.summary.find(s => s.year === year);
    if (!row) return;
    familyDatasets[f].data.push({
      x: row.sdev_yearly,
      y: row.mean_yearly,
      label: formatModelLabel(model),
      fraction_losing: row.fraction_losing,
    });
  });

  return new Chart(ctx, {
    type: "scatter",
    data: { datasets: Object.values(familyDatasets) },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: true, position: "right", labels: { boxWidth: 12, font: { size: 11 } } },
        tooltip: {
          callbacks: {
            label: ctx => {
              const d = ctx.raw;
              return [
                ` ${d.label}`,
                ` Mean yearly: ${(d.y * 100).toFixed(1)}%`,
                ` Std dev: ${(d.x * 100).toFixed(1)}%`,
                ` Losing starts: ${(d.fraction_losing * 100).toFixed(1)}%`,
              ];
            },
          },
        },
      },
      scales: {
        x: {
          title: { display: true, text: "Std Dev of Yearly Returns" },
          ticks: { callback: v => (v * 100).toFixed(0) + "%" },
        },
        y: {
          title: { display: true, text: "Mean Annualized Return" },
          ticks: { callback: v => (v * 100).toFixed(0) + "%" },
        },
      },
    },
  });
}

/* ─── Distribution histogram ───────────────────────────────────────────────── */

/**
 * Bin an array of returns into `numBins` histogram buckets.
 * Returns { labels: string[], counts: number[] }
 */
function buildHistogram(values, numBins = 45) {
  if (!values || values.length === 0) return { labels: [], counts: [] };
  const min = Math.min(...values);
  const max = Math.max(...values);
  const width = (max - min) / numBins || 1;
  const counts = new Array(numBins).fill(0);
  values.forEach(v => {
    let i = Math.floor((v - min) / width);
    if (i >= numBins) i = numBins - 1;
    counts[i]++;
  });
  const labels = Array.from({ length: numBins }, (_, i) =>
    ((min + (i + 0.5) * width) * 100).toFixed(1) + "%"
  );
  return { labels, counts };
}

/**
 * Create a distribution bar chart (histogram), optionally with overlay.
 * @param {string} canvasId
 * @param {Array} primaryValues - float array
 * @param {string} primaryLabel
 * @param {string} primaryFamily
 * @param {Array|null} overlayValues
 * @param {string|null} overlayLabel
 * @param {string|null} overlayFamily
 * @returns {Chart}
 */
function createDistributionChart(
  canvasId,
  primaryValues, primaryLabel, primaryFamily,
  overlayValues = null, overlayLabel = null, overlayFamily = null
) {
  const ctx = document.getElementById(canvasId).getContext("2d");
  const NUM_BINS = 45;

  // Compute shared bin edges from combined range so both histograms align
  const allValues = overlayValues
    ? [...primaryValues, ...overlayValues]
    : primaryValues;
  const globalMin = Math.min(...allValues);
  const globalMax = Math.max(...allValues);
  const width = (globalMax - globalMin) / NUM_BINS || 1;

  function binValues(values) {
    const counts = new Array(NUM_BINS).fill(0);
    values.forEach(v => {
      let i = Math.floor((v - globalMin) / width);
      if (i >= NUM_BINS) i = NUM_BINS - 1;
      counts[i]++;
    });
    return counts;
  }

  const labels = Array.from({ length: NUM_BINS }, (_, i) =>
    ((globalMin + (i + 0.5) * width) * 100).toFixed(1) + "%"
  );

  const primaryColor = FAMILY_COLORS[primaryFamily] || "#1a6faf";
  const datasets = [
    {
      label: primaryLabel,
      data: binValues(primaryValues),
      backgroundColor: hexToRgba(primaryColor, overlayValues ? 0.55 : 0.7),
      borderColor: primaryColor,
      borderWidth: 1,
      barPercentage: 1.0,
      categoryPercentage: 1.0,
    },
  ];

  if (overlayValues) {
    const overlayColor = FAMILY_COLORS[overlayFamily] || "#d62728";
    datasets.push({
      label: overlayLabel,
      data: binValues(overlayValues),
      backgroundColor: hexToRgba(overlayColor, 0.45),
      borderColor: overlayColor,
      borderWidth: 1,
      barPercentage: 1.0,
      categoryPercentage: 1.0,
    });
  }

  return new Chart(ctx, {
    type: "bar",
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: true, position: "top", labels: { boxWidth: 12, font: { size: 11 } } },
        tooltip: {
          callbacks: {
            label: ctx => ` ${ctx.dataset.label}: ${ctx.parsed.y} starts`,
          },
        },
      },
      scales: {
        x: {
          title: { display: true, text: "Total Return over Holding Period" },
          ticks: { maxTicksLimit: 12 },
          grid: { display: false },
        },
        y: {
          title: { display: true, text: "Number of Starting Points" },
        },
      },
    },
  });
}

function hexToRgba(hex, alpha) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}
