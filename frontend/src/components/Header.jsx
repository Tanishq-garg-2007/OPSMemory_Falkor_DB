import { useEffect, useRef, useState } from "react";
import { TENANTS } from "../api.js";

export default function Header({
  tenantKey, onTenant, onSeed, onReset, health, theme, onToggleTheme, taskCount, onOpenBoard, onOpenGraph, onOpenGuide,
}) {
  const [adminOpen, setAdminOpen] = useState(false);
  const adminRef = useRef(null);

  // Close the Admin menu when the user clicks anywhere outside it
  useEffect(() => {
    if (!adminOpen) return;
    const onDown = (e) => {
      if (adminRef.current && !adminRef.current.contains(e.target)) setAdminOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [adminOpen]);

  const runAdmin = (action) => {
    setAdminOpen(false);
    action();
  };

  return (
    <header className="app-header">
      <div className="header-left">
        <div className="logo-badge">⚡ OpsMemory</div>
        <span className="version-tag">v0.1.0</span>
      </div>
      <div className="header-right">
        <label htmlFor="tenant-select" className="tenant-label">Tenant:</label>
        <select id="tenant-select" className="tenant-select" value={tenantKey} onChange={(e) => onTenant(e.target.value)}>
          {TENANTS.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
        </select>

        <button className="btn btn-primary" onClick={onOpenGraph}>Memory Graph</button>

        <button className="btn btn-secondary" onClick={onOpenBoard}>
          Board <span className="count">{taskCount}</span>
        </button>

        <button className="btn btn-secondary" onClick={onOpenGuide}>
          Guide
        </button>

        <div className="admin-menu" ref={adminRef}>
          <button
            className="btn btn-secondary"
            aria-haspopup="menu"
            aria-expanded={adminOpen}
            onClick={() => setAdminOpen((v) => !v)}
          >
            Admin ▾
          </button>
          {adminOpen && (
            <div className="admin-dropdown" role="menu">
              <button role="menuitem" onClick={() => runAdmin(onSeed)}>Seed Fixtures</button>
              <button role="menuitem" className="danger" onClick={() => runAdmin(onReset)}>Reset Data</button>
            </div>
          )}
        </div>

        <div className={`status-indicator ${health.ok ? "connected" : ""}`}>
          <span className="status-dot" />
          <span>{health.text}</span>
        </div>

        <button
          className="theme-toggle"
          type="button"
          onClick={onToggleTheme}
          aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          title="Toggle light/dark mode"
        >
          {theme === "dark" ? (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>
          ) : (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" /></svg>
          )}
        </button>
      </div>
    </header>
  );
}