import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { forceSimulation, forceLink, forceManyBody, forceCenter, forceCollide } from "d3-force";
import { getTopology } from "../api.js";

const W = 900;
const H = 600;
// Hidden at first to keep the picture readable. Click a legend chip to show them.
const START_HIDDEN = ["Conversation", "Turn", "Session"];
// Space kept free at the edges so labels are never cut off
const PAD_X = 95;
const PAD_TOP = 45;
const PAD_BOTTOM = 65;

function shorten(text, max = 20) {
  const s = String(text ?? "");
  return s.length > max ? s.slice(0, max - 1) + "…" : s;
}

// After layout, d3 swaps link endpoints for node objects. This reads the id either way.
function idOf(v) {
  return typeof v === "object" && v !== null ? v.id : v;
}

export default function GraphView({ tenantKey, focusId = null, onClose }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [layout, setLayout] = useState({ nodes: [], links: [] });
  const [selected, setSelected] = useState(null);
  const [showJson, setShowJson] = useState(false);
  const [hiddenTypes, setHiddenTypes] = useState(() => new Set(START_HIDDEN));

  // Close with the Escape key
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Load nodes and links from the backend
  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError(null);
    setSelected(null);
    getTopology(tenantKey)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) setError(e.message); });
    return () => { cancelled = true; };
  }, [tenantKey]);

  // Opened from an evidence card: select that memory and make sure its type is visible
  useEffect(() => {
    if (!data || !focusId) return;
    const node = data.nodes.find((n) => n.id === focusId);
    if (!node) return;
    setSelected(node);
    setHiddenTypes((prev) => {
      if (!prev.has(node.type)) return prev;
      const next = new Set(prev);
      next.delete(node.type);
      return next;
    });
  }, [data, focusId]);

  // Place the visible nodes, keeping them inside the padded area
  useEffect(() => {
    if (!data) return;
    const nodes = data.nodes.filter((n) => !hiddenTypes.has(n.type)).map((n) => ({ ...n }));
    if (nodes.length === 0) {
      setLayout({ nodes: [], links: [] });
      return;
    }
    const ids = new Set(nodes.map((n) => n.id));
    const links = data.links
      .filter((l) => ids.has(l.source) && ids.has(l.target))
      .map((l) => ({ ...l }));

    const sim = forceSimulation(nodes)
      .force("link", forceLink(links).id((d) => d.id).distance(95).strength(0.5))
      .force("charge", forceManyBody().strength(-320))
      .force("center", forceCenter(W / 2, H / 2))
      .force("collide", forceCollide(34))
      .on("tick", () => {
        for (const n of nodes) {
          n.x = Math.max(PAD_X, Math.min(W - PAD_X, n.x));
          n.y = Math.max(PAD_TOP, Math.min(H - PAD_BOTTOM, n.y));
        }
        setLayout({ nodes: [...nodes], links: [...links] });
      });

    return () => sim.stop();
  }, [data, hiddenTypes]);

  // Nodes directly connected to the selected node, used to dim everything else
  const neighbors = useMemo(() => {
    if (!data || !selected) return null;
    const ids = new Set([selected.id]);
    for (const l of data.links) {
      if (l.source === selected.id) ids.add(l.target);
      if (l.target === selected.id) ids.add(l.source);
    }
    return ids;
  }, [data, selected]);

  const toggleType = (type) => {
    setHiddenTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
    setSelected((s) => (s && s.type === type ? null : s));
  };

  const types = data ? [...new Set(data.nodes.map((n) => n.type))] : [];
  const visibleCount = data ? data.nodes.filter((n) => !hiddenTypes.has(n.type)).length : 0;
  const byId = new Map((data?.nodes ?? []).map((n) => [n.id, n]));
  const selectedLinks = selected && data
    ? data.links.filter((l) => l.source === selected.id || l.target === selected.id)
    : [];

  let body;
  if (error) {
    body = <div className="empty-state">Could not load the graph: {error}</div>;
  } else if (!data) {
    body = <div className="empty-state">Loading graph...</div>;
  } else if (data.nodes.length === 0) {
    body = <div className="empty-state">No nodes yet. Use Seed Fixtures in the Admin menu first.</div>;
  } else if (showJson) {
    body = <pre className="graph-json">{JSON.stringify(data, null, 2)}</pre>;
  } else if (visibleCount === 0) {
    body = <div className="empty-state">Every type is hidden. Click a legend item to show one.</div>;
  } else {
    body = (
      <div className="graph-canvas">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="graph-svg"
          role="img"
          aria-label="Memory graph"
          onClick={() => setSelected(null)}
        >
          <defs>
            <marker id="graph-arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto">
              <path d="M0,0 L10,5 L0,10 z" className="arrow-head" />
            </marker>
          </defs>
          {layout.links.map((l, i) => {
            const linkDim = selected && idOf(l.source) !== selected.id && idOf(l.target) !== selected.id;
            return (
              <line
                key={i}
                className={`graph-link link-${l.type} ${linkDim ? "dim" : ""}`}
                markerEnd={l.type === "DEPENDS_ON" || l.type === "SUPERSEDES" ? "url(#graph-arrow)" : undefined}
                x1={l.source.x} y1={l.source.y}
                x2={l.target.x} y2={l.target.y}
              />
            );
          })}
          {layout.nodes.map((n) => {
            const dim = neighbors && !neighbors.has(n.id);
            const cls = [
              "graph-node",
              n.status === "superseded" ? "is-old" : "",
              dim ? "dim" : "",
              selected && selected.id === n.id ? "is-selected" : "",
            ].filter(Boolean).join(" ");
            return (
              <g
                key={n.id}
                className={cls}
                transform={`translate(${n.x},${n.y})`}
                onClick={(e) => { e.stopPropagation(); setSelected(n); }}
              >
                <circle r={n.type === "Entity" ? 12 : 8} className={`node-${n.type}`} />
                <text y={n.type === "Entity" ? 26 : 21} textAnchor="middle">{shorten(n.label)}</text>
              </g>
            );
          })}
        </svg>
      </div>
    );
  }

  return createPortal(
    <div className="graph-backdrop" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="graph-modal" role="dialog" aria-modal="true" aria-label="Memory graph">
        <div className="graph-head">
          <div className="graph-title">
            <h2>Memory Graph</h2>
            {data && (
              <span className="badge">
                {data.nodes.length} nodes • {data.links.length} links{data.truncated ? " • truncated" : ""}
              </span>
            )}
          </div>
          <div className="graph-actions">
            {data && data.nodes.length > 0 && (
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => setShowJson((v) => !v)}
                data-tooltip="Toggle View: Switch between interactive 2D Force-Directed Graph and raw JSON topology payload."
                data-tooltip-pos="bottom"
              >
                {showJson ? "Show graph" : "Show JSON"}
              </button>
            )}
            <button className="btn btn-secondary btn-sm" onClick={onClose} data-tooltip="Close Graph: Return to the conversation and evidence dashboard." data-tooltip-pos="bottom">Close</button>
          </div>
        </div>

        <div className="graph-body">
          <div className="graph-main">
            {body}
            {data && data.nodes.length > 0 && !showJson && (
              <div className="graph-legend">
                {types.map((t) => {
                  const off = hiddenTypes.has(t);
                  return (
                    <button
                      key={t}
                      type="button"
                      className={`legend-item ${off ? "off" : ""}`}
                      aria-pressed={!off}
                      onClick={() => toggleType(t)}
                      data-tooltip={`Toggle visibility of ${t} nodes in the graph.`}
                      data-tooltip-pos="top"
                    >
                      <span className={`legend-dot node-${t}`} />
                      {t}
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          <aside className="graph-detail">
            {!selected && <p>Click a node to see its details.</p>}
            {selected && (
              <>
                <strong className="detail-title">{selected.label}</strong>
                <div className="task-sub">Type: {selected.type}</div>
                <div className="task-sub">Status: {selected.status}</div>
                <div className="task-sub">ID: <code>{selected.id}</code></div>
                <div className="graph-rels">
                  {selectedLinks.map((l, i) => {
                    const outgoing = l.source === selected.id;
                    const otherId = outgoing ? l.target : l.source;
                    const other = byId.get(otherId);
                    return (
                      <div key={i}>
                        {outgoing ? "→" : "←"} {l.type} {other ? shorten(other.label, 30) : otherId}
                      </div>
                    );
                  })}
                </div>
              </>
            )}
          </aside>
        </div>
      </div>
    </div>,
    document.body
  );
}
