export function MiniBarChart({ items }) {
  const max = Math.max(...items.map((item) => item.value), 1);

  return (
    <div className="mini-chart">
      {items.map((item) => (
        <div key={item.label} className="mini-chart-row">
          <div className="mini-chart-labels">
            <strong>{item.label}</strong>
            <span>{item.caption}</span>
          </div>
          <div className="mini-chart-track">
            <div
              className="mini-chart-bar"
              style={{ width: `${(item.value / max) * 100}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

