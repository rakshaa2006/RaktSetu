import { useMemo, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import Alert from "../components/Alert.jsx";
import CandidateCard from "../components/CandidateCard.jsx";
import ConfirmDialog from "../components/ConfirmDialog.jsx";
import ErrorBoundary from "../components/ErrorBoundary.jsx";
import EventButtons from "../components/EventButtons.jsx";
import Legend from "../components/Legend.jsx";
import MapView from "../components/MapView.jsx";
import RequestSummary from "../components/RequestSummary.jsx";
import Spinner from "../components/Spinner.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import Timeline from "../components/Timeline.jsx";
import { useAsync } from "../hooks/useAsync.js";
import { usePageTitle } from "../hooks/usePageTitle.js";
import { api } from "../services/api.js";
import { REQUEST_STATUS, allowedEvents, formatDateTime } from "../utils/format.js";

export default function RequestDetail() {
  const { id } = useParams();
  const location = useLocation();
  usePageTitle(`Request ${id}`);

  const [viewing, setViewing] = useState(null); // null = latest ranking, number = older version (read-only)
  const [timelineKey, setTimelineKey] = useState(0);
  const [pending, setPending] = useState(null); // {kind:'event'|'status', ...}
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(location.state?.justCreated ? { tone: "success", title: "Request saved", text: "The request and patient details were saved, and ranked options were generated." } : null);
  const [actionError, setActionError] = useState(null);
  const [showNonMatching, setShowNonMatching] = useState(false);
  const [showMap, setShowMap] = useState(false);
  const [newest, setNewest] = useState(false);
  const [selectedId, setSelectedId] = useState("");

  const meta = useAsync(() => api.meta(), []);
  const request = useAsync(() => api.getRequest(id), [id]);
  const recs = useAsync(() => api.getRecommendations(id, viewing ?? undefined), [id, viewing]);
  const timeline = useAsync(() => api.getTimeline(id), [id, timelineKey]);
  const allocations = useAsync(() => api.getAllocations(id), [id, timelineKey]);

  const current = recs.data?.current;
  const latestVersion = recs.data?.history?.[0]?.version;
  const readOnly = viewing !== null && viewing !== latestVersion;

  const simulatable = useMemo(() => {
    if (!current) return [];
    return [...current.ranked, ...current.excluded.filter((c) => !["not_matched", "not_consented"].includes(c.exclusion_category))];
  }, [current]);
  const selected = simulatable.find((c) => c.candidate_id === selectedId) || simulatable[0];

  const fatal = request.error || (recs.error && !recs.data ? recs.error : null);
  if (fatal) {
    return (
      <Alert tone="error" title={fatal.status === 404 ? "Request not found" : "This request could not be loaded"}>
        {fatal.message} <Link to="/">Back to the dashboard</Link>
      </Alert>
    );
  }
  if (!request.data || !recs.data || !meta.data) return <Spinner label="Loading request..." />;
  const req = request.data;
  const m = meta.data;

  function startEvent(eventType, candidate) {
    setActionError(null);
    setPending({ kind: "event", eventType, candidate });
  }
  function startStatus(status) {
    setActionError(null);
    setPending({ kind: "status", status });
  }
  function startAllocate(candidate) {
    setActionError(null);
    setPending({ kind: "allocate", candidate, units: 1 });
  }
  function startRelease(allocation) {
    setActionError(null);
    setPending({ kind: "release", allocation });
  }

  async function confirm({ reason, acknowledged }) {
    if (!pending || busy) return;
    setBusy(true);
    setActionError(null);
    try {
      if (pending.kind === "allocate") {
        const { candidate, units } = pending;
        const numUnits = candidate.candidate_type === "donor" ? 1 : Number(units || 1);
        const result = await api.createAllocation(id, {
          candidate_type: candidate.candidate_type,
          candidate_id: candidate.candidate_id,
          units: numUnits,
        });
        request.setData(result.request);
        setNotice({
          tone: "success",
          title: "Units allocated",
          text: `Allocated ${result.allocation.units} unit(s) from ${candidate.display_name}. Total: ${result.allocated_units}/${result.units_required} unit(s). Request status is now "${REQUEST_STATUS[result.request_status]?.label || result.request_status}".`,
        });
      } else if (pending.kind === "release") {
        const { allocation } = pending;
        const result = await api.releaseAllocation(id, allocation.id, { reason: reason || undefined });
        request.setData(result.request);
        setNotice({
          tone: "success",
          title: "Allocation released",
          text: `Released ${result.allocation.units} unit(s). Remaining allocated: ${result.allocated_units}/${result.units_required} unit(s).`,
        });
      } else if (pending.kind === "event") {
        const { eventType, candidate } = pending;
        const result = await api.postEvent(id, {
          event_type: eventType,
          candidate_type: candidate.candidate_type,
          candidate_id: candidate.candidate_id,
          reason: reason || undefined,
        });
        request.setData(result.request);
        recs.setData(result.recommendations);
        setViewing(null);
        setNotice({
          tone: "success", title: "Recorded and ranking recalculated",
          text: `${m.event_types[eventType]} for ${candidate.display_name} (${candidate.candidate_id}). Ranking is now version ${result.recommendations.current.version}.`,
        });
      } else {
        const updated = await api.updateStatus(id, { status: pending.status, reason: reason || undefined, simulated_confirmation: Boolean(acknowledged) });
        request.setData(updated);
        setNotice({ tone: "success", title: "Status updated", text: `Request status is now "${REQUEST_STATUS[updated.status]?.label || updated.status}".` });
      }
      setTimelineKey((k) => k + 1);
      setPending(null);
    } catch (err) {
      setPending(null);
      setNotice(null);
      setActionError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function recalc() {
    if (busy) return;
    setBusy(true);
    setActionError(null);
    try {
      const result = await api.recalculate(id);
      recs.setData(result);
      setViewing(null);
      setTimelineKey((k) => k + 1);
      setNotice({ tone: "success", title: "Ranking recalculated", text: `Ranking is now version ${result.current.version}, using the latest freshness of each record.` });
    } catch (err) {
      setActionError(err.message);
    } finally {
      setBusy(false);
    }
  }

  // ---- dialog text -------------------------------------------------------
  let dialog = { title: "", body: null, confirmLabel: "Confirm" };
  if (pending?.kind === "event") {
    const { eventType, candidate } = pending;
    const label = m.event_types[eventType];
    dialog = {
      title: `${label}?`,
      confirmLabel: "Record this event",
      askReason: true,
      requireReason: eventType === "REINSTATE_CANDIDATE",
      body: (
        <>
          <p><strong>{candidate.display_name}</strong> ({candidate.candidate_id})</p>
          <p>
            {["STOCK_UNAVAILABLE", "DONOR_DECLINED", "DONOR_NO_RESPONSE", "DATA_STALE", "CONFIRM_AVAILABILITY"].includes(eventType)
              ? "This is a simulated event for the demonstration. "
              : ""}
            It will be added to the audit history and the ranking will be recalculated. Earlier rankings are kept.
          </p>
          {eventType === "DONOR_NO_RESPONSE" && <p>No response is never treated as acceptance.</p>}
          {eventType === "REINSTATE_CANDIDATE" && <p>This is an authorised status update. Explain why this option can be considered again.</p>}
        </>
      ),
    };
  } else if (pending?.kind === "status") {
    const s = pending.status;
    const fulfil = s === "fulfilled" || s === "partially_fulfilled";
    dialog = {
      title: `Change status to "${REQUEST_STATUS[s]?.label || s}"?`,
      confirmLabel: "Change status",
      askReason: true,
      requireReason: s === "cancelled",
      requireAck: fulfil,
      ackLabel: "I understand this is a simulated coordinator action, not a real medical transaction.",
      body: (
        <p>
          {fulfil
            ? "Only record this after required units have been allocated. Candidate confirmation alone is not an allocation."
            : "The change will be added to the audit history."}
        </p>
      ),
    };
  } else if (pending?.kind === "allocate") {
    const { candidate } = pending;
    const remaining = req.remaining_units ?? Math.max(0, req.units_required - (req.allocated_units ?? 0));
    const maxUnits = candidate.candidate_type === "donor" ? 1 : Math.max(1, Math.min(candidate.units_available ?? remaining, remaining));
    dialog = {
      title: `Allocate units from ${candidate.display_name}?`,
      confirmLabel: "Allocate units",
      askReason: false,
      body: (
        <>
          <p><strong>{candidate.display_name}</strong> ({candidate.candidate_id})</p>
          <p className="muted">Type: {candidate.candidate_type === "blood_bank" ? "Blood bank" : "Registered donor"}</p>
          {candidate.candidate_type === "donor" ? (
            <p>Donors contribute exactly <strong>1 unit</strong>. Verified consent is required.</p>
          ) : (
            <div className="field">
              <label htmlFor="alloc-units">Units to allocate (1 to {maxUnits})</label>
              <input
                id="alloc-units"
                type="number"
                min="1"
                max={maxUnits}
                defaultValue={1}
                onChange={(e) => {
                  const val = Math.max(1, Math.min(maxUnits, parseInt(e.target.value, 10) || 1));
                  setPending((p) => (p ? { ...p, units: val } : null));
                }}
              />
            </div>
          )}
          <p className="small muted">
            This operation atomically reserves stock, persists the allocation, and updates fulfillment status.
          </p>
        </>
      ),
    };
  } else if (pending?.kind === "release") {
    const { allocation } = pending;
    dialog = {
      title: `Release allocation ${allocation.id}?`,
      confirmLabel: "Release units",
      askReason: true,
      body: (
        <p>
          This will release <strong>{allocation.units} unit(s)</strong> from {allocation.candidate_id} back to available stock and recompute request fulfillment.
        </p>
      ),
    };
  }

  const nextStatuses = m.request_transitions[req.status] || [];
  const ranked = current.ranked;
  const excludedRelevant = current.excluded.filter((c) => c.exclusion_category !== "not_matched");
  const excludedOther = current.excluded.filter((c) => c.exclusion_category === "not_matched");
  const points = [...ranked, ...excludedRelevant].filter((c) => c.latitude !== null && c.latitude !== undefined)
    .map((c) => ({ lat: c.latitude, lng: c.longitude, kind: c.candidate_type, label: `${c.rank ? "#" + c.rank + " " : ""}${c.display_name} (${c.candidate_id})` }));
  const hospital = req.hospital_latitude !== null ? { lat: req.hospital_latitude, lng: req.hospital_longitude, label: `Hospital: ${req.hospital_name}` } : null;

  return (
    <>
      <div className="page-head">
        <h1>Request {req.id}</h1>
        <div className="badges">
          <StatusBadge kind="urgency" value={req.urgency} />
          <StatusBadge kind="request" value={req.status} />
          {req.approval_status && <StatusBadge kind="approval" value={req.approval_status} />}
          <span className="badge badge-plain">Demonstration data</span>
        </div>
      </div>

      {req.approval_status === "rejected" && (
        <Alert tone="error" title="Blood request rejected by blood bank">
          Blood bank <strong>{req.decided_by_bank_id || req.target_blood_bank_id}</strong> rejected this request:
          <br /><em>"{req.rejection_reason}"</em>
        </Alert>
      )}

      {req.approval_status === "pending" && (
        <Alert tone="warning" title="Awaiting blood bank approval">
          This request is assigned to <strong>{req.target_blood_bank_id}</strong> and is awaiting explicit bank review and decision.
        </Alert>
      )}

      {req.approval_status === "approved" && (
        <Alert tone="success" title="Approved by blood bank">
          Blood bank <strong>{req.decided_by_bank_id || req.target_blood_bank_id}</strong> has approved handling this request.
          <br /><span className="small muted">Note: Approval confirms readiness to handle the requirement; unit allocation remains a separate step.</span>
        </Alert>
      )}

      {notice && <Alert tone={notice.tone} title={notice.title} onDismiss={() => setNotice(null)}>{notice.text}</Alert>}
      {actionError && <Alert tone="error" title="That action was not applied" onDismiss={() => setActionError(null)}>{actionError} Nothing was changed.</Alert>}

      <RequestSummary request={req} />

      <section className="panel" aria-labelledby="alloc-title">
        <h2 id="alloc-title">Units & allocations</h2>
        <div className="stat-row">
          <div className="stat">
            <span className="small muted">Required units</span>
            <span className="stat-n">{req.units_required}</span>
          </div>
          <div className="stat">
            <span className="small muted">Allocated units</span>
            <span className="stat-n">{req.allocated_units ?? 0}</span>
          </div>
          <div className="stat">
            <span className="small muted">Remaining units</span>
            <span className="stat-n">{req.remaining_units ?? Math.max(0, req.units_required - (req.allocated_units ?? 0))}</span>
          </div>
        </div>
        {(!allocations.data || allocations.data.length === 0) ? (
          <p className="muted">No units have been allocated yet. Confirm candidate availability below to allocate units.</p>
        ) : (
          <div className="allocations-table-wrap">
            <table className="alloc-table" style={{ width: "100%", borderCollapse: "collapse", margin: "0.5rem 0 1rem" }}>
              <thead>
                <tr style={{ borderBottom: "2px solid var(--border)", textAlign: "left" }}>
                  <th style={{ padding: "0.5rem" }}>Allocation ID</th>
                  <th style={{ padding: "0.5rem" }}>Candidate</th>
                  <th style={{ padding: "0.5rem" }}>Type</th>
                  <th style={{ padding: "0.5rem" }}>Units</th>
                  <th style={{ padding: "0.5rem" }}>Status</th>
                  <th style={{ padding: "0.5rem" }}>Allocated at</th>
                  <th style={{ padding: "0.5rem" }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {allocations.data.map((a) => (
                  <tr key={a.id} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td style={{ padding: "0.5rem" }}><code>{a.id}</code></td>
                    <td style={{ padding: "0.5rem" }}><strong>{a.candidate_id}</strong></td>
                    <td style={{ padding: "0.5rem" }}>{a.candidate_type === "blood_bank" ? "Blood bank" : "Donor"}</td>
                    <td style={{ padding: "0.5rem" }}><strong>{a.units}</strong></td>
                    <td style={{ padding: "0.5rem" }}>
                      <span className={`badge ${a.status === "active" ? "badge-good" : "badge-info"}`}>
                        {a.status === "active" ? "Active" : "Released"}
                      </span>
                    </td>
                    <td style={{ padding: "0.5rem" }} className="small muted">{formatDateTime(a.created_at)}</td>
                    <td style={{ padding: "0.5rem" }}>
                      {a.status === "active" && !readOnly && req.status !== "cancelled" && (
                        <button
                          type="button"
                          className="btn btn-secondary btn-small"
                          disabled={busy}
                          onClick={() => startRelease(a)}
                        >
                          Release
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel" aria-labelledby="status-title">
        <h2 id="status-title">Request status</h2>
        <p>Current status: <StatusBadge kind="request" value={req.status} /></p>
        {nextStatuses.length === 0 ? (
          <p className="muted">This request is finished, so its status can no longer change.</p>
        ) : (
          <>
            <p className="muted">Move this request to the next step. These are simulated coordinator actions.</p>
            <div className="btn-row">
              {nextStatuses.map((s) => (
                <button key={s} type="button" className={`btn ${s === "cancelled" ? "btn-secondary" : "btn-primary"}`} disabled={busy} onClick={() => startStatus(s)}>
                  Mark as {REQUEST_STATUS[s]?.label.toLowerCase() || s}
                </button>
              ))}
            </div>
          </>
        )}
      </section>

      <section className="panel" aria-labelledby="recs-title">
        <div className="page-head">
          <h2 id="recs-title">Recommended options</h2>
          <button type="button" className="btn btn-secondary" onClick={recalc} disabled={busy || readOnly}>
            {busy ? "Working..." : "Recalculate ranking"}
          </button>
        </div>
        <p><strong>{current.summary.workflow_priority}</strong></p>
        <p className="notice-box">{current.summary.disclaimer}</p>
        {readOnly && (
          <Alert tone="warning" title={`You are viewing an earlier ranking (version ${current.version})`}>
            Actions are turned off on older versions.{" "}
            <button type="button" className="link-btn" onClick={() => setViewing(null)}>Back to the latest ranking</button>
          </Alert>
        )}
        <div className="changes" aria-live="polite">
          <h3>What changed in version {current.version}</h3>
          <p className="small muted">Trigger: {current.trigger}. Generated {formatDateTime(current.created_at)}.</p>
          <ul>{current.changes.map((c) => <li key={c}>{c}</li>)}</ul>
        </div>

        <div className="btn-row">
          <button type="button" className="btn btn-secondary" aria-expanded={showMap} onClick={() => setShowMap((s) => !s)}>
            {showMap ? "Hide map" : "Show map (optional)"}
          </button>
        </div>
        {showMap && (
          <ErrorBoundary fallback="The map could not be shown. The ranked list below has the same options.">
            <MapView points={points} hospital={hospital} />
          </ErrorBoundary>
        )}

        {ranked.length === 0 ? (
          <Alert tone="warning" title="No eligible options right now">
            Every matching option is excluded or unavailable. Review the excluded options below, or reinstate one with a reason if you have new information.
          </Alert>
        ) : (
          <ol className="candidate-list">
            {ranked.map((c) => (
              <li key={c.candidate_id}>
                <CandidateCard item={c} meta={m} onAction={startEvent} onAllocate={startAllocate} busy={busy} readOnly={readOnly} />
              </li>
            ))}
          </ol>
        )}

        <h3>Not recommended ({excludedRelevant.length})</h3>
        {excludedRelevant.length === 0 ? <p className="muted">No matching option has been excluded.</p> : (
          <ul className="candidate-list">
            {excludedRelevant.map((c) => (
              <li key={c.candidate_id}>
                <CandidateCard item={c} meta={m} onAction={startEvent} onAllocate={startAllocate} busy={busy} readOnly={readOnly} />
              </li>
            ))}
          </ul>
        )}
        <label className="check">
          <input type="checkbox" checked={showNonMatching} onChange={(e) => setShowNonMatching(e.target.checked)} />
          <span>Also show the {excludedOther.length} records that do not match this blood group or component</span>
        </label>
        {showNonMatching && (
          <ul className="candidate-list">
            {excludedOther.map((c) => (
              <li key={c.candidate_id}><CandidateCard item={c} meta={m} onAction={startEvent} busy={busy} readOnly /></li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel" aria-labelledby="sim-title">
        <h2 id="sim-title">Failure simulation</h2>
        <p className="muted">
          Test what happens when things go wrong. Pick an option, then choose an event. No messages are sent; the event
          is validated, saved, and the ranking is recalculated. Declined or unavailable options are not recommended
          again for this request unless you reinstate them with a reason.
        </p>
        {readOnly || simulatable.length === 0 ? (
          <p className="muted">{readOnly ? "Go back to the latest ranking to simulate events." : "There are no options to simulate on."}</p>
        ) : (
          <>
            <div className="field">
              <label htmlFor="sim-candidate">Option to simulate on</label>
              <select id="sim-candidate" value={selected?.candidate_id || ""} onChange={(e) => setSelectedId(e.target.value)}>
                {simulatable.map((c) => (
                  <option key={c.candidate_id} value={c.candidate_id}>
                    {c.rank ? `#${c.rank}` : "Not recommended"} - {c.display_name} ({c.candidate_id})
                  </option>
                ))}
              </select>
            </div>
            {selected && <EventButtons candidate={selected} events={allowedEvents(selected, m)} onAction={startEvent} busy={busy} />}
          </>
        )}
      </section>

      <section className="panel" aria-labelledby="hist-title">
        <h2 id="hist-title">Ranking history</h2>
        <p className="muted">Every ranking is kept. Open an older one to compare (read-only).</p>
        <ul className="versions">
          {recs.data.history.map((h) => (
            <li key={h.version}>
              <p>
                <strong>Version {h.version}</strong> <span className="small muted">{formatDateTime(h.created_at)}</span>{" "}
                {h.version === current.version ? <span className="badge badge-plain">Showing</span> : (
                  <button type="button" className="btn btn-ghost" onClick={() => setViewing(h.version)}>View this version</button>
                )}
              </p>
              <p className="small">Trigger: {h.trigger}. {h.ranked_count} ranked. {h.top_candidate_name ? `Top: ${h.top_candidate_name} (${h.top_candidate_id}).` : "No eligible option."}</p>
            </li>
          ))}
        </ul>
      </section>

      <section className="panel" aria-labelledby="tl-title">
        <div className="page-head">
          <h2 id="tl-title">Audit timeline</h2>
          <Link className="btn btn-secondary" to={`/requests/${id}/timeline`}>Open full history page</Link>
        </div>
        <label className="check">
          <input type="checkbox" checked={newest} onChange={(e) => setNewest(e.target.checked)} />
          <span>Show newest first</span>
        </label>
        {!timeline.data ? <Spinner /> : <Timeline events={timeline.data} newestFirst={newest} />}
        {timeline.error && <Alert tone="error" title="Timeline could not be refreshed">{timeline.error.message}</Alert>}
      </section>

      <Legend meta={m} />

      <ConfirmDialog
        open={Boolean(pending)}
        title={dialog.title}
        confirmLabel={dialog.confirmLabel}
        askReason={dialog.askReason}
        requireReason={dialog.requireReason}
        requireAck={dialog.requireAck}
        ackLabel={dialog.ackLabel}
        busy={busy}
        onCancel={() => setPending(null)}
        onConfirm={confirm}
      >
        {dialog.body}
      </ConfirmDialog>
    </>
  );
}
