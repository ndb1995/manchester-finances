// The page's sections, one render function each. Each takes the payload and is called by
// app.js inside its own try/catch, so one failing section cannot take the rest down.
// Nothing here hardcodes a year or a figure: labels, headline numbers and prose are all
// derived from the payload, so a new year's data.js updates the whole page.

// ---- header, headline figures and copy -------------------------------------------------

// Fills every [data-slot] element with the matching year label or text.
function fillSlots(D) {
    const latest = latestYear(D);
    const slots = {
        latest,
        latestNumber: latest.replace(/^FY/, ''),
        previous: previousYear(D) ?? '',
        first: D.years[0],
        period: D.yearInfo[latest].period,
    };
    for (const el of document.querySelectorAll('[data-slot]')) {
        el.textContent = slots[el.dataset.slot] ?? '';
    }
    document.title = `Manchester NH Budget Visualizer - ${latest}`;

    const asOf = D.yearInfo[latest].asOf;
    document.getElementById('footerEdition').textContent =
        `${latest} Budget Book · ${asOf ? `Data as of ${asOf} · ` : ''}Built for transparency.`;
}

// A year-over-year line, with the arrow and the up/down colour taken from the sign of
// the change: a decrease reads "↓ x% from FY2025" in red rather than a green rise.
function setDelta(id, now, before, beforeLabel) {
    const el = document.getElementById(id);
    if (!Number.isFinite(before)) {
        el.textContent = '';
        return;
    }
    const diff = now - before;
    el.className = 'change ' + (diff < 0 ? 'down' : 'up');
    el.textContent = `${diff < 0 ? '↓' : '↑'} ${pct(Math.abs(diff), before)} from ${beforeLabel}`;
}

function renderKpis(D) {
    const y = latestYear(D), prev = previousYear(D);
    const school = D.categories[D.meta.schoolCategory];
    document.getElementById('kpiTotal').textContent = fmt(D.citywide[y]);
    setDelta('kpiTotalChange', D.citywide[y], D.citywide[prev], prev);
    document.getElementById('kpiGeneralFund').textContent = fmt(D.generalFund[y]);
    setDelta('kpiGeneralFundChange', D.generalFund[y], D.generalFund[prev], prev);
    document.getElementById('kpiMsd').textContent = fmt(school[y]);
    setDelta('kpiMsdChange', school[y], school[prev], prev);
    document.getElementById('kpiEducationShare').textContent =
        ((100 * school[y]) / D.citywide[y]).toFixed(0) + '%';
}

function renderInsights(D) {
    const y = latestYear(D), first = D.years[0], total = D.citywide[y];
    const [a, b, c] = categoryRows(D);
    const share = r => `${fmt(r.values[y])} (${pct(r.values[y], total)})`;
    const topThree = a.values[y] + b.values[y] + c.values[y];
    document.getElementById('insightAllocation').innerHTML =
        `<strong>${esc(a.category)}</strong> receives the largest share at <strong>${share(a)}</strong> `
        + `of the total budget, followed by <strong>${esc(b.category)}</strong> at <strong>${share(b)}</strong>. `
        + `Together, ${esc(a.category)}, ${esc(b.category)}, and ${esc(c.category)} account for `
        + `<strong>${pct(topThree, total)}</strong> of all spending.`;

    const gf = D.generalFund, g = growth(gf[first], gf[y]);
    const topGf = generalFundRows(D)[0];
    document.getElementById('insightGeneralFund').innerHTML =
        `The <strong>General Fund</strong> has ${g < 0 ? 'shrunk' : 'grown'} from `
        + `<strong>${fmt(gf[first])}</strong> in ${first} to <strong>${fmt(gf[y])}</strong> in ${y} `
        + `&mdash; ${g < 0 ? 'a decrease' : 'an increase'} of <strong>${Math.abs(g).toFixed(1)}%</strong>. `
        + `Excluding the school district budget, <strong>${esc(topGf.category)}</strong> takes `
        + `<strong>${pct(topGf.values[y], gf[y])}</strong> of the General Fund.`;
}

// ---- the category table ----------------------------------------------------------------

