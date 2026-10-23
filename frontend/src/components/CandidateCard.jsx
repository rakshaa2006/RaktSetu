import { MATCH_TEXT, allowedEvents, formatAge, formatDateTime } from "../utils/format.js";
import EventButtons from "./EventButtons.jsx";
import StatusBadge from "./StatusBadge.jsx";

export default function CandidateCard({ item, meta, onAction, onAllocate, busy, readOnly }) {
  const excluded = item.rank === null || item.rank === undefined;
  const events = readOnly ? [] : allowedEvents(item, meta);
  const kind = item.candidate_type === "blood_bank" ? "Blood bank" : "Registered donor";
  const distance =
    item.distance_km !== null && item.distance_km !== undefined
      ? `About ${item.distance_km} km in a straight line (not road distance)`
      : "Distance unknown (coordinates missing)";
  return (
    <article className={`candidate${excluded ? " candidate-excluded" : ""}`} aria-labelledby={`cand-${item.candidate_id}`}>
      <div className="rank" aria-label={excluded ? "Not recommended" : `Rank ${item.rank}`}>
        {excluded ? "–" : item.rank}
      </div>
      <div className="candidate-main">
        <h3 id={`cand-${item.candidate_id}`}>
          {item.display_name} <span className="id">{item.candidate_id}</span>
        </h3>
        <p className="muted">
          {kind}, {item.location}
        </p>
        <div className="badges">
          <StatusBadge kind="verification" value={item.verification_label} />
          <StatusBadge kind="candidate" value={item.review_status} />
          <span className="badge badge-plain">{MATCH_TEXT[item.match_level] || item.match_level}</span>
        </div>
        <dl className="facts">
          <div><dt>Blood group</dt><dd>{item.blood_group}</dd></div>
          {item.component && <div><dt>Component</dt><dd>{item.component}</dd></div>}
          <div>
            <dt>Allocation capacity</dt>
            <dd>{item.candidate_type === "blood_bank" ? `${item.units_available ?? 0} unit(s) reported stock` : "1 unit maximum"}</dd>
          </div>
          <div>
            <dt>Last updated</dt>
            <dd>{item.last_updated ? `${formatDateTime(item.last_updated)} (${formatAge(item.age_hours)})` : "Not recorded or unreadable"}</dd>
          </div>
          <div><dt>Distance</dt><dd>{distance}</dd></div>
          <div><dt>Source</dt><dd>{item.data_source || "Not stated"}</dd></div>
        </dl>

        {excluded ? (
          <div className="reasons reasons-bad">
            <strong>Why this option is not recommended</strong>
            <ul>{item.exclusion_reasons.map((r) => <li key={r}>{r}</li>)}</ul>
          </div>
        ) : (
          <>
            <p className="explanation"><strong>Why this rank: </strong>{item.explanation}</p>
            {item.reduced_priority_reasons.length > 0 && (
              <div className="reasons reasons-warn">
                <strong>Check before relying on this option</strong>
                <ul>{item.reduced_priority_reasons.map((r) => <li key={r}>{r}</li>)}</ul>
              </div>
            )}
            <details>
              <summary>Factors considered</summary>
              <ul>{item.factors.map((f) => <li key={f}>{f}</li>)}</ul>
            </details>
          </>
        )}

        {!readOnly && (events.length > 0 || (onAllocate && item.review_status === "confirmed_available")) && (
          <details className="actions" open={item.review_status === "confirmed_available"}>
            <summary>Actions for this option</summary>
            {item.review_status === "confirmed_available" && onAllocate && (
              <div className="btn-row" style={{ marginBottom: "0.5rem" }}>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={busy}
                  onClick={() => onAllocate(item)}
                >
                  Allocate units ({item.candidate_type === "blood_bank" ? "reserve stock" : "1 unit"})
                </button>
              </div>
            )}
            <EventButtons candidate={item} events={events} onAction={onAction} busy={busy} />
          </details>
        )}
      </div>
    </article>
  );
}
