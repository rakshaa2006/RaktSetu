// Persistent visible label + optional hint + accessible error message.
export default function Field({ id, label, hint, error, required, children }) {
  return (
    <div className={`field${error ? " field-invalid" : ""}`}>
      <label htmlFor={id}>
        {label}
        {required && <span className="req"> (required)</span>}
      </label>
      {hint && (
        <p id={`${id}-hint`} className="hint">
          {hint}
        </p>
      )}
      {children}
      {error && (
        <p id={`${id}-error`} className="field-error" role="alert">
          <span aria-hidden="true">✖ </span>
          {error}
        </p>
      )}
    </div>
  );
}

export function describedBy(id, hint, error) {
  const parts = [];
  if (hint) parts.push(`${id}-hint`);
  if (error) parts.push(`${id}-error`);
  return parts.length ? parts.join(" ") : undefined;
}
