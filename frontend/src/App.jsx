import { useCallback, useEffect, useRef, useState } from "react";
import Header from "./components/Header.jsx";
import Hero from "./components/Hero.jsx";
import ChatPanel from "./components/ChatPanel.jsx";
import EvidencePanel from "./components/EvidencePanel.jsx";
import SidePanel from "./components/SidePanel.jsx";
import GraphView from "./components/GraphView.jsx";
import Guide from "./components/Guide.jsx";
import GlobalTooltip from "./components/GlobalTooltip.jsx";
import { TENANTS, getHealth, sendChat, getTasks, getMemories, seedTenant, resetTenant, getConversationTurns } from "./api.js";
import { useTheme } from "./hooks.js";

const INSPECTOR_HINT = 'Select a memory or click "Load All Memories" to inspect the graph JSON.';

/** localStorage key for a given tenant's active conversation ID. */
function convStorageKey(tenantId) {
  return `opsmemory-conversation-${tenantId}`;
}

export default function App() {
  const [theme, toggleTheme] = useTheme();
  const [tenantKey, setTenantKey] = useState(TENANTS[0].key);
  const [health, setHealth] = useState({ ok: false, text: "Checking..." });
  const [messages, setMessages] = useState([]);
  const [evidence, setEvidence] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [tasksError, setTasksError] = useState(null);
  const [tab, setTab] = useState("tasks");
  const [inspector, setInspector] = useState(INSPECTOR_HINT);
  const [boardOpen, setBoardOpen] = useState(false);
  const [graphOpen, setGraphOpen] = useState(false);
  const [guideOpen, setGuideOpen] = useState(false);
  const [graphFocus, setGraphFocus] = useState(null);
  const [conversationId, setConversationId] = useState(null);
  const [latestHandoffs, setLatestHandoffs] = useState([]);
  const nextId = useRef(1);

  const tenantId = TENANTS.find((t) => t.key === tenantKey).id;

  /** Persist the active conversation ID for this tenant. */
  const persistConvId = useCallback((tenantId, id) => {
    const key = convStorageKey(tenantId);
    if (id) localStorage.setItem(key, id);
    else localStorage.removeItem(key);
  }, []);

  const checkHealth = useCallback(async () => {
    try {
      const data = await getHealth();
      if (data.status === "ok") setHealth({ ok: true, text: `${data.database.mode} (healthy)` });
      else setHealth({ ok: false, text: "Degraded (Persistence Offline)" });
    } catch {
      setHealth({ ok: false, text: "Offline" });
    }
  }, []);

  const loadTasks = useCallback(async () => {
    try {
      setTasks((await getTasks(tenantKey)) || []);
      setTasksError(null);
    } catch (e) {
      setTasksError(e.message);
    }
  }, [tenantKey]);

  const loadMemories = useCallback(async () => {
    setInspector("Loading memories from persistent graph...");
    try {
      setInspector(JSON.stringify(await getMemories(tenantKey), null, 2));
    } catch (e) {
      setInspector(`Error loading memories: ${e.message}`);
    }
  }, [tenantKey]);

  /** Restore a conversation from the backend and render its turns. */
  const restoreConversation = useCallback(async (key, tenantId, convId) => {
    try {
      const turns = await getConversationTurns(key, convId);
      if (!turns || turns.length === 0) {
        // Session exists in localStorage but has no turns - clear it
        persistConvId(tenantId, null);
        return;
      }
      const msgs = turns.map((t, i) => ({
        id: i + 1,
        role: t.role,
        text: t.content,
      }));
      nextId.current = turns.length + 1;
      setMessages(msgs);
      setConversationId(convId);
    } catch {
      // Conversation no longer exists server-side - clear the stale key
      persistConvId(tenantId, null);
    }
  }, [persistConvId]);

  useEffect(() => {
    checkHealth();
    const id = setInterval(checkHealth, 15000);
    return () => clearInterval(id);
  }, [checkHealth]);

  useEffect(() => { loadTasks(); }, [loadTasks]);

  // On mount and on tenant switch: restore conversation from localStorage
  useEffect(() => {
    const storedId = localStorage.getItem(convStorageKey(tenantId));
    if (storedId) {
      restoreConversation(tenantKey, tenantId, storedId);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId]);   // intentionally only re-run when tenantId changes

  const handleSend = async (text) => {
    const userId = nextId.current++;
    const botId = nextId.current++;
    setMessages((m) => [...m, { id: userId, role: "user", text }, { id: botId, role: "assistant", pending: true }]);
    const patch = (fields) => setMessages((m) => m.map((x) => (x.id === botId ? { ...x, pending: false, ...fields } : x)));
    try {
      const data = await sendChat(tenantKey, text, conversationId);
      const newConvId = data.conversation_id;
      setConversationId(newConvId);
      persistConvId(tenantId, newConvId);
      patch({ text: data.answer, paths: data.reasoning_paths, citations: data.citations, learned: data.learned });
      setEvidence(data.evidence || []);
      if (data.agent_handoffs) setLatestHandoffs(data.agent_handoffs);
      loadTasks();
    } catch (e) {
      patch({ text: e.message });
    }
  };

  const handleNewConversation = useCallback(() => {
    persistConvId(tenantId, null);
    setConversationId(null);
    setMessages([]);
    setEvidence(null);
    setLatestHandoffs([]);
    nextId.current = 1;
  }, [tenantId, persistConvId]);

  const handleLoadConversation = useCallback(async (convId) => {
    await restoreConversation(tenantKey, tenantId, convId);
    setEvidence(null);
  }, [tenantKey, tenantId, restoreConversation]);

  const handleTenant = (key) => {
    const newTenantId = TENANTS.find((t) => t.key === key).id;
    setTenantKey(key);
    setConversationId(null);
    setMessages([]);
    setEvidence(null);
    setInspector(INSPECTOR_HINT);
    nextId.current = 1;
    // Restore conversation for the new tenant if one was previously stored
    const storedId = localStorage.getItem(convStorageKey(newTenantId));
    if (storedId) {
      restoreConversation(key, newTenantId, storedId);
    }
  };

  const handleSeed = async () => {
    try {
      const data = await seedTenant(tenantId);
      alert(`Seeded ${tenantId}: ${data.stats.memories} memories, ${data.stats.entities} entities, ${data.stats.tasks} tasks.`);
      loadTasks();
      loadMemories();
    } catch (e) {
      alert(`Seeding failed: ${e.message}`);
    }
  };

  const handleReset = async () => {
    if (!confirm(`Reset all persistent graph & memory state for tenant '${tenantId}'?`)) return;
    try {
      const data = await resetTenant(tenantId);
      alert(`Reset ${tenantId}: ${data.deleted_records} records cleared.`);
      handleNewConversation();
      loadTasks();
      loadMemories();
    } catch (e) {
      alert(`Reset failed: ${e.message}`);
    }
  };

  const handleSelectEvidence = (item) => {
    setInspector(JSON.stringify(item, null, 2));
    setTab("graph");
    setBoardOpen(true);
  };

  const handleOpenGraph = () => {
    setGraphFocus(null);
    setGraphOpen(true);
  };

  const handleShowInGraph = (item) => {
    setGraphFocus(item.memory_id);
    setGraphOpen(true);
  };

  const closeGraph = useCallback(() => setGraphOpen(false), []);

  return (
    <>
      <div className="aurora" aria-hidden="true" />
      <div className="app-layout">
        <Header
          tenantKey={tenantKey} onTenant={handleTenant}
          onSeed={handleSeed} onReset={handleReset}
          health={health} theme={theme} onToggleTheme={toggleTheme}
          taskCount={tasks.length}
          onOpenBoard={() => setBoardOpen(true)}
          onOpenGraph={handleOpenGraph}
          onOpenGuide={() => setGuideOpen(true)}
          onNewChat={handleNewConversation}
        />
        <Hero compact={messages.length > 0} />
        <div className="torn" aria-hidden="true" />
        <main className="main-grid">
          <ChatPanel
            messages={messages}
            onSend={handleSend}
            conversationId={conversationId}
            tenantKey={tenantKey}
            onNewConversation={handleNewConversation}
            onLoadConversation={handleLoadConversation}
          />
          <EvidencePanel
            evidence={evidence}
            onSelect={handleSelectEvidence}
            onShowInGraph={handleShowInGraph}
          />
        </main>
      </div>

      {boardOpen && (
        <>
          <div className="drawer-backdrop" onClick={() => setBoardOpen(false)} />
          <aside className="board-drawer" role="dialog" aria-label="Task board and memory inspector">
            <div className="drawer-head">
              <strong>Board</strong>
              <button className="btn btn-secondary btn-sm" onClick={() => setBoardOpen(false)} data-tooltip="Close Drawer: Return to main conversation dashboard." data-tooltip-pos="left">Close</button>
            </div>
            <div className="drawer-body">
              <SidePanel
                tab={tab} onTab={setTab}
                tasks={tasks} tasksError={tasksError} onRefreshTasks={loadTasks}
                inspector={inspector} onLoadMemories={loadMemories}
                onOpenGraph={handleOpenGraph}
                tenantKey={tenantKey} conversationId={conversationId}
                latestHandoffs={latestHandoffs}
              />
            </div>
          </aside>
        </>
      )}

      {graphOpen && (
        <GraphView tenantKey={tenantKey} focusId={graphFocus} onClose={closeGraph} />
      )}

      {guideOpen && (
        <Guide onClose={() => setGuideOpen(false)} />
      )}

      <GlobalTooltip />
    </>
  );
}
