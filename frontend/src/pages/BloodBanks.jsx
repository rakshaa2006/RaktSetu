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

export default function BloodBanks() {
  usePageTitle("Blood banks");
  const meta = useAsync(() => api.meta(), []);
  const locations = useAsync(() => api.locations(), []);
  const [near, setNear] = useState("");
  const [group, setGroup] = useState("");
  const [component, setComponent] = useState("");
  const [showMap, setShowMap] = useState(false);
  const { params, point } = nearParams(near, locations.data);
  const banks = useAsync(
    () => api.bloodBanks({ ...params, blood_group: group, component }),
    [near, group, component, locations.data]
  );
  const list = banks.data || [];
  const points = [
    ...list.filter((b) => b.latitude !== null).map((b) => ({ lat: b.latitude, lng: b.longitude, label: `${b.name} (${b.id})`, kind: "blood_bank" })),
  ];
  const noCoords = list.filter((b) => b.latitude === null).length;

  return (
    <>
      <h1>Blood banks and availability</h1>
      <p className="muted">Fictional demonstration records. Reported stock is not a real-time claim and must be confirmed with the blood bank.</p>
      <section className="panel filters" aria-label="Filters">
        <NearControl locations={locations.data} value={near} onChange={setNear} error={locations.error} />
        <div className="field">
          <label htmlFor="f-group">Blood group</label>
          <select id="f-group" value={group} onChange={(e) => setGroup(e.target.value)}>
            <option value="">All groups</option>
            {(meta.data?.blood_groups || []).map((g) => <option key={g} value={g}>{g}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="f-comp">Component</label>
          <select id="f-comp" value={component} onChange={(e) => setComponent(e.target.value)}>
            <option value="">All components</option>
            {(meta.data?.components || []).map((c) => <option key={c} value={c}>{c}</option>)}
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

      {banks.loading && !banks.data && <Spinner label="Loading blood banks..." />}
      {banks.error && (
        <Alert tone="error" title="Blood banks could not be loaded">
          {banks.error.message} <button type="button" className="link-btn" onClick={banks.reload}>Try again</button>
        </Alert>
      )}
      {banks.data && list.length === 0 && <EmptyState title="No blood banks match these filters">Clear a filter to see more records.</EmptyState>}
      {noCoords > 0 && <p className="small muted">{noCoords} record(s) have no coordinates, so they are not on the map and their distance is unknown.</p>}
      <ul className="record-list">
        {list.map((b) => (
          <li key={b.id} className="record">
            <h2 className="h3">{b.name} <span className="id">{b.id}</span></h2>
            <p className="muted">{b.location}</p>
            <div className="badges">
              <StatusBadge kind="verification" value={b.verification_label} />
              <span className="badge badge-plain">Record says: {humanize(b.availability_status)}</span>
              <span className="badge badge-plain">Simulated data</span>
            </div>
            <dl className="facts">
              <div><dt>Blood group</dt><dd>{b.blood_group}</dd></div>
              <div><dt>Component</dt><dd>{b.component}</dd></div>
              <div><dt>Units reported</dt><dd>{b.units_available}</dd></div>
              <div><dt>Last updated</dt><dd>{b.last_updated && b.freshness !== "unknown" ? `${formatDateTime(b.last_updated)} (${formatAge(b.age_hours)})` : "Not recorded or unreadable"}</dd></div>
              <div><dt>Distance</dt><dd>{b.distance_km !== null ? `About ${b.distance_km} km in a straight line` : b.distance_note}</dd></div>
              <div><dt>Source</dt><dd>{b.data_source}</dd></div>
            </dl>
            <p className="small muted">{b.freshness_note}</p>
          </li>
        ))}
      </ul>
      <Legend meta={meta.data} />
    </>
  );
}
