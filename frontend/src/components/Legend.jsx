import { VERIFICATION } from "../utils/format.js";
import StatusBadge from "./StatusBadge.jsx";

const FALLBACK = {
  confirmed: "Availability was verified and the record is recent.",
  reported: "Availability was stated but not verified; record is recent.",
  stale: "The record is older than the recent window; ranked lower until re-checked.",
  unverified: "The source has not verified this record.",
  unavailable: "The record says it cannot supply; not recommended.",
  unknown: "The update time is missing or unreadable.",
};

export default function Legend({ meta }) {
  const hours = meta ? meta.freshness_recent_hours : 6;
  return (
    <section className="panel" aria-labelledby="legend-title">
      <h2 id="legend-title">What the data labels mean</h2>
      <p className="muted">
        A record is "recent" if it was updated within {hours} hours. Every label has a symbol and a word, so you never
        need to rely on colour.
      </p>
      <ul className="legend">
        {Object.keys(VERIFICATION).map((key) => (
          <li key={key}>
            <StatusBadge kind="verification" value={key} />
            <span>{FALLBACK[key]}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
