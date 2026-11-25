// Number and text formatting. Pure functions: loaded as a classic script in the page (so
// the site still opens from disk -- module scripts are blocked on file://) and required
// by the Node tests in tests/js/.

const EN_US = new Intl.NumberFormat('en-US');

// '$434.5M', '$61.6M', '$304K', '-$160K'
function fmt(n) {
    if (n == null || !Number.isFinite(n)) return '—';
    const sign = n < 0 ? '-' : '';
    const abs = Math.abs(n);
    // Thresholds account for half-ulp rounding so 999,600 formats as '$1.0M', not '$1000K'.
    if (abs >= 999.95e6) return sign + '$' + (abs / 1e9).toFixed(2) + 'B';
    if (abs >= 999.5e3) return sign + '$' + (abs / 1e6).toFixed(1) + 'M';
    if (abs >= 1e3) return sign + '$' + (abs / 1e3).toFixed(0) + 'K';
    return sign + '$' + Math.round(abs);
}

// Budget-book quirks the formatter has to survive:
//  - a year is null when a program only exists in another year
//    (e.g. Housing Stability has no FY2026 appropriation) -> em dash
//  - some revenue lines are negative (state shares remitted back), so the
//    minus sign has to land outside the dollar sign
function fmtFull(n) {
    if (n == null || !Number.isFinite(n)) return '—';
    return (n < 0 ? '-' : '') + '$' + EN_US.format(Math.abs(n));
}

function pct(n, total) {
    if (!Number.isFinite(n) || !Number.isFinite(total) || total === 0) return '—';
    return ((n / total) * 100).toFixed(1) + '%';
}

function fmtMoney(n) {
    return fmtFull(n);
}

// Line-item text and labels enter HTML markup and attributes; escape all five HTML specials.
function esc(s) {
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

if (typeof module === 'object' && module.exports) {
    module.exports = { fmt, fmtFull, pct, fmtMoney, esc };
}