function renderTable(D) {
    const cells = values => D.years.map(y => `<td>${fmtMoney(values[y])}</td>`).join('');
    document.getElementById('tableHead').innerHTML =
        `<tr><th>Category</th>${D.years.map(y => `<th>${y}</th>`).join('')}</tr>`;
    document.getElementById('tableBody').innerHTML =
        categoryRows(D).map(r => `<tr class="category-row"><td>${esc(r.category)}</td>${cells(r.values)}</tr>`).join('')
        + `<tr class="total"><td>Total Budget</td>${cells(D.citywide)}</tr>`
        + `<tr class="general-fund"><td>General Fund Budget</td>${cells(D.generalFund)}</tr>`;
}

// ---- charts ----------------------------------------------------------------------------

function renderAllocation(D) {
    const y = latestYear(D), rows = categoryRows(D), total = D.citywide[y];
    const labels = rows.map(r => r.category);
    const values = rows.map(r => r.values[y]);
    const colors = labels.map(colorFor);

    const draw = view => drawChart('allocationChart', view === 'bar' ? {
        type: 'bar',
        data: { labels, datasets: [{ label: `${y} Budget`, data: values, backgroundColor: colors, borderRadius: 4 }] },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { display: false },
                tooltip: { callbacks: { label: ctx => ` ${fmtFull(ctx.parsed.x)} (${pct(ctx.parsed.x, total)})` } },
                datalabels: barLabels(v => fmt(v), 11),
            },
            scales: { x: { ticks: moneyTicks(), grid: { display: false } }, y: { grid: { display: false } } },
        },
        plugins: [ChartDataLabels],
    } : {
        type: view,
        data: { labels, datasets: [{ data: values, backgroundColor: colors, borderWidth: 2, borderColor: cssVar('--white') }] },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: { legend: moneyLegend(12, 14), tooltip: sliceTooltip(total) },
        },
        plugins: [ChartDataLabels],
    });

    draw('pie');
    bindToggle('allocationToggle', draw);
}

function renderTrend(D) {
    const rows = categoryRows(D);
    const draw = view => {
        const isLine = view === 'line';
        drawChart('trendChart', {
            type: isLine ? 'line' : 'bar',
            data: {
                labels: D.years,
                datasets: rows.map(r => ({
                    label: r.category,
                    data: D.years.map(y => r.values[y]),
                    backgroundColor: colorFor(r.category),
                    borderColor: colorFor(r.category),
                    borderWidth: isLine ? 3 : 1,
                    tension: 0.3,
                    pointRadius: isLine ? 4 : undefined,
                    pointHoverRadius: isLine ? 6 : undefined,
                })),
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: {
                        position: 'bottom',
                        // Chart.js 4 signature is filter(legendItem, chartData). Only the six
                        // largest categories are listed, for readability.
                        labels: { boxWidth: 14, padding: 12, font: { size: 11 }, filter: item => item.datasetIndex < 6 },
                    },
                    tooltip: seriesTooltip('y'),
                },
                scales: {
                    x: { stacked: view === 'stacked', grid: { display: false } },
                    y: { stacked: view === 'stacked', ticks: moneyTicks() },
                },
            },
        });
    };
    draw('bar');
    bindToggle('trendToggle', draw);
}

function renderGrowth(D) {
    const first = D.years[0], y = latestYear(D);
    const rows = categoryRows(D)
        .map(r => ({ label: r.category, growth: growth(r.values[first], r.values[y]) }))
        .filter(r => r.growth != null)
        .sort((a, b) => b.growth - a.growth);

    drawChart('growthChart', {
        type: 'bar',
        data: {
            labels: rows.map(r => r.label),
            datasets: [{
                label: `% Growth ${first} → ${y}`,
                data: rows.map(r => r.growth),
                backgroundColor: rows.map(r => colorFor(r.label)),
                borderRadius: 4,
            }],
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { display: false },
                tooltip: { callbacks: { label: ctx => ` ${ctx.parsed.x.toFixed(1)}% growth` } },
                datalabels: barLabels(v => v.toFixed(1) + '%', 11),
            },
            scales: {
                x: { ticks: { callback: v => v + '%' }, grid: { display: false } },
                y: { grid: { display: false } },
            },
        },
        plugins: [ChartDataLabels],
    });
}

