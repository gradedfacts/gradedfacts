/**
 * Application root.
 *
 * Owns all state and coordinates the full analyze flow:
 *   1. POST /claims          — create the claim record
 *   2. POST /claims/:id/analyze — fire the analysis pipeline (30–60 s, synchronous)
 *   3. Poll GET /claims/:id every 2 s until active_judgment is present
 *   4. Fetch sources + history, then render all result components
 *
 * The analyze endpoint is synchronous on the server; it blocks until Claude
 * finishes.  Polling runs in parallel so the UI always reflects actual DB
 * state — if the connection drops, the poll catches the result on reconnect.
 */

import * as ClaimInput    from './claim_input.js';
import * as PuzzleBoard   from './puzzle_board.js';
import * as SourcePanel   from './source_panel.js';
import * as RevisionTrail from './revision_trail.js';
import * as SymmetryReport from './symmetry_report.js';

// ── Config ────────────────────────────────────────────────────────────────────

const BASE = 'http://localhost:8000';
const POLL_MS = 2000;

const LOADING_MESSAGES = [
  'Searching sources…',
  'Evaluating independence…',
  'Deriving rating…',
];

// ── State ─────────────────────────────────────────────────────────────────────

const state = {
  phase: 'idle',        // idle | submitting | analyzing | done | error
  loadingMsgIdx: 0,
  claim: null,          // ClaimDetailOut
  sources: [],          // SourceOut[]
  history: null,        // ClaimHistoryOut
  error: null,          // Error with .status
};

// DOM handles — populated in init()
const el = {};
let pollTimer = null;
let loadingCycleTimer = null;
let activeClaimId = null;

// ── API layer ─────────────────────────────────────────────────────────────────

async function apiFetch(path, opts = {}) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const err = new Error(body.detail || `HTTP ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

const api = {
  createClaim:  (text) => apiFetch('/claims', { method: 'POST', body: JSON.stringify({ text }) }),
  analyzeClaim: (id)   => apiFetch(`/claims/${id}/analyze`, { method: 'POST' }),
  getClaim:     (id)   => apiFetch(`/claims/${id}`),
  getSources:   (id)   => apiFetch(`/claims/${id}/sources`),
  getHistory:   (id)   => apiFetch(`/claims/${id}/history`),
};

// ── Polling ───────────────────────────────────────────────────────────────────

function startPolling(id) {
  stopPolling();
  pollTimer = setInterval(() => pollClaim(id), POLL_MS);
}

function stopPolling() {
  clearInterval(pollTimer);
  pollTimer = null;
}

async function pollClaim(id) {
  try {
    const claim = await api.getClaim(id);
    if (claim.active_judgment) {
      stopPolling();
      stopLoadingCycle();
      const [sources, history] = await Promise.all([
        api.getSources(id),
        api.getHistory(id),
      ]);
      setState({ phase: 'done', claim, sources, history });
    }
  } catch {
    // Ignore transient network errors during polling; keep trying.
  }
}

// ── Loading message cycle ─────────────────────────────────────────────────────

function startLoadingCycle() {
  stopLoadingCycle();
  state.loadingMsgIdx = 0;
  syncLoadingMsg();
  loadingCycleTimer = setInterval(() => {
    state.loadingMsgIdx = (state.loadingMsgIdx + 1) % LOADING_MESSAGES.length;
    syncLoadingMsg();
  }, 6000);
}

function stopLoadingCycle() {
  clearInterval(loadingCycleTimer);
  loadingCycleTimer = null;
}

function syncLoadingMsg() {
  if (el.loadingMsg) el.loadingMsg.textContent = LOADING_MESSAGES[state.loadingMsgIdx];
}

// ── Submit handler ────────────────────────────────────────────────────────────

async function handleSubmit(text) {
  stopPolling();
  stopLoadingCycle();
  activeClaimId = null;

  setState({ phase: 'submitting', error: null, claim: null, sources: [], history: null });

  let claim;
  try {
    claim = await api.createClaim(text);
  } catch (err) {
    setState({ phase: 'error', error: err });
    return;
  }

  activeClaimId = claim.id;
  setState({ phase: 'analyzing' });
  startLoadingCycle();
  startPolling(claim.id);

  // Fire the analysis; the server will block for ~30–60 s.
  // Polling catches the success case; this .catch() handles server errors.
  const claimIdSnapshot = claim.id;
  api.analyzeClaim(claim.id).catch((err) => {
    if (activeClaimId === claimIdSnapshot && state.phase === 'analyzing') {
      stopPolling();
      stopLoadingCycle();
      setState({ phase: 'error', error: err });
    }
  });
}

// ── Render ────────────────────────────────────────────────────────────────────

function setState(updates) {
  Object.assign(state, updates);
  render();
}

function render() {
  // Claim input: only update enabled/error state (textarea keeps its value + focus)
  ClaimInput.update(el.claimInput, {
    disabled: state.phase === 'submitting' || state.phase === 'analyzing',
    error: state.phase === 'error' ? state.error : null,
  });

  // Loading strip
  el.loadingSection.hidden = state.phase !== 'analyzing';

  // Result pane
  el.resultSection.hidden = state.phase !== 'done';
  if (state.phase === 'done') {
    PuzzleBoard.render(el.puzzleBoard, {
      judgment: state.claim?.active_judgment ?? null,
      sources: state.sources,
    });
    SourcePanel.render(el.sourcePanel, { sources: state.sources });
    RevisionTrail.render(el.revisionTrail, { history: state.history });
    SymmetryReport.render(el.symmetryReport, {
      report: state.claim?.active_judgment?.symmetry_report ?? null,
    });
  }
}

// ── Bootstrap ─────────────────────────────────────────────────────────────────

function init() {
  document.getElementById('app').innerHTML = `
    <header class="site-header">
      <span class="site-wordmark">&#x1f9e9; TransparencyPuzzle</span>
      <span class="site-tagline">Founded in Switzerland &middot; No political funding</span>
    </header>

    <main class="site-main">

      <div class="card" id="claim-input"></div>

      <div class="loading-section" id="loading-section" hidden>
        <div class="spinner"></div>
        <span id="loading-msg">${LOADING_MESSAGES[0]}</span>
      </div>

      <div id="result-section" hidden>
        <div class="card" id="puzzle-board" style="margin-bottom:1.25rem"></div>
        <div class="result-columns">
          <div class="card" id="source-panel"></div>
          <div class="card" id="symmetry-report"></div>
        </div>
        <div class="card" id="revision-trail" style="margin-top:1.25rem"></div>
      </div>

    </main>
  `;

  el.claimInput     = document.getElementById('claim-input');
  el.loadingSection = document.getElementById('loading-section');
  el.loadingMsg     = document.getElementById('loading-msg');
  el.resultSection  = document.getElementById('result-section');
  el.puzzleBoard    = document.getElementById('puzzle-board');
  el.sourcePanel    = document.getElementById('source-panel');
  el.symmetryReport = document.getElementById('symmetry-report');
  el.revisionTrail  = document.getElementById('revision-trail');

  ClaimInput.mount(el.claimInput, { onSubmit: handleSubmit });
  render();
}

init();
