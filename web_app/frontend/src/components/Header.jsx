import React from "react";
import { ShieldCheck, RefreshCw, Sun, Moon, Search } from "lucide-react";

export default function Header({ 
  stats, 
  onSync, 
  isSyncing, 
  theme, 
  onToggleTheme, 
  searchTerm, 
  onSearchChange 
}) {
  return (
    <header className="glass-card" style={{ padding: "16px 24px", marginBottom: "24px", display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: "16px" }}>
      {/* Brand Logo & Title */}
      <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
        <div style={{ background: "linear-gradient(135deg, #0284c7 0%, #38bdf8 100%)", padding: "10px", borderRadius: "10px", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <ShieldCheck size={26} color="#ffffff" />
        </div>
        <div>
          <h1 style={{ fontSize: "1.4rem", fontWeight: "700" }}>Logistics Audit AI Platform</h1>
          <p style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>Automated Cross-Document Auditing & Instant Auditor Override Engine</p>
        </div>
      </div>

      {/* Metrics Bar */}
      <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
        <div style={{ display: "flex", gap: "12px", background: "rgba(0, 0, 0, 0.15)", padding: "6px 14px", borderRadius: "10px", border: "1px solid var(--bg-card-border)" }}>
          <div style={{ textAlign: "center" }}>
            <span style={{ fontSize: "0.72rem", color: "var(--text-dim)", textTransform: "uppercase", display: "block" }}>Total</span>
            <span style={{ fontSize: "1rem", fontWeight: "700" }}>{stats.total || 0}</span>
          </div>
          <div style={{ width: "1px", background: "var(--bg-card-border)" }}></div>
          <div style={{ textAlign: "center" }}>
            <span style={{ fontSize: "0.72rem", color: "var(--status-passed)", textTransform: "uppercase", display: "block" }}>Passed</span>
            <span style={{ fontSize: "1rem", fontWeight: "700", color: "var(--status-passed)" }}>{stats.passed || 0}</span>
          </div>
          <div style={{ width: "1px", background: "var(--bg-card-border)" }}></div>
          <div style={{ textAlign: "center" }}>
            <span style={{ fontSize: "0.72rem", color: "var(--status-failed)", textTransform: "uppercase", display: "block" }}>Failed</span>
            <span style={{ fontSize: "1rem", fontWeight: "700", color: "var(--status-failed)" }}>{stats.failed || 0}</span>
          </div>
          <div style={{ width: "1px", background: "var(--bg-card-border)" }}></div>
          <div style={{ textAlign: "center" }}>
            <span style={{ fontSize: "0.72rem", color: "var(--status-resolved)", textTransform: "uppercase", display: "block" }}>Resolved</span>
            <span style={{ fontSize: "1rem", fontWeight: "700", color: "var(--status-resolved)" }}>{stats.resolved || 0}</span>
          </div>
        </div>

        {/* Sync Button */}
        <button 
          className="btn btn-primary" 
          onClick={onSync} 
          disabled={isSyncing}
          style={{ opacity: isSyncing ? 0.7 : 1, cursor: isSyncing ? "not-allowed" : "pointer" }}
        >
          <RefreshCw size={16} className={isSyncing ? "spin-icon" : ""} />
          {isSyncing ? "Syncing Drive PDFs..." : "Sync New Documents"}
        </button>

        {/* Theme Toggle */}
        <button className="btn btn-secondary" onClick={onToggleTheme} style={{ padding: "8px 12px" }} title="Toggle Theme">
          {theme === "dark" ? <Sun size={18} color="#f59e0b" /> : <Moon size={18} color="#0284c7" />}
        </button>
      </div>
    </header>
  );
}
