import { EVENT_TYPE_LABEL, formatDateTime, humanize } from "../utils/format.js";

const ALLOC_LABELS = {
  UNITS_ALLOCATED: "Units allocated",
  ALLOCATION_RELEASED: "Allocation released",
  ALLOCATIONS_CANCELLED: "Allocations cancelled",
};

export default function Timeline({ events, newestFirst = false }) {
  const list = newestFirst ? [...events].reverse() : events;
  return (
    <ol className="timeline">
      {list.map((e) => (
        <li key={e.event_id} className="tl-item">
          <p className="tl-time">{formatDateTime(e.timestamp)}</p>
          <div className="tl-body">
            <p>
              <strong>{ALLOC_LABELS[e.event_type] || EVENT_TYPE_LABEL[e.event_type] || humanize(e.event_type)}</strong>{" "}
              {e.is_simulation ? <span className="badge badge-muted">Simulated event</span> : <span className="badge badge-plain">Recorded</span>}
            </p>
            <p>{e.reason}</p>
            {(e.previous_state || e.new_state) && (
              <p className="small">
                State changed from <strong>{humanize(e.previous_state) || "none"}</strong> to <strong>{humanize(e.new_state) || "none"}</strong>
              </p>
            )}
            {e.candidate_id && <p className="small">Option: {e.candidate_id}</p>}
            <p className="small muted">Event ID {e.event_id}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}
