const TITLES = { info: "Note", success: "Done", warning: "Please check", error: "Something went wrong" };

export default function Alert({ tone = "info", title, children, onDismiss }) {
  return (
    <div className={`alert alert-${tone}`} role={tone === "error" ? "alert" : "status"}>
      <div>
        <strong>{title || TITLES[tone]}</strong>
        {children && <div className="alert-body">{children}</div>}
      </div>
      {onDismiss && (
        <button type="button" className="btn btn-ghost" onClick={onDismiss} aria-label="Dismiss message">
          Dismiss
        </button>
      )}
    </div>
  );
}
