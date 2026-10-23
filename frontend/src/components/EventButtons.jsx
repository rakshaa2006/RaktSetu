// Buttons for the events that make sense for one option in its current state.
export default function EventButtons({ candidate, events, onAction, busy }) {
  if (!events.length) return <p className="small muted">No actions are available for this option.</p>;
  return (
    <div className="btn-row">
      {events.map((ev) => (
        <button
          key={ev.type}
          type="button"
          className={`btn ${ev.type === "SELECT_FOR_REVIEW" || ev.type === "CONFIRM_AVAILABILITY" ? "btn-primary" : "btn-secondary"}`}
          disabled={busy}
          onClick={() => onAction(ev.type, candidate)}
        >
          {ev.label}
        </button>
      ))}
    </div>
  );
}
