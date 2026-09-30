const BASE = (import.meta.env && import.meta.env.VITE_API_BASE) || '/api';

export class ApiError extends Error {
  constructor(message, { code = 'ERROR', retryable = false, status = 0, details = null } = {}) {
    super(message);
    this.code = code;
    this.retryable = retryable;
    this.status = status;
    this.details = details;
  }
}

/** POST JSON to the backend. Returns { data, roundTripMs } (roundTripMs is measured in the browser). */
export async function post(path, body, { signal } = {}) {
  const t0 = performance.now();
  let res;
  try {
    res = await fetch(`${BASE}${path}`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
      signal,
    });
  } catch (e) {
    if (e.name === 'AbortError') throw e;
    throw new ApiError('Could not reach the Syntax AI backend. Check that it is running and try again.', {
      code: 'NETWORK', retryable: true,
    });
  }
  let payload = null;
  try {
    payload = await res.json();
  } catch {
    /* non-JSON error page */
  }
  if (!res.ok) {
    const err = payload && payload.error;
    throw new ApiError(err ? err.message : `The server returned HTTP ${res.status}.`, {
      code: err ? err.code : 'HTTP_' + res.status,
      retryable: err ? !!err.retryable : res.status >= 500,
      status: res.status,
      details: err ? err.details : null,
    });
  }
  return { data: payload, roundTripMs: Math.round(performance.now() - t0) };
}

export const api = {
  analyze: (image_base64, force = false) => post('/analyze', { image_base64, force }),
  refine: (architecture, options, text) => post('/refine', { architecture, options, text }),
  patch: (architecture, ops) => post('/patch', { architecture, ops }),
  revalidate: (architecture) => post('/revalidate', { architecture }),
  generate: (architecture, options, overrides) => post('/generate', { architecture, options, overrides }),
  verify: (architecture, outputs, options, overrides) => post('/verify', { architecture, outputs, options, overrides }),
  health: async () => {
    const res = await fetch(`${BASE}/health`);
    return res.json();
  },
};
