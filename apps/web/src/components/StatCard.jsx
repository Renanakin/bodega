export function StatCard({ title, value, helper, tone = "default" }) {
  return (
    <article className={`stat-card stat-card-${tone}`}>
      <p className="stat-title">{title}</p>
      <strong className="stat-value">{value}</strong>
      <p className="stat-helper">{helper}</p>
    </article>
  );
}

