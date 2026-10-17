import { useEffect, useRef, useState } from "react";
import { TENANTS } from "../api.js";

export default function Header({
  tenantKey, onTenant, onSeed, onReset, health, theme, onToggleTheme, taskCount, onOpenBoard, onOpenGraph, onOpenGuide, onNewChat,
}) {
  const [adminOpen, setAdminOpen] = useState(false);
  const adminRef = useRef(null);

  // Close the Admin menu when the user clicks anywhere outside it or presses Escape
  useEffect(() => {
    if (!adminOpen) return;
    const onDown = (e) => {
      if (e.key === "Escape") {
        setAdminOpen(false);
      } else if (adminRef.current && !adminRef.current.contains(e.target)) {
        setAdminOpen(false);
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onDown);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onDown);
    };
  }, [adminOpen]);

  const runAdmin = (action) => {
    setAdminOpen(false);
    action();
  };

  return (
    <header className="app-header">
      <div className="header-left">
        <div className="logo-badge">
          <img src="/ui/favicon-96x96.png" alt="" className="logo-icon" />
          <span>OpsMemory</span>
        </div>
        <span className="version-tag">v0.1.0</span>
      </div>
      <div className="header-right">
        <label htmlFor="tenant-select" className="tenant-label">Tenant:</label>
        <div
          className="tooltip-wrap"
          data-tooltip="Tenant Isolation: Switch between isolated tenant graphs (Acme Corp vs Beta Labs). Memories and incidents never leak across tenants."
          data-tooltip-pos="bottom"
        >
          <select id="tenant-select" className="tenant-select" value={tenantKey} onChange={(e) => onTenant(e.target.value)}>
            {TENANTS.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
          </select>
        </div>

        <button
          id="header-new-chat-btn"
          className="btn btn-primary header-new-chat-btn"
          onClick={onNewChat}
          data-tooltip="Start New Chat Session: Clears current transcript to test Cross-Chat Persistent Memory. Memories learned in prior chats remain available in FalkorDB!"
          data-tooltip-pos="bottom"
        >
          + New Chat
        </button>

        <button
          className="btn btn-secondary"
          onClick={onOpenGraph}
          data-tooltip="Interactive FalkorDB Graph: Visualizes service dependencies, incident nodes, and episodic/semantic/procedural memory relationships in real time."
          data-tooltip-pos="bottom"
        >
          Memory Graph
        </button>

        <button
          className="btn btn-secondary"
          onClick={onOpenBoard}
          data-tooltip="Task Board & Multi-Agent Handoffs: View active tasks claimed via Cypher leases, live triage-to-resolver-to-curator handoffs, and memory inspection."
          data-tooltip-pos="bottom"
        >
          Board <span className="count">{taskCount}</span>
        </button>

        <button
          className="btn btn-secondary"
          onClick={onOpenGuide}
          data-tooltip="Interactive Documentation: Complete walkthrough of Track 2 architecture, agent coordination relay, and evaluation guide."
          data-tooltip-pos="bottom"
        >
          Guide
        </button>

        <div className="admin-menu" ref={adminRef}>
          <button
            id="admin-menu-btn"
            className={`btn btn-secondary ${adminOpen ? "active" : ""}`}
            aria-haspopup="menu"
            aria-expanded={adminOpen}
            onClick={() => setAdminOpen((v) => !v)}
            data-tooltip={adminOpen ? undefined : "Admin Controls: Seed deterministic incident fixtures or wipe tenant data. Requires ADMIN_API_KEY for privilege separation."}
            data-tooltip-pos="bottom"
          >
            Admin &#9662;
          </button>
          {adminOpen && (
            <div className="admin-dropdown" role="menu">
              <button
                className="admin-item"
                role="menuitem"
                onClick={() => runAdmin(onSeed)}
                data-tooltip="Seed Demo Fixtures: Loads standardized incidents (inc-101), dependencies, and runbooks into FalkorDB."
                data-tooltip-pos="left"
              >
                Seed Fixtures
              </button>
              <button
                className="admin-item danger"
                role="menuitem"
                onClick={() => runAdmin(onReset)}
                data-tooltip="Purge Tenant Data: Completely clears all graph memories, tasks, and conversations for this tenant."
                data-tooltip-pos="left"
              >
                Reset Data
              </button>
            </div>
          )}
        </div>

        <button
          className="btn btn-secondary theme-toggle"
          onClick={onToggleTheme}
          aria-label="Toggle light or dark theme"
          data-tooltip="Theme Switcher: Toggle between tactile parchment light mode and dark espresso journal mode."
          data-tooltip-pos="bottom"
        >
          {theme === "dark" ? "\u2600" : "\u263e"}
        </button>
      </div>
    </header>
  );
}
