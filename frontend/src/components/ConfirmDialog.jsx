import { useEffect, useRef, useState } from "react";

// Native <dialog>: focus is trapped, Escape cancels, and it works with the keyboard out of the box.
export default function ConfirmDialog({
  open, title, children, confirmLabel = "Confirm", cancelLabel = "Cancel", onConfirm, onCancel, busy,
  askReason, requireReason, reasonLabel = "Reason", reasonMinLength = 5, requireAck, ackLabel,
}) {
  const ref = useRef(null);
  const [reason, setReason] = useState("");
  const [ack, setAck] = useState(false);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      setReason("");
      setAck(false);
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  const reasonOk = !requireReason || reason.trim().length >= reasonMinLength;
  const ackOk = !requireAck || ack;

  return (
    <dialog
      ref={ref}
      className="dialog"
      aria-labelledby="dialog-title"
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) onCancel();
      }}
    >
      <h2 id="dialog-title">{title}</h2>
      <div className="dialog-body">{children}</div>
      {(askReason || requireReason) && (
        <div className="field">
          <label htmlFor="dialog-reason">
            {reasonLabel}
            {requireReason ? ` (required, at least ${reasonMinLength} characters)` : " (optional)"}
          </label>
          <textarea id="dialog-reason" rows={3} maxLength={250} value={reason} onChange={(e) => setReason(e.target.value)} />
        </div>
      )}
      {requireAck && (
        <label className="check">
          <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
          <span>{ackLabel}</span>
        </label>
      )}
      <div className="dialog-actions">
        <button type="button" className="btn btn-secondary" onClick={onCancel} disabled={busy}>
          {cancelLabel}
        </button>
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy || !reasonOk || !ackOk}
          onClick={() => onConfirm({ reason: reason.trim(), acknowledged: ack })}
        >
          {busy ? "Working..." : confirmLabel}
        </button>
      </div>
    </dialog>
  );
}
