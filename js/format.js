// Number and text formatting. Pure functions: loaded as a classic script in the page (so
// the site still opens from disk -- module scripts are blocked on file://) and required
// by the Node tests in tests/js/.

// '$434.5M', '$61.6M', '$304K'
function fmt(n) {
    if (n >= 1e9) return '$' + (n / 1e9).toFixed(2) + 'B';
    if (n >= 1e6) return '$' + (n / 1e6).toFixed(1) + 'M';
    if (n >= 1e3) return '$' + (n / 1e3).toFixed(0) + 'K';
    return '$' + n;
}

function fmtFull(n) {
    return '$' + n.toLocaleString('en-US');
}

function pct(n, total) {
    return ((n / total) * 100).toFixed(1) + '%';
}

// Budget-book quirks the formatter has to survive:
//  - a year is null when a program only exists in another year
//    (e.g. Housing Stability has no FY2026 appropriation) -> em dash
//  - some revenue lines are negative (state shares remitted back), so the
//    minus sign has to land outside the dollar sign
function fmtMoney(n) {
    if (n == null || !Number.isFinite(n)) return '—';
    return (n < 0 ? '-' : '') + fmtFull(Math.abs(n));
}

// Line-item text comes from the PDFs; keep stray &/< from breaking markup.
function esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

if (typeof module === 'object' && module.exports) {
    module.exports = { fmt, fmtFull, pct, fmtMoney, esc };
}
