import { useState } from "react";
import Alert from "../components/Alert.jsx";
import EmptyState from "../components/EmptyState.jsx";
import ErrorBoundary from "../components/ErrorBoundary.jsx";
import Legend from "../components/Legend.jsx";
import MapView from "../components/MapView.jsx";
import NearControl, { nearParams } from "../components/RecordFilters.jsx";
import Spinner from "../components/Spinner.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import { useAsync } from "../hooks/useAsync.js";
import { usePageTitle } from "../hooks/usePageTitle.js";
import { api } from "../services/api.js";
import { formatAge, formatDateTime, humanize } from "../utils/format.js";

const CONSENT = { consented_demo: "Consented (demonstration)", not_consented: "Has not consented", unknown: "Consent unknown" };
const RESPONSE = { responsive: "Responsive", no_recent_response: "No recent response", declined_recently: "Declined recently", unknown: "Response unknown" };

export default function Donors() {
  usePageTitle("Registered donors");
  const meta = useAsync(() => api.meta(), []);
  const locations = useAsync(() => api.locations(), []);
  const [near, setNear] = useState("");
  const [group, setGroup] = useState("");
  const [showMap, setShowMap] = useState(false);
  const { params, point } = nearParams(near, locations.data);
  const donors = useAsync(() => api.donors({ ...params, blood_group: group }), [near, group, locations.data]);
  const list = donors.data || [];
  const points = list.filter((d) => d.latitude !== null).map((d) => ({ lat: d.latitude, lng: d.longitude, label: `${d.display_name} (${d.id})`, kind: "donor" }));
  const noCoords = list.filter((d) => d.latitude === null).length;

  return (
    <>
      <h1>Registered donors</h1>
      <p className="muted">Pseudonymous, fictional donor records. No real names or contact details are used. Donor eligibility must always be confirmed by qualified staff.</p>
      <section className="panel filters" aria-label="Filters">
        <NearControl locations={locations.data} value={near} onChange={setNear} error={locations.error} />
        <div className="field">
          <label htmlFor="f-group">Blood group</label>
          <select id="f-group" value={group} onChange={(e) => setGroup(e.target.value)}>
            <option value="">All groups</option>
            {(meta.data?.blood_groups || []).map((g) => <option key={g} value={g}>{g}</option>)}
          </select>
        </div>
      </section>
      <div className="btn-row">
        <button type="button" className="btn btn-secondary" onClick={() => setShowMap((s) => !s)} aria-expanded={showMap}>
          {showMap ? "Hide map" : "Show map (optional)"}
        </button>
      </div>
      {showMap && (
        <ErrorBoundary fallback="The map could not be shown. The list below has the same records.">
          <MapView points={points} hospital={point} />
        </ErrorBoundary>
      )}
      {donors.loading && !donors.data && <Spinner label="Loading donors..." />}
      {donors.error && (
        <Alert tone="error" title="Donors could not be loaded">
          {donors.error.message} <button type="button" className="link-btn" onClick={donors.reload}>Try again</button>
        </Alert>
      )}
      {donors.data && list.length === 0 && <EmptyState title="No donors match this filter">Choose "All groups" to see more records.</EmptyState>}
      {noCoords > 0 && <p className="small muted">{noCoords} record(s) have no coordinates, so they are not on the map and their distance is unknown.</p>}
      <ul className="record-list">
        {list.map((d) => (
          <li key={d.id} className="record">
            <h2 className="h3">{d.display_name} <span className="id">{d.id}</span></h2>
            <p className="muted">{d.location}</p>
            <div className="badges">
              <StatusBadge kind="verification" value={d.verification_label} />
              <span className="badge badge-plain">Record says: {humanize(d.availability_status)}</span>
              <span className="badge badge-plain">Simulated data</span>
            </div>
            <dl className="facts">
              <div><dt>Blood group</dt><dd>{d.blood_group}</dd></div>
              <div><dt>Contact consent</dt><dd>{CONSENT[d.consent_status] || humanize(d.consent_status)}</dd></div>
              <div><dt>Response</dt><dd>{RESPONSE[d.response_status] || humanize(d.response_status)}</dd></div>
              <div><dt>Last updated</dt><dd>{d.last_updated && d.freshness !== "unknown" ? `${formatDateTime(d.last_updated)} (${formatAge(d.age_hours)})` : "Not recorded or unreadable"}</dd></div>
              <div><dt>Distance</dt><dd>{d.distance_km !== null ? `About ${d.distance_km} km in a straight line` : d.distance_note}</dd></div>
              <div><dt>Source</dt><dd>{d.data_source}</dd></div>
            </dl>
            <p className="small muted">{d.freshness_note}</p>
          </li>
        ))}
      </ul>
      <Legend meta={meta.data} />
    </>
  );
}
