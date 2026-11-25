// Department drill-down: the index list under the Sankey, and the detail modal.
// Columns are the extracted years; the change columns compare the last two of them.

let modalTriggerEl = null;

function comparedYears(D) {
    const years = extractedYears(D);
    return { years, before: years[years.length - 2], now: years[years.length - 1] };
}

function statusBadge(v, before, now) {
    const status = yearStatus(v, before, now);
    if (status === 'new') return ` <span class="badge-new">new ${esc(now)}</span>`;
    if (status === 'ended') return ' <span class="badge-gone">ended</span>';
    return '';
}

function changeCells(v, before, now) {
    const { amount, percent } = change(v, before, now);
    const cls = amount > 0 ? 'up' : amount < 0 ? 'down' : '';
    return `<td class="${cls}">${amount == null ? '—' : fmtMoney(amount)}</td>`
        + `<td class="${cls}">${percent == null ? '—' : percent.toFixed(1) + '%'}</td>`;
}

function yearCells(v, years) {
    return years.map(y => `<td>${fmtMoney(v[y])}</td>`).join('');
}

function headRow(leading, { years, before, now }) {
    const span = before ? esc(`${before} → ${now}`) : '';
    return `<tr>${leading.map(h => `<th>${esc(h)}</th>`).join('')}${years.map(y => `<th>${esc(y)}</th>`).join('')}`
        + `<th title="${span}">$ Change</th><th title="${span}">%</th></tr>`;
}

function lineRows(items, { years, before, now }) {
    const byLatest = byLatestDesc(years);
    return items.filter(i => hasAmount(i.amounts))
        .sort((a, b) => byLatest(a.amounts, b.amounts))
        .map(i => `<tr><td>${esc(i.code)}</td><td>${esc(i.desc)}${statusBadge(i.amounts, before, now)}</td>`
            + `${yearCells(i.amounts, years)}${changeCells(i.amounts, before, now)}</tr>`)
        .join('');
}

// Organization (division) breakdown -- the only view of internal structure for departments
// like Public Works whose line items span several categories. When the organizations fall
// short of the department total (see orgResidual), the shortfall is an explicit final row
// rather than a column that silently fails to add up.
function orgRows(orgs, totals, cols) {
    const { years, before, now } = cols;
    const byLatest = byLatestDesc(years);
    const rows = Object.entries(orgs)
        .filter(([, v]) => hasAmount(v))
        .sort((a, b) => byLatest(a[1], b[1]))
        .map(([name, v]) => `<tr><td>${esc(name)}${statusBadge(v, before, now)}</td>`
            + `${yearCells(v, years)}${changeCells(v, before, now)}</tr>`);

    // Only when a year actually falls short; hasAmount ignores the zero and null years, so a
    // fully reconciled department gains no extra row.
    const rest = orgResidual(orgs, totals);
    if (hasAmount(rest)) {
        rows.push('<tr class="org-residual"><td>Not attributed to an organization</td>'
            + `${yearCells(rest, years)}${changeCells(rest, before, now)}</tr>`);
    }
    return rows.join('');
}

// Fills one table (and its heading) or hides both when there is nothing to show.
function fillTable(prefix, headHtml, bodyHtml) {
    document.getElementById(`${prefix}Head`).innerHTML = headHtml;
    document.getElementById(`${prefix}Body`).innerHTML = bodyHtml;
    document.getElementById(`${prefix}Title`).hidden = !bodyHtml;
    document.getElementById(`${prefix}Table`).hidden = !bodyHtml;
}

