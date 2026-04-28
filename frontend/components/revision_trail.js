/**
 * RevisionTrail component.
 *
 * Renders the full judgment history as a `<details>` accordion list.
 * The most recent (active) judgment is open by default; older ones are closed.
 * No judgment is ever hidden — the full audit trail is always accessible.
 */

export function render(el, { history }) {
  if (!history || !history.judgments.length) { el.innerHTML = ''; return; }

  const judgments = [...history.judgments].reverse(); // newest first

  el.innerHTML = `
    <p class="panel-heading">Judgment history (${judgments.length})</p>
    <ol class="judgment-list">
      ${judgments.map((j, i) => judgmentEntry(j, i === 0)).join('')}
    </ol>
  `;
}

function judgmentEntry(j, isCurrent) {
  const date = new Date(j.created_at).toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });

  return `
    <li class="judgment-entry">
      <details ${isCurrent ? 'open' : ''}>
        <summary class="judgment-summary">
          <span class="rating-badge ${j.rating}">
            <span class="rating-dot"></span>${j.rating}
          </span>
          ${isCurrent ? '<span class="judgment-current-tag">current</span>' : ''}
          <span class="judgment-timestamp">${esc(date)}</span>
        </summary>
        <div class="judgment-body">
          <p class="judgment-rationale">${esc(j.rationale)}</p>
          <p class="judgment-analyst">Analyst: ${esc(j.analyst)}</p>
          ${j.superseded_by ? `
            <div class="judgment-trigger">
              <span class="judgment-trigger-label">Revised because:</span>
              ${esc(j.superseded_by.trigger_evidence)}
            </div>
          ` : ''}
        </div>
      </details>
    </li>
  `;
}

function esc(str) {
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
