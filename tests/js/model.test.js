// Node tests for the page's pure logic: `node --test`.
// js/format.js and js/model.js are classic browser scripts that also export for Node, and
// data.js is the committed payload, so these run against the numbers the site serves.
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

global.window = {};
require(path.join(__dirname, '..', '..', 'data.js'));
const D = window.BUDGET_DATA;
const m = require(path.join(__dirname, '..', '..', 'js', 'model.js'));
const f = require(path.join(__dirname, '..', '..', 'js', 'format.js'));

const sum = xs => xs.reduce((a, b) => a + b, 0);

test('every extracted year: the flow diagram balances at both funds', () => {
    for (const y of m.extractedYears(D)) {
        const flows = m.sankeyFlows(D, y);
        const into = to => sum(flows.filter(x => x.to === to).map(x => x.flow));
        const out = from => sum(flows.filter(x => x.from === from).map(x => x.flow));
        assert.equal(into('General Fund'), D.generalFund[y], y);
        assert.equal(out('General Fund'), D.generalFund[y], y);
        assert.equal(into('School District'), D.categories[D.meta.schoolCategory][y], y);
        assert.ok(flows.every(x => Number.isFinite(x.flow) && x.flow > 0), y);
    }
});

test('flow department bands never exceed their category band', () => {
    for (const y of m.extractedYears(D)) {
        const flows = m.sankeyFlows(D, y);
        for (const [category, v] of Object.entries(D.categories)) {
            const depts = sum(flows.filter(x => x.from === category).map(x => x.flow));
            assert.ok(depts <= v[y], `${y} ${category}: ${depts} > ${v[y]}`);
        }
    }
});

test('General Fund departments exceed the fund total by exactly the transit subsidy', () => {
    for (const y of m.extractedYears(D)) {
        assert.equal(m.generalFundDepartmentTotal(D, y) - D.transitSubsidy[y], D.generalFund[y]);
    }
});

test('category rows are ordered largest first in the latest year', () => {
    const y = m.latestYear(D);
    const values = m.categoryRows(D).map(r => r.values[y]);
    assert.deepEqual(values, [...values].sort((a, b) => b - a));
    assert.ok(!m.generalFundRows(D).some(r => r.category === D.meta.schoolCategory));
});

test('hasAmount keeps negative offsets and ignores zero and null years', () => {
    assert.equal(m.hasAmount({ FY2025: -160000, FY2026: null }), true);
    assert.equal(m.hasAmount({ FY2025: 0, FY2026: null }), false);
});

test('change uses |before| as the base and is null without both years', () => {
    assert.deepEqual(m.change({ A: -100, B: -50 }, 'A', 'B'), { amount: 50, percent: 50 });
    assert.deepEqual(m.change({ A: null, B: 5 }, 'A', 'B'), { amount: null, percent: null });
    assert.deepEqual(m.change({ A: 0, B: 5 }, 'A', 'B'), { amount: 5, percent: null });
    assert.deepEqual(m.change({ B: 5 }, undefined, 'B'), { amount: null, percent: null });
});

test('yearStatus distinguishes new, ended and continuing lines', () => {
    assert.equal(m.yearStatus({ A: null, B: 1 }, 'A', 'B'), 'new');
    assert.equal(m.yearStatus({ A: 1, B: null }, 'A', 'B'), 'ended');
    assert.equal(m.yearStatus({ A: 1, B: 2 }, 'A', 'B'), null);
    assert.equal(m.yearStatus({ B: 2 }, undefined, 'B'), null);
});

test('orgResidual is per year and null for a year the department is absent from', () => {
    const orgs = { X: { A: 60, B: 70 }, Y: { A: 40, B: null } };
    assert.deepEqual(m.orgResidual(orgs, { A: 100, B: 90 }), { A: 0, B: 20 });
    assert.deepEqual(m.orgResidual(orgs, { A: null, B: 70 }), { A: null, B: 0 });
});

test('Public Works organizations reconcile with its total in the served data', () => {
    const pw = D.departments.find(d => d.name === 'Public Works');
    assert.equal(m.hasAmount(m.orgResidual(pw.orgs, pw.totals)), false);
});

test('topItems falls back to the latest year that has positive items', () => {
    const items = [{ amounts: { A: 5, B: null } }, { amounts: { A: 9, B: 0 } }];
    const top = m.topItems(items, ['A', 'B'], 8);
    assert.equal(top.year, 'A');
    assert.deepEqual(top.items.map(i => i.amounts.A), [9, 5]);
});

test('latestValue and byLatestDesc sort by the latest present year', () => {
    const rows = [{ A: 1, B: null }, { A: 1, B: 10 }, { A: 50, B: null }];
    assert.deepEqual(rows.sort(m.byLatestDesc(['A', 'B'])).map(r => m.latestValue(r, ['A', 'B'])), [50, 10, 1]);
});

test('capOutlierGrowth truncates extreme small-base outliers while preserving true growth', () => {
    const capped = m.capOutlierGrowth([
        { label: 'Economic Development', growth: 2944.2 },
        { label: 'General Government', growth: 42.9 },
        { label: 'Other', growth: -13.7 },
    ]);
    assert.equal(capped[0].capped, true);
    assert.equal(capped[0].growth, 2944.2);
    assert.equal(capped[0].plotted, 65);
    assert.equal(capped[1].capped, false);
    assert.equal(capped[1].plotted, 42.9);

    const normal = m.capOutlierGrowth([
        { label: 'A', growth: 40 },
        { label: 'B', growth: 25 },
    ]);
    assert.ok(normal.every(r => !r.capped && r.plotted === r.growth));
});

test('money and HTML formatting', () => {
    assert.equal(f.fmt(434511186), '$434.5M');
    assert.equal(f.fmt(304420), '$304K');
    assert.equal(f.fmt(-50000), '-$50K');
    assert.equal(f.fmt(999600), '$1.0M');
    assert.equal(f.fmt(999960000), '$1.00B');
    assert.equal(f.fmt(null), '—');
    assert.equal(f.fmtMoney(-160000), '-$160,000');
    assert.equal(f.fmtMoney(null), '—');
    assert.equal(f.pct(61551254, 434511186), '14.2%');
    assert.equal(f.pct(10, 0), '—');
    assert.equal(f.esc('a<b & "c" \'d\'>'), 'a&lt;b &amp; &quot;c&quot; &#39;d&#39;&gt;');
});
