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

  async function confirm({ reason, acknowledged }) {
    if (!pending || busy) return;
    setBusy(true);
    setActionError(null);
    try {
      if (pending.kind === "event") {
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
            ? "Only record this after at least one option has been marked as confirmed available. Being ranked first or selected for review does not make a request fulfilled."
            : "The change will be added to the audit history."}
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
          <span className="badge badge-plain">Demonstration data</span>
        </div>
      </div>

      {notice && <Alert tone={notice.tone} title={notice.title} onDismiss={() => setNotice(null)}>{notice.text}</Alert>}
      {actionError && <Alert tone="error" title="That action was not applied" onDismiss={() => setActionError(null)}>{actionError} Nothing was changed.</Alert>}

      <RequestSummary request={req} />

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
                <CandidateCard item={c} meta={m} onAction={startEvent} busy={busy} readOnly={readOnly} />
              </li>
            ))}
          </ol>
        )}

        <h3>Not recommended ({excludedRelevant.length})</h3>
        {excludedRelevant.length === 0 ? <p className="muted">No matching option has been excluded.</p> : (
          <ul className="candidate-list">
            {excludedRelevant.map((c) => (
              <li key={c.candidate_id}>
                <CandidateCard item={c} meta={m} onAction={startEvent} busy={busy} readOnly={readOnly} />
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
