/* WoL-Monkey — shared JS helpers */

/* Auto-read CSRF token from the page meta tag or first hidden _csrf input */
function getCsrf() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  if (meta) return meta.content;
  const inp = document.querySelector('input[name="_csrf"]');
  return inp ? inp.value : '';
}

/* Generic fetch with CSRF header */
async function apiFetch(url, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...options.headers };
  const csrf = getCsrf();
  if (csrf) headers['X-CSRF-Token'] = csrf;
  const resp = await fetch(url, { ...options, headers });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail || resp.statusText);
  }
  return resp.json();
}
