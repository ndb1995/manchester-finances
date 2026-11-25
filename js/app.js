// Boot: render every section from window.BUDGET_DATA (data.js), each in isolation.
//
// Local DOM steps run immediately without waiting for the deferred CDN scripts, so headline
// figures, insights, tables and department modals render on first paint even when offline.
// Below-the-fold charts render lazily as they scroll near the viewport (and flush on print).

function showMissingData() {
    document.getElementById('content').innerHTML =
        '<section class="section"><div class="container"><p class="subtitle notice">'
        + 'This page draws everything from the extracted budget data. Run '
        + '<code>python -m budget</code> to generate <code>data.js</code>, then reload.</p></div></section>';
}

function runSafely(name, fn) {
    try {
        fn();
    } catch (err) {
        console.error(`${name} failed:`, err);
    }
}

function bootCharts(D) {
    if (typeof Chart !== 'function') return;
    runSafely('renderFlow', () => renderFlow(D));

    const deferred = [
        ['allocation', renderAllocation],
        ['trend', renderTrend],
        ['growth', renderGrowth],
        ['generalfund', renderGeneralFund],
        ['comparison', renderComparison],
    ];
    if (typeof IntersectionObserver !== 'function') {
        for (const [, step] of deferred) runSafely(step.name, () => step(D));
        return;
    }

    const pending = new Map();
    const observer = new IntersectionObserver(entries => {
        for (const entry of entries) {
            if (!entry.isIntersecting) continue;
            const step = pending.get(entry.target);
            if (!step) continue;
            pending.delete(entry.target);
            observer.unobserve(entry.target);
            runSafely(step.name, () => step(D));
        }
    }, { rootMargin: '300px 0px' });

    for (const [id, step] of deferred) {
        const el = document.getElementById(id);
        if (!el) continue;
        pending.set(el, step);
        observer.observe(el);
    }

    window.addEventListener('beforeprint', () => {
        for (const [el, step] of pending) {
            pending.delete(el);
            observer.unobserve(el);
            runSafely(step.name, () => step(D));
        }
    });
}

(function boot() {
    const D = window.BUDGET_DATA;
    if (!D || typeof D !== 'object' || !Array.isArray(D.years) || !D.years.length) {
        showMissingData();
        return;
    }
    const immediateSteps = [
        fillSlots, renderKpis, renderInsights, renderTable,
        renderDeptNote, renderDeptList, initDeptModal, animateOnScroll,
    ];
    for (const step of immediateSteps) {
        runSafely(step.name, () => step(D));
    }
    if (typeof Chart === 'function') {
        bootCharts(D);
    } else {
        window.addEventListener('DOMContentLoaded', () => bootCharts(D), { once: true });
    }
})();
