export default function EvidencePanel({ evidence, onSelect, onShowInGraph }) {
  const count = evidence?.length ?? 0;
  return (
    <section className="panel evidence-panel" aria-labelledby="evidence-heading">
      <div className="panel-header">
        <h2 id="evidence-heading">Retrieved Evidence & Citations</h2>
        <span className="badge">{count} records</span>
      </div>
      <div className="evidence-list">
        {evidence === null && (
          <div className="empty-state">No query yet. Ask a question to see the memories behind the answer.</div>
        )}
        {evidence !== null && count === 0 && (
          <div className="empty-state">No evidence retrieved for this query.</div>
        )}
        {evidence?.map((item) => (
          <div key={item.memory_id} className={`evidence-card ${item.status}`} onClick={() => onSelect(item)}>
            <div className="evidence-title">{item.title}</div>
            <div className="evidence-summary">{item.summary}</div>
            <div className="evidence-foot">
              <div className="evidence-meta">
                <code>{item.memory_id}</code>
                <span>Conf: {Math.round(item.confidence * 100)}% | Score: {item.score}</span>
              </div>
              <div>
                Valid: {item.valid_from} {item.valid_to ? `to ${item.valid_to}` : "(active current)"} | Status: {item.status}
              </div>
            </div>
            <div className="evidence-actions">
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={(e) => { e.stopPropagation(); onShowInGraph(item); }}
                data-tooltip="Show in Graph: Focuses and highlights this memory node and its relationships in the 2D graph."
                data-tooltip-pos="top"
              >
                Show in graph
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}