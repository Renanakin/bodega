export function ActivityFeed({ items }) {
  return (
    <div className="activity-feed">
      {items.map((item) => (
        <article key={item.id} className="activity-item">
          <div className={`activity-dot activity-dot-${item.tone}`} />
          <div>
            <strong>{item.title}</strong>
            <p>{item.detail}</p>
            <span>{item.time}</span>
          </div>
        </article>
      ))}
    </div>
  );
}

