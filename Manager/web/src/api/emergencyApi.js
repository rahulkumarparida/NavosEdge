const AUTH_STORAGE_KEY = 'navos_manager_auth';

export function getManagerAuth() {
  try {
    const raw = sessionStorage.getItem(AUTH_STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch (_) {}
  return { operator: 'manager', apiKey: '' };
}

export function setManagerAuth(auth) {
  try {
    sessionStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(auth));
  } catch (_) {}
}

export function buildAuthHeaders(extra = {}) {
  const { operator, apiKey } = getManagerAuth();
  const headers = {
    'Content-Type': 'application/json',
    'X-Navos-Operator': operator || 'manager',
    ...extra,
  };
  if (apiKey && apiKey.trim()) {
    headers['X-Navos-Manager-Key'] = apiKey.trim();
  }
  return headers;
}

export async function apiFetch(path, options = {}) {
  const headers = buildAuthHeaders(options.headers || {});
  const res = await fetch(path, { ...options, headers });
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch (_) {
    data = text;
  }
  if (!res.ok) {
    const msg = (data && data.detail) || (data && data.error) || `HTTP ${res.status}`;
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }
  return data;
}

