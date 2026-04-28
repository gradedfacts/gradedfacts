/**
 * ClaimInput component.
 *
 * mount()  — called once; writes the form HTML and wires event listeners.
 * update() — called on state changes; updates button / error without
 *            replacing the textarea (preserves focus and content).
 */

const MAX = 2000;

export function mount(el, { onSubmit }) {
  el.innerHTML = `
    <p class="claim-form-heading">Analyze a claim</p>
    <div class="claim-form">
      <textarea
        class="claim-textarea"
        maxlength="${MAX}"
        placeholder="Enter a political claim to verify — e.g. &quot;The unemployment rate fell to a 50-year low in 2019&quot;"
        rows="4"
        required
      ></textarea>
      <div class="form-footer">
        <span class="char-count">${MAX} characters remaining</span>
        <button type="button" class="btn btn-primary submit-btn">Analyze Claim</button>
      </div>
      <div class="error-container"></div>
    </div>
  `;

  const textarea = el.querySelector('.claim-textarea');
  const charCount = el.querySelector('.char-count');
  const btn = el.querySelector('.submit-btn');

  textarea.addEventListener('input', () => {
    const remaining = MAX - textarea.value.length;
    charCount.textContent = `${remaining} characters remaining`;
    charCount.className = 'char-count' +
      (remaining < 100 ? ' limit' : remaining < 400 ? ' near' : '');
  });

  btn.addEventListener('click', () => {
    const text = textarea.value.trim();
    if (text.length >= 10 && !btn.disabled) onSubmit(text);
  });

  // Allow Ctrl+Enter / Cmd+Enter to submit
  textarea.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      const text = textarea.value.trim();
      if (text.length >= 10 && !btn.disabled) onSubmit(text);
    }
  });
}

export function update(el, { disabled, error }) {
  const textarea = el.querySelector('.claim-textarea');
  const btn = el.querySelector('.submit-btn');
  const errorContainer = el.querySelector('.error-container');
  if (!textarea) return;

  textarea.disabled = disabled;
  btn.disabled = disabled;
  btn.textContent = disabled ? 'Analyzing…' : 'Analyze Claim';

  errorContainer.innerHTML = error
    ? `<div class="error-banner">
         <span class="error-code">${error.status || 'ERR'}</span>
         ${esc(errorMessage(error))}
       </div>`
    : '';
}

function errorMessage(err) {
  if (!err) return '';
  if (err.status === 503) return 'The analysis service requires an API key. Please configure ANTHROPIC_API_KEY on the server.';
  if (err.status === 500) return 'The analysis pipeline encountered an error. Please try again.';
  if (err.status === 409) return 'This claim already has an active judgment.';
  if (!err.status) return 'Could not connect to the analysis server. Is it running at localhost:8000?';
  return err.message || `Unexpected error (HTTP ${err.status}).`;
}

function esc(str) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
