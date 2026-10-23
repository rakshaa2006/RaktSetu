import { formatDateTime } from "../utils/format.js";
import StatusBadge from "./StatusBadge.jsx";

export default function RequestSummary({ request }) {
  return (
    <section className="panel" aria-labelledby="summary-title">
      <h2 id="summary-title">Request details</h2>
      <div className="two-col">
        <div>
          <h3>Patient (fictional)</h3>
          <p className="bloodgroup" aria-label={`Patient blood group ${request.patient_blood_group}`}>
            <span className="small">Patient blood group</span>
            <strong>{request.patient_blood_group}</strong>
          </p>
          <dl className="facts facts-stack">
            <div><dt>Name</dt><dd>{request.patient_name}</dd></div>
            <div><dt>Age</dt><dd>{request.patient_age} years</dd></div>
            <div><dt>Gender</dt><dd>{request.patient_gender}</dd></div>
          </dl>
        </div>
        <div>
          <h3>Blood request</h3>
          <dl className="facts facts-stack">
            <div><dt>Request ID</dt><dd>{request.id}</dd></div>
            <div><dt>Component needed</dt><dd>{request.component}</dd></div>
            <div><dt>Units required</dt><dd>{request.units_required}</dd></div>
            <div><dt>Units allocated</dt><dd><strong>{request.allocated_units ?? 0}</strong> / {request.units_required}</dd></div>
            <div><dt>Units remaining</dt><dd><strong>{request.remaining_units ?? Math.max(0, request.units_required - (request.allocated_units ?? 0))}</strong></dd></div>
            <div><dt>Urgency</dt><dd><StatusBadge kind="urgency" value={request.urgency} /></dd></div>
            <div><dt>Status</dt><dd><StatusBadge kind="request" value={request.status} /></dd></div>
            <div><dt>Hospital</dt><dd>{request.hospital_name}, {request.hospital_location}</dd></div>
            <div><dt>Created</dt><dd>{formatDateTime(request.created_at)}</dd></div>
          </dl>
        </div>
      </div>
    </section>
  );
}
