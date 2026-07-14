export function PageHeader({ kicker, title, description, actions }) {
  return (
    <section className="page-header">
      <div>
        {kicker ? <p className="page-kicker">{kicker}</p> : null}
        <h2>{title}</h2>
        {description ? <p className="page-description">{description}</p> : null}
      </div>
      {actions ? <div className="inline-actions">{actions}</div> : null}
    </section>
  );
}

