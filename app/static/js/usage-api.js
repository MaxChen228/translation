export async function fetchUsage(query = {}) {
  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return;
    params.append(key, value);
  });
  const url = `/usage/llm?${params.toString()}`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

export function toUnixTimestamp(value) {
  if (!value) return null;
  const ts = Date.parse(value);
  if (Number.isNaN(ts)) return null;
  return Math.floor(ts / 1000);
}

export function formatUsageTimestamp(unixSeconds) {
  if (!unixSeconds) return '-';
  const date = new Date(unixSeconds * 1000);
  if (Number.isNaN(date.getTime())) return '-';
  return date.toLocaleString();
}

export function createUsageState(initial = {}) {
  return {
    offset: initial.offset ?? 0,
    limit: initial.limit ?? 100,
    lastQuery: initial.lastQuery || {},
    lastData: null,
  };
}
