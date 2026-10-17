import { useEffect, useRef, useState } from "react";
import { getConversations } from "../api.js";

function Paths({ paths }) {
  if (!Array.isArray(paths) || paths.length === 0) return null;
  return (
    <div className="paths">
      {paths.map((p, i) => {
        const segments = Array.isArray(p)
          ? p
          : typeof p === "string" && p.includes(" -> ")
          ? p.split(" -> ")
          : typeof p === "string" && p.includes(" DEPENDS_ON ")
          ? p.split(" ")
          : [p];
        return (
          <div className="path" key={i}>
            {segments.map((x, j) =>
              j % 2 === 0
                ? <span className="path-node" key={j}>{String(x)}</span>
                : <span className="path-rel" key={j}>→ {String(x)} →</span>
            )}
          </div>
        );
      })}
    </div>
  );
}

function LearnedBlock({ learned }) {
  if (!learned) return null;
  const created = learned.created || [];
  const superseded = learned.superseded || [];
  const tasks = learned.tasks_created || [];
  if (created.length === 0 && superseded.length === 0 && tasks.length === 0) return null;

  return (
    <div className="learned-turn">
      <div className="learned-turn-title">Learned this turn</div>
      {created.length > 0 && (
        <div className="learned-group">
          <span className="learned-label">Memories:</span>
          {created.map((c) => (
            <span className="learned-chip learned-created" key={c.id} title={c.id}>
              + {c.title}
            </span>
          ))}
        </div>
      )}
      {superseded.length > 0 && (
        <div className="learned-group">
          <span className="learned-label">Superseded:</span>
          {superseded.map((s, i) => (
            <span className="learned-chip learned-superseded" key={s.old_id || i} title={`${s.old_id} → ${s.new_id}`}>
              ↷ {s.title}
            </span>
          ))}
        </div>
      )}
      {tasks.length > 0 && (
        <div className="learned-group">
          <span className="learned-label">Tasks:</span>
          {tasks.map((t) => (
            <span className="learned-chip learned-task" key={t.id} title={t.id}>
              ⚡ {t.task_type}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function Message({ m }) {
  if (m.role === "user") return <div className="message user-message">{m.text}</div>;
  if (m.pending) {
    return (
      <div className="message assistant-message">
        <span className="typing"><i /><i /><i />Querying OpsMemory graph</span>
      </div>
    );
  }
  return (
    <div className="message assistant-message">
      <p className="answer">{m.text}</p>
      <Paths paths={m.paths} />
      <LearnedBlock learned={m.learned} />
      {m.citations?.length > 0 && (
        <div className="citations"><strong>Citations:</strong> {m.citations.join(", ")}</div>
      )}
    </div>
  );
}

/** Inline modal listing past conversations for the current tenant. */
function HistoryModal({ tenantKey, onLoad, onClose }) {
  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getConversations(tenantKey)
      .then((data) => { if (!cancelled) setItems(data); })
      .catch((e) => { if (!cancelled) setError(e.message); });
    return () => { cancelled = true; };
  }, [tenantKey]);

  return (
    <div className="history-overlay" role="dialog" aria-modal="true" aria-label="Conversation history">
      <div className="history-modal">
        <div className="history-modal-head">
          <span className="history-modal-title">History</span>
          <button id="history-close-btn" className="btn btn-secondary btn-sm" onClick={onClose}>✕</button>
        </div>
        <div className="history-modal-body">
          {error && <p className="history-error">{error}</p>}
          {!error && items === null && <p className="history-loading">Loading…</p>}
          {items && items.length === 0 && (
            <p className="history-empty">No past conversations for this tenant.</p>
          )}
          {items && items.length > 0 && (
            <ul className="history-list">
              {items.map((conv) => (
                <li key={conv.id}>
                  <button
                    id={`history-conv-${conv.id.slice(-8)}`}
                    className="history-item"
                    onClick={() => { onLoad(conv.id); onClose(); }}
                  >
                    <span className="history-item-preview">
                      {conv.preview || <em>No messages</em>}
                    </span>
                    <span className="history-item-meta">
                      <span className="history-item-id">{conv.id.slice(-8)}</span>
                      <span className="history-item-count">{conv.turn_count} turn{conv.turn_count !== 1 ? "s" : ""}</span>
                      <span className="history-item-date">
                        {conv.created_at ? new Date(conv.created_at).toLocaleString() : ""}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

export default function ChatPanel({ messages, onSend, conversationId, tenantKey, onNewConversation, onLoadConversation }) {
  const [input, setInput] = useState("");
  const [historyOpen, setHistoryOpen] = useState(false);
  const endRef = useRef(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const submit = (e) => {
    e.preventDefault();
    const msg = input.trim();
    if (!msg) return;
    onSend(msg);
    setInput("");
  };

  // Short display ID: last 8 chars of the conversation ID, or "No session"
  const shortId = conversationId ? conversationId.slice(-8) : null;

  return (
    <section className="panel chat-panel" aria-labelledby="chat-heading">
      <div className="panel-header">
        <h2 id="chat-heading">Conversation &amp; Incident Triage</h2>
        <div className="chat-header-actions">
          <button
            id="new-conversation-btn"
            className="btn btn-secondary btn-sm"
            onClick={onNewConversation}
            title="Start a new conversation"
          >
            + New
          </button>
          <button
            id="history-btn"
            className="btn btn-secondary btn-sm"
            onClick={() => setHistoryOpen(true)}
            title="Browse past conversations"
          >
            History
          </button>
          <span className="badge" title={conversationId || "No active session"}>
            {shortId ? shortId : "No session"}
          </span>
        </div>
      </div>
      <div className="chat-messages">
        <div className="message system-message">
          <p>Welcome to <strong>OpsMemory</strong>. Ask about prior incidents (e.g. <code>inc-101</code>), current service facts, or runbooks, or report a new incident.</p>
        </div>
        {messages.map((m) => <Message key={m.id} m={m} />)}
        <div ref={endRef} />
      </div>
      <form className="chat-input-bar" onSubmit={submit}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about an incident, a service, or a runbook"
          autoComplete="off"
          required
        />
        <button type="submit" className="btn btn-primary">Send</button>
      </form>

      {historyOpen && (
        <HistoryModal
          tenantKey={tenantKey}
          onLoad={onLoadConversation}
          onClose={() => setHistoryOpen(false)}
        />
      )}
    </section>
  );
}
