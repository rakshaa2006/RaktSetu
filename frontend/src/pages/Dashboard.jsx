import { Link } from "react-router-dom";
import Alert from "../components/Alert.jsx";
import EmptyState from "../components/EmptyState.jsx";
import Legend from "../components/Legend.jsx";
import Spinner from "../components/Spinner.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import { useAsync } from "../hooks/useAsync.js";
import { usePageTitle } from "../hooks/usePageTitle.js";
import { api } from "../services/api.js";
import { EVENT_TYPE_LABEL, VERIFICATION, formatDateTime, humanize } from "../utils/format.js";

function LabelCounts({ title, counts }) {
  const keys = Object.keys(VERIFICATION).filter((k) => counts[k]);
  return (
    <div>
      <h3>{title}</h3>
      <ul className="count-list">
        {keys.map((k) => (
          <li key={k}>
            <StatusBadge kind="verification" value={k} /> <strong>{counts[k]}</strong>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function Dashboard() {
  usePageTitle("Dashboard");
  const summary = useAsync(() => api.dashboard(), []);
  const requests = useAsync(() => api.listRequests(), []);
  const meta = useAsync(() => api.meta(), []);

  if (summary.loading && !summary.data) return <Spinner label="Loading dashboard..." />;
  if (summary.error && !summary.data) {
    return (
      <Alert tone="error" title="The dashboard could not be loaded">
        {summary.error.message}{" "}
        <button type="button" className="link-btn" onClick={() => { summary.reload(); requests.reload(); }}>Try again</button>
      </Alert>
    );
  }
  const s = summary.data;
  const list = requests.data || [];
  const urgent = list.filter((r) => ["Critical", "Urgent"].includes(r.urgency) && !["fulfilled", "cancelled"].includes(r.status));

  return (
    <>
      <div className="page-head">
        <h1>Coordination dashboard</h1>
        <Link to="/requests/new" className="btn btn-primary btn-large">Create blood request</Link>
      </div>

      <section className="stat-row" aria-label="Request overview">
        <div className="stat"><span className="stat-n">{s.requests_active}</span><span>Active requests</span></div>
        <div className="stat"><span className="stat-n">{s.requests_urgent_active}</span><span>Critical or urgent and still active</span></div>
        <div className="stat"><span className="stat-n">{s.requests_total}</span><span>Requests in total</span></div>
      </section>

      <section className="panel" aria-labelledby="urgent-title">
        <h2 id="urgent-title">Open and urgent requests</h2>
        {urgent.length === 0 ? (
          <EmptyState title="No urgent requests right now">Create a blood request to see ranked options.</EmptyState>
        ) : (
          <ul className="req-list">
            {urgent.map((r) => (
              <li key={r.id}><RequestRow r={r} /></li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel" aria-labelledby="all-title">
        <h2 id="all-title">All requests</h2>
        {requests.loading && !requests.data ? <Spinner /> : list.length === 0 ? (
          <EmptyState title="No requests yet" action={<Link to="/requests/new" className="btn btn-primary">Create the first request</Link>}>
            Requests you create are saved and will still be here after a refresh.
          </EmptyState>
        ) : (
          <ul className="req-list">{list.map((r) => <li key={r.id}><RequestRow r={r} /></li>)}</ul>
        )}
      </section>

      <section className="panel" aria-labelledby="fresh-title">
        <h2 id="fresh-title">Availability and freshness</h2>
        <p className="muted">How the fictional demonstration records are labelled right now.</p>
        <div className="two-col">
          <LabelCounts title="Blood banks" counts={s.blood_banks} />
          <LabelCounts title="Registered donors" counts={s.donors} />
        </div>
      </section>

      <section className="panel" aria-labelledby="act-title">
        <h2 id="act-title">Recent activity</h2>
        {s.recent_activity.length === 0 ? (
          <EmptyState title="No activity yet">Events appear here as soon as a request is created.</EmptyState>
        ) : (
          <ul className="activity">
            {s.recent_activity.map((e) => (
              <li key={e.event_id}>
                <span className="small muted">{formatDateTime(e.timestamp)}</span>
                <span>
                  <strong>{EVENT_TYPE_LABEL[e.event_type] || humanize(e.event_type)}</strong> on{" "}
                  <Link to={`/requests/${e.request_id}`}>{e.request_id}</Link>
                  {e.is_simulation && " (simulated)"}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <Legend meta={meta.data} />
    </>
  );
}

function RequestRow({ r }) {
  return (
    <Link to={`/requests/${r.id}`} className="req-row">
      <span className="req-id">{r.id}</span>
      <span>{r.units_required} unit(s) of {r.component}, {r.hospital_name}</span>
      <span className="badges">
        <StatusBadge kind="urgency" value={r.urgency} />
        <StatusBadge kind="request" value={r.status} />
      </span>
      <span className="small muted">Created {formatDateTime(r.created_at)}</span>
    </Link>
  );
}