function renderGeneralFund(D) {
    const y = latestYear(D), rows = generalFundRows(D);
    drawChart('generalFundChart', {
        type: 'doughnut',
        data: {
            labels: rows.map(r => r.category),
            datasets: [{
                data: rows.map(r => r.values[y]),
                backgroundColor: rows.map(r => colorFor(r.category)),
                borderWidth: 2,
                borderColor: cssVar('--white'),
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: { legend: moneyLegend(10, 10), tooltip: sliceTooltip(D.generalFund[y]) },
        },
        plugins: [ChartDataLabels],
    });

    drawChart('generalFundTrendChart', {
        type: 'bar',
        data: {
            labels: D.years,
            datasets: [
                { label: 'General Fund', data: D.years.map(yr => D.generalFund[yr]), backgroundColor: cssVar('--blue'), borderRadius: 6 },
                { label: 'Total Budget', data: D.years.map(yr => D.citywide[yr]), backgroundColor: cssVar('--gray'), borderRadius: 6 },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { position: 'bottom' },
                tooltip: seriesTooltip('y'),
                datalabels: barLabels(v => fmt(v), 10),
            },
            scales: {
                y: { ticks: moneyTicks(), grid: { display: true, color: cssVar('--grid') } },
                x: { grid: { display: false } },
            },
        },
        plugins: [ChartDataLabels],
    });
}

function renderComparison(D) {
    const y = latestYear(D), prev = previousYear(D);
    if (!prev) {
        document.getElementById('comparison').hidden = true;
        return;
    }
    const rows = categoryRows(D);
    drawChart('comparisonChart', {
        type: 'bar',
        data: {
            labels: rows.map(r => r.category.split('(')[0].trim()),
            datasets: [
                { label: prev, data: rows.map(r => r.values[prev]), backgroundColor: cssVar('--gray-mid'), borderRadius: 4 },
                { label: y, data: rows.map(r => r.values[y]), backgroundColor: rows.map(r => colorFor(r.category)), borderRadius: 4 },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: { legend: { position: 'bottom' }, tooltip: seriesTooltip('y') },
            scales: {
                x: { grid: { display: false }, ticks: { maxRotation: 45, font: { size: 11 } } },
                y: { ticks: moneyTicks(), grid: { color: cssVar('--grid') } },
            },
        },
    });
}

// ---- money flow (Sankey) ---------------------------------------------------------------

function renderFlow(D) {
    const years = extractedYears(D), latest = years[years.length - 1];
    const draw = y => drawChart('sankeyChart', {
        type: 'sankey',
        data: {
            datasets: [{
                data: sankeyFlows(D, y),
                colorFrom: c => colorFor(c.dataset.data[c.dataIndex].from),
                colorTo: c => colorFor(c.dataset.data[c.dataIndex].to),
                colorMode: 'gradient',
                nodeWidth: 14,
                borderWidth: 0,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: c => {
                            const f = c.dataset.data[c.dataIndex];
                            return ` ${f.from} → ${f.to}: ${fmtFull(f.flow)} (${pct(f.flow, D.citywide[y])})`;
                        },
                    },
                },
            },
            onClick: (evt, els, chart) => {
                if (!els.length) return;
                const f = chart.data.datasets[0].data[els[0].index];
                if (D.departments.some(d => d.name === f.to)) openDeptDetail(D, f.to);
            },
        },
    });

    fillToggle('flowYearToggle', years, latest);
    bindToggle('flowYearToggle', draw);
    draw(latest);
}

// Why the departments listed under the flow add up to more than the General Fund total.
function renderDeptNote(D) {
    const years = extractedYears(D), y = years[years.length - 1];
    const el = document.getElementById('gfDeptNote');
    const transit = D.transitSubsidy[y];
    if (!transit) {
        el.hidden = true;
        return;
    }
    const sum = generalFundDepartmentTotal(D, y), gf = D.generalFund[y];
    el.textContent = `Adding up the General Fund departments below gives ${fmtFull(sum)} for ${y}, `
        + `${fmtFull(sum - gf)} more than the ${fmtFull(gf)} General Fund total quoted elsewhere on `
        + `this page; the budget book's own summary excludes the ${fmtFull(transit)} transit subsidy `
        + 'from the General Fund total while listing it as a separate department appropriation.';
}

// ---- entrance animation ----------------------------------------------------------------

function animateOnScroll() {
    const observer = new IntersectionObserver(entries => {
        for (const entry of entries) {
            if (entry.isIntersecting) {
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0)';
            }
        }
    }, { threshold: 0.1, rootMargin: '0px 0px -50px 0px' });

    for (const el of document.querySelectorAll('.chart-card, .insight-box')) {
        el.style.opacity = '0';
        el.style.transform = 'translateY(20px)';
        el.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
        observer.observe(el);
    }
}
