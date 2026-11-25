// Views of window.BUDGET_DATA that the page draws. Pure functions -- no DOM, no Chart.js --
// so the Node tests in tests/js/ can exercise them against the committed data.js.
//
// Every per-year value in the payload is keyed by year label ('FY2026'); D.years lists the
// labels oldest first, and D.yearInfo says which were extracted from a budget book.

function extractedYears(D) {
    return D.years.filter(y => D.yearInfo[y].extracted);
}

function latestYear(D) {
    return D.years[D.years.length - 1];
}

// The year the headline figures are compared against; undefined with a single year.
function previousYear(D) {
    return D.years[D.years.length - 2];
}

// Spending categories, schools included, largest first in the latest year.
function categoryRows(D) {
    const y = latestYear(D);
    return Object.entries(D.categories)
        .map(([category, values]) => ({ category, values }))
        .sort((a, b) => (b.values[y] ?? 0) - (a.values[y] ?? 0));
}

// The same rows without the school district: the General Fund's own categories.
function generalFundRows(D) {
    return categoryRows(D).filter(r => r.category !== D.meta.schoolCategory);
}

// Percent change, or null when either end is missing or the base is zero.
function growth(before, now) {
    if (!Number.isFinite(before) || !Number.isFinite(now) || before === 0) return null;
    return (100 * (now - before)) / Math.abs(before);
}

// Revenue sources -> funds -> spending categories -> departments, for one extracted year.
// Enterprise funds are left out: the diagram shows the tax-supported budget only. The
// departments the extractor splits across categories (inFlow false) get no band of their
// own; their money still reaches the category bands. The Sankey plugin cannot draw a
// zero, negative or missing band, so those are dropped.
function sankeyFlows(D, y) {
    const flows = [];
    for (const [group, v] of Object.entries(D.revenueGroups)) {
        flows.push({ from: group, to: 'General Fund', flow: v[y] });
    }
    flows.push({ from: 'Property Tax', to: 'General Fund', flow: D.propertyTax.gf[y] });
    flows.push({ from: 'Property Tax', to: 'School District', flow: D.propertyTax.msd[y] });
    flows.push({ from: 'State & Other School Revenue', to: 'School District', flow: D.msdOther[y] });

    for (const [category, v] of Object.entries(D.categories)) {
        const fund = category === D.meta.schoolCategory ? 'School District' : 'General Fund';
        flows.push({ from: fund, to: category, flow: v[y] });
    }

    for (const d of D.departments) {
        if (d.inFlow) flows.push({ from: d.category, to: d.name, flow: d.totals[y] });
    }
    return flows.filter(f => Number.isFinite(f.flow) && f.flow > 0);
}

// Sum of the General Fund departments' appropriations. It exceeds D.generalFund by the
// transit subsidy, which the book lists as a department but leaves out of its total.
function generalFundDepartmentTotal(D, y) {
    return D.departments.filter(d => d.generalFund)
        .reduce((sum, d) => sum + (Number.isFinite(d.totals[y]) ? d.totals[y] : 0), 0);
}

// ---- per-year value objects: {FY2025: n, FY2026: n} ------------------------------------

// Whether any year carries a nonzero amount. Filtering on "> 0" would hide negative
// revenue offsets and the visible rows would no longer add up to the department total.
function hasAmount(v) {
    return Object.values(v).some(x => Number.isFinite(x) && x !== 0);
}

// The value in the latest year it is present in (0 when absent everywhere).
function latestValue(v, years) {
    for (let i = years.length - 1; i >= 0; i--) {
        if (v[years[i]] != null) return v[years[i]];
    }
    return 0;
}

// Comparator: largest first, by whichever year is latest present.
function byLatestDesc(years) {
    return (a, b) => latestValue(b, years) - latestValue(a, years);
}

// $ and % change between two years; nulls when either year is missing. % uses |before|
// as the base so a shrinking negative offset still reads as an increase.
function change(v, before, now) {
    const a = before ? v[before] : undefined;
    const b = v[now];
    if (!Number.isFinite(a) || !Number.isFinite(b)) return { amount: null, percent: null };
    return { amount: b - a, percent: a ? (100 * (b - a)) / Math.abs(a) : null };
}

// 'new' for a value that appears in `now` but not `before`, 'ended' for the reverse.
function yearStatus(v, before, now) {
    if (!before) return null;
    if (v[before] == null && v[now] != null) return 'new';
    if (v[now] == null && v[before] != null) return 'ended';
    return null;
}

// Organization (division) figures can undershoot the department total. Aviation's
// by-organization pages print some section totals in a colon-only form
// ("Aviation-Parking & Roadways: 3,589,128") that the extractor deliberately does not
// accept as a section total, so that money reaches the agency bucket with no organization
// label. The department total and its line items are still correct; only the organization
// split is short. Computed per year, because a department can reconcile in one year and
// not another, and a year the department is absent from (null total) has no remainder.
function orgResidual(orgs, totals) {
    const out = {};
    for (const [y, total] of Object.entries(totals)) {
        if (!Number.isFinite(total)) {
            out[y] = null;
            continue;
        }
        const attributed = Object.values(orgs)
            .reduce((sum, v) => sum + (Number.isFinite(v[y]) ? v[y] : 0), 0);
        out[y] = total - attributed;
    }
    return out;
}

// The n largest positive line items of the latest year that has any.
function topItems(items, years, n) {
    for (let i = years.length - 1; i >= 0; i--) {
        const y = years[i];
        const top = items.filter(it => Number.isFinite(it.amounts[y]) && it.amounts[y] > 0)
            .sort((a, b) => b.amounts[y] - a.amounts[y])
            .slice(0, n);
        if (top.length) return { year: y, items: top };
    }
    return { year: null, items: [] };
}

// Truncates extreme small-base growth outliers (e.g. Economic Development +2,944% off a
// $10K base) so they do not crush every other category's bar to a 1px sliver. Preserves
// the true `growth` on every row and flags `capped: true` so the label and note state the
// exact figure honestly.
function capOutlierGrowth(rows) {
    const positives = rows.map(r => r.growth).filter(g => g > 0).sort((a, b) => b - a);
    const hasOutlier = positives.length >= 2 && positives[0] > 100 && positives[0] > positives[1] * 3;
    const cap = hasOutlier ? Math.ceil(positives[1] / 10) * 10 + 15 : Infinity;
    return rows.map(r => ({
        ...r,
        plotted: r.growth > cap ? cap : r.growth,
        capped: r.growth > cap,
    }));
}

if (typeof module === 'object' && module.exports) {
    module.exports = {
        extractedYears, latestYear, previousYear, categoryRows, generalFundRows, growth,
        sankeyFlows, generalFundDepartmentTotal, hasAmount, latestValue, byLatestDesc,
        change, yearStatus, orgResidual, topItems, capOutlierGrowth,
    };
}
