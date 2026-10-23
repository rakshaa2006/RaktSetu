import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import Alert from "../components/Alert.jsx";
import ConfirmDialog from "../components/ConfirmDialog.jsx";
import EmptyState from "../components/EmptyState.jsx";
import Spinner from "../components/Spinner.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import { useAsync } from "../hooks/useAsync.js";
import { usePageTitle } from "../hooks/usePageTitle.js";
import { ApiError, api } from "../services/api.js";
import { formatDateTime } from "../utils/format.js";

const TOKEN_KEY = "raktsetu_demo_token";
const BANK_KEY = "raktsetu_active_bank_id";

export default function BankInbox() {
  usePageTitle("Blood bank inbox");

  // Load list of blood banks for identity selector
  const bloodBanks = useAsync(() => api.bloodBanks(), []);
  const banksList = useMemo(() => {
    if (!bloodBanks.data) return [];
    const seen = new Set();
    const result = [];
    for (const b of bloodBanks.data) {
      if (!seen.has(b.id)) {
        seen.add(b.id);
        result.push(b);
      }
    }
    return result.sort((a, b) => a.id.localeCompare(b.id));
  }, [bloodBanks.data]);

  // Bank identity and demo token (persisted in sessionStorage)
  const [activeBankId, setActiveBankId] = useState(() => sessionStorage.getItem(BANK_KEY) || "");
  const [token, setToken] = useState(() => sessionStorage.getItem(TOKEN_KEY) || "");
  const [tokenInput, setTokenInput] = useState(() => sessionStorage.getItem(TOKEN_KEY) || "");

  // Inbox state
  const [filterStatus, setFilterStatus] = useState("all"); // 'all' | 'pending' | 'approved' | 'rejected'
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(false);
  const [inboxError, setInboxError] = useState(null);
  const [notice, setNotice] = useState(null);

  // Decision actions state
  const [pendingAction, setPendingAction] = useState(null); // { type: 'approve' | 'reject', request: {...} }
  const [rejectReason, setRejectReason] = useState("");
  const [rejectError, setRejectError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  // Sync state to sessionStorage when active bank changes
  useEffect(() => {
    if (banksList.length > 0 && !activeBankId) {
      setActiveBankId(banksList[0].id);
      sessionStorage.setItem(BANK_KEY, banksList[0].id);
    }
  }, [banksList, activeBankId]);

  function onSelectBank(bankId) {
    setActiveBankId(bankId);
    sessionStorage.setItem(BANK_KEY, bankId);
    setNotice(null);
    setInboxError(null);
  }

  function onApplyToken(e) {
    e.preventDefault();
    const clean = tokenInput.trim();
    setToken(clean);
    sessionStorage.setItem(TOKEN_KEY, clean);
    setNotice({ tone: "info", title: "Token updated", text: "Using updated demo bearer token for bank requests." });
  }

  // Fetch inbox requests whenever activeBankId, token, or filter changes
  async function loadInbox() {
    if (!token) {
      setRequests([]);
      return;
    }
    setLoading(true);
    setInboxError(null);
    try {
      const approval_status = filterStatus === "all" ? undefined : filterStatus;
      const data = await api.getBankInbox(activeBankId, { approval_status, token });
      setRequests(data || []);
    } catch (err) {
      setRequests([]);
      if (err instanceof ApiError) {
        if (err.status === 401) {
          setInboxError("Authentication required: Invalid or missing demo bearer token. Please verify your token below.");
        } else if (err.status === 403) {
          setInboxError(`Forbidden: The provided token is not authorized for blood bank '${activeBankId}'. Each bank requires its own mapped token.`);
        } else {
          setInboxError(err.message);
        }
      } else {
        setInboxError(err.message || "Failed to load bank inbox.");
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadInbox();
  }, [activeBankId, token, filterStatus]);

  // Execute approval
  async function handleApprove(req) {
    setSubmitting(true);
    setNotice(null);
    try {
      const updated = await api.approveRequest(req.id, { token, bankId: activeBankId });
      setNotice({
        tone: "success",
        title: "Request approved",
        text: `Request ${req.id} has been approved. The request status is now 'under_review'. Note: approval does not reserve or allocate stock.`,
      });
      setPendingAction(null);
      await loadInbox();
    } catch (err) {
      setNotice({
        tone: "error",
        title: "Approval failed",
        text: err.message,
      });
    } finally {
      setSubmitting(false);
    }
  }

  // Execute rejection
  async function handleReject(req) {
    const trimmed = rejectReason.trim();
    if (trimmed.length < 5) {
      setRejectError("Rejection reason must be at least 5 characters.");
      return;
    }
    if (trimmed.length > 300) {
      setRejectError("Rejection reason must be 300 characters or fewer.");
      return;
    }

    setSubmitting(true);
    setRejectError(null);
    setNotice(null);
    try {
      const updated = await api.rejectRequest(req.id, { reason: trimmed }, { token, bankId: activeBankId });
      setNotice({
        tone: "info",
        title: "Request rejected",
        text: `Request ${req.id} has been rejected. Reason recorded: "${trimmed}".`,
      });
      setPendingAction(null);
      setRejectReason("");
      await loadInbox();
    } catch (err) {
      setRejectError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  const activeBankObj = banksList.find((b) => b.id === activeBankId);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Blood bank request inbox</h1>
          <p className="muted">
            Review incoming targeted blood requests. The assigned blood bank must explicitly approve or reject requests.
          </p>
        </div>
      </div>

      {/* Demo Identity and Bearer Token Configuration Bar */}
      <section className="panel" aria-labelledby="identity-heading">
        <h2 id="identity-heading" className="h3">Bank identity and demo authorization</h2>
        <p className="small muted">
          Demo identities use server-configured Bearer tokens (via <code>RAKTSETU_DEMO_TOKENS</code>). Select your bank and enter its token.
        </p>

        <form onSubmit={onApplyToken} className="filters" style={{ alignItems: "flex-end" }}>
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor="active-bank-select">Acting as blood bank</label>
            <select
              id="active-bank-select"
              value={activeBankId}
              onChange={(e) => onSelectBank(e.target.value)}
            >
              {banksList.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name} ({b.id} &bull; {b.location})
                </option>
              ))}
            </select>
          </div>

          <div className="field" style={{ margin: 0 }}>
            <label htmlFor="token-input">Demo bearer token</label>
            <input
              id="token-input"
              type="password"
              placeholder="Enter configured demo token..."
              value={tokenInput}
              onChange={(e) => setTokenInput(e.target.value)}
              autoComplete="off"
            />
          </div>

          <div>
            <button type="submit" className="btn btn-secondary">
              Apply token
            </button>
          </div>
        </form>
      </section>

      {/* Alerts & Notifications */}
      {notice && (
        <Alert tone={notice.tone} title={notice.title} onClose={() => setNotice(null)}>
          {notice.text}
        </Alert>
      )}

      {inboxError && (
        <Alert tone="error" title="Inbox access error">
          <p>{inboxError}</p>
          <button type="button" className="link-btn" onClick={loadInbox}>
            Try reloading inbox
          </button>
        </Alert>
      )}

      {!token && (
        <Alert tone="warning" title="Authorization required">
          Please enter your blood bank demo token in the field above to view and manage your inbox.
        </Alert>
      )}

      {/* Filter Tabs */}
      <section className="panel" style={{ paddingBottom: "0.5rem" }}>
        <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "center", gap: "1rem", marginBottom: "1rem" }}>
          <h2 className="h3" style={{ margin: 0 }}>
            Incoming requests for {activeBankObj ? `${activeBankObj.name} (${activeBankId})` : activeBankId}
          </h2>
          <div className="btn-row" style={{ margin: 0 }}>
            <button
              type="button"
              className={`btn btn-small ${filterStatus === "all" ? "btn-primary" : "btn-secondary"}`}
              onClick={() => setFilterStatus("all")}
            >
              All requests
            </button>
            <button
              type="button"
              className={`btn btn-small ${filterStatus === "pending" ? "btn-primary" : "btn-secondary"}`}
              onClick={() => setFilterStatus("pending")}
            >
              Pending review
            </button>
            <button
              type="button"
              className={`btn btn-small ${filterStatus === "approved" ? "btn-primary" : "btn-secondary"}`}
              onClick={() => setFilterStatus("approved")}
            >
              Approved
            </button>
            <button
              type="button"
              className={`btn btn-small ${filterStatus === "rejected" ? "btn-primary" : "btn-secondary"}`}
              onClick={() => setFilterStatus("rejected")}
            >
              Rejected
            </button>
          </div>
        </div>

        {/* Requests List */}
        {loading ? (
          <Spinner label="Loading targeted requests..." />
        ) : requests.length === 0 ? (
          <EmptyState title="No requests found">
            {token ? (
              <p>There are no {filterStatus !== "all" ? filterStatus : ""} requests targeted to {activeBankId} at this time.</p>
            ) : (
              <p>Enter a valid demo bearer token to view this bank's inbox.</p>
            )}
          </EmptyState>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem", marginBottom: "1rem" }}>
            {requests.map((r) => (
              <article key={r.id} className="record" style={{ borderLeft: r.approval_status === "pending" ? "5px solid var(--amber)" : r.approval_status === "approved" ? "5px solid var(--green)" : "5px solid var(--red-dark)" }}>
                <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem" }}>
                  <div>
                    <Link to={`/requests/${r.id}`} className="req-id" style={{ fontSize: "1.15rem" }}>
                      {r.id}
                    </Link>
                    <span className="id">&bull; {r.hospital_name} ({r.hospital_location})</span>
                  </div>
                  <div className="badges">
                    <StatusBadge kind="urgency" value={r.urgency} />
                    <StatusBadge kind="request" value={r.status} />
                    {r.approval_status && <StatusBadge kind="approval" value={r.approval_status} />}
                  </div>
                </div>

                <div className="facts" style={{ margin: "0.75rem 0" }}>
                  <div>
                    <dt>Patient</dt>
                    <dd>{r.patient_name} ({r.patient_age}y, {r.patient_gender})</dd>
                  </div>
                  <div>
                    <dt>Required blood group & component</dt>
                    <dd><strong>{r.patient_blood_group}</strong> &bull; {r.component}</dd>
                  </div>
                  <div>
                    <dt>Units requested</dt>
                    <dd>{r.units_required} unit(s)</dd>
                  </div>
                  <div>
                    <dt>Received</dt>
                    <dd>{formatDateTime(r.created_at)}</dd>
                  </div>
                </div>

                {/* Decision Metadata */}
                {r.approval_status === "approved" && (
                  <div className="notice-box" style={{ background: "var(--green-tint)", borderLeftColor: "var(--green)", marginBottom: "0.75rem" }}>
                    <strong>Approved by bank:</strong> Decision recorded by {r.decided_by_bank_id || activeBankId} on {formatDateTime(r.decided_at)}.
                    <br /><span className="small muted">Approval confirms readiness to process this request. Stock allocation remains a separate step.</span>
                  </div>
                )}

                {r.approval_status === "rejected" && (
                  <div className="notice-box" style={{ background: "var(--red-tint)", borderLeftColor: "var(--red-dark)", marginBottom: "0.75rem" }}>
                    <strong>Rejected by bank:</strong> {r.rejection_reason || "No reason recorded."}
                    <br /><span className="small muted">Recorded by {r.decided_by_bank_id || activeBankId} on {formatDateTime(r.decided_at)}.</span>
                  </div>
                )}

                {/* Actions for Pending Requests */}
                {r.approval_status === "pending" && (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "0.6rem", alignItems: "center", paddingTop: "0.5rem", borderTop: "1px solid var(--grey-tint)" }}>
                    <button
                      type="button"
                      className="btn btn-primary btn-small"
                      disabled={submitting}
                      onClick={() => setPendingAction({ type: "approve", request: r })}
                    >
                      Approve request
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary btn-small"
                      disabled={submitting}
                      onClick={() => {
                        setPendingAction({ type: "reject", request: r });
                        setRejectReason("");
                        setRejectError(null);
                      }}
                    >
                      Reject request
                    </button>
                    <Link to={`/requests/${r.id}`} className="btn btn-ghost btn-small">
                      View details
                    </Link>
                  </div>
                )}
              </article>
            ))}
          </div>
        )}
      </section>

      {/* Confirmation Dialog for Approval */}
      {pendingAction?.type === "approve" && (
        <ConfirmDialog
          title="Approve blood request?"
          confirmLabel={submitting ? "Approving..." : "Confirm approval"}
          onCancel={() => !submitting && setPendingAction(null)}
          onConfirm={() => handleApprove(pendingAction.request)}
        >
          <p>
            You are approving request <strong>{pendingAction.request.id}</strong> for{" "}
            <strong>{pendingAction.request.patient_name}</strong> ({pendingAction.request.units_required} units of{" "}
            {pendingAction.request.patient_blood_group} {pendingAction.request.component}).
          </p>
          <div className="notice-box">
            <strong>Important note on approval:</strong>
            <br />
            Approving indicates that your blood bank agrees to coordinate and handle this request.
            Approval does <em>not</em> reserve stock, decrement inventory, or mark the request fulfilled.
          </div>
        </ConfirmDialog>
      )}

      {/* Dialog for Rejection with Required Reason */}
      {pendingAction?.type === "reject" && (
        <dialog open className="dialog">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleReject(pendingAction.request);
            }}
          >
            <h2>Reject blood request</h2>
            <p>
              Rejecting request <strong>{pendingAction.request.id}</strong> for{" "}
              <strong>{pendingAction.request.patient_name}</strong>.
            </p>

            {rejectError && (
              <Alert tone="error" title="Rejection error">
                {rejectError}
              </Alert>
            )}

            <div className="field">
              <label htmlFor="rejection-reason-text">
                Reason for rejection <span className="req">(required, 5 to 300 characters)</span>
              </label>
              <textarea
                id="rejection-reason-text"
                rows={3}
                placeholder="Explain why this request cannot be approved (e.g. required component currently reserved for trauma emergency)..."
                value={rejectReason}
                onChange={(e) => {
                  setRejectReason(e.target.value);
                  if (rejectError) setRejectError(null);
                }}
                disabled={submitting}
                maxLength={300}
                required
              />
              <div style={{ display: "flex", justifyContent: "space-between", marginTop: "0.25rem" }}>
                <span className="hint">The requester will see this reason in their request overview.</span>
                <span className={`small ${rejectReason.trim().length < 5 || rejectReason.trim().length > 300 ? "muted" : "muted"}`}>
                  {rejectReason.trim().length} / 300
                </span>
              </div>
            </div>

            <div className="dialog-actions">
              <button
                type="button"
                className="btn btn-secondary"
                disabled={submitting}
                onClick={() => setPendingAction(null)}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={submitting || rejectReason.trim().length < 5 || rejectReason.trim().length > 300}
              >
                {submitting ? "Rejecting..." : "Confirm rejection"}
              </button>
            </div>
          </form>
        </dialog>
      )}
    </>
  );
}
