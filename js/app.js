// Boot: render every section from window.BUDGET_DATA (data.js), each in isolation.
//
// Each step runs in its own try/catch. A bug, a structurally changed data.js, or the CDN
// charting scripts failing to load then costs only the sections that depend on it -- the
// headline figures and the table still render -- instead of halting the whole script.

function showMissingData() {
    document.getElementById('content').innerHTML =
        '<section class="section"><div class="container"><p class="subtitle notice">'
        + 'This page draws everything from the extracted budget data. Run '
        + '<code>python -m budget</code> to generate <code>data.js</code>, then reload.</p></div></section>';
}

(function boot() {
    const D = window.BUDGET_DATA;
    if (!D || typeof D !== 'object' || !Array.isArray(D.years)) {
        showMissingData();
        return;
    }
    const steps = [
        fillSlots, renderKpis, renderInsights, renderTable,
        renderAllocation, renderTrend, renderGrowth, renderGeneralFund, renderComparison,
        renderFlow, renderDeptNote, renderDeptList, initDeptModal,
    ];
    for (const step of steps) {
        try {
            step(D);
        } catch (err) {
            console.error(`${step.name} failed:`, err);
        }
    }
    animateOnScroll();
})();
