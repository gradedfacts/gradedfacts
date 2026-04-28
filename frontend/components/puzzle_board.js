/**
 * PuzzleBoard component.
 *
 * Renders the active judgment as:
 *   1. A rating badge + verdict text.
 *   2. The rationale paragraph.
 *   3. A grid of colored tiles — one per source — where tile color encodes
 *      source quality, not claim direction (supports_claim is not stored):
 *
 *      Green  — independent primary, relevance ≥ 0.6  (strong evidence)
 *      Yellow — independent secondary, relevance ≥ 0.6 (moderate evidence)
 *      Red    — not independent (compromised source)
 *      Gray   — tertiary or relevance < 0.6            (weak / excluded)
 *
 * Clicking a tile scrolls to and highlights the source in the source panel.
 */

export function render(el, { judgment, sources }) {
  if (!judgment) { el.innerHTML = ''; return; }

  const rating = judgment.rating; // 'verified' | 'speculative' | 'debunked' | 'missing'

  el.innerHTML = `
    <div class="board-header">
      ${ratingBadge(rating)}
      <span class="board-verdict">${verdictLine(rating)}</span>
    </div>
    <p class="board-rationale">${esc(judgment.rationale)}</p>
    ${sources.length ? `
      <p class="board-tiles-label">Evidence pieces (${sources.length})</p>
      <div class="board-tiles">
        ${sources.map(tileSvg).join('')}
      </div>
      <div class="board-legend">
        ${legend()}
      </div>
    ` : ''}
  `;

  // Wire click handlers after innerHTML is set
  el.querySelectorAll('.puzzle-tile').forEach((tile) => {
    tile.addEventListener('click', () => {
      const targetId = tile.dataset.sourceId;
      const sourceEl = document.getElementById(`source-${targetId}`);
      if (!sourceEl) return;
      sourceEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
      sourceEl.classList.add('highlighted');
      setTimeout(() => sourceEl.classList.remove('highlighted'), 2000);
    });
  });
}

function tileSvg(source) {
  const cls = tileClass(source);
  const domain = domainFrom(source.url);
  const pct = Math.round(source.relevance_score * 100);
  const indepLabel = source.is_independent ? 'Independent' : 'Not independent';
  const tip = `${domain} · ${capitalize(source.tier)} · ${pct}% relevance · ${indepLabel}`;
  return `<button
    class="puzzle-tile ${cls}"
    title="${esc(tip)}"
    data-source-id="${source.id}"
    aria-label="${esc(tip)}"
  ></button>`;
}

function tileClass(source) {
  if (!source.is_independent) return 'tile-debunked';
  if (source.relevance_score < 0.6) return 'tile-missing';
  if (source.tier === 'primary') return 'tile-verified';
  if (source.tier === 'secondary') return 'tile-speculative';
  return 'tile-missing';
}

function ratingBadge(rating) {
  return `<span class="rating-badge ${rating}">
    <span class="rating-dot"></span>${rating}
  </span>`;
}

function verdictLine(rating) {
  return {
    verified:    'Claim is verified',
    speculative: 'Claim is speculative',
    debunked:    'Claim is debunked',
    missing:     'Insufficient evidence',
  }[rating] ?? rating;
}

function legend() {
  const items = [
    { cls: 'tile-verified',    label: 'Independent primary' },
    { cls: 'tile-speculative', label: 'Independent secondary' },
    { cls: 'tile-debunked',    label: 'Compromised source' },
    { cls: 'tile-missing',     label: 'Weak / excluded' },
  ];
  return items.map(({ cls, label }) => `
    <span class="legend-item">
      <span class="legend-swatch ${cls}"></span>${label}
    </span>
  `).join('');
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