function openDeptDetail(D, name) {
    const d = D.departments.find(x => x.name === name);
    if (!d) return;
    const cols = comparedYears(D), { before, now } = cols;

    document.getElementById('deptModalTitle').textContent = d.name;

    // Meta line: only mention the sides of the ledger the department has. Aviation -
    // Revenues (Various) is revenue-only; Housing Stability has no FY2026 appropriation.
    const versus = v => (before ? ` (${before} ${fmtMoney(v[before])})` : '');
    const spends = d.expenses.length > 0 || hasAmount(d.totals);
    const meta = [d.generalFund ? d.category : `Enterprise fund ${d.fund}`];
    if (spends) meta.push(`${now} appropriation ${fmtMoney(d.totals[now])}${versus(d.totals)}`);
    if (hasAmount(d.revenueTotals)) {
        meta.push(`${now} revenue ${fmtMoney(d.revenueTotals[now])}${versus(d.revenueTotals)}`);
    }
    document.getElementById('deptModalMeta').textContent = meta.join(' · ');

    const orgHtml = d.orgs ? orgRows(d.orgs, d.totals, cols) : '';
    fillTable('deptOrg', headRow(['Organization'], cols), orgHtml);

    // The caption only earns its space when one of the two rows it explains is on screen --
    // an unnamed division from the book, or the leftover row.
    const unnamed = d.orgs?.[D.meta.unattributedOrg];
    const explained = (unnamed && hasAmount(unnamed)) || (d.orgs && hasAmount(orgResidual(d.orgs, d.totals)));
    document.getElementById('deptOrgNote').hidden = !(orgHtml && explained);

    fillTable('deptExp', headRow(['Code', 'Description'], cols), lineRows(d.expenses, cols));
    fillTable('deptRev', headRow(['Code', 'Description'], cols), lineRows(d.revenues, cols));

    // Top-items bar chart: expenses when there are any (revenue-only departments chart their
    // revenues), in the latest year that has any.
    const source = d.expenses.some(i => hasAmount(i.amounts)) ? d.expenses : d.revenues;
    const top = topItems(source, cols.years, 8);
    clearChart('deptTopChart');
    const canChart = typeof Chart === 'function' && top.items.length > 0;
    document.getElementById('deptChartWrap').hidden = !canChart;
    if (canChart) {
        drawChart('deptTopChart', {
            type: 'bar',
            data: {
                labels: top.items.map(i => i.desc),
                datasets: [{
                    label: top.year,
                    data: top.items.map(i => i.amounts[top.year]),
                    backgroundColor: colorFor(d.category),
                    borderRadius: 4,
                }],
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                plugins: { legend: { display: false }, tooltip: seriesTooltip('x') },
                scales: {
                    x: { ticks: moneyTicks() },
                    y: { grid: { display: false }, ticks: { font: { size: 11 } } },
                },
            },
        });
    }

    const modal = document.getElementById('deptModal');
    modalTriggerEl = document.activeElement;
    modal.hidden = false;
    document.body.style.overflow = 'hidden';
    modal.querySelector('.modal-close')?.focus();
}

function closeDeptDetail() {
    const modal = document.getElementById('deptModal');
    if (modal.hidden) return;
    modal.hidden = true;
    document.body.style.overflow = '';
    if (modalTriggerEl && typeof modalTriggerEl.focus === 'function') {
        modalTriggerEl.focus();
    }
    modalTriggerEl = null;
}

function initDeptModal() {
    const modal = document.getElementById('deptModal');
    modal.querySelector('.modal-close').addEventListener('click', closeDeptDetail);
    modal.addEventListener('click', e => {
        if (e.target === modal) closeDeptDetail();
    });
    document.addEventListener('keydown', e => {
        if (modal.hidden) return;
        if (e.key === 'Escape') {
            closeDeptDetail();
            return;
        }
        if (e.key === 'Tab') {
            const focusables = [...modal.querySelectorAll(
                'button:not([hidden]):not([disabled]), [href], [tabindex]:not([tabindex="-1"])'
            )].filter(el => el.offsetParent !== null);
            if (!focusables.length) return;
            const first = focusables[0], last = focusables[focusables.length - 1];
            if (e.shiftKey && document.activeElement === first) {
                e.preventDefault();
                last.focus();
            } else if (!e.shiftKey && document.activeElement === last) {
                e.preventDefault();
                first.focus();
            }
        }
    });
}

// Every department is reachable here; the Sankey only makes the single-category General
// Fund bands clickable.
function renderDeptList(D) {
    const el = document.getElementById('deptList');
    const { years, now } = comparedYears(D);
    // Sort weight: latest appropriation, then revenue for revenue-only departments.
    const weight = d => latestValue(d.totals, years) || latestValue(d.revenueTotals, years);
    // Keep a department if either side of its ledger has money in any year.
    const listed = D.departments.filter(d => hasAmount(d.totals) || hasAmount(d.revenueTotals));
    const groups = [
        ['General Fund', listed.filter(d => d.generalFund)],
        ['Enterprise Funds', listed.filter(d => !d.generalFund)],
    ];

    for (const [label, members] of groups) {
        if (!members.length) continue;
        const head = document.createElement('div');
        head.className = 'dept-list-label';
        head.textContent = label;
        el.appendChild(head);
        for (const d of members.sort((a, b) => weight(b) - weight(a))) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.textContent = d.generalFund ? d.name : `${d.name} (Enterprise)`;
            btn.title = hasAmount(d.totals)
                ? `${now} appropriation ${fmtMoney(d.totals[now])}`
                : `${now} revenue ${fmtMoney(d.revenueTotals[now])}`;
            btn.addEventListener('click', () => openDeptDetail(D, d.name));
            el.appendChild(btn);
        }
    }
}
