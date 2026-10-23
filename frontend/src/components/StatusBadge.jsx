import { CANDIDATE_STATUS, REQUEST_STATUS, URGENCY, VERIFICATION, humanize } from "../utils/format.js";

const TABLES = {
  verification: VERIFICATION,
  candidate: CANDIDATE_STATUS,
  request: REQUEST_STATUS,
  urgency: URGENCY,
};

// Always renders a symbol AND a text label, so meaning never depends on colour.
export default function StatusBadge({ kind, value }) {
  const meta = (TABLES[kind] && TABLES[kind][value]) || { label: humanize(value), symbol: "•", tone: "muted" };
  return (
    <span className={`badge badge-${meta.tone}`}>
      <span aria-hidden="true">{meta.symbol}</span> {meta.label}
    </span>
  );
}
