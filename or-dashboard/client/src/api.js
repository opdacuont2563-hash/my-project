const BASE_URL = import.meta.env.VITE_API || "http://localhost:4000";

function toQuery(params = {}) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null) {
      return;
    }
    const str = String(value).trim();
    if (str.length === 0) {
      return;
    }
    search.set(key, str);
  });
  const queryString = search.toString();
  return queryString ? `?${queryString}` : "";
}

async function fetchJSON(path) {
  const response = await fetch(path);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json();
}

export const api = {
  kpi: (params) => fetchJSON(`${BASE_URL}/api/kpi${toQuery(params)}`),
  trend: (params) => fetchJSON(`${BASE_URL}/api/trend${toQuery(params)}`),
  rooms: (params) => fetchJSON(`${BASE_URL}/api/rooms/utilization${toQuery(params)}`),
  firstcut: (params) => fetchJSON(`${BASE_URL}/api/surgeons/firstcut${toQuery(params)}`),
  topops: (params) => fetchJSON(`${BASE_URL}/api/top-operations${toQuery(params)}`),
  postpone: (params) => fetchJSON(`${BASE_URL}/api/postponements${toQuery(params)}`),
  heatmap: (params) => fetchJSON(`${BASE_URL}/api/heatmap${toQuery(params)}`)
};
