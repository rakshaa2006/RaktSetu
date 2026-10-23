import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import Alert from "../components/Alert.jsx";
import EmptyState from "../components/EmptyState.jsx";
import Spinner from "../components/Spinner.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import Timeline from "../components/Timeline.jsx";
import { useAsync } from "../hooks/useAsync.js";
import { usePageTitle } from "../hooks/usePageTitle.js";
import { api } from "../services/api.js";
import { formatDateTime } from "../utils/format.js";

export default function TimelinePage() {
  const { id } = useParams();
  usePageTitle(`Audit history ${id}`);
  const request = useAsync(() => api.getRequest(id), [id]);
  const events = useAsync(() => api.getTimeline(id), [id]);
  const recs = useAsync(() => api.getRecommendations(id), [id]);
  const [newest, setNewest] = useState(false);

  const err = request.error || events.error;
  if (err) {
    return (
      <Alert tone="error" title={err.status === 404 ? "Request not found" : "History could not be loaded"}>
        {err.message} <Link to="/">Back to the dashboard</Link>
      </Alert>
    );
  }
  if (!request.data || !events.data) return <Spinner label="Loading history..." />;

  return (
    <>
      <p><Link to={`/requests/${id}`}>← Back to request {id}</Link></p>
      <div className="page-head">
        <h1>Audit history for {id}</h1>
        <StatusBadge kind="request" value={request.data.status} />
      </div>
      <p className="muted">
        Every change is added to the end of this list; earlier entries are never removed. This is an application log
        for the demonstration, not a tamper-proof or legally certified record.
      </p>
      <section className="panel" aria-labelledby="events-title">
        <h2 id="events-title">Events ({events.data.length})</h2>
        <label className="check">
          <input type="checkbox" checked={newest} onChange={(e) => setNewest(e.target.checked)} />
          <span>Show newest first</span>
        </label>
        {events.data.length === 0 ? <EmptyState title="No events yet" /> : <Timeline events={events.data} newestFirst={newest} />}
      </section>
      <section className="panel" aria-labelledby="versions-title">
        <h2 id="versions-title">Ranking versions</h2>
        {!recs.data ? <Spinner /> : (
          <ul className="versions">
            {recs.data.history.map((h) => (
              <li key={h.version}>
                <p><strong>Version {h.version}</strong> <span className="small muted">{formatDateTime(h.created_at)}</span></p>
                <p className="small">Trigger: {h.trigger}. {h.ranked_count} ranked, {h.excluded_count} not recommended.{h.top_candidate_name ? ` Top option: ${h.top_candidate_name} (${h.top_candidate_id}).` : ""}</p>
                <ul>{h.changes.map((c) => <li key={c}>{c}</li>)}</ul>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
