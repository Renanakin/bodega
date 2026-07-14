export function FormField({ label, error, hint, children, required = false }) {
  return (
    <label className="form-field">
      <span className="form-label">
        {label}
        {required ? <em>*</em> : null}
      </span>
      {children}
      {error ? <small className="form-error">{error}</small> : null}
      {!error && hint ? <small className="form-hint">{hint}</small> : null}
    </label>
  );
}

