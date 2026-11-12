const explicitBase = import.meta.env.VITE_API_BASE?.replace(/\/$/, '');
const candidateBases = explicitBase ? [explicitBase] : ['/api', '/_/backend/api'];
let preferredBase = candidateBases[0];
// Set once a base has answered with JSON. From then on every request goes there
// and is never re-sent to another base: an upload must not be read twice just
// because a proxy answered with an HTML error page.
let confirmedBase = explicitBase || null;

function normalizePath(path) {
  return path.startsWith('/') ? path : `/${path}`;
}

function isJsonResponse(res) {
  const contentType = res.headers.get('content-type') || '';
  return contentType.includes('application/json');
}

export async function apiFetch(path, init) {
  const endpoint = normalizePath(path);
  if (confirmedBase) return fetch(`${confirmedBase}${endpoint}`, init);

  const basesToTry = [preferredBase, ...candidateBases.filter((base) => base !== preferredBase)];
  let lastError = null;

  for (const base of basesToTry) {
    try {
      const res = await fetch(`${base}${endpoint}`, init);

      // All current API endpoints return JSON. HTML here usually means wrong route.
      if (isJsonResponse(res)) {
        preferredBase = base;
        confirmedBase = base;
        return res;
      }

      // Keep trying candidates when response looks like SPA fallback HTML.
      lastError = new Error(`Unexpected non-JSON API response from ${base}${endpoint}`);
    } catch (err) {
      lastError = err;
    }
  }

  throw lastError || new Error('Unable to reach API');
}

/** URL of an API resource for use in <img src> or links, on the same base apiFetch uses. */
export function apiUrl(path) {
  return `${confirmedBase || preferredBase}${normalizePath(path)}`;
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

function detailText(detail) {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => (typeof d === 'string' ? d : d?.msg)).filter(Boolean).join('; ');
  }
  return null;
}

function statusText(status) {
  if (status === 413) return 'The file is too large for the server to accept (the limit is 4.5 MB).';
  if (status === 504) {
    return 'The server took too long to answer. The page may still have been read; check Recent uploads before trying again.';
  }
  if (status === 404) return 'Not found on the server.';
  if (status >= 500) return `The server ran into a problem (HTTP ${status}).`;
  return `The request failed (HTTP ${status}).`;
}

/**
 * JSON request. Resolves with the parsed body, or throws ApiError carrying the
 * server's `detail` message.
 *   api('/entries?month=2026-11')
 *   api('/entries/2026-11-03', { method: 'PUT', json: { gcv: 3400 } })
 *   api('/reports', { method: 'POST', body: formData })   // multipart, no Content-Type
 */
export async function api(path, { method = 'GET', json, body, signal } = {}) {
  const init = { method, signal };
  if (json !== undefined) {
    init.headers = { 'Content-Type': 'application/json' };
    init.body = JSON.stringify(json);
  } else if (body !== undefined) {
    init.body = body;
  }

  let res;
  try {
    res = await apiFetch(path, init);
  } catch (err) {
    if (err?.name === 'AbortError') throw err;
    throw new ApiError('Could not reach the server. Check the connection and try again.', 0);
  }

  const isJson = isJsonResponse(res);
  const data = isJson ? await res.json().catch(() => null) : null;
  if (!res.ok) throw new ApiError(detailText(data?.detail) || statusText(res.status), res.status);
  if (!isJson) throw new ApiError('The server sent an unexpected response.', res.status);
  return data;
}
