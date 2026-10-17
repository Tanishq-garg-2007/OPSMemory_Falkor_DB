import { useEffect, useState, useCallback } from "react";
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

  // Sync latestHandoffs prop cleanly (handle empty array resets on new chat)
  useEffect(() => {
    setHandoffs(latestHandoffs || []);
  }, [latestHandoffs]);

  // Load handoffs on tab switch or manual refresh
  const loadHandoffs = useCallback(async () => {
    setHandoffsLoading(true);
    try {
      const data = await getAgentHandoffs(tenantKey, conversationId || undefined, 15);
      setHandoffs(data || []);
    } catch {
      // Keep existing handoffs on failure
    } finally {
      setHandoffsLoading(false);
    }
  }, [tenantKey, conversationId]);

  useEffect(() => {
    if (tab === "agents" && (!handoffs || handoffs.length === 0)) {
      loadHandoffs();
    }
  }, [tab, loadHandoffs, handoffs]);

  // Load entities for timeline dropdown dynamically from live graph topology
  const loadEntities = useCallback(() => {
    getTopology(tenantKey)
      .then((topo) => {
        const ents = (topo.nodes || []).filter((n) => n.type === "Entity");
        setEntities(ents);
        if (ents.length > 0) {
          setSelectedEntity((prev) => (ents.some((e) => e.id === prev) ? prev : ents[0].id));
        } else {
          setSelectedEntity(null);
        }
      })
      .catch(() => {
        setEntities([]);
      });
  }, [tenantKey]);

  useEffect(() => {
    loadEntities();
  }, [tenantKey, tab, loadEntities]);

  // Re-fetch entities when new tasks appear (indicates a new memory or entity was learned)
  useEffect(() => {
    if (tasks && tasks.length > 0) {
      loadEntities();
    }
  }, [tasks, loadEntities]);

  // Load timeline for selected entity dynamically
  const loadTimeline = useCallback(() => {
    if (!selectedEntity) {
      setTimeline([]);
      return;
    }
    setTimelineLoading(true);
    getEntityTimeline(tenantKey, selectedEntity)
      .then((data) => {
        setTimeline(data || []);
      })
      .catch(() => {
        setTimeline([]);
      })
      .finally(() => {
        setTimelineLoading(false);
      });
  }, [tenantKey, selectedEntity]);

  useEffect(() => {
    loadTimeline();
  }, [loadTimeline]);

  // Derive latest turn relay from live handoff records
  const latestTurnId = handoffs[0]?.turn_id;
  const turnHandoffs = latestTurnId ? handoffs.filter((h) => h.turn_id === latestTurnId) : handoffs.slice(0, 3);

  const triageHandoff = turnHandoffs.find((h) => h.from_agent === "agent_triage");
  const resolverHandoff = turnHandoffs.find((h) => h.to_agent === "agent_curator" || h.from_agent === "agent_resolver");

  const triageTask = triageHandoff?.shared_state?.triage_task || triageHandoff?.task_id || "Active Triage";
  const triageReason = triageHandoff?.reason ? triageHandoff.reason.replace(/_/g, " ") : "triage message";

  const resolverTask = triageHandoff?.task_id || resolverHandoff?.shared_state?.resolve_task || "Active Resolution";
  const resolverReason = triageHandoff?.reason ? triageHandoff.reason.replace(/_/g, " ") : "execute resolution";

  const curatorTask = resolverHandoff?.task_id || resolverHandoff?.shared_state?.task_id || "Active Curation";
  const curatorReason = resolverHandoff?.reason ? resolverHandoff.reason.replace(/_/g, " ") : "curate memory";

  const hasHandoffs = turnHandoffs.length > 0;

  // Helper to parse task payload safely
  const parsePayload = (task) => {
    if (!task.payload_json) return null;
    try {
      return typeof task.payload_json === "string" ? JSON.parse(task.payload_json) : task.payload_json;
    } catch {
      return null;
    }
  };

  return (
    <section className="panel tasks-graph-panel">
      <div className="panel-header tabs-header">
        <button
          className={`tab-btn ${tab === "tasks" ? "active" : ""}`}
          onClick={() => onTab("tasks")}
          data-tooltip="Task Board: Tasks dispatched to workers with atomic Cypher mutual-exclusion leases."
          data-tooltip-pos="bottom"
        >
          Task Board ({tasks?.length || 0})
        </button>
        <button
          className={`tab-btn ${tab === "agents" ? "active" : ""}`}
          onClick={() => onTab("agents")}
          data-tooltip="Agent Relay: Real-time multi-agent handoffs (Triage &rarr; Resolver &rarr; Curator) with reasons and task IDs."
          data-tooltip-pos="bottom"
        >
          Agents {handoffs.length > 0 ? `(${handoffs.length})` : ""}
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
          {!tasksError && (!tasks || tasks.length === 0) && <div className="page-note">No open tasks in FalkorDB for this tenant.</div>}
          {!tasksError && tasks && tasks.map((t) => {
            const payload = parsePayload(t);
            return (
              <div key={t.id} className={`task-card ${t.status}`}>
                <div className="task-head">
                  <strong>{t.task_type}</strong>
                  <span className={`badge ${t.status}`}>{t.status}</span>
                </div>
                {payload?.title && <div className="task-title-sub"><strong>Title:</strong> {payload.title}</div>}
                {payload?.summary && <div className="task-desc-sub">{payload.summary}</div>}
                <div className="task-sub">ID: <code>{t.id}</code></div>
                <div className="task-sub">Lease Owner: <strong>{t.lease_owner || "Unassigned"}</strong></div>
                {t.created_at && (
                  <div className="task-sub">Created: {t.created_at.split(".")[0].replace("T", " ")}</div>
                )}
              </div>
            );
          })}
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
            <div className="page-note">No handoffs recorded yet. Send a message to see the Triage &rarr; Resolver &rarr; Curator handoff flow.</div>
          ) : (
            <>
              <div className="agent-relay">
                <div className="agent-card">
                  <div className="agent-badge">Step 1: Extract & Triage</div>
                  <strong className="agent-name">Triage Agent</strong>
                  <div className="task-sub">Action: <strong>{triageReason}</strong></div>
                  <div className="task-sub">Task: <code>{triageTask}</code></div>
                </div>

                <div className="relay-arrow" aria-hidden="true">&darr;</div>

                <div className="agent-card">
                  <div className="agent-badge">Step 2: Resolve & Synthesize</div>
                  <strong className="agent-name">Resolver Agent</strong>
                  <div className="task-sub">Action: <strong>{resolverReason}</strong></div>
                  <div className="task-sub">Task: <code>{resolverTask}</code></div>
                </div>

                <div className="relay-arrow" aria-hidden="true">&darr;</div>

                <div className="agent-card">
                  <div className="agent-badge">Step 3: Graph Curation</div>
                  <strong className="agent-name">Curator Agent</strong>
                  <div className="task-sub">Action: <strong>{curatorReason}</strong></div>
                  <div className="task-sub">Task: <code>{curatorTask}</code></div>
                </div>
              </div>

              {handoffs.length > 0 && (
                <div className="handoffs-history">
                  <div className="handoffs-history-title">Recent Handoff Audit Trail</div>
                  {handoffs.slice(0, 6).map((h, idx) => (
                    <div key={`${h.task_id}-${idx}`} className="handoff-history-item">
                      <div className="handoff-history-agents">
                        <code>{h.from_agent.replace("agent_", "")}</code> &rarr; <code>{h.to_agent.replace("agent_", "")}</code>
                      </div>
                      <div className="handoff-history-reason">Reason: <strong>{h.reason}</strong></div>
                      <div className="handoff-history-task">Task: <code>{h.task_id}</code></div>
                    </div>
                  ))}
                </div>
              )}
            </>
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
          <button className="btn btn-secondary btn-sm" onClick={() => { loadEntities(); loadTimeline(); }} style={{ marginLeft: "auto" }}>
            Refresh
          </button>
        </div>
        <div className="tasks-list">
          {timelineLoading && <div className="page-note">Loading timeline…</div>}
          {!timelineLoading && timeline.length === 0 && (
            <div className="page-note">No memories linked to this entity in the FalkorDB graph.</div>
          )}
          {!timelineLoading && timeline.map((m) => (
            <div key={m.id} className={`task-card ${m.status}`}>
              <div className="task-head">
                <strong>{m.title}</strong>
                <span className={`badge ${m.status}`}>{m.status}</span>
              </div>
              <div className={`timeline-summary ${m.status === "superseded" ? "superseded" : ""}`}>
                {m.summary}
              </div>
              <div className="task-sub">
                Validity: <strong>{m.valid_from ? m.valid_from.split("T")[0] : ""} {m.valid_to ? `to ${m.valid_to.split("T")[0]}` : "(currently active)"}</strong>
              </div>
              {m.superseded_by && (
                <div className="timeline-arrow">
                  &crarr; Superseded by: <code>{m.superseded_by}</code>
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
