export async function authedFetch(url, {
  method = 'GET',
  tokenManager,
  headers: initialHeaders = {},
  body,
  json,
} = {}) {
  const headers = { ...initialHeaders };
  if (tokenManager) {
    tokenManager.apply(headers);
  }
  let payload = body;
  if (json !== undefined) {
    headers['Content-Type'] = 'application/json';
    payload = JSON.stringify(json);
  }
  const resp = await fetch(url, { method, headers, body: payload });
  if (!resp.ok) {
    const detail = await safeReadError(resp);
    throw new Error(detail || `HTTP ${resp.status}`);
  }
  return resp;
}

async function safeReadError(response) {
  try {
    const data = await response.json();
    if (typeof data === 'object' && data !== null) {
      return data.detail || data.error || JSON.stringify(data);
    }
    return String(data);
  } catch (_) {
    try {
      return await response.text();
    } catch (__) {
      return '';
    }
  }
}

export async function authedFetchJson(url, options = {}) {
  const resp = await authedFetch(url, options);
  const text = await resp.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch (err) {
    console.warn('Failed to parse JSON response', err);
    return null;
  }
}
