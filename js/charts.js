// Chart.js plumbing every chart shares: colors from the CSS palette, one chart per canvas,
// the option fragments the charts would otherwise repeat, and the toggle button groups.

// Every chart color is a custom property in css/styles.css, so the palette lives in one place.
const COLOR_VARS = {
    'Education (MSD)': '--blue',
    'Public Safety': '--red',
    'Retirement': '--purple',
    'General Government': '--teal',
    'Highway & Streets': '--orange',
    'Health, Dental & Insurance': '--cyan',
    'Debt Service': '--gray',
    'Other': '--gray-mid',
    'Culture & Recreation': '--mint',
    'Health & Welfare': '--pink',
    'Economic Development': '--yellow',
    // fund nodes in the flow diagram, and department drill-down categories
    'General Fund': '--navy-light',
    'School District': '--blue',
    'Mixed (see line items)': '--navy-light',
    'Enterprise Funds': '--gray',
};

const cssVarCache = new Map();

function cssVar(name) {
    if (!cssVarCache.has(name)) {
        cssVarCache.set(name, getComputedStyle(document.documentElement).getPropertyValue(name).trim());
    }
    return cssVarCache.get(name);
}

// A category's or fund's color; anything unlisted (a revenue group, a department, a
// category a future book introduces) gets the neutral accent.
function colorFor(name) {
    return cssVar(COLOR_VARS[name] || '--blue-light');
}

const chartsByCanvas = {};

// Draws `config` on the canvas, replacing whatever chart was there. Returns null when
// Chart.js did not load (e.g. opened offline from disk).
function drawChart(canvasId, config) {
    if (typeof Chart !== 'function') return null;
    clearChart(canvasId);
    const ctx = document.getElementById(canvasId).getContext('2d');
    chartsByCanvas[canvasId] = new Chart(ctx, config);
    return chartsByCanvas[canvasId];
}

function clearChart(canvasId) {
    if (chartsByCanvas[canvasId]) {
        chartsByCanvas[canvasId].destroy();
        delete chartsByCanvas[canvasId];
    }
}

// ---- option fragments ------------------------------------------------------------------

function moneyTicks() {
    return { callback: v => fmt(v) };
}

// Pie/doughnut legend whose entries carry each slice's amount: 'Public Safety  $61.6M'.
// Moves below the chart on narrow viewports so the legend does not crowd out the canvas,
// and reads Chart.js's slice visibility so toggled-off slices render struck through.
function moneyLegend(fontSize, padding) {
    const narrow = typeof window !== 'undefined' && window.matchMedia?.('(max-width: 640px)').matches;
    return {
        position: narrow ? 'bottom' : 'right',
        labels: {
            padding,
            font: { size: fontSize },
            generateLabels(chart) {
                const ds = chart.data.datasets[0];
                return chart.data.labels.map((label, i) => ({
                    text: label + '  ' + fmt(ds.data[i]),
                    fillStyle: ds.backgroundColor[i],
                    fontColor: cssVar('--ink'),
                    strokeStyle: '#ccc',
                    lineWidth: 0,
                    hidden: !chart.getDataVisibility(i),
                    index: i,
                }));
            },
        },
    };
}

// Pie/doughnut slice: ' Public Safety: $61,551,254 (14.2%)' of `total`.
function sliceTooltip(total) {
    return { callbacks: { label: ctx => ` ${ctx.label}: ${fmtFull(ctx.parsed)} (${pct(ctx.parsed, total)})` } };
}

// One series value: ' FY2026: $61,551,254'. `axis` is the value axis.
function seriesTooltip(axis) {
    return { callbacks: { label: ctx => ` ${ctx.dataset.label}: ${fmtFull(ctx.parsed[axis])}` } };
}

// Value printed outside the end of each bar (chartjs-plugin-datalabels), flipping to the
// start side for negative bars so '-13.7%' sits to the left of a negative bar rather than
// overlapping its body.
function barLabels(formatter, size) {
    return {
        anchor: ctx => (ctx.dataset.data[ctx.dataIndex] < 0 ? 'start' : 'end'),
        align: ctx => (ctx.dataset.data[ctx.dataIndex] < 0 ? 'start' : 'end'),
        clip: false,
        color: cssVar('--ink'),
        font: { size, weight: '600' },
        formatter,
    };
}

// ---- toggle button groups --------------------------------------------------------------

// Calls onSelect(value) with the clicked button's data-value and marks it active.
function bindToggle(groupId, onSelect) {
    const group = document.getElementById(groupId);
    group.addEventListener('click', e => {
        const btn = e.target.closest('button');
        if (!btn || !group.contains(btn)) return;
        for (const b of group.querySelectorAll('button')) {
            b.classList.toggle('active', b === btn);
            b.setAttribute('aria-pressed', String(b === btn));
        }
        onSelect(btn.dataset.value);
    });
}

// Builds one button per value, for groups whose options come from the data.
function fillToggle(groupId, values, active) {
    const group = document.getElementById(groupId);
    group.replaceChildren(...values.map(v => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.dataset.value = v;
        btn.textContent = v;
        btn.classList.toggle('active', v === active);
        btn.setAttribute('aria-pressed', String(v === active));
        return btn;
    }));
}
