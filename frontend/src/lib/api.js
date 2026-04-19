const explicitBase = import.meta.env.VITE_API_BASE?.replace(/\/$/, '');
const candidateBases = explicitBase ? [explicitBase] : ['/api', '/_/backend/api'];
let preferredBase = candidateBases[0];

function normalizePath(path) {
  return path.startsWith('/') ? path : `/${path}`;
}

function isJsonResponse(res) {
  const contentType = res.headers.get('content-type') || '';
  return contentType.includes('application/json');
}

export async function apiFetch(path, init) {
  const endpoint = normalizePath(path);
  const basesToTry = [preferredBase, ...candidateBases.filter((base) => base !== preferredBase)];
  let lastError = null;

  for (const base of basesToTry) {
    try {
      const res = await fetch(`${base}${endpoint}`, init);

      // All current API endpoints return JSON. HTML here usually means wrong route.
      if (isJsonResponse(res)) {
        preferredBase = base;
        return res;
      }

      // If user explicitly set a base path, don't second-guess it.
      if (explicitBase) {
        preferredBase = base;
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
