/**
 * SourcePanel component.
 *
 * Lists EvaluatedSources sorted by tier (primary first) then relevance descending.
 * Each entry shows: URL, tier badge, independence badge, relevance bar, excerpt,
 * and — for non-independent sources — the affiliation note.
 */

const TIER_ORDER = { primary: 0, secondary: 1, tertiary: 2 };

export function render(el, { sources }) {
  if (!sources.length) { el.innerHTML = ''; return; }

  const sorted = [...sources].sort((a, b) => {
    const tierDiff = (TIER_ORDER[a.tier] ?? 9) - (TIER_ORDER[b.tier] ?? 9);
    return tierDiff !== 0 ? tierDiff : b.relevance_score - a.relevance_score;
  });

  el.innerHTML = `
    <p class="panel-heading">Sources (${sorted.length})</p>
    <ul class="source-list">
      ${sorted.map(sourceItem).join('')}
    </ul>
  `;
}

function sourceItem(src) {
  const domain = domainFrom(src.url);
  const pct = Math.round(src.relevance_score * 100);
  const indepClass = src.is_independent ? '' : ' not-independent';

  return `
    <li class="source-item${indepClass}" id="source-${src.id}">
      <div class="source-header">
        <a class="source-domain" href="${esc(src.url)}" target="_blank" rel="noopener noreferrer"
           title="${esc(src.url)}">${esc(domain)}</a>
        <span class="badge badge-${src.tier}">${capitalize(src.tier)}</span>
        ${src.is_independent
          ? '<span class="badge badge-indep">Independent</span>'
          : '<span class="badge badge-not-indep">Not independent</span>'}
      </div>

      <div class="relevance-row">
        <span class="relevance-label">Relevance</span>
        <div class="relevance-track">
          <div class="relevance-fill" style="width:${pct}%"></div>
        </div>
        <span class="relevance-pct">${pct}%</span>
      </div>

      ${src.excerpt
        ? `<p class="source-excerpt">${esc(src.excerpt)}</p>`
        : ''}

      ${!src.is_independent && src.affiliation_note
        ? `<p class="affiliation-note">${esc(src.affiliation_note)}</p>`
        : ''}
    </li>
  `;
}

function domainFrom(url) {
  try { return new URL(url).hostname.replace(/^www\./, ''); } catch { return url; }
}

function capitalize(str) {
  return str ? str[0].toUpperCase() + str.slice(1) : '';
}

function esc(str) {
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
