import React from "react";
import { ShieldCheck, RefreshCw, Sun, Moon, LayoutGrid, Bot } from "lucide-react";

export default function Header({ 
  stats, 
  onSync, 
  isSyncing, 
  theme, 
  onToggleTheme, 
  viewMode = "canvas", 
  onViewModeChange 
}) {
  return (
    <header className="glass-card" style={{ padding: "16px 24px", marginBottom: "20px", display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: "16px" }}>
      {/* Brand Logo & Title */}
      <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
        <div style={{ background: "linear-gradient(135deg, #0284c7 0%, #38bdf8 100%)", padding: "10px", borderRadius: "10px", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <ShieldCheck size={26} color="#ffffff" />
        </div>
        <div>
          <h1 style={{ fontSize: "1.3rem", fontWeight: "700", margin: 0 }}>Logistics Audit AI Platform</h1>
          <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", margin: 0 }}>Automated Cross-Document Auditing & Google ADK Agent Canvas</p>
        </div>
      </div>

      {/* Dual-Mode Workspace Switcher Toggle */}
      <div style={{ display: "flex", alignItems: "center", background: "rgba(0, 0, 0, 0.25)", padding: "4px", borderRadius: "12px", border: "1px solid var(--bg-card-border)" }}>
        <button
          type="button"
          onClick={() => onViewModeChange && onViewModeChange("canvas")}
          style={{
            padding: "8px 16px",
            borderRadius: "10px",
            fontWeight: "600",
            fontSize: "0.85rem",
            cursor: "pointer",
            border: "none",
            background: viewMode === "canvas" ? "linear-gradient(135deg, #8b5cf6 0%, #ec4899 100%)" : "transparent",
            color: viewMode === "canvas" ? "#ffffff" : "var(--text-muted)",
            display: "flex",
            alignItems: "center",
            gap: "8px",
            transition: "all 0.2s ease",
            boxShadow: viewMode === "canvas" ? "0 4px 12px rgba(139, 92, 246, 0.3)" : "none"
          }}
        >
          <Bot size={16} /> Agent Canvas
        </button>
        <button
          type="button"
          onClick={() => onViewModeChange && onViewModeChange("grid")}
          style={{
            padding: "8px 16px",
            borderRadius: "10px",
            fontWeight: "600",
            fontSize: "0.85rem",
            cursor: "pointer",
            border: "none",
            background: viewMode === "grid" ? "linear-gradient(135deg, #8b5cf6 0%, #ec4899 100%)" : "transparent",
            color: viewMode === "grid" ? "#ffffff" : "var(--text-muted)",
            display: "flex",
            alignItems: "center",
            gap: "8px",
            transition: "all 0.2s ease",
            boxShadow: viewMode === "grid" ? "0 4px 12px rgba(139, 92, 246, 0.3)" : "none"
          }}
        >
          <LayoutGrid size={16} /> Grid Dashboard
        </button>
      </div>

      {/* Metrics Bar & Actions */}
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
          {isSyncing ? "Syncing..." : "Sync Drive"}
        </button>

        {/* Theme Toggle */}
        <button className="btn btn-secondary" onClick={onToggleTheme} style={{ padding: "8px 12px" }} title="Toggle Theme">
          {theme === "dark" ? <Sun size={18} color="#f59e0b" /> : <Moon size={18} color="#0284c7" />}
        </button>
      </div>
    </header>
  );
}
