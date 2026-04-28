/**
 * SymmetryReport component.
 *
 * Shows whether the Symmetry Principle has been confirmed for this judgment.
 * If symmetry_report is null (not yet run), shows an amber "Pending" notice.
 * If confirmed, shows a green banner with the comparable analyses linked.
 */

export function render(el, { report }) {
  el.innerHTML = `
    <p class="panel-heading">Symmetry check</p>
    ${report ? confirmed(report) : pending()}
  `;
}

function pending() {
  return `
    <div class="symmetry-banner pending">
      <span class="symmetry-icon">⚠</span>
      <span>Symmetry check pending — an equivalent analysis for the opposing political claim has not yet been run. This judgment stands; the gap is surfaced transparently.</span>
    </div>
  `;
}

function confirmed(reportJson) {
  let report;
  try { report = typeof reportJson === 'string' ? JSON.parse(reportJson) : reportJson; }
  catch { report = null; }

  if (!report) return pending();

  return `
    <div class="symmetry-banner confirmed">
      <span class="symmetry-icon">✓</span>
      <span>Symmetry confirmed — equivalent analysis exists for the opposing claim.</span>
    </div>
  `;
}
