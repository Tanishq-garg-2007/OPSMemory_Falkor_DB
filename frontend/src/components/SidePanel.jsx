import { useEffect, useState } from "react";
import { getAgentHandoffs, getTopology, getEntityTimeline } from "../api.js";

export default function SidePanel({
  tab,
  onTab,
  tasks,
  tasksError,
  onRefreshTasks,
  inspector,
  onLoadMemories,
  onOpenGraph,
  tenantKey,
  conversationId,
  latestHandoffs,
}) {
  // Agents tab state
  const [handoffs, setHandoffs] = useState(latestHandoffs || []);
  const [handoffsLoading, setHandoffsLoading] = useState(false);

  // Timeline tab state
  const [entities, setEntities] = useState([]);
  const [selectedEntity, setSelectedEntity] = useState(null);
  const [timeline, setTimeline] = useState([]);
  const [timelineLoading, setTimelineLoading] = useState(false);

  // Sync latestHandoffs prop
  useEffect(() => {
    if (latestHandoffs && latestHandoffs.length > 0) {
      setHandoffs(latestHandoffs);
    }
  }, [latestHandoffs]);

  // Load handoffs on tab switch or refresh
  const loadHandoffs = async () => {
    setHandoffsLoading(true);
    try {
      const data = await getAgentHandoffs(tenantKey, conversationId, 10);
      setHandoffs(data || []);
    } catch {
      // Keep existing handoffs on failure
    } finally {
      setHandoffsLoading(false);
    }
  };

  useEffect(() => {
    if (tab === "agents" && (!handoffs || handoffs.length === 0)) {
      loadHandoffs();
    }
  }, [tab, tenantKey, conversationId]);

  // Load entities for timeline dropdown
  useEffect(() => {
    let cancelled = false;
    getTopology(tenantKey)
      .then((topo) => {
        if (cancelled) return;
        const ents = (topo.nodes || []).filter((n) => n.type === "Entity");
        setEntities(ents);
        if (ents.length > 0) {
          const defaultEnt = ents.find((e) => (e.label || "").toLowerCase() === "payments-api") || ents[0];
          setSelectedEntity((prev) => (ents.some((e) => e.id === prev) ? prev : defaultEnt.id));
        } else {
          setSelectedEntity(null);
        }
      })
      .catch(() => {
        if (!cancelled) setEntities([]);
      });
    return () => { cancelled = true; };
  }, [tenantKey, tab]);

  // Load timeline for selected entity
  useEffect(() => {
    if (!selectedEntity) {
      setTimeline([]);
      return;
    }
    let cancelled = false;
    setTimelineLoading(true);
    getEntityTimeline(tenantKey, selectedEntity)
      .then((data) => {
        if (!cancelled) setTimeline(data || []);
      })
      .catch(() => {
        if (!cancelled) setTimeline([]);
      })
      .finally(() => {
        if (!cancelled) setTimelineLoading(false);
      });
    return () => { cancelled = true; };
  }, [tenantKey, selectedEntity]);

  // Derive latest turn relay
  const latestTurnId = handoffs[0]?.turn_id;
  const turnHandoffs = latestTurnId ? handoffs.filter((h) => h.turn_id === latestTurnId) : handoffs.slice(0, 2);

  const triageHandoff = turnHandoffs.find((h) => h.from_agent === "agent_triage");
  const resolverHandoff = turnHandoffs.find((h) => h.to_agent === "agent_curator" || h.from_agent === "agent_resolver");

  const triageTask = triageHandoff?.shared_state?.triage_task || triageHandoff?.task_id || "triage_message";
  const resolverTask = triageHandoff?.task_id || resolverHandoff?.shared_state?.resolve_task || "resolve_query";
  const curatorTask = resolverHandoff?.task_id || "curate_memories";

  const hasHandoffs = turnHandoffs.length > 0;

  return (
    <section className="panel tasks-graph-panel">
      <div className="panel-header tabs-header">
        <button
          className={`tab-btn ${tab === "tasks" ? "active" : ""}`}
          onClick={() => onTab("tasks")}
          data-tooltip="Task Board: Tasks dispatched to workers with atomic Cypher mutual-exclusion leases."
          data-tooltip-pos="bottom"
        >
          Task Board
        </button>
        <button
          className={`tab-btn ${tab === "agents" ? "active" : ""}`}
          onClick={() => onTab("agents")}
          data-tooltip="Agent Relay: Real-time multi-agent handoffs (Triage &rarr; Resolver &rarr; Curator) with reasons and task IDs."
          data-tooltip-pos="bottom"
        >
          Agents
        </button>
        <button
          className={`tab-btn ${tab === "timeline" ? "active" : ""}`}
          onClick={() => onTab("timeline")}
          data-tooltip="Entity Timeline: Chronological audit trail showing memory validity, version bumps, and supersessions."
          data-tooltip-pos="bottom"
        >
          Timeline
        </button>
        <button
          className={`tab-btn ${tab === "graph" ? "active" : ""}`}
          onClick={() => onTab("graph")}
          data-tooltip="Memory Inspector: Raw JSON dump of all nodes, edges, and validity ranges in FalkorDB."
          data-tooltip-pos="bottom"
        >
          Memory Inspector
        </button>
      </div>

      {/* Task Board Tab */}
      <div className={`tab-content ${tab === "tasks" ? "active" : ""}`}>
        <div className="task-controls">
          <button className="btn btn-secondary btn-sm" onClick={onRefreshTasks} data-tooltip="Refresh Tasks: Re-queries FalkorDB to sync active task leases." data-tooltip-pos="bottom">Refresh Tasks</button>
        </div>
        <div className="tasks-list">
          {tasksError && <div className="empty-state">Error loading tasks: {tasksError}</div>}
          {!tasksError && tasks.length === 0 && <div className="page-note">No open tasks</div>}
          {!tasksError && tasks.map((t) => (
            <div key={t.id} className={`task-card ${t.status}`}>
              <div className="task-head">
                <strong>{t.task_type}</strong>
                <span className="badge">{t.status}</span>
              </div>
              <div className="task-sub">ID: <code>{t.id}</code></div>
              <div className="task-sub">Lease Owner: {t.lease_owner || "None"}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Agents Tab */}
      <div className={`tab-content ${tab === "agents" ? "active" : ""}`}>
        <div className="task-controls">
          <button className="btn btn-secondary btn-sm" onClick={loadHandoffs}>
            {handoffsLoading ? "Loading…" : "Refresh Handoffs"}
          </button>
        </div>
        <div className="agents-view">
          {!hasHandoffs ? (
            <div className="page-note">No handoffs recorded for this turn.</div>
          ) : (
            <div className="agent-relay">
              <div className="agent-card">
                <div className="agent-badge">Step 1</div>
                <strong className="agent-name">Triage</strong>
                <div className="task-sub">Task: <code>{triageTask}</code></div>
              </div>

              <div className="relay-arrow" aria-hidden="true">→</div>

              <div className="agent-card">
                <div className="agent-badge">Step 2</div>
                <strong className="agent-name">Resolver</strong>
                <div className="task-sub">Task: <code>{resolverTask}</code></div>
              </div>

              <div className="relay-arrow" aria-hidden="true">→</div>

              <div className="agent-card">
                <div className="agent-badge">Step 3</div>
                <strong className="agent-name">Curator</strong>
                <div className="task-sub">Task: <code>{curatorTask}</code></div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Timeline Tab */}
      <div className={`tab-content ${tab === "timeline" ? "active" : ""}`}>
        <div className="task-controls timeline-controls">
          <label className="tenant-label" htmlFor="timeline-entity-select">Entity:</label>
          <select
            id="timeline-entity-select"
            className="tenant-select"
            value={selectedEntity || ""}
            onChange={(e) => setSelectedEntity(e.target.value)}
          >
            {entities.map((e) => (
              <option key={e.id} value={e.id}>{e.label || e.name || e.id}</option>
            ))}
          </select>
        </div>
        <div className="tasks-list">
          {timelineLoading && <div className="page-note">Loading…</div>}
          {!timelineLoading && timeline.length === 0 && (
            <div className="page-note">No memories about this entity yet.</div>
          )}
          {!timelineLoading && timeline.map((m) => (
            <div key={m.id} className={`task-card ${m.status}`}>
              <div className="task-head">
                <strong>{m.title}</strong>
                <span className="badge">{m.status}</span>
              </div>
              <div className={`timeline-summary ${m.status === "superseded" ? "superseded" : ""}`}>
                {m.summary}
              </div>
              <div className="task-sub">
                Valid: {m.valid_from ? m.valid_from.split("T")[0] : ""} {m.valid_to ? `to ${m.valid_to.split("T")[0]}` : "(current)"}
              </div>
              {m.superseded_by && (
                <div className="timeline-arrow">
↳ Superseded by: <code>{m.superseded_by}</code>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Memory Inspector Tab */}
      <div className={`tab-content ${tab === "graph" ? "active" : ""}`}>
        <div className="inspector-controls">
          <button className="btn btn-secondary btn-sm" onClick={onLoadMemories} data-tooltip="Load All Memories: Fetches complete inventory of episodic, semantic, and procedural graph nodes." data-tooltip-pos="top">Load All Memories</button>
          <button className="btn btn-primary btn-sm" onClick={onOpenGraph} data-tooltip="Launch Graph View: Expands full-screen interactive 2D FalkorDB graph visualizer." data-tooltip-pos="top">Open Graph View</button>
        </div>
        <pre className="memory-inspector">{inspector}</pre>
      </div>
    </section>
  );
}
