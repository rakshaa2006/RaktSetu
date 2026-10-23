// The ONLY place that knows backend URLs. Everything else calls `api.*`.
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/+$/, "");

export class ApiError extends Error {
  constructor(message, { status = 0, fieldErrors = {} } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.fieldErrors = fieldErrors;
  }
}

function toApiError(status, data) {
  const detail = data && data.detail;
  if (Array.isArray(detail)) {
    const fieldErrors = {};
    for (const item of detail) {
      const field = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : "form";
      if (!fieldErrors[field]) fieldErrors[field] = String(item.msg || "Invalid value").replace(/^Value error, /, "");
    }
    return new ApiError("Some details need fixing. Please check the highlighted fields.", { status, fieldErrors });
  }
  if (typeof detail === "string") return new ApiError(detail, { status });
  return new ApiError(`The server returned an unexpected error (code ${status}).`, { status });
}

async function request(path, { method = "GET", body, params } = {}) {
  const url = new URL(API_BASE_URL + path);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, value);
    }
  }
  let response;
  try {
    response = await fetch(url, {
      method,
      headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(`Cannot reach the RaktSetu server at ${API_BASE_URL}. Please check that the backend is running.`);
  }
  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  if (!response.ok) throw toApiError(response.status, data);
  return data;
}

const enc = encodeURIComponent;

export const api = {
  health: () => request("/api/health"),
  meta: () => request("/api/meta"),
  locations: () => request("/api/locations"),
  dashboard: () => request("/api/dashboard/summary"),
  bloodBanks: (params) => request("/api/blood-banks", { params }),
  donors: (params) => request("/api/donors", { params }),
  listRequests: () => request("/api/requests"),
  createRequest: (body) => request("/api/requests", { method: "POST", body }),
  getRequest: (id) => request(`/api/requests/${enc(id)}`),
  getRecommendations: (id, version) =>
    request(`/api/requests/${enc(id)}/recommendations`, { params: { version } }),
  recalculate: (id) => request(`/api/requests/${enc(id)}/recommendations/recalculate`, { method: "POST" }),
  getTimeline: (id) => request(`/api/requests/${enc(id)}/timeline`),
  postEvent: (id, body) => request(`/api/requests/${enc(id)}/events`, { method: "POST", body }),
  updateStatus: (id, body) => request(`/api/requests/${enc(id)}/status`, { method: "PATCH", body }),
};
