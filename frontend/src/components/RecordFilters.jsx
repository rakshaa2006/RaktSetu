// "Show distance from" picker used by the blood bank and donor pages.
export default function NearControl({ locations, value, onChange, error }) {
  return (
    <div className="field">
      <label htmlFor="near">Show distance from</label>
      <p id="near-hint" className="hint">Straight-line distance only. It is not road distance or travel time.</p>
      <select id="near" aria-describedby="near-hint" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">No location chosen</option>
        {(locations || []).map((l) => (
          <option key={l.location_id} value={l.location_id}>{l.name}</option>
        ))}
      </select>
      {error && <p className="field-error" role="alert">Locations could not be loaded: {error.message}</p>}
    </div>
  );
}

export function nearParams(locationId, locations) {
  const loc = (locations || []).find((l) => l.location_id === locationId);
  if (!loc) return { params: {}, point: null };
  return {
    params: { near_lat: loc.latitude, near_lng: loc.longitude },
    point: { lat: loc.latitude, lng: loc.longitude, label: `Chosen location: ${loc.name}` },
  };
}
