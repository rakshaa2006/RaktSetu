// Display helpers and plain-language labels. Status is always shown as text + symbol, never colour alone.

export function formatDateTime(value) {
  if (!value) return "Not recorded";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "Time could not be read";
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function formatAge(hours) {
  if (hours === null || hours === undefined) return "age unknown";
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))} min ago`;
  if (hours < 48) return `${hours.toFixed(1)} h ago`;
  return `${Math.round(hours / 24)} days ago`;
}

export function humanize(value) {
  if (!value) return "";
  const text = String(value).replace(/_/g, " ").toLowerCase();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export const VERIFICATION = {
  confirmed: { label: "Confirmed", symbol: "✔", tone: "good" },
  reported: { label: "Reported", symbol: "●", tone: "info" },
  stale: { label: "Stale", symbol: "⏱", tone: "warn" },
  unverified: { label: "Unverified", symbol: "?", tone: "muted" },
  unavailable: { label: "Unavailable", symbol: "✖", tone: "bad" },
  unknown: { label: "Unknown", symbol: "–", tone: "muted" },
};

export const CANDIDATE_STATUS = {
  reported_available: { label: "Reported available", symbol: "●", tone: "info" },
  awaiting_confirmation: { label: "Awaiting confirmation", symbol: "…", tone: "warn" },
  confirmed_available: { label: "Confirmed available", symbol: "✔", tone: "good" },
  declined: { label: "Declined", symbol: "✖", tone: "bad" },
  unavailable: { label: "Unavailable", symbol: "✖", tone: "bad" },
  no_response: { label: "No response", symbol: "…", tone: "muted" },
  stale: { label: "Stale", symbol: "⏱", tone: "warn" },
  unverified: { label: "Unverified", symbol: "?", tone: "muted" },
};

export const REQUEST_STATUS = {
  open: { label: "Open", symbol: "●", tone: "info" },
  under_review: { label: "Under review", symbol: "…", tone: "warn" },
  awaiting_confirmation: { label: "Awaiting confirmation", symbol: "…", tone: "warn" },
  partially_fulfilled: { label: "Partially fulfilled (simulated)", symbol: "◐", tone: "good" },
  fulfilled: { label: "Fulfilled (simulated)", symbol: "✔", tone: "good" },
  cancelled: { label: "Cancelled", symbol: "✖", tone: "muted" },
};

export const URGENCY = {
  Critical: { label: "Critical", symbol: "!", tone: "bad" },
  Urgent: { label: "Urgent", symbol: "▲", tone: "warn" },
  Routine: { label: "Routine", symbol: "•", tone: "muted" },
};

export const MATCH_TEXT = {
  exact: "Exact blood group match",
  compatible: "Compatible group - a qualified person must confirm",
  none: "Not matched",
};

export const EVENT_TYPE_LABEL = {
  REQUEST_CREATED: "Request created",
  RANKING_GENERATED: "Ranking generated",
  RANKING_RECALCULATED: "Ranking recalculated",
  RECOMMENDATION_SELECTED_FOR_REVIEW: "Selected for review",
  CANDIDATE_DECLINED: "Donor declined",
  CANDIDATE_NO_RESPONSE: "Donor did not respond",
  STOCK_REPORTED_UNAVAILABLE: "Stock reported unavailable",
  DATA_MARKED_STALE: "Data marked stale",
  AVAILABILITY_CONFIRMED_SIMULATED: "Availability confirmed (simulated)",
  CANDIDATE_REINSTATED: "Option reinstated",
  REQUEST_STATUS_UPDATED: "Request status updated",
  COORDINATOR_ACTION_RECORDED: "Coordinator note",
};

// Which simulation / coordinator events make sense for an option in a given state.
export function allowedEvents(candidate, meta) {
  if (!candidate || !meta || candidate.exclusion_category === "not_matched" || candidate.exclusion_category === "not_consented") return [];
  const status = candidate.review_status;
  const label = (type) => ({ type, label: meta.event_types[type] || type });
  if (status === "declined" || status === "unavailable") return [label("REINSTATE_CANDIDATE")];
  const next = new Set(meta.candidate_transitions[status] || []);
  const out = [];
  if (candidate.candidate_type === "blood_bank" && next.has("unavailable")) out.push(label("STOCK_UNAVAILABLE"));
  if (candidate.candidate_type === "donor" && next.has("declined")) out.push(label("DONOR_DECLINED"));
  if (candidate.candidate_type === "donor" && next.has("no_response")) out.push(label("DONOR_NO_RESPONSE"));
  if (next.has("stale")) out.push(label("DATA_STALE"));
  if (next.has("awaiting_confirmation")) out.push(label("SELECT_FOR_REVIEW"));
  if (next.has("confirmed_available")) out.push(label("CONFIRM_AVAILABILITY"));
  return out;
}

export const SIMULATION_TYPES = ["STOCK_UNAVAILABLE", "DONOR_DECLINED", "DONOR_NO_RESPONSE", "DATA_STALE"];
