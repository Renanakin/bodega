export function KpiStrip({ items }) {
  return (
    <div className="kpi-strip">
      {items.map((item) => (
        <article key={item.label} className="kpi-item">
          <span>{item.label}</span>
          <strong>{item.value}</strong>
        </article>
      ))}
    </div>
  );
}

